"""Autenticação: login, logout, cadastro de veterinário e confirmação de senha por código."""
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

import config
from core.seguranca import criar_sessao, login_obrigatorio
from core.validacao import ErroNegocio, Validador, agora, senha_forte
from database import get_db, rows, transacao

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR",
       "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]


def _enviar_codigo(conn, vet_id, email, nome):
    """Gera código de 6 dígitos, guarda o HASH e 'envia' o e-mail (simulado)."""
    codigo = f"{secrets.randbelow(10**6):06d}"
    expira = (datetime.now() + timedelta(minutes=config.CODIGO_CONFIRMACAO_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE veterinario SET codigo_confirmacao_hash=?, codigo_expira_em=? WHERE id=?",
                 (generate_password_hash(codigo), expira, vet_id))
    conn.execute(
        "INSERT INTO email_simulado (destinatario, assunto, corpo) VALUES (?,?,?)",
        (email, "Confirme sua senha - Clínica Veterinária SDM",
         f"Olá, {nome}!\n\nSeu código de confirmação é: {codigo}\n"
         f"Ele expira em {config.CODIGO_CONFIRMACAO_MIN} minutos.\n\n(E-mail simulado para fins acadêmicos)"),
    )
    print(f"[E-MAIL SIMULADO] Para: {email} | Código de confirmação: {codigo}", flush=True)
    return codigo


@bp.post("/login")
def login():
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    senha = d.get("senha") or ""
    if not email or not senha:
        raise ErroNegocio("Informe e-mail e senha.", 400)
    conn = get_db()
    v = conn.execute("SELECT * FROM veterinario WHERE email = ?", (email,)).fetchone()
    # mensagem genérica para não revelar se o e-mail existe
    if not v or not check_password_hash(v["senha_hash"], senha):
        raise ErroNegocio("E-mail ou senha incorretos.", 401)
    if v["situacao"] != "ATIVO":
        raise ErroNegocio("Acesso bloqueado: veterinário inativo. Procure a administração da clínica.", 403)
    if not v["senha_confirmada"]:
        raise ErroNegocio("Acesso bloqueado: senha ainda não confirmada. Use o código enviado ao seu e-mail.",
                          403, ["SENHA_NAO_CONFIRMADA"])
    with transacao(conn):
        token, expira = criar_sessao(conn, v["id"])
        conn.execute("UPDATE veterinario SET ultimo_acesso = ? WHERE id = ?", (agora(), v["id"]))
    return jsonify({
        "token": token, "tipo": "Bearer", "expira_em": expira,
        "veterinario": {"id": v["id"], "nome": v["nome"], "email": v["email"],
                        "crmv": v["crmv"], "crmv_uf": v["crmv_uf"]},
    })


@bp.post("/logout")
@login_obrigatorio
def logout():
    get_db().execute("UPDATE sessao SET encerrada_em = ? WHERE id = ?", (agora(), g.sessao_id))
    return jsonify({"mensagem": "Sessão encerrada."})


@bp.get("/me")
@login_obrigatorio
def me():
    return jsonify(g.veterinario)


@bp.post("/registro")
def registrar():
    """Cadastro de veterinário. A conta só acessa o sistema após confirmar a senha."""
    d = request.get_json(silent=True) or {}
    val = Validador(d)
    nome = val.obrigatorio("nome", "Nome", 150)
    cpf = val.cpf()
    crmv = val.obrigatorio("crmv", "CRMV", 10)
    if crmv and not str(crmv).isdigit():
        val.adicionar("CRMV deve conter apenas números.")
    uf = val.escolha("crmv_uf", UFS, "UF do CRMV")
    email = val.email()
    tel = val.telefone()
    senha = d.get("senha") or ""
    if not senha_forte(senha):
        val.adicionar("Senha deve ter ao menos 8 caracteres, com letras e números.")
    if senha != d.get("confirmacao_senha", senha):
        val.adicionar("A confirmação da senha não confere.")
    val.verificar()
    conn = get_db()
    with transacao(conn):
        if conn.execute("SELECT 1 FROM veterinario WHERE cpf = ?", (cpf,)).fetchone():
            raise ErroNegocio("Já existe veterinário com este CPF.", 409)
        if conn.execute("SELECT 1 FROM veterinario WHERE email = ?", (email,)).fetchone():
            raise ErroNegocio("Já existe veterinário com este e-mail.", 409)
        if conn.execute("SELECT 1 FROM veterinario WHERE crmv = ? AND crmv_uf = ?", (crmv, uf)).fetchone():
            raise ErroNegocio("Já existe veterinário com este CRMV/UF.", 409)
        cur = conn.execute(
            """INSERT INTO veterinario (nome, cpf, crmv, crmv_uf, email, telefone, senha_hash)
               VALUES (?,?,?,?,?,?,?)""",
            (nome, cpf, crmv, uf, email, tel, generate_password_hash(senha)),
        )
        codigo = _enviar_codigo(conn, cur.lastrowid, email, nome)
    resp = {"id": cur.lastrowid, "mensagem": "Cadastro realizado. Enviamos um código de confirmação "
                                            "para o seu e-mail (envio simulado)."}
    if config.DEV_MODE:
        resp["codigo_simulado"] = codigo
    return jsonify(resp), 201


@bp.post("/confirmar-senha")
def confirmar_senha():
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    codigo = (d.get("codigo") or "").strip()
    conn = get_db()
    v = conn.execute("SELECT * FROM veterinario WHERE email = ?", (email,)).fetchone()
    if not v or not v["codigo_confirmacao_hash"]:
        raise ErroNegocio("Não há confirmação pendente para este e-mail.", 404)
    if v["senha_confirmada"]:
        return jsonify({"mensagem": "Senha já confirmada anteriormente."})
    if v["codigo_expira_em"] < agora():
        raise ErroNegocio("Código expirado. Solicite um novo código.", 410)
    if not check_password_hash(v["codigo_confirmacao_hash"], codigo):
        raise ErroNegocio("Código de confirmação inválido.", 400)
    conn.execute(
        """UPDATE veterinario SET senha_confirmada = 1, data_confirmacao = ?, codigo_confirmacao_hash = NULL,
               codigo_expira_em = NULL WHERE id = ?""",
        (agora(), v["id"]),
    )
    return jsonify({"mensagem": "Senha confirmada com sucesso. Você já pode fazer login."})


@bp.post("/reenviar-codigo")
def reenviar_codigo():
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    conn = get_db()
    v = conn.execute("SELECT * FROM veterinario WHERE email = ?", (email,)).fetchone()
    resp = {"mensagem": "Se houver confirmação pendente, um novo código foi enviado."}
    if v and not v["senha_confirmada"]:
        with transacao(conn):
            codigo = _enviar_codigo(conn, v["id"], v["email"], v["nome"])
        if config.DEV_MODE:
            resp["codigo_simulado"] = codigo
    return jsonify(resp)


# ---- caixa de saída simulada (apenas em modo de desenvolvimento) ----
dev = Blueprint("dev", __name__, url_prefix="/api/dev")


@dev.get("/emails")
def emails():
    if not config.DEV_MODE:
        raise ErroNegocio("Recurso disponível apenas em modo de desenvolvimento.", 404)
    return jsonify(rows(get_db().execute("SELECT * FROM email_simulado ORDER BY id DESC LIMIT 50")))
