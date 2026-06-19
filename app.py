import os
import time
import threading
from flask import Flask, render_template, jsonify, request, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def init_app():
    from database import init_db
    for tentativa in range(10):
        try:
            init_db()
            print("[DB] Banco inicializado com sucesso.")
            return
        except Exception as e:
            print(f"[DB] Tentativa {tentativa + 1}/10 falhou: {e}")
            time.sleep(3)
    print("[DB] AVISO: não foi possível inicializar o banco.")

init_app()

from database import query, execute
from agente import rodar_ciclo_completo

# Scheduler — a cada 2 horas, em thread própria, sem bloquear workers
scheduler = BackgroundScheduler()
scheduler.add_job(
    rodar_ciclo_completo,
    "interval",
    hours=2,
    id="coleta_automatica",
    max_instances=1,
    coalesce=True,
)
scheduler.start()


@app.route("/")
def index():
    categoria = request.args.get("categoria")
    tipo = request.args.get("tipo")
    status = request.args.get("status", "")
    pagina = int(request.args.get("pagina", 1))
    por_pagina = 20
    offset = (pagina - 1) * por_pagina

    filtros = "WHERE b.relevante = TRUE"
    params = []

    if categoria:
        filtros += " AND b.categoria = %s"
        params.append(categoria)
    if tipo:
        filtros += " AND b.tipo_acao = %s"
        params.append(tipo)
    if status:
        filtros += " AND COALESCE(b.status, 'Pendente') = %s"
        params.append(status)

    params_com_limit = params + [por_pagina, offset]

    briefings = query(f"""
        SELECT b.*, n.titulo, n.url, n.resumo, n.publicada_em, f.nome as fonte
        FROM briefings b
        JOIN noticias n ON n.id = b.noticia_id
        JOIN fontes f ON f.id = n.fonte_id
        {filtros}
        ORDER BY b.gerado_em DESC
        LIMIT %s OFFSET %s
    """, params_com_limit)

    total = query(f"""
        SELECT COUNT(*) as total FROM briefings b
        JOIN noticias n ON n.id = b.noticia_id
        {filtros}
    """, params, fetchall=False)

    categorias = query("""
        SELECT categoria, COUNT(*) as total
        FROM briefings WHERE relevante = TRUE AND categoria IS NOT NULL
        GROUP BY categoria ORDER BY total DESC
    """)

    tipos = query("""
        SELECT tipo_acao, COUNT(*) as total
        FROM briefings WHERE relevante = TRUE AND tipo_acao IS NOT NULL
        GROUP BY tipo_acao ORDER BY total DESC
    """)

    stats = query("""
        SELECT
            COUNT(*) FILTER (WHERE b.relevante = TRUE) as relevantes,
            COUNT(*) FILTER (WHERE b.relevante = FALSE) as descartadas,
            MAX(b.gerado_em) as ultima_atualizacao
        FROM briefings b JOIN noticias n ON n.id = b.noticia_id
    """, fetchall=False)

    total_paginas = (total["total"] // por_pagina) + 1 if total and total["total"] else 1

    return render_template("index.html",
        briefings=briefings,
        categorias=categorias,
        tipos=tipos,
        stats=stats,
        categoria_selecionada=categoria,
        tipo_selecionado=tipo,
        status_selecionado=status,
        pagina=pagina,
        total_paginas=total_paginas,
    )


@app.route("/fontes")
def fontes():
    fontes = query("SELECT * FROM fontes ORDER BY nome")
    return render_template("fontes.html", fontes=fontes)


@app.route("/fontes/adicionar", methods=["POST"])
def adicionar_fonte():
    nome = request.form.get("nome", "").strip()
    url_rss = request.form.get("url_rss", "").strip()
    if nome and url_rss:
        execute("INSERT INTO fontes (nome, url_rss) VALUES (%s, %s) ON CONFLICT (url_rss) DO NOTHING", (nome, url_rss))
    return redirect(url_for("fontes"))


@app.route("/fontes/<int:fonte_id>/toggle", methods=["POST"])
def toggle_fonte(fonte_id):
    execute("UPDATE fontes SET ativa = NOT ativa WHERE id = %s", (fonte_id,))
    return redirect(url_for("fontes"))


@app.route("/fontes/<int:fonte_id>/excluir", methods=["POST"])
def excluir_fonte(fonte_id):
    execute("DELETE FROM fontes WHERE id = %s", (fonte_id,))
    return redirect(url_for("fontes"))


@app.route("/briefing/<int:briefing_id>/atualizar", methods=["POST"])
def atualizar_briefing(briefing_id):
    status = request.form.get("status", "Pendente")
    assessor = request.form.get("assessor", "").strip()
    acao_efetuada = request.form.get("acao_efetuada", "").strip()

    # Adicionar coluna acao_efetuada se não existir (migração automática)
    from database import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name='briefings' AND column_name='acao_efetuada') THEN
                        ALTER TABLE briefings ADD COLUMN acao_efetuada TEXT;
                    END IF;
                END$$;
            """)
        conn.commit()

    execute(
        "UPDATE briefings SET status = %s, assessor = %s, acao_efetuada = %s WHERE id = %s",
        (status, assessor or None, acao_efetuada or None, briefing_id)
    )
    return redirect(request.referrer or url_for("index"))


# Flag para evitar dois ciclos simultâneos via botão
_ciclo_em_andamento = False

@app.route("/api/rodar", methods=["POST"])
def api_rodar():
    global _ciclo_em_andamento
    if _ciclo_em_andamento:
        return jsonify({"ok": False, "mensagem": "Ciclo já em andamento, aguarde."}), 429

    def executar():
        global _ciclo_em_andamento
        _ciclo_em_andamento = True
        try:
            rodar_ciclo_completo()
        finally:
            _ciclo_em_andamento = False

    # Roda em thread separada — não bloqueia o worker do gunicorn
    t = threading.Thread(target=executar, daemon=True)
    t.start()
    return jsonify({"ok": True, "mensagem": "Ciclo iniciado em background. Atualize a página em alguns minutos."})


@app.route("/api/stats")
def api_stats():
    stats = query("""
        SELECT
            (SELECT COUNT(*) FROM noticias) as total_noticias,
            (SELECT COUNT(*) FROM noticias WHERE processada = FALSE) as pendentes,
            (SELECT COUNT(*) FROM briefings WHERE relevante = TRUE) as relevantes,
            (SELECT MAX(coletada_em) FROM noticias) as ultima_coleta
    """, fetchall=False)
    return jsonify(dict(stats))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
