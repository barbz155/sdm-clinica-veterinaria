"""
API GOVERNAMENTAL SIMULADA — Registro de animais identificados por microchip RFID.

Serviço INDEPENDENTE (processo, porta e banco próprios: governo.db).
Fictício, para fins acadêmicos: NÃO é uma integração oficial com sistemas reais.

Recursos:
  - Cadastro / consulta / atualização de animais por microchip
  - Recebimento de vacinações antirrábicas (com cadastro implícito do animal)
  - Protocolos de processamento e consulta de operações
  - Idempotência via cabeçalho Idempotency-Key (sem duplicidade em reenvios)
  - Simulação de indisponibilidade, lentidão e erros intermitentes
"""
import json
import os
import random
import re
import secrets
import sqlite3
import time
from datetime import date, datetime
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("GOV_DB", os.path.join(BASE_DIR, "data", "governo.db"))
PORT = int(os.environ.get("GOV_PORT", "5001"))
API_KEYS = set(os.environ.get("GOV_API_KEYS", "chave-clinica-sdm-123").split(","))

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.json.ensure_ascii = False
app.json.sort_keys = False


# =====================================================================
# Persistência
# =====================================================================
def conectar():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def db():
    if "db" not in g:
        g.db = conectar()
    return g.db


@app.teardown_appcontext
def fechar(_e=None):
    c = g.pop("db", None)
    if c:
        c.close()


def init_db():
    conn = conectar()
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.close()


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def novo_protocolo():
    return f"GOV-{datetime.now():%Y%m%d}-{secrets.token_hex(4).upper()}"


# =====================================================================
# Segurança, simulação de falhas e idempotência
# =====================================================================
def erro(status, mensagem, **extra):
    corpo = {"status": "ERRO", "mensagem": mensagem}
    corpo.update(extra)
    return jsonify(corpo), status


@app.before_request
def antes():
    if not request.path.startswith("/api/governo"):
        return None
    if request.path.startswith("/api/governo/admin"):
        return _exigir_chave()
    r = _exigir_chave()
    if r:
        return r
    # ---- simulação de falhas ----
    sim = db().execute("SELECT modo, atraso_segundos FROM simulacao WHERE id = 1").fetchone()
    modo = sim["modo"]
    if modo == "INDISPONIVEL":
        return erro(503, "Serviço governamental temporariamente indisponível (simulação).")
    if modo == "LENTO":
        time.sleep(sim["atraso_segundos"])
    if modo == "ERRO_INTERMITENTE" and random.random() < 0.5:
        return erro(503, "Falha intermitente do serviço governamental (simulação).")
    return None


def _exigir_chave():
    if request.headers.get("X-Api-Key") not in API_KEYS:
        return erro(401, "Chave de API ausente ou inválida (cabeçalho X-Api-Key).")
    return None


def idempotente(tipo):
    """Decorator: se a Idempotency-Key já foi processada com sucesso, devolve a mesma resposta."""

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            chave = request.headers.get("Idempotency-Key", "").strip()
            if not chave:
                return erro(400, "Cabeçalho Idempotency-Key é obrigatório para operações de escrita.")
            if len(chave) > 80:
                return erro(400, "Idempotency-Key deve ter no máximo 80 caracteres.")
            conn = db()
            op = conn.execute("SELECT * FROM operacao WHERE chave_idempotencia = ?", (chave,)).fetchone()
            if op:
                conn.execute("UPDATE operacao SET replays = replays + 1 WHERE protocolo = ?", (op["protocolo"],))
                resp = jsonify(json.loads(op["resposta"]))
                resp.status_code = op["http_status"]
                resp.headers["Idempotent-Replay"] = "true"
                return resp
            g.idem_chave = chave
            g.idem_tipo = tipo
            return fn(*args, **kwargs)

        return wrapper

    return deco


def registrar_operacao(conn, tipo, http_status, corpo, microchip=None, chave=None, mensagem=None):
    """Grava a operação (protocolo). Somente sucessos guardam a chave de idempotência."""
    sucesso = http_status < 400
    conn.execute(
        """INSERT INTO operacao (protocolo, tipo, chave_idempotencia, microchip, status, http_status,
                                 mensagem, payload, resposta)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            corpo["protocolo"], tipo, chave if sucesso else None, microchip,
            "PROCESSADA" if sucesso else "REJEITADA", http_status, mensagem,
            json.dumps(request.get_json(silent=True), ensure_ascii=False),
            json.dumps(corpo, ensure_ascii=False),
        ),
    )


def responder(tipo, http_status, mensagem, dados=None, erros=None, microchip=None, conn=None):
    """Gera protocolo, registra a operação e devolve a resposta padronizada."""
    conn = conn or db()
    corpo = {
        "protocolo": novo_protocolo(),
        "status": "PROCESSADA" if http_status < 400 else "REJEITADA",
        "tipo_operacao": tipo,
        "mensagem": mensagem,
        "processado_em": agora(),
    }
    if erros:
        corpo["erros"] = erros
    if dados is not None:
        corpo["dados"] = dados
    registrar_operacao(conn, tipo, http_status, corpo, microchip,
                       getattr(g, "idem_chave", None), mensagem)
    return jsonify(corpo), http_status


# =====================================================================
# Validações
# =====================================================================
RE_CHIP = re.compile(r"^\d{15}$")
RE_CRMV = re.compile(r"^\d{3,8}$")
UFS = {"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR",
       "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"}


def _data(valor, campo, erros, nao_futura=True, obrigatoria=True):
    if not valor:
        if obrigatoria:
            erros.append(f"{campo} é obrigatório.")
        return None
    try:
        d = date.fromisoformat(valor)
    except (TypeError, ValueError):
        erros.append(f"{campo} deve estar no formato AAAA-MM-DD.")
        return None
    if nao_futura and d > date.today():
        erros.append(f"{campo} não pode ser uma data futura.")
    return d


def validar_animal(d, erros, parcial=False):
    def obrig(campo, valor):
        if not parcial and (valor is None or str(valor).strip() == ""):
            erros.append(f"{campo} é obrigatório.")

    if not parcial:
        if not RE_CHIP.match(str(d.get("microchip", ""))):
            erros.append("microchip deve conter exatamente 15 dígitos (padrão ISO 11784/11785).")
    obrig("nome", d.get("nome"))
    obrig("especie", d.get("especie"))
    if not parcial or "sexo" in d:
        if d.get("sexo") not in ("M", "F"):
            erros.append("sexo deve ser 'M' ou 'F'.")
    if d.get("data_nascimento"):
        _data(d.get("data_nascimento"), "data_nascimento", erros, obrigatoria=False)
    tutor = d.get("tutor") or {}
    if not parcial or "tutor" in d:
        obrig("tutor.nome", tutor.get("nome"))
        if not re.fullmatch(r"\d{11}", str(tutor.get("cpf", ""))):
            erros.append("tutor.cpf deve conter 11 dígitos.")
    vet = d.get("veterinario") or {}
    if not parcial or "veterinario" in d:
        if not RE_CRMV.match(str(vet.get("crmv", ""))):
            erros.append("veterinario.crmv inválido.")
        if vet.get("crmv_uf") not in UFS:
            erros.append("veterinario.crmv_uf inválida.")
    if not parcial:
        obrig("origem_sistema", d.get("origem_sistema"))
        obrig("id_animal_origem", d.get("id_animal_origem"))


def animal_json(r, conn=None):
    if r is None:
        return None
    a = dict(r)
    a["cadastro_implicito"] = bool(a["cadastro_implicito"])
    if conn is not None:
        a["vacinacoes_antirrabicas"] = [
            dict(v) for v in conn.execute(
                """SELECT protocolo, data_aplicacao, vacina_nome, fabricante, lote, veterinario_nome,
                          veterinario_crmv, veterinario_crmv_uf, id_aplicacao_origem, recebido_em
                   FROM vacinacao_antirrabica WHERE animal_registro_id = ? ORDER BY data_aplicacao""",
                (a["id"],),
            )
        ]
    return a


def _inserir_animal(conn, d, implicito=False):
    tutor = d.get("tutor") or {}
    vet = d.get("veterinario") or {}
    cur = conn.execute(
        """INSERT INTO animal_registro (microchip, nome, especie, raca, sexo, data_nascimento, cor,
               tutor_nome, tutor_cpf, tutor_municipio_ibge, veterinario_crmv, veterinario_crmv_uf,
               origem_sistema, id_animal_origem, microchip_anterior, cadastro_implicito)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            d["microchip"], d["nome"].strip(), d["especie"], d.get("raca"), d["sexo"],
            d.get("data_nascimento"), d.get("cor"), tutor["nome"], tutor["cpf"],
            tutor.get("municipio_ibge"), vet["crmv"], vet["crmv_uf"], d["origem_sistema"],
            str(d["id_animal_origem"]), d.get("microchip_anterior"), 1 if implicito else 0,
        ),
    )
    if d.get("microchip_anterior"):
        conn.execute(
            "UPDATE animal_registro SET situacao='SUBSTITUIDO', atualizado_em=? WHERE microchip=?",
            (agora(), d["microchip_anterior"]),
        )
    return cur.lastrowid


def _atualizar_animal(conn, microchip, d):
    campos, valores = [], []
    for campo in ("nome", "especie", "raca", "sexo", "data_nascimento", "cor"):
        if campo in d:
            campos.append(f"{campo} = ?")
            valores.append(d[campo])
    tutor = d.get("tutor")
    if tutor:
        campos += ["tutor_nome = ?", "tutor_cpf = ?", "tutor_municipio_ibge = ?"]
        valores += [tutor.get("nome"), tutor.get("cpf"), tutor.get("municipio_ibge")]
    vet = d.get("veterinario")
    if vet:
        campos += ["veterinario_crmv = ?", "veterinario_crmv_uf = ?"]
        valores += [vet.get("crmv"), vet.get("crmv_uf")]
    campos += ["cadastro_implicito = 0", "atualizado_em = ?"]
    valores += [agora(), microchip]
    conn.execute(f"UPDATE animal_registro SET {', '.join(campos)} WHERE microchip = ?", valores)


# =====================================================================
# Endpoints
# =====================================================================
@app.get("/api/governo/health")
def health():
    return jsonify({"status": "UP", "servico": "API Governamental Simulada", "horario": agora()})


@app.post("/api/governo/animais")
@idempotente("CADASTRO_ANIMAL")
def cadastrar_animal():
    d = request.get_json(silent=True) or {}
    erros = []
    validar_animal(d, erros)
    tipo = "CADASTRO_ANIMAL"
    if erros:
        return responder(tipo, 422, "Dados inválidos.", erros=erros, microchip=d.get("microchip"))
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        existente = conn.execute("SELECT * FROM animal_registro WHERE microchip = ?", (d["microchip"],)).fetchone()
        if existente:
            mesma_origem = (existente["origem_sistema"] == d["origem_sistema"]
                            and existente["id_animal_origem"] == str(d["id_animal_origem"]))
            if mesma_origem:
                _atualizar_animal(conn, d["microchip"], d)
                a = conn.execute("SELECT * FROM animal_registro WHERE microchip = ?", (d["microchip"],)).fetchone()
                r = responder(tipo, 200, "Animal já registrado por este sistema; dados atualizados.",
                              dados=animal_json(a), microchip=d["microchip"], conn=conn)
            else:
                r = responder(tipo, 409, "Microchip já registrado por outro sistema de origem.",
                              erros=["microchip duplicado"], microchip=d["microchip"], conn=conn)
        else:
            _inserir_animal(conn, d)
            a = conn.execute("SELECT * FROM animal_registro WHERE microchip = ?", (d["microchip"],)).fetchone()
            r = responder(tipo, 201, "Animal registrado com sucesso.", dados=animal_json(a),
                          microchip=d["microchip"], conn=conn)
        conn.execute("COMMIT")
        return r
    except Exception:
        conn.execute("ROLLBACK")
        raise


@app.get("/api/governo/animais/<microchip>")
def consultar_animal(microchip):
    conn = db()
    a = conn.execute("SELECT * FROM animal_registro WHERE microchip = ?", (microchip,)).fetchone()
    if not a:
        return erro(404, "Animal não encontrado para o microchip informado.")
    return jsonify(animal_json(a, conn))


@app.put("/api/governo/animais/<microchip>")
@idempotente("ATUALIZACAO_ANIMAL")
def atualizar_animal(microchip):
    d = request.get_json(silent=True) or {}
    erros = []
    validar_animal(d, erros, parcial=True)
    tipo = "ATUALIZACAO_ANIMAL"
    if erros:
        return responder(tipo, 422, "Dados inválidos.", erros=erros, microchip=microchip)
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if not conn.execute("SELECT 1 FROM animal_registro WHERE microchip = ?", (microchip,)).fetchone():
            r = responder(tipo, 404, "Animal não encontrado para o microchip informado.",
                          microchip=microchip, conn=conn)
        else:
            _atualizar_animal(conn, microchip, d)
            a = conn.execute("SELECT * FROM animal_registro WHERE microchip = ?", (microchip,)).fetchone()
            r = responder(tipo, 200, "Dados cadastrais atualizados.", dados=animal_json(a),
                          microchip=microchip, conn=conn)
        conn.execute("COMMIT")
        return r
    except Exception:
        conn.execute("ROLLBACK")
        raise


@app.post("/api/governo/vacinacoes-antirrabicas")
@idempotente("VACINACAO_ANTIRRABICA")
def receber_vacinacao():
    d = request.get_json(silent=True) or {}
    tipo = "VACINACAO_ANTIRRABICA"
    erros = []
    chip = str(d.get("microchip", ""))
    if not RE_CHIP.match(chip):
        erros.append("microchip deve conter exatamente 15 dígitos.")
    for campo in ("origem_sistema", "id_aplicacao_origem"):
        if not d.get(campo):
            erros.append(f"{campo} é obrigatório.")
    _data(d.get("data_aplicacao"), "data_aplicacao", erros)
    vac = d.get("vacina") or {}
    for campo in ("nome", "fabricante", "lote"):
        if not str(vac.get(campo, "")).strip():
            erros.append(f"vacina.{campo} é obrigatório.")
    vet = d.get("veterinario") or {}
    if not str(vet.get("nome", "")).strip():
        erros.append("veterinario.nome é obrigatório.")
    if not RE_CRMV.match(str(vet.get("crmv", ""))):
        erros.append("veterinario.crmv inválido.")
    if vet.get("crmv_uf") not in UFS:
        erros.append("veterinario.crmv_uf inválida.")
    animal = d.get("animal") or {}
    if erros:
        return responder(tipo, 422, "Dados inválidos.", erros=erros, microchip=chip)

    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        # 2ª barreira de duplicidade: mesma aplicação de origem enviada com outra chave
        dup = conn.execute(
            "SELECT * FROM vacinacao_antirrabica WHERE origem_sistema = ? AND id_aplicacao_origem = ?",
            (d["origem_sistema"], str(d["id_aplicacao_origem"])),
        ).fetchone()
        if dup:
            conn.execute("COMMIT")
            return jsonify({
                "protocolo": dup["protocolo"], "status": "PROCESSADA", "tipo_operacao": tipo,
                "mensagem": "Vacinação já registrada anteriormente; nenhum novo registro foi criado.",
                "duplicidade_evitada": True, "processado_em": dup["recebido_em"],
            }), 200

        reg = conn.execute("SELECT * FROM animal_registro WHERE microchip = ?", (chip,)).fetchone()
        cadastro_implicito = False
        if not reg:
            # A comunicação é obrigatória mesmo sem cadastro prévio: registra o animal implicitamente
            dados_animal = dict(animal, microchip=chip, origem_sistema=d["origem_sistema"],
                                veterinario=animal.get("veterinario") or vet)
            erros_animal = []
            validar_animal(dados_animal, erros_animal)
            if erros_animal:
                conn.execute("ROLLBACK")
                return responder(tipo, 422, "Animal não registrado e dados do animal insuficientes "
                                 "para cadastro implícito.", erros=erros_animal, microchip=chip)
            _inserir_animal(conn, dados_animal, implicito=True)
            reg = conn.execute("SELECT * FROM animal_registro WHERE microchip = ?", (chip,)).fetchone()
            cadastro_implicito = True

        protocolo = novo_protocolo()
        conn.execute(
            """INSERT INTO vacinacao_antirrabica (animal_registro_id, microchip, origem_sistema,
                   id_aplicacao_origem, data_aplicacao, vacina_nome, fabricante, lote, veterinario_nome,
                   veterinario_crmv, veterinario_crmv_uf, protocolo)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (reg["id"], chip, d["origem_sistema"], str(d["id_aplicacao_origem"]), d["data_aplicacao"],
             vac["nome"], vac["fabricante"], vac["lote"], vet["nome"], vet["crmv"], vet["crmv_uf"], protocolo),
        )
        corpo = {
            "protocolo": protocolo, "status": "PROCESSADA", "tipo_operacao": tipo,
            "mensagem": "Vacinação antirrábica registrada com sucesso.",
            "cadastro_implicito_animal": cadastro_implicito, "processado_em": agora(),
        }
        registrar_operacao(conn, tipo, 201, corpo, chip, g.idem_chave, corpo["mensagem"])
        conn.execute("COMMIT")
        return jsonify(corpo), 201
    except Exception:
        conn.execute("ROLLBACK")
        raise


@app.get("/api/governo/vacinacoes-antirrabicas")
def listar_vacinacoes():
    chip = request.args.get("microchip")
    sql = "SELECT * FROM vacinacao_antirrabica"
    params = ()
    if chip:
        sql += " WHERE microchip = ?"
        params = (chip,)
    return jsonify([dict(r) for r in db().execute(sql + " ORDER BY id DESC LIMIT 200", params)])


@app.get("/api/governo/operacoes/<protocolo>")
def consultar_operacao(protocolo):
    op = db().execute("SELECT * FROM operacao WHERE protocolo = ?", (protocolo,)).fetchone()
    if not op:
        return erro(404, "Protocolo não encontrado.")
    o = dict(op)
    o["resposta"] = json.loads(o["resposta"]) if o["resposta"] else None
    o.pop("payload", None)
    return jsonify(o)


# ---------------------------------------------------------------------
# Administração da simulação (uso em demonstração/testes)
# ---------------------------------------------------------------------
@app.get("/api/governo/admin/simulacao")
def ver_simulacao():
    return jsonify(dict(db().execute("SELECT * FROM simulacao WHERE id = 1").fetchone()))


@app.put("/api/governo/admin/simulacao")
def definir_simulacao():
    d = request.get_json(silent=True) or {}
    modo = d.get("modo", "NORMAL")
    if modo not in ("NORMAL", "INDISPONIVEL", "LENTO", "ERRO_INTERMITENTE"):
        return erro(400, "modo deve ser NORMAL, INDISPONIVEL, LENTO ou ERRO_INTERMITENTE.")
    atraso = int(d.get("atraso_segundos", 10))
    db().execute("UPDATE simulacao SET modo=?, atraso_segundos=?, atualizado_em=? WHERE id=1",
                 (modo, atraso, agora()))
    return ver_simulacao()


@app.get("/api/governo/admin/estatisticas")
def estatisticas():
    c = db()
    return jsonify({
        "animais_registrados": c.execute("SELECT COUNT(*) FROM animal_registro").fetchone()[0],
        "animais_cadastro_implicito": c.execute(
            "SELECT COUNT(*) FROM animal_registro WHERE cadastro_implicito = 1").fetchone()[0],
        "vacinacoes_antirrabicas": c.execute("SELECT COUNT(*) FROM vacinacao_antirrabica").fetchone()[0],
        "operacoes_processadas": c.execute(
            "SELECT COUNT(*) FROM operacao WHERE status='PROCESSADA'").fetchone()[0],
        "operacoes_rejeitadas": c.execute(
            "SELECT COUNT(*) FROM operacao WHERE status='REJEITADA'").fetchone()[0],
        "reenvios_idempotentes": c.execute("SELECT COALESCE(SUM(replays),0) FROM operacao").fetchone()[0],
        "ultimos_animais": [dict(r) for r in c.execute(
            """SELECT microchip, nome, especie, tutor_nome, situacao, cadastro_implicito, atualizado_em
               FROM animal_registro ORDER BY atualizado_em DESC LIMIT 10""")],
        "ultimas_operacoes": [dict(r) for r in c.execute(
            """SELECT protocolo, tipo, status, http_status, microchip, replays, recebida_em
               FROM operacao ORDER BY recebida_em DESC, rowid DESC LIMIT 15""")],
    })


# ---------------------------------------------------------------------
# Painel web e documentação
# ---------------------------------------------------------------------
@app.get("/")
def painel():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "painel.html")


@app.get("/openapi.yaml")
def openapi():
    return send_from_directory(BASE_DIR, "openapi.yaml", mimetype="text/yaml")


@app.get("/docs")
def docs():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "swagger.html")


@app.errorhandler(404)
def nao_encontrado(_e):
    return erro(404, "Recurso não encontrado.")


@app.errorhandler(Exception)
def erro_interno(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return erro(e.code, e.description)
    app.logger.exception(e)
    return erro(500, "Erro interno no serviço governamental.")


init_db()

if __name__ == "__main__":
    print(f"API Governamental Simulada em http://127.0.0.1:{PORT}  (painel: /  docs: /docs)")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
