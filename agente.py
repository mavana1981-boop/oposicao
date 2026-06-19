import os
import json
import feedparser
import requests
import google.generativeai as genai
from datetime import datetime, timezone
from database import query, execute

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

MODELOS_PREFERIDOS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
]

def detectar_modelo():
    try:
        disponiveis = [
            m.name.replace("models/", "")
            for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
        print(f"[MODELO] Disponíveis: {disponiveis}")
        for preferido in MODELOS_PREFERIDOS:
            if preferido in disponiveis:
                print(f"[MODELO] Selecionado: {preferido}")
                return preferido
        if disponiveis:
            print(f"[MODELO] Fallback para: {disponiveis[0]}")
            return disponiveis[0]
    except Exception as e:
        print(f"[MODELO] Erro ao listar: {e}")
    return "gemini-1.5-flash"

MODELO_ATIVO = detectar_modelo()

def get_model():
    return genai.GenerativeModel(MODELO_ATIVO)


PROMPT_SISTEMA = """Você é um analista político especializado em assessorar a Liderança da Oposição na Câmara dos Deputados do Brasil.

Sua tarefa é analisar notícias e decidir se elas são relevantes para ações parlamentares da oposição. O escopo é amplo: além de política, também interessam notícias de segurança pública, saúde, educação, economia, crimes, corrupção, direitos civis e qualquer tema que possa fundamentar uma ação parlamentar.

Responda APENAS com JSON puro, sem markdown, sem texto antes ou depois, sem blocos de código.

Formato obrigatório:
{"relevante": true, "categoria": "Saúde pública", "tipo_acao": "Requerimento de informações", "acao_sugerida": "Texto curto aqui", "justificativa": "Texto curto aqui"}

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

Marque relevante=true sempre que a notícia revelar falha do governo, omissão de órgão público, dado preocupante sobre serviço público, escândalo, crime com envolvimento de agente público, ou qualquer situação que justifique fiscalização parlamentar.

Se não for relevante: {"relevante": false, "categoria": null, "tipo_acao": null, "acao_sugerida": null, "justificativa": "Breve motivo"}"""


def extrair_json(texto):
    """Tenta extrair JSON válido de uma string com possível lixo ao redor."""
    texto = texto.strip()
    # Remove blocos markdown
    if "```" in texto:
        for bloco in texto.split("```"):
            bloco = bloco.strip().lstrip("json").strip()
            if bloco.startswith("{"):
                texto = bloco
                break
    # Pega só o trecho entre { }
    inicio = texto.find("{")
    fim = texto.rfind("}") + 1
    if inicio >= 0 and fim > inicio:
        texto = texto[inicio:fim]
    return json.loads(texto)


def analisar_noticia(noticia, model):
    """Analisa uma notícia e retorna o dict resultado."""
    prompt = (
        f"Fonte: {noticia['fonte_nome']}\n"
        f"Título: {noticia['titulo']}\n"
        f"Resumo: {noticia['resumo'] or 'Sem resumo'}\n\n"
        f"Responda APENAS com JSON puro conforme o formato solicitado."
    )
    response = model.generate_content(
        f"{PROMPT_SISTEMA}\n\n{prompt}",
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=1024,
        )
    )
    return extrair_json(response.text)


def coletar_noticias():
    fontes = query("SELECT * FROM fontes WHERE ativa = TRUE")
    print(f"[COLETA] {len(fontes)} fontes ativas.")
    total_novas = 0

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    for fonte in fontes:
        try:
            print(f"[COLETA] Buscando: {fonte['nome']} → {fonte['url_rss']}")
            resp = requests.get(fonte["url_rss"], headers=HEADERS, timeout=15)
            print(f"[COLETA] {fonte['nome']}: HTTP {resp.status_code}")
            if resp.status_code != 200:
                continue
            feed = feedparser.parse(resp.content)
            print(f"[COLETA] {fonte['nome']}: {len(feed.entries)} entradas")
            for entry in feed.entries[:20]:
                url = entry.get("link", "")
                titulo = entry.get("title", "").strip()
                resumo = entry.get("summary", entry.get("description", "")).strip()
                resumo = resumo.replace("<p>", "").replace("</p>", " ").strip()
                if len(resumo) > 500:
                    resumo = resumo[:500] + "..."
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                if not url or not titulo:
                    continue
                existe = query("SELECT id FROM noticias WHERE url = %s", (url,), fetchall=False)
                if existe:
                    continue
                execute(
                    "INSERT INTO noticias (fonte_id, url, titulo, resumo, publicada_em) VALUES (%s,%s,%s,%s,%s)",
                    (fonte["id"], url, titulo, resumo, pub_date)
                )
                total_novas += 1
                print(f"[COLETA] Nova: {titulo[:80]}")
        except Exception as e:
            print(f"[ERRO] Fonte {fonte['nome']}: {e}")

    print(f"[COLETA] {total_novas} novas notícias coletadas.")
    return total_novas


def analisar_noticias():
    global MODELO_ATIVO

    noticias = query(
        """SELECT n.*, f.nome as fonte_nome
           FROM noticias n
           JOIN fontes f ON f.id = n.fonte_id
           WHERE n.processada = FALSE
           ORDER BY n.coletada_em DESC
           LIMIT 20"""
    )

    if not noticias:
        print("[ANÁLISE] Nenhuma notícia pendente.")
        return 0

    print(f"[ANÁLISE] Iniciando análise de {len(noticias)} notícias com modelo {MODELO_ATIVO}.")
    model = get_model()
    analisadas = 0
    erros_parse = 0

    for noticia in noticias:
        try:
            resultado = analisar_noticia(noticia, model)

            execute(
                """INSERT INTO briefings
                   (noticia_id, relevante, categoria, acao_sugerida, justificativa, tipo_acao)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
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
            relevante = "✓ RELEVANTE" if resultado.get("relevante") else "✗ descartada"
            print(f"[ANÁLISE] {relevante} | {noticia['titulo'][:70]}")

        except Exception as e:
            erro = str(e)
            print(f"[ERRO] Notícia {noticia['id']} ({noticia['titulo'][:50]}): {erro[:120]}")

            if "no longer available" in erro or ("404" in erro and "model" in erro.lower()):
                print("[MODELO] Redetectando...")
                MODELO_ATIVO = detectar_modelo()
                model = get_model()
                # Não marca como processada — tenta no próximo ciclo
            elif any(x in erro for x in ["JSONDecodeError", "Unterminated", "Expecting", "json"]):
                erros_parse += 1
                # Após 3 erros de parse seguidos, marca como processada para desbloquear
                if erros_parse >= 3:
                    execute("UPDATE noticias SET processada = TRUE WHERE id = %s", (noticia["id"],))
                    erros_parse = 0
            else:
                execute("UPDATE noticias SET processada = TRUE WHERE id = %s", (noticia["id"],))

    print(f"[ANÁLISE] {analisadas} notícias analisadas, {analisadas} briefings inseridos.")
    return analisadas


def rodar_ciclo_completo():
    print(f"[AGENTE] Iniciando ciclo: {datetime.now().isoformat()}")
    coletar_noticias()
    pendentes = query("SELECT COUNT(*) as total FROM noticias WHERE processada = FALSE", fetchall=False)
    total = pendentes["total"] if pendentes else 0
    print(f"[AGENTE] {total} notícias pendentes de análise.")
    if total > 0:
        analisar_noticias()
    print(f"[AGENTE] Ciclo concluído.")
