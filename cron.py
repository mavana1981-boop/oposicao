"""
Serviço de cron separado no Railway.
Chama o endpoint /api/rodar do app principal a cada execução.
Configure no Railway como um Cron Job com o comando:
  python cron.py
E o schedule desejado (ex: 0 */2 * * * para a cada 2 horas)
"""
import os
import requests
import sys
from datetime import datetime

APP_URL = os.environ.get("APP_URL", "").rstrip("/")

if not APP_URL:
    print("[CRON] ERRO: variável APP_URL não definida.")
    print("[CRON] Configure APP_URL com a URL do seu app, ex: https://seu-app.up.railway.app")
    sys.exit(1)

url = f"{APP_URL}/api/rodar"
print(f"[CRON] {datetime.now().isoformat()} — Chamando {url}")

try:
    resp = requests.post(url, timeout=30)
    data = resp.json()
    print(f"[CRON] Resposta {resp.status_code}: {data.get('mensagem', '')}")
    sys.exit(0)
except Exception as e:
    print(f"[CRON] Erro: {e}")
    sys.exit(1)
