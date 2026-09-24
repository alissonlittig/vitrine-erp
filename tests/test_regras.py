"""Testes das regras de negócio do Vitrine ERP (rodam sem abrir janela).

    pytest -q
"""
import os
import sqlite3
import sys
from datetime import date, datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nucleo_pdv as n  # noqa: E402
from gerar_banco_demo import gerar_banco_demo  # noqa: E402


# --- Leitura de valores digitados no padrão brasileiro -----------------------
@pytest.mark.parametrize("texto, esperado", [
    ("150", 150.0),
    ("150,5", 150.5),
    ("150,50", 150.5),
    ("1.500", 1500.0),          # ponto de milhar NÃO vira decimal
    ("1.500,00", 1500.0),
    ("R$ 1.500,00", 1500.0),
    ("1.250.000,99", 1250000.99),
    ("-10,00", -10.0),
    ("abc", None),
    ("", None),
])
def test_ler_valor_monetario(texto, esperado):
    assert n.ler_valor_monetario(texto) == esperado


# --- Desafio do Dia: bonificação proporcional com teto -----------------------
@pytest.mark.parametrize("dias, vendido, pct, bonus, dias_ok", [
    (25, 125, 100.0, 100.00, 25),   # bateu tudo
    (25, 100, 80.0, 80.00, 20),     # 80% -> R$ 80
    (25, 130, 100.0, 100.00, 25),   # passa da meta: teto de 100%
    (20, 10, 10.0, 10.00, 2),       # 3 num dia + 7 no outro = 2 dias
    (18, 47, 52.2, 52.22, 9),
    (0, 5, 0.0, 0.00, 0),           # mês sem desafio
])
def test_calcular_conclusao_desafio(dias, vendido, pct, bonus, dias_ok):
    r = n.calcular_conclusao_desafio(dias, vendido)
    assert r["percentual"] == pct
    assert r["bonificacao"] == bonus
    assert r["dias_concluidos"] == dias_ok


# --- Normalização de nomes digitados com erro --------------------------------
@pytest.mark.parametrize("bruto, limpo", [("ana", "ANA"), ("ANA-PAULA", "ANAPAULA"), ("ANA'", "ANA"), (" Bia ", "BIA")])
def test_normalizar_nome_vendedor(bruto, limpo):
    assert n.normalizar_nome_vendedor(bruto) == limpo


# --- Senha da Área de Gestão (hash PBKDF2) -----------------------------------
def test_hash_de_senha():
    h = n.gerar_hash_senha("s3nh@", iteracoes=1_000)
    assert "s3nh@" not in h
    assert n.verificar_senha("s3nh@", h)
    assert not n.verificar_senha("errada", h)
    assert not n.verificar_senha("s3nh@", "lixo")


# --- Banco fictício: coerência com as regras do sistema ----------------------
@pytest.fixture(scope="module")
def banco_demo(tmp_path_factory):
    caminho = str(tmp_path_factory.mktemp("demo") / "teste.db")
    gerar_banco_demo(caminho, "centro", hoje=date(2026, 3, 31), verbose=False)
    con = sqlite3.connect(caminho)
    yield con
    con.close()


def test_parcelas_somam_valor_da_venda(banco_demo):
    grupos = {}
    for valor, vend, dv, hora, tipo in banco_demo.execute(
            "SELECT valor, vendedor, data_venda, horario, tipo_pagamento FROM vendas WHERE tipo_pagamento LIKE 'CRÉDITO _X (%'"):
        chave = (vend, dv, hora, tipo[:10])
        grupos.setdefault(chave, []).append((tipo, valor))
    assert grupos
    for parcelas in grupos.values():
        n_total = int(parcelas[0][0][-2])
        assert len(parcelas) % n_total == 0            # nenhuma parcela perdida
        for _, v in parcelas:
            assert round(v, 2) == v                    # centavos exatos, sem dízima


def test_vencimentos_coerentes(banco_demo):
    fmt = "%d/%m/%Y"
    for dv, dvenc, tipo in banco_demo.execute("SELECT data_venda, data_vencimento, tipo_pagamento FROM vendas"):
        dias = (datetime.strptime(dvenc, fmt) - datetime.strptime(dv, fmt)).days
        if tipo in ("DINHEIRO", "PIX", "DÉBITO", "RECEBIMENTO"):
            assert dias == 0
        elif tipo == "CRÉDITO A V.":
            assert dias == 30
        else:
            assert dias in (30, 60, 90)


def test_sem_valores_invalidos(banco_demo):
    assert banco_demo.execute("SELECT COUNT(*) FROM vendas WHERE valor <= 0 OR vendedor IS NULL OR vendedor = ''").fetchone()[0] == 0
    assert banco_demo.execute("SELECT COUNT(*) FROM despesas WHERE valor <= 0").fetchone()[0] == 0


# --- Parcelamento com centavos exatos ----------------------------------------
@pytest.mark.parametrize("valor, n_parc, esperado", [
    (431.50, 3, [143.84, 143.83, 143.83]),
    (100.00, 3, [33.34, 33.33, 33.33]),
    (99.99, 2, [50.00, 49.99]),
    (60.00, 2, [30.00, 30.00]),
])
def test_dividir_em_parcelas(valor, n_parc, esperado):
    parcelas = n.dividir_em_parcelas(valor, n_parc)
    assert parcelas == esperado
    assert round(sum(parcelas), 2) == valor
