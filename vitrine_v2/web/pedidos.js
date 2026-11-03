// =============================================================================
// PEDIDOS ONLINE — lista por situação, passo a passo do pedido, aviso sonoro de pedido novo pago.
// A lista vem do banco local (copia trazida pela sincronização): abre na hora e funciona sem internet.
// Mudar a situação passa pela nuvem (precisa de internet) e a baixa do estoque acontece só em "Entregue".
// =============================================================================
"use strict";

const GRUPOS_PED = [["novos", "Novos (aguardando pagamento)"], ["pagos", "Pagos"], ["separando", "Separando"], ["prontos", "Prontos"],
                    ["entrega", "Em entrega"], ["concluidos", "Concluídos"], ["problemas", "Problemas"]];
const ped = { grupo: "pagos", itens: [], ultimoSom: 0, som: true, ctx: null };
const reais = (c) => "R$ " + (c / 100).toFixed(2).replace(".", ",");
// próximo passo do pedido: [status que vai ser gravado, texto do botão grande]
function proximoPasso(p) {
  if (p.status === "pago") return ["separando", "Começar a separar"];
  if (p.status === "separando") return p.modo === "retirada" ? ["pronto_retirada", "Pronto para retirar"] : ["saiu_entrega", "Saiu para entrega"];
  if (p.status === "pronto_retirada" || p.status === "saiu_entrega") return ["entregue", p.modo === "retirada" ? "Cliente retirou" : "Entregue"];
  return null;
}
const PODE_REEMBOLSAR = ["pago", "separando", "pronto_retirada", "saiu_entrega", "cancelado", "arrependimento"];
const PODE_CANCELAR = ["pago", "separando", "pronto_retirada", "saiu_entrega"];

function tocarAviso() {
  if (!ped.som) return;
  try {
    ped.ctx = ped.ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ped.ctx.state === "suspended") ped.ctx.resume();
    [[880, 0], [1175, 0.18], [880, 0.36], [1175, 0.54]].forEach(([f, t]) => {
      const o = ped.ctx.createOscillator(), g = ped.ctx.createGain();
      o.frequency.value = f; o.connect(g); g.connect(ped.ctx.destination);
      const t0 = ped.ctx.currentTime + t;
      g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(0.35, t0 + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.16);
      o.start(t0); o.stop(t0 + 0.18);
    });
  } catch (e) { /* sem som: o toast e o piscar do menu avisam do mesmo jeito */ }
}

async function checarPedidos() {
  let r;
  try { r = await api().pedidos_resumo(); } catch (e) { return; }
  if (!r || !r.ok) return;
  const selo = $("#pedidos-selo"), nav = $("#nav-pedidos");
  selo.textContent = r.novos || r.abertos;
  selo.classList.toggle("oculto", !(r.novos || r.abertos));
  nav.classList.toggle("piscando", r.novos > 0 && App.telaAtual !== "pedidos");
  window.__pedidos_estado = r;
  if (r.novos > 0 && r.ultimo_novo > ped.ultimoSom) {
    ped.ultimoSom = r.ultimo_novo;
    tocarAviso();
    toast(`🔔 ${r.novos === 1 ? "Novo pedido pago" : r.novos + " pedidos novos pagos"}! Abra "Pedidos online".`, "aviso");
    if (App.telaAtual === "pedidos") carregarPedidos();
  }
}

async function carregarPedidos() {
  const r = await api().pedidos_listar(ped.grupo);
  if (!r.ok) { feedback("#po-feedback", r.erro, "erro"); return; }
  ped.itens = r.itens;
  fichas("#po-grupos", GRUPOS_PED.map(([g, n]) => [g, `${n.split(" (")[0]} ${r.contagem[g] || 0}`]), ped.grupo, (g) => { ped.grupo = g; carregarPedidos(); });
  const dados = {
    colunas: ["Pedido", "Cliente", "Itens", "Total", "Retirada / entrega", "Situação"],
    linhas: r.itens.map((p) => [p.id, p.cliente_nome, p.itens.reduce((a, i) => a + i.qtd, 0), reais(p.total_cent),
      p.modo === "retirada" ? "Retira na " + titulo(p.filial) : "Entrega: " + (p.bairro || ""), p.rotulo + (p.novo ? " · NOVO" : "")]),
    classes: r.itens.map((p) => (p.novo ? "ped-novo" : "")),
  };
  tabela("#po-tabela", dados, {
    vazio: "Nenhum pedido nesta situação.", aoDuploClique: (i) => abrirPedido(r.itens[i]),
    acoes: (i) => `<button class="btn btn-p" data-abrir="${i}">${ic("i-abrir")}Abrir</button>`,
  });
  $("#po-tabela").onclick = (e) => { const b = e.target.closest("[data-abrir]"); if (b) abrirPedido(ped.itens[+b.dataset.abrir]); };
  if (r.itens.some((p) => p.novo)) api().pedidos_vistos().then(checarPedidos); // já viu: o menu para de piscar
}

async function mudarPedido(p, novo, textoOk) {
  const r = await api().pedido_avancar(p.id, novo);
  if (!r.ok) { await avisar("Pedido " + p.id, esc(r.erro), "perigo"); return false; }
  toast("✔️ " + textoOk);
  carregarPedidos(); checarPedidos();
  return true;
}

function abrirPedido(p) {
  const passo = proximoPasso(p);
  const itens = p.itens.map((i) => `<li>${i.qtd} × ${esc(i.nome)} <span class="dica dica-normal">(${esc(i.sku)}) ${reais(i.preco_cent * i.qtd)}</span></li>`).join("");
  const onde = p.modo === "retirada" ? `Retira na loja <b>${esc(titulo(p.filial))}</b>` : `Entrega em <b>${esc(p.bairro || "")}</b>: ${esc(p.endereco || "")} (taxa ${reais(p.taxa_entrega_cent)})`;
  const { modal } = abrirModal(`<h2>${ic("i-presente")}Pedido ${esc(p.id)} · ${esc(p.rotulo)}</h2>
    <div class="alvo">${esc(p.cliente_nome)} · WhatsApp ${esc(p.cliente_whatsapp)}${p.cliente_email ? " · " + esc(p.cliente_email) : ""}<br>${onde}</div>
    <ul class="ped-itens">${itens}</ul>
    <p><b>Total ${reais(p.total_cent)}</b>${p.forma_pagamento ? " · " + ({ pix: "Pix", debito: "Débito", credito: "Crédito " + (p.parcelas || 1) + "x" }[p.forma_pagamento] || "") : ""}${p.baixado ? " · estoque já baixado" : p.status === "entregue" ? "" : " · estoque reservado (baixa ao entregar)"}</p>
    <div class="feedback" id="pd-fb"></div>
    <div class="botoes no-print" style="flex-wrap:wrap">
      <button class="btn" data-r="nao">Fechar (Esc)</button>
      <button class="btn" id="pd-zap">WhatsApp</button><button class="btn" id="pd-print">${ic("i-pdf")}Imprimir lista de separação</button>
      ${PODE_CANCELAR.includes(p.status) ? `<button class="btn" id="pd-cancelar">Cancelar pedido</button>` : ""}
      ${PODE_REEMBOLSAR.includes(p.status) ? `<button class="btn btn-perigo" id="pd-reembolso">Reembolsar</button>` : ""}
      ${passo ? `<button class="btn btn-confirmar ped-passo" data-r="sim">${esc(passo[1])}</button>` : ""}
    </div>`, { aoConfirmar: async () => {
      if (!passo) return;
      $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null;
      await mudarPedido(p, passo[0], passo[1] + ": ok");
    } });
  $("#pd-zap", modal).onclick = () => api().pedido_whatsapp(p.id);
  $("#pd-print", modal).onclick = () => window.print();
  const sair = () => { $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null; };
  const c = $("#pd-cancelar", modal), rb = $("#pd-reembolso", modal);
  if (c) c.onclick = async () => { sair(); if (await confirmar({ titulo: "Cancelar o pedido?", texto: "O estoque reservado volta a ficar livre. O dinheiro só volta ao cliente se você clicar em Reembolsar depois.", sim: "Sim, cancelar", tipo: "perigo", icone: "i-alerta", focoNoNao: true })) mudarPedido(p, "cancelado", "Pedido cancelado."); };
  if (rb) rb.onclick = async () => { sair(); if (await confirmar({ titulo: "Reembolsar o cliente?", texto: `Devolve ${reais(p.total_cent)} pelo Mercado Pago e libera o estoque. Não dá para desfazer.`, sim: "Sim, reembolsar", tipo: "perigo", icone: "i-alerta", focoNoNao: true })) mudarPedido(p, "reembolsado", "Reembolso pedido."); };
}

// --- Bairros de entrega: taxa por bairro que o site cobra. Precisa de internet (a lista mora na nuvem). -------------
function linhaBairro(b = { bairro: "", taxa: "", prazo: "", ativo: true }) {
  return `<tr class="bairro-linha"><td><input class="b-nome" value="${esc(b.bairro)}" placeholder="Bairro" aria-label="Bairro"></td>
    <td><input class="b-taxa num campo-dinheiro" value="${esc(b.taxa)}" placeholder="0,00" inputmode="decimal" aria-label="Taxa de entrega (R$)"></td>
    <td><input class="b-prazo" value="${esc(b.prazo)}" placeholder="Ex.: no mesmo dia" aria-label="Prazo"></td>
    <td class="centro"><input type="checkbox" class="b-ativo" ${b.ativo ? "checked" : ""} aria-label="Ativo no site"></td></tr>`;
}
async function abrirBairros() {
  const r = await api().bairros_listar();
  if (!r.ok) { await avisar("Bairros de entrega", esc(r.erro), "perigo"); return; }
  const { modal } = abrirModal(`<h2>${ic("i-presente")}Bairros de entrega</h2>
    <p class="dica">O site cobra esta taxa de quem escolhe entrega. Para tirar um bairro do site, desmarque <b>Ativo</b> (não some da lista, assim dá para ligar de novo).</p>
    <div class="rolagem rolagem-baixa"><table class="tabela bairros"><thead><tr><th>Bairro</th><th>Taxa (R$)</th><th>Prazo</th><th>Ativo</th></tr></thead>
      <tbody id="b-corpo">${r.bairros.map(linhaBairro).join("") || ""}</tbody></table>
      <p class="vazio ${r.bairros.length ? "oculto" : ""}" id="b-vazio">Nenhum bairro ainda. Clique em "Adicionar bairro".</p></div>
    <div class="feedback" id="b-fb"></div>
    <div class="botoes"><button class="btn" id="b-add">${ic("i-mais")}Adicionar bairro</button><button class="btn" data-r="nao">Fechar (Esc)</button>
      <button class="btn btn-confirmar" data-r="sim">Salvar bairros</button></div>`, {
    aoConfirmar: async () => {
      const bairros = [...modal.querySelectorAll(".bairro-linha")].map((tr) => ({ bairro: tr.querySelector(".b-nome").value, taxa: tr.querySelector(".b-taxa").value,
        prazo: tr.querySelector(".b-prazo").value, ativo: tr.querySelector(".b-ativo").checked }))
        .filter((b) => b.bairro.trim() || b.taxa.trim() || b.prazo.trim());  // linha em branco não conta
      const s = await api().bairros_salvar(bairros);
      if (!s.ok) { feedback("#b-fb", s.erro, "erro"); return; }
      $("#modal-fundo").classList.add("oculto"); fecharModalAtual = null;
      toast(`✔️ ${s.total} bairro(s) salvo(s). O site já usa as taxas novas.`);
    } });
  $("#b-add", modal).onclick = () => {
    $("#b-corpo", modal).insertAdjacentHTML("beforeend", linhaBairro());
    $("#b-vazio", modal).classList.add("oculto");
    [...modal.querySelectorAll(".b-nome")].pop().focus();
  };
}

Telas.pedidos = {
  montar() {
    $("#po-som").onclick = (e) => {
      ped.som = !ped.som;
      e.currentTarget.setAttribute("aria-pressed", ped.som);
      e.currentTarget.textContent = ped.som ? "🔔 Som ligado" : "🔕 Som desligado";
      if (ped.som) tocarAviso();
    };
    $("#po-bairros").onclick = abrirBairros;
    checarPedidos();
    setInterval(checarPedidos, 4000); // só lê o banco local: leve
  },
  abrir() { carregarPedidos(); checarPedidos(); },
};
window.__pedidos = { carregarPedidos, abrirPedido, ped };
