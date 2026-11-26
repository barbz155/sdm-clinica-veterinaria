/* =====================================================================
   SDM · Clínica Veterinária — Frontend (SPA em JavaScript puro)
   Comunica-se com a API privada exclusivamente via REST (fetch + JSON).
   ===================================================================== */
"use strict";

// ---------------------------------------------------------------------
// Utilitários
// ---------------------------------------------------------------------
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dig = (v) => String(v ?? "").replace(/\D/g, "");
const hojeISO = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const agoraLocal = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);

function fmtData(v) {
  if (!v) return "—";
  const [d, h] = String(v).split(/[ T]/);
  const [a, m, di] = d.split("-");
  return `${di}/${m}/${a}${h ? " " + h.slice(0, 5) : ""}`;
}
const fmtCPF = (c) => { c = dig(c); return c.length === 11 ? `${c.slice(0, 3)}.${c.slice(3, 6)}.${c.slice(6, 9)}-${c.slice(9)}` : c; };
const fmtCEP = (c) => { c = dig(c); return c.length === 8 ? `${c.slice(0, 5)}-${c.slice(5)}` : c; };
const fmtTel = (t) => { t = dig(t); return t.length === 11 ? `(${t.slice(0, 2)}) ${t.slice(2, 7)}-${t.slice(7)}` : t.length === 10 ? `(${t.slice(0, 2)}) ${t.slice(2, 6)}-${t.slice(6)}` : t; };
function idade(a) {
  if (a.data_nascimento) {
    const n = new Date(a.data_nascimento), h = new Date();
    let m = (h.getFullYear() - n.getFullYear()) * 12 + h.getMonth() - n.getMonth();
    return m >= 24 ? `${Math.floor(m / 12)} anos` : `${Math.max(m, 0)} meses`;
  }
  if (a.idade_estimada_meses != null) return `~${a.idade_estimada_meses >= 24 ? Math.floor(a.idade_estimada_meses / 12) + " anos" : a.idade_estimada_meses + " meses"} (estimada)`;
  return "—";
}

const TAGS = {
  ATIVO: "ok", INATIVO: "neutral", OBITO: "neutral",
  AGENDADA: "info", REALIZADA: "ok", CANCELADA: "neutral", NAO_COMPARECEU: "warn", APLICADA: "ok",
  PENDENTE: "warn", ENVIADA: "info", CONFIRMADA: "ok", FALHA: "err",
  SINCRONIZADO: "ok", NAO_ENVIADO: "neutral", NAO_SE_APLICA: "neutral", NAO_GERADA: "neutral",
};
const ROTULOS = {
  NAO_COMPARECEU: "NÃO COMPARECEU", NAO_ENVIADO: "NÃO ENVIADO", NAO_SE_APLICA: "NÃO SE APLICA", OBITO: "ÓBITO",
  CADASTRO_ANIMAL: "Cadastro do animal", ATUALIZACAO_ANIMAL: "Atualização do animal", VACINACAO_ANTIRRABICA: "Vacinação antirrábica",
};
const tag = (s) => s ? `<span class="tag ${TAGS[s] || "neutral"}">${esc(ROTULOS[s] || s.replace(/_/g, " "))}</span>` : "—";

function toast(msg, tipo = "") {
  const t = document.createElement("div");
  t.className = `toast ${tipo}`;
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 4500);
}

function erroHTML(e) {
  if (!e) return "";
  const det = e.detalhes && e.detalhes.length ? `<ul>${e.detalhes.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>` : "";
  return `<div class="alert err"><b>${esc(e.message || e.erro || "Erro")}</b>${det}</div>`;
}

// ---------------------------------------------------------------------
// Cliente da API REST
// ---------------------------------------------------------------------
const Sessao = {
  get token() { return localStorage.getItem("sdm_token"); },
  get vet() { try { return JSON.parse(localStorage.getItem("sdm_vet")); } catch { return null; } },
  salvar(t, v) { localStorage.setItem("sdm_token", t); localStorage.setItem("sdm_vet", JSON.stringify(v)); },
  limpar() { localStorage.removeItem("sdm_token"); localStorage.removeItem("sdm_vet"); },
};

class ApiErro extends Error {
  constructor(status, corpo) {
    super((corpo && corpo.erro) || `Erro HTTP ${status}`);
    this.status = status;
    this.detalhes = (corpo && corpo.detalhes) || [];
  }
}

async function api(metodo, rota, corpo, { timeout = 20000 } = {}) {
  const ctrl = new AbortController();
  const tm = setTimeout(() => ctrl.abort(), timeout);
  const headers = { "Content-Type": "application/json" };
  if (Sessao.token) headers.Authorization = `Bearer ${Sessao.token}`;
  let r;
  try {
    r = await fetch(rota, { method: metodo, headers, body: corpo ? JSON.stringify(corpo) : undefined, signal: ctrl.signal });
  } catch (e) {
    throw new ApiErro(0, { erro: e.name === "AbortError" ? "Tempo de resposta esgotado. Tente novamente." : "Não foi possível conectar ao servidor da clínica." });
  } finally { clearTimeout(tm); }
  let dados = null;
  try { dados = await r.json(); } catch { /* sem corpo */ }
  if (r.status === 401 && !rota.startsWith("/api/auth/login")) {
    Sessao.limpar();
    toast("Sua sessão terminou. Faça login novamente.", "warn");
    mostrarAuth("login");
    throw new ApiErro(401, dados);
  }
  if (!r.ok) throw new ApiErro(r.status, dados);
  return dados;
}
const GET = (r) => api("GET", r), POST = (r, b) => api("POST", r, b || {}), PUT = (r, b) => api("PUT", r, b), DEL = (r) => api("DELETE", r), PATCH = (r, b) => api("PATCH", r, b);

function dadosForm(form) {
  const d = {};
  new FormData(form).forEach((v, k) => {
    v = typeof v === "string" ? v.trim() : v;
    if (k.includes(".")) { const [a, b] = k.split("."); d[a] = d[a] || {}; d[a][b] = v; } else d[k] = v;
  });
  return d;
}
const limparVazios = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== "" && v != null));

// ---------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------
function abrirModal(titulo, html, { largura } = {}) {
  const root = $("#modal-root");
  root.innerHTML = `<div class="modal-bg"><div class="modal" ${largura ? `style="max-width:${largura}px"` : ""}>
    <header><h2>${esc(titulo)}</h2><button class="x" aria-label="Fechar">×</button></header>
    <div class="body">${html}</div></div></div>`;
  const fechar = () => (root.innerHTML = "");
  $(".x", root).onclick = fechar;
  $(".modal-bg", root).addEventListener("mousedown", (e) => { if (e.target.classList.contains("modal-bg")) fechar(); });
  return { el: $(".modal", root), fechar };
}
const fecharModal = () => ($("#modal-root").innerHTML = "");

/** Liga um <form> a uma função assíncrona, exibindo erros de validação da API. */
function ligarForm(form, acao) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("button[type=submit]", form), box = $(".form-erro", form);
    if (btn) btn.disabled = true;
    if (box) box.innerHTML = "";
    try { await acao(dadosForm(form)); }
    catch (err) { if (box) { box.innerHTML = erroHTML(err); box.scrollIntoView({ block: "nearest" }); } else toast(err.message, "err"); }
    finally { if (btn) btn.disabled = false; }
  });
}

// ---------------------------------------------------------------------
// Autenticação
// ---------------------------------------------------------------------
function mostrarAuth(tela = "login", email = "") {
  $("#app").classList.add("hidden");
  $("#auth").classList.remove("hidden");
  const card = $("#auth-card");
  if (tela === "login") {
    card.innerHTML = `
      <h2>Entrar</h2><p class="muted small">Acesso exclusivo para veterinários cadastrados, ativos e com senha confirmada.</p>
      <form id="f-login"><div class="form-erro"></div>
        <div class="f"><label>E-mail</label><input name="email" type="email" required autocomplete="username" value="${esc(email)}"></div>
        <div class="f" style="margin-top:.7rem"><label>Senha</label><input name="senha" type="password" required autocomplete="current-password"></div>
        <button class="btn primary" type="submit" style="width:100%;justify-content:center;margin-top:1rem">Entrar</button>
      </form>
      <p class="small" style="margin-top:1rem"><a href="#" id="l-reg">Criar conta de veterinário</a> · <a href="#" id="l-conf">Confirmar senha</a></p>
      <div class="demo-box"><b>Usuários de demonstração</b> (senha <span class="mono">Senha@123</span>)<br>
        ana@clinica.vet — ativa e confirmada<br>bruno@clinica.vet — inativo (bloqueado)<br>carla@clinica.vet — senha não confirmada</div>`;
    ligarForm($("#f-login"), async (d) => {
      try {
        const r = await POST("/api/auth/login", d);
        Sessao.salvar(r.token, r.veterinario);
        iniciarApp();
      } catch (e) {
        if (e.detalhes.includes("SENHA_NAO_CONFIRMADA")) { toast(e.message, "warn"); return mostrarAuth("confirmar", d.email); }
        throw e;
      }
    });
    $("#l-reg").onclick = (e) => { e.preventDefault(); mostrarAuth("registro"); };
    $("#l-conf").onclick = (e) => { e.preventDefault(); mostrarAuth("confirmar"); };
  } else if (tela === "registro") {
    card.innerHTML = `
      <h2>Cadastro de veterinário</h2><p class="muted small">Após o cadastro você receberá um código por e-mail para confirmar a senha.</p>
      <form id="f-reg"><div class="form-erro"></div><div class="row">
        <div class="f"><label>Nome completo</label><input name="nome" required></div>
        <div class="f c6"><label>CPF</label><input name="cpf" required inputmode="numeric" placeholder="000.000.000-00"></div>
        <div class="f c6"><label>Telefone</label><input name="telefone" required inputmode="tel"></div>
        <div class="f c8"><label>CRMV</label><input name="crmv" required inputmode="numeric"></div>
        <div class="f c4"><label>UF</label><select name="crmv_uf">${UFS.map((u) => `<option ${u === "RJ" ? "selected" : ""}>${u}</option>`).join("")}</select></div>
        <div class="f"><label>E-mail</label><input name="email" type="email" required></div>
        <div class="f c6"><label>Senha</label><input name="senha" type="password" required minlength="8"></div>
        <div class="f c6"><label>Confirmar senha</label><input name="confirmacao_senha" type="password" required></div>
        <div class="f"><span class="hint">Mínimo de 8 caracteres, com letras e números. A senha é armazenada apenas como hash.</span></div>
      </div><button class="btn primary" type="submit" style="width:100%;justify-content:center;margin-top:1rem">Cadastrar</button></form>
      <p class="small" style="margin-top:1rem"><a href="#" id="l-login">Voltar ao login</a></p>`;
    ligarForm($("#f-reg"), async (d) => {
      const r = await POST("/api/auth/registro", d);
      toast(r.mensagem, "ok");
      mostrarAuth("confirmar", d.email, r.codigo_simulado);
    });
    $("#l-login").onclick = (e) => { e.preventDefault(); mostrarAuth("login"); };
  } else if (tela === "confirmar") {
    const codigoSim = arguments[2];
    card.innerHTML = `
      <h2>Confirmar senha</h2><p class="muted small">Informe o código de 6 dígitos enviado ao seu e-mail.</p>
      ${codigoSim ? `<div class="alert info">📧 <b>E-mail simulado</b>: seu código é <span class="mono"><b>${esc(codigoSim)}</b></span></div>` : ""}
      <form id="f-conf"><div class="form-erro"></div>
        <div class="f"><label>E-mail</label><input name="email" type="email" required value="${esc(email)}"></div>
        <div class="f" style="margin-top:.7rem"><label>Código</label><input name="codigo" required maxlength="6" inputmode="numeric" class="mono"></div>
        <button class="btn primary" type="submit" style="width:100%;justify-content:center;margin-top:1rem">Confirmar</button>
      </form>
      <p class="small" style="margin-top:1rem"><a href="#" id="l-reenv">Reenviar código</a> · <a href="#" id="l-login">Voltar ao login</a></p>`;
    ligarForm($("#f-conf"), async (d) => {
      const r = await POST("/api/auth/confirmar-senha", d);
      toast(r.mensagem, "ok");
      mostrarAuth("login", d.email);
    });
    $("#l-reenv").onclick = async (e) => {
      e.preventDefault();
      const em = $("#f-conf [name=email]").value;
      try { const r = await POST("/api/auth/reenviar-codigo", { email: em }); toast(r.mensagem, "ok"); if (r.codigo_simulado) mostrarAuth("confirmar", em, r.codigo_simulado); }
      catch (err) { toast(err.message, "err"); }
    };
    $("#l-login").onclick = (e) => { e.preventDefault(); mostrarAuth("login"); };
  }
}

const UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"];

async function iniciarApp() {
  if (!Sessao.token) return mostrarAuth("login");
  try { const me = await GET("/api/auth/me"); Sessao.salvar(Sessao.token, me); }
  catch { return; }
  $("#auth").classList.add("hidden");
  $("#app").classList.remove("hidden");
  const v = Sessao.vet;
  $("#user-name").textContent = `${v.nome} · CRMV ${v.crmv}-${v.crmv_uf}`;
  $("#avatar").textContent = v.nome.replace(/^(Dra?\.?\s+)/i, "").charAt(0);
  if (!location.hash || location.hash === "#/") location.hash = "#/painel";
  rotear();
  atualizarStatus();
}

async function atualizarStatus() {
  if (!Sessao.token) return;
  try {
    const [h, r] = await Promise.all([GET("/api/health"), GET("/api/integracoes/resumo")]);
    const el = $("#gov-status");
    const up = h.api_governamental === "UP";
    el.className = `tag ${up ? "ok" : "err"} small`;
    el.textContent = up ? "Serviço gov.: online" : "Serviço gov.: indisponível";
    const pend = r.PENDENTE + r.FALHA + r.ENVIADA;
    const b = $("#badge-pend");
    b.textContent = pend; b.classList.toggle("hidden", !pend);
  } catch { /* silencioso */ }
}
setInterval(atualizarStatus, 15000);

$("#btn-logout").onclick = async () => {
  try { await POST("/api/auth/logout"); } catch { /* ignora */ }
  Sessao.limpar();
  location.hash = "";
  mostrarAuth("login");
};
$("#menu-btn").onclick = () => $("#sidebar").classList.toggle("open");

// ---------------------------------------------------------------------
// Roteamento
// ---------------------------------------------------------------------
const ROTAS = {};
function rotear() {
  if (!Sessao.token) return mostrarAuth("login");
  const [nomeBruto, ...params] = location.hash.replace(/^#\//, "").split("?")[0].split("/");
  const nome = nomeBruto || "painel";
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.r === nome));
  $("#sidebar").classList.remove("open");
  fecharModal();
  const fn = ROTAS[nome] || ROTAS.painel;
  $("#view").innerHTML = `<div class="muted">Carregando…</div>`;
  fn(...params).catch((e) => { if (e.status !== 401) $("#view").innerHTML = erroHTML(e); });
}
window.addEventListener("hashchange", rotear);

// cache simples de catálogos
const Cache = { especies: null, racas: null, tipos: null };
async function catalogos(forcar = false) {
  if (forcar || !Cache.especies) {
    [Cache.especies, Cache.racas, Cache.tipos] = await Promise.all([GET("/api/especies"), GET("/api/racas"), GET("/api/vacinas/tipos")]);
  }
  return Cache;
}

// =====================================================================
// PAINEL
// =====================================================================
ROTAS.painel = async () => {
  const [tutores, animais, doses, resumo, consultas] = await Promise.all([
    GET("/api/tutores?situacao=ATIVO"), GET("/api/animais?situacao=ATIVO"), GET("/api/vacinas/proximas-doses?dias=30"),
    GET("/api/integracoes/resumo"), GET(`/api/consultas?data=${hojeISO()}`),
  ]);
  $("#view").innerHTML = `
    <div class="page-head"><div><h1>Olá, ${esc(Sessao.vet.nome)}</h1><span class="muted small">${new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long", year: "numeric" })}</span></div></div>
    <div class="grid k4">
      <div class="card kpi"><div class="l">Tutores ativos</div><div class="v">${tutores.length}</div></div>
      <div class="card kpi"><div class="l">Animais ativos</div><div class="v">${animais.length}</div></div>
      <div class="card kpi"><div class="l">Doses previstas (30 dias)</div><div class="v">${doses.length}</div></div>
      <div class="card kpi"><div class="l">Comunicações gov. pendentes</div><div class="v" style="color:${resumo.PENDENTE + resumo.FALHA ? "var(--warn)" : "inherit"}">${resumo.PENDENTE + resumo.FALHA + resumo.ENVIADA}</div>
        <a class="small" href="#/integracoes">ver integrações →</a></div>
    </div>
    <div class="grid k2">
      <div class="card"><h2>Próximas doses</h2>${tabelaDoses(doses.slice(0, 8))}</div>
      <div class="card"><h2>Consultas de hoje</h2>${consultas.length ? `<div class="table-wrap"><table><thead><tr><th>Hora</th><th>Animal</th><th>Motivo</th><th>Situação</th></tr></thead><tbody>
        ${consultas.map((c) => `<tr class="click" onclick="location.hash='#/animais/${c.animal_id}/consultas'"><td>${fmtData(c.data_hora).slice(11)}</td><td>${esc(c.animal_nome)}</td><td>${esc(c.motivo)}</td><td>${tag(c.situacao)}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">Nenhuma consulta para hoje.</div>`}</div>
    </div>`;
};

function tabelaDoses(doses) {
  if (!doses.length) return `<div class="empty">Nenhuma dose prevista no período.</div>`;
  return `<div class="table-wrap"><table><thead><tr><th>Data</th><th>Animal</th><th>Vacina</th><th>Tutor</th></tr></thead><tbody>
    ${doses.map((d) => `<tr class="click" onclick="location.hash='#/animais/${d.animal_id}/vacinas'">
      <td>${fmtData(d.data_proxima_dose)} ${d.atrasada ? '<span class="tag err">atrasada</span>' : ""}</td>
      <td>${esc(d.animal_nome)}</td><td>${esc(d.nome_vacina)}</td><td>${esc(d.tutor_nome)}<div class="muted small">${fmtTel(d.tutor_telefone)}</div></td></tr>`).join("")}
    </tbody></table></div>`;
}

// =====================================================================
// TUTORES
// =====================================================================
ROTAS.tutores = async () => {
  $("#view").innerHTML = `
    <div class="page-head"><h1>Tutores</h1><div class="actions"><button class="btn primary" id="novo">+ Novo tutor</button></div></div>
    <div class="card"><div class="filters">
      <input id="busca" placeholder="Buscar por nome ou CPF…">
      <select id="sit"><option value="">Todas as situações</option><option value="ATIVO" selected>Ativos</option><option value="INATIVO">Inativos</option></select>
    </div><div id="lista"></div></div>`;
  const carregar = async () => {
    const q = encodeURIComponent($("#busca").value), s = $("#sit").value;
    const lista = await GET(`/api/tutores?q=${q}&situacao=${s}`);
    $("#lista").innerHTML = lista.length ? `<div class="table-wrap"><table><thead><tr><th>Nome</th><th>CPF</th><th>Contato</th><th>Cidade</th><th>Animais</th><th>Situação</th><th></th></tr></thead><tbody>
      ${lista.map((t) => `<tr><td><b>${esc(t.nome)}</b></td><td class="mono">${fmtCPF(t.cpf)}</td><td>${esc(t.email)}<div class="muted small">${fmtTel(t.telefone)}</div></td>
        <td>${esc(t.cidade)}/${esc(t.uf)}</td><td>${t.qtd_animais}</td><td>${tag(t.situacao)}</td>
        <td style="white-space:nowrap"><button class="btn sm" data-ed="${t.id}">Editar</button> <a class="btn sm" href="#/animais?tutor=${t.id}">Animais</a></td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">Nenhum tutor encontrado.</div>`;
    $$("[data-ed]").forEach((b) => (b.onclick = async () => formTutor(await GET(`/api/tutores/${b.dataset.ed}`), carregar)));
  };
  let tm;
  $("#busca").oninput = () => { clearTimeout(tm); tm = setTimeout(carregar, 300); };
  $("#sit").onchange = carregar;
  $("#novo").onclick = () => formTutor(null, carregar);
  await carregar();
};

function formTutor(t, aoSalvar) {
  const e = (t && t.endereco) || {};
  const { el, fechar } = abrirModal(t ? "Editar tutor" : "Novo tutor", `
    <form id="f-tutor"><div class="form-erro"></div>
      <div class="row">
        <div class="f c8"><label>Nome completo *</label><input name="nome" required value="${esc(t?.nome)}"></div>
        <div class="f c4"><label>CPF *</label><input name="cpf" required inputmode="numeric" value="${esc(fmtCPF(t?.cpf))}" placeholder="000.000.000-00"></div>
        <div class="f c4"><label>Data de nascimento *</label><input name="data_nascimento" type="date" required max="${hojeISO()}" value="${esc(t?.data_nascimento)}"></div>
        <div class="f c4"><label>Telefone *</label><input name="telefone" required inputmode="tel" value="${esc(fmtTel(t?.telefone))}"></div>
        <div class="f c4"><label>E-mail *</label><input name="email" type="email" required value="${esc(t?.email)}"></div>
        ${t ? `<div class="f c4"><label>Situação</label><select name="situacao"><option ${t.situacao === "ATIVO" ? "selected" : ""}>ATIVO</option><option ${t.situacao === "INATIVO" ? "selected" : ""}>INATIVO</option></select></div>` : ""}
      </div>
      <h3>Endereço</h3>
      ${camposEndereco(e)}
      <div class="form-actions">${t && t.situacao === "ATIVO" ? `<button type="button" class="btn danger" id="inat" style="margin-right:auto">Inativar</button>` : ""}
        <button type="button" class="btn" id="canc">Cancelar</button><button class="btn primary" type="submit">Salvar</button></div>
    </form>`);
  ligarCEP(el);
  $("#canc", el).onclick = fechar;
  if ($("#inat", el)) $("#inat", el).onclick = async () => {
    if (!confirm("Inativar este tutor? O histórico será preservado.")) return;
    await DEL(`/api/tutores/${t.id}`); toast("Tutor inativado.", "ok"); fechar(); aoSalvar();
  };
  ligarForm($("#f-tutor", el), async (d) => {
    d.cpf = dig(d.cpf); d.telefone = dig(d.telefone); d.endereco.cep = dig(d.endereco.cep);
    if (t) await PUT(`/api/tutores/${t.id}`, d); else await POST("/api/tutores", d);
    toast("Tutor salvo com sucesso.", "ok"); fechar(); aoSalvar();
  });
}

function camposEndereco(e = {}) {
  return `<div class="row">
    <div class="f c4"><label>CEP *</label><div class="input-group"><input name="endereco.cep" id="cep" required inputmode="numeric" maxlength="9" value="${esc(fmtCEP(e.cep))}" placeholder="00000-000"><button type="button" class="btn" id="btn-cep">Buscar</button></div>
      <span class="field-msg" id="cep-msg"></span></div>
    <div class="f c8"><label>Logradouro *</label><input name="endereco.logradouro" required value="${esc(e.logradouro)}"></div>
    <div class="f c3"><label>Número *</label><input name="endereco.numero" required value="${esc(e.numero)}"></div>
    <div class="f c5"><label>Complemento</label><input name="endereco.complemento" value="${esc(e.complemento)}"></div>
    <div class="f c4"><label>Bairro *</label><input name="endereco.bairro" required value="${esc(e.bairro)}"></div>
    <div class="f c6"><label>Cidade *</label><input name="endereco.cidade" required value="${esc(e.cidade)}"></div>
    <div class="f c2"><label>UF *</label><select name="endereco.uf">${UFS.map((u) => `<option ${u === (e.uf || "RJ") ? "selected" : ""}>${u}</option>`).join("")}</select></div>
    <div class="f c4"><label>Código IBGE</label><input name="endereco.codigo_ibge" maxlength="7" value="${esc(e.codigo_ibge)}" readonly title="Preenchido pela consulta de CEP"></div>
  </div>`;
}

/** Consulta de CEP via API da clínica (que consome o ViaCEP) com preenchimento automático. */
function ligarCEP(el) {
  const inp = $("#cep", el), msg = $("#cep-msg", el);
  const set = (n, v) => { const f = $(`[name="endereco.${n}"]`, el); if (f && v != null && v !== "") f.value = v; };
  const buscar = async () => {
    const cep = dig(inp.value);
    if (cep.length !== 8) { msg.className = "field-msg err"; msg.textContent = "Informe um CEP com 8 dígitos."; return; }
    msg.className = "field-msg"; msg.textContent = "Consultando ViaCEP…";
    try {
      const r = await GET(`/api/cep/${cep}`);
      set("logradouro", r.logradouro); set("bairro", r.bairro); set("cidade", r.cidade); set("uf", r.uf);
      set("codigo_ibge", r.codigo_ibge);
      if (r.complemento && !$('[name="endereco.complemento"]', el).value) set("complemento", r.complemento);
      inp.value = fmtCEP(cep);
      msg.className = "field-msg ok"; msg.textContent = "Endereço preenchido automaticamente. Informe o número.";
      $('[name="endereco.numero"]', el).focus();
    } catch (e) {
      msg.className = `field-msg ${e.status === 404 ? "err" : "warn"}`;
      msg.textContent = e.status === 404 ? "CEP não encontrado. Verifique o número ou preencha manualmente." : `${e.message}`;
    }
  };
  $("#btn-cep", el).onclick = buscar;
  inp.addEventListener("input", () => { if (dig(inp.value).length === 8) buscar(); });
}

// =====================================================================
// ANIMAIS
// =====================================================================
ROTAS["animais"] = async (id, aba) => {
  if (id && /^\d+/.test(id)) return detalheAnimal(parseInt(id, 10), aba || "dados");
  const tutorFiltro = new URLSearchParams(location.hash.split("?")[1] || "").get("tutor") || "";
  const { especies } = await catalogos();
  $("#view").innerHTML = `
    <div class="page-head"><h1>Animais</h1><div class="actions"><button class="btn primary" id="novo">+ Novo animal</button></div></div>
    <div class="card"><div class="filters">
      <input id="busca" placeholder="Nome, tutor ou microchip…">
      <select id="esp"><option value="">Todas as espécies</option>${especies.map((e) => `<option value="${e.id}">${esc(e.nome)}</option>`).join("")}</select>
      <select id="gov"><option value="">Situação gov.: todas</option><option>SINCRONIZADO</option><option>PENDENTE</option><option>FALHA</option><option value="NAO_ENVIADO">NÃO ENVIADO</option></select>
      ${tutorFiltro ? `<a class="btn" href="#/animais">✕ filtro por tutor</a>` : ""}
    </div><div id="lista"></div></div>`;
  const carregar = async () => {
    const p = new URLSearchParams({ q: $("#busca").value, especie_id: $("#esp").value, gov_situacao: $("#gov").value, tutor_id: tutorFiltro });
    const lista = await GET(`/api/animais?${p}`);
    $("#lista").innerHTML = lista.length ? `<div class="table-wrap"><table><thead><tr><th>Animal</th><th>Espécie / raça</th><th>Tutor</th><th>Microchip</th><th>Governo</th><th>Situação</th></tr></thead><tbody>
      ${lista.map((a) => `<tr class="click" onclick="location.hash='#/animais/${a.id}'"><td><b>${esc(a.nome)}</b><div class="muted small">${a.sexo === "M" ? "Macho" : "Fêmea"} · ${idade(a)}</div></td>
        <td>${esc(a.especie_nome)}<div class="muted small">${esc(a.raca_nome || "Sem raça definida")}</div></td><td>${esc(a.tutor_nome)}</td>
        <td class="mono">${a.microchip_atual || '<span class="muted">—</span>'}</td><td>${tag(a.gov_situacao)}</td><td>${tag(a.situacao)}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">Nenhum animal encontrado.</div>`;
  };
  let tm;
  $("#busca").oninput = () => { clearTimeout(tm); tm = setTimeout(carregar, 300); };
  $("#esp").onchange = carregar; $("#gov").onchange = carregar;
  $("#novo").onclick = () => formAnimal(null, (a) => (location.hash = `#/animais/${a.id}`), tutorFiltro);
  await carregar();
};

async function formAnimal(a, aoSalvar, tutorPadrao) {
  const [{ especies, racas }, tutores] = await Promise.all([catalogos(), GET("/api/tutores?situacao=ATIVO")]);
  const tutorSel = a?.tutor_id || tutorPadrao;
  const { el, fechar } = abrirModal(a ? `Editar ${a.nome}` : "Novo animal", `
    <form id="f-animal"><div class="form-erro"></div><div class="row">
      <div class="f c6"><label>Nome *</label><input name="nome" required value="${esc(a?.nome)}"></div>
      <div class="f c6"><label>Tutor responsável *</label><select name="tutor_id" required><option value="">Selecione…</option>
        ${tutores.map((t) => `<option value="${t.id}" ${t.id == tutorSel ? "selected" : ""}>${esc(t.nome)} — ${fmtCPF(t.cpf)}</option>`).join("")}</select></div>
      <div class="f c4"><label>Espécie *</label><select name="especie_id" id="sel-esp" required><option value="">Selecione…</option>
        ${especies.filter((e) => e.situacao === "ATIVO" || e.id === a?.especie_id).map((e) => `<option value="${e.id}" ${e.id === a?.especie_id ? "selected" : ""}>${esc(e.nome)}</option>`).join("")}</select></div>
      <div class="f c4"><label>Raça</label><select name="raca_id" id="sel-raca"></select><span class="hint">Somente raças da espécie escolhida.</span></div>
      <div class="f c4"><label>Sexo *</label><select name="sexo" required><option value="M" ${a?.sexo === "M" ? "selected" : ""}>Macho</option><option value="F" ${a?.sexo === "F" ? "selected" : ""}>Fêmea</option></select></div>
      <div class="f c4"><label>Data de nascimento</label><input name="data_nascimento" type="date" max="${hojeISO()}" value="${esc(a?.data_nascimento)}"></div>
      <div class="f c4"><label>ou idade estimada (meses)</label><input name="idade_estimada_meses" type="number" min="0" value="${esc(a?.idade_estimada_meses)}"></div>
      <div class="f c4"><label>Peso atual (kg) *</label><input name="peso_atual" type="number" step="0.01" min="0.01" required value="${esc(a?.peso_atual)}"></div>
      <div class="f c6"><label>Cor / pelagem *</label><input name="cor" required value="${esc(a?.cor)}"></div>
      ${a ? `<div class="f c6"><label>Situação</label><select name="situacao">${["ATIVO", "INATIVO", "OBITO"].map((s) => `<option value="${s}" ${a.situacao === s ? "selected" : ""}>${ROTULOS[s] || s}</option>`).join("")}</select></div>` : `
      <div class="f c6"><label>Microchip RFID (opcional agora)</label><input name="microchip" inputmode="numeric" maxlength="15" placeholder="15 dígitos"><span class="hint">Vinculado em seu nome (veterinário autenticado).</span></div>`}
    </div>
    ${a?.microchip_atual ? `<div class="alert info small" style="margin-top:.8rem">Este animal já está no cadastro governamental: as alterações serão comunicadas automaticamente.</div>` : ""}
    <div class="form-actions"><button type="button" class="btn" id="canc">Cancelar</button><button class="btn primary" type="submit">Salvar</button></div></form>`);
  const selEsp = $("#sel-esp", el), selRaca = $("#sel-raca", el);
  const preencherRacas = () => {
    const lista = racas.filter((r) => r.especie_id == selEsp.value && (r.situacao === "ATIVO" || r.id === a?.raca_id));
    selRaca.innerHTML = `<option value="">Sem raça definida</option>` + lista.map((r) => `<option value="${r.id}" ${r.id === a?.raca_id ? "selected" : ""}>${esc(r.nome)}</option>`).join("");
  };
  selEsp.onchange = preencherRacas; preencherRacas();
  $("#canc", el).onclick = fechar;
  ligarForm($("#f-animal", el), async (d) => {
    d = limparVazios(d);
    if (d.microchip) { d.microchip = dig(d.microchip); d.data_implantacao = hojeISO(); }
    const r = a ? await PUT(`/api/animais/${a.id}`, d) : await POST("/api/animais", d);
    toast("Animal salvo com sucesso.", "ok");
    avisarIntegracoes(r.integracoes, 3);
    fechar(); aoSalvar(r);
  });
}

function avisarIntegracoes(integs, n = 2) {
  (integs || []).slice(0, n).forEach((i) => {
    if (i.situacao === "CONFIRMADA" && Date.now() - new Date(i.data_resposta?.replace(" ", "T")).getTime() < 15000) toast(`Governo: ${ROTULOS[i.tipo_operacao]} confirmado (${i.protocolo_externo}).`, "ok");
    if (i.situacao === "PENDENTE") toast(`Governo indisponível: ${ROTULOS[i.tipo_operacao]} ficou pendente e será reenviado.`, "warn");
  });
}

async function detalheAnimal(id, aba) {
  const a = await GET(`/api/animais/${id}`);
  $("#view").innerHTML = `
    <div class="page-head"><div><a class="small" href="#/animais">← Animais</a><h1>${esc(a.nome)} ${tag(a.situacao)}</h1>
      <span class="muted small">${esc(a.especie_nome)} · ${esc(a.raca_nome || "Sem raça definida")} · ${a.sexo === "M" ? "Macho" : "Fêmea"} · ${idade(a)} · Tutor: ${esc(a.tutor_nome)}</span></div>
      <div class="actions"><button class="btn" id="editar">Editar</button></div></div>
    <div class="tabs">${[["dados", "Dados e microchip"], ["consultas", "Consultas"], ["vacinas", "Vacinas"], ["governo", "Integração governamental"]]
      .map(([k, l]) => `<button data-aba="${k}" class="${k === aba ? "active" : ""}">${l}</button>`).join("")}</div>
    <div id="aba"></div>`;
  $$(".tabs button").forEach((b) => (b.onclick = () => (location.hash = `#/animais/${id}/${b.dataset.aba}`)));
  $("#editar").onclick = () => formAnimal(a, () => rotear());
  await ({ dados: abaDados, consultas: abaConsultas, vacinas: abaVacinas, governo: abaGoverno }[aba] || abaDados)(a);
}

async function abaDados(a) {
  $("#aba").innerHTML = `<div class="grid k2">
    <div class="card"><h2>Dados do animal</h2><dl class="dl">
      <dt>Identificador interno</dt><dd>#${a.id}</dd><dt>Espécie</dt><dd>${esc(a.especie_nome)}</dd>
      <dt>Raça</dt><dd>${esc(a.raca_nome || "Sem raça definida")}</dd><dt>Sexo</dt><dd>${a.sexo === "M" ? "Macho" : "Fêmea"}</dd>
      <dt>Nascimento / idade</dt><dd>${a.data_nascimento ? fmtData(a.data_nascimento) + " · " : ""}${idade(a)}</dd>
      <dt>Cor</dt><dd>${esc(a.cor)}</dd><dt>Peso atual</dt><dd>${a.peso_atual} kg</dd>
      <dt>Tutor</dt><dd>${esc(a.tutor_nome)} <span class="muted mono small">${fmtCPF(a.tutor_cpf)}</span></dd>
      <dt>Cadastrado em</dt><dd>${fmtData(a.data_cadastro)}</dd>
      <dt>Situação governamental</dt><dd>${tag(a.gov_situacao)} ${a.gov_protocolo ? `<span class="mono small">${esc(a.gov_protocolo)}</span>` : ""}</dd></dl></div>
    <div class="card"><h2>Microchip RFID</h2>
      ${a.microchip_atual ? `<div style="font-size:1.35rem" class="mono"><b>${a.microchip_atual}</b></div><p class="muted small">Ativo · vinculado por ${esc(a.microchips[0].veterinario_nome)} (CRMV ${a.microchips[0].crmv}-${a.microchips[0].crmv_uf}) em ${fmtData(a.microchips[0].data_vinculo)}</p>`
      : `<div class="alert warn">Animal ainda sem microchip vinculado.</div>`}
      ${a.situacao === "ATIVO" ? `<form id="f-chip"><div class="form-erro"></div><div class="row">
        <div class="f c6"><label>${a.microchip_atual ? "Novo código (substituição)" : "Código do microchip"} *</label><input name="codigo_microchip" required inputmode="numeric" maxlength="15" class="mono" placeholder="15 dígitos">
          <span class="hint">Leitura simulada: digite o código ou <a href="#" id="gerar">gerar um fictício</a>.</span></div>
        <div class="f c6"><label>Data de implantação *</label><input name="data_implantacao" type="date" required max="${hojeISO()}" value="${hojeISO()}"></div>
        ${a.microchip_atual ? `<div class="f"><label>Motivo da substituição *</label><input name="motivo_substituicao" required placeholder="Ex.: chip anterior sem leitura"></div>` : ""}
      </div><div class="form-actions"><button class="btn primary" type="submit">${a.microchip_atual ? "Substituir microchip" : "Vincular microchip"}</button></div>
      <p class="hint">O vínculo é registrado em nome de <b>${esc(Sessao.vet.nome)}</b> e comunicado ao serviço governamental.</p></form>` : ""}
      <h3>Histórico de vínculos</h3>
      ${a.microchips.length ? `<div class="timeline">${a.microchips.map((m) => `<div class="it"><span class="mono"><b>${m.codigo_microchip}</b></span> ${m.ativo ? tag("ATIVO") : tag("INATIVO")}
        <div class="small muted">Implantação ${fmtData(m.data_implantacao)} · vínculo ${fmtData(m.data_vinculo)} por ${esc(m.veterinario_nome)}</div>
        ${m.motivo_substituicao ? `<div class="small">Substituído em ${fmtData(m.data_desativacao)} — motivo: ${esc(m.motivo_substituicao)}</div>` : ""}</div>`).join("")}</div>` : `<div class="muted small">Sem histórico.</div>`}
    </div></div>`;
  const f = $("#f-chip");
  if (!f) return;
  $("#gerar").onclick = (e) => { e.preventDefault(); $("[name=codigo_microchip]", f).value = "076" + Array.from({ length: 12 }, () => Math.floor(Math.random() * 10)).join(""); };
  ligarForm(f, async (d) => {
    d.codigo_microchip = dig(d.codigo_microchip);
    const r = await POST(`/api/animais/${a.id}/microchip`, d);
    toast("Microchip vinculado.", "ok");
    avisarIntegracoes(r.integracoes, 3);
    rotear();
  });
}

async function abaConsultas(a) {
  const lista = await GET(`/api/animais/${a.id}/consultas`);
  $("#aba").innerHTML = `<div class="card"><div class="page-head" style="margin-bottom:.5rem"><h2 style="margin:0">Histórico de atendimentos</h2>
    <div class="actions">${a.situacao === "ATIVO" ? `<button class="btn primary" id="nova">+ Nova consulta</button>` : ""}</div></div>
    ${lista.length ? `<div class="timeline">${lista.map((c) => `<div class="it"><b>${fmtData(c.data_hora)}</b> · ${esc(c.motivo)} ${tag(c.situacao)}
      <div class="small muted">${esc(c.veterinario_nome)} (CRMV ${c.crmv}-${c.crmv_uf})${c.peso_registrado ? ` · ${c.peso_registrado} kg` : ""}${c.temperatura ? ` · ${c.temperatura} °C` : ""}</div>
      ${c.diagnostico ? `<div class="small"><b>Diagnóstico:</b> ${esc(c.diagnostico)}</div>` : ""}
      ${c.tratamento ? `<div class="small"><b>Tratamento:</b> ${esc(c.tratamento)}</div>` : ""}
      <button class="btn sm" data-c="${c.id}" style="margin-top:.3rem">Ver / editar</button></div>`).join("")}</div>` : `<div class="empty">Nenhuma consulta registrada.</div>`}</div>`;
  if ($("#nova")) $("#nova").onclick = () => formConsulta(a, null);
  $$("[data-c]").forEach((b) => (b.onclick = async () => formConsulta(a, await GET(`/api/consultas/${b.dataset.c}`))));
}

function formConsulta(a, c) {
  const so = c && ["CANCELADA"].includes(c.situacao);
  const { el, fechar } = abrirModal(c ? `Consulta de ${fmtData(c.data_hora)}` : `Nova consulta — ${a.nome}`, `
    <form id="f-cons"><div class="form-erro"></div><fieldset ${so ? "disabled" : ""} style="border:0;padding:0;margin:0"><div class="row">
      <div class="f c4"><label>Data e hora *</label><input name="data_hora" type="datetime-local" required value="${esc(c ? c.data_hora.replace(" ", "T").slice(0, 16) : agoraLocal())}"></div>
      <div class="f c4"><label>Situação *</label><select name="situacao">${["AGENDADA", "REALIZADA", "CANCELADA", "NAO_COMPARECEU"].map((s) => `<option value="${s}" ${(c?.situacao || "REALIZADA") === s ? "selected" : ""}>${ROTULOS[s] || s}</option>`).join("")}</select></div>
      <div class="f c4"><label>Veterinário responsável</label><input disabled value="${esc(c?.veterinario_nome || Sessao.vet.nome)}"></div>
      <div class="f"><label>Motivo do atendimento *</label><input name="motivo" required value="${esc(c?.motivo)}"></div>
      <div class="f c6"><label>Anamnese</label><textarea name="anamnese">${esc(c?.anamnese)}</textarea></div>
      <div class="f c6"><label>Sintomas</label><textarea name="sintomas">${esc(c?.sintomas)}</textarea></div>
      <div class="f c6"><label>Diagnóstico</label><textarea name="diagnostico">${esc(c?.diagnostico)}</textarea></div>
      <div class="f c6"><label>Tratamento prescrito</label><textarea name="tratamento">${esc(c?.tratamento)}</textarea></div>
      <div class="f"><label>Prescrição de medicamentos</label><textarea name="prescricao" placeholder="Medicamento, dose, frequência e duração">${esc(c?.prescricao)}</textarea></div>
      <div class="f c3"><label>Peso (kg)</label><input name="peso_registrado" type="number" step="0.01" min="0.01" value="${esc(c?.peso_registrado)}"></div>
      <div class="f c3"><label>Temperatura (°C)</label><input name="temperatura" type="number" step="0.1" min="30" max="45" value="${esc(c?.temperatura)}"></div>
      <div class="f c6"><label>Observações</label><input name="observacoes" value="${esc(c?.observacoes)}"></div>
    </div></fieldset>
    <div class="form-actions">${c && c.situacao !== "REALIZADA" && !so ? `<button type="button" class="btn danger" id="cancel-c" style="margin-right:auto">Cancelar consulta</button>` : ""}
      <button type="button" class="btn" id="fechar">Fechar</button>${so ? "" : `<button class="btn primary" type="submit">Salvar</button>`}</div></form>`, { largura: 820 });
  $("#fechar", el).onclick = fechar;
  if ($("#cancel-c", el)) $("#cancel-c", el).onclick = async () => { await DEL(`/api/consultas/${c.id}`); toast("Consulta cancelada.", "ok"); fechar(); rotear(); };
  ligarForm($("#f-cons", el), async (d) => {
    d = limparVazios(d); d.animal_id = a.id;
    if (c) await PUT(`/api/consultas/${c.id}`, d); else await POST("/api/consultas", d);
    toast("Consulta salva.", "ok"); fechar(); rotear();
  });
}

async function abaVacinas(a) {
  const [{ historico, proximas_doses }, { tipos }] = await Promise.all([GET(`/api/animais/${a.id}/vacinas`), catalogos()]);
  $("#aba").innerHTML = `
    <div class="card"><h2>Próximas doses</h2>${proximas_doses.length ? `<div class="table-wrap"><table><thead><tr><th>Data prevista</th><th>Vacina</th><th>Tipo</th></tr></thead><tbody>
      ${proximas_doses.map((p) => `<tr><td>${fmtData(p.data_proxima_dose)} ${p.atrasada ? '<span class="tag err">atrasada</span>' : ""}</td><td>${esc(p.nome_vacina)}</td><td>${esc(tipos.find((t) => t.codigo === p.tipo_vacina)?.descricao || p.tipo_vacina)}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">Nenhuma dose prevista.</div>`}</div>
    <div class="card"><div class="page-head" style="margin-bottom:.5rem"><h2 style="margin:0">Histórico de vacinação</h2>
      <div class="actions">${a.situacao === "ATIVO" ? `<button class="btn primary" id="nova">+ Registrar vacina</button>` : ""}</div></div>
      ${historico.length ? `<div class="table-wrap"><table><thead><tr><th>Aplicação</th><th>Vacina</th><th>Lote / fabricante</th><th>Dose</th><th>Situação</th><th>Comunicação gov.</th></tr></thead><tbody>
      ${historico.map((v) => `<tr><td>${fmtData(v.data_aplicacao)}</td><td><b>${esc(v.nome_vacina)}</b>${v.antirrabica ? ' <span class="tag info">antirrábica</span>' : ""}<div class="muted small">${esc(v.veterinario_nome)}</div></td>
        <td>${esc(v.lote)}<div class="muted small">${esc(v.fabricante)} · val. ${fmtData(v.data_validade_lote)}</div></td><td>${esc(v.dose)}<div class="muted small">${esc(v.via_aplicacao.toLowerCase())}</div></td>
        <td>${tag(v.situacao)}${v.situacao === "AGENDADA" ? ` <button class="btn sm" data-apl="${v.id}">Marcar aplicada</button>` : ""}</td>
        <td>${comunicacaoHTML(v)}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">Nenhuma vacina registrada.</div>`}</div>`;
  if ($("#nova")) $("#nova").onclick = () => formVacina(a, tipos);
  $$("[data-apl]").forEach((b) => (b.onclick = async () => {
    try {
      const v = await PUT(`/api/vacinas/${b.dataset.apl}`, { situacao: "APLICADA", data_aplicacao: hojeISO() });
      avisarVacina(v); rotear();
    } catch (e) { toast(e.message + (e.detalhes.length ? ": " + e.detalhes.join(" ") : ""), "err"); }
  }));
  $$("[data-reenv]").forEach((b) => (b.onclick = () => reenviar(b.dataset.reenv)));
}

function comunicacaoHTML(v) {
  const c = v.comunicacao_governo;
  if (!c.obrigatoria) return `<span class="muted small">não obrigatória</span>`;
  return `${tag(c.situacao)}${c.protocolo ? `<div class="mono small">${esc(c.protocolo)}</div>` : ""}
    ${c.situacao !== "CONFIRMADA" && c.mensagem ? `<div class="small muted">${esc(c.mensagem)}</div>` : ""}
    ${c.integracao_id && ["PENDENTE", "FALHA"].includes(c.situacao) ? `<button class="btn sm" data-reenv="${c.integracao_id}">Reenviar</button>` : ""}`;
}

function avisarVacina(v) {
  const c = v.comunicacao_governo;
  if (!c.obrigatoria) return toast("Vacina registrada. (Não exige comunicação governamental.)", "ok");
  if (c.situacao === "CONFIRMADA") toast(`Vacina antirrábica registrada e comunicada ao governo. Protocolo ${c.protocolo}.`, "ok");
  else if (c.situacao === "PENDENTE") toast("Vacina registrada localmente. Serviço governamental indisponível: comunicação PENDENTE (reenvio automático).", "warn");
  else if (c.situacao === "FALHA") toast(`Vacina registrada localmente. Comunicação com FALHA: ${c.mensagem}`, "err");
  else toast("Vacina registrada.", "ok");
}

function formVacina(a, tipos) {
  const { el, fechar } = abrirModal(`Registrar vacina — ${a.nome}`, `
    <form id="f-vac"><div class="form-erro"></div><div class="row">
      <div class="f c6"><label>Tipo de vacina (classificação) *</label><select name="tipo_vacina" id="tipo" required><option value="">Selecione…</option>
        ${tipos.map((t) => `<option value="${t.codigo}">${esc(t.descricao)}</option>`).join("")}</select></div>
      <div class="f c6"><label>Nome comercial *</label><input name="nome_vacina" required></div>
      <div class="f" id="aviso-rab"></div>
      <div class="f c6"><label>Fabricante *</label><input name="fabricante" required></div>
      <div class="f c3"><label>Lote *</label><input name="lote" required></div>
      <div class="f c3"><label>Validade do lote *</label><input name="data_validade_lote" type="date" required></div>
      <div class="f c4"><label>Situação *</label><select name="situacao" id="sit-vac"><option value="APLICADA">Aplicada</option><option value="AGENDADA">Agendada</option></select></div>
      <div class="f c4"><label>Data de aplicação *</label><input name="data_aplicacao" type="date" required value="${hojeISO()}"></div>
      <div class="f c4"><label>Próxima dose</label><input name="data_proxima_dose" type="date"></div>
      <div class="f c6"><label>Dose / etapa *</label><input name="dose" required placeholder="Ex.: 1ª dose, reforço anual"></div>
      <div class="f c6"><label>Via de aplicação *</label><select name="via_aplicacao"><option value="SUBCUTANEA">Subcutânea</option><option value="INTRAMUSCULAR">Intramuscular</option><option value="INTRANASAL">Intranasal</option><option value="ORAL">Oral</option></select></div>
      <div class="f"><label>Observações</label><input name="observacoes"></div>
    </div><div class="form-actions"><button type="button" class="btn" id="canc">Cancelar</button><button class="btn primary" type="submit">Registrar</button></div></form>`, { largura: 820 });
  const aviso = () => {
    const rab = $("#tipo", el).value === "ANTIRRABICA";
    $("#aviso-rab", el).innerHTML = rab ? `<div class="alert info small">💉 <b>Vacina antirrábica:</b> após o registro local, a aplicação será <b>comunicada obrigatoriamente</b> ao serviço governamental${a.microchip_atual ? ` (microchip ${a.microchip_atual})` : ". <b>Atenção:</b> o animal ainda não tem microchip; a comunicação ficará aguardando o vínculo"}.</div>` : "";
  };
  $("#tipo", el).onchange = aviso;
  $("#canc", el).onclick = fechar;
  ligarForm($("#f-vac", el), async (d) => {
    d = limparVazios(d); d.animal_id = a.id;
    const v = await POST("/api/vacinas", d);
    avisarVacina(v); fechar(); rotear();
  });
}

async function reenviar(id, forcar = false) {
  try {
    const r = await POST(`/api/integracoes/${id}/reenviar${forcar ? "?forcar=true" : ""}`);
    if (r.situacao === "CONFIRMADA") toast(`Confirmado pelo serviço governamental. Protocolo ${r.protocolo_externo}.${r.mensagem_erro ? " " + r.mensagem_erro : ""}`, "ok");
    else toast(`Ainda ${r.situacao}: ${r.mensagem_erro || ""}`, r.situacao === "FALHA" ? "err" : "warn");
  } catch (e) { toast(e.message, "err"); }
  atualizarStatus();
  rotear();
}

async function abaGoverno(a) {
  $("#aba").innerHTML = `<div class="muted">Consultando o serviço governamental…</div>`;
  const s = await GET(`/api/animais/${a.id}/situacao-governo`);
  const ext = s.registro_externo;
  $("#aba").innerHTML = `<div class="grid k2">
    <div class="card"><h2>Situação local</h2><dl class="dl">
      <dt>Microchip</dt><dd class="mono">${s.microchip || "—"}</dd><dt>Situação</dt><dd>${tag(s.gov_situacao)}</dd>
      <dt>Último protocolo</dt><dd class="mono">${esc(s.gov_protocolo || "—")}</dd><dt>Última sincronização</dt><dd>${fmtData(s.gov_ultima_sync)}</dd></dl>
      <div class="form-actions" style="justify-content:flex-start"><button class="btn primary" id="sync" ${s.microchip ? "" : "disabled"}>Sincronizar agora</button></div></div>
    <div class="card"><h2>Registro no serviço externo <span class="muted small">(consulta em tempo real)</span></h2>
      ${ext ? `<dl class="dl"><dt>Nome</dt><dd>${esc(ext.nome)}</dd><dt>Espécie / raça</dt><dd>${esc(ext.especie)} · ${esc(ext.raca || "—")}</dd>
        <dt>Cor</dt><dd>${esc(ext.cor || "—")}</dd><dt>Tutor</dt><dd>${esc(ext.tutor_nome)}</dd><dt>Situação</dt><dd>${tag(ext.situacao)}</dd>
        <dt>Atualizado em</dt><dd>${fmtData(ext.atualizado_em)}</dd>
        <dt>Vacinas antirrábicas</dt><dd>${ext.vacinacoes_antirrabicas.length ? ext.vacinacoes_antirrabicas.map((v) => `${fmtData(v.data_aplicacao)} · ${esc(v.vacina_nome)} lote ${esc(v.lote)} <span class="mono small">${esc(v.protocolo)}</span>`).join("<br>") : "nenhuma"}</dd></dl>`
      : `<div class="alert ${s.consulta_externa.startsWith("INDISP") ? "err" : "warn"}">${esc(s.consulta_externa.replace(/_/g, " "))}</div>`}</div></div>
    <div class="card"><h2>Operações de integração deste animal</h2>${tabelaIntegracoes(s.integracoes)}</div>`;
  $("#sync").onclick = async () => {
    try { const r = await POST(`/api/animais/${a.id}/sincronizar-governo`); avisarIntegracoes([r.integracao], 1); if (r.integracao?.situacao === "FALHA") toast(r.integracao.mensagem_erro, "err"); }
    catch (e) { toast(e.message, "err"); }
    rotear();
  };
  ligarTabelaIntegracoes();
}

// =====================================================================
// CONSULTAS (visão geral)
// =====================================================================
ROTAS.consultas = async () => {
  $("#view").innerHTML = `<div class="page-head"><h1>Consultas</h1><div class="actions"><span class="muted small">Para registrar, abra o animal → aba Consultas.</span></div></div>
    <div class="card"><div class="filters"><input type="date" id="dt"><select id="sit"><option value="">Todas as situações</option>
      ${["AGENDADA", "REALIZADA", "CANCELADA", "NAO_COMPARECEU"].map((s) => `<option value="${s}">${ROTULOS[s] || s}</option>`).join("")}</select></div><div id="lista"></div></div>`;
  const carregar = async () => {
    const lista = await GET(`/api/consultas?data=${$("#dt").value}&situacao=${$("#sit").value}`);
    $("#lista").innerHTML = lista.length ? `<div class="table-wrap"><table><thead><tr><th>Data/hora</th><th>Animal</th><th>Motivo</th><th>Veterinário</th><th>Situação</th></tr></thead><tbody>
      ${lista.map((c) => `<tr class="click" onclick="location.hash='#/animais/${c.animal_id}/consultas'"><td>${fmtData(c.data_hora)}</td><td>${esc(c.animal_nome)}</td><td>${esc(c.motivo)}</td><td>${esc(c.veterinario_nome)}</td><td>${tag(c.situacao)}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">Nenhuma consulta encontrada.</div>`;
  };
  $("#dt").onchange = carregar; $("#sit").onchange = carregar;
  await carregar();
};

// =====================================================================
// VACINAS (próximas doses)
// =====================================================================
ROTAS.vacinas = async () => {
  $("#view").innerHTML = `<div class="page-head"><h1>Vacinas — próximas doses</h1><div class="actions"><span class="muted small">Para registrar, abra o animal → aba Vacinas.</span></div></div>
    <div class="card"><div class="filters"><label style="align-self:center">Período:</label><select id="dias"><option value="7">7 dias</option><option value="30" selected>30 dias</option><option value="90">90 dias</option><option value="365">1 ano</option></select></div>
    <div id="lista"></div></div>`;
  const carregar = async () => ($("#lista").innerHTML = tabelaDoses(await GET(`/api/vacinas/proximas-doses?dias=${$("#dias").value}`)));
  $("#dias").onchange = carregar;
  await carregar();
};

// =====================================================================
// INTEGRAÇÕES GOVERNAMENTAIS
// =====================================================================
function tabelaIntegracoes(lista) {
  if (!lista.length) return `<div class="empty">Nenhuma operação de integração.</div>`;
  return `<div class="table-wrap"><table><thead><tr><th>#</th><th>Operação</th><th>Animal</th><th>Situação</th><th>Tentativas</th><th>Protocolo</th><th>Solicitação / resposta</th><th></th></tr></thead><tbody>
    ${lista.map((i) => `<tr><td>${i.id}</td><td>${esc(ROTULOS[i.tipo_operacao])}${i.vacina_id ? `<div class="muted small">vacina #${i.vacina_id}</div>` : ""}</td>
      <td><a href="#/animais/${i.animal_id}/governo">${esc(i.animal_nome)}</a><div class="mono small muted">${i.microchip_atual || ""}</div></td>
      <td>${tag(i.situacao)}${i.mensagem_erro ? `<div class="small muted" style="max-width:260px">${esc(i.mensagem_erro)}</div>` : ""}</td>
      <td>${i.tentativas}${i.situacao === "PENDENTE" && i.proxima_tentativa ? `<div class="small muted">próx.: ${fmtData(i.proxima_tentativa).slice(11)}</div>` : ""}</td>
      <td class="mono small">${esc(i.protocolo_externo || "—")}</td>
      <td class="small">${fmtData(i.data_solicitacao)}<div class="muted">${fmtData(i.data_resposta)}</div></td>
      <td style="white-space:nowrap"><button class="btn sm" data-det="${i.id}">Detalhes</button>
        ${["PENDENTE", "FALHA"].includes(i.situacao) ? `<button class="btn sm primary" data-reenv="${i.id}">Reenviar</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div>`;
}

function ligarTabelaIntegracoes() {
  $$("[data-reenv]").forEach((b) => (b.onclick = () => reenviar(b.dataset.reenv)));
  $$("[data-det]").forEach((b) => (b.onclick = async () => {
    const i = await GET(`/api/integracoes/${b.dataset.det}`);
    const { el } = abrirModal(`Integração #${i.id} — ${ROTULOS[i.tipo_operacao]}`, `
      <dl class="dl"><dt>Situação</dt><dd>${tag(i.situacao)}</dd><dt>Chave de idempotência</dt><dd class="mono">${esc(i.chave_idempotencia)}</dd>
        <dt>Protocolo externo</dt><dd class="mono">${esc(i.protocolo_externo || "—")}</dd><dt>HTTP</dt><dd>${i.http_status || "—"}</dd>
        <dt>Tentativas</dt><dd>${i.tentativas}</dd><dt>Solicitação</dt><dd>${fmtData(i.data_solicitacao)}</dd><dt>Último envio</dt><dd>${fmtData(i.data_ultimo_envio)}</dd>
        <dt>Resposta</dt><dd>${fmtData(i.data_resposta)}</dd><dt>Mensagem</dt><dd>${esc(i.mensagem_erro || "—")}</dd></dl>
      <h3>Payload enviado</h3><pre class="json">${esc(JSON.stringify(i.payload, null, 2))}</pre>
      <h3>Resposta do serviço</h3><pre class="json">${esc(JSON.stringify(i.resposta, null, 2))}</pre>
      ${i.situacao === "CONFIRMADA" ? `<div class="form-actions"><button class="btn" id="forcar">Repetir envio (teste de idempotência)</button></div>` : ""}`, { largura: 820 });
    if ($("#forcar", el)) $("#forcar", el).onclick = () => reenviar(i.id, true);
  }));
}

ROTAS.integracoes = async () => {
  const [resumo, health] = await Promise.all([GET("/api/integracoes/resumo"), GET("/api/health")]);
  $("#view").innerHTML = `
    <div class="page-head"><div><h1>Integração governamental</h1><span class="muted small">Serviço simulado · ${health.api_governamental === "UP" ? '<span class="tag ok">online</span>' : `<span class="tag err">${esc(health.api_governamental)}</span>`}
      · reenvio automático ${health.reenvio_automatico ? `a cada ${health.intervalo_reenvio_seg}s (backoff exponencial)` : "desativado"}</span></div>
      <div class="actions"><button class="btn primary" id="reproc">Reprocessar pendências</button></div></div>
    <div class="grid k4">${["PENDENTE", "ENVIADA", "CONFIRMADA", "FALHA"].map((s) => `<div class="card kpi"><div class="l">${tag(s)}</div><div class="v">${resumo[s]}</div></div>`).join("")}</div>
    <div class="card"><div class="filters"><select id="fs"><option value="">Todas as situações</option>${["PENDENTE", "ENVIADA", "CONFIRMADA", "FALHA"].map((s) => `<option>${s}</option>`).join("")}</select>
      <select id="ft"><option value="">Todas as operações</option>${["VACINACAO_ANTIRRABICA", "CADASTRO_ANIMAL", "ATUALIZACAO_ANIMAL"].map((s) => `<option value="${s}">${ROTULOS[s]}</option>`).join("")}</select></div>
    <div id="lista"></div>
    <p class="hint">PENDENTE: aguardando (re)envio · ENVIADA: em transmissão · CONFIRMADA: recebida pelo serviço, com protocolo · FALHA: rejeitada (exige correção) ou limite de tentativas atingido.</p></div>`;
  const carregar = async () => {
    $("#lista").innerHTML = tabelaIntegracoes(await GET(`/api/integracoes?situacao=${$("#fs").value}&tipo=${$("#ft").value}`));
    ligarTabelaIntegracoes();
  };
  $("#fs").onchange = carregar; $("#ft").onchange = carregar;
  $("#reproc").onclick = async () => {
    try { const r = await POST("/api/integracoes/reprocessar-pendentes"); toast(`Processadas: ${r.processadas} · confirmadas: ${r.confirmadas} · ainda pendentes: ${r.ainda_pendentes} · falhas: ${r.falhas}`, r.ainda_pendentes ? "warn" : "ok"); }
    catch (e) { toast(e.message, "err"); }
    atualizarStatus(); rotear();
  };
  await carregar();
};

// =====================================================================
// CATÁLOGOS (espécies e raças)
// =====================================================================
ROTAS.catalogos = async () => {
  const { especies, racas } = await catalogos(true);
  $("#view").innerHTML = `<div class="page-head"><h1>Espécies e raças</h1></div><div class="grid k2">
    <div class="card"><div class="page-head" style="margin-bottom:.5rem"><h2 style="margin:0">Espécies</h2><div class="actions"><button class="btn sm primary" id="n-esp">+ Espécie</button></div></div>
      <table><thead><tr><th>Nome</th><th>Descrição</th><th>Situação</th><th></th></tr></thead><tbody>
      ${especies.map((e) => `<tr><td><b>${esc(e.nome)}</b></td><td class="small">${esc(e.descricao)}</td><td>${tag(e.situacao)}</td><td><button class="btn sm" data-esp="${e.id}">Editar</button></td></tr>`).join("")}</tbody></table></div>
    <div class="card"><div class="page-head" style="margin-bottom:.5rem"><h2 style="margin:0">Raças</h2><div class="actions"><button class="btn sm primary" id="n-raca">+ Raça</button></div></div>
      <div class="table-wrap"><table><thead><tr><th>Raça</th><th>Espécie</th><th>Situação</th><th></th></tr></thead><tbody>
      ${racas.map((r) => `<tr><td><b>${esc(r.nome)}</b><div class="muted small">${esc(r.descricao)}</div></td><td>${esc(r.especie_nome)}</td><td>${tag(r.situacao)}</td><td><button class="btn sm" data-raca="${r.id}">Editar</button></td></tr>`).join("")}</tbody></table></div>
      <p class="hint">A opção "Sem raça definida" está sempre disponível no cadastro do animal.</p></div></div>`;
  const formCat = (tipo, item) => {
    const esp = tipo === "esp";
    const { el, fechar } = abrirModal(`${item ? "Editar" : "Nova"} ${esp ? "espécie" : "raça"}`, `<form id="f-cat"><div class="form-erro"></div><div class="row">
      <div class="f"><label>Nome *</label><input name="nome" required value="${esc(item?.nome)}"></div>
      <div class="f"><label>Descrição</label><input name="descricao" value="${esc(item?.descricao)}"></div>
      ${esp ? "" : `<div class="f c6"><label>Espécie *</label><select name="especie_id">${especies.filter((e) => e.situacao === "ATIVO").map((e) => `<option value="${e.id}" ${e.id === item?.especie_id ? "selected" : ""}>${esc(e.nome)}</option>`).join("")}</select></div>`}
      ${item ? `<div class="f c6"><label>Situação</label><select name="situacao"><option ${item.situacao === "ATIVO" ? "selected" : ""}>ATIVO</option><option ${item.situacao === "INATIVO" ? "selected" : ""}>INATIVO</option></select></div>` : ""}
      </div><div class="form-actions"><button type="button" class="btn" id="canc">Cancelar</button><button class="btn primary" type="submit">Salvar</button></div></form>`, { largura: 520 });
    $("#canc", el).onclick = fechar;
    ligarForm($("#f-cat", el), async (d) => {
      const base = esp ? "/api/especies" : "/api/racas";
      if (item) await PUT(`${base}/${item.id}`, d); else await POST(base, d);
      toast("Salvo.", "ok"); fechar(); Cache.especies = null; rotear();
    });
  };
  $("#n-esp").onclick = () => formCat("esp");
  $("#n-raca").onclick = () => formCat("raca");
  $$("[data-esp]").forEach((b) => (b.onclick = () => formCat("esp", especies.find((e) => e.id == b.dataset.esp))));
  $$("[data-raca]").forEach((b) => (b.onclick = () => formCat("raca", racas.find((r) => r.id == b.dataset.raca))));
};

// =====================================================================
// VETERINÁRIOS
// =====================================================================
ROTAS.veterinarios = async () => {
  const lista = await GET("/api/veterinarios");
  $("#view").innerHTML = `<div class="page-head"><h1>Veterinários</h1><div class="actions"><span class="muted small">Novos veterinários se cadastram pela tela de login e confirmam a senha por e-mail.</span></div></div>
    <div class="card"><div class="table-wrap"><table><thead><tr><th>Nome</th><th>CRMV</th><th>Contato</th><th>Senha</th><th>Último acesso</th><th>Situação</th><th></th></tr></thead><tbody>
    ${lista.map((v) => `<tr><td><b>${esc(v.nome)}</b><div class="muted small mono">${fmtCPF(v.cpf)}</div></td><td>${esc(v.crmv)}-${esc(v.crmv_uf)}</td>
      <td>${esc(v.email)}<div class="muted small">${fmtTel(v.telefone)}</div></td>
      <td>${v.senha_confirmada ? `<span class="tag ok">confirmada</span><div class="muted small">${fmtData(v.data_confirmacao)}</div>` : '<span class="tag warn">não confirmada</span>'}</td>
      <td class="small">${fmtData(v.ultimo_acesso)}</td><td>${tag(v.situacao)}</td>
      <td>${v.id === Sessao.vet.id ? '<span class="muted small">você</span>' : `<button class="btn sm ${v.situacao === "ATIVO" ? "danger" : ""}" data-v="${v.id}" data-s="${v.situacao === "ATIVO" ? "INATIVO" : "ATIVO"}">${v.situacao === "ATIVO" ? "Inativar" : "Reativar"}</button>`}</td></tr>`).join("")}
    </tbody></table></div><p class="hint">A inativação bloqueia o acesso imediatamente e encerra as sessões abertas.</p></div>`;
  $$("[data-v]").forEach((b) => (b.onclick = async () => {
    try { await PATCH(`/api/veterinarios/${b.dataset.v}/situacao`, { situacao: b.dataset.s }); toast("Situação atualizada.", "ok"); rotear(); }
    catch (e) { toast(e.message, "err"); }
  }));
};

// ---------------------------------------------------------------------
iniciarApp();
