# =============================================================================
# NOVA INTERFACE — CAMADA DE DADOS (todas as regras do sistema atual)
# =============================================================================
# Python puro, sem nenhuma tela. Cada função aqui reproduz uma tela do
# nucleo_pdv.py com AS MESMAS regras de hoje (decisão do usuário em 09/10/2026:
# "só visual, regras de hoje"). O que muda é só a aparência e a usabilidade.
#
# Únicas diferenças, exigidas pelo CLAUDE.md do projeto:
#   * todo valor em dinheiro é lido com ler_valor_monetario ("1.500" = R$ 1.500,
#     e não R$ 1,50 como em texto_para_valor, bug C1 do RELATORIO_REVISAO.md);
#   * valores gravados com 2 casas; nas parcelas, a sobra dos centavos vai para
#     a 1ª (A1);
#   * datas digitadas são gravadas e filtradas sempre como DD/MM/AAAA (A2, A4).
#
# Formato gravado: o mesmo que o sistema atual lê (data DD/MM/AAAA, horário
# "1:34:07 PM", pagamento "CRÉDITO 2X (1/2)"). O schema só recebe o que o
# próprio nucleo_pdv já cria (CREATE TABLE IF NOT EXISTS / ALTER TABLE).
import base64
import calendar
import hashlib
import hmac
import json
import os
import re
import shutil
import socket
import sqlite3
import traceback
import sincro
from estoque_dados import EstoqueMixin, eh_codigo_de_barras  # noqa: F401
from pedidos_dados import PedidosMixin, LOJA_ONLINE
from datetime import datetime, timedelta

PRODUTOS = ["PERFUMARIA", "OUTROS"]
# Ordem do sistema atual (usada nos relatórios e no Dashboard)
PAGAMENTOS = ["DINHEIRO", "PIX", "DÉBITO", "RECEBIMENTO", "CRÉDITO A V.", "CRÉDITO 2X", "CRÉDITO 3X"]
# Ordem dos botões na tela de venda: as mais usadas primeiro (ata do Parlamento, D6)
PAGAMENTOS_BOTOES = [
    ("DINHEIRO", "Dinheiro", ""), ("PIX", "PIX", ""), ("DÉBITO", "Débito", ""),
    ("CRÉDITO A V.", "Crédito", "à vista"), ("CRÉDITO 2X", "Crédito", "2 parcelas"),
    ("CRÉDITO 3X", "Crédito", "3 parcelas"), ("RECEBIMENTO", "Recebimento", ""),
]
TIPOS_DESPESA = ["PRÓ LABORE", "SALÁRIOS", "COMISSÕES", "ALUGUEL", "IMPOSTOS", "MARKETING",
                 "TELEFONE", "INTERNET", "ÁGUA", "LUZ", "IPTU", "TAXA DE LIXO", "PAG. DE EMPRÉSTIMOS",
                 "MAT. DE LIMPEZA E ESCRITÓRIO", "LANCHE", "CONTADOR", "COMPRAS DE PRODUTO",
                 "TAXA DE ENTREGA", "MEDICAMENTOS LOJA", "SISTEMA SINTEGRA", "OUTROS CUSTOS"]
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_CURTOS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
COLS_MESES = ["Nome"] + MESES_CURTOS + ["TOTAL"]

TROCO_INICIAL_PADRAO = 200.0
META_DIARIA_DESAFIO = 5
BONIFICACAO_MAXIMA_DESAFIO = 100.0
PERCENTUAL_COMISSAO = 0.01
TIPO_DESPESA_COMISSAO = "COMISSÕES"

SQL_NOME_VENDEDOR = "TRIM(REPLACE(REPLACE(UPPER(vendedor), '-', ''), '''', ''))"

MSG_ERRO_BANCO = ("Não foi possível acessar o banco de dados agora. Motivos comuns: o arquivo está aberto em "
                  "outro programa, ou o disco está cheio/sem permissão de escrita. Feche outros programas que "
                  "possam estar usando o arquivo e tente novamente.")

# Cores dos gráficos (as mesmas do sistema atual)
CORES_EXTRA = ["#FF69B4", "#1E90FF", "#32CD32", "#9370DB", "#DAA520", "#FF4500", "#00CED1", "#FF1493"]
CORES_VENDEDOR_ORIGINAIS = {"DANIELA": "#FF69B4", "CAMILA": "#1E90FF", "ANA": "#32CD32", "BEATRIZ": "#9370DB",
                            "FERNANDO": "#C0C0C0"}
CORES_PRODUTO = {"PERFUMARIA": "#FF1493", "OUTROS": "#A9A9A9"}
CORES_PAGAMENTO = {"DINHEIRO": "#2E8B57", "PIX": "#00CED1", "DÉBITO": "#4682B4", "RECEBIMENTO": "#DAA520",
                   "CRÉDITO A V.": "#9370DB", "CRÉDITO 2X": "#8A2BE2", "CRÉDITO 3X": "#4B0082"}


# -----------------------------------------------------------------------------
# Funções utilitárias (iguais às do nucleo_pdv.py; os testes conferem)
# -----------------------------------------------------------------------------
def formatar_moeda(valor):
    if not valor:
        return "-"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def valor_dre(valor):
    if not valor:
        return "-"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def moeda_sempre(valor):
    valor = valor or 0.0
    texto = f"R$ {abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"- {texto}" if valor < -0.004 else texto


def numero_br(valor):
    """42.5 -> '42,50' (valor sem 'R$', para as colunas 'Valor (R$)')."""
    if valor is None:
        return ""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def texto_para_data(texto):
    if texto is None:
        return None
    try:
        return datetime.strptime(str(texto).strip(), "%d/%m/%Y")
    except (ValueError, AttributeError):
        return None


def ler_valor_monetario(texto):
    """'150', '150,5', '1.500', '1.500,00', 'R$ 1.500,00'. None se inválido."""
    if texto is None:
        return None
    s = str(texto).strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    negativo = s.startswith("-")
    s = s.lstrip("-")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") == 1 and len(s.split(".")[1]) == 3:
        s = s.replace(".", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        v = round(float(s), 2)
    except ValueError:
        return None
    return -v if negativo else v


def dividir_parcelas(total, parcelas):
    """Parcelas com 2 casas; a sobra dos centavos vai para a 1ª."""
    base = round(total / parcelas, 2)
    valores = [base] * parcelas
    valores[0] = round(total - base * (parcelas - 1), 2)
    return valores


def normalizar_nome_vendedor(nome):
    return (nome or "").upper().replace("-", "").replace("'", "").strip()


def calcular_conclusao_desafio(dias_com_desafio, vendido_no_mes,
                               meta_diaria=META_DIARIA_DESAFIO, bonificacao_maxima=BONIFICACAO_MAXIMA_DESAFIO):
    meta = max(int(dias_com_desafio), 0) * meta_diaria
    vendido = max(int(vendido_no_mes or 0), 0)
    if meta == 0:
        return {"meta": 0, "vendido": vendido, "dias_concluidos": 0, "percentual": 0.0, "bonificacao": 0.0}
    fracao = min(vendido / meta, 1.0)
    return {
        "meta": meta,
        "vendido": vendido,
        "dias_concluidos": min(vendido // meta_diaria, int(dias_com_desafio)),
        "percentual": round(fracao * 100, 1),
        "bonificacao": round(bonificacao_maxima * fracao, 2),
    }


def novo_mapa_meses():
    return {f"{i:02d}": 0.0 for i in range(1, 13)}


def ano_mes_de_data_flexivel(data_texto):
    if not data_texto:
        return None, None
    d = str(data_texto).strip()
    if "/" in d and len(d) >= 10:
        return d[-4:], d[3:5]
    if "-" in d and len(d) >= 10:
        return d[:4], d[5:7]
    return None, None


def hora_para_grafico(h_str):
    """'1:34:07 PM' / '13:34:07' / '13:34' -> '13:00'. None se não der para ler."""
    for formato in ("%I:%M:%S %p", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(h_str or "", formato).strftime("%H:00")
        except ValueError:
            continue
    return None


def _ok(**kw):
    return {"ok": True, **kw}


def _erro(texto, **kw):
    return {"ok": False, "erro": texto, **kw}


class ErroBanco(Exception):
    pass


EstoqueMixin.ErroBanco = ErroBanco


class FilialDiferente(Exception):
    """O banco aberto pertence a outra filial (a filial fica gravada na tabela config)."""


# --- senha em hash (pbkdf2) ----------------------------------------------------
ITER_PBKDF2 = 200_000
SENHA_MINIMA = 6


def hash_senha(senha, iteracoes=ITER_PBKDF2):
    sal = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, iteracoes)
    return f"pbkdf2${iteracoes}${base64.b64encode(sal).decode()}${base64.b64encode(h).decode()}"


def conferir_senha(senha, guardado):
    try:
        _, it, sal, h = guardado.split("$")
        novo = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), base64.b64decode(sal), int(it))
        return hmac.compare_digest(novo, base64.b64decode(h))
    except (ValueError, AttributeError):
        return False


# -----------------------------------------------------------------------------
# Configuração de cada filial (os mesmos parâmetros de iniciar_aplicativo)
# -----------------------------------------------------------------------------
class Filial:
    def __init__(self, codigo, nome_loja, equipe_inicial, participantes_desafio_iniciais=None,
                 minutos_bloqueio_gestao=5,
                 excluidos_desafio=("BEATRIZ", "FERNANDO"), inicio_comissao_automatica="09/2026",
                 sem_comissao=("FERNANDO",), excluidos_bonificacao=("BEATRIZ", "FERNANDO")):
        self.codigo = codigo
        self.nome_loja = nome_loja
        self.equipe_inicial = list(equipe_inicial)
        self.participantes_desafio_iniciais = participantes_desafio_iniciais
        self.minutos_bloqueio_gestao = minutos_bloqueio_gestao
        # LOJA ONLINE nunca recebe comissão nem entra no Desafio/bonificação (decisão 7), qualquer que seja a configuração da filial
        excluidos_desafio = tuple(excluidos_desafio) + (LOJA_ONLINE,)
        sem_comissao = tuple(sem_comissao) + (LOJA_ONLINE,)
        excluidos_bonificacao = tuple(excluidos_bonificacao) + (LOJA_ONLINE,)
        self.excluidos_desafio = {normalizar_nome_vendedor(n) for n in excluidos_desafio}
        self.inicio_comissao_automatica = inicio_comissao_automatica
        self.sem_comissao = [normalizar_nome_vendedor(n) for n in sem_comissao]
        self.sem_comissao_texto = ", ".join(n for n in sem_comissao if n != LOJA_ONLINE)
        self.excluidos_bonificacao = {normalizar_nome_vendedor(n) for n in excluidos_bonificacao}
        mes, ano = (inicio_comissao_automatica.split("/") + ["", ""])[:2]
        self.ano_ini_com = ano
        self.chave_inicio_comissao = f"{ano}{mes.zfill(2)}"

    def comissao_automatica_no_mes(self, ano, mes):
        return f"{ano}{mes}" >= self.chave_inicio_comissao


# -----------------------------------------------------------------------------
# Banco + regras
# -----------------------------------------------------------------------------
class Dados(EstoqueMixin, PedidosMixin):
    def __init__(self, caminho_banco, filial, caminho_log=None):
        self.caminho = caminho_banco
        self.filial = filial
        self.caminho_log = caminho_log or os.path.join(os.path.dirname(caminho_banco), "erros_nova_interface.log")
        self.con = sqlite3.connect(caminho_banco, check_same_thread=False, timeout=10)
        self.con.row_factory = sqlite3.Row
        try:
            self.con.execute("PRAGMA journal_mode=DELETE")  # nunca WAL (incidente do OneDrive, 01/10/2026)
        except sqlite3.Error as e:
            self.registrar_erro("trocar journal_mode para DELETE", e)
        try:
            self.con.execute("PRAGMA foreign_keys=ON")
            self.con.execute("PRAGMA synchronous=FULL")  # pior caso: queda de luz; prefere lento a perder venda
        except sqlite3.Error:
            pass
        self._criar_estrutura()
        self._criar_estoque()
        self._criar_config_e_auditoria()
        sincro.preparar(self.con, self.filial.codigo)  # uid + fila de envio (F4/F5); nunca espera a rede

    def fechar(self):
        try:
            self.con.close()
        except sqlite3.Error:
            pass

    def registrar_erro(self, origem, excecao):
        try:
            with open(self.caminho_log, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now():%d/%m/%Y %H:%M:%S}] Erro em: {origem}\n")
                f.write("".join(traceback.format_exception(type(excecao), excecao, excecao.__traceback__)))
                f.write("-" * 80 + "\n")
        except Exception:
            pass

    # --- mesmo schema do nucleo_pdv.BancoDados._criar_estrutura -----------------
    def _criar_estrutura(self):
        cur = self.con.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS vendedores (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT UNIQUE,
                        status TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS vendas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        valor REAL,
                        vendedor TEXT,
                        data_venda TEXT,
                        data_vencimento TEXT,
                        horario TEXT,
                        tipo_produto TEXT,
                        tipo_pagamento TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS despesas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        descricao TEXT,
                        valor REAL,
                        tipo TEXT,
                        data_despesa TEXT)''')
        cur.execute("CREATE INDEX IF NOT EXISTS idx_vendas_vendedor ON vendas(vendedor)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_vendas_data_venda ON vendas(data_venda)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_vendas_data_vencimento ON vendas(data_vencimento)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_despesas_data ON despesas(data_despesa)")
        cur.execute('''CREATE TABLE IF NOT EXISTS fechamento_caixa (
                        data TEXT PRIMARY KEY,
                        troco_inicial REAL NOT NULL DEFAULT 0,
                        observacao TEXT,
                        fechado_em TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS fechamento_contagem (
                        data TEXT NOT NULL,
                        forma_pagamento TEXT NOT NULL,
                        valor_contado REAL NOT NULL,
                        PRIMARY KEY (data, forma_pagamento))''')
        cur.execute('''CREATE TABLE IF NOT EXISTS movimentos_caixa (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        data TEXT NOT NULL,
                        tipo TEXT NOT NULL CHECK (tipo IN ('SANGRIA', 'SUPRIMENTO')),
                        valor REAL NOT NULL CHECK (valor > 0),
                        descricao TEXT,
                        horario TEXT)''')
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimentos_caixa_data ON movimentos_caixa(data)")
        cur.execute('''CREATE TABLE IF NOT EXISTS desafios (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        data TEXT NOT NULL UNIQUE,
                        produto TEXT NOT NULL,
                        meta_quantidade INTEGER NOT NULL CHECK (meta_quantidade > 0),
                        criado_em TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS bonificacoes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        vendedor TEXT NOT NULL,
                        mes TEXT NOT NULL,
                        ano TEXT NOT NULL,
                        valor REAL NOT NULL CHECK (valor > 0),
                        motivo TEXT,
                        criado_em TEXT)''')
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bonificacoes_periodo ON bonificacoes(ano, mes)")
        cur.execute('''CREATE TABLE IF NOT EXISTS desafio_resultados (
                        desafio_id INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
                        vendedor TEXT NOT NULL,
                        quantidade INTEGER NOT NULL DEFAULT 0 CHECK (quantidade >= 0),
                        PRIMARY KEY (desafio_id, vendedor))''')

        cur.execute("SELECT count(*) FROM vendedores")
        if cur.fetchone()[0] == 0 and self.filial.equipe_inicial:
            cur.executemany("INSERT INTO vendedores (nome, status) VALUES (?, 'Ativo')",
                            [(p,) for p in self.filial.equipe_inicial])
        self.con.commit()

        colunas = {linha[1] for linha in cur.execute("PRAGMA table_info(vendedores)")}
        if "participa_desafio" not in colunas:
            try:
                cur.execute("BEGIN")
                cur.execute("ALTER TABLE vendedores ADD COLUMN participa_desafio INTEGER NOT NULL DEFAULT 0")
                cur.execute("UPDATE vendedores SET participa_desafio = 1")
                self.con.commit()
            except sqlite3.Error:
                self.con.rollback()
                raise

        versao = cur.execute("PRAGMA user_version").fetchone()[0]
        iniciais = self.filial.participantes_desafio_iniciais
        if iniciais is not None and versao < 1:
            marcados = {normalizar_nome_vendedor(n) for n in iniciais}
            ids = [(l[0],) for l in cur.execute("SELECT id, nome FROM vendedores").fetchall()
                   if normalizar_nome_vendedor(l[1]) in marcados]
            try:
                cur.execute("BEGIN")
                cur.execute("UPDATE vendedores SET participa_desafio = 0")
                cur.executemany("UPDATE vendedores SET participa_desafio = 1 WHERE id = ?", ids)
                cur.execute("PRAGMA user_version = 1")
                self.con.commit()
            except sqlite3.Error:
                self.con.rollback()
                raise

    # --- config (chave/valor), auditoria e backup (F1) --------------------------
    TABELAS_AUDITADAS = ("vendas", "despesas", "vendedores", "fechamento_caixa", "fechamento_contagem",
                         "movimentos_caixa", "desafios", "desafio_resultados", "bonificacoes", "produtos", "transferencias")

    def _criar_config_e_auditoria(self):
        cur = self.con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        cur.execute('''CREATE TABLE IF NOT EXISTS auditoria (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT NOT NULL, acao TEXT NOT NULL,
                        tabela TEXT, registro INTEGER, antes TEXT, depois TEXT, detalhe TEXT)''')
        # Gatilhos: todo INSERT/UPDATE/DELETE nas tabelas de negócio deixa rastro, por qualquer caminho
        # (inclusive o nucleo_pdv antigo). Recriados a cada abertura (colunas novas entram). detalhe = quem fez: este
        # computador, ou "sincronizado de <outro computador>" (t105). Na 1ª carga de uma réplica (aplicando=2) não grava.
        cur.execute("CREATE TABLE IF NOT EXISTS sync_estado (aplicando INTEGER NOT NULL)")
        if "quem" not in {l[1] for l in cur.execute("PRAGMA table_info(sync_estado)")}:
            cur.execute("ALTER TABLE sync_estado ADD COLUMN quem TEXT")
        for t in self.TABELAS_AUDITADAS:
            cols = [l[1] for l in cur.execute(f"PRAGMA table_info({t})") if l[1] not in ("uid", "sync_origem", "sync_em", "sync_disp")]
            if not cols:
                continue
            def obj(ref):
                return "json_object(" + ", ".join(f"'{c}', {ref}.\"{c}\"" for c in cols) + ")"
            # UPDATE OF <colunas de negócio>: as colunas da sincronização (uid, sync_*) mudam sem gerar auditoria
            for ev, antes, depois in (("INSERT", "NULL", obj("NEW")), ("UPDATE", obj("OLD"), obj("NEW")),
                                      ("DELETE", obj("OLD"), "NULL")):
                ref = "OLD" if ev == "DELETE" else "NEW"
                of = " OF " + ", ".join(f'"{c}"' for c in cols) if ev == "UPDATE" else ""
                cur.execute(f"DROP TRIGGER IF EXISTS aud_{t}_{ev.lower()}")
                cur.execute(f"CREATE TRIGGER aud_{t}_{ev.lower()} AFTER {ev}{of} ON {t} "
                            f"WHEN COALESCE((SELECT aplicando FROM sync_estado), 0) < 2 BEGIN "
                            f"INSERT INTO auditoria (quando, acao, tabela, registro, antes, depois, detalhe) VALUES "
                            f"(datetime('now','localtime'), '{ev}', '{t}', {ref}.rowid, {antes}, {depois}, "
                            f"(SELECT quem FROM sync_estado)); END")
        self.con.commit()
        gravada = self.cfg_get("filial")
        if gravada is None:
            self.cfg_set("filial", self.filial.codigo)
        elif gravada != self.filial.codigo:
            raise FilialDiferente(f"Este banco é da filial '{gravada}', mas o programa aberto é da filial "
                                  f"'{self.filial.codigo}'.")
        # Nenhuma senha mora no código. Na 1ª vez: variável VITRINE_SENHA_INICIAL (instalação/testes) ou a 1ª senha digitada na tela.
        ini = os.environ.get("VITRINE_SENHA_INICIAL", "")
        if self.cfg_get("senha_gestao_hash") is None and len(ini) >= SENHA_MINIMA:
            self.cfg_set("senha_gestao_hash", hash_senha(ini))

    def cfg_get(self, chave, padrao=None):
        r = self._um("SELECT valor FROM config WHERE chave = ?", (chave,))
        return r[0] if r else padrao

    def cfg_set(self, chave, valor):
        self._exec("INSERT INTO config (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                   (chave, valor), commit=True)

    def auditar(self, acao, detalhe=""):
        self._exec("INSERT INTO auditoria (quando, acao, detalhe) VALUES (datetime('now','localtime'), ?, ?)",
                   (acao, f"{socket.gethostname()}: {detalhe}"), commit=True)

    def auditoria_listar(self, busca="", limite=300):
        sql = "SELECT id, quando, acao, tabela, registro, antes, depois, detalhe FROM auditoria"
        params = []
        b = (busca or "").strip()
        if b:
            sql += " WHERE " + " OR ".join(f"COALESCE({c},'') LIKE ?" for c in ("tabela", "acao", "detalhe", "antes", "depois"))
            params = [f"%{b}%"] * 5
        res = self._todos(sql + " ORDER BY id DESC LIMIT ?", params + [int(limite)])
        return _ok(itens=[dict(r) for r in res])

    def senha_definida(self):
        return self.cfg_get("senha_gestao_hash") is not None

    def verificar_senha(self, senha):
        if not self.senha_definida():  # 1ª migração: a senha digitada agora vira o hash guardado
            if len(senha or "") < SENHA_MINIMA:
                return False
            self.cfg_set("senha_gestao_hash", hash_senha(senha))
            self.auditar("SENHA_DEFINIDA", "primeira senha da Gestão")
            return True
        ok = conferir_senha(senha or "", self.cfg_get("senha_gestao_hash", ""))
        self.auditar("GESTAO_ENTROU" if ok else "GESTAO_SENHA_ERRADA")
        return ok

    def trocar_senha(self, atual, nova, confirmacao):
        if not conferir_senha(atual or "", self.cfg_get("senha_gestao_hash", "")):
            self.auditar("SENHA_TROCA_RECUSADA", "senha atual errada")
            return _erro("A senha atual não confere.")
        if len(nova or "") < SENHA_MINIMA:
            return _erro(f"A senha nova precisa ter pelo menos {SENHA_MINIMA} caracteres.")
        if nova != confirmacao:
            return _erro("A confirmação não é igual à senha nova.")
        if nova == atual:
            return _erro("A senha nova precisa ser diferente da atual.")
        self.cfg_set("senha_gestao_hash", hash_senha(nova))
        self.auditar("SENHA_TROCADA")
        return _ok()

    def backup_antes_de_atualizar(self, manter=5):
        """Cópia conferida (VACUUM INTO) logo antes de trocar a versão do programa. Guarda as `manter` mais novas
        (as outras vão para backup/_rotacionados: nada é apagado). Devolve o caminho."""
        pasta = os.path.join(os.path.dirname(self.caminho), "backup")
        os.makedirs(pasta, exist_ok=True)
        destino = os.path.join(pasta, f"{self.filial.codigo}_antes_atualizar_{datetime.now():%Y-%m-%d_%H%M%S}.db")
        c = sqlite3.connect(self.caminho, timeout=10)
        try:
            c.execute("VACUUM INTO ?", (destino,))
        finally:
            c.close()
        b = sqlite3.connect(destino)
        try:
            ok = b.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            q = "SELECT count(*), coalesce(sum(valor), 0) FROM vendas"
            ok = ok and tuple(b.execute(q).fetchone()) == tuple(self._um(q))
        finally:
            b.close()
        if not ok:
            raise sqlite3.DatabaseError("backup antes de atualizar não conferiu")
        antigos = sorted(f for f in os.listdir(pasta) if "_antes_atualizar_" in f)[:-manter]
        if antigos:
            rot = os.path.join(pasta, "_rotacionados")
            os.makedirs(rot, exist_ok=True)
            for f in antigos:
                os.replace(os.path.join(pasta, f), os.path.join(rot, f))
        return destino

    def backup_diario(self, pasta_extra=None, manter=30, agora=None):
        """VACUUM INTO em <pasta do banco>/backup/<filial>_AAAA-MM-DD.db (1 por dia, confere a cópia). Guarda as
        `manter` mais novas (as outras vão para backup/_rotacionados: nada é apagado) e copia a do dia para
        `pasta_extra`. Devolve {"feito", "arquivo", "avisos"}."""
        agora = agora or datetime.now()
        pasta = os.path.join(os.path.dirname(self.caminho), "backup")
        os.makedirs(pasta, exist_ok=True)
        cod = self.filial.codigo
        destino = os.path.join(pasta, f"{cod}_{agora:%Y-%m-%d}.db")
        avisos, feito = [], False
        if not os.path.exists(destino):
            tmp = destino + f".{agora:%H%M%S}.tmp"
            try:
                c = sqlite3.connect(self.caminho, timeout=10)
                try:
                    c.execute("VACUUM INTO ?", (tmp,))
                finally:
                    c.close()
                b = sqlite3.connect(tmp)
                try:
                    if b.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise sqlite3.DatabaseError("cópia do backup não passou na verificação")
                    consulta = "SELECT count(*), coalesce(sum(valor), 0) FROM vendas"
                    if tuple(b.execute(consulta).fetchone()) != tuple(self._um(consulta)):
                        raise sqlite3.DatabaseError("cópia do backup tem total de vendas diferente")
                finally:
                    b.close()
                os.replace(tmp, destino)
                feito = True
                self.auditar("BACKUP", destino)
            except (sqlite3.Error, OSError) as e:
                self.registrar_erro("backup diário", e)
                avisos.append("Não foi possível fazer o backup de hoje. Avise o suporte.")
                if os.path.exists(tmp):
                    morto = os.path.join(pasta, "_incompletos")
                    os.makedirs(morto, exist_ok=True)
                    os.replace(tmp, os.path.join(morto, os.path.basename(tmp)))
        if os.path.exists(destino):
            if pasta_extra:
                try:
                    os.makedirs(pasta_extra, exist_ok=True)
                    extra = os.path.join(pasta_extra, os.path.basename(destino))
                    if not os.path.exists(extra):
                        shutil.copy2(destino, extra)
                except OSError as e:
                    self.registrar_erro("cópia do backup para a pasta extra", e)
                    avisos.append(f"Não consegui copiar o backup para '{pasta_extra}'. Confira se a pasta existe.")
            padrao = re.compile(rf"^{re.escape(cod)}_\d{{4}}-\d{{2}}-\d{{2}}\.db$")
            antigos = sorted(f for f in os.listdir(pasta) if padrao.match(f))[:-manter]
            if antigos:
                rot = os.path.join(pasta, "_rotacionados")
                os.makedirs(rot, exist_ok=True)
                for f in antigos:
                    os.replace(os.path.join(pasta, f), os.path.join(rot, f))
        return {"feito": feito, "arquivo": destino, "avisos": avisos}

    # --- acesso ao banco (mesmo tratamento de erro do sistema atual) -----------
    def _exec(self, sql, params=(), commit=False):
        try:
            cur = self.con.execute(sql, params)
            if commit:
                self.con.commit()
            return cur
        except sqlite3.Error as e:
            self.registrar_erro(f"SQL -> {sql} | params={params}", e)
            if commit:
                try:
                    self.con.rollback()
                except sqlite3.Error:
                    pass
            raise ErroBanco(str(e)) from e

    def _um(self, sql, params=()):
        return self._exec(sql, params).fetchone()

    def _todos(self, sql, params=()):
        return self._exec(sql, params).fetchall()

    def _transacao(self, comandos):
        try:
            cur = self.con.cursor()
            cur.execute("BEGIN")
            for sql, params in comandos:
                cur.execute(sql, params)
            self.con.commit()
        except sqlite3.Error as e:
            self.registrar_erro("transacao -> " + " | ".join(s for s, _ in comandos), e)
            try:
                self.con.rollback()
            except sqlite3.Error:
                pass
            raise ErroBanco(str(e)) from e

    # =========================================================================
    # Comum
    # =========================================================================
    def vendedores_ativos(self):
        ativos = [r[0] for r in self._todos("SELECT nome FROM vendedores WHERE status = 'Ativo' ORDER BY nome")]
        return ativos if ativos else ["Nenhum Vendedor Ativo"]

    def todos_historico(self):
        todos = set()
        for r in self._todos("SELECT DISTINCT vendedor FROM vendas UNION SELECT nome FROM vendedores WHERE status = 'Ativo'"):
            if r[0]:
                todos.add(normalizar_nome_vendedor(r[0]))
        return sorted(todos)

    def anos_distintos(self, consultas):
        anos = set()
        for sql, params in consultas:
            try:
                linhas = self._todos(sql, params)
            except ErroBanco:
                continue
            for r in linhas:
                if r[0]:
                    ano, _ = ano_mes_de_data_flexivel(r[0])
                    if ano:
                        anos.add(ano)
        return sorted(anos, reverse=True)

    @staticmethod
    def ano_padrao(anos):
        atual = str(datetime.now().year)
        return atual if atual in anos else anos[0]

    @staticmethod
    def _normalizar_data(texto):
        """'' -> ('', None); '1/9/2026' -> ('01/09/2026', None); 'xx' -> (None, erro)."""
        texto = (texto or "").strip()
        if not texto:
            return "", None
        d = texto_para_data(texto)
        if d is None:
            return None, "⚠️ Data inválida! Use DD/MM/AAAA"
        return d.strftime("%d/%m/%Y"), None

    # =========================================================================
    # TELA 1: REGISTRAR VENDA
    # =========================================================================
    def registrar_venda(self, vendedor, produto, pagamento, valor_txt, data_txt, agora=None, itens=None):
        agora = agora or datetime.now()
        vendedor = (vendedor or "").strip()
        valor_txt = (valor_txt or "").strip()
        if (vendedor in ("", "Selecione", "Nenhum Vendedor Ativo") or produto not in PRODUTOS
                or pagamento not in PAGAMENTOS or valor_txt == ""):
            return _erro("⚠️ Preencha todos os campos!")
        if vendedor not in self.vendedores_ativos():
            return _erro("⚠️ Escolha uma vendedora ativa!")
        val_total = ler_valor_monetario(valor_txt)
        data_base = texto_para_data(data_txt)
        if val_total is None or data_base is None:
            return _erro("⚠️ Valor ou Data inválida!")
        if val_total == 0:
            return _erro("⚠️ O valor não pode ser zero!")

        d_venda = data_base.strftime("%d/%m/%Y")
        h_venda = agora.strftime("%I:%M:%S %p").lstrip("0")
        if pagamento in ("DINHEIRO", "RECEBIMENTO", "PIX", "DÉBITO"):
            linhas = [(val_total, vendedor, d_venda, d_venda, h_venda, produto, pagamento)]
        elif pagamento == "CRÉDITO A V.":
            d_venc = (data_base + timedelta(days=30)).strftime("%d/%m/%Y")
            linhas = [(val_total, vendedor, d_venda, d_venc, h_venda, produto, pagamento)]
        else:
            n = 2 if pagamento == "CRÉDITO 2X" else 3
            linhas = [(v, vendedor, d_venda, (data_base + timedelta(days=30 * i)).strftime("%d/%m/%Y"), h_venda,
                       produto, f"{pagamento} ({i}/{n})")
                      for i, v in enumerate(dividir_parcelas(val_total, n), start=1)]
        avisos_estoque = []
        try:
            self.con.executemany(
                "INSERT INTO vendas (valor, vendedor, data_venda, data_vencimento, horario, tipo_produto, tipo_pagamento) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", linhas)
            if itens:  # venda híbrida: produtos bipados baixam o estoque na MESMA transação da venda
                avisos_estoque, erro_itens = self._baixar_itens_venda(itens)
                if erro_itens:
                    self.con.rollback()
                    return _erro("⚠️ " + erro_itens)
            self.con.commit()
        except sqlite3.Error as e:
            self.registrar_erro("registrar_venda", e)
            try:
                self.con.rollback()
            except sqlite3.Error:
                pass
            raise ErroBanco(str(e)) from e
        return _ok(mensagem="✔️ Venda registrada com sucesso!",
                   venda={"valor_fmt": moeda_sempre(val_total), "vendedor": vendedor, "produto": produto,
                          "pagamento": pagamento, "data": d_venda, "hora": agora.strftime("%H:%M"),
                          "parcelas": len(linhas)}, avisos_estoque=avisos_estoque)

    def vendas_do_dia(self, data):
        """Painel 'Vendas de hoje' da tela de venda (só leitura)."""
        linhas = self._todos("SELECT id, horario, valor, tipo_pagamento, vendedor, tipo_produto FROM vendas "
                             "WHERE data_venda = ? ORDER BY id DESC", (data,))
        total = round(sum((l["valor"] or 0.0) for l in linhas), 2)
        itens = []
        for l in linhas[:40]:
            hora = ""
            for formato in ("%I:%M:%S %p", "%H:%M:%S", "%H:%M"):
                try:
                    hora = datetime.strptime(l["horario"] or "", formato).strftime("%H:%M")
                    break
                except ValueError:
                    continue
            itens.append({"id": l["id"], "hora": hora, "valor_fmt": moeda_sempre(l["valor"]),
                          "pagamento": l["tipo_pagamento"] or "", "vendedor": normalizar_nome_vendedor(l["vendedor"]),
                          "produto": l["tipo_produto"] or ""})
        return _ok(data=data, itens=itens, qtd=len(linhas), total_fmt=moeda_sempre(total))

    # =========================================================================
    # TELA 2: HISTÓRICO DE VENDAS
    # =========================================================================
    COLUNAS_HISTORICO = ["ID", "Vendedor", "Produto", "Valor (R$)", "Forma Pagamento", "Horário", "Vendido em",
                         "Vencimento"]

    def historico_vendas(self, vendedor="Todos", ordem="Mais Recentes", data=""):
        data, erro = self._normalizar_data(data)
        if erro:
            return _erro(erro)
        dir_sql = "DESC" if ordem == "Mais Recentes" else "ASC"
        query = ("SELECT id, vendedor, tipo_produto, valor, tipo_pagamento, horario, data_venda, data_vencimento "
                 "FROM vendas WHERE 1=1")
        params = []
        if vendedor != "Todos":
            query += f" AND {SQL_NOME_VENDEDOR} = ?"
            params.append(vendedor)
        if data:
            query += " AND data_venda = ?"
            params.append(data)
        query += (f" ORDER BY substr(data_venda, 7, 4) {dir_sql}, substr(data_venda, 4, 2) {dir_sql}, "
                  f"substr(data_venda, 1, 2) {dir_sql}, id {dir_sql} LIMIT 1000")
        res = self._todos(query, params)
        linhas = [[l[0], normalizar_nome_vendedor(l[1]) or l[1], l[2], numero_br(l[3]), l[4], l[5], l[6], l[7]]
                  for l in res]
        aviso = " (mostrando as 1.000 mais recentes)" if len(res) >= 1000 else ""
        return _ok(colunas=self.COLUNAS_HISTORICO, linhas=linhas, data=data,
                   contagem=f"{len(res)} venda(s) encontrada(s){aviso}")

    def obter_venda(self, id_venda):
        r = self._um("SELECT id, vendedor, tipo_produto, valor, tipo_pagamento, horario, data_venda FROM vendas "
                     "WHERE id = ?", (int(id_venda),))
        if r is None:
            return _erro("Essa venda não existe mais.")
        return _ok(id=r["id"], vendedor=normalizar_nome_vendedor(r["vendedor"]) or r["vendedor"],
                   produto=r["tipo_produto"], valor=numero_br(r["valor"]), pagamento=r["tipo_pagamento"],
                   horario=r["horario"], data=r["data_venda"], vendedores=self.todos_historico())

    def editar_venda(self, id_venda, vendedor, produto, pagamento, valor_txt):
        """Mesmas regras de hoje: vendedor, produto, pagamento e valor da LINHA escolhida."""
        atual = self._um("SELECT tipo_pagamento, tipo_produto FROM vendas WHERE id = ?", (int(id_venda),))
        if atual is None:
            return _erro("Essa venda não existe mais.")
        novo_valor = ler_valor_monetario(valor_txt)
        if novo_valor is None:
            return _erro("Valor inválido!")
        if novo_valor == 0:
            return _erro("O valor não pode ser zero!")
        if pagamento not in PAGAMENTOS and pagamento != atual["tipo_pagamento"]:
            return _erro("Forma de pagamento inválida!")
        if produto not in PRODUTOS and produto != atual["tipo_produto"]:
            return _erro("Produto inválido!")
        if not (vendedor or "").strip():
            return _erro("Escolha o vendedor!")
        self._exec("UPDATE vendas SET vendedor = ?, tipo_produto = ?, tipo_pagamento = ?, valor = ? WHERE id = ?",
                   (vendedor, produto, pagamento, novo_valor, int(id_venda)), commit=True)
        return _ok()

    def excluir_venda(self, id_venda):
        self._exec("DELETE FROM vendas WHERE id = ?", (int(id_venda),), commit=True)
        return _ok()

    # =========================================================================
    # TELA 4: FECHAMENTO DE CAIXA
    # =========================================================================
    @staticmethod
    def texto_diferenca(dif):
        if abs(dif) < 0.005:
            return "OK", "ok"
        if dif < 0:
            return f"Falta {moeda_sempre(-dif)}", "falta"
        return f"Sobra {moeda_sempre(dif)}", "sobra"

    def online_do_dia(self, data):
        """Vendas da loja online no dia (por data da venda), separadas das do balcão. Pix/cartão não passam pela gaveta."""
        linhas = self._todos("SELECT CASE WHEN tipo_pagamento LIKE 'CRÉDITO%' THEN 'CRÉDITO' ELSE UPPER(tipo_pagamento) END AS forma, "
                             "SUM(valor) AS total FROM vendas WHERE vendedor = ? AND data_venda = ? GROUP BY 1 ORDER BY 1", (LOJA_ONLINE, data))
        pedidos = [r[0] for r in self._todos("SELECT DISTINCT vo.pedido_id FROM vendas_online vo JOIN vendas v ON v.id = vo.venda_id "
                                             "WHERE v.data_venda = ?", (data,))]
        taxa = 0
        for pid in pedidos:
            r = self._um("SELECT dados FROM pedidos_online WHERE id = ?", (pid,))
            taxa += int(json.loads(r[0]).get("taxa_entrega_cent") or 0) if r else 0
        total = round(sum((l["total"] or 0.0) for l in linhas), 2)
        return {"qtd": len(pedidos), "total": total, "total_fmt": moeda_sempre(total), "taxa_fmt": moeda_sempre(taxa / 100),
                "formas": [[l["forma"], moeda_sempre(l["total"])] for l in linhas]}

    def carregar_fechamento(self, data_txt):
        data, erro = self._normalizar_data(data_txt)
        if erro or not data:
            return _erro(erro or "⚠️ Data inválida! Use DD/MM/AAAA")
        din = self._um("SELECT COALESCE(SUM(valor), 0), COUNT(*) FROM vendas "
                       "WHERE data_venda = ? AND UPPER(TRIM(tipo_pagamento)) = 'DINHEIRO'", (data,))
        fech = self._um("SELECT troco_inicial, observacao, fechado_em FROM fechamento_caixa WHERE data = ?", (data,))
        contado = self._um("SELECT valor_contado FROM fechamento_contagem WHERE data = ? AND forma_pagamento = 'DINHEIRO'",
                           (data,))
        movs = self._todos("SELECT id, horario, tipo, valor, descricao FROM movimentos_caixa WHERE data = ? ORDER BY id",
                           (data,))
        troco = (fech["troco_inicial"] or 0.0) if fech else TROCO_INICIAL_PADRAO
        return _ok(
            data=data, dinheiro=din[0] or 0.0, qtd_dinheiro=din[1] or 0, online=self.online_do_dia(data),
            suprimento=sum(m["valor"] for m in movs if m["tipo"] == "SUPRIMENTO"),
            sangria=sum(m["valor"] for m in movs if m["tipo"] == "SANGRIA"),
            troco_txt=f"{troco:.2f}".replace(".", ","),
            observacao=(fech["observacao"] or "") if fech else "",
            contado_txt=f"{contado['valor_contado']:.2f}".replace(".", ",") if contado is not None else "",
            fechado_em=fech["fechado_em"] if fech else None,
            movimentos=[{"id": m["id"], "hora": m["horario"] or "", "tipo": m["tipo"].title(),
                         "sinal": "+" if m["tipo"] == "SUPRIMENTO" else "−",
                         "valor_fmt": f"{'+' if m['tipo'] == 'SUPRIMENTO' else '−'} {moeda_sempre(m['valor'])}",
                         "motivo": m["descricao"] or "—"} for m in movs])

    def calcular_caixa(self, dinheiro, qtd_dinheiro, suprimento, sangria, troco_txt, contado_txt):
        """Recalcula esperado e diferença a partir do que está digitado (sem ir ao banco)."""
        troco = ler_valor_monetario(troco_txt) or 0.0
        esperado = troco + (dinheiro or 0.0) + (suprimento or 0.0) - (sangria or 0.0)
        r = {"troco": moeda_sempre(troco), "dinheiro": moeda_sempre(dinheiro),
             "rotulo_dinheiro": f"+ Vendas em dinheiro ({qtd_dinheiro or 0})",
             "suprimento": moeda_sempre(suprimento), "sangria": moeda_sempre(sangria),
             "esperado": moeda_sempre(esperado)}
        contado_txt = (contado_txt or "").strip()
        if contado_txt == "":
            r.update(diferenca="—", situacao="vazio")
        else:
            contado = ler_valor_monetario(contado_txt)
            if contado is None:
                r.update(diferenca="valor inválido", situacao="invalido")
            else:
                txt, sit = self.texto_diferenca(contado - esperado)
                r.update(diferenca=txt, situacao=sit, contado=moeda_sempre(contado))
        return _ok(**r)

    def adicionar_movimento(self, data_txt, tipo, valor_txt, motivo, agora=None):
        data, erro = self._normalizar_data(data_txt)
        if erro or not data:
            return _erro(erro or "⚠️ Data inválida! Use DD/MM/AAAA")
        if tipo not in ("SANGRIA", "SUPRIMENTO"):
            return _erro("Tipo inválido")
        valor = ler_valor_monetario(valor_txt)
        if valor is None or valor <= 0:
            return _erro("⚠️ Digite um valor maior que zero!")
        self._exec("INSERT INTO movimentos_caixa (data, tipo, valor, descricao, horario) VALUES (?, ?, ?, ?, ?)",
                   (data, tipo, valor, (motivo or "").strip(), (agora or datetime.now()).strftime("%H:%M")),
                   commit=True)
        return _ok(mensagem=f"✔️ {tipo.title()} de {moeda_sempre(valor)} registrada")

    def remover_movimento(self, id_mov):
        self._exec("DELETE FROM movimentos_caixa WHERE id = ?", (int(id_mov),), commit=True)
        return _ok()

    def salvar_fechamento(self, data_txt, troco_txt, contado_txt, observacao, confirmou_vazio=False):
        data, erro = self._normalizar_data(data_txt)
        if erro or not data:
            return _erro(erro or "⚠️ Data inválida! Use DD/MM/AAAA")
        troco_txt = (troco_txt or "").strip()
        troco = ler_valor_monetario(troco_txt) if troco_txt else 0.0
        if troco is None or troco < 0:
            return _erro("⚠️ Troco inicial inválido!")
        contado_txt = (contado_txt or "").strip()
        contado = ler_valor_monetario(contado_txt) if contado_txt else None
        if contado_txt and (contado is None or contado < 0):
            return _erro("⚠️ Valor contado inválido!")
        if contado is None and not confirmou_vazio:
            return _erro("", confirmar="O valor \"Contado na gaveta\" está vazio.\nSalvar o fechamento mesmo assim?")
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        comandos = [
            ("INSERT INTO fechamento_caixa (data, troco_inicial, observacao, fechado_em) VALUES (?, ?, ?, ?) "
             "ON CONFLICT(data) DO UPDATE SET troco_inicial = excluded.troco_inicial, "
             "observacao = excluded.observacao, fechado_em = excluded.fechado_em",
             (data, troco, (observacao or "").strip(), agora)),
            ("DELETE FROM fechamento_contagem WHERE data = ?", (data,)),
        ]
        if contado is not None:
            comandos.append(("INSERT INTO fechamento_contagem (data, forma_pagamento, valor_contado) "
                             "VALUES (?, 'DINHEIRO', ?)", (data, contado)))
        self._transacao(comandos)
        return _ok(fechado_em=agora, mensagem="✔️ Fechamento salvo!")

    def exportacao_fechamento(self, data_txt, troco_txt, contado_txt, observacao):
        """As mesmas linhas que o sistema atual exporta (Item / Valor)."""
        f = self.carregar_fechamento(data_txt)
        if not f["ok"]:
            return f
        c = self.calcular_caixa(f["dinheiro"], f["qtd_dinheiro"], f["suprimento"], f["sangria"], troco_txt, contado_txt)
        contado_txt = (contado_txt or "").strip()
        linhas = [["Troco inicial", c["troco"]], [c["rotulo_dinheiro"], c["dinheiro"]],
                  ["+ Suprimentos", c["suprimento"]], ["− Sangrias", c["sangria"]],
                  ["= Esperado na gaveta", c["esperado"]],
                  ["Contado na gaveta", moeda_sempre(ler_valor_monetario(contado_txt)) if contado_txt else "—"],
                  ["Diferença", c["diferenca"]]]
        for m in f["movimentos"]:
            linhas.append([f"{m['tipo']} às {m['hora']}", m["valor_fmt"]])
        o = f["online"]
        if o["qtd"]:  # separado do balcão: não entra na conta da gaveta
            linhas.append([f"Vendas online ({o['qtd']} pedido(s), fora da gaveta)", o["total_fmt"]])
            linhas += [[f"  online {forma.title()}", val] for forma, val in o["formas"]]
            linhas.append(["  taxas de entrega recebidas (não são venda)", o["taxa_fmt"]])
        if (observacao or "").strip():
            linhas.append(["Observação", observacao.strip()])
        return _ok(colunas=["Item", "Valor"], linhas=linhas, nome=f"fechamento_caixa_{f['data'].replace('/', '-')}",
                   titulo=f"Fechamento de Caixa - {f['data']}", titulo_excel="Fechamento de Caixa")

    def dados_graficos_dia(self, data):
        vendas_dia = self._todos("SELECT horario, valor FROM vendas WHERE data_venda = ?", (data,))
        ranking = self._todos(f"SELECT {SQL_NOME_VENDEDOR}, SUM(valor) FROM vendas WHERE data_venda = ? "
                              "GROUP BY 1 ORDER BY 2 DESC", (data,))
        horas = {f"{h:02d}:00": 0.0 for h in range(6, 21)}
        for h_str, val in vendas_dia:
            h = hora_para_grafico(h_str)
            if h:
                horas[h] = horas.get(h, 0.0) + (val or 0.0)
        return horas, [((r[0] or "SEM NOME"), r[1] or 0.0) for r in ranking]

    # --- Histórico de Fechamentos ---------------------------------------------
    COLUNAS_HIST_FECH = ["Data", "Troco", "Vendas dinheiro", "Suprimentos", "Sangrias", "Motivos das sangrias",
                         "Esperado", "Contado", "Diferença", "Fechado em", "Observação"]

    def anos_fechamentos(self):
        anos = self.anos_distintos([("SELECT DISTINCT data FROM fechamento_caixa", ())])
        atual = str(datetime.now().year)
        if atual not in anos:
            anos = sorted(anos + [atual], reverse=True)
        return anos

    def historico_fechamentos(self, mes_nome, ano):
        mes = f"{MESES.index(mes_nome) + 1:02d}"
        filtro = "substr({c}, 4, 2) = ? AND substr({c}, 7, 4) = ?"
        fechamentos = self._todos("SELECT data, troco_inicial, observacao, fechado_em FROM fechamento_caixa WHERE "
                                  + filtro.format(c="data") + " ORDER BY substr(data, 1, 2)", (mes, ano))
        contados = {r[0]: r[1] for r in self._todos(
            "SELECT data, valor_contado FROM fechamento_contagem WHERE forma_pagamento = 'DINHEIRO' AND "
            + filtro.format(c="data"), (mes, ano))}
        dinheiro = {r[0]: r[1] for r in self._todos(
            "SELECT data_venda, SUM(valor) FROM vendas WHERE UPPER(TRIM(tipo_pagamento)) = 'DINHEIRO' AND "
            + filtro.format(c="data_venda") + " GROUP BY data_venda", (mes, ano))}
        movs = {}
        for r in self._todos("SELECT data, tipo, SUM(valor) FROM movimentos_caixa WHERE " + filtro.format(c="data")
                             + " GROUP BY data, tipo", (mes, ano)):
            movs[(r[0], r[1])] = r[2]
        motivos = {}
        for r in self._todos("SELECT data, valor, descricao FROM movimentos_caixa WHERE tipo = 'SANGRIA' AND "
                             + filtro.format(c="data") + " ORDER BY id", (mes, ano)):
            motivos.setdefault(r[0], []).append(f"{(r[2] or '').strip() or 'sem motivo'} ({moeda_sempre(r[1])})")

        linhas, classes = [], []
        soma_dif, dias_com_dif = 0.0, 0
        for f in fechamentos:
            d = f["data"]
            troco = f["troco_inicial"] or 0.0
            din = dinheiro.get(d, 0.0) or 0.0
            sup = movs.get((d, "SUPRIMENTO"), 0.0)
            san = movs.get((d, "SANGRIA"), 0.0)
            esperado = troco + din + sup - san
            contado = contados.get(d)
            classe = ""
            if contado is None:
                txt_dif = "não contado"
            else:
                dif = contado - esperado
                txt_dif, _ = self.texto_diferenca(dif)
                soma_dif += dif
                if abs(dif) >= 0.005:
                    dias_com_dif += 1
                    classe = "falta" if dif < 0 else "sobra"
            linhas.append([d, moeda_sempre(troco), moeda_sempre(din), moeda_sempre(sup), moeda_sempre(san),
                           "; ".join(motivos.get(d, [])), moeda_sempre(esperado),
                           moeda_sempre(contado) if contado is not None else "—", txt_dif, f["fechado_em"] or "",
                           f["observacao"] or ""])
            classes.append(classe)
        if fechamentos:
            txt_total, _ = self.texto_diferenca(soma_dif)
            linhas.append(["TOTAL", "", "", "", "", "", "", "", txt_total, "", ""])
            classes.append("total")
        resumo = (f"{len(fechamentos)} dia(s) fechado(s) · {dias_com_dif} com diferença" if fechamentos
                  else "Nenhum fechamento salvo neste mês.")
        return _ok(colunas=self.COLUNAS_HIST_FECH, linhas=linhas, classes=classes, resumo=resumo,
                   nome=f"historico_fechamentos_{mes_nome}_{ano}", titulo=f"Histórico de Fechamentos - {mes_nome}/{ano}",
                   titulo_excel="Histórico de Fechamentos")

    # --- Relatório Diário -------------------------------------------------------
    def relatorio_diario(self, data_txt, produto, pagamento):
        d, erro = self._normalizar_data(data_txt)
        if erro or not d:
            return _erro(erro or "⚠️ Data inválida! Use DD/MM/AAAA")
        t, p = produto, pagamento

        def b_val(col_d):
            vt = (self._um(f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ?", (d,))[0]) or 0.0
            vtp = (self._um(f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ? AND UPPER(tipo_produto) = ?", (d, t))[0]) or 0.0
            if "CRÉDITO" in p:
                vpag = (self._um(f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ? AND UPPER(tipo_pagamento) LIKE ?",
                                 (d, p + "%"))[0]) or 0.0
                vambos = (self._um(f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ? AND UPPER(tipo_produto) = ? "
                                   "AND UPPER(tipo_pagamento) LIKE ?", (d, t, p + "%"))[0]) or 0.0
            else:
                vpag = (self._um(f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ? AND UPPER(tipo_pagamento) = ?",
                                 (d, p))[0]) or 0.0
                vambos = (self._um(f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ? AND UPPER(tipo_produto) = ? "
                                   "AND UPPER(tipo_pagamento) = ?", (d, t, p))[0]) or 0.0
            return vt, vtp, vpag, vambos

        venda, recebido = b_val("data_venda"), b_val("data_vencimento")

        if "CRÉDITO" in p:
            cond, params = "UPPER(tipo_pagamento) LIKE ?", (d, t, p + "%")
        else:
            cond, params = "UPPER(tipo_pagamento) = ?", (d, t, p)
        vendas_dia = self._todos(f"SELECT horario, valor FROM vendas WHERE data_venda = ? AND UPPER(tipo_produto) = ? "
                                 f"AND {cond}", params)
        vendas_vend = self._todos(f"SELECT {SQL_NOME_VENDEDOR}, SUM(valor) FROM vendas WHERE data_venda = ? "
                                  f"AND UPPER(tipo_produto) = ? AND {cond} GROUP BY 1 ORDER BY 2 DESC", params)
        horas = {f"{h:02d}:00": 0.0 for h in range(6, 21)}
        for h_str, val in vendas_dia:
            h = hora_para_grafico(h_str) or "Outros"
            horas[h] = horas.get(h, 0) + (val or 0.0)

        def cartao(valores):
            vt, vtp, vpag, vambos = valores
            return [["TOTAL GERAL DO DIA:", formatar_moeda(vt)], [f"{t}:", formatar_moeda(vtp)],
                    [f"{p}:", formatar_moeda(vpag)], [f"{t} + {p}:", formatar_moeda(vambos)]]

        exportacao = {
            "colunas": ["Relatório", "Data", "Produto", "Pagamento", "Total Geral", "Total Produto", "Total Pagamento",
                        "Total Cruzado"],
            "linhas": [["Venda Diária (Faturado)", d, t, p, *[formatar_moeda(v) for v in venda]],
                       ["Recebimento Diário (Caixa)", d, t, p, *[formatar_moeda(v) for v in recebido]]],
            "nome": f"relatorio_diario_{d.replace('/', '-')}", "titulo": "Relatório Diário",
            "titulo_excel": "Relatório Diário"}
        online = self.online_do_dia(d)
        if online["qtd"]:
            exportacao["linhas"].append(["Vendas online do dia (já incluídas acima)", d, "", "", online["total_fmt"], "", "", ""])
        return _ok(data=d, venda=cartao(venda), recebido=cartao(recebido), horas=horas, online=online,
                   ranking=[((r[0] or "SEM NOME").strip(), r[1] or 0.0) for r in vendas_vend],
                   exportacao=exportacao)

    # =========================================================================
    # TELA 5: EQUIPE
    # =========================================================================
    def listar_equipe(self):
        res = self._todos("SELECT id, nome, status FROM vendedores ORDER BY status ASC, nome ASC")
        return _ok(colunas=["ID", "Nome do Vendedor", "Status"], linhas=[[r[0], r[1], r[2]] for r in res])

    def adicionar_vendedor(self, nome):
        novo = (nome or "").strip().upper()
        if not novo:
            return _erro("Digite um nome!")
        if normalizar_nome_vendedor(novo) == LOJA_ONLINE:
            return _erro(f"⚠️ {LOJA_ONLINE} é o nome das vendas do site. Use outro nome.")
        existente = self._um("SELECT status FROM vendedores WHERE nome = ?", (novo,))
        if existente is None:
            self._exec("INSERT INTO vendedores (nome, status) VALUES (?, 'Ativo')", (novo,), commit=True)
            return _ok(mensagem=f"Vendedor {novo} cadastrado!")
        if existente["status"] == "Ativo":
            return _ok(mensagem=f"{novo} já está cadastrado(a) e ativo(a).", aviso=True)
        self._exec("UPDATE vendedores SET status = 'Ativo', participa_desafio = 0 WHERE nome = ?", (novo,), commit=True)
        return _ok(mensagem=f"Vendedor {novo} reativado!")

    def desativar_vendedor(self, id_vend):
        r = self._um("SELECT status FROM vendedores WHERE id = ?", (int(id_vend),))
        if r is None:
            return _erro("Vendedor não encontrado.")
        if r["status"] == "Inativo":
            return _erro("Este vendedor já está inativo!")
        self._exec("UPDATE vendedores SET status = 'Inativo' WHERE id = ?", (int(id_vend),), commit=True)
        return _ok(mensagem="Vendedor desativado!")

    # =========================================================================
    # TELA 6: DESPESAS
    # =========================================================================
    def _precisa_confirmar_comissao(self, tipo, datas):
        if tipo != TIPO_DESPESA_COMISSAO:
            return None
        if not any(self.filial.comissao_automatica_no_mes(d.strftime("%Y"), d.strftime("%m")) for d in datas):
            return None
        ini = self.filial.inicio_comissao_automatica
        return (f"Desde {ini} a comissão é calculada AUTOMATICAMENTE no DRE, e bonificações são lançadas em "
                f"Gestão → Bonificações.\n\nEsta despesa do tipo {TIPO_DESPESA_COMISSAO} fica salva em Despesas, "
                "mas NÃO entra no DRE.\n\nSalvar mesmo assim?")

    def salvar_despesa(self, descricao, valor_txt, parcelas_txt, data_txt, tipo, confirmou=False):
        desc = (descricao or "").strip()
        valor_txt = (valor_txt or "").strip()
        data_txt = (data_txt or "").strip()
        if not desc or not valor_txt or not data_txt:
            return _erro("⚠️ Preencha todos os campos!")
        val_total = ler_valor_monetario(valor_txt)
        if val_total is None:
            return _erro("⚠️ Digite um valor numérico válido!")
        if val_total == 0:
            return _erro("⚠️ O valor não pode ser zero!")
        try:
            p_txt = str(parcelas_txt or "").strip()
            parcelas = int(p_txt) if p_txt else 1
            if parcelas < 1 or parcelas > 24:
                raise ValueError()
        except ValueError:
            return _erro("⚠️ Parcelas devem ser entre 1 e 24!")
        data_inicial = texto_para_data(data_txt)
        if data_inicial is None:
            return _erro("⚠️ Data inválida! Use DD/MM/AAAA")
        if tipo not in TIPOS_DESPESA:
            return _erro("⚠️ Escolha o tipo de despesa!")

        valores = dividir_parcelas(val_total, parcelas)
        deslocamento = 1 if parcelas > 1 else 0  # parcelado começa no mês seguinte (regra de hoje)
        linhas = []
        for i in range(parcelas):
            m = data_inicial.month + i + deslocamento
            y = data_inicial.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            dia = min(data_inicial.day, calendar.monthrange(y, m)[1])
            desc_final = desc.upper() + (f" ({i + 1}/{parcelas})" if parcelas > 1 else "")
            linhas.append((desc_final, valores[i], tipo, datetime(y, m, dia).strftime("%d/%m/%Y")))

        if not confirmou:
            aviso = self._precisa_confirmar_comissao(tipo, [texto_para_data(l[3]) for l in linhas])
            if aviso:
                return _erro("", confirmar=aviso)
        try:
            self.con.executemany("INSERT INTO despesas (descricao, valor, tipo, data_despesa) VALUES (?, ?, ?, ?)",
                                 linhas)
            self.con.commit()
        except sqlite3.Error as e:
            self.registrar_erro("salvar_despesa", e)
            try:
                self.con.rollback()
            except sqlite3.Error:
                pass
            raise ErroBanco(str(e)) from e
        return _ok(mensagem="✔️ Despesa salva com sucesso!", qtd=len(linhas))

    COLUNAS_DESPESAS = ["ID", "Descrição", "Valor (R$)", "Tipo", "Data"]

    def historico_despesas(self, data_txt=""):
        data, erro = self._normalizar_data(data_txt)
        if erro:
            return _erro(erro)
        query = "SELECT id, descricao, valor, tipo, data_despesa FROM despesas WHERE 1=1"
        params = []
        if data:
            query += " AND data_despesa = ?"
            params.append(data)
        query += " ORDER BY id DESC"
        res = self._todos(query, params)
        return _ok(colunas=self.COLUNAS_DESPESAS, data=data,
                   linhas=[[l[0], l[1], numero_br(l[2]), l[3], l[4]] for l in res],
                   contagem=f"{len(res)} despesa(s)")

    def obter_despesa(self, id_desp):
        r = self._um("SELECT id, descricao, valor, tipo, data_despesa FROM despesas WHERE id = ?", (int(id_desp),))
        if r is None:
            return _erro("Essa despesa não existe mais.")
        return _ok(id=r["id"], descricao=r["descricao"] or "", valor=numero_br(r["valor"]), tipo=r["tipo"] or "",
                   data=r["data_despesa"] or "")

    def editar_despesa(self, id_desp, descricao, valor_txt, tipo, data_txt, confirmou=False):
        atual = self._um("SELECT tipo FROM despesas WHERE id = ?", (int(id_desp),))
        if atual is None:
            return _erro("Essa despesa não existe mais.")
        novo_valor = ler_valor_monetario(valor_txt)
        nova_data = texto_para_data(data_txt)
        if novo_valor is None or nova_data is None:
            return _erro("Valor ou Data inválida!")
        if novo_valor == 0:
            return _erro("O valor não pode ser zero!")
        if tipo not in TIPOS_DESPESA and tipo != atual["tipo"]:
            return _erro("Tipo de despesa inválido!")
        if not confirmou:
            aviso = self._precisa_confirmar_comissao(tipo, [nova_data])
            if aviso:
                return _erro("", confirmar=aviso)
        self._exec("UPDATE despesas SET descricao = ?, valor = ?, tipo = ?, data_despesa = ? WHERE id = ?",
                   ((descricao or "").strip().upper(), novo_valor, tipo, nova_data.strftime("%d/%m/%Y"), int(id_desp)),
                   commit=True)
        return _ok()

    def excluir_despesa(self, id_desp):
        self._exec("DELETE FROM despesas WHERE id = ?", (int(id_desp),), commit=True)
        return _ok()

    def anos_despesas(self):
        anos = self.anos_distintos([("SELECT DISTINCT data_despesa FROM despesas WHERE data_despesa IS NOT NULL", ())])
        if not anos:
            anos = [datetime.now().strftime("%Y")]
        return ["Todos"] + anos, self.ano_padrao(anos)

    def grafico_despesas(self, ano_sel, tipos_selecionados):
        tipos_selecionados = [t for t in TIPOS_DESPESA if t in set(tipos_selecionados or [])]
        dados = self._todos("SELECT UPPER(tipo), valor, data_despesa FROM despesas WHERE data_despesa IS NOT NULL")
        m = {tipo: novo_mapa_meses() for tipo in tipos_selecionados}
        for tipo, val, data_d in dados:
            tipo = str(tipo or "OUTROS CUSTOS").strip()
            if tipo not in m:
                continue
            ano_d, mes_d = ano_mes_de_data_flexivel(data_d)
            if ano_d is None or (ano_sel != "Todos" and ano_d != ano_sel):
                continue
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = 0.0
            if mes_d in m[tipo]:
                m[tipo][mes_d] += val
        linhas, classes, series = [], [], []
        total_meses = novo_mapa_meses()
        total = 0.0
        for tipo, meses in m.items():
            valores = list(meses.values())
            soma = sum(valores)
            if soma > 0:
                linhas.append([tipo] + [formatar_moeda(v) for v in valores] + [formatar_moeda(soma)])
                classes.append("")
                series.append((tipo, valores))
                for k, v in meses.items():
                    total_meses[k] += v
                total += soma
        if series:
            linhas.append(["TOTAL DE DESPESAS"] + [formatar_moeda(total_meses[f"{i:02d}"]) for i in range(1, 13)]
                          + [formatar_moeda(total)])
            classes.append("total")
        return _ok(colunas=["TIPO DE DESPESA"] + MESES_CURTOS + ["TOTAL"], linhas=linhas, classes=classes,
                   series=series, nome="grafico_de_despesas", titulo="Evolução Mensal de Despesas",
                   titulo_grafico=f"Evolução Mensal de Despesas - {ano_sel if ano_sel != 'Todos' else 'Todos os Anos'}")

    # =========================================================================
    # TELA 3: DASHBOARD
    # =========================================================================
    def anos_dashboard(self):
        anos = self.anos_distintos([
            ("SELECT DISTINCT data_venda FROM vendas WHERE data_venda IS NOT NULL", ()),
            ("SELECT DISTINCT data_vencimento FROM vendas WHERE data_vencimento IS NOT NULL", ())])
        if not anos:
            anos = [datetime.now().strftime("%Y")]
        return ["Todos"] + anos, self.ano_padrao(anos)

    def cores_vendedores(self):
        cores = {}
        for i, v in enumerate(self.todos_historico()):
            cores[v] = CORES_VENDEDOR_ORIGINAIS.get(v, CORES_EXTRA[i % len(CORES_EXTRA)])
        return cores

    def dashboard(self, ano, vend_selecionados):
        todos = self.todos_historico()
        vend_selecionados = [v for v in todos if v in set(vend_selecionados or [])]
        cores_v = self.cores_vendedores()

        param_v, f_venda = [], ""
        param_c, f_caixa = [], ""
        if ano != "Todos":
            f_venda += " AND substr(data_venda, 7, 4) = ?"
            param_v.append(ano)
            f_caixa += " AND substr(data_vencimento, 7, 4) = ?"
            param_c.append(ano)
        if not vend_selecionados:
            f_venda += " AND 1=0"
            f_caixa += " AND 1=0"
        else:
            ph = ",".join("?" for _ in vend_selecionados)
            f_venda += f" AND {SQL_NOME_VENDEDOR} IN ({ph})"
            param_v.extend(vend_selecionados)
            f_caixa += f" AND {SQL_NOME_VENDEDOR} IN ({ph})"
            param_c.extend(vend_selecionados)

        d_v = self._todos(f"SELECT {SQL_NOME_VENDEDOR}, UPPER(tipo_produto), UPPER(tipo_pagamento), "
                          f"substr(data_venda, 4, 2), SUM(valor) FROM vendas WHERE 1=1 {f_venda} GROUP BY 1, 2, 3, 4",
                          param_v)
        d_c = self._todos(f"SELECT {SQL_NOME_VENDEDOR}, substr(data_vencimento, 4, 2), SUM(valor) "
                          f"FROM vendas WHERE 1=1 {f_caixa} GROUP BY 1, 2", param_c)

        m_v = {v: novo_mapa_meses() for v in vend_selecionados}
        m_p = {p: novo_mapa_meses() for p in PRODUTOS}
        m_pag = {p: novo_mapa_meses() for p in PAGAMENTOS}
        t_v_m, t_v_g = novo_mapa_meses(), 0.0
        for vd, pd, pg, m_num, val in d_v:
            vd, pd, pg = (vd or "").strip(), (pd or "").strip(), (pg or "").strip()
            if "CRÉDITO 2X" in pg:
                pg = "CRÉDITO 2X"
            if "CRÉDITO 3X" in pg:
                pg = "CRÉDITO 3X"
            if vd in m_v and m_num in m_v[vd]:
                m_v[vd][m_num] += val
            if pd in m_p and m_num in m_p[pd]:
                m_p[pd][m_num] += val
            if pg in m_pag and m_num in m_pag[pg]:
                m_pag[pg][m_num] += val
            if m_num in t_v_m:
                t_v_m[m_num] += val
            t_v_g += val

        m_rec = {v: novo_mapa_meses() for v in vend_selecionados}
        t_c_m, t_c_g = novo_mapa_meses(), 0.0
        for vd, m_num, val in d_c:
            vd = (vd or "").strip()
            if vd in m_rec and m_num in m_rec[vd]:
                m_rec[vd][m_num] += val
            if m_num in t_c_m:
                t_c_m[m_num] += val
            t_c_g += val

        m_com = {v: {m: val * 0.01 for m, val in m_rec[v].items()} for v in vend_selecionados}
        sem = set(self.filial.sem_comissao)
        t_com_m, t_com_g = novo_mapa_meses(), 0.0

        def tabela(titulo_coluna, nomes, matriz, cores, rotulo_total, tot_m, tot_g, comissao=False):
            nonlocal t_com_g
            linhas, classes, cores_linha = [], [], []
            for n in nomes:
                if comissao and n in sem:
                    continue
                vals = list(matriz[n].values())
                linhas.append([n] + [formatar_moeda(v) for v in vals] + [formatar_moeda(sum(vals))])
                classes.append("")
                cores_linha.append(cores.get(n, ""))
                if comissao:
                    for mm, v in matriz[n].items():
                        t_com_m[mm] += v
                    t_com_g += sum(vals)
            if comissao:
                tot_m, tot_g = t_com_m, t_com_g
            linhas.append([rotulo_total] + [formatar_moeda(tot_m[f"{i:02d}"]) for i in range(1, 13)]
                          + [formatar_moeda(tot_g)])
            classes.append("total")
            cores_linha.append("")
            return {"colunas": [titulo_coluna] + MESES_CURTOS + ["TOTAL"], "linhas": linhas, "classes": classes,
                    "cores": cores_linha}

        def series(matriz, nomes, cores, comissao=False):
            out = []
            for n in nomes:
                if comissao and n in sem:
                    continue
                vals = list(matriz[n].values())
                if sum(vals) > 0:
                    out.append((n, vals, cores.get(n, "#000000")))
            return out

        abas = [
            ("vendedores", "Vendedores (Faturado)", tabela("VENDEDOR", vend_selecionados, m_v, cores_v,
                                                           "TOTAL FATURADO", t_v_m, t_v_g),
             series(m_v, vend_selecionados, cores_v), "Evolução Mensal de Faturamento",
             "dashboard_vendedores", "Faturamento por Vendedor"),
            ("produtos", "Produtos (Faturado)", tabela("PRODUTO", PRODUTOS, m_p, CORES_PRODUTO, "TOTAL FATURADO",
                                                       t_v_m, t_v_g),
             series(m_p, PRODUTOS, CORES_PRODUTO), "Evolução Mensal de Volume por Produto",
             "dashboard_produtos", "Faturamento por Produto"),
            ("pagamento", "Pagamento (Faturado)", tabela("PAGAMENTO", PAGAMENTOS, m_pag, CORES_PAGAMENTO,
                                                         "TOTAL FATURADO", t_v_m, t_v_g),
             series(m_pag, PAGAMENTOS, CORES_PAGAMENTO), "Evolução Mensal por Pagamento",
             "dashboard_pagamento", "Faturamento por Forma de Pagamento"),
            ("caixa", "Caixa (Recebido)", tabela("RECEBIMENTOS", vend_selecionados, m_rec, cores_v, "TOTAL RECEBIDO",
                                                 t_c_m, t_c_g),
             series(m_rec, vend_selecionados, cores_v), "Evolução Mensal do Fluxo de Caixa",
             "dashboard_caixa", "Recebimentos (Caixa)"),
        ]
        tab_com = tabela("COMISSÃO (1%)", vend_selecionados, m_com, cores_v, "TOTAL A PAGAR", None, None, comissao=True)
        abas.append(("comissoes", "Comissões (A Pagar)", tab_com, series(m_com, vend_selecionados, cores_v, True),
                     "Evolução de Comissões", "dashboard_comissoes", "Comissões a Pagar"))
        sufixo = "Todos os Anos" if ano == "Todos" else ano
        return _ok(abas=[{"id": i, "rotulo": r, **tab, "series": s, "titulo_grafico": f"{tg} - {sufixo}",
                          "nome": n, "titulo": t} for i, r, tab, s, tg, n, t in abas])

    # =========================================================================
    # TELA 7: DRE ANUAL
    # =========================================================================
    def anos_dre(self):
        anos = self.anos_distintos([
            ("SELECT DISTINCT data_despesa FROM despesas WHERE data_despesa IS NOT NULL", ()),
            ("SELECT DISTINCT data_venda FROM vendas WHERE data_venda IS NOT NULL", ())])
        if not anos:
            anos = [datetime.now().strftime("%Y")]
        return anos, self.ano_padrao(anos)

    def _comissao_automatica_por_mes(self, ano):
        meses = novo_mapa_meses()
        filtro, params = "", [ano]
        if self.filial.sem_comissao:
            filtro = f" AND {SQL_NOME_VENDEDOR} NOT IN ({','.join('?' for _ in self.filial.sem_comissao)})"
            params += self.filial.sem_comissao
        for mes, soma in self._todos("SELECT substr(data_vencimento, 4, 2), SUM(valor) FROM vendas "
                                     f"WHERE substr(data_vencimento, 7, 4) = ?{filtro} GROUP BY 1", params):
            if mes in meses and self.filial.comissao_automatica_no_mes(ano, mes):
                meses[mes] = round((soma or 0.0) * PERCENTUAL_COMISSAO, 2)
        return meses

    def _bonificacoes_por_mes(self, ano):
        meses = novo_mapa_meses()
        for mes, soma in self._todos("SELECT mes, SUM(valor) FROM bonificacoes WHERE ano = ? GROUP BY mes", (ano,)):
            if mes in meses:
                meses[mes] += soma or 0.0
        dias = {r[0]: r[1] for r in self._todos(
            "SELECT substr(data, 4, 2), COUNT(*) FROM desafios WHERE substr(data, 7, 4) = ? GROUP BY 1", (ano,))}
        for mes, vendedor, qtd in self._todos(
                "SELECT substr(d.data, 4, 2), r.vendedor, SUM(r.quantidade) FROM desafio_resultados r "
                "JOIN desafios d ON d.id = r.desafio_id WHERE substr(d.data, 7, 4) = ? GROUP BY 1, 2", (ano,)):
            if mes in meses and normalizar_nome_vendedor(vendedor) not in self.filial.excluidos_desafio:
                meses[mes] += calcular_conclusao_desafio(dias.get(mes, 0), qtd or 0)["bonificacao"]
        return {m: round(v, 2) for m, v in meses.items()}

    def dre(self, ano_sel):
        vendas = self._todos("SELECT data_venda, valor FROM vendas")
        despesas = self._todos("SELECT tipo, data_despesa, valor FROM despesas")
        receita = novo_mapa_meses()
        for data_v, val in vendas:
            a, m = ano_mes_de_data_flexivel(data_v)
            if a == ano_sel and m in receita:
                receita[m] += val
        por_tipo, total_desp = {}, novo_mapa_meses()
        for tipo, data_d, val in despesas:
            if not data_d:
                continue
            tipo = tipo.strip().upper() if tipo else "OUTROS CUSTOS"
            a, m = ano_mes_de_data_flexivel(data_d)
            if a == ano_sel and m in total_desp:
                if tipo == TIPO_DESPESA_COMISSAO and self.filial.comissao_automatica_no_mes(a, m):
                    continue
                por_tipo.setdefault(tipo, novo_mapa_meses())[m] += val or 0.0
                total_desp[m] += val or 0.0
        comissao = self._comissao_automatica_por_mes(ano_sel)
        bonif = self._bonificacoes_por_mes(ano_sel)
        if any(bonif.values()):
            linha = por_tipo.setdefault("BONIFICAÇÕES", novo_mapa_meses())
            for m, v in bonif.items():
                linha[m] += v
                total_desp[m] += v
        if any(comissao.values()):
            linha = por_tipo.setdefault(TIPO_DESPESA_COMISSAO, novo_mapa_meses())
            for m, v in comissao.items():
                linha[m] += v
                total_desp[m] += v

        tot_rec = sum(receita.values())
        linhas = [["RECEITA BRUTA"] + [valor_dre(receita[f"{i:02d}"]) for i in range(1, 13)]
                  + [valor_dre(tot_rec), "100%"]]
        classes = ["receita"]
        for c, tipo in enumerate(sorted(por_tipo)):
            vals = list(por_tipo[tipo].values())
            tt = sum(vals)
            pct = f"{(tt / tot_rec * 100):.1f}%" if tot_rec > 0 else "0.0%"
            linhas.append([tipo] + [valor_dre(v) for v in vals] + [valor_dre(tt), pct])
            classes.append("despesa")
        tot_desp = sum(total_desp.values())
        pct_desp = f"{(tot_desp / tot_rec * 100):.1f}%" if tot_rec > 0 else "0.0%"
        linhas.append(["TOTAL DESPESAS"] + [valor_dre(total_desp[f"{i:02d}"]) for i in range(1, 13)]
                      + [valor_dre(tot_desp), pct_desp])
        classes.append("total-despesa")
        lucro = {m: receita[m] - total_desp[m] for m in receita}
        tot_lucro = tot_rec - tot_desp
        pct_lucro = f"{(tot_lucro / tot_rec * 100):.1f}%" if tot_rec > 0 else "0.0%"
        linhas.append(["LUCRO LÍQUIDO"] + [valor_dre(lucro[f"{i:02d}"]) for i in range(1, 13)]
                      + [valor_dre(tot_lucro), pct_lucro])
        classes.append("lucro" if tot_lucro >= 0 else "prejuizo")
        ini = self.filial.inicio_comissao_automatica
        notas = [f"COMISSÕES: até o mês anterior a {ini}, valores lançados em Despesas; a partir de {ini}, 1% "
                 f"automático sobre o recebido no mês (sem {self.filial.sem_comissao_texto or 'exceções'}).",
                 "BONIFICAÇÕES: lançadas em Gestão → Bonificações + bonificação dos Desafios do mês."]
        return _ok(colunas=["CATEGORIA (R$)"] + MESES_CURTOS + ["TOTAL ANO", "%"], linhas=linhas, classes=classes,
                   kpis={"receita": formatar_moeda(tot_rec), "despesas": formatar_moeda(tot_desp),
                         "lucro": formatar_moeda(tot_lucro), "margem": pct_lucro, "positivo": tot_lucro >= 0},
                   series={"receita": list(receita.values()), "despesas": list(total_desp.values()),
                           "lucro": list(lucro.values())},
                   notas=notas, nome="dre_anual", titulo="DRE Anual", titulo_grafico=f"DRE Anual - {ano_sel}")

    # =========================================================================
    # TELA 7B: DESAFIOS
    # =========================================================================
    def _participantes_desafio(self, extras=()):
        exc = self.filial.excluidos_desafio
        nomes = [r["nome"] for r in self._todos(
            "SELECT nome FROM vendedores WHERE status = 'Ativo' AND participa_desafio = 1 ORDER BY nome")
            if normalizar_nome_vendedor(r["nome"]) not in exc]
        nomes += sorted(n for n in extras if n not in nomes and normalizar_nome_vendedor(n) not in exc)
        return nomes

    def carregar_desafio(self, data_txt):
        data, erro = self._normalizar_data(data_txt)
        if erro or not data:
            return _erro(erro or "⚠️ Data inválida! Use DD/MM/AAAA")
        desafio = self._um("SELECT id, data, produto FROM desafios WHERE data = ?", (data,))
        if desafio is None:
            return _ok(data=data, desafio=None, participantes=[], meta=META_DIARIA_DESAFIO)
        resultados = {r["vendedor"]: r["quantidade"] for r in self._todos(
            "SELECT vendedor, quantidade FROM desafio_resultados WHERE desafio_id = ?", (desafio["id"],))}
        nomes = self._participantes_desafio(extras=resultados.keys())
        return _ok(data=data, desafio={"id": desafio["id"], "produto": desafio["produto"]}, meta=META_DIARIA_DESAFIO,
                   participantes=[{"nome": n, "quantidade": resultados.get(n, 0)} for n in nomes])

    def salvar_desafio(self, data_txt, produto):
        data, erro = self._normalizar_data(data_txt)
        if erro or not data:
            return _erro(erro or "⚠️ Data inválida! Use DD/MM/AAAA")
        produto = (produto or "").strip().upper()
        if not produto:
            return _erro("⚠️ Informe o nome do produto!")
        self._exec("INSERT INTO desafios (data, produto, meta_quantidade, criado_em) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT(data) DO UPDATE SET produto = excluded.produto",
                   (data, produto, META_DIARIA_DESAFIO, datetime.now().strftime("%d/%m/%Y %H:%M")), commit=True)
        return _ok(mensagem=f"✔️ Desafio de {data} salvo!")

    def excluir_desafio(self, data_txt):
        data, erro = self._normalizar_data(data_txt)
        if erro or not data:
            return _erro(erro or "⚠️ Data inválida! Use DD/MM/AAAA")
        d = self._um("SELECT id FROM desafios WHERE data = ?", (data,))
        if d is None:
            return _erro("⚠️ Não há desafio cadastrado nesta data.")
        self._transacao([("DELETE FROM desafio_resultados WHERE desafio_id = ?", (d["id"],)),
                         ("DELETE FROM desafios WHERE id = ?", (d["id"],))])
        return _ok(mensagem="✔️ Desafio excluído.")

    def salvar_quantidades_desafio(self, desafio_id, quantidades):
        if not self._um("SELECT id FROM desafios WHERE id = ?", (int(desafio_id),)):
            return _erro("Esse desafio não existe mais.")
        comandos = []
        for nome, txt in quantidades.items():
            txt = str(txt).strip() or "0"
            if not txt.isdigit():
                return _erro(f"Quantidade inválida para {nome}. Use um número inteiro (0, 1, 2...).")
            comandos.append(("INSERT INTO desafio_resultados (desafio_id, vendedor, quantidade) VALUES (?, ?, ?) "
                             "ON CONFLICT(desafio_id, vendedor) DO UPDATE SET quantidade = excluded.quantidade",
                             (int(desafio_id), nome, int(txt))))
        if comandos:
            self._transacao(comandos)
        return _ok(mensagem="✔️ Quantidades salvas!")

    def anos_desafio(self):
        anos = self.anos_distintos([("SELECT DISTINCT data FROM desafios", ())])
        atual = str(datetime.now().year)
        if atual not in anos:
            anos.insert(0, atual)
        return sorted(anos, reverse=True)

    def conclusao_mensal(self, mes_nome, ano):
        mes = f"{MESES.index(mes_nome) + 1:02d}"
        desafios_mes = self._todos("SELECT id, data, produto FROM desafios WHERE substr(data, 4, 2) = ? "
                                   "AND substr(data, 7, 4) = ? ORDER BY substr(data, 1, 2)", (mes, ano))
        resultados = self._todos("SELECT r.desafio_id, r.vendedor, r.quantidade FROM desafio_resultados r "
                                 "JOIN desafios d ON d.id = r.desafio_id WHERE substr(d.data, 4, 2) = ? "
                                 "AND substr(d.data, 7, 4) = ?", (mes, ano))
        por_dia, total_v = {}, {}
        for r in resultados:
            por_dia.setdefault(r["desafio_id"], {})[r["vendedor"]] = r["quantidade"]
            total_v[r["vendedor"]] = total_v.get(r["vendedor"], 0) + r["quantidade"]
        if total_v:
            nomes = sorted(n for n in total_v if normalizar_nome_vendedor(n) not in self.filial.excluidos_desafio)
        else:
            nomes = self._participantes_desafio()
        dias = len(desafios_mes)
        linhas, classes = [], []
        total_bonus, total_vendido = 0.0, 0
        for nome in nomes:
            r = calcular_conclusao_desafio(dias, total_v.get(nome, 0))
            total_bonus += r["bonificacao"]
            total_vendido += r["vendido"]
            linhas.append([nome, r["vendido"], r["meta"], f"{r['dias_concluidos']} de {dias}",
                           f"{r['percentual']:.1f}%".replace(".", ","), moeda_sempre(r["bonificacao"])])
            classes.append("bateu" if r["percentual"] >= 100 else "")
        if nomes:
            linhas.append(["TOTAL", total_vendido, "", "", "", moeda_sempre(total_bonus)])
            classes.append("total")
        periodo = f"{mes_nome}/{ano}"
        por_dia_linhas = [[d["data"], d["produto"]] + [por_dia.get(d["id"], {}).get(n, 0) for n in nomes]
                          for d in desafios_mes]
        return _ok(
            kpis={"dias": str(dias), "meta": f"{dias * META_DIARIA_DESAFIO} un.", "total": moeda_sempre(total_bonus)},
            resumo={"colunas": ["Vendedora", "Vendido no mês", "Meta do mês", "Dias concluídos", "% concluída",
                                "Bonificação"], "linhas": linhas, "classes": classes,
                    "nome": "conclusao_desafios_" + periodo.replace("/", "_"),
                    "titulo": "Conclusão dos Desafios - " + periodo},
            por_dia={"colunas": ["Data", "Produto"] + nomes, "linhas": por_dia_linhas,
                     "nome": "desafios_por_dia_" + periodo.replace("/", "_"), "titulo": "Desafios por Dia - " + periodo})

    def participantes_desafio(self):
        equipe = self._todos("SELECT id, nome, participa_desafio FROM vendedores WHERE status = 'Ativo' ORDER BY nome")
        return _ok(equipe=[{"id": v["id"], "nome": v["nome"], "participa": bool(v["participa_desafio"])}
                           for v in equipe if normalizar_nome_vendedor(v["nome"]) not in self.filial.excluidos_desafio])

    def alterar_participacao(self, id_vend, participa):
        r = self._um("SELECT nome FROM vendedores WHERE id = ?", (int(id_vend),))
        if r is None:
            return _erro("Vendedora não encontrada.")
        self._exec("UPDATE vendedores SET participa_desafio = ? WHERE id = ?", (1 if participa else 0, int(id_vend)),
                   commit=True)
        nome = r["nome"]
        return _ok(mensagem=f"✔️ {nome} agora participa dos desafios" if participa else f"✔️ {nome} saiu dos desafios")

    # =========================================================================
    # TELA 7C: BONIFICAÇÕES
    # =========================================================================
    def anos_permitidos_bonif(self):
        a = self.filial.ano_ini_com
        inicio = int(a) if a.isdigit() else datetime.now().year
        return [str(x) for x in range(datetime.now().year + 1, inicio - 1, -1)]

    def vendedoras_bonif(self):
        return [n for n in self.vendedores_ativos()
                if n != "Nenhum Vendedor Ativo" and normalizar_nome_vendedor(n) not in self.filial.excluidos_bonificacao]

    def _validar_bonif(self, vendedora, mes_nome, ano, valor_txt):
        if vendedora in ("Selecione", "Nenhum Vendedor Ativo", "", None):
            return None, "⚠️ Escolha a vendedora!"
        if normalizar_nome_vendedor(vendedora) in self.filial.excluidos_bonificacao:
            return None, f"⚠️ {vendedora} não participa das bonificações."
        if mes_nome not in MESES:
            return None, "⚠️ Escolha o mês!"
        mes = f"{MESES.index(mes_nome) + 1:02d}"
        if not self.filial.comissao_automatica_no_mes(ano, mes):
            return None, f"⚠️ Só são aceitos meses a partir de {self.filial.inicio_comissao_automatica}."
        valor = ler_valor_monetario(valor_txt)
        if valor is None or valor <= 0:
            return None, "⚠️ Digite um valor maior que zero!"
        return (mes, valor), None

    def salvar_bonificacao(self, vendedora, mes_nome, ano, valor_txt, motivo, confirmou=False):
        ok, erro = self._validar_bonif(vendedora, mes_nome, ano, valor_txt)
        if erro:
            return _erro(erro)
        mes, valor = ok
        if valor >= 1000 and not confirmou:
            return _erro("", confirmar=f"Confirma a bonificação de {moeda_sempre(valor)} para {vendedora} ({mes}/{ano})?")
        self._exec("INSERT INTO bonificacoes (vendedor, mes, ano, valor, motivo, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
                   (vendedora, mes, ano, valor, (motivo or "").strip().upper(),
                    datetime.now().strftime("%d/%m/%Y %H:%M")), commit=True)
        return _ok(mensagem=f"✔️ {moeda_sempre(valor)} para {vendedora} salvo!")

    def listar_bonificacoes(self, mes_nome, ano):
        sql = "SELECT id, vendedor, mes, ano, valor, motivo, criado_em FROM bonificacoes WHERE ano = ?"
        params = [ano]
        if mes_nome != "Ano inteiro":
            sql += " AND mes = ?"
            params.append(f"{MESES.index(mes_nome) + 1:02d}")
        sql += " ORDER BY mes, vendedor, id"
        res = self._todos(sql, params)
        linhas, classes, ids = [], [], []
        total = 0.0
        for r in res:
            total += r["valor"] or 0.0
            linhas.append([r["id"], r["vendedor"], f"{r['mes']}/{r['ano']}", moeda_sempre(r["valor"]),
                           r["motivo"] or "", r["criado_em"] or ""])
            classes.append("")
            ids.append(r["id"])
        if res:
            linhas.append(["", "TOTAL", "", moeda_sempre(total), "", ""])
            classes.append("total")
            ids.append(None)
        periodo = ano if mes_nome == "Ano inteiro" else f"{mes_nome}/{ano}"
        periodo_arq = ano if mes_nome == "Ano inteiro" else f"{mes_nome}_{ano}"
        return _ok(colunas=["ID", "Vendedora", "Mês ref.", "Valor", "Motivo", "Lançado em"], linhas=linhas,
                   classes=classes, ids=ids, resumo=f"{len(res)} lançamento(s) · {moeda_sempre(total)} em {periodo}",
                   nome=f"bonificacoes_{periodo_arq}", titulo=f"Bonificações - {periodo}", titulo_excel="Bonificações")

    def obter_bonificacao(self, id_bonif):
        r = self._um("SELECT vendedor, mes, ano, valor, motivo FROM bonificacoes WHERE id = ?", (int(id_bonif),))
        if r is None:
            return _erro("Essa bonificação não existe mais.")
        nomes = self.vendedoras_bonif()
        if r["vendedor"] not in nomes:
            nomes.append(r["vendedor"])
        anos = self.anos_permitidos_bonif()
        if r["ano"] not in anos:
            anos.append(r["ano"])
        return _ok(id=int(id_bonif), vendedor=r["vendedor"], mes_nome=MESES[int(r["mes"]) - 1], ano=r["ano"],
                   valor=f"{r['valor']:.2f}".replace(".", ","), motivo=r["motivo"] or "", vendedoras=nomes, anos=anos)

    def editar_bonificacao(self, id_bonif, vendedora, mes_nome, ano, valor_txt, motivo):
        ok, erro = self._validar_bonif(vendedora, mes_nome, ano, valor_txt)
        if erro:
            return _erro(erro)
        mes, valor = ok
        self._exec("UPDATE bonificacoes SET vendedor = ?, mes = ?, ano = ?, valor = ?, motivo = ? WHERE id = ?",
                   (vendedora, mes, ano, valor, (motivo or "").strip().upper(), int(id_bonif)), commit=True)
        return _ok()

    def excluir_bonificacao(self, id_bonif):
        self._exec("DELETE FROM bonificacoes WHERE id = ?", (int(id_bonif),), commit=True)
        return _ok()


# -----------------------------------------------------------------------------
# Cópias de conflito do OneDrive (mesmo aviso do sistema atual)
# -----------------------------------------------------------------------------
def copias_de_conflito(caminho_banco):
    pasta, arquivo = os.path.split(caminho_banco)
    nome, ext = os.path.splitext(arquivo)
    try:
        return sorted(f for f in os.listdir(pasta or ".")
                      if f.lower().startswith(nome.lower() + "-") and f.lower().endswith(ext.lower()))
    except OSError:
        return []
