# Monitor Legislativo – Liderança da Oposição

Agente de monitoramento de notícias políticas com análise por IA para subsidiar
proposições legislativas e requerimentos da Liderança da Oposição na Câmara.

## Como funciona

1. **Coleta automática** — a cada 2 horas o agente busca notícias via RSS dos portais configurados
2. **Deduplicação** — notícias já vistas são ignoradas automaticamente
3. **Análise por IA** — o Gemini classifica cada notícia: relevante? qual ação parlamentar cabe?
4. **Briefing** — interface web exibe apenas o que importa, com ação sugerida e justificativa

## Fontes padrão incluídas

- Agência Câmara
- Agência Senado
- G1 Política
- Poder360
- Metrópoles Política

Novas fontes podem ser adicionadas pela interface em `/fontes`.

## Deploy no Railway

### 1. Criar projeto no Railway

```bash
railway login
railway init
railway up
```

### 2. Adicionar PostgreSQL

No painel do Railway: **New** → **Database** → **PostgreSQL**

O Railway injeta `DATABASE_URL` automaticamente.

### 3. Configurar variáveis de ambiente

No painel do Railway → **Variables**:

```
GEMINI_API_KEY=sua_chave_do_google_ai_studio
```

Obtenha a chave gratuitamente em: https://aistudio.google.com/app/apikey

### 4. Deploy

O Railway detecta o `Procfile` e faz o deploy automaticamente.
O banco é inicializado automaticamente na primeira execução.

## Desenvolvimento local

```bash
pip install -r requirements.txt
cp .env.example .env
# preencher .env com suas credenciais

python app.py
# acesse http://localhost:5000
```

## Estrutura

```
├── app.py          # Flask + rotas + scheduler
├── agente.py       # Lógica de coleta RSS e análise Gemini
├── database.py     # Conexão PostgreSQL e inicialização
├── templates/
│   ├── index.html  # Tela de briefings
│   └── fontes.html # Gerenciamento de fontes RSS
├── requirements.txt
├── Procfile
└── railway.toml
```

## Tipos de ação sugeridos pelo agente

- Requerimento de informações
- Requerimento de audiência pública
- Nota à imprensa
- Projeto de Lei / PEC
- Ofício
- Denúncia ao TCU/MPF
