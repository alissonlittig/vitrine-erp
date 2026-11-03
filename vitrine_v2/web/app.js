// =============================================================================
// NOVA INTERFACE — base comum a todas as telas
// Regra: o JS só mostra e chama o Python (window.pywebview.api). Validação,
// regras e banco ficam em dados.py, iguais às do sistema atual.
// =============================================================================
"use strict";

// Erros de JavaScript ficam guardados aqui (o teste automático confere que a lista termina vazia)
window.__erros = [];
window.addEventListener("error", (e) => window.__erros.push(String(e.message)));
window.addEventListener("unhandledrejection", (e) => window.__erros.push("promessa: " + String(e.reason && (e.reason.message || e.reason))));

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = () => window.pywebview.api;
const ic = (id) => `<svg class="ic"><use href="#${id}"/></svg>`;
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const PALAVRAS_MINUSCULAS = new Set(["de", "da", "do", "das", "dos", "e"]);
const SIGLAS = new Set(["PIX", "IPTU", "DRE"]);
const titulo = (t) => String(t || "").split(" ").map((p, i) => {
  if (SIGLAS.has(p.toUpperCase())) return p.toUpperCase();
  const m = p.toLowerCase();
  return i > 0 && PALAVRAS_MINUSCULAS.has(m) ? m : m.replace(/(^|[(/.-])(\p{L})/gu, (x, a, b) => a + b.toUpperCase());
}).join(" ");

const App = { telaAtual: "venda", gestaoAberta: false };
const Telas = {};        // cada arquivo de tela registra aqui: montar(), abrir(), tecla(e)
const Exportacoes = {};  // chave -> função que devolve {colunas, linhas, nome, titulo}

// --- datas DD/MM/AAAA ----------------------------------------------------------
function paraData(txt) {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec((txt || "").trim());
  if (!m) return null;
  const d = new Date(+m[3], +m[2] - 1, +m[1]);
  return d.getDate() === +m[1] && d.getMonth() === +m[2] - 1 ? d : null;
}
const fmtData = (d) => `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
function somarDias(txt, n) { const d = paraData(txt) || paraData(App.hoje); d.setDate(d.getDate() + n); return fmtData(d); }
function normalizarData(txt) { const d = paraData(txt); return d ? fmtData(d) : null; }

// =============================================================================
// AVISOS NA TELA
// =============================================================================
function feedback(el, texto, tipo = "ok") {
  if (typeof el === "string") el = $(el);
  el.className = "feedback " + (texto ? tipo : "");
  el.textContent = texto || "";
}
let _toastTimer = null;
function toast(texto, tipo = "ok") {
  let t = $("#toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; document.body.appendChild(t); }
  t.className = "toast " + tipo;
  t.textContent = texto;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.add("oculto"), 6000);
}

// =============================================================================
// JANELAS (modal) — Enter confirma, Esc cancela
// =============================================================================
let fecharModalAtual = null;
function modalAberto() { return !$("#modal-fundo").classList.contains("oculto"); }

function abrirModal(html, { tipo = "", aoConfirmar = null, aoCancelar = null } = {}) {
  const modal = $("#modal");
  modal.className = "modal " + tipo;
  modal.innerHTML = html;
  $("#modal-fundo").classList.remove("oculto");
  const fechar = () => { $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null; };
  fecharModalAtual = (ok) => (ok ? (aoConfirmar ? aoConfirmar() : fechar()) : (aoCancelar ? aoCancelar() : fechar()));
  const sim = modal.querySelector('[data-r="sim"]'), nao = modal.querySelector('[data-r="nao"]');
  if (sim) sim.onclick = () => fecharModalAtual && fecharModalAtual(true);
  if (nao) nao.onclick = () => fecharModalAtual && fecharModalAtual(false);
  setTimeout(() => { const f = modal.querySelector("[autofocus]") || modal.querySelector("input, select") || sim; f && f.focus(); }, 0);
  return { modal, fechar };
}

function confirmar({ titulo: t, texto = "", alvo = "", sim = "Confirmar", nao = "Cancelar", tipo = "", icone = "", focoNoNao = false }) {
  return new Promise((resolve) => {
    let feito = false;
    const fim = (ok) => { if (feito) return; feito = true; $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null; resolve(ok); };
    const { modal } = abrirModal(`<h2>${icone ? ic(icone) : ""}${esc(t)}</h2>${texto ? `<p>${texto}</p>` : ""}
      ${alvo ? `<div class="alvo num">${alvo}</div>` : ""}
      <div class="botoes"><button class="btn" data-r="nao">${esc(nao)}</button>
      <button class="btn ${tipo === "perigo" ? "btn-perigo" : "btn-confirmar"}" data-r="sim">${esc(sim)}</button></div>`,
      { tipo, aoConfirmar: () => fim(true), aoCancelar: () => fim(false) });
    setTimeout(() => modal.querySelector(focoNoNao ? '[data-r="nao"]' : '[data-r="sim"]').focus(), 0);
  });
}

function avisar(t, texto, tipo = "aviso") {
  return new Promise((resolve) => {
    const fim = () => { $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null; resolve(); };
    const { modal } = abrirModal(`<h2>${ic(/perigo|alerta/.test(tipo) ? "i-alerta" : "i-check")}${esc(t)}</h2><p>${texto}</p>
      <div class="botoes"><button class="btn btn-confirmar" data-r="sim">Ok</button></div>`,
      { tipo, aoConfirmar: fim, aoCancelar: fim });
    setTimeout(() => modal.querySelector('[data-r="sim"]').focus(), 0);
  });
}

// Python devolveu {confirmar: "..."}: pergunta e, se a pessoa aceitar, chama de novo com a confirmação.
async function comConfirmacao(chamar, campo, titulo_ = "Confirmar") {
  let r = await chamar({});
  if (r && r.confirmar) {
    const ok = await confirmar({ titulo: titulo_, texto: esc(r.confirmar).replace(/\n/g, "<br>"), tipo: "aviso", icone: "i-alerta",
                                 sim: "Sim, salvar", nao: "Cancelar" });
    if (!ok) return null;
    r = await chamar({ [campo]: true });
  }
  return r;
}

// =============================================================================
// TABELAS
// =============================================================================
const RE_NUM = /^(-\s?)?(R\$\s?)?-?[\d.]+(,\d+)?%?$|^-$|^—$/;
// dados: {colunas, linhas, classes?, cores?}; op: {acoes(i, linha), aoDuploClique(i), vazio, larga, semMoeda}
// (a exportação usa sempre os dados originais, iguais aos do sistema atual)
function tabela(el, dados, op = {}) {
  if (typeof el === "string") el = $(el);
  const linhas = dados.linhas || [];
  const cab = dados.colunas.map((c) => `<th>${esc(c)}</th>`).join("") + (op.acoes ? "<th></th>" : "");
  const corpo = linhas.map((l, i) => {
    const classe = (dados.classes && dados.classes[i]) || "";
    const cor = dados.cores && dados.cores[i];
    const celulas = l.map((v, j) => {
      let txt = v === null || v === undefined ? "" : String(v);
      if (op.semMoeda) txt = txt.replace(/^(-\s)?R\$\s/, "$1");
      const ponto = j === 0 && cor ? `<span class="ponto" style="background:${esc(cor)}"></span>` : "";
      return `<td class="${j > 0 && RE_NUM.test(txt.trim()) ? "n" : ""}">${ponto}${esc(txt)}</td>`;
    }).join("");
    const acoes = op.acoes ? `<td class="acoes">${classe === "total" ? "" : op.acoes(i, l)}</td>` : "";
    return `<tr class="${classe}" data-i="${i}">${celulas}${acoes}</tr>`;
  }).join("");
  const vazio = `<tr><td colspan="${dados.colunas.length + (op.acoes ? 1 : 0)}" class="vazio">${esc(op.vazio || "Nada encontrado.")}</td></tr>`;
  el.innerHTML = `<table class="tabela${op.larga ? " larga" : ""}"><thead><tr>${cab}</tr></thead><tbody>${corpo || vazio}</tbody></table>`;
  if (op.aoDuploClique) {
    el.querySelector("tbody").ondblclick = (e) => { const tr = e.target.closest("tr[data-i]"); if (tr) op.aoDuploClique(+tr.dataset.i); };
  }
  return el;
}

// =============================================================================
// EXPORTAR (Excel / PDF) — exporta exatamente o que a tabela da tela mostra
// =============================================================================
function montarBotoesExportar() {
  $$("[data-exportar]").forEach((el) => {
    const chave = el.dataset.exportar, extra = el.dataset.rotulo ? ` (${el.dataset.rotulo})` : "";
    el.innerHTML = `<button class="btn btn-p" data-tipo="excel">${ic("i-excel")}Excel${esc(extra)}</button>
                    <button class="btn btn-p" data-tipo="pdf">${ic("i-pdf")}PDF${esc(extra)}</button>`;
    el.onclick = (e) => { const b = e.target.closest("[data-tipo]"); if (b) exportar(chave, b.dataset.tipo); };
  });
}
async function exportar(chave, tipo, payload = null) {
  const p = payload || (Exportacoes[chave] && (await Exportacoes[chave]()));
  if (!p || !p.linhas || !p.linhas.length) { await avisar("Exportar", "Não há dados para exportar nesta tela.", "aviso"); return; }
  const r = await api().exportar(tipo, p);
  if (r.ok) toast("✔️ " + r.mensagem);
  else if (!r.cancelado) await avisar("Erro ao exportar", esc(r.erro), "perigo");
}

// =============================================================================
// COMPONENTES PEQUENOS
// =============================================================================
function preencherSelect(sel, valores, atual) {
  if (typeof sel === "string") sel = $(sel);
  sel.innerHTML = valores.map((v) => {
    const [val, rot] = Array.isArray(v) ? v : [v, v];
    return `<option value="${esc(val)}">${esc(rot)}</option>`;
  }).join("");
  if (atual !== undefined && valores.some((v) => (Array.isArray(v) ? v[0] : v) === atual)) sel.value = atual;
}

// Botões ◀ ▶ Hoje (Todas) ao lado de um campo de data. aoMudar(dataNormalizada | "")
function ligarNavData(container, input, aoMudar, { permitirVazio = false } = {}) {
  if (typeof container === "string") container = $(container);
  if (typeof input === "string") input = $(input);
  const aplicar = () => {
    const txt = input.value.trim();
    if (!txt && permitirVazio) { input.classList.remove("invalido"); aoMudar(""); return; }
    const n = normalizarData(txt);
    if (!n) { input.classList.add("invalido"); aoMudar(null); return; }
    input.classList.remove("invalido");
    input.value = n;
    aoMudar(n);
  };
  container.addEventListener("click", (e) => {
    const b = e.target.closest("[data-nav]");
    if (!b) return;
    const n = b.dataset.nav;
    if (n === "hoje") input.value = App.hoje;
    else if (n === "todas") input.value = "";
    else input.value = somarDias(input.value || App.hoje, +n);
    aplicar();
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); aplicar(); } });
  input.addEventListener("change", aplicar);
}

// Abas internas de uma tela
function ligarAbas(grupo, aoTrocar) {
  const barra = $(`.abas[data-grupo="${grupo}"]`);
  barra.addEventListener("click", (e) => {
    const b = e.target.closest("[data-aba]");
    if (b) mostrarAba(grupo, b.dataset.aba, aoTrocar);
  });
}
function mostrarAba(grupo, aba, aoTrocar) {
  $$(`.abas[data-grupo="${grupo}"] [data-aba]`).forEach((x) => x.setAttribute("aria-selected", x.dataset.aba === aba));
  $$(`.painel-aba[data-grupo="${grupo}"]`).forEach((p) => p.classList.toggle("oculto", p.dataset.aba !== aba));
  if (aoTrocar) aoTrocar(aba);
}
function abaAtual(grupo) {
  const b = $(`.abas[data-grupo="${grupo}"] [aria-selected="true"]`);
  return b ? b.dataset.aba : null;
}

// Fichas (botões de escolha)
function fichas(el, itens, marcado, aoEscolher, { multipla = false } = {}) {
  if (typeof el === "string") el = $(el);
  el.innerHTML = itens.map(([val, rot, extra]) => `<button class="ficha" role="${multipla ? "checkbox" : "radio"}" data-v="${esc(val)}"
     aria-checked="${multipla ? marcado.includes(val) : val === marcado}">${extra || ""}${esc(rot)}</button>`).join("");
  el.onclick = (e) => { const b = e.target.closest("[data-v]"); if (b) aoEscolher(b.dataset.v, b); };
}
function marcarFichas(el, valorOuLista) {
  if (typeof el === "string") el = $(el);
  const lista = Array.isArray(valorOuLista) ? valorOuLista : [valorOuLista];
  $$("[data-v]", el).forEach((b) => b.setAttribute("aria-checked", lista.includes(b.dataset.v)));
}

// Campo de dinheiro: só números, vírgula e ponto
function soDinheiro(input) {
  input.addEventListener("beforeinput", (e) => { if (e.data && /[^0-9.,-]/.test(e.data)) e.preventDefault(); });
}

// =============================================================================
// NAVEGAÇÃO
// =============================================================================
const TELAS_GESTAO = ["dashboard", "desafios", "bonificacoes", "equipe", "dre", "auditoria"];

function irPara(tela) {
  if (TELAS_GESTAO.includes(tela) && !App.gestaoAberta) tela = "gestao";
  if (App.telaAtual && Telas[App.telaAtual] && Telas[App.telaAtual].sair && App.telaAtual !== tela) Telas[App.telaAtual].sair();
  App.telaAtual = tela;
  $$(".tela").forEach((s) => s.classList.toggle("oculto", s.id !== "tela-" + tela));
  const nav = TELAS_GESTAO.includes(tela) ? "gestao" : tela;
  $$(".nav-item").forEach((b) => (b.dataset.tela === nav ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
  $("main").scrollTop = 0;
  if (Telas[tela] && Telas[tela].abrir) Telas[tela].abrir();
}

// =============================================================================
// GESTÃO: senha e bloqueio automático por inatividade (igual ao sistema atual)
// =============================================================================
let ultimaAtividade = Date.now();
["keydown", "mousedown", "wheel", "mousemove"].forEach((ev) => document.addEventListener(ev, () => { ultimaAtividade = Date.now(); }, true));

function atualizarCadeado() {
  $("#nav-cadeado").setAttribute("href", App.gestaoAberta ? "#i-cadeado-aberto" : "#i-cadeado");
}
async function bloquearGestao(motivo = "") {
  await api().sair_gestao();
  App.gestaoAberta = false;
  atualizarCadeado();
  if (TELAS_GESTAO.includes(App.telaAtual) || App.telaAtual === "gestao") {
    irPara("venda");
    if (motivo) feedback("#v-feedback", motivo, "aviso");
  }
}
setInterval(() => {
  if (App.gestaoAberta && Date.now() - ultimaAtividade >= (App.minutos_bloqueio || 5) * 60000) {
    bloquearGestao("🔒 Gestão bloqueada por inatividade");
  }
}, 10000);

// =============================================================================
// TECLADO
// =============================================================================
// Alt + letra troca de tela (a letra aparece sublinhada no menu); Alt+G abre a Gestão
const ATALHOS_TELA = { v: "venda", h: "historico", c: "caixa", d: "despesas", e: "estoque", p: "pedidos", g: "gestao" };
const inicioAberto = () => !$("#inicio-painel").classList.contains("oculto");
document.addEventListener("keydown", (e) => {
  if (inicioAberto()) {  // tela inicial aberta: nada age na tela de venda por tras (Tab e Enter ficam para os cartoes)
    if (e.key !== "Tab" && !(e.key === "Enter" && e.target.closest && e.target.closest("#inicio-painel"))) e.preventDefault();
    e.stopImmediatePropagation();
    return;
  }
  if (e.altKey && !e.ctrlKey && ATALHOS_TELA[e.key.toLowerCase()] && !modalAberto()) {
    e.preventDefault();
    irPara(ATALHOS_TELA[e.key.toLowerCase()]);
    return;
  }
  if (/^F([1-9]|1[0-2])$/.test(e.key)) e.preventDefault();  // nenhum atalho de navegador (F5 recarrega, F7…)
  if (e.ctrlKey && ["r", "R", "p", "P", "f", "F", "s", "S", "u", "U"].includes(e.key)) e.preventDefault();
  if (modalAberto()) {
    if (e.key === "Escape") { e.preventDefault(); fecharModalAtual && fecharModalAtual(false); }
    else if (e.key === "Enter" && (e.target.tagName === "INPUT" || e.target.tagName === "SELECT")) {
      e.preventDefault(); fecharModalAtual && fecharModalAtual(true);
    }
    return;
  }
  const t = Telas[App.telaAtual];
  if (t && t.tecla) t.tecla(e);
});

// =============================================================================
// INÍCIO
// =============================================================================
async function iniciar() {
  if (App.iniciado) return;
  App.iniciado = true;
  const r = await api().iniciar();
  if (!r.ok) { await avisar("Erro ao abrir", esc(r.erro), "perigo"); return; }
  Object.assign(App, r);
  mostrarLoja();
  $("#computador").textContent = `Computador: ${r.computador}`;
  $$(".nav-item").forEach((b) => { b.onclick = () => irPara(b.dataset.tela); });
  $$("[data-voltar]").forEach((b) => { b.onclick = () => irPara("gestao"); });
  for (const nome of Object.keys(Telas)) if (Telas[nome].montar) Telas[nome].montar();
  montarBotoesExportar();
  irPara("venda");
  $("#nav-trocar").onclick = voltarAoInicio;
  if (!r.sem_inicio && !sessaoEntrou()) await telaInicial();
  if (r.aviso && !sessaoAvisou()) { marcarAviso(); await avisar("Aviso", esc(r.aviso), "aviso alerta"); }
  if (r.conflitos && r.conflitos.length) {
    await avisar("Atenção: cópia do banco de dados encontrada",
      "O OneDrive criou outra versão do banco de dados nesta pasta:<br><b>" + r.conflitos.map(esc).join("<br>") +
      "</b><br><br>Ela pode conter vendas que NÃO aparecem no sistema agora. Avise o suporte antes de continuar lançando vendas, e NÃO apague esse arquivo.");
  }
}
// --- atualização automática: consulta o estado a cada 30 s (leve, só lê memória do programa) ---
function vendaEmAndamento() {
  const v = ($("#v-valor") || {}).value || "";
  const d = ["#d-desc", "#d-valor"].some((q) => (($(q) || {}).value || "").trim() !== "");  // despesa digitada e não salva
  return v.trim() !== "" || d || (typeof venda !== "undefined" && (venda.itens.length > 0 || venda.salvando)) ||
    !$("#modal-fundo").classList.contains("oculto");
}
async function checarAtualizacao() {
  try {
    const r = await api().atualizacao_estado();
    if (r.versao) $("#versao-app").textContent = "Versão " + r.versao;
    $("#atu-aviso").classList.toggle("oculto", r.status !== "pronta");
    $("#atu-nova").textContent = r.nova ? "v" + r.nova : "";
  } catch (e) { /* sem resposta: tenta de novo depois */ }
}
// --- sincronização: só lê a memória do programa; a venda nunca espera a rede ---
async function checarSync() {
  try {
    const r = await api().sync_estado();
    const el = $("#sync-estado");
    if (!r.configurado) { el.textContent = "Nuvem: não configurada"; return; }
    const pend = r.pendentes ? " · " + r.pendentes + " a enviar" : "";
    el.textContent = r.status === "ok" ? "Sincronizado " + (r.ultima_ok || "").slice(0, 16) + pend
      : r.status === "sem conexão" ? "Sem internet (vendas guardadas" + pend + ")"
      : r.status === "chave" ? "Nuvem: chave recusada, avise o suporte" : "Nuvem: " + r.status + pend;
    // t139: cota mensal do banco central (banco central grátis): avisa em 50% e 80%; em 90% o portão pausa o site e o resto não essencial
    const u = r.uso_nuvem;
    if (u && u.nivel && u.nivel !== "ok") el.textContent += " · Banco da nuvem em " + u.pct + "% da cota do mês" + (u.nivel === "freio" ? " (site pausado)" : "");
    el.title = u ? "Uso do banco central no mês: " + u.pct + "% (" + u.lidas + " leituras, " + u.escritas + " gravações)" : "";
  } catch (e) { /* tenta de novo depois */ }
}
// --- várias lojas no mesmo computador: tela inicial, faixa fixa e troca com confirmação ---
const ENDERECOS = { centro: "Av. das Flores, 100", jardins: "Rua do Comércio, 250" };
const nomeCurtoLoja = () => App.loja.replace(/^Vitrine Cosméticos\s*-?\s*/, "") || "Cosméticos";  // "Filial Centro"
function mostrarLoja() {
  document.documentElement.dataset.loja = App.filial_codigo;
  document.title = "Vitrine · " + nomeCurtoLoja();
  $("#faixa-nome").textContent = nomeCurtoLoja();
  $("#faixa-end").textContent = ENDERECOS[App.filial_codigo] || "";
}
function corSync(s) {
  if (!s || !s.configurado || s.status === "sem conexão") return "cinza";
  return s.status === "ok" && !s.pendentes ? "verde" : "ambar";
}
function rotuloSync(s) {
  if (!s || !s.configurado) return "nuvem não configurada";
  return s.status === "sem conexão" ? "sem internet" : s.pendentes ? s.pendentes + " a enviar" : s.status === "ok" ? "sincronizada" : s.status === "chave" ? "chave recusada, avise o suporte" : s.status;
}
// sessionStorage vive só enquanto a janela está aberta: reabrir o programa sempre volta à tela inicial
const sessaoEntrou = () => { try { return sessionStorage.getItem("entrou") === "1"; } catch (e) { return false; } };
const marcarSessao = (v) => { try { v ? sessionStorage.setItem("entrou", "1") : sessionStorage.removeItem("entrou"); } catch (e) { /* segue */ } };
const sessaoAvisou = () => { try { return sessionStorage.getItem("avisou") === "1"; } catch (e) { return false; } };
const marcarAviso = () => { try { sessionStorage.setItem("avisou", "1"); } catch (e) { /* segue */ } };
const CARTAO_LOJA = { centro: "#0F5C63", jardins: "#6B2D8B" };
async function telaInicial() {
  const r = await api().lojas();
  if (!r.ok || !r.lojas.length) return;
  const painel = $("#inicio-painel");
  $("#inicio-cartoes").innerHTML = r.lojas.slice().sort((a, b) => a.codigo.localeCompare(b.codigo)).map((l) => `<button class="inicio-cartao" data-loja="${esc(l.codigo)}" style="--cartao:${CARTAO_LOJA[l.codigo] || "#334155"}">
    ${l.codigo === App.ultima_loja ? '<span class="ultima">Última usada</span>' : ""}
    <svg class="ic"><use href="#i-loja"/></svg><span class="quase">Vitrine</span><h2>Filial ${esc(l.nome)}</h2>
    <span class="end">${esc(ENDERECOS[l.codigo] || "")}</span>
    <span class="sync-linha"><i class="sync-ponto ${corSync(l.sync)}"></i>${esc(rotuloSync(l.sync))}</span>
    <span class="entrar">Entrar <svg class="ic"><use href="#i-voltar"/></svg></span></button>`).join("");
  $("#inicio-rodape").textContent = "Computador: " + App.computador;
  painel.classList.remove("oculto");
  // sem foco em nenhum cartao: um Enter perdido (leitor de codigo de barras) nao entra numa loja; so clique ou Tab+Enter
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  return new Promise((resolve) => {
    $("#inicio-cartoes").onclick = async (e) => {
      const b = e.target.closest("[data-loja]");
      if (!b) return;
      const t = await api().trocar_loja(b.dataset.loja);
      if (!t.ok) { toast(t.erro || "Não foi possível abrir a loja.", "erro"); return; }
      marcarSessao(true);
      if (b.dataset.loja !== App.filial_codigo) { location.reload(); return; }  // recarrega já na outra loja
      painel.classList.add("oculto");
      resolve();
    };
  });
}
async function voltarAoInicio() {
  if (vendaEmAndamento()) {
    await avisar("Tem lançamento em andamento", "Há uma venda ou janela aberta que ainda não foi salva. Salve ou limpe antes de voltar à tela inicial.");
    return;
  }
  if (!(await confirmar({ titulo: "Trocar de loja?", texto: `Você está na <b>${esc(nomeCurtoLoja())}</b>. Ir para a tela inicial?`,
                          tipo: "aviso", icone: "i-alerta", sim: "Ir para a tela inicial", nao: "Ficar aqui", focoNoNao: true }))) return;
  await api().inicio();
  marcarSessao(false);
  location.reload();
}
// --- 1ª carga do histórico: painel sobre a tela até terminar, depois recarrega ---
const fmtN = (n) => Number(n || 0).toLocaleString("pt-BR");
async function checarCarga() {
  let c = null;
  try { const r = await api().sync_estado(); c = r.carga && r.carga.primeira ? r.carga : null; } catch (e) { return; }
  const painel = $("#carga-painel");
  if (!c) {
    if (!painel.classList.contains("oculto")) { location.reload(); return; }
  } else {
    const pct = c.total ? Math.min(100, Math.floor((c.feito / c.total) * 100)) : 0;
    $("#carga-loja").textContent = App.loja.replace(/^Vitrine Cosméticos\s*-?\s*/, "");
    $("#carga-texto").textContent = `${fmtN(c.feito)} de ${fmtN(c.total)}`;
    $("#carga-pct").textContent = pct + "%";
    $("#carga-fill").style.width = pct + "%";
    painel.classList.remove("oculto");
  }
  setTimeout(checarCarga, 1000);
}
async function atualizarAgora() {
  if (vendaEmAndamento()) {
    toast("Termine ou limpe a venda que está na tela e feche as janelas abertas antes de atualizar.", "erro");
    return;
  }
  const r = await api().atualizacao_aplicar();
  if (r && r.ok === false) toast(r.erro, "erro");
}
window.addEventListener("pywebviewready", () => {
  iniciar().then(() => {
    $("#atu-botao").onclick = atualizarAgora;
    checarAtualizacao();
    setInterval(checarAtualizacao, 30000);
    checarCarga();
    checarSync();
    setInterval(checarSync, 15000);
  });
});
window.__app_atu = { checarAtualizacao, atualizarAgora, vendaEmAndamento };
window.__app = { irPara, App, Telas, mostrarAba };  // usado pelo teste automático
