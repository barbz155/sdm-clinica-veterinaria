"""Cliente HTTP da API governamental simulada.

Classifica o resultado de cada chamada para o serviço de integração decidir o próximo estado:
  - SUCESSO        -> CONFIRMADA
  - INDISPONIVEL   -> PENDENTE (timeout, conexão recusada, HTTP 5xx/429) — reenvio automático
  - REJEITADA      -> FALHA    (HTTP 4xx de validação) — exige correção e reenvio manual
"""
from dataclasses import dataclass

import requests

import config

ROTAS = {
    "CADASTRO_ANIMAL": ("POST", "/api/governo/animais"),
    "ATUALIZACAO_ANIMAL": ("PUT", "/api/governo/animais/{microchip}"),
    "VACINACAO_ANTIRRABICA": ("POST", "/api/governo/vacinacoes-antirrabicas"),
}


@dataclass
class Resultado:
    categoria: str            # SUCESSO | INDISPONIVEL | REJEITADA
    http_status: int | None
    corpo: dict | None
    mensagem: str
    replay: bool = False


def enviar(tipo_operacao, payload, chave_idempotencia):
    metodo, rota = ROTAS[tipo_operacao]
    url = config.GOV_API_URL + rota.format(microchip=payload.get("microchip", ""))
    cabecalhos = {
        "X-Api-Key": config.GOV_API_KEY,
        "Idempotency-Key": chave_idempotencia,
        "Content-Type": "application/json",
    }
    try:
        r = requests.request(metodo, url, json=payload, headers=cabecalhos,
                             timeout=(config.GOV_TIMEOUT_CONEXAO, config.GOV_TIMEOUT_LEITURA))
    except requests.Timeout:
        return Resultado("INDISPONIVEL", None, None, "Timeout ao comunicar com a API governamental.")
    except requests.ConnectionError:
        return Resultado("INDISPONIVEL", None, None, "API governamental inacessível (falha de conexão).")
    except requests.RequestException as e:
        return Resultado("INDISPONIVEL", None, None, f"Erro de comunicação: {e}")

    try:
        corpo = r.json()
    except ValueError:
        corpo = None
    msg = (corpo or {}).get("mensagem") or f"HTTP {r.status_code}"
    replay = r.headers.get("Idempotent-Replay") == "true"

    if r.status_code < 300:
        return Resultado("SUCESSO", r.status_code, corpo, msg, replay)
    if r.status_code == 409 and tipo_operacao == "CADASTRO_ANIMAL":
        # microchip já registrado no serviço externo: não é falha de comunicação
        return Resultado("REJEITADA", r.status_code, corpo, msg)
    if r.status_code >= 500 or r.status_code in (408, 429):
        return Resultado("INDISPONIVEL", r.status_code, corpo, msg)
    erros = (corpo or {}).get("erros")
    if erros:
        msg = f"{msg} {'; '.join(erros)}"
    return Resultado("REJEITADA", r.status_code, corpo, msg)
