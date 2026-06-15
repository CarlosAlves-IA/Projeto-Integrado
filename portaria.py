import cv2
import time
from datetime import datetime
import os
import numpy as np
import base64
from pymongo import MongoClient
import certifi
import urllib.request
from dotenv import load_dotenv
import insightface
from insightface.app import FaceAnalysis
import requests

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '2'

load_dotenv()
URI_MONGO = os.getenv("URI_MONGO")
TOKEN_BOT = os.getenv("TELEGRAM_TOKEN", "")
CAMERA_INDEX = int(os.getenv("CAMERA_PORTARIA", 1))

# TRAVA DE TEMPO (Em segundos) - Alterado para 15s para testes (Mude para 300s em producao)
COOLDOWN_SEGUNDOS = 15

client = MongoClient(URI_MONGO, tlsCAFile=certifi.where())
db = client["escola_inteligente"]
colecao_alunos = db["alunos"]
colecao_portaria = db["registro_portaria"]

face_app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
face_app.prepare(ctx_id=0, det_size=(640, 640))

def extrair_embedding(img_bgr):
    faces = face_app.get(img_bgr)
    if not faces:
        return None
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return face.normed_embedding

def cosine_distance(a, b):
    a = a / (np.linalg.norm(a) + 1e-6)
    b = b / (np.linalg.norm(b) + 1e-6)
    return float(1.0 - np.dot(a, b))

def enviar_telegram(chat_id, mensagem):
    if TOKEN_BOT != "" and chat_id != "":
        url = "https://api.telegram.org/bot" + TOKEN_BOT + "/sendMessage"
        payload = {"chat_id": chat_id, "text": mensagem}
        try:
            resposta = requests.post(url, json=payload, timeout=10)
            if resposta.status_code != 200:
                print("ERRO API TELEGRAM:", resposta.text)
        except Exception as e:
            print("ERRO DE REDE AO ENVIAR TELEGRAM:", e)
    else:
        print(f"ALERTA: Telegram não enviado. Token ou Chat ID ausente. Chat ID atual: '{chat_id}'")

alunos_banco = list(colecao_alunos.find({}))
embeddings_conhecidos = []
matriculas_conhecidas = []
nomes_conhecidos = []
chat_ids_conhecidos = []
fotos_conhecidas = []

for aluno in alunos_banco:
    foto_b64 = aluno.get("foto_base64", "")
    if foto_b64 != "":
        try:
            img_bytes = base64.b64decode(foto_b64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            emb = extrair_embedding(img_cv)
            if emb is not None:
                embeddings_conhecidos.append(emb)
                matriculas_conhecidas.append(aluno.get("matricula"))
                nomes_conhecidos.append(aluno.get("nome"))
                chat_ids_conhecidos.append(aluno.get("info_pais", ""))
                fotos_conhecidas.append(img_cv)
        except:
            pass

# Sincronizador de Memoria (Evita o bug de "Sempre Entrada" ao reiniciar)
memoria_catraca = {}
for matr in matriculas_conhecidas:
    ultimo_registro = colecao_portaria.find_one({"matricula": matr}, sort=[("timestamp", -1)])
    if ultimo_registro:
        try:
            ts_banco = datetime.fromisoformat(ultimo_registro["timestamp"]).timestamp()
            status_banco = ultimo_registro["tipo"]
        except:
            ts_banco = 0
            status_banco = "Saida"
        memoria_catraca[matr] = {"ultimo_acesso": ts_banco, "status": status_banco}
    else:
        memoria_catraca[matr] = {"ultimo_acesso": 0, "status": "Saida"}

cap = cv2.VideoCapture(CAMERA_INDEX)
ultimo_processamento = time.time()

while cap.isOpened():
    sucesso, frame = cap.read()
    if not sucesso:
        break

    tempo_atual = time.time()

    if tempo_atual - ultimo_processamento >= 1.0:
        emb_atual = extrair_embedding(frame)
        
        if emb_atual is not None and len(embeddings_conhecidos) > 0:
            distancias = [cosine_distance(emb_atual, e) for e in embeddings_conhecidos]
            idx_min = int(np.argmin(distancias))
            dist_min = distancias[idx_min]
            
            if dist_min < 0.45:
                matr = matriculas_conhecidas[idx_min]
                nome = nomes_conhecidos[idx_min]
                chat_id = chat_ids_conhecidos[idx_min]
                foto_aluno = fotos_conhecidas[idx_min]
                
                dados_aluno = memoria_catraca.get(matr, {"ultimo_acesso": 0, "status": "Saida"})
                
                # Usa a trava de 15 segundos para testes
                if tempo_atual - dados_aluno["ultimo_acesso"] > COOLDOWN_SEGUNDOS:
                    if dados_aluno["status"] == "Saida":
                        novo_status = "Entrada"
                        cor_status = (0, 255, 0)
                    else:
                        novo_status = "Saida"
                        cor_status = (0, 0, 255)
                        
                    hora_str = datetime.now().strftime('%H:%M:%S')
                    data_str = datetime.now().strftime('%d/%m/%Y')
                    
                    registro = {
                        "matricula": matr,
                        "nome": nome,
                        "tipo": novo_status,
                        "data": data_str,
                        "hora": hora_str,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    try:
                        colecao_portaria.insert_one(registro)
                        msg = f"Sistema Escolar:\nAluno(a) {nome} registrou {novo_status} as {hora_str} do dia {data_str}."
                        enviar_telegram(chat_id, msg)
                        print(msg)
                    except Exception as e:
                        print("Erro ao salvar log na portaria:", e)
                        
                    memoria_catraca[matr] = {"ultimo_acesso": tempo_atual, "status": novo_status}
                    
                    cv2.rectangle(frame, (20, 20), (320, 380), (30, 30, 30), -1)
                    cv2.rectangle(frame, (20, 20), (320, 380), cor_status, 2)
                    
                    foto_redimensionada = cv2.resize(foto_aluno, (260, 260))
                    frame[40:300, 40:300] = foto_redimensionada
                    
                    texto_status = novo_status.upper() + " RECONHECIDA"
                    cv2.putText(frame, texto_status, (40, 330), cv2.FONT_HERSHEY_SIMPLEX, 0.7, cor_status, 2)
                    
                    nome_curto = nome.split()[0]
                    cv2.putText(frame, "Aluno: " + nome_curto, (40, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                    
                    cv2.imshow("Catraca Inteligente", frame)
                    cv2.waitKey(3000)
                    
        ultimo_processamento = tempo_atual

    cv2.imshow("Catraca Inteligente", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()