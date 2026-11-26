"""
Execução automatizada dos 16 TESTES OBRIGATÓRIOS do enunciado (+ testes complementares).

Pré-requisito: API da clínica (5000) e API governamental (5001) em execução,
de preferência com RETRY_AUTO=0 para que a pendência fique visível durante o teste 14.

Uso:
    python tests/testes_obrigatorios.py [--clinica http://127.0.0.1:5000] [--gov http://127.0.0.1:5001]

Gera: docs/04_relatorio_testes.md e tests/resultado_testes.json
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import date, datetime, timedelta

import requests

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOV_KEY = "chave-clinica-sdm-123"

p = argparse.ArgumentParser()
p.add_argument("--clinica", default="http://127.0.0.1:5000")
p.add_argument("--gov", default="http://127.0.0.1:5001")
p.add_argument("--viacep-obs", default="")
args = p.parse_args()
API, GOV = args.clinica.rstrip("/"), args.gov.rstrip("/")

resultados = []
TOKEN = None


# ---------------------------------------------------------------------
def cpf_aleatorio():
    n = [random.randint(0, 9) for _ in range(9)]
    for _ in range(2):
        s = sum(d * w for d, w in zip(n, range(len(n) + 1, 1, -1)))
        r = (s * 10) % 11
        n.append(0 if r == 10 else r)
    return "".join(map(str, n))


def chip_aleatorio():
    return "076" + "".join(str(random.randint(0, 9)) for _ in range(12))


def req(metodo, url, token=True, **kw):
    h = kw.pop("headers", {})
    if token and TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    r = requests.request(metodo, url, headers=h, timeout=30, **kw)
    try:
        corpo = r.json()
    except ValueError:
        corpo = r.text
    return r, corpo


def gov(metodo, rota, **kw):
    h = kw.pop("headers", {})
    h["X-Api-Key"] = GOV_KEY
    r = requests.request(metodo, GOV + rota, headers=h, timeout=30, **kw)
    return r, (r.json() if r.content else None)


def simular_gov(modo):
    gov("PUT", "/api/governo/admin/simulacao", json={"modo": modo})


class Teste:
    def __init__(self, numero, titulo, esperado):
        self.numero, self.titulo, self.esperado = numero, titulo, esperado
        self.evidencias, self.ok = [], True

    def __enter__(self):
        self.inicio = time.time()
        return self

    def check(self, condicao, descricao):
        self.evidencias.append(("[OK]" if condicao else "[FALHA]") + " " + descricao)
        if not condicao:
            self.ok = False
        return condicao

    def __exit__(self, tipo, valor, tb):
        if tipo is not None:
            self.ok = False
            self.evidencias.append(f"[FALHA] Exceção: {tipo.__name__}: {valor}")
        resultados.append({"numero": self.numero, "titulo": self.titulo, "esperado": self.esperado,
                           "resultado": "APROVADO" if self.ok else "REPROVADO", "evidencias": self.evidencias,
                           "duracao_ms": int((time.time() - self.inicio) * 1000)})
        print(f"[{'OK ' if self.ok else 'FALHOU'}] {self.numero} - {self.titulo}")
        for e in self.evidencias:
            print("      ", e)
        return True  # continua os demais testes


hoje = date.today()
ctx = {}
simular_gov("NORMAL")

# =====================================================================
with Teste(1, "Login de veterinário ativo e com senha confirmada", "HTTP 200 com token Bearer") as t:
    r, c = req("POST", f"{API}/api/auth/login", token=False,
               json={"email": "ana@clinica.vet", "senha": "Senha@123"})
    t.check(r.status_code == 200, f"POST /api/auth/login (ana@clinica.vet) -> HTTP {r.status_code}")
    t.check(bool(c.get("token")), f"token recebido ({str(c.get('token'))[:18]}...), expira_em={c.get('expira_em')}")
    TOKEN = c.get("token")
    r, c = req("GET", f"{API}/api/auth/me")
    t.check(r.status_code == 200 and c.get("email") == "ana@clinica.vet", f"GET /api/auth/me -> {c.get('nome')}")

with Teste(2, "Bloqueio de veterinário inativo", "HTTP 403 - veterinário inativo") as t:
    r, c = req("POST", f"{API}/api/auth/login", token=False,
               json={"email": "bruno@clinica.vet", "senha": "Senha@123"})
    t.check(r.status_code == 403, f"login bruno@clinica.vet (INATIVO) -> HTTP {r.status_code}: {c.get('erro')}")

with Teste(3, "Bloqueio de veterinário com senha não confirmada", "HTTP 403 - senha não confirmada") as t:
    r, c = req("POST", f"{API}/api/auth/login", token=False,
               json={"email": "carla@clinica.vet", "senha": "Senha@123"})
    t.check(r.status_code == 403, f"login carla@clinica.vet (não confirmada) -> HTTP {r.status_code}: {c.get('erro')}")

with Teste(4, "Rejeição de senha incorreta", "HTTP 401 - e-mail ou senha incorretos") as t:
    r, c = req("POST", f"{API}/api/auth/login", token=False,
               json={"email": "ana@clinica.vet", "senha": "senhaErrada1"})
    t.check(r.status_code == 401, f"login com senha errada -> HTTP {r.status_code}: {c.get('erro')}")

with Teste(5, "Cadastro de tutor e validação de CPF duplicado", "201 no cadastro; 409 no CPF repetido; 422 CPF inválido") as t:
    cpf = cpf_aleatorio()
    tutor = {"nome": "João da Silva (fictício)", "cpf": cpf, "data_nascimento": "1985-08-20",
             "email": "joao.teste@exemplo.com", "telefone": "21987654321",
             "endereco": {"cep": "22775040", "logradouro": "Avenida Embaixador Abelardo Bueno", "numero": "500",
                          "complemento": "Bloco 1", "bairro": "Barra da Tijuca", "cidade": "Rio de Janeiro",
                          "uf": "RJ", "codigo_ibge": "3304557"}}
    r, c = req("POST", f"{API}/api/tutores", json=tutor)
    t.check(r.status_code == 201, f"POST /api/tutores (CPF {cpf}) -> HTTP {r.status_code}, id={c.get('id')}")
    ctx["tutor_id"] = c.get("id")
    r, c = req("POST", f"{API}/api/tutores", json=dict(tutor, nome="Outro Nome"))
    t.check(r.status_code == 409, f"POST /api/tutores com o mesmo CPF -> HTTP {r.status_code}: {c.get('erro')}")
    r, c = req("POST", f"{API}/api/tutores", json=dict(tutor, cpf="12345678900"))
    t.check(r.status_code == 422, f"POST /api/tutores com CPF inválido -> HTTP {r.status_code}: {c.get('detalhes')}")

with Teste(6, "Consulta de CEP válido e tratamento de CEP inexistente", "200 com endereço preenchido; 404 CEP inexistente") as t:
    r, c = req("GET", f"{API}/api/cep/22775040")
    t.check(r.status_code == 200 and c.get("cidade") == "Rio de Janeiro",
            f"GET /api/cep/22775040 -> HTTP {r.status_code}: {c.get('logradouro')}, {c.get('bairro')}, "
            f"{c.get('cidade')}/{c.get('uf')}, IBGE {c.get('codigo_ibge')}")
    r, c = req("GET", f"{API}/api/cep/00000000")
    t.check(r.status_code == 404, f"GET /api/cep/00000000 -> HTTP {r.status_code}: {c.get('erro')}")
    r, c = req("GET", f"{API}/api/cep/123")
    t.check(r.status_code == 400, f"GET /api/cep/123 (formato inválido) -> HTTP {r.status_code}: {c.get('erro')}")
    if args.viacep_obs:
        t.evidencias.append("Nota: " + args.viacep_obs)

with Teste(7, "Cadastro de animal e vínculo de microchip", "201; vínculo registra veterinário e data; animal sincronizado") as t:
    r, c = req("POST", f"{API}/api/animais", json={
        "nome": "Rex (teste)", "data_nascimento": "2022-01-15", "sexo": "M", "cor": "Preto",
        "peso_atual": 22.3, "tutor_id": ctx["tutor_id"], "especie_id": 1, "raca_id": 1})
    t.check(r.status_code == 201, f"POST /api/animais -> HTTP {r.status_code}, id={c.get('id')}")
    ctx["animal_id"] = c.get("id")
    ctx["chip"] = chip_aleatorio()
    r, c = req("POST", f"{API}/api/animais/{ctx['animal_id']}/microchip",
               json={"codigo_microchip": ctx["chip"], "data_implantacao": hoje.isoformat()})
    t.check(r.status_code == 201 and c.get("microchip_atual") == ctx["chip"],
            f"POST /api/animais/{ctx['animal_id']}/microchip ({ctx['chip']}) -> HTTP {r.status_code}")
    v = (c.get("microchips") or [{}])[0]
    t.check(v.get("veterinario_nome") == "Dra. Ana Souza" and v.get("data_vinculo"),
            f"vínculo por {v.get('veterinario_nome')} (CRMV {v.get('crmv')}-{v.get('crmv_uf')}) em {v.get('data_vinculo')}")
    t.check(c.get("gov_situacao") == "SINCRONIZADO",
            f"situação governamental do animal: {c.get('gov_situacao')} (protocolo {c.get('gov_protocolo')})")

with Teste(8, "Rejeição de microchip já utilizado", "HTTP 409") as t:
    r, c = req("POST", f"{API}/api/animais", json={
        "nome": "Bidu (teste)", "idade_estimada_meses": 30, "sexo": "M", "cor": "Branco",
        "peso_atual": 8, "tutor_id": ctx["tutor_id"], "especie_id": 1})
    ctx["animal2_id"] = c.get("id")
    r, c = req("POST", f"{API}/api/animais/{ctx['animal2_id']}/microchip",
               json={"codigo_microchip": ctx["chip"], "data_implantacao": hoje.isoformat()})
    t.check(r.status_code == 409, f"vincular {ctx['chip']} a outro animal -> HTTP {r.status_code}: {c.get('erro')}")

with Teste(9, "Registro de consulta e consulta ao histórico clínico", "201; consulta aparece no histórico do animal") as t:
    r, c = req("POST", f"{API}/api/consultas", json={
        "animal_id": ctx["animal_id"], "data_hora": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "motivo": "Check-up anual", "anamnese": "Tutor relata apetite normal.", "sintomas": "Nenhum",
        "diagnostico": "Animal saudável", "tratamento": "Manter alimentação", "peso_registrado": 23.1,
        "temperatura": 38.6, "situacao": "REALIZADA"})
    t.check(r.status_code == 201, f"POST /api/consultas -> HTTP {r.status_code}, id={c.get('id')}, "
            f"veterinário={c.get('veterinario_nome')}")
    cid = c.get("id")
    r, c = req("GET", f"{API}/api/animais/{ctx['animal_id']}/consultas")
    t.check(r.status_code == 200 and any(x["id"] == cid for x in c),
            f"GET /api/animais/{ctx['animal_id']}/consultas -> {len(c)} registro(s) no histórico")
    r, c = req("GET", f"{API}/api/animais/{ctx['animal_id']}")
    t.check(c.get("peso_atual") == 23.1, f"peso atual do animal atualizado para {c.get('peso_atual')} kg")

with Teste(10, "Registro de vacina e consulta às próximas doses", "201; próxima dose listada") as t:
    prox = (hoje + timedelta(days=21)).isoformat()
    r, c = req("POST", f"{API}/api/vacinas", json={
        "animal_id": ctx["animal_id"], "nome_vacina": "V10 Polivalente", "tipo_vacina": "POLIVALENTE_CANINA",
        "fabricante": "Laboratório Fictício", "lote": "V10-2026-01", "data_aplicacao": hoje.isoformat(),
        "dose": "1ª dose", "via_aplicacao": "SUBCUTANEA", "data_proxima_dose": prox,
        "data_validade_lote": "2027-12-31", "situacao": "APLICADA"})
    t.check(r.status_code == 201, f"POST /api/vacinas (V10) -> HTTP {r.status_code}, id={c.get('id')}")
    ctx["vacina_v10"] = c.get("id")
    r, c = req("GET", f"{API}/api/animais/{ctx['animal_id']}/vacinas")
    t.check(any(p["vacina_id"] == ctx["vacina_v10"] and p["data_proxima_dose"] == prox for p in c["proximas_doses"]),
            f"GET /api/animais/{ctx['animal_id']}/vacinas -> próximas doses: "
            f"{[(p['nome_vacina'], p['data_proxima_dose']) for p in c['proximas_doses']]}")
    r, c = req("GET", f"{API}/api/vacinas/proximas-doses?dias=30")
    t.check(any(p["vacina_id"] == ctx["vacina_v10"] for p in c),
            f"GET /api/vacinas/proximas-doses?dias=30 -> {len(c)} dose(s) prevista(s) na clínica")

with Teste(11, "Cadastro e atualização de animal na API governamental simulada", "Animal encontrado no serviço externo; atualização confirmada") as t:
    r, c = req("GET", f"{API}/api/animais/{ctx['animal_id']}/situacao-governo")
    t.check(c.get("consulta_externa") == "ENCONTRADO",
            f"cadastro: GET situacao-governo -> registro externo {c.get('consulta_externa')} "
            f"(nome={c.get('registro_externo', {}).get('nome')}, cor={c.get('registro_externo', {}).get('cor')})")
    r, c = req("PUT", f"{API}/api/animais/{ctx['animal_id']}", json={
        "nome": "Rex (teste)", "data_nascimento": "2022-01-15", "sexo": "M", "cor": "Preto e branco",
        "peso_atual": 23.1, "tutor_id": ctx["tutor_id"], "especie_id": 1, "raca_id": 1})
    integ = [i for i in c.get("integracoes", []) if i["tipo_operacao"] == "ATUALIZACAO_ANIMAL"]
    t.check(r.status_code == 200 and integ and integ[0]["situacao"] == "CONFIRMADA",
            f"PUT /api/animais/{ctx['animal_id']} -> integração ATUALIZACAO_ANIMAL "
            f"{integ[0]['situacao'] if integ else '-'} protocolo {integ[0]['protocolo_externo'] if integ else '-'}")
    r, c = gov("GET", f"/api/governo/animais/{ctx['chip']}")
    t.check(c.get("cor") == "Preto e branco", f"GET {GOV}/api/governo/animais/{ctx['chip']} -> cor='{c.get('cor')}'")

with Teste(12, "Envio obrigatório de vacina antirrábica", "Registro local + comunicação CONFIRMADA com protocolo, inclusive para animal ainda não cadastrado no serviço externo") as t:
    r, c = req("POST", f"{API}/api/vacinas", json={
        "animal_id": ctx["animal_id"], "nome_vacina": "Rabisin", "tipo_vacina": "ANTIRRABICA",
        "fabricante": "Laboratório Fictício", "lote": "RAB-2026-07", "data_aplicacao": hoje.isoformat(),
        "dose": "Reforço anual", "via_aplicacao": "SUBCUTANEA",
        "data_proxima_dose": (hoje + timedelta(days=365)).isoformat(), "data_validade_lote": "2027-06-30"})
    cg = c.get("comunicacao_governo", {})
    t.check(r.status_code == 201 and c.get("situacao") == "APLICADA",
            f"POST /api/vacinas (ANTIRRABICA) -> HTTP {r.status_code}, registro local {cg.get('registro_local')}")
    t.check(cg.get("situacao") == "CONFIRMADA" and cg.get("protocolo"),
            f"comunicação obrigatória: {cg.get('situacao')} - protocolo {cg.get('protocolo')}")
    ctx["vacina_rab_protocolo"] = cg.get("protocolo")
    r, c = gov("GET", f"/api/governo/vacinacoes-antirrabicas?microchip={ctx['chip']}")
    t.check(len(c) == 1, f"serviço externo possui {len(c)} vacinação(ões) antirrábica(s) para {ctx['chip']}")
    # animal NÃO cadastrado previamente no serviço externo
    simular_gov("INDISPONIVEL")
    r, c = req("POST", f"{API}/api/animais", json={
        "nome": "Luna (teste)", "data_nascimento": "2023-05-01", "sexo": "F", "cor": "Cinza",
        "peso_atual": 3.9, "tutor_id": ctx["tutor_id"], "especie_id": 2, "raca_id": 7,
        "microchip": chip_aleatorio(), "data_implantacao": hoje.isoformat()})
    ctx["animal3_id"], chip3 = c.get("id"), c.get("microchip_atual")
    t.check(c.get("gov_situacao") == "PENDENTE",
            f"animal Luna com microchip {chip3} criado com o serviço externo fora do ar -> cadastro externo {c.get('gov_situacao')}")
    simular_gov("NORMAL")
    r, c = req("POST", f"{API}/api/vacinas", json={
        "animal_id": ctx["animal3_id"], "nome_vacina": "Defensor", "tipo_vacina": "ANTIRRABICA",
        "fabricante": "Laboratório Fictício", "lote": "RAB-2026-08", "data_aplicacao": hoje.isoformat(),
        "dose": "1ª dose", "via_aplicacao": "INTRAMUSCULAR", "data_validade_lote": "2027-06-30"})
    cg = c.get("comunicacao_governo", {})
    integ = req("GET", f"{API}/api/integracoes/{cg.get('integracao_id')}")[1]
    t.check(cg.get("situacao") == "CONFIRMADA" and (integ.get("resposta") or {}).get("cadastro_implicito_animal"),
            f"antirrábica de animal não cadastrado no serviço externo -> {cg.get('situacao')} "
            f"(protocolo {cg.get('protocolo')}, cadastro_implicito_animal="
            f"{(integ.get('resposta') or {}).get('cadastro_implicito_animal')})")

with Teste(13, "Ausência de comunicação obrigatória para vacina não antirrábica", "Nenhuma integração gerada") as t:
    r, c = req("GET", f"{API}/api/vacinas/{ctx['vacina_v10']}")
    t.check(c["comunicacao_governo"]["obrigatoria"] is False and c.get("integracao_id") is None,
            f"vacina V10 (POLIVALENTE_CANINA): comunicação={c['comunicacao_governo']['situacao']}, integração={c.get('integracao_id')}")
    r, c = req("POST", f"{API}/api/vacinas", json={
        "animal_id": ctx["animal_id"], "nome_vacina": "Vacina contra raiva? (texto livre)", "tipo_vacina": "GRIPE_CANINA",
        "fabricante": "Laboratório Fictício", "lote": "GR-01", "data_aplicacao": hoje.isoformat(), "dose": "Dose única",
        "via_aplicacao": "INTRANASAL", "data_validade_lote": "2027-01-31"})
    t.check(c.get("antirrabica") is False and c.get("integracao_id") is None,
            "texto digitado contendo 'raiva' com tipo GRIPE_CANINA -> não classificada como antirrábica "
            "(classificação estruturada pelo tipo)")
    n_gov = len(gov("GET", f"/api/governo/vacinacoes-antirrabicas?microchip={ctx['chip']}")[1])
    t.check(n_gov == 1, f"serviço externo continua com {n_gov} vacinação(ões) para {ctx['chip']}")

with Teste(14, "Indisponibilidade da API governamental e registro de pendência", "Vacina registrada localmente; comunicação PENDENTE com erro e tentativa contabilizada") as t:
    simular_gov("INDISPONIVEL")
    r, c = req("POST", f"{API}/api/vacinas", json={
        "animal_id": ctx["animal_id"], "nome_vacina": "Rabisin", "tipo_vacina": "ANTIRRABICA",
        "fabricante": "Laboratório Fictício", "lote": "RAB-2026-09", "data_aplicacao": hoje.isoformat(),
        "dose": "Dose extra (pós-exposição)", "via_aplicacao": "SUBCUTANEA", "data_validade_lote": "2027-06-30"})
    cg = c["comunicacao_governo"]
    ctx["vacina_pend"], ctx["integ_pend"] = c["id"], cg["integracao_id"]
    t.check(r.status_code == 201 and c["situacao"] == "APLICADA",
            f"POST /api/vacinas com o serviço fora do ar -> HTTP {r.status_code}; vacina #{c['id']} registrada localmente ({c['situacao']})")
    t.check(cg["situacao"] == "PENDENTE" and cg["tentativas"] >= 1,
            f"comunicação {cg['situacao']}, tentativas={cg['tentativas']}, erro='{cg['mensagem']}'")
    r, c = req("GET", f"{API}/api/integracoes/{ctx['integ_pend']}")
    t.check(c.get("proxima_tentativa") is not None and c.get("chave_idempotencia") == f"VAC-ANTIRRABICA-{ctx['vacina_pend']}",
            f"integração #{ctx['integ_pend']}: próxima tentativa automática agendada para {c.get('proxima_tentativa')}, "
            f"chave {c.get('chave_idempotencia')}")
    r, c = req("GET", f"{API}/api/integracoes?situacao=PENDENTE")
    t.check(any(i["id"] == ctx["integ_pend"] for i in c), f"GET /api/integracoes?situacao=PENDENTE -> {len(c)} pendência(s)")
    r, c = gov("GET", f"/api/governo/vacinacoes-antirrabicas?microchip={ctx['chip']}")
    t.check(r.status_code == 503, f"serviço externo responde HTTP {r.status_code} (indisponível)")

with Teste(15, "Reenvio de comunicação pendente e confirmação posterior", "Após o retorno do serviço, reenvio confirma com protocolo") as t:
    simular_gov("NORMAL")
    r, c = req("POST", f"{API}/api/integracoes/{ctx['integ_pend']}/reenviar")
    t.check(r.status_code == 200 and c.get("situacao") == "CONFIRMADA",
            f"POST /api/integracoes/{ctx['integ_pend']}/reenviar -> {c.get('situacao')}, protocolo "
            f"{c.get('protocolo_externo')}, tentativas={c.get('tentativas')}")
    ctx["protocolo_pend"] = c.get("protocolo_externo")
    r, c = req("POST", f"{API}/api/integracoes/reprocessar-pendentes")
    t.check(r.status_code == 200, f"POST /api/integracoes/reprocessar-pendentes -> processadas={c.get('processadas')}, "
            f"confirmadas={c.get('confirmadas')}, pendentes={c.get('ainda_pendentes')}")
    r, c = req("GET", f"{API}/api/animais/{ctx['animal3_id']}")
    t.check(c.get("gov_situacao") == "SINCRONIZADO", f"cadastro pendente da Luna regularizado -> {c.get('gov_situacao')}")
    r, c = gov("GET", f"/api/governo/vacinacoes-antirrabicas?microchip={ctx['chip']}")
    ctx["qtd_gov"] = len(c)
    t.check(len(c) == 2, f"serviço externo agora tem {len(c)} vacinações antirrábicas para {ctx['chip']} "
            "(a de 12 + a regularizada)")

with Teste(16, "Repetição de solicitação sem duplicidade de vacinação no serviço externo", "Mesmo protocolo; contagem inalterada") as t:
    r, c = req("POST", f"{API}/api/integracoes/{ctx['integ_pend']}/reenviar?forcar=true")
    t.check(c.get("protocolo_externo") == ctx["protocolo_pend"],
            f"reenvio forçado pela clínica -> protocolo {c.get('protocolo_externo')} (igual ao original); "
            f"msg: {c.get('mensagem_erro')}")
    integ = req("GET", f"{API}/api/integracoes/{ctx['integ_pend']}")[1]
    payload, chave = integ["payload"], integ["chave_idempotencia"]
    r, c = gov("POST", "/api/governo/vacinacoes-antirrabicas", json=payload, headers={"Idempotency-Key": chave})
    t.check(r.headers.get("Idempotent-Replay") == "true" and c.get("protocolo") == ctx["protocolo_pend"],
            f"POST direto com a mesma Idempotency-Key ({chave}) -> HTTP {r.status_code}, "
            f"Idempotent-Replay={r.headers.get('Idempotent-Replay')}")
    r, c = gov("POST", "/api/governo/vacinacoes-antirrabicas", json=payload,
               headers={"Idempotency-Key": "OUTRA-CHAVE-" + str(random.randint(1, 10**9))})
    t.check(c.get("duplicidade_evitada") is True,
            f"mesma aplicação com OUTRA chave -> HTTP {r.status_code}, duplicidade_evitada={c.get('duplicidade_evitada')}")
    r, c = gov("GET", f"/api/governo/vacinacoes-antirrabicas?microchip={ctx['chip']}")
    t.check(len(c) == ctx["qtd_gov"], f"contagem no serviço externo após 3 repetições: {len(c)} (antes: {ctx['qtd_gov']})")

# =====================================================================
# Testes complementares
# =====================================================================
with Teste("C1", "Proteção de endpoints sem autenticação", "HTTP 401") as t:
    r, c = req("GET", f"{API}/api/tutores", token=False)
    t.check(r.status_code == 401, f"GET /api/tutores sem token -> HTTP {r.status_code}")

with Teste("C2", "Raça incompatível com a espécie", "HTTP 422") as t:
    r, c = req("POST", f"{API}/api/animais", json={
        "nome": "Teste", "idade_estimada_meses": 5, "sexo": "F", "cor": "Preta", "peso_atual": 2,
        "tutor_id": ctx["tutor_id"], "especie_id": 2, "raca_id": 1})
    t.check(r.status_code == 422, f"gato com raça Labrador -> HTTP {r.status_code}: {c.get('erro')}")

with Teste("C3", "Substituição de microchip preservando histórico", "Novo chip ativo, anterior inativo com motivo") as t:
    novo = chip_aleatorio()
    r, c = req("POST", f"{API}/api/animais/{ctx['animal_id']}/microchip",
               json={"codigo_microchip": novo, "data_implantacao": hoje.isoformat()})
    t.check(r.status_code == 422, f"substituir sem motivo -> HTTP {r.status_code}")
    r, c = req("POST", f"{API}/api/animais/{ctx['animal_id']}/microchip",
               json={"codigo_microchip": novo, "data_implantacao": hoje.isoformat(),
                     "motivo_substituicao": "Falha de leitura do chip anterior"})
    hist = c.get("microchips", [])
    t.check(len(hist) == 2 and hist[0]["ativo"] == 1 and hist[1]["ativo"] == 0 and hist[1]["motivo_substituicao"],
            f"histórico: {[(h['codigo_microchip'], 'ativo' if h['ativo'] else 'inativo') for h in hist]}")
    r2, g2 = gov("GET", f"/api/governo/animais/{ctx['chip']}")
    t.check(g2.get("situacao") == "SUBSTITUIDO", f"serviço externo marcou o chip antigo como {g2.get('situacao')}")

with Teste("C4", "Cadastro de veterinário com confirmação de senha por código", "403 antes; 200 após confirmar") as t:
    email = f"vet{random.randint(1000, 9999)}@clinica.vet"
    r, c = req("POST", f"{API}/api/auth/registro", token=False, json={
        "nome": "Dr. Teste", "cpf": cpf_aleatorio(), "crmv": str(random.randint(10000, 99999)), "crmv_uf": "RJ",
        "email": email, "telefone": "21912345678", "senha": "Teste1234", "confirmacao_senha": "Teste1234"})
    t.check(r.status_code == 201, f"POST /api/auth/registro -> HTTP {r.status_code} (código simulado {c.get('codigo_simulado')})")
    codigo = c.get("codigo_simulado")
    r, _ = req("POST", f"{API}/api/auth/login", token=False, json={"email": email, "senha": "Teste1234"})
    t.check(r.status_code == 403, f"login antes de confirmar -> HTTP {r.status_code}")
    r, _ = req("POST", f"{API}/api/auth/confirmar-senha", token=False, json={"email": email, "codigo": "000000"})
    t.check(r.status_code == 400, f"código errado -> HTTP {r.status_code}")
    r, _ = req("POST", f"{API}/api/auth/confirmar-senha", token=False, json={"email": email, "codigo": codigo})
    t.check(r.status_code == 200, f"código correto -> HTTP {r.status_code}")
    r, _ = req("POST", f"{API}/api/auth/login", token=False, json={"email": email, "senha": "Teste1234"})
    t.check(r.status_code == 200, f"login após confirmar -> HTTP {r.status_code}")

with Teste("C5", "Logout encerra a sessão", "token deixa de valer (401)") as t:
    r, c = req("POST", f"{API}/api/auth/login", token=False, json={"email": "ana@clinica.vet", "senha": "Senha@123"})
    tk = c["token"]
    r, _ = req("POST", f"{API}/api/auth/logout", token=False, headers={"Authorization": f"Bearer {tk}"})
    t.check(r.status_code == 200, f"POST /api/auth/logout -> HTTP {r.status_code}")
    r, _ = req("GET", f"{API}/api/auth/me", token=False, headers={"Authorization": f"Bearer {tk}"})
    t.check(r.status_code == 401, f"GET /api/auth/me com token encerrado -> HTTP {r.status_code}")

with Teste("C6", "Antirrábica em animal sem microchip: registro local mantido e envio após o vínculo", "FALHA aguardando microchip -> CONFIRMADA após vincular") as t:
    r, c = req("POST", f"{API}/api/vacinas", json={
        "animal_id": ctx["animal2_id"], "nome_vacina": "Rabisin", "tipo_vacina": "ANTIRRABICA",
        "fabricante": "Laboratório Fictício", "lote": "RAB-2026-10", "data_aplicacao": hoje.isoformat(),
        "dose": "1ª dose", "via_aplicacao": "SUBCUTANEA", "data_validade_lote": "2027-06-30"})
    cg = c["comunicacao_governo"]
    t.check(c["situacao"] == "APLICADA" and cg["situacao"] == "FALHA",
            f"vacina registrada ({c['situacao']}); comunicação {cg['situacao']}: {cg['mensagem']}")
    r, c = req("POST", f"{API}/api/animais/{ctx['animal2_id']}/microchip",
               json={"codigo_microchip": chip_aleatorio(), "data_implantacao": hoje.isoformat()})
    r, c = req("GET", f"{API}/api/integracoes/{cg['integracao_id']}")
    t.check(c.get("situacao") == "CONFIRMADA", f"após vincular o microchip a comunicação foi reenviada -> {c.get('situacao')} "
            f"(protocolo {c.get('protocolo_externo')})")

with Teste("C7", "Timeout com processamento tardio no serviço externo: reenvio reconhecido sem duplicar", "PENDENTE por timeout -> reenvio CONFIRMADA (replay idempotente); 1 único registro externo") as t:
    gov("PUT", "/api/governo/admin/simulacao", json={"modo": "LENTO", "atraso_segundos": 7})
    r, c = req("POST", f"{API}/api/vacinas", json={
        "animal_id": ctx["animal3_id"], "nome_vacina": "Rabisin", "tipo_vacina": "ANTIRRABICA",
        "fabricante": "Laboratório Fictício", "lote": "RAB-2026-11", "data_aplicacao": hoje.isoformat(),
        "dose": "Reforço", "via_aplicacao": "SUBCUTANEA", "data_validade_lote": "2027-06-30"})
    cg = c["comunicacao_governo"]
    t.check(cg["situacao"] == "PENDENTE", f"clínica desistiu após o timeout de leitura: {cg['situacao']} — {cg['mensagem']}")
    time.sleep(4)  # o serviço externo termina de processar a requisição "perdida"
    simular_gov("NORMAL")
    chip_luna = req("GET", f"{API}/api/animais/{ctx['animal3_id']}")[1]["microchip_atual"]
    antes = len(gov("GET", f"/api/governo/vacinacoes-antirrabicas?microchip={chip_luna}")[1])
    r, c = req("POST", f"{API}/api/integracoes/{cg['integracao_id']}/reenviar")
    t.check(c.get("situacao") == "CONFIRMADA" and "idempotente" in (c.get("mensagem_erro") or ""),
            f"reenvio -> {c.get('situacao')}: {c.get('mensagem_erro')}")
    depois = len(gov("GET", f"/api/governo/vacinacoes-antirrabicas?microchip={chip_luna}")[1])
    t.check(depois == antes, f"registros externos antes/depois do reenvio: {antes}/{depois} (sem duplicidade)")

simular_gov("NORMAL")

# =====================================================================
# Relatório
# =====================================================================
obrig = [r for r in resultados if isinstance(r["numero"], int)]
compl = [r for r in resultados if not isinstance(r["numero"], int)]
aprov = sum(r["resultado"] == "APROVADO" for r in resultados)
with open(os.path.join(RAIZ, "tests", "resultado_testes.json"), "w", encoding="utf-8") as f:
    json.dump(resultados, f, ensure_ascii=False, indent=2)

linhas = [
    "# Relatório de Testes — SDM Clínica Veterinária", "",
    f"**Execução:** {datetime.now():%d/%m/%Y %H:%M:%S}  ",
    f"**Ambiente:** API da clínica `{API}` · API governamental simulada `{GOV}`  ",
    "**Ferramenta:** script automatizado `tests/testes_obrigatorios.py` (Python + requests). "
    "A mesma sequência está na coleção Postman `tests/SDM_Clinica.postman_collection.json`.  ",
    f"**Resultado geral:** {aprov} de {len(resultados)} testes aprovados "
    f"({sum(r['resultado']=='APROVADO' for r in obrig)}/{len(obrig)} obrigatórios, "
    f"{sum(r['resultado']=='APROVADO' for r in compl)}/{len(compl)} complementares).", "",
    "## Resumo", "", "| # | Teste | Esperado | Resultado |", "|---|---|---|---|",
]
for r in resultados:
    linhas.append(f"| {r['numero']} | {r['titulo']} | {r['esperado']} | "
                  f"{'APROVADO' if r['resultado']=='APROVADO' else 'REPROVADO'} |")
linhas += ["", "## Evidências detalhadas", ""]
for r in resultados:
    linhas += [f"### {r['numero']}. {r['titulo']}", "", f"*Esperado:* {r['esperado']}  ",
               f"*Resultado:* **{r['resultado']}** ({r['duracao_ms']} ms)", ""]
    linhas += [f"- {e}" for e in r["evidencias"]] + [""]
with open(os.path.join(RAIZ, "docs", "04_relatorio_testes.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(linhas))

print(f"\n{aprov}/{len(resultados)} aprovados. Relatório: docs/04_relatorio_testes.md")
sys.exit(0 if aprov == len(resultados) else 1)
