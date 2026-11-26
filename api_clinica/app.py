"""
API PRIVADA DA CLÍNICA VETERINÁRIA (SDM) + servidor do frontend web.

Camadas:
  routes/    -> controladores HTTP (Blueprints Flask)
  services/  -> regras de integração (outbox, reenvio, idempotência)
  clients/   -> clientes HTTP externos (ViaCEP e API governamental simulada)
  core/      -> segurança (token/sessão) e validações
  database.py-> acesso a dados (SQLite) e carga inicial
  static/    -> frontend (HTML/CSS/JS) que consome esta API via REST
"""
import logging
import os

import requests
from flask import Flask, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException

import config
import database
from core.validacao import ErroNegocio
from routes import animais, atendimento, auth, cadastros
from services.integracao import WorkerReenvio

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

STATIC_DIR = os.path.join(config.BASE_DIR, "static")


def criar_app():
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.teardown_appcontext(database.close_db)

    for bp in (auth.bp, auth.dev, cadastros.bp, animais.bp, atendimento.bp):
        app.register_blueprint(bp)

    @app.get("/api/health")
    def health():
        gov = "DESCONHECIDO"
        try:
            r = requests.get(f"{config.GOV_API_URL}/api/governo/health",
                             headers={"X-Api-Key": config.GOV_API_KEY}, timeout=2)
            gov = "UP" if r.status_code == 200 else f"INDISPONIVEL (HTTP {r.status_code})"
        except requests.RequestException:
            gov = "INDISPONIVEL (sem comunicação)"
        return jsonify({"status": "UP", "servico": "API Privada da Clínica", "api_governamental": gov,
                        "reenvio_automatico": config.RETRY_AUTO, "intervalo_reenvio_seg": config.RETRY_INTERVALO_SEG})

    # ---- erros padronizados ----
    @app.errorhandler(ErroNegocio)
    def erro_negocio(e):
        corpo = {"erro": e.mensagem, "status": e.status}
        if e.erros:
            corpo["detalhes"] = e.erros
        return jsonify(corpo), e.status

    @app.errorhandler(HTTPException)
    def erro_http(e):
        return jsonify({"erro": e.description, "status": e.code}), e.code

    @app.errorhandler(Exception)
    def erro_interno(e):
        app.logger.exception(e)
        return jsonify({"erro": "Erro interno do servidor.", "status": 500}), 500

    # ---- documentação ----
    @app.get("/openapi.yaml")
    def openapi():
        return send_from_directory(config.BASE_DIR, "openapi.yaml", mimetype="text/yaml")

    @app.get("/docs")
    def docs():
        return send_from_directory(STATIC_DIR, "swagger.html")

    # ---- frontend (SPA) ----
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/<path:arquivo>")
    def estaticos(arquivo):
        if arquivo.startswith("api/"):
            raise ErroNegocio("Recurso não encontrado.", 404)
        return send_from_directory(STATIC_DIR, arquivo)

    return app


database.init_db()
app = criar_app()

if __name__ == "__main__":
    if config.RETRY_AUTO:
        WorkerReenvio().start()
    print(f"API da Clínica + Frontend em http://127.0.0.1:{config.PORT}  (docs: /docs)")
    app.run(host="0.0.0.0", port=config.PORT, debug=False, threaded=True)
