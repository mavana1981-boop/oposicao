import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

FONTES_PADRAO = [
    # Grupo Globo
    ("G1 Política",         "https://g1.globo.com/rss/g1/politica/"),
    ("G1 Economia",         "https://g1.globo.com/rss/g1/economia/"),
    ("G1 Saúde",            "https://g1.globo.com/rss/g1/ciencia-e-saude/"),
    ("G1 Educação",         "https://g1.globo.com/rss/g1/educacao/"),
    # Grupo Estado
    ("Estadão Política",    "https://feeds.estadao.com.br/rss/politica"),
    ("Estadão Economia",    "https://feeds.estadao.com.br/rss/economia"),
    ("Estadão Brasil",      "https://feeds.estadao.com.br/rss/brasil"),
    # Folha de S.Paulo
    ("Folha Poder",         "https://feeds.folha.uol.com.br/poder/rss091.xml"),
    ("Folha Mercado",       "https://feeds.folha.uol.com.br/mercado/rss091.xml"),
    ("Folha Saúde",         "https://feeds.folha.uol.com.br/equilibrioesaude/rss091.xml"),
    ("Folha Educação",      "https://feeds.folha.uol.com.br/educacao/rss091.xml"),
    ("Folha Cotidiano",     "https://feeds.folha.uol.com.br/cotidiano/rss091.xml"),
    # O Antagonista
    ("O Antagonista",       "https://www.oantagonista.com/feed/"),
    # Poder360
    ("Poder360",            "https://www.poder360.com.br/feed/"),
    # Metrópoles
    ("Metrópoles Política", "https://www.metropoles.com/brasil/politica-brasil/feed"),
    ("Metrópoles Crimes",   "https://www.metropoles.com/brasil/policia/feed"),
    # CNN Brasil
    ("CNN Brasil",          "https://www.cnnbrasil.com.br/feed/"),
    # Veja
    ("Veja Brasil",         "https://veja.abril.com.br/feed/"),
]

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Criar tabelas
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fontes (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    url_rss TEXT NOT NULL,
                    ativa BOOLEAN DEFAULT TRUE,
                    criada_em TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS noticias (
                    id SERIAL PRIMARY KEY,
                    fonte_id INTEGER REFERENCES fontes(id),
                    url TEXT UNIQUE NOT NULL,
                    titulo TEXT NOT NULL,
                    resumo TEXT,
                    publicada_em TIMESTAMPTZ,
                    coletada_em TIMESTAMPTZ DEFAULT NOW(),
                    processada BOOLEAN DEFAULT FALSE
                );

                CREATE TABLE IF NOT EXISTS briefings (
                    id SERIAL PRIMARY KEY,
                    noticia_id INTEGER REFERENCES noticias(id),
                    relevante BOOLEAN NOT NULL,
                    categoria TEXT,
                    acao_sugerida TEXT,
                    justificativa TEXT,
                    tipo_acao TEXT,
                    gerado_em TIMESTAMPTZ DEFAULT NOW(),
                    status TEXT DEFAULT 'Pendente',
                    assessor TEXT
                );
            """)

            # Adicionar colunas novas se não existirem (banco já existente)
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='briefings' AND column_name='status') THEN
                        ALTER TABLE briefings ADD COLUMN status TEXT DEFAULT 'Pendente';
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='briefings' AND column_name='assessor') THEN
                        ALTER TABLE briefings ADD COLUMN assessor TEXT;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='briefings' AND column_name='acao_efetuada') THEN
                        ALTER TABLE briefings ADD COLUMN acao_efetuada TEXT;
                    END IF;
                END$$;
            """)

            # Remover Câmara e Senado (e dados vinculados)
            cur.execute("""
                DELETE FROM briefings WHERE noticia_id IN (
                    SELECT n.id FROM noticias n
                    JOIN fontes f ON f.id = n.fonte_id
                    WHERE f.nome IN ('Agência Câmara', 'Agência Senado')
                );
                DELETE FROM noticias WHERE fonte_id IN (
                    SELECT id FROM fontes WHERE nome IN ('Agência Câmara', 'Agência Senado')
                );
                DELETE FROM fontes WHERE nome IN ('Agência Câmara', 'Agência Senado');
            """)

            # Remover duplicatas de url_rss mantendo o menor id
            cur.execute("""
                DELETE FROM fontes
                WHERE id NOT IN (
                    SELECT MIN(id) FROM fontes GROUP BY url_rss
                );
            """)

            # Agora criar constraint UNIQUE com segurança
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'fontes_url_rss_key'
                    ) THEN
                        ALTER TABLE fontes ADD CONSTRAINT fontes_url_rss_key UNIQUE (url_rss);
                    END IF;
                END$$;
            """)

            # Inserir fontes padrão
            for nome, url in FONTES_PADRAO:
                cur.execute("""
                    INSERT INTO fontes (nome, url_rss)
                    VALUES (%s, %s)
                    ON CONFLICT (url_rss) DO NOTHING
                """, (nome, url))

        conn.commit()
        print("[DB] Banco inicializado com sucesso.")

def query(sql, params=None, fetchall=True):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            if fetchall:
                return cur.fetchall()
            return cur.fetchone()

def execute(sql, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
