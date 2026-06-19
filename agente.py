import os
import json
import feedparser
import requests
import google.generativeai as genai
from datetime import datetime, timezone
from database import query, execute

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

MODELOS_PREFERIDOS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
]

def detectar_modelo():
    """Retorna o primeiro modelo preferido disponível na API."""
    try:
        disponiveis = [
            m.name.replace("models/", "")
            for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
        for preferido in MODELOS_PREFERIDOS:
            if preferido in disponiveis:
                print(f"[MODELO] Usando: {preferido}")
                return preferido
        if disponiveis:
            print(f"[MODELO] Fallback para: {disponiveis[0]}")
            return disponiveis[0]
    except Exception as e:
        print(f"[MODELO] Erro ao listar modelos: {e}")
    return "gemini-2.0-flash"

MODELO_ATIVO = detectar_modelo()

PROMPT_SISTEMA = """Você é um analista político especializado em assessorar a Liderança da Oposição na Câmara dos Deputados do Brasil.

Sua tarefa é analisar notícias e decidir se elas são relevantes para ações parlamentares da oposição. O escopo é amplo: além de política, também interessam notícias de segurança pública, saúde, educação, economia, crimes, corrupção, direitos civis e qualquer tema que possa fundamentar uma ação parlamentar.

Para cada notícia, responda APENAS com um JSON válido neste formato:
{
  "relevante": true ou false,
  "categoria": "uma das categorias abaixo ou null",
  "tipo_acao": "um dos tipos abaixo ou null",
  "acao_sugerida": "texto objetivo descrevendo a ação (máx. 120 chars) ou null",
  "justificativa": "por que é relevante ou irrelevante (máx. 200 chars)"
}

Categorias possíveis:
- "Gastos públicos / corrupção"
- "Segurança pública e crimes"
- "Saúde pública"
- "Educação"
- "Economia e emprego"
- "Direitos e liberdades civis"
- "Meio ambiente"
- "Política externa"
- "Reforma institucional"
- "Infraestrutura e serviços públicos"
- "Outros"

Tipos de ação parlamentar:
- "Requerimento de informações"
- "Requerimento de audiência pública"
- "Nota à imprensa"
- "Projeto de Lei"
- "PEC"
- "Ofício"
- "Denúncia ao TCU/MPF"
- "Requerimento de convocação"

Marque como relevante sempre que a notícia revelar: falha do governo, omissão de órgão público, dado preocupante sobre serviço público, escândalo, crime com envolvimento de agente público, ou qualquer situação que justifique fiscalização parlamentar."""


def coletar_noticias():
    """Coleta notícias de todas as fontes ativas via RSS."""
    fontes = query("SELECT * FROM fontes WHERE ativa = TRUE")
    print(f"[COLETA] {len(fontes)} fontes ativas encontradas.")
    total_novas = 0

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    for fonte in fontes:
        try:
            print(f"[COLETA] Buscando: {fonte['nome']} → {fonte['url_rss']}")
            # Busca manual com headers de navegador para evitar bloqueio 405/403
            resp = requests.get(fonte["url_rss"], headers=HEADERS, timeout=15)
            print(f"[COLETA] {fonte['nome']}: HTTP {resp.status_code}")
            if resp.status_code != 200:
                print(f"[COLETA] Pulando {fonte['nome']} — status {resp.status_code}")
                continue
            feed = feedparser.parse(resp.content)
            print(f"[COLETA] {fonte['nome']}: {len(feed.entries)} entradas no feed")
            for entry in feed.entries[:20]:  # máximo 20 por fonte
                url = entry.get("link", "")
                titulo = entry.get("title", "").strip()
                resumo = entry.get("summary", entry.get("description", "")).strip()
                # Limpar HTML básico do resumo
                resumo = resumo.replace("<p>", "").replace("</p>", " ").strip()
                if len(resumo) > 500:
                    resumo = resumo[:500] + "..."

                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                if not url or not titulo:
                    continue

                # Deduplicação por URL
                existe = query(
                    "SELECT id FROM noticias WHERE url = %s",
                    (url,),
                    fetchall=False
                )
                if existe:
                    continue  # já visto

                execute(
                    """INSERT INTO noticias (fonte_id, url, titulo, resumo, publicada_em)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (fonte["id"], url, titulo, resumo, pub_date)
                )
                total_novas += 1
                print(f"[COLETA] Nova: {titulo[:80]}")

        except Exception as e:
            print(f"[ERRO] Fonte {fonte['nome']}: {e}")

    print(f"[COLETA] {total_novas} novas notícias coletadas.")
    return total_novas


def analisar_noticias():
    """Passa notícias não processadas pelo LLM Gemini para classificação."""
    noticias = query(
        """SELECT n.*, f.nome as fonte_nome
           FROM noticias n
           JOIN fontes f ON f.id = n.fonte_id
           WHERE n.processada = FALSE
           ORDER BY n.coletada_em DESC
           LIMIT 100"""
    )

    if not noticias:
        print("[ANÁLISE] Nenhuma notícia pendente.")
        return 0

    model = genai.GenerativeModel(MODELO_ATIVO)
    analisadas = 0

    for noticia in noticias:
        try:
            prompt = f"""Fonte: {noticia['fonte_nome']}
Título: {noticia['titulo']}
Resumo: {noticia['resumo'] or 'Sem resumo disponível'}

Analise esta notícia conforme as instruções."""

            response = model.generate_content(
                [PROMPT_SISTEMA, prompt],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=400,
                )
            )

            raw = response.text.strip()
            # Limpar possíveis marcadores de código
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            resultado = json.loads(raw)

            execute(
                """INSERT INTO briefings
                   (noticia_id, relevante, categoria, acao_sugerida, justificativa, tipo_acao)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    noticia["id"],
                    resultado.get("relevante", False),
                    resultado.get("categoria"),
                    resultado.get("acao_sugerida"),
                    resultado.get("justificativa"),
                    resultado.get("tipo_acao"),
                )
            )
            execute("UPDATE noticias SET processada = TRUE WHERE id = %s", (noticia["id"],))
            analisadas += 1

        except Exception as e:
            print(f"[ERRO] Notícia {noticia['id']}: {e}")
            # Marca como processada mesmo com erro para não travar o loop
            execute("UPDATE noticias SET processada = TRUE WHERE id = %s", (noticia["id"],))

    print(f"[ANÁLISE] {analisadas} notícias analisadas.")
    return analisadas


def rodar_ciclo_completo():
    """Executa um ciclo completo: coleta + análise."""
    print(f"[AGENTE] Iniciando ciclo: {datetime.now().isoformat()}")
    coletar_noticias()
    # Analisa tudo que estiver pendente, independente de ter coletado novidades agora
    pendentes = query("SELECT COUNT(*) as total FROM noticias WHERE processada = FALSE", fetchall=False)
    total_pendentes = pendentes["total"] if pendentes else 0
    print(f"[AGENTE] {total_pendentes} notícias pendentes de análise.")
    if total_pendentes > 0:
        analisar_noticias()
    print(f"[AGENTE] Ciclo concluído.")
