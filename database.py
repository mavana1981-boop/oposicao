import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
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
                    gerado_em TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            # Fontes padrão
            cur.execute("""
                INSERT INTO fontes (nome, url_rss) VALUES
                    ('Agência Câmara', 'https://agencia.camara.leg.br/agencia/rss/rss-politica.xml'),
                    ('Agência Senado', 'https://www12.senado.leg.br/noticias/rss/ultimas'),
                    ('G1 Política', 'https://g1.globo.com/rss/g1/politica/'),
                    ('Poder360', 'https://www.poder360.com.br/feed/'),
                    ('Metrópoles Política', 'https://www.metropoles.com/brasil/politica-brasil/feed')
                ON CONFLICT DO NOTHING;
            """)
        conn.commit()

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
