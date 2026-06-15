from flask import Flask, Response
import threading

app = Flask(__name__)
frame_transmissao = None

def gerar_fluxo():
    global frame_transmissao
    while True:
        if frame_transmissao is not None:
            sucesso_encode, buffer = cv2.imencode('.jpg', frame_transmissao)
            if sucesso_encode == True:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n' + b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    return Response(gerar_fluxo(), mimetype='multipart/x-mixed-replace; boundary=frame')

def iniciar_servidor():
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

import cv2
import mediapipe as mp
import time
from pymongo import MongoClient
import certifi
from datetime import datetime
import math
import os
import urllib.request
from dotenv import load_dotenv
import numpy as np
import base64
import insightface
from insightface.app import FaceAnalysis

# ─────────────────────────────────────────────
#  Configuração
# ─────────────────────────────────────────────
load_dotenv()
URI_MONGO     = os.getenv("URI_MONGO")
CAMERA_INDEX  = int(os.getenv("CAMERA_INDEX", 1))
LIMIAR_RECONHECIMENTO = float(os.getenv("LIMIAR_RECONHECIMENTO", 0.45))  # cosine distance
INTERVALO_SAVE        = int(os.getenv("INTERVALO_SAVE", 30))             # segundos entre saves

# ─────────────────────────────────────────────
#  MongoDB
# ─────────────────────────────────────────────
client        = MongoClient(URI_MONGO, tlsCAFile=certifi.where())
db            = client["escola_inteligente"]
colecao_logs  = db["logs_acesso"]
colecao_alunos = db["alunos"]

# ─────────────────────────────────────────────
#  InsightFace — buffalo_sc: leve, roda em CPU,
#  embeddings de 512 dims, ~99.7% no benchmark LFW
# ─────────────────────────────────────────────
print("[INIT] Carregando modelo InsightFace buffalo_sc...")
face_app = FaceAnalysis(
    name="buffalo_sc",
    providers=["CPUExecutionProvider"]
)
face_app.prepare(ctx_id=0, det_size=(640, 640))
print("[INIT] Modelo carregado.")

# ─────────────────────────────────────────────
#  MediaPipe — só para análise comportamental
#  (EAR, MAR, sobrancelha — sem mais assinatura geométrica)
# ─────────────────────────────────────────────
def baixar_modelo_se_necessario():
    modelo_path = "face_landmarker.task"
    url = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    if not os.path.exists(modelo_path):
        print("[INIT] Baixando modelo MediaPipe...")
        urllib.request.urlretrieve(url, modelo_path)
    return modelo_path

modelo_path   = baixar_modelo_se_necessario()
BaseOptions   = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

mp_options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=modelo_path),
    running_mode=VisionRunningMode.IMAGE,
    num_faces=1
)

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
def calcular_distancia(p1, p2):
    return math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)

def calcular_ear(olho):
    v1 = calcular_distancia(olho[1], olho[5])
    v2 = calcular_distancia(olho[2], olho[4])
    h  = calcular_distancia(olho[0], olho[3])
    if h == 0:
        h = 0.001
    return (v1 + v2) / (2.0 * h)

def cosine_distance(a, b):
    """Distância cosseno entre dois embeddings normalizados. 0 = idêntico, 2 = oposto."""
    a = a / (np.linalg.norm(a) + 1e-6)
    b = b / (np.linalg.norm(b) + 1e-6)
    return float(1.0 - np.dot(a, b))

def extrair_embedding(img_bgr):
    """Retorna o embedding (512-d) do primeiro rosto encontrado na imagem, ou None."""
    faces = face_app.get(img_bgr)
    if not faces:
        return None
    # Pega o rosto com maior bounding box (mais próximo da câmera)
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return face.normed_embedding  # já normalizado pelo InsightFace

# ─────────────────────────────────────────────
#  Carregar embeddings dos alunos cadastrados
# ─────────────────────────────────────────────
print("[INIT] Carregando alunos do banco de dados...")
alunos_banco          = list(colecao_alunos.find({}))
embeddings_conhecidos = []
matriculas_conhecidas  = []
nomes_conhecidos       = []

for aluno in alunos_banco:
    foto_b64 = aluno.get("foto_base64", "")
    if not foto_b64:
        continue
    try:
        img_bytes = base64.b64decode(foto_b64)
        nparr     = np.frombuffer(img_bytes, np.uint8)
        img_cv    = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        emb       = extrair_embedding(img_cv)
        if emb is not None:
            embeddings_conhecidos.append(emb)
            matriculas_conhecidas.append(aluno.get("matricula"))
            nomes_conhecidos.append(aluno.get("nome"))
            print(f"  ✓ Aluno carregado: {aluno.get('nome')}")
        else:
            print(f"  ✗ Nenhum rosto detectado na foto de {aluno.get('nome', 'Desconhecido')}")
    except Exception as e:
        print(f"  ✗ Erro ao processar foto de {aluno.get('nome', 'Desconhecido')}: {e}")

print(f"[INIT] {len(embeddings_conhecidos)} aluno(s) carregado(s) com sucesso.\n")

# ─────────────────────────────────────────────
#  Estado de calibração comportamental
# ─────────────────────────────────────────────
historico_estados     = []
max_historico         = 10
frames_calibracao     = 0
max_frames_calibracao = 30
soma_ear = soma_mar   = 0.0
ear_base = mar_base   = 0.0
calibrado             = False
aluno_em_calibracao   = "Desconhecido"
ultimo_save_alunos    = {}

# Overlay
nome_tela   = "Aguardando..."
estado_tela = "Analisando..."
conf_tela   = 0.0

# Cores por estado (BGR)
CORES_ESTADO = {
    "focado":    (0,   200,   0),
    "feliz":     (0,   255, 200),
    "neutro":    (200, 200, 200),
    "desatento": (0,   165, 255),
    "triste":    (255, 100, 100),
    "agressivo": (0,     0, 255),
}
#servidor 

thread_servidor = threading.Thread(target=iniciar_servidor)
thread_servidor.daemon = True
thread_servidor.start()


# ─────────────────────────────────────────────
#  Loop principal
# ─────────────────────────────────────────────
with FaceLandmarker.create_from_options(mp_options) as landmarker:
    # Tentativa de abrir a câmera com retries
    cap = None
    MAX_TENTATIVAS = 3
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        print(f"[CAM] Tentativa {tentativa}/{MAX_TENTATIVAS} — abrindo câmera no índice {CAMERA_INDEX}...")
        cap = cv2.VideoCapture(CAMERA_INDEX)
        if cap.isOpened():
            print(f"[CAM] Câmera aberta com sucesso no índice {CAMERA_INDEX}.")
            break
        print(f"[CAM] Falha ao abrir câmera na tentativa {tentativa}.")
        cap.release()
        if tentativa < MAX_TENTATIVAS:
            time.sleep(2)

    if cap is None or not cap.isOpened():
        print(f"\n[ERRO] Não foi possível abrir a câmera no índice {CAMERA_INDEX}.")
        print("       Verifique se:")
        print("       1. A câmera está conectada e reconhecida pelo Windows")
        print("       2. Nenhum outro programa está usando a câmera")
        print("       3. O índice da câmera está correto (CAMERA_INDEX no .env)")
        import sys
        sys.exit(1)

    ultimo_processamento  = time.time()
    intervalo_processamento  = 0.5   # análise comportamental a cada 0.5s
    intervalo_reconhecimento = 1.0   # reconhecimento InsightFace a cada 1s
    ultimo_reconhecimento    = 0.0

    aluno_detectado          = "Desconhecido"
    nome_detectado           = "Desconhecido"
    confianca_reconhecimento = 0.0

    print("[RUN] Sistema iniciado. Pressione 'Q' para sair.\n")

    while cap.isOpened():
        sucesso, frame = cap.read()
        if not sucesso:
            break

        tempo_atual = time.time()

        # ── Reconhecimento facial (InsightFace) — a cada 1s ──────────────
        if tempo_atual - ultimo_reconhecimento >= intervalo_reconhecimento:
            emb_atual = extrair_embedding(frame)

            if emb_atual is not None and len(embeddings_conhecidos) > 0:
                distancias = [cosine_distance(emb_atual, e) for e in embeddings_conhecidos]
                idx_min    = int(np.argmin(distancias))
                dist_min   = distancias[idx_min]

                if dist_min < LIMIAR_RECONHECIMENTO:
                    novo_aluno     = matriculas_conhecidas[idx_min]
                    novo_nome      = nomes_conhecidos[idx_min]
                    nova_confianca = round((1.0 - dist_min / LIMIAR_RECONHECIMENTO) * 100, 1)
                else:
                    novo_aluno     = "Desconhecido"
                    novo_nome      = "Desconhecido"
                    nova_confianca = 0.0
            else:
                novo_aluno     = "Desconhecido"
                novo_nome      = "Desconhecido"
                nova_confianca = 0.0

            # Reset de calibração se o aluno mudou (e é reconhecido)
            if novo_aluno != aluno_em_calibracao and novo_aluno != "Desconhecido":
                calibrado           = False
                frames_calibracao   = 0
                soma_ear = soma_mar = 0.0
                aluno_em_calibracao = novo_aluno
                historico_estados.clear()
                print(f"[CAL] Iniciando calibração para {novo_nome}...")

            aluno_detectado          = novo_aluno
            nome_detectado           = novo_nome
            confianca_reconhecimento = nova_confianca
            nome_tela                = novo_nome
            conf_tela                = nova_confianca
            ultimo_reconhecimento    = tempo_atual

        # ── Análise comportamental (MediaPipe) — a cada 0.5s ─────────────
        if tempo_atual - ultimo_processamento >= intervalo_processamento:
            rgb_frame  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image   = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            resultados = landmarker.detect(mp_image)

            if resultados.face_landmarks:
                landmarks = resultados.face_landmarks[0]

                olho_esq = [landmarks[33],  landmarks[160], landmarks[158],
                            landmarks[133], landmarks[153], landmarks[144]]
                olho_dir = [landmarks[362], landmarks[385], landmarks[387],
                            landmarks[263], landmarks[373], landmarks[380]]

                ear_atual = (calcular_ear(olho_esq) + calcular_ear(olho_dir)) / 2.0
                h_olhos   = calcular_distancia(landmarks[33], landmarks[263]) or 0.001
                mar_atual = calcular_distancia(landmarks[13], landmarks[14]) / h_olhos

                if not calibrado:
                    soma_ear += ear_atual
                    soma_mar += mar_atual
                    frames_calibracao += 1
                    estado_tela = f"Calibrando... ({frames_calibracao}/{max_frames_calibracao})"
                    if frames_calibracao >= max_frames_calibracao:
                        ear_base  = soma_ear / max_frames_calibracao
                        mar_base  = soma_mar / max_frames_calibracao
                        calibrado = True
                        print(f"[CAL] Calibração concluída para {nome_detectado}. "
                              f"EAR_base={ear_base:.3f}  MAR_base={mar_base:.3f}")
                else:
                    dist_sobrancelha  = calcular_distancia(landmarks[105], landmarks[334])
                    ratio_sobrancelha = dist_sobrancelha / h_olhos

                    canto_esq   = landmarks[61].y
                    canto_dir   = landmarks[291].y
                    centro_boca = (landmarks[13].y + landmarks[14].y) / 2.0

                    if ear_atual < ear_base * 0.70:
                        estado_momento = "desatento"
                    elif mar_atual > mar_base * 1.5:
                        estado_momento = "desatento"
                    elif canto_esq < centro_boca and canto_dir < centro_boca:
                        estado_momento = "feliz"
                    elif canto_esq > centro_boca and canto_dir > centro_boca:
                        estado_momento = "triste"
                    elif ratio_sobrancelha < 0.35:
                        estado_momento = "agressivo"
                    elif ratio_sobrancelha > 0.45:
                        estado_momento = "focado"
                    else:
                        estado_momento = "neutro"

                    historico_estados.append(estado_momento)
                    if len(historico_estados) > max_historico:
                        historico_estados.pop(0)

                    if len(historico_estados) == max_historico:
                        estado_predominante = max(
                            set(historico_estados),
                            key=historico_estados.count
                        )
                        estado_tela = estado_predominante

                        # ── Salvar no MongoDB ─────────────────────────────
                        if aluno_detectado != "Desconhecido":
                            ultimo_save = ultimo_save_alunos.get(aluno_detectado, 0)
                            if tempo_atual - ultimo_save >= INTERVALO_SAVE:
                                dado_log = {
                                    "aluno_id": aluno_detectado,
                                    "nome":     nome_detectado,
                                    "contexto_captura": "Sala de Aula",
                                    "analise_comportamental": {
                                        "estado_predominante": estado_predominante,
                                        "nivel_confianca":     confianca_reconhecimento
                                    },
                                    "timestamp": datetime.now().isoformat()
                                }
                                try:
                                    colecao_logs.insert_one(dado_log)
                                    print(f"[LOG {datetime.now().strftime('%H:%M:%S')}] "
                                          f"{nome_detectado} | {estado_predominante} "
                                          f"| confiança {confianca_reconhecimento}%")
                                    ultimo_save_alunos[aluno_detectado] = tempo_atual
                                except Exception as e:
                                    print(f"[ERR] Falha ao salvar no MongoDB: {e}")

            ultimo_processamento = tempo_atual

        # ── Overlay visual ────────────────────────────────────────────────
        cor_estado = CORES_ESTADO.get(estado_tela, (200, 200, 200))

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, frame.shape[0] - 90), (frame.shape[1], frame.shape[0]), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

        cv2.putText(frame, f"Aluno : {nome_tela}",
                    (15, frame.shape[0] - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Estado: {estado_tela}",
                    (15, frame.shape[0] - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, cor_estado, 2)
        if conf_tela > 0:
            cv2.putText(frame, f"Conf.: {conf_tela}%",
                        (frame.shape[1] - 160, frame.shape[0] - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
        frame_transmissao = frame.copy()
        cv2.imshow("Monitoramento Escolar", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[END] Sistema encerrado.")