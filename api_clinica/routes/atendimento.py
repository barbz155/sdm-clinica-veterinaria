"""Consultas, vacinas (com comunicação obrigatória da antirrábica) e controle das integrações."""
from datetime import date, timedelta

from flask import Blueprint, g, jsonify, request

from core.seguranca import login_obrigatorio
from core.validacao import ErroNegocio, Validador
from database import get_db, row, rows, transacao
from routes.animais import obter_animal
from services import integracao

bp = Blueprint("atendimento", __name__, url_prefix="/api")

# =====================================================================
# Consultas
# =====================================================================
SIT_CONSULTA = ["AGENDADA", "REALIZADA", "CANCELADA", "NAO_COMPARECEU"]
SQL_CONSULTA = """SELECT c.*, a.nome AS animal_nome, v.nome AS veterinario_nome, v.crmv, v.crmv_uf
                  FROM consulta c JOIN animal a ON a.id = c.animal_id
                  JOIN veterinario v ON v.id = c.veterinario_id"""


def _consulta(conn, id_):
    r = conn.execute(SQL_CONSULTA + " WHERE c.id = ?", (id_,)).fetchone()
    if not r:
        raise ErroNegocio("Consulta não encontrada.", 404)
    return row(r)


def _validar_consulta(conn, d):
    val = Validador(d)
    c = {
        "animal_id": val.numero("animal_id", "Animal", inteiro=True),
        "data_hora": val.data_hora("data_hora", "Data e hora"),
        "motivo": val.obrigatorio("motivo", "Motivo do atendimento", 255),
        "anamnese": val.opcional("anamnese"),
        "sintomas": val.opcional("sintomas"),
        "diagnostico": val.opcional("diagnostico"),
        "tratamento": val.opcional("tratamento"),
        "prescricao": val.opcional("prescricao"),
        "peso_registrado": val.numero("peso_registrado", "Peso", obrigatorio=False, minimo=0.01, maximo=1500),
        "temperatura": val.numero("temperatura", "Temperatura (°C)", obrigatorio=False, minimo=30, maximo=45),
        "observacoes": val.opcional("observacoes"),
        "situacao": val.escolha("situacao", SIT_CONSULTA, "Situação", padrao="AGENDADA", obrigatorio=False),
    }
    if c["situacao"] == "REALIZADA" and not (c["diagnostico"] or c["tratamento"] or c["anamnese"]):
        val.adicionar("Consulta realizada deve conter ao menos anamnese, diagnóstico ou tratamento.")
    val.verificar()
    a = obter_animal(conn, c["animal_id"])
    if a["situacao"] != "ATIVO" and c["situacao"] in ("AGENDADA", "REALIZADA"):
        raise ErroNegocio("Animal não está ativo.", 422)
    return c


def _atualiza_peso(conn, c):
    if c["situacao"] == "REALIZADA" and c["peso_registrado"]:
        conn.execute("UPDATE animal SET peso_atual = ? WHERE id = ?", (c["peso_registrado"], c["animal_id"]))


@bp.post("/consultas")
@login_obrigatorio
def criar_consulta():
    conn = get_db()
    c = _validar_consulta(conn, request.get_json(silent=True) or {})
    c["veterinario_id"] = g.veterinario["id"]  # responsável = veterinário autenticado
    with transacao(conn):
        cur = conn.execute(
            """INSERT INTO consulta (animal_id, veterinario_id, data_hora, motivo, anamnese, sintomas, diagnostico,
                   tratamento, prescricao, peso_registrado, temperatura, observacoes, situacao)
               VALUES (:animal_id,:veterinario_id,:data_hora,:motivo,:anamnese,:sintomas,:diagnostico,
                       :tratamento,:prescricao,:peso_registrado,:temperatura,:observacoes,:situacao)""", c)
        _atualiza_peso(conn, c)
    return jsonify(_consulta(conn, cur.lastrowid)), 201


@bp.get("/consultas")
@login_obrigatorio
def listar_consultas():
    sql, params = SQL_CONSULTA + " WHERE 1=1", []
    if request.args.get("situacao"):
        sql += " AND c.situacao = ?"
        params.append(request.args["situacao"].upper())
    if request.args.get("data"):
        sql += " AND date(c.data_hora) = ?"
        params.append(request.args["data"])
    return jsonify(rows(get_db().execute(sql + " ORDER BY c.data_hora DESC LIMIT 300", params)))


@bp.get("/consultas/<int:id_>")
@login_obrigatorio
def obter_consulta(id_):
    return jsonify(_consulta(get_db(), id_))


@bp.put("/consultas/<int:id_>")
@login_obrigatorio
def alterar_consulta(id_):
    conn = get_db()
    atual = _consulta(conn, id_)
    if atual["situacao"] in ("CANCELADA",):
        raise ErroNegocio("Consulta cancelada não pode ser alterada.", 409)
    c = _validar_consulta(conn, request.get_json(silent=True) or {})
    if c["animal_id"] != atual["animal_id"]:
        raise ErroNegocio("Não é permitido trocar o animal de uma consulta.", 422)
    with transacao(conn):
        conn.execute(
            """UPDATE consulta SET data_hora=:data_hora, motivo=:motivo, anamnese=:anamnese, sintomas=:sintomas,
                   diagnostico=:diagnostico, tratamento=:tratamento, prescricao=:prescricao,
                   peso_registrado=:peso_registrado, temperatura=:temperatura, observacoes=:observacoes,
                   situacao=:situacao WHERE id=:id""", dict(c, id=id_))
        _atualiza_peso(conn, c)
    return jsonify(_consulta(conn, id_))


@bp.delete("/consultas/<int:id_>")
@login_obrigatorio
def cancelar_consulta(id_):
    conn = get_db()
    atual = _consulta(conn, id_)
    if atual["situacao"] == "REALIZADA":
        raise ErroNegocio("Consulta já realizada não pode ser cancelada (histórico clínico).", 409)
    conn.execute("UPDATE consulta SET situacao='CANCELADA' WHERE id=?", (id_,))
    return jsonify(_consulta(conn, id_))


@bp.get("/animais/<int:id_>/consultas")
@login_obrigatorio
def historico_consultas(id_):
    conn = get_db()
    obter_animal(conn, id_)
    return jsonify(rows(conn.execute(SQL_CONSULTA + " WHERE c.animal_id = ? ORDER BY c.data_hora DESC", (id_,))))


# =====================================================================
# Vacinas
# =====================================================================
TIPOS_VACINA = {
    "ANTIRRABICA": "Antirrábica (raiva)",
    "POLIVALENTE_CANINA": "Polivalente canina (V8/V10)",
    "POLIVALENTE_FELINA": "Polivalente felina (V3/V4/V5)",
    "GRIPE_CANINA": "Gripe canina (tosse dos canis)",
    "GIARDIASE": "Giardíase",
    "LEISHMANIOSE": "Leishmaniose",
    "LEUCEMIA_FELINA": "Leucemia felina (FeLV)",
    "OUTRA": "Outra",
}
VIAS = ["SUBCUTANEA", "INTRAMUSCULAR", "INTRANASAL", "ORAL"]
SIT_VACINA = ["AGENDADA", "APLICADA", "CANCELADA"]
SQL_VACINA = """SELECT va.*, a.nome AS animal_nome, a.microchip_atual, ve.nome AS veterinario_nome,
                       ig.id AS integracao_id, ig.situacao AS comunicacao_situacao,
                       ig.protocolo_externo AS comunicacao_protocolo, ig.tentativas AS comunicacao_tentativas,
                       ig.mensagem_erro AS comunicacao_mensagem
                FROM vacina va JOIN animal a ON a.id = va.animal_id
                JOIN veterinario ve ON ve.id = va.veterinario_id
                LEFT JOIN integracao_governo ig ON ig.vacina_id = va.id"""


def _vacina(conn, id_):
    r = conn.execute(SQL_VACINA + " WHERE va.id = ?", (id_,)).fetchone()
    if not r:
        raise ErroNegocio("Aplicação de vacina não encontrada.", 404)
    return _fmt_vacina(row(r))


def _fmt_vacina(v):
    v["antirrabica"] = bool(v["antirrabica"])
    if v["antirrabica"]:
        v["comunicacao_governo"] = {
            "obrigatoria": True,
            "registro_local": "REGISTRADA" if v["situacao"] == "APLICADA" else "NAO_APLICADA",
            "situacao": v["comunicacao_situacao"] or ("NAO_GERADA" if v["situacao"] != "APLICADA" else "PENDENTE"),
            "protocolo": v["comunicacao_protocolo"], "tentativas": v["comunicacao_tentativas"],
            "mensagem": v["comunicacao_mensagem"], "integracao_id": v["integracao_id"],
        }
    else:
        v["comunicacao_governo"] = {"obrigatoria": False, "situacao": "NAO_SE_APLICA"}
    for k in ("comunicacao_situacao", "comunicacao_protocolo", "comunicacao_tentativas", "comunicacao_mensagem"):
        v.pop(k, None)
    return v


def _validar_vacina(conn, d):
    val = Validador(d)
    v = {
        "animal_id": val.numero("animal_id", "Animal", inteiro=True),
        "nome_vacina": val.obrigatorio("nome_vacina", "Nome da vacina", 100),
        "tipo_vacina": val.escolha("tipo_vacina", list(TIPOS_VACINA), "Tipo de vacina"),
        "fabricante": val.obrigatorio("fabricante", "Fabricante", 100),
        "lote": val.obrigatorio("lote", "Número do lote", 40),
        "data_aplicacao": val.data("data_aplicacao", "Data de aplicação"),
        "dose": val.obrigatorio("dose", "Dose/etapa", 40),
        "via_aplicacao": val.escolha("via_aplicacao", VIAS, "Via de aplicação"),
        "data_proxima_dose": val.data("data_proxima_dose", "Data da próxima dose", obrigatoria=False),
        "data_validade_lote": val.data("data_validade_lote", "Validade do lote"),
        "observacoes": val.opcional("observacoes"),
        "situacao": val.escolha("situacao", SIT_VACINA, "Situação", padrao="APLICADA", obrigatorio=False),
    }
    # classificação ESTRUTURADA: o indicador vem do tipo, nunca do texto digitado
    v["antirrabica"] = 1 if v["tipo_vacina"] == "ANTIRRABICA" else 0
    hoje = date.today().isoformat()
    if v["data_aplicacao"]:
        if v["situacao"] == "APLICADA" and v["data_aplicacao"] > hoje:
            val.adicionar("Vacina aplicada não pode ter data de aplicação futura.")
        if v["data_validade_lote"] and v["data_validade_lote"] < v["data_aplicacao"]:
            val.adicionar("Lote vencido na data de aplicação.")
        if v["data_proxima_dose"] and v["data_proxima_dose"] <= v["data_aplicacao"]:
            val.adicionar("A próxima dose deve ser posterior à data de aplicação.")
    val.verificar()
    a = obter_animal(conn, v["animal_id"])
    if a["situacao"] != "ATIVO":
        raise ErroNegocio("Animal não está ativo.", 422)
    return v


@bp.get("/vacinas/tipos")
@login_obrigatorio
def tipos_vacina():
    return jsonify([{"codigo": k, "descricao": d, "antirrabica": k == "ANTIRRABICA",
                     "comunicacao_obrigatoria": k == "ANTIRRABICA"} for k, d in TIPOS_VACINA.items()])


@bp.post("/vacinas")
@login_obrigatorio
def registrar_vacina():
    conn = get_db()
    v = _validar_vacina(conn, request.get_json(silent=True) or {})
    v["veterinario_id"] = g.veterinario["id"]
    integ_id = None
    with transacao(conn):
        # 1) registro LOCAL da aplicação
        cur = conn.execute(
            """INSERT INTO vacina (animal_id, veterinario_id, nome_vacina, tipo_vacina, antirrabica, fabricante,
                   lote, data_aplicacao, dose, via_aplicacao, data_proxima_dose, data_validade_lote,
                   observacoes, situacao)
               VALUES (:animal_id,:veterinario_id,:nome_vacina,:tipo_vacina,:antirrabica,:fabricante,:lote,
                       :data_aplicacao,:dose,:via_aplicacao,:data_proxima_dose,:data_validade_lote,
                       :observacoes,:situacao)""", v)
        vacina_id = cur.lastrowid
        # 2) comunicação OBRIGATÓRIA (só antirrábica efetivamente aplicada), gravada na mesma transação
        if v["antirrabica"] and v["situacao"] == "APLICADA":
            integ_id = integracao.solicitar_vacina_antirrabica(conn, vacina_id, v["animal_id"])
    # 3) envio após o commit: falhas não desfazem o registro local
    if integ_id:
        integracao.processar_varias(conn, [integ_id])
    return jsonify(_vacina(conn, vacina_id)), 201


@bp.get("/vacinas/<int:id_>")
@login_obrigatorio
def obter_vacina(id_):
    return jsonify(_vacina(get_db(), id_))


@bp.put("/vacinas/<int:id_>")
@login_obrigatorio
def alterar_vacina(id_):
    """Permite completar uma vacina AGENDADA (ex.: marcar como APLICADA). Aplicadas são imutáveis,
    exceto observações e data da próxima dose, para preservar a rastreabilidade."""
    conn = get_db()
    atual = _vacina(conn, id_)
    d = request.get_json(silent=True) or {}
    if atual["situacao"] == "CANCELADA":
        raise ErroNegocio("Aplicação cancelada não pode ser alterada.", 409)
    if atual["situacao"] == "APLICADA":
        val = Validador(d)
        prox = val.data("data_proxima_dose", "Data da próxima dose", obrigatoria=False)
        val.verificar()
        if prox and prox <= atual["data_aplicacao"]:
            raise ErroNegocio("A próxima dose deve ser posterior à data de aplicação.", 422)
        conn.execute("UPDATE vacina SET observacoes=?, data_proxima_dose=? WHERE id=?",
                     (d.get("observacoes", atual["observacoes"]), prox, id_))
        return jsonify(_vacina(conn, id_))
    v = _validar_vacina(conn, dict(atual, **d))
    if v["animal_id"] != atual["animal_id"]:
        raise ErroNegocio("Não é permitido trocar o animal da aplicação.", 422)
    integ_id = None
    with transacao(conn):
        conn.execute(
            """UPDATE vacina SET nome_vacina=:nome_vacina, tipo_vacina=:tipo_vacina, antirrabica=:antirrabica,
                   fabricante=:fabricante, lote=:lote, data_aplicacao=:data_aplicacao, dose=:dose,
                   via_aplicacao=:via_aplicacao, data_proxima_dose=:data_proxima_dose,
                   data_validade_lote=:data_validade_lote, observacoes=:observacoes, situacao=:situacao
               WHERE id=:id""", dict(v, id=id_))
        if v["antirrabica"] and v["situacao"] == "APLICADA":
            integ_id = integracao.solicitar_vacina_antirrabica(conn, id_, v["animal_id"])
    if integ_id:
        integracao.processar_varias(conn, [integ_id])
    return jsonify(_vacina(conn, id_))


@bp.delete("/vacinas/<int:id_>")
@login_obrigatorio
def cancelar_vacina(id_):
    conn = get_db()
    atual = _vacina(conn, id_)
    if atual["situacao"] == "APLICADA":
        raise ErroNegocio("Vacina já aplicada não pode ser cancelada (rastreabilidade).", 409)
    conn.execute("UPDATE vacina SET situacao='CANCELADA' WHERE id=?", (id_,))
    return jsonify(_vacina(conn, id_))


@bp.get("/animais/<int:id_>/vacinas")
@login_obrigatorio
def historico_vacinas(id_):
    conn = get_db()
    obter_animal(conn, id_)
    hist = [_fmt_vacina(dict(r)) for r in conn.execute(
        SQL_VACINA + " WHERE va.animal_id = ? ORDER BY va.data_aplicacao DESC, va.id DESC", (id_,))]
    proximas = [
        {"vacina_id": v["id"], "nome_vacina": v["nome_vacina"], "tipo_vacina": v["tipo_vacina"],
         "data_proxima_dose": v["data_proxima_dose"],
         "atrasada": v["data_proxima_dose"] < date.today().isoformat()}
        for v in hist if v["situacao"] == "APLICADA" and v["data_proxima_dose"]
        and not _tem_dose_posterior(hist, v)
    ]
    proximas.sort(key=lambda p: p["data_proxima_dose"])
    return jsonify({"historico": hist, "proximas_doses": proximas})


def _tem_dose_posterior(hist, v):
    """Uma próxima dose prevista deixa de ser pendente se já existe aplicação do mesmo tipo depois dela."""
    return any(o["id"] != v["id"] and o["situacao"] == "APLICADA" and o["tipo_vacina"] == v["tipo_vacina"]
               and o["data_aplicacao"] > v["data_aplicacao"] for o in hist)


@bp.get("/vacinas/proximas-doses")
@login_obrigatorio
def proximas_doses():
    dias = int(request.args.get("dias", 30))
    limite = (date.today() + timedelta(days=dias)).isoformat()
    r = rows(get_db().execute(
        """SELECT va.id AS vacina_id, va.animal_id, a.nome AS animal_nome, t.nome AS tutor_nome,
                  t.telefone AS tutor_telefone, va.nome_vacina, va.tipo_vacina, va.data_aplicacao,
                  va.data_proxima_dose, (va.data_proxima_dose < date('now','localtime')) AS atrasada
           FROM vacina va JOIN animal a ON a.id = va.animal_id JOIN tutor t ON t.id = a.tutor_id
           WHERE va.situacao = 'APLICADA' AND va.data_proxima_dose IS NOT NULL AND va.data_proxima_dose <= ?
             AND a.situacao = 'ATIVO'
             AND NOT EXISTS (SELECT 1 FROM vacina v2 WHERE v2.animal_id = va.animal_id AND v2.situacao='APLICADA'
                             AND v2.tipo_vacina = va.tipo_vacina AND v2.data_aplicacao > va.data_aplicacao)
           ORDER BY va.data_proxima_dose""", (limite,)))
    for x in r:
        x["atrasada"] = bool(x["atrasada"])
    return jsonify(r)


# =====================================================================
# Controle das integrações governamentais
# =====================================================================
@bp.get("/integracoes")
@login_obrigatorio
def listar_integracoes():
    a = request.args
    return jsonify(integracao.listar(get_db(), a.get("situacao"), a.get("animal_id"), a.get("tipo")))


@bp.get("/integracoes/resumo")
@login_obrigatorio
def resumo_integracoes():
    r = get_db().execute("SELECT situacao, COUNT(*) AS qtd FROM integracao_governo GROUP BY situacao").fetchall()
    base = {"PENDENTE": 0, "ENVIADA": 0, "CONFIRMADA": 0, "FALHA": 0}
    base.update({x["situacao"]: x["qtd"] for x in r})
    return jsonify(base)


@bp.get("/integracoes/<int:id_>")
@login_obrigatorio
def obter_integracao(id_):
    r = integracao.obter(get_db(), id_)
    if not r:
        raise ErroNegocio("Integração não encontrada.", 404)
    return jsonify(r)


@bp.post("/integracoes/<int:id_>/reenviar")
@login_obrigatorio
def reenviar(id_):
    """Reenvio manual. Com ?forcar=true repete até uma operação já CONFIRMADA (demonstra a idempotência)."""
    conn = get_db()
    atual = integracao.obter(conn, id_)
    if not atual:
        raise ErroNegocio("Integração não encontrada.", 404)
    forcar = request.args.get("forcar", "").lower() in ("1", "true", "sim")
    if atual["situacao"] == "CONFIRMADA" and not forcar:
        raise ErroNegocio("Operação já confirmada pelo serviço externo. Use ?forcar=true para repetir "
                          "(a chave de idempotência impede duplicidade).", 409)
    return jsonify(integracao.processar(conn, id_, forcar=forcar))


@bp.post("/integracoes/reprocessar-pendentes")
@login_obrigatorio
def reprocessar():
    conn = get_db()
    feitos = integracao.reprocessar_pendentes(conn, somente_vencidas=False)
    return jsonify({"processadas": len(feitos),
                    "confirmadas": sum(1 for f in feitos if f and f["situacao"] == "CONFIRMADA"),
                    "ainda_pendentes": sum(1 for f in feitos if f and f["situacao"] == "PENDENTE"),
                    "falhas": sum(1 for f in feitos if f and f["situacao"] == "FALHA"),
                    "itens": feitos})
