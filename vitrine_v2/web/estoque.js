// =============================================================================
// ESTOQUE (F6) — consulta, entrada/contagem/ajuste, produtos + etiqueta, transferência.
// Leitor USB (modo teclado): o campo de bipe fica sempre focado; o leitor "digita" o
// código e aperta Enter. Tudo lê/grava só no banco local (nada espera a internet).
// =============================================================================
"use strict";

const RE_CODIGO = /^(\d{8,14}|VT-\d+)$/i;   // igual a estoque_dados.eh_codigo_de_barras
const est = { itens: [], lanc: [], tipo: "entrada", produtos: [], temp: null };
const fmtPreco = (p) => (p === null || p === undefined ? "—" : "R$ " + Number(p).toFixed(2).replace(".", ","));

Telas.estoque = {
  montar() {
    ligarAbas("estoque", (aba) => { Telas.estoque.abaAberta(aba); });
    $("#ep-categoria").innerHTML = `<option value="">(sem categoria)</option>` + App.produtos.map((p) => `<option value="${esc(p)}">${esc(titulo(p))}</option>`).join("");

    // Consulta
    const busca = $("#e-busca");
    let t = null;
    busca.addEventListener("input", () => { clearTimeout(t); if (!RE_CODIGO.test(busca.value.trim())) t = setTimeout(carregarEstoque, 120); });
    busca.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const txt = busca.value.trim();
      if (!txt) return;
      if (RE_CODIGO.test(txt)) {
        const r = await api().bipar(txt);
        busca.value = "";
        if (!r.ok) { feedback("#e-feedback", `${r.erro} (${txt})`, "erro"); if (r.nao_cadastrado) cadastrarRapido(txt); return; }
        feedback("#e-feedback", "");
        mostrarProduto(r.produto);
      } else carregarEstoque();
    });
    $("#e-so-alerta").onchange = carregarEstoque;
    Exportacoes.estoque = async () => {
      const r = await api().estoque_consultar("", $("#e-so-alerta").checked);
      return { nome: "estoque", titulo: "Estoque", colunas: ["Código", "Produto", "Categoria", "Aqui", "Mínimo", "Situação", "Outra loja"],
               linhas: (r.itens || []).map(linhaEstoque) };
    };

    // Lançar
    $("#el-tipo").onclick = (e) => {
      const b = e.target.closest("[data-valor]");
      if (!b) return;
      est.tipo = b.dataset.valor;
      $$("#el-tipo button").forEach((x) => x.setAttribute("aria-checked", x === b));
      $("#el-obs-campo").classList.toggle("oculto", est.tipo !== "ajuste");
      desenharLancamento();
      $("#el-scan").focus();
    };
    $("#el-scan").addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const txt = e.target.value.trim();
      e.target.value = "";
      if (txt) await bipLancar(txt);
    });
    $("#el-lista").addEventListener("change", (e) => {
      const i = e.target.dataset.q;
      if (i === undefined) return;
      const n = parseInt(e.target.value, 10);
      if (Number.isNaN(n)) { e.target.value = est.lanc[i].qtd; return; }
      est.lanc[i].qtd = n;
    });
    $("#el-lista").addEventListener("click", (e) => {
      const b = e.target.closest("[data-rm]");
      if (b) { est.lanc.splice(+b.dataset.rm, 1); desenharLancamento(); $("#el-scan").focus(); }
    });
    $("#el-gravar").onclick = gravarLancamento;

    // Produtos
    $("#ep-codigo").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("#ep-nome").focus(); } });
    $("#ep-nome").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("#ep-preco").focus(); } });
    $("#ep-preco").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); salvarProduto(); } });
    soDinheiro($("#ep-preco"));
    $("#ep-salvar").onclick = salvarProduto;
    let t2 = null;
    $("#ep-busca").addEventListener("input", () => { clearTimeout(t2); t2 = setTimeout(carregarProdutos, 120); });
    $("#ep-tabela").addEventListener("click", (e) => {
      const b = e.target.closest("[data-acao]");
      if (!b) return;
      const p = est.produtos.find((x) => x.codigo === b.dataset.c);
      if (b.dataset.acao === "editar") editarProduto(p);
      if (b.dataset.acao === "etiqueta") pedirEtiquetas(p);
    });

    // Transferências
    $("#et-scan").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); pedirTransferencia(); } });
    $("#et-pedir").onclick = pedirTransferencia;
    $("#et-tabela").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-t]");
      if (!b) return;
      const r = await api()[b.dataset.t](+b.dataset.id);
      feedback("#et-feedback", r.ok ? r.mensagem : r.erro, r.ok ? "ok" : "erro");
      carregarTransf();
    });
  },

  abrir() {
    if (!abaAtual("estoque")) mostrarAba("estoque", "consulta");
    this.abaAberta(abaAtual("estoque"));
  },

  abaAberta(aba) {
    ({ consulta: carregarEstoque, lancar: desenharLancamento, produtos: carregarProdutos, transf: carregarTransf })[aba]();
    const foco = { consulta: "#e-busca", lancar: "#el-scan", produtos: "#ep-codigo", transf: "#et-scan" }[aba];
    setTimeout(() => $(foco).focus(), 0);
  },

  // Leitor: o código "digitado" fora de qualquer campo vai para o campo de bipe da aba
  tecla(e) {
    const foco = document.activeElement;
    if (e.ctrlKey || e.altKey || e.key.length !== 1 || !/[0-9A-Za-z]/.test(e.key)) return;
    if (foco && ["INPUT", "SELECT", "TEXTAREA"].includes(foco.tagName)) return;
    const aba = abaAtual("estoque");
    const alvo = { consulta: "#e-busca", lancar: "#el-scan", produtos: "#ep-codigo", transf: "#et-scan" }[aba];
    if (alvo) $(alvo).focus();
  },
};

// ---------------------------------------------------------------- consulta
function linhaEstoque(p) {
  const o = p.outra ? `${p.outra.quantidade}` : "—";
  const aqui = p.reservado ? `${p.quantidade} (${p.reservado} reservado online)` : p.quantidade;
  return [p.codigo, p.nome, titulo(p.categoria), aqui, p.minimo || "—", p.situacao, o];
}
async function carregarEstoque() {
  const r = await api().estoque_consultar($("#e-busca").value.trim(), $("#e-so-alerta").checked);
  if (!r.ok) { feedback("#e-feedback", r.erro, "erro"); return; }
  est.itens = r.itens;
  const dados = { colunas: ["Código", "Produto", "Categoria", "Aqui", "Mínimo", "Situação", `Outra loja (${r.outra}) — só leitura`],
                  linhas: r.itens.map(linhaEstoque),
                  classes: r.itens.map((p) => (p.situacao === "OK" ? "" : "alerta")) };
  tabela("#e-tabela", dados, { vazio: "Nenhum produto. Cadastre em 'Produtos e etiquetas'.", aoDuploClique: (i) => mostrarProduto(r.itens[i]) });
  $("#e-contagem").textContent = `${r.itens.length} produto${r.itens.length === 1 ? "" : "s"}`;
}

function mostrarProduto(p) {
  const o = p.outra ? `${p.outra.quantidade} (atualizado ${esc(p.outra.atualizado)})` : "sem informação ainda";
  abrirModal(`<h2>${ic("i-caixote")}${esc(p.nome)}</h2>
    <div class="alvo num">Código ${esc(p.codigo)} · ${esc(fmtPreco(p.preco))}<br>
      Aqui: <b>${p.quantidade}</b>${p.reservado ? ` (${p.reservado} reservado para pedido online)` : ""} · Mínimo: ${p.minimo || "—"} · ${esc(p.situacao)}<br>
      Outra loja (${esc(App.estoque_outra || "")}): ${o}</div>
    <label class="campo">Mínimo para avisar (0 = não avisar)<input id="pm-min" class="num" value="${p.minimo}" autofocus></label>
    <div class="feedback" id="pm-fb"></div>
    <div class="botoes"><button class="btn" id="pm-hist">Ver movimentos</button><button class="btn" id="pm-transf">Pedir à outra loja</button>
    <button class="btn" data-r="nao">Fechar (Esc)</button><button class="btn btn-confirmar" data-r="sim">Salvar mínimo (Enter)</button></div>`, {
    aoConfirmar: async () => {
      const r = await api().estoque_minimo(p.codigo, $("#pm-min").value);
      if (!r.ok) { feedback("#pm-fb", r.erro, "erro"); return; }
      $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null;
      toast(r.mensagem); carregarEstoque();
    },
  });
  $("#pm-hist").onclick = async () => {
    const r = await api().estoque_historico(p.codigo);
    if (!r.ok) return;
    const dados = { colunas: ["Data", "Tipo", "Quantidade", "Obs."], linhas: r.itens.map((m) => [m.data, m.tipo, m.quantidade > 0 ? "+" + m.quantidade : m.quantidade, m.obs || ""]) };
    $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null;
    abrirModal(`<h2>Movimentos: ${esc(r.produto)}</h2><div id="pm-t" class="rolagem" style="max-height:340px"></div><div class="botoes"><button class="btn btn-confirmar" data-r="sim">Fechar</button></div>`);
    tabela("#pm-t", dados, { vazio: "Sem movimentos." });
  };
  $("#pm-transf").onclick = () => {
    $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null;
    mostrarAba("estoque", "transf"); Telas.estoque.abaAberta("transf");
    $("#et-scan").value = p.codigo; $("#et-qtd").focus();
  };
}

// Código bipado que não existe: oferece cadastrar na hora
function cadastrarRapido(codigo, depois) {
  abrirModal(`<h2>${ic("i-alerta")}Código novo: ${esc(codigo)}</h2><p>Esse produto ainda não está cadastrado. Cadastrar agora?</p>
    <label class="campo">Nome do produto<input id="cr-nome" autocomplete="off" autofocus></label>
    <label class="campo">Preço (R$)<input id="cr-preco" class="num campo-dinheiro" placeholder="0,00" autocomplete="off"></label>
    <label class="campo">Categoria<select id="cr-cat"><option value="">(sem categoria)</option>${App.produtos.map((p) => `<option value="${esc(p)}">${esc(titulo(p))}</option>`).join("")}</select></label>
    <div class="feedback" id="cr-fb"></div>
    <div class="botoes"><button class="btn" data-r="nao">Agora não (Esc)</button><button class="btn btn-confirmar" data-r="sim">Cadastrar (Enter)</button></div>`, {
    aoConfirmar: async () => {
      const r = await api().estoque_cadastrar({ codigo, nome: $("#cr-nome").value, preco: $("#cr-preco").value, categoria: $("#cr-cat").value });
      if (!r.ok) { feedback("#cr-fb", r.erro, "erro"); return; }
      $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null;
      toast(r.mensagem);
      if (depois) depois(r.codigo); else carregarEstoque();
    },
  });
  soDinheiro($("#cr-preco"));
}

// ------------------------------------------------------------ entrada / contagem
function desenharLancamento() {
  const contagem = est.tipo === "contagem";
  tabela("#el-lista", { colunas: ["Código", "Produto", contagem ? "Quantidade contada (vira o saldo)" : est.tipo === "ajuste" ? "Quantidade (negativo tira)" : "Quantidade que chegou", "Já tem aqui"],
    linhas: est.lanc.map((l) => [l.codigo, l.nome, l.qtd, l.atual]) },
    { vazio: "Bipe o primeiro produto.", acoes: (i, l) => `<input data-q="${i}" class="num" value="${est.lanc[i].qtd}" style="width:80px" aria-label="Quantidade"> <button class="btn btn-p" data-rm="${i}" aria-label="Tirar da lista">${ic("i-lixo")}</button>` });
}
async function bipLancar(codigo) {
  if (!RE_CODIGO.test(codigo)) { feedback("#el-feedback", `"${codigo}" não parece um código de barras.`, "erro"); return; }
  const r = await api().bipar(codigo);
  if (!r.ok) {
    feedback("#el-feedback", `${r.erro} (${codigo})`, "erro");
    if (r.nao_cadastrado) cadastrarRapido(codigo, (c) => bipLancar(c));
    return;
  }
  feedback("#el-feedback", "");
  const p = r.produto, ja = est.lanc.find((l) => l.codigo === p.codigo);
  if (ja) ja.qtd += 1; else est.lanc.push({ codigo: p.codigo, nome: p.nome, qtd: 1, atual: p.quantidade });
  desenharLancamento();
}
async function gravarLancamento() {
  const r = await api().estoque_movimentar(est.tipo, est.lanc.map((l) => ({ codigo: l.codigo, qtd: l.qtd })), $("#el-obs").value);
  if (!r.ok) { feedback("#el-feedback", r.erro, "erro"); return; }
  est.lanc = []; $("#el-obs").value = "";
  desenharLancamento();
  feedback("#el-feedback", r.mensagem, "ok");
  $("#el-scan").focus();
}

// ------------------------------------------------------------------- produtos
async function salvarProduto() {
  const r = await api().estoque_cadastrar({ codigo: $("#ep-codigo").value, nome: $("#ep-nome").value, categoria: $("#ep-categoria").value, preco: $("#ep-preco").value });
  if (!r.ok) { feedback("#ep-feedback", r.erro, "erro"); return; }
  feedback("#ep-feedback", r.mensagem, "ok");
  ["#ep-codigo", "#ep-nome", "#ep-preco"].forEach((s) => { $(s).value = ""; });
  carregarProdutos();
  $("#ep-codigo").focus();
}
async function carregarProdutos() {
  const r = await api().estoque_consultar($("#ep-busca").value.trim(), false);
  if (!r.ok) return;
  est.produtos = r.itens;
  tabela("#ep-tabela", { colunas: ["Código", "Produto", "Categoria", "Preço"], linhas: r.itens.map((p) => [p.codigo, p.nome, titulo(p.categoria), fmtPreco(p.preco)]) },
    { vazio: "Nenhum produto cadastrado ainda.",
      acoes: (i, l) => `<button class="btn btn-p" data-acao="editar" data-c="${esc(l[0])}">${ic("i-editar")}Editar</button> <button class="btn btn-p" data-acao="etiqueta" data-c="${esc(l[0])}">${ic("i-pdf")}Etiqueta</button>` });
}
function editarProduto(p) {
  const st = p.site || {};
  abrirModal(`<h2>${ic("i-editar")}Editar produto</h2><div class="alvo num">${esc(p.codigo)}</div>
    <label class="campo">Nome<input id="pe-nome" value="${esc(p.nome)}" autocomplete="off" autofocus></label>
    <label class="campo">Preço (R$)<input id="pe-preco" class="num campo-dinheiro" value="${p.preco === null ? "" : String(p.preco.toFixed(2)).replace(".", ",")}" autocomplete="off"></label>
    <label class="campo">Categoria<select id="pe-cat"><option value="">(sem categoria)</option>${App.produtos.map((c) => `<option value="${esc(c)}" ${c === p.categoria ? "selected" : ""}>${esc(titulo(c))}</option>`).join("")}</select></label>
    <label class="campo">Produto no site (para o selo Esgotado)<select id="pe-site"><option value="">(não aparece no site)</option>${(App.site_produtos || []).map(([i, n]) => `<option value="${esc(i)}" ${i === p.site_id ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>
    <label class="campo-inline"><input type="checkbox" id="pe-ativo" ${p.ativo ? "checked" : ""}> Produto ativo (desmarque para parar de vender)</label>
    <p class="rotulo" style="margin-top:12px">Loja online</p>
    <label class="campo-inline"><input type="checkbox" id="pe-asite" ${st.ativo_site ? "checked" : ""}> Vender no site (precisa de preço do site e foto)</label>
    <div class="linha-3col" style="grid-template-columns: 1fr 1fr">
      <label class="campo">Preço no site (R$)<input id="pe-psite" class="num campo-dinheiro" value="${st.preco_site ? String(Number(st.preco_site).toFixed(2)).replace(".", ",") : ""}" autocomplete="off"></label>
      <label class="campo">Foto (arquivo ex.: batom.webp)<input id="pe-foto" value="${esc(st.foto || "")}" autocomplete="off"></label>
      <label class="campo">Marca<input id="pe-marca" value="${esc(st.marca || "")}" autocomplete="off"></label>
      <label class="campo">Variação (tom, tamanho)<input id="pe-var" value="${esc(st.variacao || "")}" autocomplete="off"></label>
    </div>
    <label class="campo">Descrição curta<input id="pe-desc" value="${esc(st.descricao_site || "")}" autocomplete="off"></label>
    <label class="campo">Grupo (liga tons do mesmo produto)<input id="pe-grupo" value="${esc(st.grupo_site || "")}" autocomplete="off"></label>
    <div class="feedback" id="pe-fb"></div>
    <div class="botoes"><button class="btn" data-r="nao">Cancelar (Esc)</button><button class="btn btn-confirmar" data-r="sim">Salvar (Enter)</button></div>`, {
    aoConfirmar: async () => {
      const r = await api().estoque_editar({ codigo: p.codigo, nome: $("#pe-nome").value, preco: $("#pe-preco").value, categoria: $("#pe-cat").value, ativo: $("#pe-ativo").checked, site_id: $("#pe-site").value,
        site: { ativo_site: $("#pe-asite").checked, preco_site: $("#pe-psite").value, foto: $("#pe-foto").value, marca: $("#pe-marca").value,
                variacao: $("#pe-var").value, descricao_site: $("#pe-desc").value, grupo_site: $("#pe-grupo").value } });
      if (!r.ok) { feedback("#pe-fb", r.erro, "erro"); return; }
      $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null;
      toast(r.mensagem); carregarProdutos();
    },
  });
}
function pedirEtiquetas(p) {
  abrirModal(`<h2>${ic("i-pdf")}Etiqueta Code 128</h2><div class="alvo num">${esc(p.codigo)} · ${esc(p.nome)}</div>
    <label class="campo">Quantas etiquetas imprimir?<input id="pt-n" class="num" value="1" autofocus></label>
    <div class="botoes"><button class="btn" data-r="nao">Cancelar (Esc)</button><button class="btn btn-confirmar" data-r="sim">Gerar PDF (Enter)</button></div>`, {
    aoConfirmar: async () => {
      const n = Math.max(1, parseInt($("#pt-n").value, 10) || 1);
      $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null;
      const r = await api().etiquetas([{ codigo: p.codigo, copias: n }]);
      if (r.ok) toast("✔️ " + r.mensagem); else if (!r.cancelado) avisar("Etiquetas", esc(r.erro), "perigo");
    },
  });
}

// ------------------------------------------------------------- transferências
async function pedirTransferencia() {
  const cod = $("#et-scan").value.trim();
  if (!cod) { feedback("#et-feedback", "Bipe o produto que quer pedir.", "erro"); return; }
  const r = await api().transf_pedir(cod, $("#et-qtd").value);
  feedback("#et-feedback", r.ok ? r.mensagem : r.erro, r.ok ? "ok" : "erro");
  if (r.ok) { $("#et-scan").value = ""; $("#et-qtd").value = "1"; carregarTransf(); }
}
async function carregarTransf() {
  const r = await api().transf_listar("");
  if (!r.ok) return;
  const eu = App.filial_codigo;
  tabela("#et-tabela", { colunas: ["Pedido em", "Produto", "Qtd", "De → Para", "Situação"],
    linhas: r.itens.map((t) => [t.pedido_em, `${t.produto_nome} (${t.produto_codigo})`, t.quantidade, `${t.origem} → ${t.destino}`, t.status]) },
    { vazio: "Nenhuma transferência.",
      acoes: (i) => {
        const t = r.itens[i], b = [];
        if (t.status === "pedido" && t.origem === eu) b.push(["transf_enviar", "Enviei"]);
        if ((t.status === "pedido" || t.status === "enviada") && t.destino === eu) b.push(["transf_receber", "Chegou"]);
        if (t.status === "pedido") b.push(["transf_cancelar", "Cancelar"]);
        return b.map(([m, rot]) => `<button class="btn btn-p" data-t="${m}" data-id="${t.id}">${rot}</button>`).join(" ");
      } });
}
