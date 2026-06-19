"""
Execute UMA VEZ no Railway para reorganizar as fontes no banco:
  railway run python fix_fontes.py
"""
import os
from dotenv import load_dotenv
load_dotenv()
from database import execute, query, FONTES_PADRAO

# 1. Remover Agência Câmara e Agência Senado (e noticias/briefings vinculados)
print("Removendo Agência Câmara e Agência Senado...")
fontes_remover = query(
    "SELECT id, nome FROM fontes WHERE nome IN ('Agência Câmara', 'Agência Senado')"
)
for f in fontes_remover:
    # briefings → noticias → fonte
    execute("""
        DELETE FROM briefings WHERE noticia_id IN (
            SELECT id FROM noticias WHERE fonte_id = %s
        )
    """, (f["id"],))
    execute("DELETE FROM noticias WHERE fonte_id = %s", (f["id"],))
    execute("DELETE FROM fontes WHERE id = %s", (f["id"],))
    print(f"  Removido: {f['nome']}")

# 2. Adicionar novas fontes (ON CONFLICT ignora duplicatas)
print("\nAdicionando novas fontes...")
for nome, url in FONTES_PADRAO:
    execute("""
        INSERT INTO fontes (nome, url_rss)
        VALUES (%s, %s)
        ON CONFLICT (url_rss) DO NOTHING
    """, (nome, url))
    print(f"  ✓ {nome}")

# 3. Listar estado final
print("\nFontes ativas no banco:")
fontes = query("SELECT nome, url_rss, ativa FROM fontes ORDER BY nome")
for f in fontes:
    status = "✓" if f["ativa"] else "✗"
    print(f"  {status} {f['nome']}")

print(f"\nTotal: {len(fontes)} fontes")
