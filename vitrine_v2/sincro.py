"""Sincronização com o portão (Cloudflare Worker) -- F4/F5.

Regras de ouro:
  * A interface e o banco local NUNCA esperam a rede. Tudo que viaja entra numa fila (tabela fila_envio) por GATILHO
    do SQLite, na mesma transação da venda/movimento. Um laço em 2º plano esvazia a fila.
  * Todo evento tem um id único (eid). O portão faz INSERT OR IGNORE por eid: reenviar não duplica.
  * Só sai da fila (enviado_em) depois que o portão confirmou. Se o programa morrer no meio, reenvia; o portão ignora.
  * VÁRIOS COMPUTADORES (t105): tudo o que a loja edita viaja nos dois sentidos. Cada computador tem uma réplica completa
    de cada loja; envia os seus eventos e PUXA os dos outros (/pull?desde=seq). Conflito: a última escrita vence por registro,
    pelo relógio híbrido (HLC em sync_estado.hlc) e, no empate, pelo id do computador (sync_disp) -- a MESMA regra do portão.
    Remoção = lápide (sync_lapide aqui, apagado=1 no portão). Tabelas com chave natural (dia, nome) têm uid determinístico:
    dois computadores que criam o "mesmo" registro (fechamento do dia, desafio do dia) fundem em um só.

Uso na linha de comando (testes e carga histórica):
  python sincro.py enviar    --banco X.db --filial jardins --url U --chave K
  python sincro.py conferir  --banco X.db --filial jardins --url U --chave K --csv saida.csv
"""
import argparse
import csv
import json
import os
import socket
import sqlite3
import sys
import threading
import time
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # roda também com python -I (sem a pasta do script no caminho)
import pedidos_dados  # noqa: E402

# tabela -> coluna do id único global. 'uid' é criada por nós; 'uuid' já existia em movimentos e transferencias.
TABELAS = {"vendas": "uid", "despesas": "uid", "movimentos": "uuid", "produtos": "uid", "transferencias": "uuid",
           "movimentos_caixa": "uid", "fechamento_caixa": "uid", "fechamento_contagem": "uid",
           "estoque": "uid",  # do estoque só viaja o MÍNIMO (a quantidade vem dos movimentos)
           "vendedores": "uid", "desafios": "uid", "desafio_resultados": "uid", "bonificacoes": "uid", "config": "uid"}
_PREFIXO = {"vendas": "V", "despesas": "D", "movimentos": "M", "movimentos_caixa": "C", "bonificacoes": "B"}
_COLS_SYNC = ("uid", "sync_origem", "sync_em", "sync_disp")
CONFIG_SYNC = ("senha_gestao_hash",)  # da tabela config só viaja isto (a senha da Gestão é a mesma em todos os computadores)
_SEM_BARRA = "replace({r}.data,'/','')"
# uid determinístico (r = linha): mesmo registro natural => mesmo uid em qualquer computador. Texto livre vai em hex (cabe no RE_ID).
_UID_NATURAL = {
    "produtos": "'P-' || {r}.codigo",
    "estoque": "'{I}-E-' || (SELECT codigo FROM produtos WHERE id = {r}.produto_id)",
    "fechamento_caixa": "'{I}-F-' || " + _SEM_BARRA,
    "fechamento_contagem": "'{I}-FC-' || " + _SEM_BARRA + " || '-' || lower(hex({r}.forma_pagamento))",
    "vendedores": "'{I}-VD-' || lower(hex({r}.nome))",
    "desafios": "'{I}-DS-' || " + _SEM_BARRA,
    "desafio_resultados": "'{I}-DR-' || (SELECT replace(data,'/','') FROM desafios WHERE id = {r}.desafio_id) || '-' || lower(hex({r}.vendedor))",
    "config": "'{I}-CF-' || {r}.chave",
}
_FILTRO = {"config": "{r}.chave IN (" + ",".join(f"'{c}'" for c in CONFIG_SYNC) + ")"}
AGORA_SQL = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
TS_ANTIGO = "2000-01-01T00:00:00.000Z"  # carga retroativa: nunca vence uma edição de verdade feita em outro computador
TS_VAZIO = "1999-01-01T00:00:00.000Z"  # banco recém-criado (equipe inicial etc.): perde até para o banco antigo migrado
# Relógio híbrido: o próximo ts é max(agora, último ts visto + 1 ms). Assim uma edição feita DEPOIS de ver a de outro
# computador sempre vence, mesmo com o relógio deste PC atrasado.
HLC_PASSO = ("UPDATE sync_estado SET hlc = CASE WHEN " + AGORA_SQL + " > COALESCE(hlc, '') THEN " + AGORA_SQL +
             " ELSE strftime('%Y-%m-%dT%H:%M:%fZ', julianday(hlc) + 1.0/86400000) END WHERE aplicando = 0;")
HLC = "(SELECT hlc FROM sync_estado)"
EU = "(SELECT disp FROM sync_estado)"
_RANK = {"pedido": 0, "enviada": 1, "recebida": 2, "cancelada": 2}
LOTE = int(os.environ.get("SINCRO_LOTE", 100))  # (variável só para teste) o plano grátis do Worker tem ~10 ms de CPU por chamada


def agora_utc():
    t = datetime.now(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


# --------------------------------------------------------------------------------------------------------------
# Estrutura local: colunas, fila, gatilhos, uid retroativo. Idempotente (pode rodar a cada abertura).
# --------------------------------------------------------------------------------------------------------------
def preparar(con, filial):
    assert filial.isalpha() and filial.islower(), "código de filial inesperado"
    inicial = filial[0].upper()
    try:
        cur = con.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS fila_envio (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, eid TEXT NOT NULL UNIQUE, tabela TEXT NOT NULL,
                        uid TEXT NOT NULL, op TEXT NOT NULL, ts TEXT NOT NULL, tentativas INTEGER NOT NULL DEFAULT 0,
                        enviado_em TEXT, erro TEXT)""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fila_pendente ON fila_envio(id) WHERE enviado_em IS NULL AND erro IS NULL")
        cur.execute("CREATE TABLE IF NOT EXISTS sync_estado (aplicando INTEGER NOT NULL)")
        if cur.execute("SELECT COUNT(*) FROM sync_estado").fetchone()[0] == 0:
            cur.execute("INSERT INTO sync_estado (aplicando) VALUES (0)")
        for c in ("hlc", "disp", "quem"):
            if c not in {r[1] for r in cur.execute("PRAGMA table_info(sync_estado)")}:
                cur.execute(f"ALTER TABLE sync_estado ADD COLUMN {c} TEXT")
        cur.execute("UPDATE sync_estado SET aplicando = 0, quem = ?", (socket.gethostname(),))
        cur.execute("""CREATE TABLE IF NOT EXISTS sync_lapide (tabela TEXT NOT NULL, uid TEXT NOT NULL, ts TEXT NOT NULL, disp TEXT,
                       PRIMARY KEY (tabela, uid))""")
        cur.execute("CREATE TABLE IF NOT EXISTS sync_espera (tabela TEXT NOT NULL, uid TEXT NOT NULL, reg TEXT NOT NULL, "
                    "PRIMARY KEY (tabela, uid))")
        ts_bf = TS_ANTIGO if cur.execute("SELECT 1 FROM vendas LIMIT 1").fetchone() else TS_VAZIO
        for t, u in TABELAS.items():
            existentes = {r[1] for r in cur.execute(f"PRAGMA table_info({t})")}
            if not existentes:
                continue
            for c in {u, "sync_origem", "sync_em", "sync_disp"} - existentes:
                cur.execute(f"ALTER TABLE {t} ADD COLUMN {c} TEXT")
            # Linhas antigas ganham uid DETERMINÍSTICO (rodar de novo não duplica) e entram na fila como 'I', com ts antigo.
            novo = (_UID_NATURAL[t].format(r=t, I=inicial) if t in _UID_NATURAL else
                    "uuid" if t == "transferencias" else f"'{inicial}-{_PREFIXO.get(t, '')}' || id")
            filtro = " AND " + _FILTRO[t].format(r=t) if t in _FILTRO else ""
            cur.execute(f"INSERT OR IGNORE INTO fila_envio (eid, tabela, uid, op, ts) "
                        f"SELECT 'bf-' || COALESCE({u}, {novo}), '{t}', COALESCE({u}, {novo}), 'I', '{ts_bf}' "
                        f"FROM {t} WHERE sync_origem IS NULL{filtro}")
            cur.execute(f"UPDATE {t} SET {u} = COALESCE({u}, {novo}), sync_origem = '{filial}', sync_em = '{ts_bf}' "
                        f"WHERE sync_origem IS NULL{filtro}")
            cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{t}_{u} ON {t}({u})")
            _gatilhos(cur, t, u, filial, existentes)
        for ev in ("insert", "delete"):  # versão t105 reenviava o fechamento; agora a contagem viaja sozinha
            cur.execute(f"DROP TRIGGER IF EXISTS sync_contagem_{ev}")
        con.commit()
    except sqlite3.Error:
        con.rollback()
        raise


def _gatilhos(cur, t, u, filial, colunas_antes):
    negocio = [r[1] for r in cur.execute(f"PRAGMA table_info({t})") if r[1] not in _COLS_SYNC + ("id", u)]
    if t == "estoque":
        negocio = ["minimo"]  # a quantidade muda a cada venda e ja viaja pelos movimentos: so o minimo gera evento
    novo_uid = _UID_NATURAL[t].format(r="NEW", I=filial[0].upper()) if t in _UID_NATURAL else "lower(hex(randomblob(16)))"
    fora = "(SELECT aplicando FROM sync_estado) = 0"
    so_i = " WHEN " + _FILTRO[t].format(r="NEW") if t in _FILTRO else ""
    so_u = " AND " + _FILTRO[t].format(r="NEW") if t in _FILTRO else ""
    so_d = " AND " + _FILTRO[t].format(r="OLD") if t in _FILTRO else ""
    enfileira = ("INSERT INTO fila_envio (eid, tabela, uid, op, ts) SELECT lower(hex(randomblob(16))), '{t}', {u}, '{op}', sync_em "
                 "FROM {t} WHERE rowid = NEW.rowid AND {fora};")
    for sufixo in ("i", "u", "d"):
        cur.execute(f"DROP TRIGGER IF EXISTS sync_{t}_{sufixo}")
    # Ao APLICAR o que veio de outro computador, quem aplica já preenche uid/sync_em/sync_disp: os COALESCE mantêm.
    cur.execute(f"CREATE TRIGGER sync_{t}_i AFTER INSERT ON {t}{so_i} BEGIN {HLC_PASSO} "
                f"UPDATE {t} SET {u} = COALESCE({u}, {novo_uid}), sync_origem = COALESCE(sync_origem, '{filial}'), "
                f"sync_em = COALESCE(sync_em, {HLC}), sync_disp = COALESCE(sync_disp, {EU}) WHERE rowid = NEW.rowid; "
                + enfileira.format(t=t, u=u, op="I", fora=fora) + " END")
    cur.execute(f"CREATE TRIGGER sync_{t}_u AFTER UPDATE OF {', '.join(chr(34) + c + chr(34) for c in negocio)} ON {t} "
                f"WHEN {fora}{so_u} BEGIN {HLC_PASSO} UPDATE {t} SET sync_em = {HLC}, sync_disp = {EU} WHERE rowid = NEW.rowid; "
                + enfileira.format(t=t, u=u, op="U", fora=fora) + " END")
    cur.execute(f"CREATE TRIGGER sync_{t}_d AFTER DELETE ON {t} WHEN OLD.{u} IS NOT NULL AND {fora}{so_d} BEGIN {HLC_PASSO} "
                f"INSERT INTO fila_envio (eid, tabela, uid, op, ts) VALUES (lower(hex(randomblob(16))), '{t}', OLD.{u}, 'D', {HLC}); "
                f"INSERT OR REPLACE INTO sync_lapide (tabela, uid, ts, disp) VALUES ('{t}', OLD.{u}, {HLC}, {EU}); END")


def pendentes(con):
    return con.execute("SELECT COUNT(*) FROM fila_envio WHERE enviado_em IS NULL AND erro IS NULL").fetchone()[0]


# --------------------------------------------------------------------------------------------------------------
# Montar o evento a partir do estado ATUAL da linha (reenviar nunca manda dado velho).
# --------------------------------------------------------------------------------------------------------------
def _dados_da_linha(con, tabela, uid):
    u = TABELAS[tabela]
    r = con.execute(f"SELECT * FROM {tabela} WHERE {u} = ?", (uid,)).fetchone()
    if r is None:
        return None
    d = {k: r[k] for k in r.keys() if k not in _COLS_SYNC + ("id", u)}
    if tabela == "movimentos":
        p = con.execute("SELECT codigo FROM produtos WHERE id = ?", (d.pop("produto_id"),)).fetchone()
        d["produto_codigo"] = p[0] if p else None
    if tabela == "estoque":
        d.pop("quantidade", None)
        p = con.execute("SELECT codigo FROM produtos WHERE id = ?", (d.pop("produto_id"),)).fetchone()
        d["produto_codigo"] = p[0] if p else None
    if tabela == "desafio_resultados":
        p = con.execute("SELECT data FROM desafios WHERE id = ?", (d.pop("desafio_id"),)).fetchone()
        d["desafio_data"] = p[0] if p else None
    if tabela == "fechamento_caixa":  # o dinheiro contado vai junto (Painel web); a contagem completa viaja em fechamento_contagem
        c = con.execute("SELECT valor_contado FROM fechamento_contagem WHERE data = ? AND forma_pagamento = 'DINHEIRO'", (d["data"],)).fetchone()
        d["contado_dinheiro"] = c[0] if c else None
    return d


def montar_evento(con, linha):
    ev = {"eid": linha["eid"], "tabela": linha["tabela"], "uid": linha["uid"], "ts": linha["ts"]}
    d = None if linha["op"] == "D" else _dados_da_linha(con, linha["tabela"], linha["uid"])
    if d is None:  # apagada (ou apagada depois de enfileirar): manda como exclusão
        return {**ev, "op": "D"}
    return {**ev, "op": linha["op"], "dados": d}


try:  # o Windows de alguns PCs traz uma raiz vencida e o Python recusa o certificado da Cloudflare: usa as raizes do certifi
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:  # noqa: BLE001
    _CTX = None


class ErroRede(Exception):
    pass


class ChaveInvalida(Exception):
    pass


def _conectar(caminho):
    con = sqlite3.connect(caminho, timeout=10)
    con.row_factory = sqlite3.Row
    return con


class Sincronizador:
    def __init__(self, caminho_banco, filial, url, chave, versao="", registrar_erro=None, intervalo=30, timeout=20, arquivo_disp=None):
        """chave = chave de instalação (a da loja, do config.json). Com arquivo_disp, o computador se registra sozinho uma vez
        (POST /registrar) e passa a usar a chave PRÓPRIA guardada nesse arquivo (revogável pelo admin, abre todas as lojas)."""
        self.caminho, self.filial = caminho_banco, filial
        self.url, self.chave, self.versao = (url or "").rstrip("/"), chave or "", versao
        self.arquivo_disp = arquivo_disp
        self.disp = None  # {"id", "nome", "chave", "lojas"} depois do registro
        self.nome_pc = socket.gethostname()
        self.registrar_erro = registrar_erro or (lambda o, e: None)
        self.intervalo, self.timeout = intervalo, timeout
        self._ultimo = {}  # t138: quando rodou cada chamada espacada (saldos, batimento)
        self._parar = threading.Event()
        self._acordar = threading.Event()
        self._lock = threading.Lock()
        self.estado = {"configurado": bool(self.url and self.chave), "online": None, "ultima_ok": "", "ultima_tentativa": "",
                       "pendentes": 0, "com_erro": 0, "ultimo_erro": "", "enviados": 0, "status": "desligado"}
        self.dormir_ate = 0.0

    # --- HTTP -----------------------------------------------------------------------------------------------
    def http(self, metodo, caminho, corpo=None, aceita=(400, 413)):
        dados = None if corpo is None else json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        chave = self.disp["chave"] if self.disp else self.chave
        req = urllib.request.Request(self.url + caminho, data=dados, method=metodo, headers={
            "Authorization": "Bearer " + chave, "Content-Type": "application/json", "User-Agent": "Vitrine-Sync/2",
            "X-Loja": self.filial})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=_CTX) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
                msg = {}
            if e.code == 401:
                raise ChaveInvalida("este computador foi desligado da nuvem (chave recusada). Avise o suporte." if self.disp
                                    else "chave da loja recusada pelo portão") from e
            if e.code in aceita:
                return e.code, msg
            raise ErroRede(f"portão respondeu {e.code}") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ErroRede(str(e)) from e

    # --- envio ----------------------------------------------------------------------------------------------
    def enviar_fila(self, max_lotes=None, ao_lote=None):
        """Esvazia a fila em lotes. Devolve quantos eventos o portão confirmou. Levanta ErroRede/ChaveInvalida."""
        total, lotes = 0, 0
        con = _conectar(self.caminho)
        try:
            while max_lotes is None or lotes < max_lotes:
                linhas = con.execute("SELECT * FROM fila_envio WHERE enviado_em IS NULL AND erro IS NULL ORDER BY id LIMIT ?",
                                     (LOTE,)).fetchall()
                if not linhas:
                    break
                total += self._enviar_lote(con, linhas)
                lotes += 1
                time.sleep(float(os.environ.get("SINCRO_PAUSA", 0)))  # só para teste (dá tempo de matar o processo)
                if ao_lote:
                    ao_lote(total)
        finally:
            con.close()
        return total

    def _enviar_lote(self, con, linhas):
        eventos = [montar_evento(con, l) for l in linhas]
        status, r = self.http("POST", "/eventos", {"eventos": eventos})
        if status != 200:
            if len(linhas) == 1:  # um evento que o portão recusa de vez: isola, avisa, não trava a fila
                self._marcar_erro(con, linhas[0]["eid"], str(r.get("erro", status)))
                return 0
            return sum(self._enviar_lote(con, [l]) for l in linhas)  # acha o ruim enviando um a um
        agora = agora_utc()
        con.executemany("UPDATE fila_envio SET enviado_em = ?, tentativas = tentativas + 1 WHERE eid = ?",
                        [(agora, e) for e in r["aceitos"]])
        for rej in r.get("rejeitados", []):
            self._marcar_erro(con, rej["eid"], rej["motivo"], confirmar=False)
        con.commit()  # só depois da confirmação do portão
        return len(r["aceitos"])

    def _marcar_erro(self, con, eid, motivo, confirmar=True):
        con.execute("UPDATE fila_envio SET erro = ?, tentativas = tentativas + 1 WHERE eid = ?", (motivo[:200], eid))
        if confirmar:
            con.commit()
        self.registrar_erro("sync: evento recusado pelo portão", Exception(f"{eid}: {motivo}"))
        try:
            self.http("POST", "/log", {"nivel": "erro", "versao": self.versao, "msg": f"evento {eid} recusado: {motivo}"})
        except (ErroRede, ChaveInvalida):
            pass

    # --- registro automático do computador (sem tela) ----------------------------------------------------------
    def garantir_dispositivo(self):
        """Lê a chave própria deste computador; se ainda não tem, pede uma ao portão (uma vez só). Se o admin revogar, a
        chave própria passa a ser recusada (401) e o programa NÃO se registra de novo sozinho."""
        if self.disp or not self.arquivo_disp:
            return
        with _TRAVA_DISP:
            try:
                with open(self.arquivo_disp, encoding="utf-8") as f:
                    self.disp = json.load(f)
            except (OSError, ValueError):
                status, r = self.http("POST", "/registrar", {"nome": self.nome_pc}, aceita=(400, 403, 404))
                if status != 200:
                    return  # portão antigo (sem /registrar): segue com a chave da loja
                os.makedirs(os.path.dirname(self.arquivo_disp), exist_ok=True)
                tmp = self.arquivo_disp + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({k: r[k] for k in ("id", "nome", "chave", "lojas")}, f)
                os.replace(tmp, self.arquivo_disp)
                self.disp = r
        con = _conectar(self.caminho)
        try:
            con.execute("UPDATE sync_estado SET disp = ?", (self.disp["id"],))
            con.commit()
        finally:
            con.close()

    # --- sincronização nos dois sentidos: puxa TUDO o que mudou na loja (de qualquer computador) ------------------
    def puxar(self):
        """Puxa em páginas desde o último seq. Na 1ª carga (réplica nova) mostra o progresso em self.estado['carga']."""
        con = _conectar(self.caminho)
        try:
            primeira = (con.execute("SELECT valor FROM config WHERE chave = 'sync_baixado'").fetchone() or [""])[0] != "1"
            contar = primeira
            while True:
                desde = int((con.execute("SELECT valor FROM config WHERE chave = 'sync_seq_tudo'").fetchone() or ["0"])[0])
                status, r = self.http("GET", f"/pull?desde={desde}&limite={1000 if primeira else 300}" + ("&contar=1" if contar else ""))
                if status == 400 and "tabela" in str(r.get("erro", "")):
                    return self._puxar_antigo(con)  # portão ainda sem a sincronização de 2 sentidos
                if status != 200:
                    raise ErroRede(f"pull: {r.get('erro', status)}")
                if contar and r.get("restantes") is not None:
                    self.estado["carga"] = {"feito": 0, "total": int(r["restantes"]), "primeira": primeira}
                    contar = False
                regs = [dict(zip(r["cols"], l)) for l in r["rows"]]
                aplicar_registros(con, regs, r.get("nomes", {}), carga=primeira)
                con.execute("INSERT INTO config (chave, valor) VALUES ('sync_seq_tudo', ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                            (str(r["proximo"]),))
                con.commit()
                if self.estado.get("carga"):
                    self.estado["carga"]["feito"] += len(regs)
                if not r["mais"]:
                    break
            if primeira:
                con.execute("INSERT INTO config (chave, valor) VALUES ('sync_baixado', '1') ON CONFLICT(chave) DO UPDATE SET valor = '1'")
                con.commit()
            self.estado["carga"] = None
            self._puxar_saldos(con)
        finally:
            con.close()

    def _puxar_antigo(self, con):
        try:
            for tabela, aplicar in (("produtos", _aplicar_produto), ("transferencias", _aplicar_transferencia)):
                while True:
                    chave = f"sync_seq_{tabela}"
                    desde = int((con.execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone() or ["0"])[0])
                    status, r = self.http("GET", f"/pull?tabela={tabela}&desde={desde}")
                    if status != 200:
                        raise ErroRede(f"pull {tabela}: {r.get('erro', status)}")
                    _aplicando(con, lambda: [aplicar(con, x) for x in r["registros"]])
                    con.execute("INSERT INTO config (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                                (chave, str(r["proximo"])))
                    con.commit()
                    if not r["mais"]:
                        break
            self._puxar_saldos(con)
        finally:
            pass

    # --- pedidos da loja online -------------------------------------------------------------------------------
    def puxar_pedidos(self):
        """Traz os pedidos desta filial (novos e mudados). Pedido entregue baixa o estoque local, uma vez só."""
        con = _conectar(self.caminho)
        try:
            while True:
                desde = int((con.execute("SELECT valor FROM config WHERE chave = 'sync_seq_pedidos'").fetchone() or ["0"])[0])
                status, r = self.http("GET", f"/pedidos?desde={desde}")
                if status != 200:
                    raise ErroRede(f"pedidos: {r.get('erro', status)}")
                for p in r["pedidos"]:
                    pedidos_dados.aplicar_pedido(con, self.filial, p, self.registrar_erro)
                con.execute("INSERT INTO config (chave, valor) VALUES ('sync_seq_pedidos', ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                            (str(r["proximo"]),))
                con.commit()
                if not r["mais"]:
                    break
        finally:
            con.close()

    def puxar_pedidos_seguro(self):
        """Falha nos pedidos (ex.: portão antigo sem a rota) não derruba a sincronização de vendas e estoque."""
        try:
            self.puxar_pedidos()
        except ChaveInvalida:
            raise
        except (ErroRede, sqlite3.Error, KeyError, ValueError) as e:
            self.estado["erro_pedidos"] = str(e)[:200]

    def bairros_entrega(self):
        """Lista completa de bairros do portão (inclui desligados). Devolve (lista, erro)."""
        try:
            status, r = self.http("GET", "/entrega")
        except (ErroRede, ChaveInvalida) as e:
            return None, "Sem conexão com a nuvem agora: " + str(e)
        return (r["bairros"], "") if status == 200 else (None, str(r.get("erro", status)))

    def gravar_bairros(self, bairros):
        """Grava bairros e taxas no portão (o site passa a cobrar a taxa nova). Devolve (ok, erro)."""
        try:
            status, r = self.http("PUT", "/entrega", {"bairros": bairros})
        except (ErroRede, ChaveInvalida) as e:
            return False, "Sem conexão com a nuvem agora: " + str(e)
        return (True, "") if status == 200 else (False, str(r.get("erro", status)))

    def mudar_pedido(self, pedido_id, novo_status):
        """Pede ao portão para mudar o status (precisa de internet) e já traz o resultado. Devolve (ok, erro)."""
        try:
            status, r = self.http("PATCH", f"/pedidos/{pedido_id}", {"status": novo_status}, aceita=(400, 403, 404, 409, 413))
        except ErroRede:
            return False, "Sem internet agora. Tente de novo em instantes; o pedido não foi alterado."
        except ChaveInvalida:
            return False, "A chave da nuvem foi recusada. Avise o suporte."
        if status != 200:
            return False, str(r.get("erro", "O portão recusou a mudança."))
        self.puxar_pedidos_seguro()
        return True, ""

    def _a_cada(self, nome, segundos):
        """t138: True no máximo 1 vez a cada `segundos` (o banco central cobra cada linha lida; isto não precisa ser a cada ciclo)."""
        if time.monotonic() - self._ultimo.get(nome, -1e9) < segundos:
            return False
        self._ultimo[nome] = time.monotonic()
        return True

    def _puxar_saldos(self, con):
        outras = [f for f in ("jardins", "centro") if f != self.filial]
        if len(outras) != 1:
            return
        # t139: este PC já tem a réplica da outra loja (<pasta>\<outra>.db, sincronizada pelo laço dela): o estoque dela sai
        # de lá, sem ler o banco central. Só sem a réplica (nuvem só desta loja) pergunta ao portão, a cada 10 min.
        local = os.path.join(os.path.dirname(os.path.abspath(self.caminho)), f"{outras[0]}.db")
        if os.path.exists(local):
            if not self._a_cada("saldos", 60):
                return
            try:
                o = sqlite3.connect(f"file:{local}?mode=ro", uri=True, timeout=5)
                try:
                    linhas = o.execute("SELECT p.codigo, e.quantidade FROM estoque e JOIN produtos p ON p.id = e.produto_id "
                                       "WHERE e.filial = ?", (outras[0],)).fetchall()
                finally:
                    o.close()
            except sqlite3.Error:
                return  # réplica ainda sem as tabelas de estoque: tenta no próximo minuto
            saldos = [{"codigo": c, "quantidade": q} for c, q in linhas]
        else:
            if not self._a_cada("saldos", 600):
                return
            status, r = self.http("GET", f"/saldos?filial={outras[0]}", aceita=(400, 413, 503))  # 503 = freio da cota: não é falta de rede
            if status != 200:
                return
            saldos = r["saldos"]
        nomes = dict(con.execute("SELECT codigo, nome FROM produtos").fetchall())
        quando = datetime.now().strftime("%d/%m/%Y %H:%M")
        con.execute("DELETE FROM estoque_outra WHERE filial = ?", (outras[0],))
        con.executemany("INSERT INTO estoque_outra (filial, codigo, nome, quantidade, atualizado) VALUES (?,?,?,?,?)",
                        [(outras[0], s["codigo"], nomes.get(s["codigo"]), int(s["quantidade"] or 0), quando)
                         for s in saldos if s["codigo"]])
        con.commit()

    def batimento(self):
        if not self._a_cada("batimento", 900):  # "estou vivo" no painel: a cada 15 min (t139: cada um = 1 escrita no banco central)
            return
        con = _conectar(self.caminho)
        try:
            pend = pendentes(con)
        finally:
            con.close()
        _st, r = self.http("POST", "/batimento", {"versao": self.versao, "pendentes": pend, "ultima_sync": self.estado["ultima_ok"],
                                         "detalhe": {"computador": socket.gethostname(), "erros": self.estado["com_erro"],
                                                     "disp": (self.disp or {}).get("id")}})
        if isinstance(r, dict) and isinstance(r.get("uso"), dict):
            self.estado["uso_nuvem"] = r["uso"]  # t139: % da cota mensal do banco central (a barra avisa a partir de 50%)

    # --- ciclo e laço ---------------------------------------------------------------------------------------
    def ciclo(self):
        """Um ciclo completo. Nunca levanta: erro de rede vira estado 'sem conexão' e a fila fica intacta."""
        if not (self.url and self.chave):
            return False
        self.estado["ultima_tentativa"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        try:
            self.garantir_dispositivo()
            n = self.enviar_fila()
            self.puxar()
            while _ERROS_APLICAR:
                self.registrar_erro("sync: registro de outro computador não aplicado", Exception(_ERROS_APLICAR.pop(0)))
            self.puxar_pedidos_seguro()
            self.batimento()
            with self._lock:
                self.estado.update(online=True, ultima_ok=datetime.now().strftime("%d/%m/%Y %H:%M:%S"), ultimo_erro="",
                                   status="ok", enviados=self.estado["enviados"] + n)
            self.dormir_ate = 0
            ok = True
        except ChaveInvalida as e:
            self.estado.update(online=True, status="chave", ultimo_erro=str(e))
            ok = False
        except ErroRede as e:  # a 1ª carga interrompida mantém o painel "baixando" (estado["carga"]) e continua no próximo ciclo
            self.estado.update(online=False, status="sem conexão", ultimo_erro=str(e)[:200])
            ok = False
        except Exception as e:  # noqa: BLE001  -- erro inesperado: registra, a fila continua guardada
            self.registrar_erro("sincronização", e)
            self.estado.update(status="erro", ultimo_erro=str(e)[:200])
            ok = False
        self.atualizar_contagens()
        return ok

    def atualizar_contagens(self):
        try:
            con = _conectar(self.caminho)
            try:
                self.estado["pendentes"] = pendentes(con)
                self.estado["com_erro"] = con.execute("SELECT COUNT(*) FROM fila_envio WHERE erro IS NOT NULL").fetchone()[0]
            finally:
                con.close()
        except sqlite3.Error:
            pass

    def iniciar_laco(self):
        if not (self.url and self.chave):
            self.estado["status"] = "não configurado"
            return
        self.estado["status"] = "iniciando"

        def laco():
            espera = self.intervalo
            while not self._parar.is_set():
                ok = self.ciclo()
                espera = self.intervalo if ok else min(max(espera * 2, 15), 300)  # recuo: 15 s ... 5 min
                fim = time.time() + espera
                while time.time() < fim and not self._acordar.is_set():
                    self._acordar.wait(1)
                    if ok and self._tem_pendente():  # algo novo neste PC: envia já (os outros veem em segundos)
                        break
                self._acordar.clear()
        threading.Thread(target=laco, daemon=True, name="sincro").start()

    def _tem_pendente(self):
        try:
            con = _conectar(self.caminho)
            try:
                return con.execute("SELECT 1 FROM fila_envio WHERE enviado_em IS NULL AND erro IS NULL LIMIT 1").fetchone() is not None
            finally:
                con.close()
        except sqlite3.Error:
            return False

    def parar(self):
        self._parar.set()
        self._acordar.set()


# --------------------------------------------------------------------------------------------------------------
# Aplicar o que veio do portão. 'aplicando=1' desliga os gatilhos de fila: o que chega não volta (sem eco).
# --------------------------------------------------------------------------------------------------------------
def _aplicando(con, fn):
    try:
        con.execute("UPDATE sync_estado SET aplicando = 1")
        fn()
        con.execute("UPDATE sync_estado SET aplicando = 0")
        con.commit()
    except Exception:
        con.rollback()  # desfaz também o aplicando=1
        raise


_TRAVA_DISP = threading.Lock()
_NOMES_DISP = {}


class _Espera(Exception):
    """O registro aponta para outro que ainda não chegou (ex.: resultado de um desafio que veio depois). Fica guardado."""


def _quem(disp, nomes):
    if disp in nomes:
        _NOMES_DISP[disp] = nomes[disp]
    nome = _NOMES_DISP.get(disp) or (("PC da loja " + disp[5:]) if (disp or "").startswith("loja-") else disp or "outro computador")
    return "sincronizado de " + nome


def aplicar_registros(con, regs, nomes=None, carga=False):
    """Aplica uma página do /pull numa transação. carga=True (1ª carga da réplica): sem auditoria linha a linha."""
    nomes = nomes or {}

    def tudo():
        if carga:
            con.execute("UPDATE sync_estado SET aplicando = 2")
        for reg in regs:
            _aplicar_um(con, reg, nomes)
        # os que esperavam um registro "pai" tentam de novo (o pai pode ter chegado nesta página)
        for t, u, js in con.execute("SELECT tabela, uid, reg FROM sync_espera").fetchall():
            if _aplicar_um(con, json.loads(js), nomes, de_espera=True):
                con.execute("DELETE FROM sync_espera WHERE tabela = ? AND uid = ?", (t, u))
    _aplicando(con, tudo)
    con.execute("UPDATE sync_estado SET quem = ?", (socket.gethostname(),))
    con.commit()


def _aplicar_um(con, reg, nomes, de_espera=False):
    """Um registro do portão. Devolve False se ficou esperando. Erro de um registro não trava os outros."""
    t = reg["tabela"]
    if t not in TABELAS:
        return True
    con.execute("UPDATE sync_estado SET hlc = MAX(COALESCE(hlc, ''), ?), quem = ?", (reg["ts"], _quem(reg.get("disp"), nomes)))
    con.execute("SAVEPOINT reg")
    try:
        if t == "produtos":
            _aplicar_produto(con, reg)
        elif t == "transferencias":
            _aplicar_transferencia(con, reg)
        else:
            _aplicar_generico(con, reg)
        con.execute("RELEASE reg")
        return True
    except _Espera:
        con.execute("ROLLBACK TO reg")
        con.execute("RELEASE reg")
        if not de_espera:
            con.execute("INSERT OR REPLACE INTO sync_espera (tabela, uid, reg) VALUES (?,?,?)", (t, reg["uid"], json.dumps(reg)))
        return False
    except sqlite3.Error as e:
        con.execute("ROLLBACK TO reg")
        con.execute("RELEASE reg")
        _ERROS_APLICAR.append(f"{t} {reg['uid']}: {e}")
        return True


_ERROS_APLICAR = []  # o laço registra no log de erros


def _saldo_por_contagem(con, pid, filial):
    """Saldo = ÚLTIMA contagem (por ts/computador, a mesma ordem do LWW) + movimentos depois dela. Assim duas contagens
    offline do mesmo produto não se somam: vale a mais recente, igual em todos os PCs. False se não há contagem absoluta."""
    c = con.execute("SELECT contado, sync_em, sync_disp FROM movimentos WHERE produto_id = ? AND filial = ? AND tipo = 'contagem' "
                    "AND contado IS NOT NULL ORDER BY sync_em DESC, sync_disp DESC LIMIT 1", (pid, filial)).fetchone()
    if c is None:
        return False
    soma = con.execute("SELECT COALESCE(SUM(quantidade), 0) FROM movimentos WHERE produto_id = ? AND filial = ? "
                       "AND (sync_em > ? OR (sync_em = ? AND COALESCE(sync_disp,'') > ?))",
                       (pid, filial, c[1], c[1], c[2] or "")).fetchone()[0]
    con.execute("UPDATE estoque SET quantidade = ? WHERE produto_id = ? AND filial = ?", (c[0] + soma, pid, filial))
    return True


def _aplicar_generico(con, reg):
    """Última escrita vence: (ts, computador) maior ganha -- a mesma ordem do portão, então todos convergem."""
    t, uid = reg["tabela"], reg["uid"]
    u = TABELAS[t]
    novo = (reg["ts"], reg.get("disp") or "")
    local = con.execute(f"SELECT rowid AS rid, sync_em, sync_disp FROM {t} WHERE {u} = ?", (uid,)).fetchone()
    if local is not None:
        if (local["sync_em"] or "", local["sync_disp"] or "") >= novo:
            return
        if t == "movimentos":
            return  # movimento de estoque não muda depois de feito
    else:
        lap = con.execute("SELECT ts, disp FROM sync_lapide WHERE tabela = ? AND uid = ?", (t, uid)).fetchone()
        if lap is not None and (lap[0], lap[1] or "") >= novo:
            return  # apagado aqui depois disso
    if reg["apagado"]:
        if local is not None:
            con.execute(f"DELETE FROM {t} WHERE rowid = ?", (local["rid"],))
        con.execute("INSERT OR REPLACE INTO sync_lapide (tabela, uid, ts, disp) VALUES (?,?,?,?)", (t, uid, *novo))
        return
    d = json.loads(reg["dados"]) if isinstance(reg["dados"], str) else dict(reg["dados"])
    d.pop("contado_dinheiro", None)
    if t in ("movimentos", "estoque"):
        p = con.execute("SELECT id FROM produtos WHERE codigo = ?", (d.pop("produto_codigo", None),)).fetchone()
        if p is None:
            raise _Espera()
        d["produto_id"] = p[0]
    if t == "estoque":
        d = {"produto_id": d["produto_id"], "filial": d["filial"], "minimo": d.get("minimo", 0)}
        if local is None:  # a linha do estoque pode existir sem uid (criada por um movimento): junta pela chave natural
            r = con.execute("SELECT rowid AS rid, sync_em, sync_disp FROM estoque WHERE produto_id = ? AND filial = ?", (d["produto_id"], d["filial"])).fetchone()
            if r is not None:
                if (r["sync_em"] or "", r["sync_disp"] or "") >= novo:
                    return
                con.execute("UPDATE estoque SET minimo = ?, uid = ?, sync_em = ?, sync_disp = ? WHERE rowid = ?", (d["minimo"], uid, *novo, r["rid"]))
                return
    if t == "desafio_resultados":
        p = con.execute("SELECT id FROM desafios WHERE data = ?", (d.pop("desafio_data", None),)).fetchone()
        if p is None:
            raise _Espera()
        d["desafio_id"] = p[0]
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({t})")} - set(_COLS_SYNC) - {"id", u}
    d = {k: v for k, v in d.items() if k in cols}
    con.execute("DELETE FROM sync_lapide WHERE tabela = ? AND uid = ?", (t, uid))
    if local is not None:
        con.execute(f"UPDATE {t} SET " + ", ".join(f'"{k}" = ?' for k in d) + ", sync_em = ?, sync_disp = ? WHERE rowid = ?",
                    (*d.values(), *novo, local["rid"]))
        return
    con.execute(f"INSERT INTO {t} (" + ", ".join(f'"{k}"' for k in d) + f", {u}, sync_origem, sync_em, sync_disp) VALUES ("
                + ",".join("?" * (len(d) + 4)) + ")", (*d.values(), uid, reg.get("origem"), *novo))
    if t == "movimentos":  # o saldo acompanha o movimento que veio de outro computador
        con.execute("INSERT OR IGNORE INTO estoque (produto_id, filial) VALUES (?,?)", (d["produto_id"], d["filial"]))
        if not _saldo_por_contagem(con, d["produto_id"], d["filial"]):
            con.execute("UPDATE estoque SET quantidade = quantidade + ? WHERE produto_id = ? AND filial = ?",
                        (int(d["quantidade"]), d["produto_id"], d["filial"]))


def _aplicar_produto(con, reg):
    if reg["apagado"]:
        return  # produto não se apaga (só inativa)
    d = json.loads(reg["dados"]) if isinstance(reg["dados"], str) else reg["dados"]
    local = con.execute("SELECT sync_em FROM produtos WHERE codigo = ?", (d["codigo"],)).fetchone()
    campos = (d["nome"], d.get("categoria"), d.get("preco"), 1 if d.get("ativo", 1) else 0, d.get("site_id"),
              1 if d.get("ativo_site") else 0, d.get("foto"), d.get("descricao_site"), d.get("preco_site"), d.get("marca"),
              d.get("grupo_site"), d.get("variacao"))
    nomes = "nome, categoria, preco, ativo, site_id, ativo_site, foto, descricao_site, preco_site, marca, grupo_site, variacao"
    if local is None:
        con.execute(f"INSERT INTO produtos ({nomes}, codigo, uid, sync_origem, sync_em) VALUES ({','.join('?' * 16)})",
                    (*campos, d["codigo"], reg["uid"], reg["origem"], reg["ts"]))
    elif (local["sync_em"] or "") < reg["ts"]:  # o mais recente vence
        con.execute("UPDATE produtos SET " + ", ".join(f"{c.strip()}=?" for c in nomes.split(",")) + ", uid=?, sync_origem=?, sync_em=? WHERE codigo=?",
                    (*campos, reg["uid"], reg["origem"], reg["ts"], d["codigo"]))


def _aplicar_transferencia(con, reg):
    if reg["apagado"]:
        return
    d = json.loads(reg["dados"]) if isinstance(reg["dados"], str) else reg["dados"]
    local = con.execute("SELECT status FROM transferencias WHERE uuid = ?", (reg["uid"],)).fetchone()
    if local is None:
        con.execute("INSERT INTO transferencias (uuid, produto_codigo, produto_nome, origem, destino, quantidade, status, "
                    "pedido_em, enviada_em, recebida_em, obs, sync_origem, sync_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (reg["uid"], d["produto_codigo"], d.get("produto_nome"), d["origem"], d["destino"], d["quantidade"], d["status"],
                     d.get("pedido_em"), d.get("enviada_em"), d.get("recebida_em"), d.get("obs"), reg["origem"], reg["ts"]))
    elif _RANK.get(d["status"], 0) > _RANK.get(local["status"], 0):  # só avança; quem executa o passo é a loja dona dele
        con.execute("UPDATE transferencias SET status=?, enviada_em=COALESCE(?, enviada_em), recebida_em=COALESCE(?, recebida_em), "
                    "sync_em=? WHERE uuid=?", (d["status"], d.get("enviada_em"), d.get("recebida_em"), reg["ts"], reg["uid"]))


# --------------------------------------------------------------------------------------------------------------
# Conferência local x central (mesmos SQL do Worker). Só passa se tudo bater, centavo a centavo.
# --------------------------------------------------------------------------------------------------------------
_MES = "substr({d},-4)||'-'||substr({d},-7,2)"


def numeros_locais(con):
    def mapa(sql):
        return {str(k): int(v or 0) for k, v in con.execute(sql).fetchall()}
    one = lambda sql: int(con.execute(sql).fetchone()[0] or 0)  # noqa: E731
    return {
        "vendas": {"total": one("SELECT COUNT(*) FROM vendas"),
                   "por_ano": mapa("SELECT substr(data_venda,-4), COUNT(*) FROM vendas GROUP BY 1"),
                   "centavos_por_mes": mapa(f"SELECT {_MES.format(d='data_venda')}, SUM(CAST(ROUND(valor*100) AS INTEGER)) FROM vendas GROUP BY 1"),
                   "por_pagamento": mapa("SELECT tipo_pagamento, COUNT(*) FROM vendas GROUP BY 1")},
        "despesas": {"total": one("SELECT COUNT(*) FROM despesas"),
                     "centavos_por_mes": mapa(f"SELECT {_MES.format(d='data_despesa')}, SUM(CAST(ROUND(valor*100) AS INTEGER)) FROM despesas GROUP BY 1")},
        "movimentos": {"total": one("SELECT COUNT(*) FROM movimentos"), "soma_quantidade": one("SELECT SUM(quantidade) FROM movimentos")},
        "eventos_enviados": one("SELECT COUNT(*) FROM fila_envio WHERE enviado_em IS NOT NULL"),
    }


def comparar(local, central):
    """Lista de (item, local, central, igual)."""
    linhas = []

    def cmp(item, a, b):
        linhas.append((item, a, b, "SIM" if a == b else "NAO"))

    def cmp_mapa(prefixo, a, b):
        for k in sorted(set(a) | set(b)):
            cmp(f"{prefixo}[{k}]", a.get(k, 0), b.get(k, 0))
    for t in ("vendas", "despesas"):
        cmp(f"{t}.total", local[t]["total"], central[t]["total"])
        cmp_mapa(f"{t}.centavos_por_mes", local[t]["centavos_por_mes"], central[t]["centavos_por_mes"])
    cmp_mapa("vendas.por_ano", local["vendas"]["por_ano"], central["vendas"]["por_ano"])
    cmp_mapa("vendas.por_pagamento", local["vendas"]["por_pagamento"], central["vendas"]["por_pagamento"])
    cmp("movimentos.total", local["movimentos"]["total"], central["movimentos"]["total"])
    cmp("movimentos.soma_quantidade", local["movimentos"]["soma_quantidade"], central["movimentos"]["soma_quantidade"])
    cmp("eventos (fila enviada x portão)", local["eventos_enviados"], central["eventos"])
    cmp("eventos repetidos no portão", 0, central["eventos"] - central["eventos_distintos"])
    return linhas


def conferir(caminho_banco, url, chave, filial, csv_saida=None):
    s = Sincronizador(caminho_banco, filial, url, chave)
    con = _conectar(caminho_banco)
    try:
        pend = pendentes(con)
        local = numeros_locais(con)
    finally:
        con.close()
    status, central = s.http("GET", "/conferencia")
    linhas = comparar(local, central)
    if pend:
        linhas.insert(0, ("fila: eventos ainda pendentes (precisa ser 0)", pend, 0, "NAO"))
    if csv_saida:
        with open(csv_saida, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["item", "local", "central", "igual"])
            w.writerows(linhas)
    return all(l[3] == "SIM" for l in linhas), linhas


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("comando", choices=["enviar", "conferir"])
    ap.add_argument("--banco", required=True)
    ap.add_argument("--filial", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--chave", required=True)
    ap.add_argument("--csv")
    a = ap.parse_args(argv)
    if a.comando == "enviar":
        con = _conectar(a.banco)
        preparar(con, a.filial)
        con.close()
        s = Sincronizador(a.banco, a.filial, a.url, a.chave)
        t0 = time.time()
        n = s.enviar_fila(ao_lote=lambda x: print(f"\r{x} eventos confirmados", end="", flush=True) if x % 1000 < LOTE else None)
        print(f"\n{n} eventos em {time.time() - t0:.1f}s")
        return 0
    ok, linhas = conferir(a.banco, a.url, a.chave, a.filial, a.csv)
    ruins = [l for l in linhas if l[3] != "SIM"]
    print(f"{len(linhas)} conferências, {len(ruins)} divergentes -> {'APROVADO' if ok else 'REPROVADO'}")
    for l in ruins[:30]:
        print("  ", l)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
