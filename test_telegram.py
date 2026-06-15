import os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN_BOT = os.getenv("TELEGRAM_TOKEN")

print("Token carregado do .env:", TOKEN_BOT)
CHAT_ID = input("Digite o seu Chat ID numerico do Telegram para o teste: ")

url = "https://api.telegram.org/bot" + str(TOKEN_BOT) + "/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": "Conexao estabelecida com sucesso! O motor de notificacao da portaria esta online."
}

try:
    resposta = requests.post(url, json=payload, timeout=5)
    if resposta.status_code == 200:
        print("Sucesso absoluto! Verifique o seu aplicativo do Telegram.")
    else:
        print("Falha na API do Telegram. Status Code:", resposta.status_code)
        print("Resposta do servidor:", resposta.text)
except Exception as e:
    print("Erro critico de rede/timeout ao tentar alcancar o Telegram:", e)