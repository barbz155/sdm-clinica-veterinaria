"""Autenticação por token assinado + sessão revogável e decorator de proteção de endpoints."""
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import config
from core.validacao import ErroNegocio, agora
from database import get_db

_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="sdm-auth")


def criar_sessao(conn, veterinario_id):
    sid = secrets.token_hex(24)
    expira = (datetime.now() + timedelta(hours=config.TOKEN_HORAS)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO sessao (id, veterinario_id, expira_em) VALUES (?,?,?)",
                 (sid, veterinario_id, expira))
    return _serializer.dumps({"sid": sid, "vid": veterinario_id}), expira


def _ler_token():
    cab = request.headers.get("Authorization", "")
    if not cab.startswith("Bearer "):
        raise ErroNegocio("Autenticação necessária. Envie o cabeçalho Authorization: Bearer <token>.", 401)
    try:
        return _serializer.loads(cab[7:], max_age=config.TOKEN_HORAS * 3600)
    except SignatureExpired:
        raise ErroNegocio("Sessão expirada. Faça login novamente.", 401)
    except BadSignature:
        raise ErroNegocio("Token inválido.", 401)


def login_obrigatorio(fn):
    """Protege o endpoint: exige token válido, sessão ativa e veterinário ativo e confirmado."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        dados = _ler_token()
        conn = get_db()
        s = conn.execute(
            """SELECT s.id AS sessao_id, s.expira_em, s.encerrada_em, v.*
               FROM sessao s JOIN veterinario v ON v.id = s.veterinario_id
               WHERE s.id = ? AND s.veterinario_id = ?""",
            (dados["sid"], dados["vid"]),
        ).fetchone()
        if not s or s["encerrada_em"] is not None or s["expira_em"] < agora():
            raise ErroNegocio("Sessão encerrada ou expirada. Faça login novamente.", 401)
        # reavaliado a cada requisição: inativação/descadastro têm efeito imediato
        if s["situacao"] != "ATIVO":
            raise ErroNegocio("Acesso bloqueado: veterinário inativo.", 403)
        if not s["senha_confirmada"]:
            raise ErroNegocio("Acesso bloqueado: senha ainda não confirmada.", 403)
        g.sessao_id = dados["sid"]
        g.veterinario = {k: s[k] for k in ("id", "nome", "email", "crmv", "crmv_uf", "cpf")}
        return fn(*args, **kwargs)

    return wrapper
