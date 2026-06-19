import os
from flask import Flask, render_template, jsonify, request, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from database import init_db, query, execute
from agente import rodar_ciclo_completo, coletar_noticias, analisar_noticias

load_dotenv()

app = Flask(__name__)

# Scheduler para coleta automática (a cada 2 horas)
scheduler = BackgroundScheduler()
scheduler.add_job(rodar_ciclo_completo, "interval", hours=2, id="coleta_automatica")
scheduler.start()


@app.route("/")
def index():
    categoria = request.args.get("categoria")
    tipo = request.args.get("tipo")
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

    params += [por_pagina, offset]

    briefings = query(f"""
        SELECT b.*, n.titulo, n.url, n.resumo, n.publicada_em, f.nome as fonte
        FROM briefings b
        JOIN noticias n ON n.id = b.noticia_id
        JOIN fontes f ON f.id = n.fonte_id
        {filtros}
        ORDER BY b.gerado_em DESC
        LIMIT %s OFFSET %s
    """, params)

    total = query(f"""
        SELECT COUNT(*) as total FROM briefings b
        JOIN noticias n ON n.id = b.noticia_id
        {filtros.replace('LIMIT %s OFFSET %s', '')}
    """, params[:-2], fetchall=False)

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
            COUNT(DISTINCT n.fonte_id) as fontes_ativas,
            MAX(b.gerado_em) as ultima_atualizacao
        FROM briefings b JOIN noticias n ON n.id = b.noticia_id
    """, fetchall=False)

    total_paginas = (total["total"] // por_pagina) + 1 if total else 1

    return render_template("index.html",
        briefings=briefings,
        categorias=categorias,
        tipos=tipos,
        stats=stats,
        categoria_selecionada=categoria,
        tipo_selecionado=tipo,
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
        execute("INSERT INTO fontes (nome, url_rss) VALUES (%s, %s)", (nome, url_rss))
    return redirect(url_for("fontes"))


@app.route("/fontes/<int:fonte_id>/toggle", methods=["POST"])
def toggle_fonte(fonte_id):
    execute("UPDATE fontes SET ativa = NOT ativa WHERE id = %s", (fonte_id,))
    return redirect(url_for("fontes"))


@app.route("/fontes/<int:fonte_id>/excluir", methods=["POST"])
def excluir_fonte(fonte_id):
    execute("DELETE FROM fontes WHERE id = %s", (fonte_id,))
    return redirect(url_for("fontes"))


@app.route("/api/rodar", methods=["POST"])
def api_rodar():
    try:
        rodar_ciclo_completo()
        return jsonify({"ok": True, "mensagem": "Ciclo concluído com sucesso."})
    except Exception as e:
        return jsonify({"ok": False, "mensagem": str(e)}), 500


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
    init_db()
    app.run(debug=True, port=5000)
