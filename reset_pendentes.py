"""
Execute no Railway para desbloquear notícias que falharam e nunca foram analisadas:
  railway run python reset_pendentes.py
"""
import os
from dotenv import load_dotenv
load_dotenv()
from database import execute, query

# Notícias marcadas como processadas mas sem briefing correspondente
resultado = query("""
    SELECT COUNT(*) as total FROM noticias n
    WHERE n.processada = TRUE
    AND NOT EXISTS (SELECT 1 FROM briefings b WHERE b.noticia_id = n.id)
""", fetchall=False)

print(f"Notícias processadas sem briefing: {resultado['total']}")

execute("""
    UPDATE noticias SET processada = FALSE
    WHERE processada = TRUE
    AND NOT EXISTS (SELECT 1 FROM briefings b WHERE b.noticia_id = id)
""")

pendentes = query("SELECT COUNT(*) as total FROM noticias WHERE processada = FALSE", fetchall=False)
print(f"Total pendentes após reset: {pendentes['total']}")
print("Pronto. Clique em 'Atualizar agora' no app para processar.")
