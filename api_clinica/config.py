"""Configurações da API privada da clínica (variáveis de ambiente com padrões)."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.environ.get("CLINICA_DB", os.path.join(BASE_DIR, "data", "clinica.db"))
SECRET_KEY = os.environ.get("CLINICA_SECRET", "troque-esta-chave-em-producao-sdm-2026")
PORT = int(os.environ.get("CLINICA_PORT", "5000"))

# Sessão / token
TOKEN_HORAS = int(os.environ.get("TOKEN_HORAS", "8"))
CODIGO_CONFIRMACAO_MIN = int(os.environ.get("CODIGO_CONFIRMACAO_MIN", "30"))

# Modo de desenvolvimento: devolve o código de confirmação na resposta
# (envio de e-mail é SIMULADO, conforme permitido no enunciado)
DEV_MODE = os.environ.get("DEV_MODE", "1") == "1"

# API pública ViaCEP
VIACEP_URL = os.environ.get("VIACEP_URL", "https://viacep.com.br/ws/{cep}/json/")
VIACEP_TIMEOUT = float(os.environ.get("VIACEP_TIMEOUT", "5"))

# API governamental simulada
GOV_API_URL = os.environ.get("GOV_API_URL", "http://127.0.0.1:5001")
GOV_API_KEY = os.environ.get("GOV_API_KEY", "chave-clinica-sdm-123")
GOV_TIMEOUT_CONEXAO = float(os.environ.get("GOV_TIMEOUT_CONEXAO", "3"))
GOV_TIMEOUT_LEITURA = float(os.environ.get("GOV_TIMEOUT_LEITURA", "5"))
ORIGEM_SISTEMA = os.environ.get("ORIGEM_SISTEMA", "CLINICA-VET-SDM")

# Reenvio automático de pendências
RETRY_AUTO = os.environ.get("RETRY_AUTO", "1") == "1"
RETRY_INTERVALO_SEG = int(os.environ.get("RETRY_INTERVALO_SEG", "30"))
RETRY_MAX_TENTATIVAS = int(os.environ.get("RETRY_MAX_TENTATIVAS", "10"))
