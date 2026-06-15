# Projeto Integrador: Escola Inteligente (Monitoramento e Portaria)

Este projeto é um ecossistema integrado de Visão Computacional e Internet das Coisas (IoT) focado na segurança, controle de acesso e análise comportamental em ambientes acadêmicos. O sistema utiliza Inteligência Artificial para reconhecer alunos, mapear estados emocionais (foco, desatenção, etc.) e notificar responsáveis automaticamente, tudo centralizado em um banco de dados NoSQL e gerido por um Dashboard Web interativo.

## 🏗️ Arquitetura do Sistema

O projeto foi construído sob uma arquitetura modular, dividida em três pilares principais:

1. **`monitoramento_escolar.py` (Motor de IA em Sala de Aula):**
   - Realiza o reconhecimento facial biométrico de alta precisão contínuo.
   - Aplica geometria Euclidiana sobre 468 pontos faciais para calcular o EAR (Eye Aspect Ratio) e MAR (Mouth Aspect Ratio), identificando o nível de atenção e o estado emocional predominante do aluno.
   - Opera como um servidor HTTP de *streaming* (MJPEG) em uma *thread* paralela, permitindo a transmissão de vídeo sem concorrência de hardware (I/O).
   - Envia logs consolidados de comportamento para o banco de dados.

2. **`portaria.py` (Controle de Acesso Inteligente):**
   - Sistema otimizado para catracas, focado em reconhecimento rápido.
   - Processa a entrada e saída de alunos aplicando uma trava temporal (*cooldown* de 5 minutos) para evitar redundância.
   - Renderiza uma interface visual (Sinalização Digital) sobrepondo a foto cadastrada do aluno e o status de acesso no frame de vídeo.
   - Integra-se nativamente com a API do Telegram, disparando notificações de *Push* em tempo real para o *smartphone* dos responsáveis.

3. **`dashboard_escola.py` (Painel de Gestão e BI):**
   - Aplicação web administrativa com controle de sessão (Login/Senha).
   - Permite o cadastro de novos alunos (CRUD), com conversão e armazenamento de imagens em Base64.
   - Painel de Business Intelligence (BI) para a Diretoria, gerando gráficos de foco e atenção, filtrando alunos únicos e exibindo a câmera da sala de aula ao vivo.

---

## 🛠️ Tecnologias e Bibliotecas Utilizadas

O sistema exige a instalação de pacotes específicos de visão computacional, aprendizado de máquina e redes. 

* **Interface e Redes:**
  * `streamlit`: Framework de renderização do Dashboard Web.
  * `flask`: Servidor web leve utilizado para criar o streaming de vídeo MJPEG do monitoramento.
  * `requests`: Responsável pelas requisições HTTP POST para o webhook da API do Telegram.
* **Inteligência Artificial e Visão Computacional:**
  * `opencv-python` (`cv2`): Captura de hardware (câmera) e processamento/desenho das matrizes de imagem.
  * `mediapipe`: Framework do Google utilizado para extração ultrarrápida da malha facial e análise comportamental.
  * `insightface` & `onnxruntime`: Motor de Deep Learning que extrai embeddings faciais (vetores de 512 dimensões) e realiza reconhecimento biométrico por Similaridade do Cosseno.
* **Ciência de Dados e Matemática:**
  * `numpy`: Processamento de tensores, álgebra linear e cálculo de distâncias vetoriais.
  * `pandas`: Estruturação, filtragem e exibição em DataFrames dos logs no Dashboard.
* **Banco de Dados e Segurança:**
  * `pymongo`: Driver oficial para comunicação com o banco de dados NoSQL (MongoDB).
  * `certifi`: Fornece certificados raiz da Mozilla para validar conexões TLS/SSL seguras com o cluster do banco.
  * `python-dotenv`: Carregamento seguro de variáveis de ambiente e credenciais.

### Comando para instalação das dependências:
```bash
python -m pip install streamlit pandas pymongo certifi opencv-python mediapipe python-dotenv numpy insightface onnxruntime flask requests