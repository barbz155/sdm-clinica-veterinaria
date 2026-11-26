"""Cliente da API pública ViaCEP (https://viacep.com.br/) com tratamento de falhas."""
import requests

import config
from core.validacao import ErroNegocio, somente_digitos


def consultar_cep(cep):
    cep = somente_digitos(cep)
    if len(cep) != 8:
        raise ErroNegocio("CEP deve conter 8 dígitos.", 400)
    try:
        r = requests.get(config.VIACEP_URL.format(cep=cep), timeout=config.VIACEP_TIMEOUT)
    except requests.Timeout:
        raise ErroNegocio("O serviço de CEP não respondeu a tempo (timeout). "
                          "Preencha o endereço manualmente.", 504)
    except requests.RequestException:
        raise ErroNegocio("Serviço de CEP indisponível no momento. Preencha o endereço manualmente.", 503)

    if r.status_code == 400:
        raise ErroNegocio("CEP com formato inválido.", 400)
    if r.status_code >= 500:
        raise ErroNegocio("Serviço de CEP indisponível no momento. Preencha o endereço manualmente.", 503)
    try:
        dados = r.json()
    except ValueError:
        raise ErroNegocio("Resposta inválida do serviço de CEP. Preencha o endereço manualmente.", 502)
    if dados.get("erro"):
        raise ErroNegocio("CEP não encontrado.", 404)
    return {
        "cep": somente_digitos(dados.get("cep")),
        "logradouro": dados.get("logradouro") or "",
        "complemento": dados.get("complemento") or "",
        "bairro": dados.get("bairro") or "",
        "cidade": dados.get("localidade") or "",
        "uf": dados.get("uf") or "",
        "codigo_ibge": dados.get("ibge") or None,
        "fonte": "ViaCEP",
    }
