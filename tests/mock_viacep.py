"""Dublê (mock) local da API ViaCEP — usado SOMENTE quando a máquina de testes não tem internet.

Responde no mesmo formato de https://viacep.com.br/ws/{cep}/json/ .
Uso:  python mock_viacep.py   (porta 5099)
      VIACEP_URL=http://127.0.0.1:5099/ws/{cep}/json/ python ../api_clinica/app.py
CEP 99999999 simula timeout (demora 10 s).
"""
import time

from flask import Flask, jsonify

app = Flask(__name__)
app.json.ensure_ascii = False

CEPS = {
    "01001000": {"cep": "01001-000", "logradouro": "Praça da Sé", "complemento": "lado ímpar", "bairro": "Sé",
                 "localidade": "São Paulo", "uf": "SP", "ibge": "3550308"},
    "22775040": {"cep": "22775-040", "logradouro": "Avenida Embaixador Abelardo Bueno", "complemento": "",
                 "bairro": "Barra da Tijuca", "localidade": "Rio de Janeiro", "uf": "RJ", "ibge": "3304557"},
    "22750009": {"cep": "22750-009", "logradouro": "Estrada dos Bandeirantes", "complemento": "",
                 "bairro": "Taquara", "localidade": "Rio de Janeiro", "uf": "RJ", "ibge": "3304557"},
}


@app.get("/ws/<cep>/json/")
def cep(cep):
    if not cep.isdigit() or len(cep) != 8:
        return "Bad Request", 400
    if cep == "99999999":
        time.sleep(10)
    return jsonify(CEPS.get(cep, {"erro": "true"}))


if __name__ == "__main__":
    app.run(port=5099)
