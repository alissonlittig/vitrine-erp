// =============================================================================
// DESPESAS — Registrar, Histórico (editar/apagar) e Gráficos (mesmas regras de hoje)
// =============================================================================
"use strict";

const desp = { tipo: "OUTROS CUSTOS", hist: null, graf: null, tiposMarcados: null, anoGraf: null };

Telas.despesas = {
  montar() {
    ligarAbas("despesas", (aba) => {
      if (aba === "registrar") carregarUltimasDespesas();
      if (aba === "historico") carregarHistoricoDespesas();
      if (aba === "graficos") abrirGraficoDespesas();
    });

    // --- Registrar ---
    $("#d-data").value = App.hoje;
    fichas("#d-tipos", App.tipos_despesa.map((t) => [t, titulo(t)]), desp.tipo, escolherTipoDespesa);
    escolherTipoDespesa(desp.tipo);
    soDinheiro($("#d-valor"));
    const parc = $("#d-parcelas");
    parc.addEventListener("beforeinput", (e) => { if (e.data && /\D/.test(e.data)) e.preventDefault(); });
    $("#d-parc-menos").onclick = () => { parc.value = Math.max(1, (parseInt(parc.value, 10) || 1) - 1); };
    $("#d-parc-mais").onclick = () => { parc.value = Math.min(24, (parseInt(parc.value, 10) || 0) + 1); };
    for (const id of ["#d-desc", "#d-valor", "#d-parcelas", "#d-data"]) {
      $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); salvarDespesa(); } });
    }
    $("#d-salvar").onclick = salvarDespesa;

    // --- Histórico ---
    ligarNavData("#dh-navdata", "#dh-data", (d) => { if (d === null) feedback("#dh-feedback", "⚠️ Data inválida! Use DD/MM/AAAA", "erro"); else carregarHistoricoDespesas(); },
                 { permitirVazio: true });
    $("#dh-tabela").addEventListener("click", (e) => {
      const ed = e.target.closest("[data-editar]"), ex = e.target.closest("[data-excluir]");
      if (ed) editarDespesa(+ed.dataset.editar);
      if (ex) apagarDespesa(+ex.dataset.excluir);
    });
    Exportacoes.hist_despesas = () => desp.hist && { colunas: desp.hist.colunas, linhas: desp.hist.linhas,
                                                     nome: "historico_de_despesas", titulo: "Histórico de Despesas" };

    // --- Gráficos ---
    desp.tiposMarcados = [...App.tipos_despesa];
    fichas("#dg-tipos", App.tipos_despesa.map((t) => [t, titulo(t)]), desp.tiposMarcados, (t) => {
      desp.tiposMarcados = desp.tiposMarcados.includes(t) ? desp.tiposMarcados.filter((x) => x !== t) : [...desp.tiposMarcados, t];
      marcarFichas("#dg-tipos", desp.tiposMarcados);
      carregarGraficoDespesas();
    }, { multipla: true });
    $("#dg-todos").onclick = () => { desp.tiposMarcados = [...App.tipos_despesa]; marcarFichas("#dg-tipos", desp.tiposMarcados); carregarGraficoDespesas(); };
    $("#dg-nenhum").onclick = () => { desp.tiposMarcados = []; marcarFichas("#dg-tipos", []); carregarGraficoDespesas(); };
    $("#dg-ano").onchange = carregarGraficoDespesas;
    Exportacoes.graf_despesas = () => desp.graf;
  },
  abrir() {
    const aba = abaAtual("despesas");
    if (aba === "registrar") { carregarUltimasDespesas(); setTimeout(() => $("#d-desc").focus(), 0); }
    else if (aba === "historico") carregarHistoricoDespesas();
    else abrirGraficoDespesas();
  },
};

function escolherTipoDespesa(t) {
  desp.tipo = t;
  marcarFichas("#d-tipos", t);
  $("#d-tipo-escolhido").textContent = "· " + titulo(t);
}

async function salvarDespesa() {
  const dados = { descricao: $("#d-desc").value, valor: $("#d-valor").value, parcelas: $("#d-parcelas").value,
                  data: $("#d-data").value, tipo: desp.tipo };
  const r = await comConfirmacao((extra) => api().salvar_despesa({ ...dados, ...extra }), "confirmou", "Atenção: comissão manual");
  if (!r) return;
  if (!r.ok) { feedback("#d-feedback", r.erro, "erro"); return; }
  const parc = r.qtd > 1 ? ` (${r.qtd} parcelas)` : "";
  feedback("#d-feedback", r.mensagem + parc, "ok");
  $("#d-desc").value = "";
  $("#d-valor").value = "";
  $("#d-parcelas").value = "1";
  $("#d-desc").focus();
  carregarUltimasDespesas();
}

async function carregarUltimasDespesas() {
  const r = await api().historico_despesas("");
  if (!r.ok) return;
  $("#d-ultimas").innerHTML = r.linhas.slice(0, 12).map((l) => `<li><span>${esc(l[1])}<br><span class="dica">${esc(titulo(l[3] || ""))} · ${esc(l[4])}</span></span>
      <span class="num"><b>R$ ${esc(l[2])}</b></span></li>`).join("") || `<li class="vazio" style="display:block">Nenhuma despesa lançada.</li>`;
}

async function carregarHistoricoDespesas() {
  const r = await api().historico_despesas($("#dh-data").value);
  if (!r.ok) { feedback("#dh-feedback", r.erro, "erro"); return; }
  feedback("#dh-feedback", "");
  desp.hist = r;
  $("#dh-contagem").textContent = r.contagem;
  tabela("#dh-tabela", r, {
    vazio: "Nenhuma despesa encontrada.",
    acoes: (i) => `<button class="btn btn-p" data-editar="${i}">${ic("i-editar")}Editar</button>
                   <button class="btn btn-p btn-perigo-leve" data-excluir="${i}">${ic("i-lixo")}Apagar</button>`,
  });
}

async function apagarDespesa(i) {
  const l = desp.hist.linhas[i];
  const ok = await confirmar({ titulo: "Deseja apagar esta despesa?", alvo: `${esc(l[1])} · R$ ${esc(l[2])} · ${esc(l[3])} · ${esc(l[4])}`,
                               tipo: "perigo", icone: "i-lixo", sim: "Apagar despesa", nao: "Cancelar", focoNoNao: true });
  if (!ok) return;
  const r = await api().excluir_despesa(l[0]);
  if (!r.ok) { await avisar("Erro ao apagar despesa", esc(r.erro), "perigo"); return; }
  toast("✔️ Despesa apagada.");
  carregarHistoricoDespesas();
}

async function editarDespesa(i) {
  const l = desp.hist.linhas[i];
  const d = await api().obter_despesa(l[0]);
  if (!d.ok) { await avisar("Editar despesa", esc(d.erro), "perigo"); return; }
  const tipos = App.tipos_despesa.includes(d.tipo) ? App.tipos_despesa : [d.tipo, ...App.tipos_despesa];
  const { modal, fechar } = abrirModal(`
    <h2>${ic("i-editar")}Editar despesa ID ${esc(d.id)}</h2>
    <div class="form-modal">
      <label class="campo">Descrição <input id="ed-desc" value="${esc(d.descricao)}" autofocus></label>
      <label class="campo">Valor (R$) <input id="ed-valor" class="num campo-dinheiro" value="${esc(d.valor)}"></label>
      <label class="campo">Tipo de despesa <select id="ed-tipo"></select></label>
      <label class="campo">Data (DD/MM/AAAA) <input id="ed-data" class="num" value="${esc(d.data)}"></label>
    </div>
    <div class="feedback" id="ed-erro"></div>
    <div class="botoes"><button class="btn" data-r="nao">Cancelar</button>
      <button class="btn btn-confirmar" data-r="sim">${ic("i-salvar")}SALVAR ALTERAÇÕES</button></div>`,
    { aoConfirmar: async () => {
        const dados = { id: d.id, descricao: $("#ed-desc").value, valor: $("#ed-valor").value, tipo: $("#ed-tipo").value,
                        data: $("#ed-data").value };
        let r = await api().editar_despesa(dados);
        if (r.confirmar) {
          fechar();
          const ok = await confirmar({ titulo: "Atenção: comissão manual", texto: esc(r.confirmar).replace(/\n/g, "<br>"), tipo: "aviso",
                                       icone: "i-alerta", sim: "Sim, salvar", nao: "Cancelar" });
          if (!ok) return;
          r = await api().editar_despesa({ ...dados, confirmou: true });
          if (!r.ok) { await avisar("Erro", esc(r.erro), "perigo"); return; }
        } else if (!r.ok) { feedback("#ed-erro", r.erro, "erro"); return; } else fechar();
        toast("✔️ Despesa alterada.");
        carregarHistoricoDespesas();
      } });
  preencherSelect($("#ed-tipo", modal), tipos, d.tipo);
  soDinheiro($("#ed-valor", modal));
}

async function abrirGraficoDespesas() {
  const r = await api().anos_despesas();
  if (r.ok) preencherSelect("#dg-ano", r.anos, desp.anoGraf || r.padrao);
  desp.anoGraf = desp.anoGraf || r.padrao;
  carregarGraficoDespesas();
}
async function carregarGraficoDespesas() {
  desp.anoGraf = $("#dg-ano").value || desp.anoGraf;
  const r = await api().grafico_despesas(desp.anoGraf, desp.tiposMarcados);
  if (!r.ok) { toast(r.erro, "erro"); return; }
  desp.graf = r;
  tabela("#dg-tabela", { ...r, colunas: [r.colunas[0] + " (R$)", ...r.colunas.slice(1)] }, { vazio: "Sem registros para as opções selecionadas.", larga: true, semMoeda: true });
  $("#dg-grafico").innerHTML = r.grafico;
}
