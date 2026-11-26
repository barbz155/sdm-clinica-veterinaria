"""Cadastros básicos: CEP (ViaCEP), endereços, tutores, espécies, raças e veterinários."""
from flask import Blueprint, g, jsonify, request

from clients.viacep import consultar_cep
from core.seguranca import login_obrigatorio
from core.validacao import ErroNegocio, Validador, somente_digitos
from database import get_db, row, rows, transacao
from routes.auth import UFS

bp = Blueprint("cadastros", __name__, url_prefix="/api")

SITUACOES = ["ATIVO", "INATIVO"]


def _obter(conn, tabela, id_, nome):
    r = conn.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id_,)).fetchone()
    if not r:
        raise ErroNegocio(f"{nome} não encontrado(a).", 404)
    return row(r)


# =====================================================================
# CEP (consumo da API pública ViaCEP)
# =====================================================================
@bp.get("/cep/<cep>")
@login_obrigatorio
def cep(cep):
    return jsonify(consultar_cep(cep))


# =====================================================================
# Endereços
# =====================================================================
def validar_endereco(d, val=None):
    val = val or Validador(d)
    cep_ = somente_digitos(d.get("cep"))
    if len(cep_) != 8:
        val.adicionar("Endereço: CEP deve ter 8 dígitos.")
    end = {
        "cep": cep_,
        "logradouro": (d.get("logradouro") or "").strip(),
        "numero": str(d.get("numero") or "").strip(),
        "complemento": (d.get("complemento") or "").strip() or None,
        "bairro": (d.get("bairro") or "").strip(),
        "cidade": (d.get("cidade") or "").strip(),
        "uf": (d.get("uf") or "").strip().upper(),
        "codigo_ibge": somente_digitos(d.get("codigo_ibge")) or None,
    }
    for campo, rot in (("logradouro", "Logradouro"), ("numero", "Número"), ("bairro", "Bairro"),
                       ("cidade", "Cidade")):
        if not end[campo]:
            val.adicionar(f"Endereço: {rot} é obrigatório.")
    if end["uf"] not in UFS:
        val.adicionar("Endereço: UF inválida.")
    if end["codigo_ibge"] and len(end["codigo_ibge"]) != 7:
        val.adicionar("Endereço: código IBGE deve ter 7 dígitos.")
    return end


def inserir_endereco(conn, end, tipo="TUTOR"):
    cur = conn.execute(
        """INSERT INTO endereco (cep, logradouro, numero, complemento, bairro, cidade, uf, codigo_ibge, tipo)
           VALUES (:cep,:logradouro,:numero,:complemento,:bairro,:cidade,:uf,:codigo_ibge, :tipo)""",
        dict(end, tipo=tipo),
    )
    return cur.lastrowid


def atualizar_endereco(conn, end_id, end):
    conn.execute(
        """UPDATE endereco SET cep=:cep, logradouro=:logradouro, numero=:numero, complemento=:complemento,
               bairro=:bairro, cidade=:cidade, uf=:uf, codigo_ibge=:codigo_ibge WHERE id=:id""",
        dict(end, id=end_id),
    )


@bp.post("/enderecos")
@login_obrigatorio
def criar_endereco():
    d = request.get_json(silent=True) or {}
    val = Validador(d)
    end = validar_endereco(d, val)
    tipo = val.escolha("tipo", ["TUTOR", "CLINICA"], padrao="TUTOR", obrigatorio=False)
    val.verificar()
    conn = get_db()
    end_id = inserir_endereco(conn, end, tipo)
    return jsonify(_obter(conn, "endereco", end_id, "Endereço")), 201


@bp.get("/enderecos/<int:id_>")
@login_obrigatorio
def obter_endereco(id_):
    return jsonify(_obter(get_db(), "endereco", id_, "Endereço"))


@bp.put("/enderecos/<int:id_>")
@login_obrigatorio
def alterar_endereco(id_):
    conn = get_db()
    _obter(conn, "endereco", id_, "Endereço")
    d = request.get_json(silent=True) or {}
    val = Validador(d)
    end = validar_endereco(d, val)
    val.verificar()
    atualizar_endereco(conn, id_, end)
    return jsonify(_obter(conn, "endereco", id_, "Endereço"))


@bp.get("/clinica/endereco")
@login_obrigatorio
def endereco_clinica():
    r = get_db().execute("SELECT * FROM endereco WHERE tipo='CLINICA' ORDER BY id LIMIT 1").fetchone()
    return jsonify(row(r))


# =====================================================================
# Tutores
# =====================================================================
SQL_TUTOR = """SELECT t.*, e.cep, e.logradouro, e.numero, e.complemento, e.bairro, e.cidade, e.uf,
                      e.codigo_ibge,
                      (SELECT COUNT(*) FROM animal a WHERE a.tutor_id = t.id AND a.situacao='ATIVO') AS qtd_animais
               FROM tutor t JOIN endereco e ON e.id = t.endereco_id"""


def _tutor(conn, id_):
    r = conn.execute(SQL_TUTOR + " WHERE t.id = ?", (id_,)).fetchone()
    if not r:
        raise ErroNegocio("Tutor não encontrado.", 404)
    t = dict(r)
    t["endereco"] = {k: t.pop(k) for k in ("cep", "logradouro", "numero", "complemento", "bairro",
                                            "cidade", "uf", "codigo_ibge")}
    t["endereco"]["id"] = t["endereco_id"]
    return t


def _validar_tutor(d):
    val = Validador(d)
    dados = {
        "nome": val.obrigatorio("nome", "Nome completo", 150),
        "cpf": val.cpf(),
        "data_nascimento": val.data("data_nascimento", "Data de nascimento", nao_futura=True),
        "email": val.email(),
        "telefone": val.telefone(),
    }
    end = validar_endereco(d.get("endereco") or {}, val)
    val.verificar()
    return dados, end


@bp.get("/tutores")
@login_obrigatorio
def listar_tutores():
    q = (request.args.get("q") or "").strip()
    situacao = request.args.get("situacao")
    sql, params = SQL_TUTOR + " WHERE 1=1", []
    if q:
        sql += " AND (t.nome LIKE ? OR t.cpf LIKE ?)"
        params += [f"%{q}%", f"%{somente_digitos(q) or q}%"]
    if situacao:
        sql += " AND t.situacao = ?"
        params.append(situacao.upper())
    return jsonify(rows(get_db().execute(sql + " ORDER BY t.nome LIMIT 500", params)))


@bp.post("/tutores")
@login_obrigatorio
def criar_tutor():
    dados, end = _validar_tutor(request.get_json(silent=True) or {})
    conn = get_db()
    with transacao(conn):
        if conn.execute("SELECT 1 FROM tutor WHERE cpf = ?", (dados["cpf"],)).fetchone():
            raise ErroNegocio("Já existe um tutor cadastrado com este CPF.", 409)
        dados["endereco_id"] = inserir_endereco(conn, end)
        cur = conn.execute(
            """INSERT INTO tutor (nome, cpf, data_nascimento, email, telefone, endereco_id)
               VALUES (:nome,:cpf,:data_nascimento,:email,:telefone,:endereco_id)""", dados)
    return jsonify(_tutor(conn, cur.lastrowid)), 201


@bp.get("/tutores/<int:id_>")
@login_obrigatorio
def obter_tutor(id_):
    return jsonify(_tutor(get_db(), id_))


@bp.put("/tutores/<int:id_>")
@login_obrigatorio
def alterar_tutor(id_):
    conn = get_db()
    atual = _tutor(conn, id_)
    d = request.get_json(silent=True) or {}
    dados, end = _validar_tutor(d)
    situacao = (d.get("situacao") or atual["situacao"]).upper()
    if situacao not in SITUACOES:
        raise ErroNegocio("Situação inválida.", 422)
    with transacao(conn):
        if conn.execute("SELECT 1 FROM tutor WHERE cpf = ? AND id <> ?", (dados["cpf"], id_)).fetchone():
            raise ErroNegocio("Já existe um tutor cadastrado com este CPF.", 409)
        atualizar_endereco(conn, atual["endereco_id"], end)
        conn.execute(
            """UPDATE tutor SET nome=:nome, cpf=:cpf, data_nascimento=:data_nascimento, email=:email,
                   telefone=:telefone, situacao=:situacao WHERE id=:id""",
            dict(dados, situacao=situacao, id=id_))
    return jsonify(_tutor(conn, id_))


@bp.delete("/tutores/<int:id_>")
@login_obrigatorio
def inativar_tutor(id_):
    """Exclusão lógica: o tutor passa a INATIVO (histórico preservado)."""
    conn = get_db()
    _tutor(conn, id_)
    conn.execute("UPDATE tutor SET situacao = 'INATIVO' WHERE id = ?", (id_,))
    return jsonify(_tutor(conn, id_))


@bp.get("/tutores/<int:id_>/animais")
@login_obrigatorio
def animais_do_tutor(id_):
    conn = get_db()
    _tutor(conn, id_)
    return jsonify(rows(conn.execute(
        """SELECT a.*, e.nome AS especie_nome, r.nome AS raca_nome FROM animal a
           JOIN especie e ON e.id=a.especie_id LEFT JOIN raca r ON r.id=a.raca_id
           WHERE a.tutor_id = ? ORDER BY a.nome""", (id_,))))


# =====================================================================
# Espécies
# =====================================================================
@bp.get("/especies")
@login_obrigatorio
def listar_especies():
    sql = "SELECT * FROM especie"
    if request.args.get("situacao"):
        return jsonify(rows(get_db().execute(sql + " WHERE situacao = ? ORDER BY nome",
                                             (request.args["situacao"].upper(),))))
    return jsonify(rows(get_db().execute(sql + " ORDER BY nome")))


@bp.post("/especies")
@login_obrigatorio
def criar_especie():
    d = request.get_json(silent=True) or {}
    val = Validador(d)
    nome = val.obrigatorio("nome", "Nome", 60)
    desc = val.opcional("descricao", 255)
    val.verificar()
    conn = get_db()
    if conn.execute("SELECT 1 FROM especie WHERE lower(nome) = lower(?)", (nome,)).fetchone():
        raise ErroNegocio("Espécie já cadastrada.", 409)
    cur = conn.execute("INSERT INTO especie (nome, descricao) VALUES (?,?)", (nome, desc))
    return jsonify(_obter(conn, "especie", cur.lastrowid, "Espécie")), 201


@bp.get("/especies/<int:id_>")
@login_obrigatorio
def obter_especie(id_):
    return jsonify(_obter(get_db(), "especie", id_, "Espécie"))


@bp.put("/especies/<int:id_>")
@login_obrigatorio
def alterar_especie(id_):
    conn = get_db()
    _obter(conn, "especie", id_, "Espécie")
    d = request.get_json(silent=True) or {}
    val = Validador(d)
    nome = val.obrigatorio("nome", "Nome", 60)
    desc = val.opcional("descricao", 255)
    sit = val.escolha("situacao", SITUACOES, padrao="ATIVO", obrigatorio=False)
    val.verificar()
    if conn.execute("SELECT 1 FROM especie WHERE lower(nome)=lower(?) AND id<>?", (nome, id_)).fetchone():
        raise ErroNegocio("Espécie já cadastrada.", 409)
    conn.execute("UPDATE especie SET nome=?, descricao=?, situacao=? WHERE id=?", (nome, desc, sit, id_))
    return jsonify(_obter(conn, "especie", id_, "Espécie"))


@bp.delete("/especies/<int:id_>")
@login_obrigatorio
def inativar_especie(id_):
    conn = get_db()
    _obter(conn, "especie", id_, "Espécie")
    conn.execute("UPDATE especie SET situacao='INATIVO' WHERE id=?", (id_,))
    return jsonify(_obter(conn, "especie", id_, "Espécie"))


# =====================================================================
# Raças
# =====================================================================
SQL_RACA = "SELECT r.*, e.nome AS especie_nome FROM raca r JOIN especie e ON e.id = r.especie_id"


@bp.get("/racas")
@login_obrigatorio
def listar_racas():
    sql, params = SQL_RACA + " WHERE 1=1", []
    if request.args.get("especie_id"):
        sql += " AND r.especie_id = ?"
        params.append(request.args["especie_id"])
    if request.args.get("situacao"):
        sql += " AND r.situacao = ?"
        params.append(request.args["situacao"].upper())
    return jsonify(rows(get_db().execute(sql + " ORDER BY e.nome, r.nome", params)))


@bp.get("/especies/<int:id_>/racas")
@login_obrigatorio
def racas_da_especie(id_):
    return jsonify(rows(get_db().execute(SQL_RACA + " WHERE r.especie_id=? AND r.situacao='ATIVO' ORDER BY r.nome",
                                         (id_,))))


def _validar_raca(conn, d):
    val = Validador(d)
    nome = val.obrigatorio("nome", "Nome", 80)
    desc = val.opcional("descricao", 255)
    esp = val.numero("especie_id", "Espécie", inteiro=True)
    sit = val.escolha("situacao", SITUACOES, padrao="ATIVO", obrigatorio=False)
    val.verificar()
    e = conn.execute("SELECT situacao FROM especie WHERE id = ?", (esp,)).fetchone()
    if not e:
        raise ErroNegocio("Espécie informada não existe.", 422)
    if e["situacao"] != "ATIVO":
        raise ErroNegocio("Espécie informada está inativa.", 422)
    return nome, desc, esp, sit


@bp.post("/racas")
@login_obrigatorio
def criar_raca():
    conn = get_db()
    nome, desc, esp, _ = _validar_raca(conn, request.get_json(silent=True) or {})
    if conn.execute("SELECT 1 FROM raca WHERE lower(nome)=lower(?) AND especie_id=?", (nome, esp)).fetchone():
        raise ErroNegocio("Raça já cadastrada para esta espécie.", 409)
    cur = conn.execute("INSERT INTO raca (nome, descricao, especie_id) VALUES (?,?,?)", (nome, desc, esp))
    return jsonify(row(conn.execute(SQL_RACA + " WHERE r.id=?", (cur.lastrowid,)).fetchone())), 201


@bp.put("/racas/<int:id_>")
@login_obrigatorio
def alterar_raca(id_):
    conn = get_db()
    _obter(conn, "raca", id_, "Raça")
    nome, desc, esp, sit = _validar_raca(conn, request.get_json(silent=True) or {})
    if conn.execute("SELECT 1 FROM animal WHERE raca_id=? AND especie_id<>?", (id_, esp)).fetchone():
        raise ErroNegocio("Não é possível mudar a espécie: há animais vinculados a esta raça.", 409)
    conn.execute("UPDATE raca SET nome=?, descricao=?, especie_id=?, situacao=? WHERE id=?",
                 (nome, desc, esp, sit, id_))
    return jsonify(row(conn.execute(SQL_RACA + " WHERE r.id=?", (id_,)).fetchone()))


@bp.delete("/racas/<int:id_>")
@login_obrigatorio
def inativar_raca(id_):
    conn = get_db()
    _obter(conn, "raca", id_, "Raça")
    conn.execute("UPDATE raca SET situacao='INATIVO' WHERE id=?", (id_,))
    return jsonify(row(conn.execute(SQL_RACA + " WHERE r.id=?", (id_,)).fetchone()))


# =====================================================================
# Veterinários (gestão pelos usuários autenticados)
# =====================================================================
CAMPOS_VET = """id, nome, cpf, crmv, crmv_uf, email, telefone, senha_confirmada, data_confirmacao,
                data_cadastro, situacao, ultimo_acesso"""


@bp.get("/veterinarios")
@login_obrigatorio
def listar_veterinarios():
    return jsonify(rows(get_db().execute(f"SELECT {CAMPOS_VET} FROM veterinario ORDER BY nome")))


@bp.get("/veterinarios/<int:id_>")
@login_obrigatorio
def obter_veterinario(id_):
    r = get_db().execute(f"SELECT {CAMPOS_VET} FROM veterinario WHERE id=?", (id_,)).fetchone()
    if not r:
        raise ErroNegocio("Veterinário não encontrado.", 404)
    return jsonify(row(r))


@bp.put("/veterinarios/<int:id_>")
@login_obrigatorio
def alterar_veterinario(id_):
    conn = get_db()
    _obter(conn, "veterinario", id_, "Veterinário")
    d = request.get_json(silent=True) or {}
    val = Validador(d)
    nome = val.obrigatorio("nome", "Nome", 150)
    tel = val.telefone()
    email = val.email()
    val.verificar()
    if conn.execute("SELECT 1 FROM veterinario WHERE email=? AND id<>?", (email, id_)).fetchone():
        raise ErroNegocio("E-mail já utilizado por outro veterinário.", 409)
    conn.execute("UPDATE veterinario SET nome=?, telefone=?, email=? WHERE id=?", (nome, tel, email, id_))
    return obter_veterinario(id_)


@bp.patch("/veterinarios/<int:id_>/situacao")
@login_obrigatorio
def situacao_veterinario(id_):
    conn = get_db()
    _obter(conn, "veterinario", id_, "Veterinário")
    sit = ((request.get_json(silent=True) or {}).get("situacao") or "").upper()
    if sit not in SITUACOES:
        raise ErroNegocio("Situação deve ser ATIVO ou INATIVO.", 422)
    if id_ == g.veterinario["id"] and sit == "INATIVO":
        raise ErroNegocio("Você não pode inativar o seu próprio usuário.", 409)
    conn.execute("UPDATE veterinario SET situacao=? WHERE id=?", (sit, id_))
    if sit == "INATIVO":  # encerra sessões abertas imediatamente
        conn.execute("UPDATE sessao SET encerrada_em=datetime('now','localtime') "
                     "WHERE veterinario_id=? AND encerrada_em IS NULL", (id_,))
    return obter_veterinario(id_)
