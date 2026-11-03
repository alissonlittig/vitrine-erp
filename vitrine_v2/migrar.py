# =============================================================================
# MIGRAÇÃO do banco antigo (cosmeticos_vendas.db) para o banco oficial local
# =============================================================================
#   python demo_ui/migrar.py --filial jardins --origem CAMINHO\cosmeticos_vendas.db [--destino C:\Vitrine\dados\jardins.db]
#
# O banco antigo é aberto SÓ para leitura. A cópia é feita num arquivo provisório, recebe o schema novo e só vira o
# banco oficial se TUDO bater com o original (contagem e conteúdo de cada tabela, soma de vendas por mês, por
# pagamento, por produto e por vendedor, soma de despesas por mês). Não bateu: o provisório fica como
# <destino>.invalido, o destino não é criado e nada do original é alterado.
# O relatório antes/depois fica em CSV ao lado do banco novo (migracao_<filial>_<data>.csv).
import argparse
import csv
import hashlib
import math
import os
import sqlite3
import sys
from datetime import datetime

import dados as D

PASTA_PADRAO = r"C:\Vitrine\dados"


def _tabelas(con):
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _colunas(con, t):
    return [r[1] for r in con.execute(f"PRAGMA table_info({t})")]


def _soma_por(con, tabela, col_data, col_valor, chave):
    tot = {}
    for data, valor, grupo in con.execute(f"SELECT {col_data or 'NULL'}, {col_valor}, {chave} FROM {tabela}"):
        k = grupo
        if col_data:
            ano, mes = D.ano_mes_de_data_flexivel(data)
            k = f"{ano}-{mes}"
        tot.setdefault(k, []).append(valor or 0)
    return {k: round(math.fsum(v), 2) for k, v in tot.items()}


def resumo(caminho, colunas_ref=None):
    """Fotografia do banco, só leitura. colunas_ref: {tabela: [colunas]} para comparar só o que o original tinha."""
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    try:
        r = {"tabelas": {}, "metricas": {}}
        for t in _tabelas(con):
            cols = (colunas_ref or {}).get(t) or _colunas(con, t)
            if colunas_ref is not None and t not in colunas_ref:
                continue
            h = hashlib.sha256()
            n = 0
            for linha in con.execute(f"SELECT {', '.join(cols)} FROM {t} ORDER BY rowid"):
                h.update(repr(linha).encode("utf-8"))
                n += 1
            r["tabelas"][t] = (n, h.hexdigest()[:16], cols)
        if "vendas" in r["tabelas"]:
            m = r["metricas"]
            m["vendas por mês"] = _soma_por(con, "vendas", "data_venda", "valor", "1")
            m["vendas por pagamento"] = _soma_por(con, "vendas", None, "valor", "tipo_pagamento")
            m["vendas por produto"] = _soma_por(con, "vendas", None, "valor", "tipo_produto")
            m["vendas por vendedor"] = _soma_por(con, "vendas", None, "valor", "vendedor")
        if "despesas" in r["tabelas"]:
            r["metricas"]["despesas por mês"] = _soma_por(con, "despesas", "data_despesa", "valor", "1")
        return r
    finally:
        con.close()


def comparar(antes, depois):
    """Lista de (tabela/metrica, chave, antes, depois, ok)."""
    linhas = []
    for t, (n, h, _) in antes["tabelas"].items():
        d = depois["tabelas"].get(t, (None, None, None))
        linhas.append(("tabela: linhas", t, n, d[0], n == d[0]))
        linhas.append(("tabela: conteúdo (hash)", t, h, d[1], h == d[1]))
    for nome, ant in antes["metricas"].items():
        dep = depois["metricas"].get(nome, {})
        for k in sorted(set(ant) | set(dep), key=str):
            linhas.append((nome, k, ant.get(k), dep.get(k), ant.get(k) == dep.get(k)))
    return linhas


def migrar(origem, destino, filial, pasta_relatorio=None):
    """Devolve {"ok", "relatorio", "vendas", "erro"}. Nunca altera a origem nem sobrescreve o destino."""
    origem, destino = os.path.abspath(origem), os.path.abspath(destino)
    if os.path.normcase(origem) == os.path.normcase(destino):
        return {"ok": False, "erro": "Origem e destino são o mesmo arquivo."}
    if os.path.exists(destino):
        return {"ok": False, "erro": f"Já existe um banco em {destino}. Nada foi feito."}
    if not os.path.exists(origem):
        return {"ok": False, "erro": f"Banco de origem não encontrado: {origem}"}
    pasta = os.path.dirname(destino)
    os.makedirs(pasta, exist_ok=True)
    tmp = destino + ".migrando"
    if os.path.exists(tmp):
        os.replace(tmp, tmp + datetime.now().strftime(".%Y%m%d%H%M%S.velho"))
    antes = resumo(origem)
    ref = {t: v[2] for t, v in antes["tabelas"].items()}
    src = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    dados = D.Dados(tmp, filial)  # aplica o schema novo (só acrescenta), journal DELETE, config, auditoria
    try:
        dados.auditar("MIGRACAO", f"de {origem}")
        integro = dados.con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        dados.fechar()
    depois = resumo(tmp, colunas_ref=ref)
    linhas = comparar(antes, depois)
    linhas.append(("integridade do banco novo", "integrity_check", "ok", integro, integro == "ok"))
    tudo_ok = all(l[4] for l in linhas)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    relatorio = os.path.join(pasta_relatorio or pasta, f"migracao_{filial.codigo}_{carimbo}.csv")
    with open(relatorio, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["o que", "chave", "antes (original)", "depois (banco novo)", "confere"])
        for l in linhas:
            w.writerow([l[0], l[1], l[2], l[3], "SIM" if l[4] else "NÃO"])
        w.writerow(["RESULTADO", origem, "", destino, "TUDO CONFERE" if tudo_ok else "DIVERGÊNCIA"])
    if not tudo_ok:
        os.replace(tmp, destino + ".invalido")
        return {"ok": False, "relatorio": relatorio, "erro": "Os números do banco novo não bateram com o original. "
                "O banco novo NÃO foi criado; o original continua intacto. Veja o relatório."}
    os.replace(tmp, destino)
    return {"ok": True, "relatorio": relatorio, "vendas": antes["tabelas"].get("vendas", (0,))[0],
            "linhas": len(linhas)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--filial", required=True, choices=["jardins", "centro"])
    ap.add_argument("--origem", required=True)
    ap.add_argument("--destino")
    a = ap.parse_args(argv)
    from lojas import FILIAIS
    filial = FILIAIS[a.filial]
    destino = a.destino or os.path.join(PASTA_PADRAO, f"{a.filial}.db")
    r = migrar(a.origem, destino, filial)
    print(("OK" if r["ok"] else "FALHOU") + f" - relatório: {r.get('relatorio')}")
    if not r["ok"]:
        print(r["erro"])
    else:
        print(f"{r['vendas']} vendas migradas; {r['linhas']} conferências, todas iguais. Banco: {destino}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
