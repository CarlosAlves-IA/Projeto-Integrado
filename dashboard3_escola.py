import streamlit as st
import pandas as pd
from pymongo import MongoClient
import urllib.parse
import base64
from datetime import datetime, timedelta
import cv2

st.set_page_config(page_title="Escola Inteligente", layout="wide")

username = urllib.parse.quote_plus("CARLOSADMIN")
password = urllib.parse.quote_plus("130820$")
URI_MONGO = f"mongodb+srv://{username}:{password}@bancopi.cmlpnxv.mongodb.net/?appName=BANCOPI"

client = MongoClient(URI_MONGO)
db = client["escola_inteligente"]
colecao_alunos = db["alunos"]
colecao_usuarios = db["usuarios"]
colecao_logs = db["logs_acesso"]

usuario_logado = False
chaves_sessao = list(st.session_state.keys())
for chave in chaves_sessao:
    if chave == 'logado':
        if st.session_state['logado'] == True:
            usuario_logado = True
            break

if usuario_logado == False:
    st.session_state['logado'] = False
    st.session_state['perfil'] = ""
    st.session_state['nome_usuario'] = ""

def tela_login_cadastro():
    st.title("Acesso ao Sistema Escolar")
    aba_login, aba_cadastro = st.tabs(["Entrar", "Criar Conta Chefe"])
    
    with aba_login:
        with st.form("form_login"):
            usuario_login = st.text_input("Usuario")
            senha_login = st.text_input("Senha", type="password")
            submit_login = st.form_submit_button("Acessar")
            
            if submit_login:
                todos_usuarios = list(colecao_usuarios.find({}))
                usuario_encontrado = False
                perfil_encontrado = ""
                
                for user in todos_usuarios:
                    if user.get("usuario") == usuario_login:
                        if user.get("senha") == senha_login:
                            usuario_encontrado = True
                            perfil_encontrado = user.get("perfil")
                            break
                
                if usuario_encontrado == True:
                    st.session_state['logado'] = True
                    st.session_state['perfil'] = perfil_encontrado
                    st.session_state['nome_usuario'] = usuario_login
                    st.rerun()
                else:
                    st.error("Credenciais invalidas.")
    
    with aba_cadastro:
        with st.form("form_criar_chefe"):
            st.info("Area restrita. Necessario codigo de autorizacao.")
            novo_usuario = st.text_input("Novo Usuario")
            nova_senha = st.text_input("Nova Senha", type="password")
            codigo_chefe = st.text_input("Codigo de Acesso (Diretoria)", type="password")
            submit_cadastro = st.form_submit_button("Criar Conta")
            
            if submit_cadastro:
                if codigo_chefe == "0101":
                    todos_usuarios = list(colecao_usuarios.find({}))
                    existe = False
                    for user in todos_usuarios:
                        if user.get("usuario") == novo_usuario:
                            existe = True
                            break
                            
                    if existe == True:
                        st.error("Usuario ja existe.")
                    else:
                        documento = {
                            "usuario": novo_usuario,
                            "senha": nova_senha,
                            "perfil": "diretoria"
                        }
                        colecao_usuarios.insert_one(documento)
                        st.success("Conta criada com sucesso!")
                else:
                    st.error("Codigo invalido.")

def tela_painel_principal():
    st.sidebar.title("Bem-vindo, " + st.session_state['nome_usuario'])
    st.sidebar.write("Perfil de Acesso: " + st.session_state['perfil'])
    
    logout = st.sidebar.button("Sair do Sistema")
    if logout:
        st.session_state['logado'] = False
        st.session_state['perfil'] = ""
        st.session_state['nome_usuario'] = ""
        st.rerun()

    if st.session_state['perfil'] == "diretoria":
        st.title("Painel de Controle - Diretoria")
        aba_dash, aba_cad_aluno, aba_cad_prof, aba_camera = st.tabs(["Dashboard", "Gerenciar Alunos", "Cadastrar Professor", "Camera ao Vivo"])
        
        with aba_dash:
            st.header("Metricas Comportamentais e Fluxo")
            logs_banco = list(colecao_logs.find({}))
            
            contagem_total = 0
            for log in logs_banco:
                contagem_total += 1
                
            if contagem_total > 0:
                df_logs = pd.DataFrame(logs_banco)
                estados_lista = []
                
                alunos_focados_unicos = []
                alunos_alerta_unicos = []
                
                for index, row in df_logs.iterrows():
                    dicionario_comportamento = row.get('analise_comportamental', {})
                    if isinstance(dicionario_comportamento, dict):
                        estado = dicionario_comportamento.get('estado_predominante', 'Desconhecido')
                    else:
                        estado = 'Desconhecido'
                    estados_lista.append(estado)
                    
                    nome_aluno = row.get('nome', 'Desconhecido')
                    if nome_aluno != "Desconhecido":
                        if estado == "focado":
                            ja_existe_focado = False
                            for af in alunos_focados_unicos:
                                if af == nome_aluno:
                                    ja_existe_focado = True
                                    break
                            if ja_existe_focado == False:
                                alunos_focados_unicos.append(nome_aluno)
                                
                        if estado == "triste" or estado == "agressivo":
                            ja_existe_alerta = False
                            for aa in alunos_alerta_unicos:
                                if aa == nome_aluno:
                                    ja_existe_alerta = True
                                    break
                            if ja_existe_alerta == False:
                                alunos_alerta_unicos.append(nome_aluno)
                                
                df_logs['estado'] = estados_lista
                
                focados_total = 0
                for a in alunos_focados_unicos:
                    focados_total += 1
                    
                alertas_total = 0
                for a in alunos_alerta_unicos:
                    alertas_total += 1
                
                col_metrica1, col_metrica2, col_metrica3 = st.columns(3)
                col_metrica1.metric("Total de Registros de IA", contagem_total)
                col_metrica2.metric("Alunos Unicos Focados", focados_total)
                col_metrica3.metric("Alunos Unicos em Alerta", alertas_total)
                
                col_grafico, col_tabela = st.columns(2)
                
                with col_grafico:
                    st.subheader("Frequencia Geral")
                    contagem_estados = df_logs['estado'].value_counts()
                    st.bar_chart(contagem_estados)
                    
                with col_tabela:
                    st.subheader("Feed do Banco de Dados")
                    df_view = df_logs[['timestamp', 'nome', 'estado']].sort_values(by='timestamp', ascending=False).head(10)
                    st.dataframe(df_view, use_container_width=True)
                    
                st.divider()
                st.subheader("Analise Grafica por Aluno")
                
                nomes_validos = []
                for n in df_logs['nome']:
                    if n != "Desconhecido":
                        existe_nome = False
                        for nv in nomes_validos:
                            if nv == n:
                                existe_nome = True
                                break
                        if existe_nome == False:
                            nomes_validos.append(n)
                            
                tamanho_nomes_validos = 0
                for n in nomes_validos:
                    tamanho_nomes_validos += 1
                    
                if tamanho_nomes_validos > 0:
                    aluno_alvo = st.selectbox("Selecione o Aluno para Filtrar:", nomes_validos)
                    
                    logs_alvo = []
                    for index, row in df_logs.iterrows():
                        if row.get('nome') == aluno_alvo:
                            logs_alvo.append(row)
                            
                    df_aluno = pd.DataFrame(logs_alvo)
                    st.bar_chart(df_aluno['estado'].value_counts(), color="#FF4B4B")
                else:
                    st.info("Nenhum aluno reconhecido ainda para gerar graficos.")

            else:
                st.info("Nenhum dado registrado.")
            
        with aba_cad_aluno:
            st.header("Cadastrar Novo Aluno")
            with st.form("form_cad_aluno"):
                col1, col2 = st.columns(2)
                nome = col1.text_input("Nome Completo")
                matricula = col2.text_input("Matricula")
                
                col3, col4 = st.columns(2)
                tipo_sanguineo = col3.selectbox("Sangue", ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"])
                info_pais = col4.text_input("Chat ID Telegram (Responsavel)")
                
                foto_upload = st.file_uploader("Foto (Rosto limpo)", type=["jpg", "png", "jpeg"])
                
                submit_aluno = st.form_submit_button("Salvar Novo")
                
                if submit_aluno:
                    todos_alunos = list(colecao_alunos.find({}))
                    aluno_existe = False
                    for aluno in todos_alunos:
                        if aluno.get("matricula") == matricula:
                            aluno_existe = True
                            break
                            
                    if aluno_existe == True:
                        st.error("Matricula ja existe!")
                    else:
                        foto_base64 = ""
                        if foto_upload != None:
                            foto_bytes = foto_upload.getvalue()
                            foto_base64 = base64.b64encode(foto_bytes).decode('utf-8')
                            
                        novo_aluno = {
                            "nome": nome,
                            "matricula": matricula,
                            "tipo_sanguineo": tipo_sanguineo,
                            "info_pais": info_pais,
                            "foto_base64": foto_base64
                        }
                        colecao_alunos.insert_one(novo_aluno)
                        st.success("Cadastrado com sucesso!")
                        st.rerun()

            st.divider()
            st.header("Base de Alunos Cadastrados")
            todos_alunos_cadastrados = list(colecao_alunos.find({}))
            
            cont_alunos = 0
            for a in todos_alunos_cadastrados:
                cont_alunos += 1
                
            if cont_alunos > 0:
                lista_exibicao = []
                opcoes_matricula = []
                for aluno in todos_alunos_cadastrados:
                    tem_foto = "Nao"
                    if aluno.get("foto_base64") != "":
                        tem_foto = "Sim"
                    
                    matr = aluno.get("matricula")
                    nome_al = aluno.get("nome")
                    opcoes_matricula.append(matr + " - " + nome_al)
                    
                    lista_exibicao.append({
                        "Matricula": matr,
                        "Nome": nome_al,
                        "Sangue": aluno.get("tipo_sanguineo"),
                        "Foto Cadastrada": tem_foto
                    })
                st.table(lista_exibicao)
                
                st.subheader("Acoes (Editar / Excluir)")
                aluno_selecionado = st.selectbox("Selecione um registro:", opcoes_matricula)
                
                if aluno_selecionado:
                    matricula_alvo = aluno_selecionado.split(" - ")[0]
                    
                    col_ed, col_del = st.columns(2)
                    with col_ed:
                        with st.expander("Editar Nome e Telegram"):
                            with st.form("form_edit"):
                                nome_update = st.text_input("Novo Nome")
                                resp_update = st.text_input("Novo Chat ID Telegram")
                                btn_update = st.form_submit_button("Atualizar")
                                if btn_update:
                                    colecao_alunos.update_one(
                                        {"matricula": matricula_alvo}, 
                                        {"$set": {"nome": nome_update, "info_pais": resp_update}}
                                    )
                                    st.success("Atualizado!")
                                    st.rerun()
                                    
                    with col_del:
                        btn_delete = st.button("Excluir Matrícula Completamente")
                        if btn_delete:
                            colecao_alunos.delete_one({"matricula": matricula_alvo})
                            st.success("Registro removido.")
                            st.rerun()

        with aba_cad_prof:
            st.write("Criar acesso para docentes.")

        with aba_camera:

            st.write("Transmissao do Motor de IA ao Vivo")
            st.markdown('<img src="http://127.0.0.1:5000/video_feed" width="100%" style="border-radius: 8px;">', unsafe_allow_html=True)
                
    else:
        st.title("Painel do Professor")
        st.write("Acesso restrito.")

logado = False
chaves_state = list(st.session_state.keys())
for k in chaves_state:
    if k == 'logado':
        if st.session_state['logado'] == True:
            logado = True
            break

if logado == False:
    tela_login_cadastro()
else:
    tela_painel_principal()