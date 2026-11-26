"""Serviço de integração com a API governamental simulada.

Fluxo (padrão "outbox" + idempotência):
  1. A operação de negócio (ex.: vacina antirrábica aplicada) é gravada LOCALMENTE e confirmada.
  2. Na mesma transação é criada uma linha em integracao_governo (situação PENDENTE) com uma
     chave de idempotência determinística (ex.: VAC-<id da vacina>).
  3. Após o commit, a clínica tenta enviar. A linha é "reivindicada" atomicamente (PENDENTE->ENVIADA)
     para que o worker e um reenvio manual nunca enviem a mesma operação ao mesmo tempo.
  4. Resultado:  sucesso -> CONFIRMADA (guarda protocolo)
                 indisponível/timeout/5xx -> PENDENTE (novo agendamento com backoff exponencial)
                 rejeição 4xx -> FALHA (exige correção; reenvio manual)
  5. Reenvios reutilizam a MESMA chave; a API externa devolve a resposta original sem duplicar.
"""
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta

import config
from clients import gov_client
from core.validacao import ErroNegocio, agora
from database import conexao_avulsa, row, rows, transacao

log = logging.getLogger("integracao")

TIPOS_ANIMAL = ("CADASTRO_ANIMAL", "ATUALIZACAO_ANIMAL")
ENVIADA_TRAVADA_SEG = 60  # ENVIADA há mais que isso = processo caiu durante o envio -> pode reenviar


# ---------------------------------------------------------------------
# Montagem dos payloads
# ---------------------------------------------------------------------
def _dados_animal(conn, animal_id):
    a = conn.execute(
        """SELECT a.*, e.nome AS especie_nome, r.nome AS raca_nome,
                  t.nome AS tutor_nome, t.cpf AS tutor_cpf, en.codigo_ibge
           FROM animal a
           JOIN especie e ON e.id = a.especie_id
           LEFT JOIN raca r ON r.id = a.raca_id
           JOIN tutor t ON t.id = a.tutor_id
           JOIN endereco en ON en.id = t.endereco_id
           WHERE a.id = ?""",
        (animal_id,),
    ).fetchone()
    if not a:
        raise ErroNegocio("Animal não encontrado.", 404)
    return a


def payload_animal(conn, animal_id):
    a = _dados_animal(conn, animal_id)
    if not a["microchip_atual"]:
        raise ErroNegocio("Animal sem microchip vinculado: não é possível comunicar ao serviço externo.", 422)
    vinc = conn.execute(
        """SELECT vm.*, v.nome AS vet_nome, v.crmv, v.crmv_uf FROM vinculo_microchip vm
           JOIN veterinario v ON v.id = vm.veterinario_id
           WHERE vm.animal_id = ? AND vm.ativo = 1""",
        (animal_id,),
    ).fetchone()
    anterior = conn.execute(
        """SELECT codigo_microchip FROM vinculo_microchip
           WHERE animal_id = ? AND ativo = 0 AND substituido_por_id = ?""",
        (animal_id, vinc["id"]),
    ).fetchone()
    p = {
        "microchip": a["microchip_atual"],
        "nome": a["nome"],
        "especie": a["especie_nome"],
        "raca": a["raca_nome"] or "Sem raça definida",
        "sexo": a["sexo"],
        "data_nascimento": a["data_nascimento"],
        "cor": a["cor"],
        "tutor": {"nome": a["tutor_nome"], "cpf": a["tutor_cpf"], "municipio_ibge": a["codigo_ibge"]},
        "veterinario": {"nome": vinc["vet_nome"], "crmv": vinc["crmv"], "crmv_uf": vinc["crmv_uf"]},
        "data_implantacao_microchip": vinc["data_implantacao"],
        "origem_sistema": config.ORIGEM_SISTEMA,
        "id_animal_origem": str(animal_id),
    }
    if anterior:
        p["microchip_anterior"] = anterior["codigo_microchip"]
    return p


def payload_vacina(conn, vacina_id):
    v = conn.execute(
        """SELECT va.*, ve.nome AS vet_nome, ve.crmv, ve.crmv_uf FROM vacina va
           JOIN veterinario ve ON ve.id = va.veterinario_id WHERE va.id = ?""",
        (vacina_id,),
    ).fetchone()
    animal = payload_animal(conn, v["animal_id"])  # inclui dados para cadastro implícito
    microchip = animal.pop("microchip")
    return {
        "microchip": microchip,
        "origem_sistema": config.ORIGEM_SISTEMA,
        "id_aplicacao_origem": str(v["id"]),
        "id_animal_origem": str(v["animal_id"]),
        "data_aplicacao": v["data_aplicacao"],
        "vacina": {"nome": v["nome_vacina"], "tipo": v["tipo_vacina"], "fabricante": v["fabricante"],
                   "lote": v["lote"], "dose": v["dose"]},
        "veterinario": {"nome": v["vet_nome"], "crmv": v["crmv"], "crmv_uf": v["crmv_uf"]},
        "animal": animal,
    }


def montar_payload(conn, integ):
    if integ["tipo_operacao"] == "VACINACAO_ANTIRRABICA":
        return payload_vacina(conn, integ["vacina_id"])
    return payload_animal(conn, integ["animal_id"])


# ---------------------------------------------------------------------
# Criação das solicitações (chamadas DENTRO da transação do negócio)
# ---------------------------------------------------------------------
def solicitar(conn, animal_id, tipo, chave, vacina_id=None):
    """Cria a solicitação de integração (idempotente pela chave). Retorna o id."""
    existente = conn.execute("SELECT id FROM integracao_governo WHERE chave_idempotencia = ?",
                             (chave,)).fetchone()
    if existente:
        return existente["id"]
    try:
        payload = json.dumps(montar_payload(conn, {"tipo_operacao": tipo, "animal_id": animal_id,
                                                   "vacina_id": vacina_id}), ensure_ascii=False)
    except ErroNegocio:
        payload = "{}"  # será montado no envio (ex.: microchip ainda não vinculado)
    cur = conn.execute(
        """INSERT INTO integracao_governo (animal_id, vacina_id, tipo_operacao, chave_idempotencia,
               situacao, payload, proxima_tentativa)
           VALUES (?,?,?,?, 'PENDENTE', ?, ?)""",
        (animal_id, vacina_id, tipo, chave, payload, agora()),
    )
    if tipo in TIPOS_ANIMAL:
        conn.execute("UPDATE animal SET gov_situacao = 'PENDENTE' WHERE id = ? AND gov_situacao <> 'SINCRONIZADO'",
                     (animal_id,))
    return cur.lastrowid


def solicitar_vacina_antirrabica(conn, vacina_id, animal_id):
    return solicitar(conn, animal_id, "VACINACAO_ANTIRRABICA", f"VAC-ANTIRRABICA-{vacina_id}", vacina_id)


def solicitar_cadastro(conn, animal_id, microchip):
    return solicitar(conn, animal_id, "CADASTRO_ANIMAL", f"CAD-ANIMAL-{animal_id}-{microchip}")


def solicitar_atualizacao(conn, animal_id):
    return solicitar(conn, animal_id, "ATUALIZACAO_ANIMAL", f"ATU-ANIMAL-{animal_id}-{uuid.uuid4().hex[:12]}")


def cadastro_confirmado(conn, animal_id):
    """O microchip atual do animal já está registrado no serviço externo?"""
    a = conn.execute("SELECT gov_situacao FROM animal WHERE id = ?", (animal_id,)).fetchone()
    return a is not None and a["gov_situacao"] == "SINCRONIZADO"


# ---------------------------------------------------------------------
# Envio
# ---------------------------------------------------------------------
def _backoff(tentativas):
    seg = min(config.RETRY_INTERVALO_SEG * (2 ** max(tentativas - 1, 0)), 600)
    return (datetime.now() + timedelta(seconds=seg)).strftime("%Y-%m-%d %H:%M:%S")


def _reivindicar(conn, integ_id, forcar=False):
    """Transição atômica para ENVIADA. Garante que só um processo envia por vez."""
    limite = (datetime.now() - timedelta(seconds=ENVIADA_TRAVADA_SEG)).strftime("%Y-%m-%d %H:%M:%S")
    situacoes = "('PENDENTE','FALHA','CONFIRMADA')" if forcar else "('PENDENTE','FALHA')"
    cur = conn.execute(
        f"""UPDATE integracao_governo
            SET situacao = 'ENVIADA', tentativas = tentativas + 1, data_ultimo_envio = ?
            WHERE id = ? AND (situacao IN {situacoes} OR (situacao = 'ENVIADA' AND data_ultimo_envio < ?))""",
        (agora(), integ_id, limite),
    )
    return cur.rowcount == 1


def processar(conn, integ_id, forcar=False):
    """Envia uma solicitação e registra o resultado. Retorna a linha atualizada."""
    anterior = row(conn.execute("SELECT * FROM integracao_governo WHERE id = ?", (integ_id,)).fetchone())
    if not anterior:
        raise ErroNegocio("Integração não encontrada.", 404)
    if not _reivindicar(conn, integ_id, forcar):
        return obter(conn, integ_id)  # outro processo já está enviando / já confirmada
    integ = row(conn.execute("SELECT * FROM integracao_governo WHERE id = ?", (integ_id,)).fetchone())

    try:
        payload = montar_payload(conn, integ)
    except ErroNegocio as e:
        conn.execute(
            """UPDATE integracao_governo SET situacao='FALHA', mensagem_erro=?, data_resposta=?,
                   proxima_tentativa=NULL WHERE id=?""",
            (e.mensagem, agora(), integ_id),
        )
        _atualizar_situacao_animal(conn, integ, "FALHA")
        return obter(conn, integ_id)

    conn.execute("UPDATE integracao_governo SET payload = ? WHERE id = ?",
                 (json.dumps(payload, ensure_ascii=False), integ_id))
    res = gov_client.enviar(integ["tipo_operacao"], payload, integ["chave_idempotencia"])
    resposta = json.dumps(res.corpo, ensure_ascii=False) if res.corpo is not None else None

    if res.categoria == "SUCESSO":
        protocolo = (res.corpo or {}).get("protocolo")
        msg = "Reenvio reconhecido pelo serviço externo (idempotente, sem duplicidade)." if res.replay else None
        if (res.corpo or {}).get("duplicidade_evitada"):
            msg = res.corpo.get("mensagem")
        if forcar and anterior["situacao"] == "CONFIRMADA" and anterior["protocolo_externo"] == protocolo:
            msg = "Solicitação repetida: o serviço externo devolveu o MESMO protocolo, sem novo registro."
        conn.execute(
            """UPDATE integracao_governo SET situacao='CONFIRMADA', protocolo_externo=?, http_status=?,
                   data_resposta=?, mensagem_erro=?, resposta=?, proxima_tentativa=NULL WHERE id=?""",
            (protocolo, res.http_status, agora(), msg, resposta, integ_id),
        )
        if integ["tipo_operacao"] in TIPOS_ANIMAL or (res.corpo or {}).get("cadastro_implicito_animal"):
            conn.execute(
                "UPDATE animal SET gov_situacao='SINCRONIZADO', gov_protocolo=?, gov_ultima_sync=? WHERE id=?",
                (protocolo, agora(), integ["animal_id"]),
            )
    elif res.categoria == "INDISPONIVEL":
        esgotou = integ["tentativas"] >= config.RETRY_MAX_TENTATIVAS
        conn.execute(
            """UPDATE integracao_governo SET situacao=?, http_status=?, data_resposta=?, mensagem_erro=?,
                   resposta=?, proxima_tentativa=? WHERE id=?""",
            ("FALHA" if esgotou else "PENDENTE", res.http_status, agora(),
             res.mensagem + (" Limite de tentativas automáticas atingido." if esgotou else ""),
             resposta, None if esgotou else _backoff(integ["tentativas"]), integ_id),
        )
        _atualizar_situacao_animal(conn, integ, "FALHA" if esgotou else "PENDENTE")
    else:  # REJEITADA
        conn.execute(
            """UPDATE integracao_governo SET situacao='FALHA', http_status=?, data_resposta=?, mensagem_erro=?,
                   resposta=?, proxima_tentativa=NULL WHERE id=?""",
            (res.http_status, agora(), res.mensagem, resposta, integ_id),
        )
        _atualizar_situacao_animal(conn, integ, "FALHA")
    return obter(conn, integ_id)


def _atualizar_situacao_animal(conn, integ, situacao):
    if integ["tipo_operacao"] in TIPOS_ANIMAL:
        conn.execute("UPDATE animal SET gov_situacao=? WHERE id=? AND gov_situacao <> 'SINCRONIZADO'",
                     (situacao, integ["animal_id"]))


def processar_varias(conn, ids):
    resultados = []
    for i in ids:
        try:
            resultados.append(processar(conn, i))
        except Exception as e:  # nunca derruba a operação de negócio já gravada
            log.exception("Falha ao processar integração %s: %s", i, e)
    return resultados


def reprocessar_pendentes(conn, somente_vencidas=True, animal_id=None):
    limite = (datetime.now() - timedelta(seconds=ENVIADA_TRAVADA_SEG)).strftime("%Y-%m-%d %H:%M:%S")
    sql = """SELECT id FROM integracao_governo
             WHERE (situacao = 'PENDENTE' OR (situacao = 'ENVIADA' AND data_ultimo_envio < ?))"""
    params = [limite]
    if somente_vencidas:
        sql += " AND (proxima_tentativa IS NULL OR proxima_tentativa <= ?)"
        params.append(agora())
    if animal_id:
        sql += " AND animal_id = ?"
        params.append(animal_id)
    ids = [r["id"] for r in conn.execute(sql + " ORDER BY id", params)]
    return processar_varias(conn, ids)


def obter(conn, integ_id):
    r = row(conn.execute(
        """SELECT i.*, a.nome AS animal_nome, a.microchip_atual FROM integracao_governo i
           JOIN animal a ON a.id = i.animal_id WHERE i.id = ?""", (integ_id,)).fetchone())
    if r:
        for campo in ("payload", "resposta"):
            try:
                r[campo] = json.loads(r[campo]) if r[campo] else None
            except ValueError:
                pass
    return r


def listar(conn, situacao=None, animal_id=None, tipo=None, limite=200):
    sql = """SELECT i.id, i.animal_id, a.nome AS animal_nome, a.microchip_atual, i.vacina_id, i.tipo_operacao,
                    i.protocolo_externo, i.chave_idempotencia, i.situacao, i.data_solicitacao,
                    i.data_ultimo_envio, i.data_resposta, i.proxima_tentativa, i.tentativas,
                    i.http_status, i.mensagem_erro
             FROM integracao_governo i JOIN animal a ON a.id = i.animal_id WHERE 1=1"""
    params = []
    if situacao:
        sql += " AND i.situacao = ?"
        params.append(situacao.upper())
    if animal_id:
        sql += " AND i.animal_id = ?"
        params.append(animal_id)
    if tipo:
        sql += " AND i.tipo_operacao = ?"
        params.append(tipo.upper())
    sql += " ORDER BY i.id DESC LIMIT ?"
    params.append(limite)
    return rows(conn.execute(sql, params))


# ---------------------------------------------------------------------
# Worker de reenvio automático
# ---------------------------------------------------------------------
class WorkerReenvio(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="worker-reenvio-governo")

    def run(self):
        log.info("Worker de reenvio iniciado (intervalo %ss).", config.RETRY_INTERVALO_SEG)
        while True:
            time.sleep(config.RETRY_INTERVALO_SEG)
            try:
                with conexao_avulsa() as conn:
                    feitos = reprocessar_pendentes(conn)
                    if feitos:
                        log.info("Worker reprocessou %d integração(ões).", len(feitos))
            except Exception as e:
                log.exception("Erro no worker de reenvio: %s", e)


__all__ = ["solicitar_vacina_antirrabica", "solicitar_cadastro", "solicitar_atualizacao", "processar",
           "processar_varias", "reprocessar_pendentes", "obter", "listar", "WorkerReenvio", "transacao",
           "cadastro_confirmado"]
