"""Animais, vínculo/substituição de microchip RFID e situação da integração governamental."""
import requests
from flask import Blueprint, g, jsonify, request

import config
from core.seguranca import login_obrigatorio
from core.validacao import ErroNegocio, Validador, agora, microchip_valido, somente_digitos
from database import get_db, row, rows, transacao
from services import integracao

bp = Blueprint("animais", __name__, url_prefix="/api/animais")

SQL_ANIMAL = """SELECT a.*, e.nome AS especie_nome, r.nome AS raca_nome, t.nome AS tutor_nome,
                       t.cpf AS tutor_cpf
                FROM animal a JOIN especie e ON e.id = a.especie_id
                LEFT JOIN raca r ON r.id = a.raca_id JOIN tutor t ON t.id = a.tutor_id"""


def obter_animal(conn, id_, completo=False):
    r = conn.execute(SQL_ANIMAL + " WHERE a.id = ?", (id_,)).fetchone()
    if not r:
        raise ErroNegocio("Animal não encontrado.", 404)
    a = dict(r)
    if completo:
        a["microchips"] = historico_microchip(conn, id_)
        a["integracoes"] = integracao.listar(conn, animal_id=id_, limite=20)
    return a


def historico_microchip(conn, animal_id):
    return rows(conn.execute(
        """SELECT vm.*, v.nome AS veterinario_nome, v.crmv, v.crmv_uf FROM vinculo_microchip vm
           JOIN veterinario v ON v.id = vm.veterinario_id WHERE vm.animal_id = ? ORDER BY vm.id DESC""",
        (animal_id,)))


def _validar(conn, d):
    val = Validador(d)
    dados = {
        "nome": val.obrigatorio("nome", "Nome", 100),
        "data_nascimento": val.data("data_nascimento", "Data de nascimento", obrigatoria=False, nao_futura=True),
        "idade_estimada_meses": val.numero("idade_estimada_meses", "Idade estimada (meses)", obrigatorio=False,
                                           minimo=0, maximo=600, inteiro=True),
        "sexo": val.escolha("sexo", ["M", "F"], "Sexo"),
        "cor": val.obrigatorio("cor", "Cor", 60),
        "peso_atual": val.numero("peso_atual", "Peso atual (kg)", minimo=0.01, maximo=1500),
        "tutor_id": val.numero("tutor_id", "Tutor responsável", inteiro=True),
        "especie_id": val.numero("especie_id", "Espécie", inteiro=True),
        "raca_id": val.numero("raca_id", "Raça", obrigatorio=False, inteiro=True),
    }
    if dados["data_nascimento"] is None and dados["idade_estimada_meses"] is None:
        val.adicionar("Informe a data de nascimento ou a idade estimada.")
    val.verificar()
    tutor = conn.execute("SELECT situacao FROM tutor WHERE id = ?", (dados["tutor_id"],)).fetchone()
    if not tutor:
        raise ErroNegocio("Todo animal deve possuir um tutor: tutor informado não existe.", 422)
    if tutor["situacao"] != "ATIVO":
        raise ErroNegocio("Tutor informado está inativo.", 422)
    esp = conn.execute("SELECT situacao FROM especie WHERE id = ?", (dados["especie_id"],)).fetchone()
    if not esp or esp["situacao"] != "ATIVO":
        raise ErroNegocio("Espécie inexistente ou inativa.", 422)
    if dados["raca_id"]:
        raca = conn.execute("SELECT especie_id, situacao FROM raca WHERE id = ?", (dados["raca_id"],)).fetchone()
        if not raca:
            raise ErroNegocio("Raça inexistente.", 422)
        if raca["especie_id"] != dados["especie_id"]:
            raise ErroNegocio("A raça selecionada não é compatível com a espécie informada.", 422)
    return dados


@bp.get("")
@login_obrigatorio
def listar():
    sql, params = SQL_ANIMAL + " WHERE 1=1", []
    q = (request.args.get("q") or "").strip()
    if q:
        sql += " AND (a.nome LIKE ? OR t.nome LIKE ? OR a.microchip_atual LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    for filtro, coluna in (("tutor_id", "a.tutor_id"), ("especie_id", "a.especie_id")):
        if request.args.get(filtro):
            sql += f" AND {coluna} = ?"
            params.append(request.args[filtro])
    if request.args.get("microchip"):
        sql += " AND a.microchip_atual = ?"
        params.append(somente_digitos(request.args["microchip"]))
    if request.args.get("situacao"):
        sql += " AND a.situacao = ?"
        params.append(request.args["situacao"].upper())
    if request.args.get("gov_situacao"):
        sql += " AND a.gov_situacao = ?"
        params.append(request.args["gov_situacao"].upper())
    return jsonify(rows(get_db().execute(sql + " ORDER BY a.nome LIMIT 500", params)))


@bp.post("")
@login_obrigatorio
def criar():
    conn = get_db()
    d = request.get_json(silent=True) or {}
    dados = _validar(conn, d)
    chip = somente_digitos(d.get("microchip"))
    with transacao(conn):
        cur = conn.execute(
            """INSERT INTO animal (nome, data_nascimento, idade_estimada_meses, sexo, cor, peso_atual,
                   tutor_id, especie_id, raca_id)
               VALUES (:nome,:data_nascimento,:idade_estimada_meses,:sexo,:cor,:peso_atual,
                       :tutor_id,:especie_id,:raca_id)""", dados)
        animal_id = cur.lastrowid
        integ_ids = []
        if chip:  # vínculo opcional já no cadastro
            integ_ids = _vincular(conn, animal_id, chip, d.get("data_implantacao") or agora()[:10], None)
    integracao.processar_varias(conn, integ_ids)
    return jsonify(obter_animal(conn, animal_id, completo=True)), 201


@bp.get("/<int:id_>")
@login_obrigatorio
def obter(id_):
    return jsonify(obter_animal(get_db(), id_, completo=True))


@bp.put("/<int:id_>")
@login_obrigatorio
def alterar(id_):
    conn = get_db()
    atual = obter_animal(conn, id_)
    d = request.get_json(silent=True) or {}
    dados = _validar(conn, d)
    sit = (d.get("situacao") or atual["situacao"]).upper()
    if sit not in ("ATIVO", "INATIVO", "OBITO"):
        raise ErroNegocio("Situação inválida.", 422)
    with transacao(conn):
        conn.execute(
            """UPDATE animal SET nome=:nome, data_nascimento=:data_nascimento,
                   idade_estimada_meses=:idade_estimada_meses, sexo=:sexo, cor=:cor, peso_atual=:peso_atual,
                   tutor_id=:tutor_id, especie_id=:especie_id, raca_id=:raca_id, situacao=:situacao
               WHERE id=:id""", dict(dados, situacao=sit, id=id_))
        integ_ids = []
        # já registrado no serviço externo -> comunica a atualização cadastral
        if atual["microchip_atual"] and integracao.cadastro_confirmado(conn, id_):
            integ_ids.append(integracao.solicitar_atualizacao(conn, id_))
    integracao.processar_varias(conn, integ_ids)
    return jsonify(obter_animal(conn, id_, completo=True))


@bp.delete("/<int:id_>")
@login_obrigatorio
def inativar(id_):
    conn = get_db()
    obter_animal(conn, id_)
    conn.execute("UPDATE animal SET situacao='INATIVO' WHERE id=?", (id_,))
    return jsonify(obter_animal(conn, id_))


# ---------------------------------------------------------------------
# Microchip RFID
# ---------------------------------------------------------------------
def _vincular(conn, animal_id, chip, data_implantacao, motivo):
    """Vincula (ou substitui) o microchip. Deve ser chamado dentro de uma transação."""
    if not microchip_valido(chip):
        raise ErroNegocio("Microchip deve conter exatamente 15 dígitos (padrão ISO 11784/11785).", 422)
    em_uso = conn.execute(
        """SELECT vm.animal_id, a.nome FROM vinculo_microchip vm JOIN animal a ON a.id = vm.animal_id
           WHERE vm.codigo_microchip = ?""", (chip,)).fetchone()
    if em_uso:
        raise ErroNegocio(f"Microchip já utilizado (animal #{em_uso['animal_id']} - {em_uso['nome']}). "
                          "Um microchip não pode ser reutilizado.", 409)
    ativo = conn.execute("SELECT * FROM vinculo_microchip WHERE animal_id = ? AND ativo = 1",
                         (animal_id,)).fetchone()
    if ativo and not (motivo or "").strip():
        raise ErroNegocio("O animal já possui microchip ativo. Para substituí-lo, informe o motivo.", 422)
    if ativo:  # desativa o anterior, preservando o histórico
        conn.execute("UPDATE vinculo_microchip SET ativo = 0, data_desativacao = ?, motivo_substituicao = ? "
                     "WHERE id = ?", (agora(), motivo.strip(), ativo["id"]))
    cur = conn.execute(
        """INSERT INTO vinculo_microchip (animal_id, codigo_microchip, veterinario_id, data_implantacao)
           VALUES (?,?,?,?)""", (animal_id, chip, g.veterinario["id"], data_implantacao))
    if ativo:
        conn.execute("UPDATE vinculo_microchip SET substituido_por_id = ? WHERE id = ?", (cur.lastrowid, ativo["id"]))
    conn.execute("UPDATE animal SET microchip_atual = NULL WHERE id = ?", (animal_id,))
    conn.execute("UPDATE animal SET microchip_atual = ?, gov_situacao = 'PENDENTE' WHERE id = ?", (chip, animal_id))
    # cadastro/atualização do novo microchip no serviço externo
    ids = [integracao.solicitar_cadastro(conn, animal_id, chip)]
    # vacinas antirrábicas que aguardavam microchip voltam para a fila
    pend = [r["id"] for r in conn.execute(
        """SELECT id FROM integracao_governo
           WHERE animal_id = ? AND tipo_operacao = 'VACINACAO_ANTIRRABICA' AND situacao = 'FALHA'
             AND mensagem_erro LIKE 'Animal sem microchip%'""", (animal_id,))]
    for iid in pend:
        conn.execute("UPDATE integracao_governo SET situacao = 'PENDENTE', proxima_tentativa = ? WHERE id = ?",
                     (agora(), iid))
    return ids + pend


@bp.post("/<int:id_>/microchip")
@login_obrigatorio
def vincular_microchip(id_):
    """Vínculo realizado pelo veterinário AUTENTICADO (ativo e com senha confirmada)."""
    conn = get_db()
    animal = obter_animal(conn, id_)
    if animal["situacao"] != "ATIVO":
        raise ErroNegocio("Somente animais ativos podem receber microchip.", 422)
    d = request.get_json(silent=True) or {}
    val = Validador(d)
    chip = somente_digitos(d.get("codigo_microchip") or d.get("microchip"))
    data_impl = val.data("data_implantacao", "Data de implantação", nao_futura=True)
    val.verificar()
    with transacao(conn):
        ids = _vincular(conn, id_, chip, data_impl, d.get("motivo_substituicao"))
    integracao.processar_varias(conn, ids)
    return jsonify(obter_animal(conn, id_, completo=True)), 201


@bp.get("/<int:id_>/microchips")
@login_obrigatorio
def microchips(id_):
    conn = get_db()
    obter_animal(conn, id_)
    return jsonify(historico_microchip(conn, id_))


# ---------------------------------------------------------------------
# Integração governamental do animal
# ---------------------------------------------------------------------
@bp.post("/<int:id_>/sincronizar-governo")
@login_obrigatorio
def sincronizar(id_):
    conn = get_db()
    a = obter_animal(conn, id_)
    if not a["microchip_atual"]:
        raise ErroNegocio("Vincule um microchip antes de sincronizar com o serviço externo.", 422)
    with transacao(conn):
        if integracao.cadastro_confirmado(conn, id_):
            ids = [integracao.solicitar_atualizacao(conn, id_)]
        else:
            iid = integracao.solicitar_cadastro(conn, id_, a["microchip_atual"])
            conn.execute("UPDATE integracao_governo SET situacao='PENDENTE' WHERE id=? AND situacao='FALHA'", (iid,))
            ids = [iid]
    res = integracao.processar_varias(conn, ids)
    return jsonify({"animal": obter_animal(conn, id_), "integracao": res[0] if res else None})


@bp.get("/<int:id_>/situacao-governo")
@login_obrigatorio
def situacao_governo(id_):
    """Situação local da integração + consulta em tempo real ao serviço externo (quando disponível)."""
    conn = get_db()
    a = obter_animal(conn, id_)
    resp = {
        "animal_id": id_, "microchip": a["microchip_atual"], "gov_situacao": a["gov_situacao"],
        "gov_protocolo": a["gov_protocolo"], "gov_ultima_sync": a["gov_ultima_sync"],
        "integracoes": integracao.listar(conn, animal_id=id_, limite=50),
        "registro_externo": None, "consulta_externa": "NAO_REALIZADA",
    }
    if a["microchip_atual"]:
        try:
            r = requests.get(f"{config.GOV_API_URL}/api/governo/animais/{a['microchip_atual']}",
                             headers={"X-Api-Key": config.GOV_API_KEY},
                             timeout=(config.GOV_TIMEOUT_CONEXAO, config.GOV_TIMEOUT_LEITURA))
            if r.status_code == 200:
                resp["registro_externo"], resp["consulta_externa"] = r.json(), "ENCONTRADO"
            elif r.status_code == 404:
                resp["consulta_externa"] = "NAO_ENCONTRADO"
            else:
                resp["consulta_externa"] = f"INDISPONIVEL (HTTP {r.status_code})"
        except requests.RequestException:
            resp["consulta_externa"] = "INDISPONIVEL (sem comunicação)"
    return jsonify(resp)


@bp.get("/<int:id_>/integracoes")
@login_obrigatorio
def integracoes_animal(id_):
    conn = get_db()
    obter_animal(conn, id_)
    return jsonify(integracao.listar(conn, animal_id=id_))
