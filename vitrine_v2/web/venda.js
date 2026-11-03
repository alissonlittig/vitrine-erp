// =============================================================================
// REGISTRAR VENDA — mesmas regras de hoje: escolhe vendedora, produto, pagamento
// e valor, e salva no botão (ou Enter). As escolhas continuam valendo depois de
// salvar; só o valor e a data voltam ao padrão (como no sistema atual).
// =============================================================================
"use strict";

const ICONE_PAGAMENTO = {
  "DINHEIRO": "i-dinheiro", "PIX": "i-pix", "DÉBITO": "i-cartao", "CRÉDITO A V.": "i-cartao",
  "CRÉDITO 2X": "i-parcela", "CRÉDITO 3X": "i-parcela", "RECEBIMENTO": "i-receber",
};
const venda = { vendedor: "", produto: "", pagamento: "", salvando: false, seq: 0, itens: [] };
const RE_BIPE = /^(\d{8,14}|VT-\d+)$/i;  // 8-14 dígitos ou VT-xxxxxx = código de barras; o resto é valor em reais

Telas.venda = {
  montar() {
    fichas("#v-produto", App.produtos.map((p) => [p, titulo(p)]), "", (p) => { escolherProduto(p); $("#v-valor").focus(); });
    $("#v-produto").classList.add("alto");
    $("#v-pagamentos").innerHTML = App.pagamentos_botoes.map(([cod, nome, sub], i) => `
      <button class="pagar ${i < 3 ? "principal" : ""}" role="radio" aria-checked="false" data-v="${esc(cod)}">
        <span class="topo">${ic(ICONE_PAGAMENTO[cod] || "i-cartao")}<span class="kbd">F${i + 1}</span></span>
        <span class="nome">${esc(nome)}</span>${sub ? `<span class="sub">${esc(sub)}</span>` : ""}</button>`).join("");
    $("#v-pagamentos").onclick = (e) => { const b = e.target.closest("[data-v]"); if (b) { escolherPagamento(b.dataset.v); $("#v-valor").focus(); } };

    const campo = $("#v-valor");
    // aceita também as letras do código interno (VT-000001) vindas do leitor
    campo.addEventListener("beforeinput", (e) => { if (e.data && /[^0-9.,\-AEae]/.test(e.data)) e.preventDefault(); });
    campo.addEventListener("input", interpretarValorVenda);
    campo.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (RE_BIPE.test(campo.value.trim())) bipar(campo.value.trim()); else salvarVenda();
      }
      if (e.key === "Escape") { campo.value = ""; interpretarValorVenda(); }
    });
    $("#v-cesta-lista").addEventListener("change", (e) => {
      const i = e.target.dataset.q;
      if (i === undefined) return;
      const n = parseInt(e.target.value, 10);
      venda.itens[i].qtd = n > 0 ? n : 1;
      desenharCesta();
    });
    $("#v-cesta-lista").addEventListener("click", (e) => {
      const b = e.target.closest("[data-rm]");
      if (b) { venda.itens.splice(+b.dataset.rm, 1); desenharCesta(); $("#v-valor").focus(); }
    });
    const data = $("#v-data");
    data.value = App.hoje;
    data.addEventListener("input", atualizarAvisoData);
    data.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); salvarVenda(); } });
    $("#v-data-hoje").onclick = () => { data.value = App.hoje; atualizarAvisoData(); $("#v-valor").focus(); };
    $("#v-salvar").onclick = salvarVenda;
    montarFichasVendedoras(App.vendedores);
  },

  async abrir() {
    const r = await api().vendedores();  // a equipe pode ter mudado na Gestão
    if (r.ok) montarFichasVendedoras(r.ativos);
    atualizarListaHoje();
    setTimeout(() => $("#v-valor").focus(), 0);
  },

  tecla(e) {
    const n = /^F([1-7])$/.exec(e.key);
    if (n) { const p = App.pagamentos_botoes[+n[1] - 1]; if (p) escolherPagamento(p[0]); return; }
    if (e.key === "F8") { escolherProduto(venda.produto === "PERFUMARIA" ? "OUTROS" : "PERFUMARIA"); return; }
    if (e.ctrlKey && /^[1-9]$/.test(e.key)) {
      e.preventDefault();
      const b = $$("#v-fichas .ficha")[+e.key - 1];
      if (b) escolherVendedor(b.dataset.v);
      return;
    }
    const foco = document.activeElement;
    if (/^[0-9aA]$/.test(e.key) && !e.ctrlKey && !e.altKey && (!foco || !["INPUT", "SELECT", "TEXTAREA"].includes(foco.tagName))) {
      $("#v-valor").focus();  // digitou um número fora de um campo: vai para o valor
    }
  },
};

function montarFichasVendedoras(ativos) {
  const lista = ativos.filter((v) => v !== "Nenhum Vendedor Ativo");
  if (!lista.includes(venda.vendedor)) venda.vendedor = "";
  if (!lista.length) { $("#v-fichas").innerHTML = `<span class="dica">Nenhum vendedor ativo. Cadastre a equipe em Gestão → Equipe.</span>`; return; }
  fichas("#v-fichas", lista.map((v, i) => [v, titulo(v), i < 9 ? `<span class="kbd kbd-mini">${i + 1}</span>` : ""]), venda.vendedor,
    (v) => { escolherVendedor(v); $("#v-valor").focus(); });
}
function escolherVendedor(v) { venda.vendedor = v; marcarFichas("#v-fichas", v); limparErroVenda(); }
function escolherProduto(p) { venda.produto = p; marcarFichas("#v-produto", p); limparErroVenda(); }
function escolherPagamento(p) { venda.pagamento = p; marcarFichas("#v-pagamentos", p); limparErroVenda(); }
function limparErroVenda() { const f = $("#v-feedback"); if (f.classList.contains("erro")) feedback(f, ""); }

async function interpretarValorVenda() {
  const seq = ++venda.seq;
  const texto = $("#v-valor").value.trim();
  const st = $("#v-valor-status");
  if (RE_BIPE.test(texto)) { st.className = "valor-status ok"; st.textContent = "Código de barras: aperte Enter"; $("#v-caixa-valor").classList.remove("invalido"); return; }
  if (/[a-z]/i.test(texto) || texto.replace(/\D/g, "").length > 9) {  // bipe misturado com número: nunca vira valor
    st.className = "valor-status erro"; st.textContent = "Valor inválido. Esc limpa o campo."; $("#v-caixa-valor").classList.add("invalido"); return;
  }
  const soma = totalCesta();
  if (!texto && soma !== null) { st.className = "valor-status ok"; st.textContent = `Soma dos produtos: R$ ${brl(soma)}. Aperte Enter para salvar.`; $("#v-caixa-valor").classList.remove("invalido"); return; }
  if (!texto) { st.className = "valor-status"; st.textContent = "Ex.: 42,50 ou 1.500"; $("#v-caixa-valor").classList.remove("invalido"); return; }
  const r = await api().interpretar_valor(texto);
  if (seq !== venda.seq) return;  // resposta de uma digitação antiga
  const ruim = !r.ok || r.zero;
  st.className = "valor-status " + (ruim ? "erro" : "ok");
  st.textContent = !r.ok ? "Valor inválido" : r.zero ? "O valor não pode ser zero" : `= ${r.formatado}`;
  $("#v-caixa-valor").classList.toggle("invalido", ruim);
  limparErroVenda();
}

function atualizarAvisoData() {
  const outra = $("#v-data").value.trim() !== App.hoje;
  $("#v-data").classList.toggle("outra-data", outra);
  $("#v-data").title = outra ? "Atenção: a venda vai ser lançada em outra data, não hoje." : "";
}

async function salvarVenda() {
  if (venda.salvando || modalAberto()) return;
  const digitado = $("#v-valor").value.trim();
  if (/[a-z]/i.test(digitado) || digitado.replace(/\D/g, "").length > 9) {
    feedback("#v-feedback", "Valor inválido. Se você bipou um produto, aperte Esc para limpar o campo e bipe de novo.", "erro");
    return;
  }
  const soma = totalCesta();
  venda.salvando = true;
  try {
    const r = await api().registrar_venda({ vendedor: venda.vendedor, produto: venda.produto, pagamento: venda.pagamento,
                                            valor: digitado || (soma === null ? "" : brl(soma)), data: $("#v-data").value,
                                            itens: venda.itens.map((i) => ({ codigo: i.codigo, qtd: i.qtd })) });
    if (!r.ok) { feedback("#v-feedback", r.erro, "erro"); return; }
    const v = r.venda;
    const rotPag = (App.pagamentos_botoes.find((p) => p[0] === v.pagamento) || [v.pagamento, v.pagamento, ""]);
    const outraData = v.data !== App.hoje ? ` · em ${v.data}` : "";
    feedback("#v-feedback", `${r.mensagem}  ${v.valor_fmt} · ${rotPag[1]}${rotPag[2] ? " " + rotPag[2] : ""} · ${titulo(v.vendedor)} · ${titulo(v.produto)} · ${v.hora}${outraData}`, "ok");
    if (r.avisos_estoque && r.avisos_estoque.length) toast("⚠️ " + r.avisos_estoque.join(" "), "aviso");
    venda.itens = []; desenharCesta();
    $("#v-valor").value = "";
    $("#v-data").value = App.hoje;
    atualizarAvisoData();
    interpretarValorVenda();
    atualizarListaHoje();
  } finally {
    venda.salvando = false;
    if (!modalAberto()) $("#v-valor").focus();
  }
}

async function atualizarListaHoje() {
  const r = await api().vendas_do_dia(App.hoje);
  if (!r.ok) return;
  $("#v-total-hoje").textContent = r.total_fmt;
  $("#v-qtd-hoje").textContent = `${r.qtd} lançamento${r.qtd === 1 ? "" : "s"}`;
  $("#v-lista-hoje").innerHTML = r.itens.map((v) => `<li>
      <span class="hora num">${esc(v.hora)}</span>
      <span class="info"><b class="num">${esc(v.valor_fmt)}</b><br>${esc(titulo(v.pagamento))} · ${esc(titulo(v.vendedor))}</span></li>`).join("")
    || `<li class="vazio" style="display:block">Nenhuma venda hoje ainda.</li>`;
}

// --- venda híbrida: bipar produto baixa o estoque; digitar só o valor continua como sempre ---
async function bipar(codigo) {
  const campo = $("#v-valor");
  const r = await api().bipar(codigo);
  campo.value = "";
  if (!r.ok) {
    interpretarValorVenda();
    feedback("#v-feedback", `${r.erro} (${codigo}). Digite o valor para lançar sem baixar estoque.`, "erro");
    return;
  }
  limparErroVenda();
  const p = r.produto, ja = venda.itens.find((i) => i.codigo === p.codigo);
  if (ja) ja.qtd += 1; else venda.itens.push({ codigo: p.codigo, nome: p.nome, preco: p.preco, qtd: 1 });
  if (p.categoria && App.produtos.includes(p.categoria) && !venda.produto) escolherProduto(p.categoria);
  desenharCesta();
  if (p.preco === null) feedback("#v-feedback", `${p.nome} está sem preço cadastrado: digite o valor total.`, "aviso");
}
function desenharCesta() {
  const box = $("#v-cesta");
  box.classList.toggle("oculto", !venda.itens.length);
  tabela("#v-cesta-lista", { colunas: ["Produto", "Preço (cada)"], linhas: venda.itens.map((i) => [i.nome, i.preco === null ? "sem preço" : "R$ " + i.preco.toFixed(2).replace(".", ",")]) },
    { acoes: (k) => `<input class="num cesta-qtd" data-q="${k}" value="${venda.itens[k].qtd}" aria-label="Quantidade"> <button class="btn btn-p" data-rm="${k}" aria-label="Tirar">${ic("i-lixo")}</button>` });
  interpretarValorVenda();
}
// Soma dos produtos bipados (em centavos) ou null se algum está sem preço / não há itens
function totalCesta() {
  if (!venda.itens.length || venda.itens.some((i) => i.preco === null)) return null;
  return venda.itens.reduce((s, i) => s + Math.round(i.preco * 100) * i.qtd, 0) / 100;
}
const brl = (n) => n.toFixed(2).replace(".", ",");
