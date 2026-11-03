# =============================================================================
# ESTOQUE (F6) — produtos centrais, estoque por filial, movimentos, mínimo,
# transferência entre filiais, etiqueta Code 128. Regras da branch estoque-fase1
# (estoque.py), agora dentro da Dados (mesmo banco, mesma transação da venda).
# Tudo lê/grava só no SQLite local; a outra filial aparece pelo espelho
# `estoque_outra` (preenchido pela sincronização, só leitura).
# =============================================================================
import json
import re
import sqlite3
import uuid
from datetime import datetime

import pedidos_dados

FILIAIS_CODIGOS = ("jardins", "centro")
# Produtos do catálogo do site (id, nome): o cadastro liga cada produto do sistema a um deles (campo site_id).
SITE_PRODUTOS = [["base", "Base líquida"], ["corretivo", "Corretivo"], ["batom", "Batom"], ["gloss", "Gloss labial"], ["mascara-cilios", "Máscara de cílios"], ["delineador", "Delineador"], ["paleta", "Paleta de sombras"], ["po", "Pó compacto ou solto"], ["blush", "Blush e iluminador"], ["pinceis", "Pincéis e esponjas"], ["limpeza", "Sabonete facial"], ["agua-micelar", "Água micelar"], ["hidratante-facial", "Hidratante facial"], ["serum", "Sérum facial"], ["protetor", "Protetor solar facial"], ["mascara-facial", "Máscara facial"], ["shampoo", "Shampoo"], ["condicionador", "Condicionador"], ["mascara-capilar", "Máscara capilar"], ["creme-pentear", "Creme para pentear"], ["finalizador", "Óleo e finalizador"], ["coloracao", "Coloração"], ["escova", "Escovas e acessórios"], ["perfume-f", "Perfume feminino"], ["perfume-m", "Perfume masculino"], ["body-splash", "Body splash"], ["desodorante", "Desodorante"], ["hidratante-corpo", "Hidratante corporal"], ["sabonete", "Sabonete"], ["oleo-corpo", "Óleo corporal"], ["esfoliante", "Esfoliante"], ["depilacao", "Cera e depilação"], ["esmalte", "Esmalte"], ["base-unha", "Base e fortalecedor"], ["removedor", "Removedor de esmalte"], ["alicate", "Alicates e lixas"], ["kit-pronto", "Kit presente pronto"], ["kit-montado", "Kit do seu jeito"]]
SITE_IDS = {i for i, _ in SITE_PRODUTOS}
# Campos do produto para a loja online (só vai ao site se ativo_site=1, preço > 0 e foto)
CAMPOS_SITE = [("ativo_site", "INTEGER NOT NULL DEFAULT 0"), ("foto", "TEXT"), ("descricao_site", "TEXT"), ("preco_site", "REAL"),
               ("marca", "TEXT"), ("grupo_site", "TEXT"), ("variacao", "TEXT")]


def _agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def ean_valido(cod):
    """EAN-8 / UPC-A(12) / EAN-13 / GTIN-14: confere o dígito verificador."""
    if not re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", cod):
        return False
    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(cod[:-1])))
    return (10 - soma % 10) % 10 == int(cod[-1])


def eh_codigo_de_barras(texto):
    """Texto bipado que parece código (e não um valor em reais): 8 a 14 dígitos ou VT-xxxxxx."""
    t = (texto or "").strip()
    return bool(re.fullmatch(r"\d{8,14}", t) or re.fullmatch(r"VT-\d+", t, re.I))


def _ok(**kw):
    return {"ok": True, **kw}


def _erro(t, **kw):
    return {"ok": False, "erro": t, **kw}


def _preco(txt):
    """'' -> (None, None); inválido -> (None, 'erro'); senão (valor, None)."""
    if not (txt or "").strip():
        return None, None
    from dados import ler_valor_monetario
    v = ler_valor_monetario(txt)
    if v is None or v < 0:
        return None, "Preço inválido."
    return round(v, 2), None


class EstoqueMixin:
    ErroBanco = Exception  # dados.py troca pelo ErroBanco real

    # --- estrutura -------------------------------------------------------------
    def _criar_estoque(self):
        c = self.con
        c.execute('''CREATE TABLE IF NOT EXISTS produtos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT NOT NULL UNIQUE, nome TEXT NOT NULL,
                        categoria TEXT, preco REAL, ativo INTEGER NOT NULL DEFAULT 1)''')
        c.execute('''CREATE TABLE IF NOT EXISTS estoque (
                        produto_id INTEGER NOT NULL REFERENCES produtos(id), filial TEXT NOT NULL,
                        quantidade INTEGER NOT NULL DEFAULT 0, minimo INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (produto_id, filial))''')
        c.execute('''CREATE TABLE IF NOT EXISTS movimentos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, produto_id INTEGER NOT NULL REFERENCES produtos(id),
                        filial TEXT NOT NULL,
                        tipo TEXT NOT NULL CHECK (tipo IN ('entrada','ajuste','contagem','venda','transferencia')),
                        quantidade INTEGER NOT NULL, data TEXT NOT NULL, obs TEXT)''')
        if "uuid" not in {l[1] for l in c.execute("PRAGMA table_info(movimentos)")}:
            c.execute("ALTER TABLE movimentos ADD COLUMN uuid TEXT")  # id global do evento (sincronização)
        if "contado" not in {l[1] for l in c.execute("PRAGMA table_info(movimentos)")}:
            c.execute("ALTER TABLE movimentos ADD COLUMN contado INTEGER")  # contagem: saldo absoluto contado (sincronização)
        if "site_id" not in {l[1] for l in c.execute("PRAGMA table_info(produtos)")}:
            c.execute("ALTER TABLE produtos ADD COLUMN site_id TEXT")  # liga ao produto do catálogo do site
        for col, tipo in CAMPOS_SITE:  # loja online: só acrescenta colunas, nunca recria
            if col not in {l[1] for l in c.execute("PRAGMA table_info(produtos)")}:
                c.execute(f"ALTER TABLE produtos ADD COLUMN {col} {tipo}")
        c.execute("CREATE INDEX IF NOT EXISTS idx_movimentos_produto ON movimentos(produto_id, filial)")
        c.execute('''CREATE TABLE IF NOT EXISTS transferencias (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT NOT NULL UNIQUE, produto_codigo TEXT NOT NULL,
                        produto_nome TEXT, origem TEXT NOT NULL, destino TEXT NOT NULL,
                        quantidade INTEGER NOT NULL CHECK (quantidade > 0),
                        status TEXT NOT NULL DEFAULT 'pedido', pedido_em TEXT, enviada_em TEXT, recebida_em TEXT, obs TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS estoque_outra (
                        filial TEXT NOT NULL, codigo TEXT NOT NULL, nome TEXT, quantidade INTEGER NOT NULL DEFAULT 0,
                        atualizado TEXT, PRIMARY KEY (filial, codigo))''')
        pedidos_dados.preparar(c)
        c.commit()

    @property
    def filial_outra(self):
        outras = [f for f in FILIAIS_CODIGOS if f != self.filial.codigo]
        return outras[0] if len(outras) == 1 else "outra"

    def _tx(self, origem, fn):
        """Roda fn() numa transação; qualquer erro desfaz tudo."""
        try:
            r = fn()
            if isinstance(r, dict) and not r.get("ok", True):
                self.con.rollback()
            else:
                self.con.commit()
            return r
        except sqlite3.Error as e:
            self.registrar_erro(origem, e)
            self.con.rollback()
            raise self.ErroBanco(str(e)) from e
        except Exception:
            self.con.rollback()
            raise

    # --- produtos --------------------------------------------------------------
    def _produto(self, codigo):
        return self._um("SELECT * FROM produtos WHERE codigo = ?", ((codigo or "").strip().upper(),))

    def novo_codigo_interno(self):
        ult = self._um("SELECT MAX(CAST(SUBSTR(codigo, 4) AS INTEGER)) FROM produtos WHERE codigo GLOB 'VT-[0-9]*'")[0] or 0
        return f"VT-{ult + 1:06d}"

    def cadastrar_produto(self, codigo, nome, categoria="", preco_txt=""):
        codigo, nome = (codigo or "").strip().upper(), " ".join((nome or "").split())
        if not nome:
            return _erro("Informe o nome do produto.")
        if re.fullmatch(r"\d+", codigo) and not ean_valido(codigo):
            return _erro("Esse código de barras não é válido (o último dígito não confere). Bipe de novo o produto.")
        if codigo and not re.fullmatch(r"[A-Z0-9._-]{3,30}", codigo):
            return _erro("Código com caracteres inválidos. Use só letras, números, ponto e traço.")
        preco, e = _preco(preco_txt)
        if e:
            return _erro(e)

        def f():
            cod = codigo or self.novo_codigo_interno()
            if self._produto(cod):
                return _erro("Esse código já está cadastrado.")
            cur = self.con.execute("INSERT INTO produtos (codigo, nome, categoria, preco) VALUES (?,?,?,?)",
                                   (cod, nome, (categoria or "").strip().upper() or None, preco))
            return _ok(id=cur.lastrowid, codigo=cod, mensagem=f"✔️ Produto cadastrado: {nome} ({cod})")
        return self._tx("cadastrar_produto", f)

    def editar_produto(self, codigo, nome, categoria, preco_txt, ativo=True, site_id=None, site=None):
        p = self._produto(codigo)
        if not p:
            return _erro("Produto não encontrado.")
        nome = " ".join((nome or "").split())
        if not nome:
            return _erro("Informe o nome do produto.")
        preco, e = _preco(preco_txt)
        if e:
            return _erro(e)
        site_id = (site_id or "").strip() or None
        if site_id and site_id not in SITE_IDS:
            return _erro("Esse produto do site não existe.")
        extra, e = self._campos_site(site)
        if e:
            return _erro(e)
        sets = "".join(f", {k}=?" for k in extra)
        self._exec(f"UPDATE produtos SET nome=?, categoria=?, preco=?, ativo=?, site_id=?{sets} WHERE id=?",
                   (nome, (categoria or "").strip().upper() or None, preco, 1 if ativo else 0, site_id, *extra.values(), p["id"]), commit=True)
        return _ok(mensagem="✔️ Produto atualizado.")

    @staticmethod
    def _campos_site(site):
        """site = dict da tela (ou None = não mexe). Devolve ({coluna: valor}, erro)."""
        if not site:
            return {}, None
        ps, e = _preco(site.get("preco_site"))
        if e:
            return None, "Preço do site inválido."
        txt = lambda k, n: " ".join(str(site.get(k) or "").split())[:n] or None  # noqa: E731
        foto = txt("foto", 300)
        if foto and not re.fullmatch(r"[A-Za-z0-9._-]{1,80}|https?://\S+", foto):
            return None, "Foto: use o nome do arquivo (ex.: batom.webp) ou o endereço https://."
        out = {"ativo_site": 1 if site.get("ativo_site") else 0, "foto": foto, "descricao_site": txt("descricao_site", 300),
               "preco_site": ps, "marca": txt("marca", 60), "grupo_site": txt("grupo_site", 60), "variacao": txt("variacao", 60)}
        if out["ativo_site"] and not (ps or 0) > 0:
            return None, "Para aparecer no site, preencha o preço do site (maior que zero)."
        if out["ativo_site"] and not foto:
            return None, "Para aparecer no site o produto precisa de foto."
        return out, None

    _SQL_PRODUTO = ("SELECT p.*, e.quantidade AS q, e.minimo AS mn, o.quantidade AS oq, o.atualizado AS oat, ro.qtd AS res "
                    "FROM produtos p LEFT JOIN estoque e ON e.produto_id = p.id AND e.filial = ? "
                    "LEFT JOIN estoque_outra o ON o.codigo = p.codigo AND o.filial = ? "
                    "LEFT JOIN reservado_online ro ON ro.codigo = p.codigo ")

    def _dict_produto(self, p):
        q, mn = p["q"] or 0, p["mn"] or 0
        return {"id": p["id"], "codigo": p["codigo"], "nome": p["nome"], "categoria": p["categoria"] or "",
                "preco": p["preco"], "ativo": bool(p["ativo"]), "site_id": p["site_id"], "quantidade": q, "minimo": mn,
                "reservado": p["res"] or 0,  # pedidos online pagos que ainda não saíram (informação; o saldo não muda)
                "site": {k: p[k] for k, _ in CAMPOS_SITE},
                "situacao": self.situacao(q, mn),
                "outra": None if p["oq"] is None else {"filial": self.filial_outra, "quantidade": p["oq"],
                                                       "atualizado": p["oat"]}}

    @staticmethod
    def situacao(q, minimo):
        if minimo > 0 and q < minimo:
            return "ABAIXO DO MÍNIMO"
        return "ZERADO" if q <= 0 else "OK"

    def buscar_codigo(self, codigo):
        """Bipe: produto ativo desse código (uma consulta indexada) ou erro."""
        p = self._um(self._SQL_PRODUTO + "WHERE p.codigo = ?", (self.filial.codigo, self.filial_outra, (codigo or "").strip().upper()))
        if not p or not p["ativo"]:
            return _erro("Código não cadastrado.", codigo=(codigo or "").strip(), nao_cadastrado=True)
        return _ok(produto=self._dict_produto(p))

    def consultar_estoque(self, busca="", so_alerta=False, incluir_inativos=False):
        t = f"%{(busca or '').strip().upper()}%"
        linhas = self._todos(
            self._SQL_PRODUTO + "WHERE (p.ativo=1 OR ?) AND (UPPER(p.codigo) LIKE ? OR UPPER(p.nome) LIKE ?) ORDER BY p.nome LIMIT 2000",
            (self.filial.codigo, self.filial_outra, 1 if incluir_inativos else 0, t, t))
        itens = [self._dict_produto(p) for p in linhas]
        if so_alerta:
            itens = [i for i in itens if i["situacao"] == "ABAIXO DO MÍNIMO"]
        return _ok(itens=itens, outra=self.filial_outra)

    # --- movimentos ------------------------------------------------------------
    def _mov(self, pid, tipo, valor, obs=None, uid=None):
        """Sem commit (o chamador controla a transação). contagem: `valor` é o novo saldo; demais: variação (+/-)."""
        fil = self.filial.codigo
        self.con.execute("INSERT OR IGNORE INTO estoque (produto_id, filial) VALUES (?,?)", (pid, fil))
        atual = self.con.execute("SELECT quantidade FROM estoque WHERE produto_id=? AND filial=?", (pid, fil)).fetchone()[0]
        delta = valor - atual if tipo == "contagem" else valor
        self.con.execute("UPDATE estoque SET quantidade=? WHERE produto_id=? AND filial=?", (atual + delta, pid, fil))
        self.con.execute("INSERT INTO movimentos (produto_id, filial, tipo, quantidade, data, obs, uuid, contado) VALUES (?,?,?,?,?,?,?,?)",
                         (pid, fil, tipo, delta, _agora(), obs, uid or str(uuid.uuid4()), valor if tipo == "contagem" else None))
        return atual + delta

    def movimentar(self, tipo, itens, obs=""):
        """itens = [{codigo, qtd}]. entrada: soma | ajuste: soma (aceita negativo, exige motivo) | contagem: qtd vira o
        saldo. Tudo ou nada."""
        if tipo not in ("entrada", "ajuste", "contagem"):
            return _erro("Tipo de movimento inválido.")
        if not itens:
            return _erro("Nenhum produto na lista.")
        prontos = []
        for it in itens:
            p = self._produto(it.get("codigo"))
            if not p:
                return _erro(f"Código não cadastrado: {it.get('codigo')}")
            try:
                q = int(it.get("qtd"))
            except (TypeError, ValueError):
                return _erro(f"Quantidade inválida para {p['nome']}.")
            if (q < 0 and tipo != "ajuste") or (q == 0 and tipo != "contagem") or abs(q) > 100000:
                return _erro(f"Quantidade inválida para {p['nome']}.")
            prontos.append((p["id"], q))
        if tipo == "ajuste" and not (obs or "").strip():
            return _erro("No ajuste, escreva o motivo (ex.: quebra, perda).")

        def f():
            for pid, q in prontos:
                self._mov(pid, tipo, q, (obs or "").strip() or None)
            return _ok(mensagem=f"✔️ {len(prontos)} produto(s) registrado(s) ({tipo}).")
        return self._tx("movimentar", f)

    def definir_minimo(self, codigo, minimo):
        p = self._produto(codigo)
        if not p:
            return _erro("Produto não encontrado.")
        try:
            m = max(0, int(minimo))
        except (TypeError, ValueError):
            return _erro("Mínimo inválido.")
        self._exec("INSERT OR IGNORE INTO estoque (produto_id, filial) VALUES (?,?)", (p["id"], self.filial.codigo))
        self._exec("UPDATE estoque SET minimo=? WHERE produto_id=? AND filial=?", (m, p["id"], self.filial.codigo), commit=True)
        return _ok(mensagem="✔️ Mínimo salvo.")

    def historico_movimentos(self, codigo, limite=100):
        p = self._produto(codigo)
        if not p:
            return _erro("Produto não encontrado.")
        ls = self._todos("SELECT data, tipo, quantidade, obs FROM movimentos WHERE produto_id=? AND filial=? "
                         "ORDER BY id DESC LIMIT ?", (p["id"], self.filial.codigo, int(limite)))
        return _ok(produto=p["nome"], itens=[dict(l) for l in ls])

    # --- venda híbrida: baixa de estoque na MESMA transação da venda ------------
    def _baixar_itens_venda(self, itens):
        """Chamado por registrar_venda antes do commit. Devolve (avisos, erro)."""
        avisos = []
        for it in itens:
            p = self._produto(it.get("codigo"))
            if not p:
                return None, f"Código não cadastrado: {it.get('codigo')}"
            try:
                q = int(it.get("qtd", 1))
            except (TypeError, ValueError):
                q = 0
            if q < 1 or q > 10000:
                return None, f"Quantidade inválida: {p['nome']}"
            novo = self._mov(p["id"], "venda", -q, "venda")
            if novo < 0:
                avisos.append(f"{p['nome']}: estoque ficou negativo ({novo}). Faça a contagem depois.")
        return avisos, None

    # --- transferência entre filiais ---------------------------------------------
    def pedir_transferencia(self, codigo, qtd, obs=""):
        """Esta filial PEDE à outra. A outra só vê o pedido quando a sincronização o levar."""
        p = self._produto(codigo)
        if not p:
            return _erro("Produto não encontrado.")
        try:
            q = int(qtd)
        except (TypeError, ValueError):
            q = 0
        if q < 1 or q > 10000:
            return _erro("Quantidade inválida.")
        self._exec("INSERT INTO transferencias (uuid, produto_codigo, produto_nome, origem, destino, quantidade, status, "
                   "pedido_em, obs) VALUES (?,?,?,?,?,?, 'pedido', ?, ?)",
                   (str(uuid.uuid4()), p["codigo"], p["nome"], self.filial_outra, self.filial.codigo, q, _agora(),
                    (obs or "").strip() or None), commit=True)
        return _ok(mensagem=f"✔️ Pedido feito: {q} × {p['nome']}, da loja {self.filial_outra}.")

    def listar_transferencias(self, status=""):
        ls = self._todos("SELECT * FROM transferencias WHERE (?='' OR status=?) ORDER BY id DESC LIMIT 300", (status, status))
        out = []
        for l in ls:
            d = dict(l)
            d["sentido"] = "pedi" if l["destino"] == self.filial.codigo else "pediram"
            out.append(d)
        return _ok(itens=out)

    def _transf(self, tid):
        return self._um("SELECT * FROM transferencias WHERE id=?", (tid,))

    def enviar_transferencia(self, tid):
        """Filial de ORIGEM despacha: baixa o estoque daqui."""
        t = self._transf(tid)
        if not t or t["origem"] != self.filial.codigo or t["status"] != "pedido":
            return _erro("Só dá para enviar um pedido feito a esta loja e ainda em aberto.")
        p = self._produto(t["produto_codigo"])
        if not p:
            return _erro("Produto não está cadastrado aqui.")

        def f():
            novo = self._mov(p["id"], "transferencia", -t["quantidade"], f"para {t['destino']}")
            self.con.execute("UPDATE transferencias SET status='enviada', enviada_em=? WHERE id=?", (_agora(), tid))
            return _ok(mensagem="✔️ Enviado. O estoque desta loja foi baixado.", saldo=novo)
        return self._tx("enviar_transferencia", f)

    def receber_transferencia(self, tid):
        """Filial de DESTINO confirma que chegou: entra no estoque daqui."""
        t = self._transf(tid)
        if not t or t["destino"] != self.filial.codigo or t["status"] not in ("pedido", "enviada"):
            return _erro("Só dá para receber uma transferência pedida por esta loja e ainda não recebida.")
        p = self._produto(t["produto_codigo"])
        if not p:
            return _erro("Produto não está cadastrado aqui.")

        def f():
            novo = self._mov(p["id"], "transferencia", t["quantidade"], f"de {t['origem']}")
            self.con.execute("UPDATE transferencias SET status='recebida', recebida_em=? WHERE id=?", (_agora(), tid))
            return _ok(mensagem="✔️ Recebido. O estoque desta loja foi atualizado.", saldo=novo)
        return self._tx("receber_transferencia", f)

    def cancelar_transferencia(self, tid):
        t = self._transf(tid)
        if not t or t["status"] != "pedido":
            return _erro("Só dá para cancelar um pedido ainda em aberto.")
        self._exec("UPDATE transferencias SET status='cancelada' WHERE id=?", (tid,), commit=True)
        return _ok(mensagem="Pedido cancelado.")

    # --- espelho da outra filial e site -------------------------------------------
    def importar_estoque_outra(self, filial, linhas):
        """linhas = [(codigo, nome, quantidade)]. Usado pela sincronização; substitui o espelho dessa filial."""
        def f():
            self.con.execute("DELETE FROM estoque_outra WHERE filial=?", (filial,))
            self.con.executemany("INSERT INTO estoque_outra (filial, codigo, nome, quantidade, atualizado) VALUES (?,?,?,?,?)",
                                 [(filial, c, n, int(q), _agora()) for c, n, q in linhas])
            return len(linhas)
        return self._tx("importar_estoque_outra", f)

    def exportar_json_site(self, caminho):
        """Só disponível sim/não por filial (sem quantidade). Gera o arquivo; não publica."""
        outra = {c: q for c, q in self._todos("SELECT codigo, quantidade FROM estoque_outra WHERE filial=?", (self.filial_outra,))}
        aqui = {c: q for c, q in self._todos("SELECT p.codigo, e.quantidade FROM estoque e JOIN produtos p ON p.id=e.produto_id "
                                             "WHERE e.filial=?", (self.filial.codigo,))}
        prods = [{"codigo": p["codigo"], "nome": p["nome"], "site_id": p["site_id"],
                  "disponivel": {self.filial.codigo: aqui.get(p["codigo"], 0) > 0,
                                 self.filial_outra: outra.get(p["codigo"], 0) > 0}}
                 for p in self._todos("SELECT codigo, nome, site_id FROM produtos WHERE ativo=1 ORDER BY nome")]
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({"atualizado": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "produtos": prods}, f,
                      ensure_ascii=False, indent=1)
        return len(prods)

    # --- etiqueta Code 128 ----------------------------------------------------------
    def etiquetas_pdf(self, caminho, pedidos):
        """pedidos = [{codigo, copias}]. A4, etiquetas 63×30 mm (3 colunas × 9): nome, preço e Code 128."""
        from reportlab.graphics.barcode import code128
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        etiq = []
        for pd in pedidos:
            p = self._produto(pd.get("codigo"))
            if not p:
                return _erro(f"Código não cadastrado: {pd.get('codigo')}")
            etiq += [p] * max(1, min(int(pd.get("copias", 1)), 500))
        if not etiq:
            return _erro("Nenhuma etiqueta para imprimir.")
        _, H = A4
        lw, lh, cols, rows = 63 * mm, 30 * mm, 3, 9
        c = canvas.Canvas(caminho, pagesize=A4)
        for i, p in enumerate(etiq):
            pos = i % (cols * rows)
            if i and pos == 0:
                c.showPage()
            x = 10 * mm + (pos % cols) * lw
            y = H - 15 * mm - (pos // cols + 1) * lh
            c.setFont("Helvetica", 7)
            c.drawString(x + 2 * mm, y + lh - 5 * mm, p["nome"][:38])
            if p["preco"] is not None:
                c.setFont("Helvetica-Bold", 9)
                c.drawString(x + 2 * mm, y + lh - 9 * mm, f"R$ {p['preco']:.2f}".replace(".", ","))
            code128.Code128(p["codigo"], barHeight=12 * mm, barWidth=0.33 * mm, humanReadable=True).drawOn(c, x + 2 * mm, y + 2 * mm)
        c.save()
        return _ok(mensagem=f"Etiquetas salvas em: {caminho}", total=len(etiq))
