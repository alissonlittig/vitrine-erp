# =============================================================================
# GERADOR DE BANCO DE DADOS FICTÍCIO (DEMONSTRAÇÃO / PORTFÓLIO)
# =============================================================================
# Cria um banco SQLite com o MESMO esquema do sistema real e preenche com
# dados 100% fictícios, mas com comportamento realista de uma loja de
# cosméticos:
#   * ~2,5 anos de vendas, com sazonalidade (Dia das Mães, Dia dos Namorados,
#     Black Friday, Natal), crescimento anual e picos de horário;
#   * mix de pagamentos (dinheiro, PIX, débito, crédito à vista e parcelado,
#     com as parcelas gravadas exatamente como o sistema grava);
#   * rotatividade de equipe (uma vendedora saiu, outra entrou);
#   * despesas mensais (aluguel, folha, impostos, compras de mercadoria...);
#   * Desafios do Dia, bonificações e fechamentos de caixa recentes.
#
# Os números são gerados com semente fixa: rodar de novo produz o mesmo banco.
#
# Uso direto:  python gerar_banco_demo.py            (gera as duas filiais)
#              python gerar_banco_demo.py centro     (só uma)
# =============================================================================
import calendar
import math
import os
import random
import sys
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# Perfis das filiais (tudo fictício)
# ---------------------------------------------------------------------------
PERFIS = {
    "centro": {
        "semente": 2024,
        "vendas_dia_base": 36,
        "aluguel": 4500.00,
        "equipe": {  # nome: (peso nas vendas, entrou_em, saiu_em)
            "ANA": (1.30, None, None),
            "BEATRIZ": (1.00, None, None),
            "CAMILA": (0.90, date(2024, 8, 1), None),
            "DANIELA": (1.10, None, None),
            "FERNANDO": (0.25, None, None),          # sócio: vende pouco, sem comissão
            "GABRIELA": (0.90, None, date(2024, 7, 31)),  # saiu da loja
        },
    },
    "jardins": {
        "semente": 2025,
        "vendas_dia_base": 24,
        "aluguel": 3200.00,
        "equipe": {
            "BRUNA": (1.20, None, None),
            "CLARA": (1.00, None, None),
            "ELISA": (0.90, date(2025, 3, 1), None),
            "FERNANDO": (0.15, None, None),
            "HELENA": (0.90, None, date(2025, 2, 28)),
        },
    },
}

INICIO = date(2024, 1, 2)
SAZONALIDADE = {1: 0.85, 2: 0.88, 3: 0.95, 4: 0.98, 5: 1.28, 6: 1.12,
                7: 0.95, 8: 1.02, 9: 0.96, 10: 1.00, 11: 1.18, 12: 1.55}
PESO_DIA_SEMANA = {0: 0.85, 1: 0.95, 2: 1.00, 3: 1.00, 4: 1.15, 5: 1.35}  # seg..sáb (domingo fechado)
PESO_HORA = {9: 0.5, 10: 0.9, 11: 1.3, 12: 1.4, 13: 1.0, 14: 1.0, 15: 1.1,
             16: 1.3, 17: 1.4, 18: 1.2, 19: 0.6}
PAGAMENTOS = [("DINHEIRO", 0.27), ("PIX", 0.31), ("DÉBITO", 0.17), ("CRÉDITO A V.", 0.14),
              ("CRÉDITO 2X", 0.06), ("CRÉDITO 3X", 0.03), ("RECEBIMENTO", 0.02)]
PRODUTOS_DESAFIO = [
    "CREME HIDRATANTE CORPORAL 200ML", "PERFUME FLORAL 100ML", "SÉRUM VITAMINA C", "PROTETOR SOLAR FPS 50",
    "SHAMPOO REPARADOR 300ML", "BATOM MATTE", "MÁSCARA DE CÍLIOS", "ÓLEO CORPORAL", "BODY SPLASH",
    "ESFOLIANTE FACIAL", "CONDICIONADOR NUTRITIVO", "BASE LÍQUIDA", "ÁGUA MICELAR", "HIDRATANTE FACIAL",
]
FERIADOS_FECHADO = {(1, 1), (25, 12), (1, 5), (21, 4), (7, 9), (12, 10), (2, 11), (15, 11)}


def _hora_aleatoria(rng):
    horas, pesos = zip(*PESO_HORA.items())
    h = rng.choices(horas, pesos)[0]
    t = datetime(2000, 1, 1, h, rng.randint(0, 59), rng.randint(0, 59))
    return t.strftime("%I:%M:%S %p").lstrip("0")  # mesmo formato gravado pelo sistema


def _valor_venda(rng, produto):
    # Distribuição log-normal: muitas vendas pequenas, poucas grandes.
    mediana = 46.0 if produto == "PERFUMARIA" else 32.0
    v = rng.lognormvariate(math.log(mediana), 0.62)
    v = min(v, 1400.0)
    fim = rng.choice([0.00, 0.90, 0.50, 0.99, 0.00, 0.90])
    return round(max(int(v), 5) + fim, 2)


def _ativo(nome, dia, equipe):
    _, entrou, saiu = equipe[nome]
    return (entrou is None or dia >= entrou) and (saiu is None or dia <= saiu)


def _mes_seguinte(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _fmt(d):
    return d.strftime("%d/%m/%Y")


def gerar_banco_demo(caminho, filial="centro", equipe_inicial=None, hoje=None, verbose=True):
    """Cria (ou recria) o banco fictício da filial em `caminho`."""
    perfil = PERFIS.get(filial, PERFIS["centro"])
    rng = random.Random(perfil["semente"])
    hoje = hoje or date.today()
    equipe = perfil["equipe"]

    for sufixo in ("", "-wal", "-shm"):
        if os.path.exists(caminho + sufixo):
            os.remove(caminho + sufixo)

    # O próprio sistema cria as tabelas (mesmo esquema da versão em produção).
    import nucleo_pdv
    banco = nucleo_pdv.BancoDados(caminho, [])
    con = banco.conexao
    cur = con.cursor()

    # --- Equipe ---
    for nome, (_, _, saiu) in equipe.items():
        cur.execute("INSERT INTO vendedores (nome, status) VALUES (?, ?)",
                    (nome, "Inativo" if saiu and saiu < hoje else "Ativo"))

    # --- Vendas ---
    vendas = []
    faturamento_mes = {}
    dias_trabalhados = []
    d = INICIO
    anos_desde_inicio = lambda dia: (dia - INICIO).days / 365.0
    while d <= hoje:
        if d.weekday() == 6 or (d.day, d.month) in FERIADOS_FECHADO:
            d += timedelta(days=1)
            continue
        dias_trabalhados.append(d)
        media = (perfil["vendas_dia_base"] * SAZONALIDADE[d.month] * PESO_DIA_SEMANA[d.weekday()]
                 * (1 + 0.09 * anos_desde_inicio(d)))
        if d.month == 5 and 5 <= d.day <= 12:      # semana do Dia das Mães
            media *= 1.6
        if d.month == 6 and 8 <= d.day <= 12:      # Dia dos Namorados
            media *= 1.4
        if d.month == 12 and 15 <= d.day <= 24:    # Natal
            media *= 1.5
        if d == hoje:                              # hoje: só as vendas "até agora"
            media *= min(max((datetime.now().hour - 9) / 10, 0.1), 1.0)
        qtd = max(0, int(rng.gauss(media, media * 0.18)))

        nomes = [n for n in equipe if _ativo(n, d, equipe)]
        pesos = [equipe[n][0] for n in nomes]
        for _ in range(qtd):
            vend = rng.choices(nomes, pesos)[0]
            prod = "PERFUMARIA" if rng.random() < 0.80 else "OUTROS"
            valor = _valor_venda(rng, prod)
            pag = rng.choices([p for p, _ in PAGAMENTOS], [w for _, w in PAGAMENTOS])[0]
            if pag in ("CRÉDITO 2X", "CRÉDITO 3X") and valor < 60:
                pag = "CRÉDITO A V."
            hora = _hora_aleatoria(rng)
            dv = _fmt(d)
            if pag in ("CRÉDITO 2X", "CRÉDITO 3X"):
                n = 2 if pag == "CRÉDITO 2X" else 3
                centavos = round(valor * 100)
                parcela = centavos // n
                for i in range(1, n + 1):
                    val_parc = (parcela + (centavos - parcela * n if i == 1 else 0)) / 100
                    vendas.append((val_parc, vend, dv, _fmt(d + timedelta(days=30 * i)), hora, prod, f"{pag} ({i}/{n})"))
            elif pag == "CRÉDITO A V.":
                vendas.append((valor, vend, dv, _fmt(d + timedelta(days=30)), hora, prod, pag))
            else:
                vendas.append((valor, vend, dv, dv, hora, prod, pag))
            chave = (d.year, d.month)
            faturamento_mes[chave] = faturamento_mes.get(chave, 0.0) + valor
        d += timedelta(days=1)

    # Ordena por data + hora (como seria digitado no dia a dia)
    def _chave(v):
        dt = datetime.strptime(v[2], "%d/%m/%Y")
        hr = datetime.strptime(v[4], "%I:%M:%S %p")
        return (dt, hr.time())
    vendas.sort(key=_chave)
    cur.executemany("INSERT INTO vendas (valor, vendedor, data_venda, data_vencimento, horario, tipo_produto, "
                    "tipo_pagamento) VALUES (?, ?, ?, ?, ?, ?, ?)", vendas)

    # --- Despesas mensais ---
    despesas = []
    mes = date(INICIO.year, INICIO.month, 1)
    while mes <= date(hoje.year, hoje.month, 1):
        fat = faturamento_mes.get((mes.year, mes.month), 0.0)
        fat_ant = faturamento_mes.get(((mes - timedelta(days=1)).year, (mes - timedelta(days=1)).month), fat)
        n_equipe = len([n for n in equipe if n != "FERNANDO" and _ativo(n, _mes_seguinte(mes, 0), equipe)])

        def add(dia, desc, valor, tipo):
            data = date(mes.year, mes.month, min(dia, calendar.monthrange(mes.year, mes.month)[1]))
            if data <= hoje:
                despesas.append((desc, round(valor, 2), tipo, _fmt(data)))

        add(5, "ALUGUEL LOJA", perfil["aluguel"] * (1.045 if mes.year >= 2025 else 1.0), "ALUGUEL")
        add(5, "FOLHA DE PAGAMENTO", 1850.00 * n_equipe * (1.06 if mes.year >= 2025 else 1.0), "SALÁRIOS")
        add(5, "PRÓ-LABORE SÓCIO", 5000.00, "PRÓ LABORE")
        add(10, "LUZ", rng.uniform(340, 560) * (1.25 if mes.month in (12, 1, 2) else 1.0), "LUZ")
        add(10, "ÁGUA", rng.uniform(85, 140), "ÁGUA")
        add(12, "INTERNET FIBRA", 129.90, "INTERNET")
        add(12, "TELEFONE", 79.90, "TELEFONE")
        add(15, "ESCRITÓRIO CONTÁBIL", 650.00, "CONTADOR")
        add(20, "SIMPLES NACIONAL", fat_ant * 0.061, "IMPOSTOS")
        add(18, "SISTEMA FISCAL", 99.00, "SISTEMA SINTEGRA")
        add(25, "TAXA DE LIXO", 45.00, "TAXA DE LIXO")
        if 2 <= mes.month <= 11:
            add(10, f"IPTU ({mes.month - 1}/10)", 185.00, "IPTU")
        add(rng.randint(3, 27), "IMPULSIONAMENTO REDES SOCIAIS", rng.uniform(250, 900), "MARKETING")
        add(rng.randint(3, 27), "LANCHE EQUIPE", rng.uniform(120, 280), "LANCHE")
        add(rng.randint(3, 27), "MATERIAL DE LIMPEZA E ESCRITÓRIO", rng.uniform(110, 260), "MAT. DE LIMPEZA E ESCRITÓRIO")
        # Compras de mercadoria: ~46% do faturamento, em 3 a 5 pedidos
        pedidos = rng.randint(3, 5)
        for i in range(pedidos):
            forn = rng.choice(["DISTRIBUIDORA PERFUMES", "FORNECEDOR MAQUIAGEM", "ATACADO CABELOS", "DISTRIBUIDORA SKINCARE"])
            add(rng.randint(2, 26), f"{forn}", fat * 0.46 / pedidos * rng.uniform(0.85, 1.15), "COMPRAS DE PRODUTO")
        mes = _mes_seguinte(mes, 1)

    # Uma compra parcelada recente (parcelas futuras aparecem nos próximos meses)
    base = _mes_seguinte(date(hoje.year, hoje.month, 10), -1)
    for i in range(1, 4):
        dp = _mes_seguinte(base, i)
        despesas.append((f"EXPOSITOR DE VITRINE ({i}/3)", 780.00, "OUTROS CUSTOS", _fmt(dp)))
    cur.executemany("INSERT INTO despesas (descricao, valor, tipo, data_despesa) VALUES (?, ?, ?, ?)", despesas)

    # --- Desafios do Dia (últimos ~75 dias trabalhados) ---
    participantes = [n for n in equipe if n != "FERNANDO"]
    talento = {n: rng.uniform(3.2, 6.2) for n in participantes}
    for dia in [x for x in dias_trabalhados if (hoje - x).days <= 110][:-1]:
        produto = rng.choice(PRODUTOS_DESAFIO)
        cur.execute("INSERT INTO desafios (data, produto, meta_quantidade, criado_em) VALUES (?, ?, 5, ?)",
                    (_fmt(dia), produto, _fmt(dia) + " 08:45"))
        did = cur.lastrowid
        for n in participantes:
            if _ativo(n, dia, equipe):
                q = max(0, int(round(rng.gauss(talento[n], 1.8))))
                cur.execute("INSERT INTO desafio_resultados (desafio_id, vendedor, quantidade) VALUES (?, ?, ?)",
                            (did, n, q))

    # --- Bonificações (critério da gerência) nos últimos meses ---
    for k in range(0, 3):
        m = _mes_seguinte(date(hoje.year, hoje.month, 1), -k)
        for n in rng.sample([p for p in participantes if _ativo(p, m, equipe)], 2):
            cur.execute("INSERT INTO bonificacoes (vendedor, mes, ano, valor, motivo, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
                        (n, f"{m.month:02d}", str(m.year), rng.choice([150.0, 200.0, 250.0, 300.0]),
                         rng.choice(["META DE PERFUMARIA BATIDA", "MELHOR ATENDIMENTO DO MÊS",
                                     "CAMPANHA DE LANÇAMENTO", "MAIOR TICKET MÉDIO"]),
                         _fmt(m) + " 18:00"))

    # --- Fechamentos de caixa dos últimos 40 dias (dinheiro) ---
    din_dia = {}
    for v in vendas:
        if v[6] == "DINHEIRO":
            din_dia[v[2]] = din_dia.get(v[2], 0.0) + v[0]
    for dia in [x for x in dias_trabalhados if 0 < (hoje - x).days <= 40]:
        ds = _fmt(dia)
        troco = 200.0
        dinheiro = din_dia.get(ds, 0.0)
        sangria = 0.0
        if dinheiro > 700:
            sangria = float(int(dinheiro * rng.uniform(0.5, 0.75) / 50) * 50)
            cur.execute("INSERT INTO movimentos_caixa (data, tipo, valor, descricao, horario) VALUES (?, 'SANGRIA', ?, '', ?)",
                        (ds, sangria, "16:30"))
        esperado = troco + dinheiro - sangria
        dif = rng.choices([0.0, -2.0, 1.0, -5.0, 0.5], [0.80, 0.07, 0.06, 0.04, 0.03])[0]
        cur.execute("INSERT INTO fechamento_caixa (data, troco_inicial, observacao, fechado_em) VALUES (?, ?, ?, ?)",
                    (ds, troco, "" if dif == 0 else "DIFERENÇA CONFERIDA NO FECHAMENTO", ds + " 20:05"))
        cur.execute("INSERT INTO fechamento_contagem (data, forma_pagamento, valor_contado) VALUES (?, 'DINHEIRO', ?)",
                    (ds, round(esperado + dif, 2)))

    con.commit()
    banco.fechar()
    if verbose:
        print(f"[demo] {os.path.basename(caminho)}: {len(vendas):,} lançamentos de venda, "
              f"{len(despesas):,} despesas ({filial}).".replace(",", "."))
    return caminho


if __name__ == "__main__":
    from config_filiais import FILIAIS
    import nucleo_pdv
    alvo = sys.argv[1:] or list(FILIAIS)
    for chave in alvo:
        cfg = FILIAIS[chave]
        gerar_banco_demo(os.path.join(nucleo_pdv.BASE_DIR, cfg["arquivo_banco"]), chave, cfg["equipe_inicial"])
