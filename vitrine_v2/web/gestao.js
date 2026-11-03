// =============================================================================
// ÁREA DE GESTÃO (com senha) — Painel de vendas, Desafios, Bonificações,
// Equipe e DRE anual. Tranca sozinha depois de alguns minutos sem uso.
// =============================================================================
"use strict";

const CARTOES_GESTAO = [
  ["dashboard", "Painel de vendas", "i-grafico", "--azul", "Faturado, recebido e comissões mês a mês"],
  ["desafios", "Desafios", "i-trofeu", "--ambar", "Produto do dia, quantidades e bonificação do mês"],
  ["bonificacoes", "Bonificações", "i-presente", "--violeta", "Bonificações pagas à parte, por mês de referência"],
  ["equipe", "Equipe", "i-equipe", "--ardosia", "Cadastrar, reativar e desativar vendedores"],
  ["dre", "DRE anual", "i-dre", "--verde", "Receita, despesas e lucro do ano"],
  ["auditoria", "Histórico de alterações", "i-lista", "--ardosia", "Quem mudou o quê, onde e quando"],
  ["senha", "Trocar senha", "i-cadeado", "--ardosia", "Muda a senha da área de gestão"],
];

// Resposta {bloqueado: true}: a Gestão trancou (inatividade) — volta para a senha
function gestaoTrancou(r) {
  if (r && r.bloqueado) { App.gestaoAberta = false; atualizarCadeado(); irPara("gestao"); return true; }
  return false;
}

Telas.gestao = {
  montar() {
    $("#g-hub").innerHTML = CARTOES_GESTAO.map(([tela, t, i, c, sub]) =>
      `<button class="cartao c-gestao" data-ir="${tela}" style="--c: var(${c}); --c-claro: var(${c}-claro)">
        <span class="icone">${ic(i)}</span><span class="t">${esc(t)}</span><span class="dica">${esc(sub)}</span></button>`).join("");
    $("#g-hub").onclick = (e) => { const b = e.target.closest("[data-ir]"); if (b) (b.dataset.ir === "senha" ? trocarSenha() : irPara(b.dataset.ir)); };
    $("#g-entrar").onclick = entrarGestao;
    $("#g-senha-campo").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); entrarGestao(); } });
    $("#g-bloquear").onclick = () => bloquearGestao();
  },
  async abrir() {
    const sd = await api().senha_definida();
    $("#g-senha p").textContent = sd.definida === false
      ? "Primeira vez neste computador: digite a senha da gestão (mínimo 6 caracteres). Ela fica guardada protegida e vale daqui para frente."
      : "Digite a senha para continuar.";
    $("#g-senha").classList.toggle("oculto", App.gestaoAberta);
    $("#g-hub").classList.toggle("oculto", !App.gestaoAberta);
    $("#g-bloquear").classList.toggle("oculto", !App.gestaoAberta);
    if (!App.gestaoAberta) { $("#g-senha-campo").value = ""; feedback("#g-senha-erro", ""); setTimeout(() => $("#g-senha-campo").focus(), 0); }
  },
};

function trocarSenha() {
  let ocupado = false;
  const { fechar } = abrirModal(`<h2>${ic("i-cadeado")}Trocar senha da gestão</h2>
    <label class="campo">Senha atual<input id="ts-a" type="password" autocomplete="off" autofocus></label>
    <label class="campo">Senha nova (mínimo 6 caracteres)<input id="ts-n" type="password" autocomplete="off"></label>
    <label class="campo">Repita a senha nova<input id="ts-c" type="password" autocomplete="off"></label>
    <div class="feedback" id="ts-erro"></div>
    <div class="botoes"><button class="btn" data-r="nao">Cancelar (Esc)</button>
    <button class="btn btn-confirmar" data-r="sim">Trocar senha (Enter)</button></div>`, {
    aoConfirmar: async () => {
      if (ocupado) return;
      ocupado = true;
      const r = await api().trocar_senha($("#ts-a").value, $("#ts-n").value, $("#ts-c").value);
      ocupado = false;
      if (gestaoTrancou(r)) { fechar(); return; }
      if (!r.ok) { feedback("#ts-erro", r.erro, "erro"); return; }
      fechar();
      toast("✔️ Senha trocada. Use a nova na próxima vez.");
    },
  });
}

async function entrarGestao() {
  const r = await api().entrar_gestao($("#g-senha-campo").value);
  if (!r.ok) { feedback("#g-senha-erro", r.erro, "erro"); $("#g-senha-campo").value = ""; $("#g-senha-campo").focus(); return; }
  App.gestaoAberta = true;
  ultimaAtividade = Date.now();
  atualizarCadeado();
  Telas.gestao.abrir();
}

// =============================================================================
// PAINEL DE VENDAS (Dashboard)
// =============================================================================
const dash = { iniciado: false, ano: null, marcados: [], todos: [], ativos: [], aba: "vendedores", dados: null, seq: 0 };

Telas.dashboard = {
  montar() {
    $("#db-ano").onchange = () => { dash.ano = $("#db-ano").value; carregarDashboard(); };
    $("#db-todos").onclick = () => { dash.marcados = [...dash.todos]; marcarFichas("#db-equipe", dash.marcados); carregarDashboard(); };
    $("#db-ativos").onclick = () => { dash.marcados = dash.todos.filter((v) => dash.ativos.includes(v)); marcarFichas("#db-equipe", dash.marcados); carregarDashboard(); };
    $("#db-abas").onclick = (e) => { const b = e.target.closest("[data-aba]"); if (b) { dash.aba = b.dataset.aba; desenharAbaDashboard(); } };
    Exportacoes.dashboard = () => { const a = abaDashboard(); return a && { colunas: a.colunas, linhas: a.linhas, nome: a.nome, titulo: a.titulo }; };
  },
  async abrir() {
    const r = await api().dashboard_inicio();
    if (gestaoTrancou(r) || !r.ok) return;
    const novos = r.todos.filter((v) => !dash.todos.includes(v));
    dash.marcados = dash.iniciado ? [...dash.marcados, ...novos] : [...r.todos];  // quem aparece pela 1ª vez vem marcado
    dash.todos = r.todos;
    dash.ativos = r.ativos;
    if (!dash.ano || !r.anos.includes(dash.ano)) dash.ano = r.padrao;
    dash.iniciado = true;
    preencherSelect("#db-ano", r.anos, dash.ano);
    fichas("#db-equipe", r.todos.map((v) => [v, v, `<span class="ponto" style="background:${esc(r.cores[v] || "#999")}"></span>`]), dash.marcados, (v) => {
      dash.marcados = dash.marcados.includes(v) ? dash.marcados.filter((x) => x !== v) : [...dash.marcados, v];
      marcarFichas("#db-equipe", dash.marcados);
      carregarDashboard();
    }, { multipla: true });
    carregarDashboard();
  },
};

function abaDashboard() { return dash.dados && dash.dados.abas.find((a) => a.id === dash.aba); }

async function carregarDashboard() {
  const seq = ++dash.seq;
  $("#db-tabela").classList.add("carregando");
  const r = await api().dashboard(dash.ano, dash.marcados);
  if (seq !== dash.seq) return;
  $("#db-tabela").classList.remove("carregando");
  if (gestaoTrancou(r)) return;
  if (!r.ok) { toast(r.erro, "erro"); return; }
  dash.dados = r;
  $("#db-abas").innerHTML = r.abas.map((a) => `<button data-aba="${a.id}" aria-selected="${a.id === dash.aba}">${esc(a.rotulo)}</button>`).join("");
  desenharAbaDashboard();
}
function desenharAbaDashboard() {
  $$("#db-abas [data-aba]").forEach((b) => b.setAttribute("aria-selected", b.dataset.aba === dash.aba));
  const a = abaDashboard();
  if (!a) return;
  tabela("#db-tabela", { ...a, colunas: [a.colunas[0] + " (R$)", ...a.colunas.slice(1)] }, { larga: true, semMoeda: true });
  $("#db-grafico").innerHTML = a.grafico;
}

// =============================================================================
// DESAFIOS
// =============================================================================
const desafio = { atual: null, mensal: null };

Telas.desafios = {
  montar() {
    ligarAbas("desafios", (aba) => {
      if (aba === "lancar") carregarDesafio();
      if (aba === "mensal") abrirConclusaoMensal();
      if (aba === "participantes") carregarParticipantes();
    });
    $("#ds-data").value = App.hoje;
    $("#ds-meta").textContent = `Meta fixa: ${App.meta_desafio} por vendedora`;
    ligarNavData("#ds-navdata", "#ds-data", (d) => { if (d === null) feedback("#ds-feedback", "⚠️ Data inválida! Use DD/MM/AAAA", "erro"); else carregarDesafio(); });
    $("#ds-produto").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); salvarProdutoDesafio(); } });
    $("#ds-salvar").onclick = salvarProdutoDesafio;
    $("#ds-excluir").onclick = excluirDesafio;
    preencherSelect("#dm-mes", App.meses, App.mes);
    $("#dm-mes").onchange = carregarConclusaoMensal;
    $("#dm-ano").onchange = carregarConclusaoMensal;
    $("#dm-exportar").innerHTML = `
      <button class="btn btn-p" data-exp="resumo" data-tipo="excel">${ic("i-excel")}Excel (resumo)</button>
      <button class="btn btn-p" data-exp="resumo" data-tipo="pdf">${ic("i-pdf")}PDF (resumo)</button>
      <button class="btn btn-p" data-exp="por_dia" data-tipo="excel">${ic("i-excel")}Excel (por dia)</button>`;
    $("#dm-exportar").onclick = (e) => {
      const b = e.target.closest("[data-exp]");
      if (!b || !desafio.mensal) return;
      const t = desafio.mensal[b.dataset.exp];
      exportar(null, b.dataset.tipo, { ...t, titulo_excel: t.titulo.slice(0, 31) });
    };
    $("#dp-lista").addEventListener("change", async (e) => {
      const cb = e.target.closest("input[data-id]");
      if (!cb) return;
      const r = await api().alterar_participacao(+cb.dataset.id, cb.checked);
      if (gestaoTrancou(r)) return;
      if (!r.ok) { cb.checked = !cb.checked; await avisar("Erro", esc(r.erro), "perigo"); return; }
      feedback("#dp-feedback", r.mensagem, "ok");
    });
  },
  abrir() {
    const aba = abaAtual("desafios");
    if (aba === "lancar") carregarDesafio();
    else if (aba === "mensal") abrirConclusaoMensal();
    else carregarParticipantes();
  },
};

async function carregarDesafio() {
  const r = await api().carregar_desafio($("#ds-data").value);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { feedback("#ds-feedback", r.erro, "erro"); return; }
  desafio.atual = r;
  $("#ds-data").value = r.data;
  $("#ds-produto").value = r.desafio ? r.desafio.produto : "";
  const grade = $("#ds-grade");
  if (!r.desafio) {
    $("#ds-titulo-res").textContent = "Quantidade vendida por vendedora";
    grade.innerHTML = `<p class="dica">Salve o produto do desafio deste dia para lançar as quantidades.</p>`;
    return;
  }
  $("#ds-titulo-res").textContent = `Quantidade vendida por vendedora — ${r.desafio.produto}`;
  if (!r.participantes.length) { grade.innerHTML = `<p class="dica">Nenhuma vendedora ativa participa do desafio.</p>`; return; }
  grade.innerHTML = `<div class="grade-desafio">${r.participantes.map((p, i) => `
      <span class="nome">${esc(p.nome)}</span>
      <div class="passo-num"><button type="button" data-menos="${i}" aria-label="Menos">−</button>
        <input class="num" data-qtd="${i}" value="${esc(p.quantidade)}" aria-label="Quantidade de ${esc(p.nome)}">
        <button type="button" data-mais="${i}" aria-label="Mais">+</button></div>
      <div class="barra"><span data-barra="${i}"></span></div>
      <span class="progresso num" data-txt="${i}"></span>`).join("")}</div>
    <div class="linha-botoes" style="justify-content:flex-end; margin-top:14px">
      <button class="btn btn-confirmar" id="ds-salvar-qtd">${ic("i-salvar")}SALVAR QUANTIDADES</button></div>`;
  const atualizar = (i) => {
    const txt = $(`[data-qtd="${i}"]`).value.trim();
    const q = /^\d+$/.test(txt) ? +txt : 0, meta = r.meta, bateu = q >= meta;
    const barra = $(`[data-barra="${i}"]`);
    barra.style.width = `${Math.min(q / meta, 1) * 100}%`;
    barra.className = bateu ? "bateu" : "";
    $(`[data-txt="${i}"]`).textContent = `${bateu ? "✔ " : ""}${q}/${meta}`;
    $(`[data-txt="${i}"]`).classList.toggle("bateu", bateu);
  };
  r.participantes.forEach((_, i) => atualizar(i));
  grade.oninput = (e) => { const c = e.target.closest("[data-qtd]"); if (c) atualizar(+c.dataset.qtd); };
  grade.onclick = (e) => {
    const m = e.target.closest("[data-menos]"), p = e.target.closest("[data-mais]");
    const i = m ? +m.dataset.menos : p ? +p.dataset.mais : null;
    if (i === null) return;
    const c = $(`[data-qtd="${i}"]`);
    c.value = Math.max(0, (parseInt(c.value, 10) || 0) + (m ? -1 : 1));
    atualizar(i);
  };
  $$("[data-qtd]", grade).forEach((c) => c.addEventListener("beforeinput", (e) => { if (e.data && /\D/.test(e.data)) e.preventDefault(); }));
  $("#ds-salvar-qtd").onclick = salvarQuantidades;
}

async function salvarProdutoDesafio() {
  const r = await api().salvar_desafio($("#ds-data").value, $("#ds-produto").value);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { feedback("#ds-feedback", r.erro, "erro"); return; }
  await carregarDesafio();
  feedback("#ds-feedback", r.mensagem, "ok");
}

async function excluirDesafio() {
  if (!desafio.atual || !desafio.atual.desafio) { feedback("#ds-feedback", "⚠️ Não há desafio cadastrado nesta data.", "erro"); return; }
  const ok = await confirmar({ titulo: "Excluir o desafio?", alvo: `${esc(desafio.atual.data)} · ${esc(desafio.atual.desafio.produto)}`,
                               texto: "As quantidades lançadas também serão excluídas. Esse dia deixa de contar na meta do mês.",
                               tipo: "perigo", icone: "i-lixo", sim: "Excluir desafio", nao: "Cancelar", focoNoNao: true });
  if (!ok) return;
  const r = await api().excluir_desafio(desafio.atual.data);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { feedback("#ds-feedback", r.erro, "erro"); return; }
  await carregarDesafio();
  feedback("#ds-feedback", r.mensagem, "ok");
}

async function salvarQuantidades() {
  const qtds = {};
  desafio.atual.participantes.forEach((p, i) => { qtds[p.nome] = $(`[data-qtd="${i}"]`).value; });
  const r = await api().salvar_quantidades_desafio(desafio.atual.desafio.id, qtds);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { await avisar("Erro", esc(r.erro), "perigo"); return; }
  await carregarDesafio();
  feedback("#ds-feedback", r.mensagem, "ok");
}

async function abrirConclusaoMensal() {
  const r = await api().anos_desafio();
  if (gestaoTrancou(r)) return;
  preencherSelect("#dm-ano", r.anos, $("#dm-ano").value || App.ano);
  if (!r.anos.includes($("#dm-ano").value)) $("#dm-ano").value = r.anos[0];
  carregarConclusaoMensal();
}
async function carregarConclusaoMensal() {
  const r = await api().conclusao_mensal($("#dm-mes").value, $("#dm-ano").value);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { toast(r.erro, "erro"); return; }
  desafio.mensal = r;
  $("#dm-kpis").innerHTML = [["DIAS COM DESAFIO", r.kpis.dias, ""], ["META DO MÊS (POR VENDEDORA)", r.kpis.meta, ""],
                             ["TOTAL DE BONIFICAÇÕES", r.kpis.total, "verde"]]
    .map(([t, v, c]) => `<div class="cartao kpi"><span class="rotulo">${esc(t)}</span><strong class="num ${c}">${esc(v)}</strong></div>`).join("");
  tabela("#dm-resumo", r.resumo, { vazio: "Nenhuma vendedora no desafio deste mês." });
  tabela("#dm-por-dia", r.por_dia, { vazio: "Nenhum desafio lançado neste mês.", larga: true });
}

async function carregarParticipantes() {
  const r = await api().participantes_desafio();
  if (gestaoTrancou(r)) return;
  if (!r.ok) { toast(r.erro, "erro"); return; }
  $("#dp-lista").innerHTML = r.equipe.map((v) => `<label class="caixa-marcar"><input type="checkbox" data-id="${v.id}" ${v.participa ? "checked" : ""}>
      <span>${esc(v.nome)}</span></label>`).join("") || `<p class="dica">Nenhuma vendedora ativa. Cadastre a equipe na tela Equipe.</p>`;
}

// =============================================================================
// BONIFICAÇÕES
// =============================================================================
const bonif = { lista: null };

Telas.bonificacoes = {
  montar() {
    preencherSelect("#b-mes", App.meses, App.mes);
    preencherSelect("#bf-mes", ["Ano inteiro", ...App.meses], App.mes);
    soDinheiro($("#b-valor"));
    $("#b-nota").textContent = `Aceita meses a partir de ${App.inicio_comissao}. No DRE, a linha BONIFICAÇÕES soma estes lançamentos com a bonificação dos Desafios do mês.`;
    $("#b-salvar").onclick = salvarBonificacao;
    for (const id of ["#b-valor", "#b-motivo"]) $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); salvarBonificacao(); } });
    $("#bf-mes").onchange = carregarBonificacoes;
    $("#bf-ano").onchange = carregarBonificacoes;
    $("#b-tabela").addEventListener("click", (e) => {
      const ed = e.target.closest("[data-editar]"), ex = e.target.closest("[data-excluir]");
      if (ed) editarBonificacao(+ed.dataset.editar);
      if (ex) excluirBonificacao(+ex.dataset.excluir);
    });
    Exportacoes.bonificacoes = () => bonif.lista;
  },
  async abrir() {
    const r = await api().bonificacoes_inicio();
    if (gestaoTrancou(r) || !r.ok) return;
    const atual = $("#b-vendedora").value;
    preencherSelect("#b-vendedora", [["", "Selecione"], ...r.vendedoras.map((v) => [v, v])], r.vendedoras.includes(atual) ? atual : "");
    preencherSelect("#b-ano", r.anos, $("#b-ano").value || App.ano);
    preencherSelect("#bf-ano", r.anos, $("#bf-ano").value || App.ano);
    carregarBonificacoes();
  },
};

async function salvarBonificacao() {
  const dados = { vendedora: $("#b-vendedora").value, mes: $("#b-mes").value, ano: $("#b-ano").value, valor: $("#b-valor").value,
                  motivo: $("#b-motivo").value };
  const r = await comConfirmacao((extra) => api().salvar_bonificacao({ ...dados, ...extra }), "confirmou", "Confirmar valor");
  if (!r) return;
  if (gestaoTrancou(r)) return;
  if (!r.ok) { feedback("#b-feedback", r.erro, "erro"); return; }
  $("#b-valor").value = "";
  $("#b-motivo").value = "";
  $("#bf-mes").value = dados.mes;  // mostra o período do lançamento, para conferir na hora
  $("#bf-ano").value = dados.ano;
  await carregarBonificacoes();
  feedback("#b-feedback", r.mensagem, "ok");
}

async function carregarBonificacoes() {
  const r = await api().listar_bonificacoes($("#bf-mes").value, $("#bf-ano").value);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { toast(r.erro, "erro"); return; }
  bonif.lista = r;
  $("#bf-resumo").textContent = r.resumo;
  tabela("#b-tabela", r, { vazio: "Nenhuma bonificação neste período.",
    acoes: (i) => `<button class="btn btn-p" data-editar="${i}">${ic("i-editar")}Editar</button>
                   <button class="btn btn-p btn-perigo-leve" data-excluir="${i}">${ic("i-lixo")}Excluir</button>` });
}

async function excluirBonificacao(i) {
  const l = bonif.lista.linhas[i];
  const ok = await confirmar({ titulo: "Excluir esta bonificação?", alvo: `${esc(l[3])} para ${esc(l[1])} (${esc(l[2])})`,
                               tipo: "perigo", icone: "i-lixo", sim: "Excluir", nao: "Cancelar", focoNoNao: true });
  if (!ok) return;
  const r = await api().excluir_bonificacao(bonif.lista.ids[i]);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { await avisar("Erro", esc(r.erro), "perigo"); return; }
  carregarBonificacoes();
}

async function editarBonificacao(i) {
  const b = await api().obter_bonificacao(bonif.lista.ids[i]);
  if (gestaoTrancou(b)) return;
  if (!b.ok) { await avisar("Editar bonificação", esc(b.erro), "perigo"); return; }
  const { modal, fechar } = abrirModal(`
    <h2>${ic("i-editar")}Editar bonificação ID ${esc(b.id)}</h2>
    <div class="form-modal">
      <label class="campo">Vendedora <select id="eb-vend"></select></label>
      <div class="linha-2col"><label class="campo">Mês de referência <select id="eb-mes"></select></label>
        <label class="campo">Ano <select id="eb-ano"></select></label></div>
      <label class="campo">Valor (R$) <input id="eb-valor" class="num campo-dinheiro" value="${esc(b.valor)}" autofocus></label>
      <label class="campo">Motivo <input id="eb-motivo" value="${esc(b.motivo)}"></label>
    </div>
    <div class="feedback" id="eb-erro"></div>
    <div class="botoes"><button class="btn" data-r="nao">Cancelar</button>
      <button class="btn btn-confirmar" data-r="sim">${ic("i-salvar")}SALVAR ALTERAÇÕES</button></div>`,
    { aoConfirmar: async () => {
        const r = await api().editar_bonificacao({ id: b.id, vendedora: $("#eb-vend").value, mes: $("#eb-mes").value,
                                                   ano: $("#eb-ano").value, valor: $("#eb-valor").value, motivo: $("#eb-motivo").value });
        if (gestaoTrancou(r)) { fechar(); return; }
        if (!r.ok) { feedback("#eb-erro", r.erro, "erro"); return; }
        fechar();
        carregarBonificacoes();
      } });
  preencherSelect($("#eb-vend", modal), b.vendedoras, b.vendedor);
  preencherSelect($("#eb-mes", modal), App.meses, b.mes_nome);
  preencherSelect($("#eb-ano", modal), b.anos, b.ano);
  soDinheiro($("#eb-valor", modal));
}

// =============================================================================
// EQUIPE
// =============================================================================
const equipe = { dados: null };

Telas.equipe = {
  montar() {
    $("#e-adicionar").onclick = adicionarVendedor;
    $("#e-nome").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); adicionarVendedor(); } });
    $("#e-tabela").addEventListener("click", (e) => { const b = e.target.closest("[data-desativar]"); if (b) desativarVendedor(+b.dataset.desativar); });
  },
  abrir() { carregarEquipe(); setTimeout(() => $("#e-nome").focus(), 0); },
};

async function carregarEquipe() {
  const r = await api().listar_equipe();
  if (gestaoTrancou(r)) return;
  if (!r.ok) { toast(r.erro, "erro"); return; }
  equipe.dados = r;
  tabela("#e-tabela", { ...r, classes: r.linhas.map((l) => (l[2] === "Inativo" ? "inativo" : "")) }, {
    acoes: (i, l) => (l[2] === "Ativo" ? `<button class="btn btn-p btn-perigo-leve" data-desativar="${i}">Desligar / desativar</button>` : "") });
}

async function adicionarVendedor() {
  const r = await api().adicionar_vendedor($("#e-nome").value);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { feedback("#e-feedback", r.erro, "erro"); return; }
  feedback("#e-feedback", r.mensagem, r.aviso ? "aviso" : "ok");
  $("#e-nome").value = "";
  carregarEquipe();
}

async function desativarVendedor(i) {
  const l = equipe.dados.linhas[i];
  const ok = await confirmar({ titulo: "Desativar vendedor?", alvo: esc(l[1]), texto: "Tem certeza que deseja DESATIVAR este vendedor?",
                               tipo: "perigo", icone: "i-alerta", sim: "Desativar", nao: "Cancelar", focoNoNao: true });
  if (!ok) return;
  const r = await api().desativar_vendedor(l[0]);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { feedback("#e-feedback", r.erro, "erro"); return; }
  feedback("#e-feedback", r.mensagem, "ok");
  carregarEquipe();
}

// =============================================================================
// DRE ANUAL
// =============================================================================
const dreEstado = { dados: null, ano: null };

Telas.dre = {
  montar() {
    $("#dre-ano").onchange = () => { dreEstado.ano = $("#dre-ano").value; carregarDre(); };
    Exportacoes.dre = () => dreEstado.dados;
  },
  async abrir() {
    const r = await api().anos_dre();
    if (gestaoTrancou(r) || !r.ok) return;
    if (!dreEstado.ano || !r.anos.includes(dreEstado.ano)) dreEstado.ano = r.padrao;
    preencherSelect("#dre-ano", r.anos, dreEstado.ano);
    carregarDre();
  },
};

async function carregarDre() {
  const r = await api().dre(dreEstado.ano);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { toast(r.erro, "erro"); return; }
  dreEstado.dados = r;
  const cor = r.kpis.positivo ? "verde" : "vermelho";
  $("#dre-kpis").innerHTML = [["RECEITA BRUTA", r.kpis.receita, "verde"], ["TOTAL DESPESAS", r.kpis.despesas, "vermelho"],
                              ["LUCRO LÍQUIDO", r.kpis.lucro, cor], ["MARGEM DE LUCRO", r.kpis.margem, cor]]
    .map(([t, v, c]) => `<div class="cartao kpi"><span class="rotulo">${esc(t)}</span><strong class="num ${c}">${esc(v)}</strong></div>`).join("");
  tabela("#dre-tabela", r, { larga: true });
  $("#dre-notas").innerHTML = r.notas.map(esc).join("<br>");
  $("#dre-grafico").innerHTML = r.grafico;
}

// =============================================================================
// HISTÓRICO DE ALTERAÇÕES (trilha de auditoria)
// =============================================================================
const AUD_ACAO = { INSERT: "Incluiu", UPDATE: "Alterou", DELETE: "Removeu" };
const AUD_TABELA = { vendas: "Venda", despesas: "Despesa", desafios: "Desafio", desafio_resultados: "Resultado do desafio",
  bonificacoes: "Bonificação", vendedores: "Equipe", fechamento_caixa: "Fechamento de caixa", fechamento_contagem: "Contagem do caixa",
  movimentos_caixa: "Sangria/suprimento", produtos: "Produto", transferencias: "Transferência" };
function audJson(t) { try { const o = JSON.parse(t); return o && typeof o === "object" ? o : null; } catch (e) { return null; } }
function audResumo(it) {
  const a = audJson(it.antes), d = audJson(it.depois);
  const v = (x) => (x === null || x === undefined || x === "" ? "vazio" : String(x));
  if (it.acao === "UPDATE" && a && d) {
    const m = Object.keys(d).filter((k) => String(a[k]) !== String(d[k])).map((k) => `${k}: ${v(a[k])} → ${v(d[k])}`);
    return m.join("; ");
  }
  const o = d || a;
  return o ? Object.entries(o).filter(([, x]) => x !== null && x !== "").map(([k, x]) => `${k}: ${x}`).join("; ") : "";
}
let audTemporizador = null;
Telas.auditoria = {
  montar() {
    $("#au-busca").oninput = () => { clearTimeout(audTemporizador); audTemporizador = setTimeout(carregarAuditoria, 300); };
  },
  abrir() { carregarAuditoria(); },
};
async function carregarAuditoria() {
  const alvo = $("#au-tabela");
  alvo.innerHTML = `<p class="dica" style="padding:14px">Carregando…</p>`;
  const r = await api().auditoria_listar($("#au-busca").value);
  if (gestaoTrancou(r)) return;
  if (!r.ok) { alvo.innerHTML = `<p class="feedback erro">${esc(r.erro)}</p>`; return; }
  $("#au-resumo").textContent = r.itens.length ? `${r.itens.length} mais recentes` : "";
  tabela(alvo, { colunas: ["Quando", "Onde / quem", "Ação", "O quê", "O que mudou"],
    linhas: r.itens.map((it) => [it.quando, it.detalhe || "", AUD_ACAO[it.acao] || it.acao,
      it.tabela ? `${AUD_TABELA[it.tabela] || it.tabela} #${it.registro}` : "", audResumo(it)]) },
    { vazio: "Nenhuma alteração registrada." });
}
