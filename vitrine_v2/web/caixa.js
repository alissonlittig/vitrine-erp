// =============================================================================
// FECHAMENTO DE CAIXA — Fechamento do dia, Histórico de fechamentos e
// Relatório diário (mesmas contas do sistema atual, feitas no Python).
//   Esperado = troco inicial + vendas em DINHEIRO + suprimentos − sangrias
//   Diferença = contado − esperado (negativo = FALTA, positivo = SOBRA)
// =============================================================================
"use strict";

const cx = { dia: null, alterado: false, fechado_em: null, histDados: null, relatorio: null, seqCarregar: 0, seqCalculo: 0 };

Telas.caixa = {
  montar() {
    ligarAbas("caixa", (aba) => {
      if (aba === "dia") carregarFechamento(true);
      if (aba === "historico") abrirHistoricoFechamentos();
      if (aba === "relatorio") carregarRelatorioDiario();
    });

    // --- Fechamento do dia ---
    $("#c-data").value = App.hoje;
    ligarNavData("#c-navdata", "#c-data", (d) => {
      if (d === null) { feedback("#c-feedback", "⚠️ Data inválida! Use DD/MM/AAAA", "erro"); return; }
      carregarFechamento(false);
    });
    for (const id of ["#c-troco", "#c-contado", "#c-obs"]) $(id).addEventListener("input", marcarAlterado);
    soDinheiro($("#c-troco"));
    soDinheiro($("#c-contado"));
    soDinheiro($("#c-mov-valor"));
    $("#c-contado").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); salvarFechamento(); } });
    $("#c-suprimento").onclick = () => adicionarMovimento("SUPRIMENTO");
    $("#c-sangria").onclick = () => adicionarMovimento("SANGRIA");
    $("#c-salvar").onclick = salvarFechamento;
    $("#c-movimentos").addEventListener("click", (e) => { const b = e.target.closest("[data-remover]"); if (b) removerMovimento(+b.dataset.remover); });
    Exportacoes.fechamento = async () => {
      if (!cx.dia) return null;
      const r = await api().exportacao_fechamento({ data: cx.dia.data, troco: $("#c-troco").value, contado: $("#c-contado").value,
                                                    observacao: $("#c-obs").value });
      return r.ok ? r : null;
    };

    // --- Histórico de fechamentos ---
    preencherSelect("#hf-mes", App.meses, App.mes);
    $("#hf-mes").onchange = carregarHistoricoFechamentos;
    $("#hf-ano").onchange = carregarHistoricoFechamentos;
    $("#hf-tabela").addEventListener("click", (e) => { const b = e.target.closest("[data-abrir]"); if (b) abrirDiaDoHistorico(b.dataset.abrir); });
    Exportacoes.hist_fechamentos = () => cx.histDados;

    // --- Relatório diário ---
    $("#r-data").value = App.hoje;
    preencherSelect("#r-produto", App.produtos, App.produtos[0]);
    preencherSelect("#r-pagamento", App.pagamentos, App.pagamentos[0]);
    ligarNavData("#r-navdata", "#r-data", (d) => { if (d === null) feedback("#r-feedback", "⚠️ Data inválida! Use DD/MM/AAAA", "erro"); else carregarRelatorioDiario(); });
    $("#r-produto").onchange = carregarRelatorioDiario;
    $("#r-pagamento").onchange = carregarRelatorioDiario;
    Exportacoes.relatorio = () => cx.relatorio && cx.relatorio.exportacao;
  },

  abrir() {
    const aba = abaAtual("caixa");
    if (aba === "dia") carregarFechamento(true);
    else if (aba === "historico") abrirHistoricoFechamentos();
    else carregarRelatorioDiario();
  },
};

// -----------------------------------------------------------------------------
// Fechamento do dia
// -----------------------------------------------------------------------------
function atualizarStatusCaixa() {
  const el = $("#c-status");
  if (cx.alterado) { el.className = "status aviso"; el.textContent = "● Alterações não salvas"; }
  else if (cx.fechado_em) { el.className = "status ok"; el.textContent = `✔ Fechado em ${cx.fechado_em}`; }
  else { el.className = "status"; el.textContent = "Caixa em aberto"; }
}
function marcarAlterado() {
  if (cx.dia && !cx.alterado) { cx.alterado = true; atualizarStatusCaixa(); }
  recalcularCaixa();
}

// manterDigitado=true: só atualiza os números do sistema (ao voltar para a tela), sem apagar o que foi digitado
async function carregarFechamento(manterDigitado) {
  const data = normalizarData($("#c-data").value);
  if (!data) { feedback("#c-feedback", "⚠️ Data inválida! Use DD/MM/AAAA", "erro"); return; }
  if (cx.alterado && cx.dia && data !== cx.dia.data) {
    const ok = await confirmar({ titulo: "Alterações não salvas", texto: `O fechamento de ${esc(cx.dia.data)} tem alterações não salvas.<br>Descartar e abrir outro dia?`,
                                 tipo: "aviso", icone: "i-alerta", sim: "Descartar", nao: "Continuar neste dia", focoNoNao: true });
    if (!ok) { $("#c-data").value = cx.dia.data; return; }
  }
  manterDigitado = manterDigitado && cx.dia && data === cx.dia.data;
  const seq = ++cx.seqCarregar;
  const r = await api().carregar_fechamento(data);
  if (seq !== cx.seqCarregar) return;
  if (!r.ok) { feedback("#c-feedback", r.erro, "erro"); return; }
  cx.dia = r;
  cx.fechado_em = r.fechado_em;
  if (!manterDigitado) {
    cx.alterado = false;
    $("#c-troco").value = r.troco_txt;   // dia já fechado: troco salvo; dia novo: padrão de R$ 200
    $("#c-obs").value = r.observacao;
    $("#c-contado").value = r.contado_txt;
    feedback("#c-feedback", "");
  }
  desenharMovimentos(r.movimentos);
  desenharOnline("#c-online", r.online);
  $("#c-graf-horas").innerHTML = r.grafico_horas;
  $("#c-graf-ranking").innerHTML = r.grafico_ranking;
  atualizarStatusCaixa();
  recalcularCaixa();
}

// Vendas da loja online do dia: separadas do balcão e FORA da conta da gaveta (Pix e cartão não passam por ela).
function desenharOnline(sel, o) {
  const el = $(sel);
  el.classList.toggle("oculto", !(o && o.qtd));
  if (!o || !o.qtd) { el.innerHTML = ""; return; }
  el.innerHTML = `<p class="rotulo">Loja online · não entra na gaveta</p>
    <ul class="conta num"><li class="destaque"><span>Vendas online (${o.qtd} pedido${o.qtd > 1 ? "s" : ""})</span><span>${esc(o.total_fmt)}</span></li>
    ${o.formas.map(([f, v]) => `<li><span>${esc(f.charAt(0) + f.slice(1).toLowerCase())}</span><span>${esc(v)}</span></li>`).join("")}
    <li><span>Taxas de entrega (fora das vendas)</span><span>${esc(o.taxa_fmt)}</span></li></ul>`;
}

function desenharMovimentos(movs) {
  tabela("#c-movimentos", { colunas: ["Hora", "Tipo", "Valor", "Motivo"], linhas: movs.map((m) => [m.hora, m.tipo, m.valor_fmt, m.motivo]),
                            classes: movs.map((m) => (m.tipo === "Sangria" ? "sangria" : "suprimento")) },
        { vazio: "Nenhuma sangria ou suprimento neste dia.",
          acoes: (i) => `<button class="btn btn-p btn-perigo-leve" data-remover="${i}" title="Remover">${ic("i-lixo")}</button>` });
}

async function recalcularCaixa() {
  if (!cx.dia) return;
  const seq = ++cx.seqCalculo;
  const d = cx.dia;
  const r = await api().calcular_caixa({ dinheiro: d.dinheiro, qtd_dinheiro: d.qtd_dinheiro, suprimento: d.suprimento,
                                         sangria: d.sangria, troco: $("#c-troco").value, contado: $("#c-contado").value });
  if (seq !== cx.seqCalculo || !r.ok) return;
  $("#c-conta").innerHTML = `
    <li><span>Troco inicial</span><span>${esc(r.troco)}</span></li>
    <li><span>${esc(r.rotulo_dinheiro)}</span><span>${esc(r.dinheiro)}</span></li>
    <li><span>+ Suprimentos</span><span>${esc(r.suprimento)}</span></li>
    <li><span>− Sangrias</span><span>${esc(r.sangria)}</span></li>
    <li class="total"><span>= Esperado na gaveta</span><span>${esc(r.esperado)}</span></li>`;
  const dif = $("#c-diferenca");
  dif.textContent = r.diferenca;
  dif.className = "dif-" + r.situacao;
}

async function adicionarMovimento(tipo) {
  if (!cx.dia) return;
  const r = await api().adicionar_movimento({ data: cx.dia.data, tipo, valor: $("#c-mov-valor").value, motivo: $("#c-mov-motivo").value });
  if (!r.ok) { feedback("#c-feedback", r.erro, "erro"); $("#c-mov-valor").focus(); return; }
  $("#c-mov-valor").value = "";
  $("#c-mov-motivo").value = "";
  await carregarFechamento(true);
  feedback("#c-feedback", r.mensagem, "ok");
  marcarAlterado();
}

async function removerMovimento(i) {
  const m = cx.dia.movimentos[i];
  const ok = await confirmar({ titulo: `Remover ${m.tipo.toLowerCase()}?`, alvo: `${esc(m.hora)} · ${esc(m.valor_fmt)} · ${esc(m.motivo)}`,
                               tipo: "perigo", icone: "i-lixo", sim: "Remover", nao: "Cancelar", focoNoNao: true });
  if (!ok) return;
  const r = await api().remover_movimento(m.id);
  if (!r.ok) { await avisar("Erro ao remover movimento", esc(r.erro), "perigo"); return; }
  await carregarFechamento(true);
  marcarAlterado();
}

async function salvarFechamento() {
  const data = normalizarData($("#c-data").value);
  if (!data || !cx.dia || data !== cx.dia.data) { carregarFechamento(false); return; }
  const r = await comConfirmacao((extra) => api().salvar_fechamento({ data, troco: $("#c-troco").value, contado: $("#c-contado").value,
                                                                      observacao: $("#c-obs").value, ...extra }),
                                 "confirmou_vazio", "Confirmar");
  if (!r) return;
  if (!r.ok) { feedback("#c-feedback", r.erro, "erro"); return; }
  cx.fechado_em = r.fechado_em;
  cx.alterado = false;
  atualizarStatusCaixa();
  feedback("#c-feedback", r.mensagem, "ok");
}

// -----------------------------------------------------------------------------
// Histórico de fechamentos
// -----------------------------------------------------------------------------
async function abrirHistoricoFechamentos() {
  const r = await api().anos_fechamentos();
  if (r.ok) preencherSelect("#hf-ano", r.anos, $("#hf-ano").value || App.ano);
  if (!$("#hf-ano").value) $("#hf-ano").value = r.anos[0];
  carregarHistoricoFechamentos();
}
async function carregarHistoricoFechamentos() {
  const r = await api().historico_fechamentos($("#hf-mes").value, $("#hf-ano").value);
  if (!r.ok) { toast(r.erro, "erro"); return; }
  cx.histDados = r;
  $("#hf-resumo").textContent = r.resumo;
  tabela("#hf-tabela", r, { vazio: "Nenhum fechamento salvo neste mês.", larga: true,
    acoes: (i, l) => `<button class="btn btn-p" data-abrir="${esc(l[0])}">${ic("i-abrir")}Abrir</button>`,
    aoDuploClique: (i) => { const l = r.linhas[i]; if (r.classes[i] !== "total") abrirDiaDoHistorico(l[0]); } });
}
function abrirDiaDoHistorico(data) {
  $("#c-data").value = data;
  mostrarAba("caixa", "dia");
  carregarFechamento(false);
}

// -----------------------------------------------------------------------------
// Relatório diário
// -----------------------------------------------------------------------------
async function carregarRelatorioDiario() {
  const r = await api().relatorio_diario($("#r-data").value, $("#r-produto").value, $("#r-pagamento").value);
  if (!r.ok) { feedback("#r-feedback", r.erro, "erro"); return; }
  feedback("#r-feedback", "");
  cx.relatorio = r;
  const lista = (linhas) => linhas.map(([rot, val], i) => `<li class="${i === 0 ? "destaque" : ""}"><span>${esc(rot)}</span><span>${esc(val)}</span></li>`).join("");
  $("#r-venda").innerHTML = lista(r.venda) + (r.online && r.online.qtd
    ? `<li><span>Dentro disso, loja online (${r.online.qtd})</span><span>${esc(r.online.total_fmt)}</span></li>` : "");
  $("#r-recebido").innerHTML = lista(r.recebido);
  $("#r-data-venda").textContent = r.data;
  $("#r-data-rec").textContent = r.data;
  $("#r-graf-horas").innerHTML = r.grafico_horas;
  $("#r-graf-ranking").innerHTML = r.grafico_ranking;
}
