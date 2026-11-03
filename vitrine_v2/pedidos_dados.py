"""Pedidos da loja online, lado do sistema da loja.

Os pedidos moram no portão (banco central). Aqui fica uma CÓPIA local (tabela pedidos_online) trazida pela sincronização, para a tela
abrir na hora e funcionar sem internet. Avançar status passa pelo portão (precisa de internet); a baixa definitiva do estoque
acontece quando o pedido chega aqui como 'entregue': um movimento 'venda' com uuid PED-<pedido>-<sku> (repetir não duplica).
"""
import json
import sqlite3
from datetime import datetime, timedelta

# Vendedor reservado da loja online: NÃO está na tabela vendedores (não aparece para escolher, não entra no Desafio) e
# Filial.sem_comissao o inclui (sem comissão). Aparece nos relatórios como uma "vendedora" à parte.
LOJA_ONLINE = "LOJA ONLINE"
COM_VENDA = ("pago", "separando", "pronto_retirada", "saiu_entrega", "entregue")  # dinheiro recebido e pedido de pé
DESFAZ_VENDA = ("cancelado", "reembolsado", "recusado", "expirado")              # dinheiro devolvido / nunca pago

# status do portão -> (rótulo, grupo da tela)
STATUS = {
    "aguardando_pagamento": ("Aguardando pagamento", "novos"), "pago": ("Pago", "pagos"), "separando": ("Separando", "separando"),
    "pronto_retirada": ("Pronto para retirar", "prontos"), "saiu_entrega": ("Saiu para entrega", "entrega"),
    "entregue": ("Entregue", "concluidos"), "expirado": ("Expirado", "problemas"), "recusado": ("Recusado", "problemas"),
    "cancelado": ("Cancelado", "problemas"), "arrependimento": ("Arrependimento", "problemas"), "reembolsado": ("Reembolsado", "problemas"),
}
ABERTOS = ("pago", "separando", "pronto_retirada", "saiu_entrega")  # reserva confirmada, ainda não saiu
GRUPOS = ["novos", "pagos", "separando", "prontos", "entrega", "concluidos", "problemas"]


def preparar(con):
    con.execute("""CREATE TABLE IF NOT EXISTS pedidos_online (
                     id TEXT PRIMARY KEY, filial TEXT NOT NULL, status TEXT NOT NULL, grupo TEXT NOT NULL, seq INTEGER NOT NULL,
                     criado_em TEXT, dados TEXT NOT NULL, aviso INTEGER NOT NULL DEFAULT 0, baixado INTEGER NOT NULL DEFAULT 0)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_online_grupo ON pedidos_online(grupo, seq)")
    con.execute("CREATE TABLE IF NOT EXISTS reservado_online (codigo TEXT PRIMARY KEY, qtd INTEGER NOT NULL)")
    # ligação pedido <-> venda. A chave (pedido + produto + parcela) é única: o pedido repetido (webhook 3x, resincronização)
    # nunca lança a venda duas vezes. venda_id aponta a linha de vendas (apagada junto se o pedido for reembolsado).
    con.execute("CREATE TABLE IF NOT EXISTS vendas_online (chave TEXT PRIMARY KEY, pedido_id TEXT NOT NULL, venda_id INTEGER)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_vendas_online_pedido ON vendas_online(pedido_id)")


def _agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _baixar(con, p):
    """Baixa definitiva: um movimento 'venda' por item, uuid PED-<pedido>-<sku>. Já existe = não faz de novo."""
    avisos = []
    for it in p["itens"]:
        uid = f"PED-{p['id']}-{it['sku']}"
        if con.execute("SELECT 1 FROM movimentos WHERE uuid = ?", (uid,)).fetchone():
            continue
        prod = con.execute("SELECT id FROM produtos WHERE codigo = ?", (it["sku"],)).fetchone()
        if not prod:
            avisos.append(f"pedido {p['id']}: produto {it['sku']} não está cadastrado aqui; baixa não feita")
            continue
        con.execute("INSERT OR IGNORE INTO estoque (produto_id, filial) VALUES (?,?)", (prod[0], p["filial"]))
        con.execute("UPDATE estoque SET quantidade = quantidade - ? WHERE produto_id = ? AND filial = ?", (it["qtd"], prod[0], p["filial"]))
        con.execute("INSERT INTO movimentos (produto_id, filial, tipo, quantidade, data, obs, uuid) VALUES (?,?,?,?,?,?,?)",
                    (prod[0], p["filial"], "venda", -int(it["qtd"]), _agora(), f"pedido online {p['id']}", uid))
    return avisos


def _data_hora_pago(p):
    """Quando o pedido foi pago, no relógio local da loja (o portão guarda em UTC)."""
    try:
        t = datetime.fromisoformat(str(p.get("pago_em") or p["criado_em"]).replace("Z", "+00:00"))
        return t.astimezone().replace(tzinfo=None) if t.tzinfo else t
    except (ValueError, TypeError, KeyError):
        return datetime.now()


def _lancar_venda(con, p):
    """Pedido pago vira linhas em vendas: vendedor LOJA ONLINE, forma de pagamento real, uma linha por tipo de produto
    (e por parcela no crédito 2x/3x, como o PDV faz). Só mercadoria: a taxa de entrega não é venda. Uma vez só por pedido."""
    import dados as d  # import tardio: dados importa este módulo
    if con.execute("SELECT 1 FROM vendas_online WHERE pedido_id = ? LIMIT 1", (p["id"],)).fetchone():
        return
    por_tipo = {}
    for it in p["itens"]:
        r = con.execute("SELECT categoria FROM produtos WHERE codigo = ?", (it["sku"],)).fetchone()
        tipo = "PERFUMARIA" if r and "PERFUM" in (r[0] or "").upper() else "OUTROS"
        por_tipo[tipo] = por_tipo.get(tipo, 0) + int(it["preco_cent"]) * int(it["qtd"])
    forma, n = str(p.get("forma_pagamento") or "pix").lower(), int(p.get("parcelas") or 1)
    n = n if forma == "credito" and n in (1, 2, 3) else 1
    quando = _data_hora_pago(p)
    dia, hora = quando.strftime("%d/%m/%Y"), quando.strftime("%I:%M:%S %p").lstrip("0")
    tem_uid = "uid" in {c[1] for c in con.execute("PRAGMA table_info(vendas)")}
    for tipo in sorted(por_tipo):
        total = por_tipo[tipo] / 100
        if total <= 0:
            continue
        if forma == "credito":
            nome = "CRÉDITO A V." if n == 1 else f"CRÉDITO {n}X"  # vencimentos e rótulos como no PDV (30 dias por parcela)
            parcelas = [(v, nome if n == 1 else f"{nome} ({i}/{n})", (quando + timedelta(days=30 * i)).strftime("%d/%m/%Y"))
                        for i, v in enumerate(d.dividir_parcelas(total, n), start=1)]
        else:
            parcelas = [(total, "DÉBITO" if forma == "debito" else "PIX", dia)]
        for i, (valor, pagto, venc) in enumerate(parcelas, start=1):
            chave = f"ONL-{p['id']}-{tipo[0]}{i}"
            cols, vals = ["valor", "vendedor", "data_venda", "data_vencimento", "horario", "tipo_produto", "tipo_pagamento"],                 [valor, LOJA_ONLINE, dia, venc, hora, tipo, pagto]
            if tem_uid:
                cols.append("uid"), vals.append(chave)
                ja = con.execute("SELECT id FROM vendas WHERE uid = ?", (chave,)).fetchone()
                if ja:  # outro computador da loja já lançou esta venda (veio pela sincronização): só liga ao pedido
                    con.execute("INSERT OR IGNORE INTO vendas_online (chave, pedido_id, venda_id) VALUES (?,?,?)", (chave, p["id"], ja[0]))
                    continue
            cur = con.execute(f"INSERT INTO vendas ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
            con.execute("INSERT INTO vendas_online (chave, pedido_id, venda_id) VALUES (?,?,?)", (chave, p["id"], cur.lastrowid))


def _desfazer_venda(con, pedido_id):
    """Pedido reembolsado/cancelado: a venda dele sai de vendas (o dinheiro voltou ao cliente)."""
    ids = [r[0] for r in con.execute("SELECT venda_id FROM vendas_online WHERE pedido_id = ?", (pedido_id,))]
    for i in ids:
        con.execute("DELETE FROM vendas WHERE id = ?", (i,))
    con.execute("DELETE FROM vendas_online WHERE pedido_id = ?", (pedido_id,))


def recalcular_reservado(con, filial):
    con.execute("DELETE FROM reservado_online")
    marcas = ",".join("?" * len(ABERTOS))
    con.execute(f"""INSERT INTO reservado_online (codigo, qtd)
                    SELECT json_extract(i.value, '$.sku'), SUM(json_extract(i.value, '$.qtd'))
                    FROM pedidos_online po, json_each(po.dados, '$.itens') i
                    WHERE po.filial = ? AND po.status IN ({marcas}) GROUP BY 1""", (filial, *ABERTOS))


def aplicar_pedido(con, filial, p, registrar_erro=None):
    """Guarda/atualiza um pedido vindo do portão. Tudo (cópia, baixa, reservas) numa transação."""
    status = p["status"]
    grupo = STATUS.get(status, ("", "problemas"))[1]
    try:
        con.execute("BEGIN IMMEDIATE")
        antes = con.execute("SELECT status FROM pedidos_online WHERE id = ?", (p["id"],)).fetchone()
        # aviso (som) só quando o pedido PASSA a pago; pedido ainda não pago não toca
        aviso = 1 if status == "pago" and (antes is None or antes[0] != "pago") else 0
        if antes is None:
            con.execute("INSERT INTO pedidos_online (id, filial, status, grupo, seq, criado_em, dados, aviso) VALUES (?,?,?,?,?,?,?,?)",
                        (p["id"], p["filial"], status, grupo, p["seq"], p["criado_em"], json.dumps(p, ensure_ascii=False), aviso))
        else:
            con.execute("UPDATE pedidos_online SET status=?, grupo=?, seq=?, dados=?, aviso=MAX(aviso, ?) WHERE id=?",
                        (status, grupo, p["seq"], json.dumps(p, ensure_ascii=False), aviso, p["id"]))
        if p["filial"] == filial:  # só a loja do pedido lança a venda (e baixa o estoque)
            if status in COM_VENDA:
                _lancar_venda(con, p)
            elif status in DESFAZ_VENDA:
                _desfazer_venda(con, p["id"])
        if status == "entregue" and p["filial"] == filial:
            for msg in _baixar(con, p):
                if registrar_erro:
                    registrar_erro("pedido online", Exception(msg))
            con.execute("UPDATE pedidos_online SET baixado = 1 WHERE id = ?", (p["id"],))
        recalcular_reservado(con, filial)
        con.commit()
    except Exception:
        con.rollback()
        raise


def validar_bairros(lista, ler_valor):
    """Tela de bairros: devolve (lista pronta para o portão em centavos, erro). Nome único, taxa >= 0, até 200 bairros."""
    if not isinstance(lista, list) or len(lista) > 200:
        return None, "Lista de bairros inválida (máximo 200)."
    vistos, saida = set(), []
    for b in lista:
        nome = " ".join(str((b or {}).get("bairro", "")).split())
        if not nome:
            return None, "Há um bairro sem nome. Preencha ou remova a linha."
        if nome.upper() in vistos:
            return None, f"O bairro {nome} aparece duas vezes."
        vistos.add(nome.upper())
        taxa = ler_valor(str(b.get("taxa", "")).strip() or "0")
        if taxa is None or taxa < 0:
            return None, f"A taxa de {nome} é inválida."
        saida.append({"bairro": nome, "taxa_cent": int(round(taxa * 100)), "prazo_txt": str(b.get("prazo", "")).strip()[:80],
                      "ativo": 0 if b.get("ativo") in (0, False) else 1})
    return saida, ""


class PedidosMixin:
    """Leitura local para a tela. Nada aqui espera a rede."""

    def pedidos_listar(self, grupo="", filial=None):
        cont = {g: 0 for g in GRUPOS}
        for g, n in self.con.execute("SELECT grupo, COUNT(*) FROM pedidos_online GROUP BY grupo"):
            cont[g] = n
        linhas = self.con.execute("SELECT dados, aviso, baixado FROM pedidos_online WHERE (?='' OR grupo=?) ORDER BY seq DESC LIMIT 300",
                                  (grupo, grupo)).fetchall()
        itens = []
        for dados, aviso, baixado in linhas:
            p = json.loads(dados)
            p["rotulo"] = STATUS.get(p["status"], (p["status"], ""))[0]
            p["novo"] = bool(aviso)
            p["baixado"] = bool(baixado)
            itens.append(p)
        return {"ok": True, "itens": itens, "contagem": cont}

    def pedidos_resumo(self):
        """Barato (chamado a cada poucos segundos): quantos pagos ainda não vistos e quantos abertos."""
        novos = self.con.execute("SELECT COUNT(*) FROM pedidos_online WHERE aviso = 1").fetchone()[0]
        abertos = self.con.execute("SELECT COUNT(*) FROM pedidos_online WHERE status IN ('pago','separando','pronto_retirada','saiu_entrega')").fetchone()[0]
        ult = self.con.execute("SELECT COALESCE(MAX(seq),0) FROM pedidos_online WHERE aviso = 1").fetchone()[0]
        return {"ok": True, "novos": novos, "abertos": abertos, "ultimo_novo": ult}

    def pedidos_marcar_vistos(self):
        self._exec("UPDATE pedidos_online SET aviso = 0 WHERE aviso = 1", commit=True)
        return {"ok": True}
