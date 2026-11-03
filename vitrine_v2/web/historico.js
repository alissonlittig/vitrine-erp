// =============================================================================
// HISTÓRICO DE VENDAS — filtros por vendedor, ordem e data; editar e excluir
// (mesmas regras de hoje: cada linha é editada/excluída sozinha).
// =============================================================================
"use strict";

const hist = { dados: null, ordem: "Mais Recentes" };

Telas.historico = {
  montar() {
    $("#h-vendedor").onchange = carregarHistorico;
    $("#h-ordem").onclick = (e) => {
      const b = e.target.closest("[data-valor]");
      if (!b) return;
      hist.ordem = b.dataset.valor;
      $$("#h-ordem [data-valor]").forEach((x) => x.setAttribute("aria-checked", x === b));
      carregarHistorico();
    };
    ligarNavData("#h-navdata", "#h-data", (d) => { if (d !== null) carregarHistorico(); else feedback("#h-feedback", "⚠️ Data inválida! Use DD/MM/AAAA", "erro"); },
                 { permitirVazio: true });
    $("#h-tabela").addEventListener("click", (e) => {
      const ed = e.target.closest("[data-editar]"), ex = e.target.closest("[data-excluir]");
      if (ed) editarVendaHistorico(+ed.dataset.editar);
      if (ex) excluirVendaHistorico(+ex.dataset.excluir);
    });
    Exportacoes.historico = () => hist.dados && { colunas: hist.dados.colunas, linhas: hist.dados.linhas,
                                                  nome: "historico_de_vendas", titulo: "Histórico de Vendas" };
  },
  async abrir() {
    const r = await api().vendedores();
    if (r.ok) preencherSelect("#h-vendedor", [["Todos", "Todos"], ...r.todos.map((v) => [v, v])], $("#h-vendedor").value || "Todos");
    carregarHistorico();
  },
};

async function carregarHistorico() {
  const r = await api().historico_vendas($("#h-vendedor").value || "Todos", hist.ordem, $("#h-data").value);
  if (!r.ok) { feedback("#h-feedback", r.erro, "erro"); return; }
  feedback("#h-feedback", "");
  hist.dados = r;
  $("#h-contagem").textContent = r.contagem;
  tabela("#h-tabela", r, {
    vazio: "Nenhuma venda encontrada.",
    acoes: (i, l) => `<button class="btn btn-p" data-editar="${i}">${ic("i-editar")}Editar</button>
                      <button class="btn btn-p btn-perigo-leve" data-excluir="${i}">${ic("i-lixo")}Excluir</button>`,
  });
}

function descreverLinhaVenda(l) {
  // l = [ID, Vendedor, Produto, Valor, Pagamento, Horário, Vendido em, Vencimento]
  return `ID ${esc(l[0])} · R$ ${esc(l[3])} · ${esc(l[4])} · ${esc(l[1])} · ${esc(l[6])} ${esc(l[5])}`;
}

async function excluirVendaHistorico(i) {
  const l = hist.dados.linhas[i];
  const ok = await confirmar({ titulo: "Eliminar esta venda?", alvo: descreverLinhaVenda(l), tipo: "perigo", icone: "i-lixo",
                               texto: "Isso afetará o Dashboard.", sim: "Eliminar venda", nao: "Cancelar", focoNoNao: true });
  if (!ok) return;
  const r = await api().excluir_venda(l[0]);
  if (!r.ok) { await avisar("Erro ao eliminar venda", esc(r.erro), "perigo"); return; }
  toast("✔️ Venda eliminada.");
  carregarHistorico();
}

async function editarVendaHistorico(i) {
  const l = hist.dados.linhas[i];
  const v = await api().obter_venda(l[0]);
  if (!v.ok) { await avisar("Editar venda", esc(v.erro), "perigo"); return; }
  const vendedores = v.vendedores.includes(v.vendedor) ? v.vendedores : [v.vendedor, ...v.vendedores];
  const pagamentos = App.pagamentos.includes(v.pagamento) ? App.pagamentos : [v.pagamento, ...App.pagamentos];
  const produtos = App.produtos.includes(v.produto) ? App.produtos : [v.produto, ...App.produtos];
  let prod = v.produto;
  const { modal, fechar } = abrirModal(`
    <h2>${ic("i-editar")}Editar venda ID ${esc(v.id)}</h2>
    <p>${esc(v.data)} · ${esc(v.horario || "")}</p>
    <div class="form-modal">
      <label class="campo">Vendedor <select id="ev-vendedor"></select></label>
      <div class="campo"><span>Produto</span><div class="segmentado" id="ev-produto"></div></div>
      <label class="campo">Pagamento <select id="ev-pagamento"></select></label>
      <label class="campo">Valor (R$) <input id="ev-valor" class="num campo-dinheiro" value="${esc(v.valor)}" autofocus></label>
    </div>
    <div class="feedback" id="ev-erro"></div>
    <div class="botoes"><button class="btn" data-r="nao">Cancelar</button>
      <button class="btn btn-confirmar" data-r="sim">${ic("i-salvar")}SALVAR ALTERAÇÕES</button></div>`,
    { aoConfirmar: async () => {
        const r = await api().editar_venda({ id: v.id, vendedor: $("#ev-vendedor").value, produto: prod,
                                             pagamento: $("#ev-pagamento").value, valor: $("#ev-valor").value });
        if (!r.ok) { feedback("#ev-erro", r.erro, "erro"); return; }
        fechar();
        toast("✔️ Venda alterada.");
        carregarHistorico();
      } });
  preencherSelect($("#ev-vendedor", modal), vendedores, v.vendedor);
  preencherSelect($("#ev-pagamento", modal), pagamentos, v.pagamento);
  fichas($("#ev-produto", modal), produtos.map((p) => [p, titulo(p)]), prod, (p) => { prod = p; marcarFichas("#ev-produto", p); });
  $$("#ev-produto .ficha", modal).forEach((b) => b.classList.remove("ficha"));
  soDinheiro($("#ev-valor", modal));
}
