# =============================================================================
# NOVA INTERFACE — GRÁFICOS
# =============================================================================
# Os mesmos gráficos do sistema atual (matplotlib), desenhados como SVG para a
# página mostrar. Usa só a Figure do matplotlib (sem pyplot e sem Tkinter), então
# pode rodar em qualquer thread da janela.
import io
import re

import matplotlib
import matplotlib.ticker
import matplotlib.backends.backend_svg  # noqa: F401  (import direto: sem ele o .exe não leva o módulo do SVG)
from matplotlib.figure import Figure

matplotlib.rcParams.update({
    "svg.fonttype": "none",  # texto como texto: usa a fonte da página e fica nítido
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "font.size": 9,
    "axes.edgecolor": "#B9C0B8",
    "axes.labelcolor": "#5A625C",
    "xtick.color": "#5A625C",
    "ytick.color": "#5A625C",
    "axes.titlecolor": "#1A1F1B",
    "axes.titleweight": "bold",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

VERDE = "#15803D"
VERMELHO = "#B42318"
AZUL = "#1D4ED8"
PALETA_RANKING = ["#DB2777", "#2563EB", "#16A34A", "#7C3AED", "#CA8A04", "#EA580C", "#0891B2"]
PALETA_DESPESAS = ["#FF69B4", "#1E90FF", "#32CD32", "#9370DB", "#DAA520", "#FF4500", "#00CED1", "#8A2BE2",
                   "#008080", "#D2691E", "#FF1493", "#2E8B57", "#4B0082", "#A52A2A", "#5F9EA0", "#D2B48C",
                   "#FF8C00", "#9932CC", "#8B0000", "#4682B4", "#696969"]
MESES_CURTOS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _moeda(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eixo_reais(ax):
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"{v:,.0f}".replace(",", ".")))
    ax.grid(axis="y", linestyle="--", alpha=0.45, color="#B9C0B8")
    ax.set_axisbelow(True)


def _svg(fig):
    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=True)
    svg = buf.getvalue()
    svg = svg[svg.find("<svg"):]
    # sem largura/altura fixas: o CSS da página decide o tamanho (o viewBox mantém a proporção)
    return re.sub(r'<svg([^>]*?) width="[^"]*" height="[^"]*"', r'<svg\1', svg, count=1)


def _vazio(texto, largura=6, altura=2.6):
    fig = Figure(figsize=(largura, altura), dpi=100)
    ax = fig.subplots()
    ax.text(0.5, 0.5, texto, ha="center", va="center", color="#5A625C", fontsize=10)
    ax.axis("off")
    return _svg(fig)


def barras_horario(horas, titulo, rotulos=False, rotulo_y=None):
    """Vendas por horário (Fechamento do Dia e Relatório Diário)."""
    fig = Figure(figsize=(5.6, 2.9), dpi=100)
    ax = fig.subplots()
    chaves = sorted(horas)
    valores = [horas[k] for k in chaves]
    barras = ax.bar(chaves, valores, color=VERDE)
    ax.set_title(titulo, fontsize=10.5)
    if rotulo_y:
        ax.set_ylabel(rotulo_y)
    ax.tick_params(axis="x", rotation=45, labelsize=7.5)
    _eixo_reais(ax)
    teto = max(valores, default=0)
    if rotulos:
        for b in barras:
            if b.get_height() > 0:
                ax.annotate(_moeda(b.get_height()), xy=(b.get_x() + b.get_width() / 2, b.get_height()),
                            xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=7,
                            rotation=90, color="#1A1F1B")
        ax.set_ylim(0, teto * 1.45 if teto > 0 else 100)
    else:
        ax.set_ylim(0, teto * 1.25 if teto > 0 else 100)
    fig.tight_layout()
    return _svg(fig)


def barras_ranking(ranking, titulo, vazio="Sem vendas neste dia."):
    """Ranking da equipe no dia: [(nome, valor), ...]."""
    if not ranking:
        return _vazio(vazio, 5.6, 2.9)
    fig = Figure(figsize=(5.6, 2.9), dpi=100)
    ax = fig.subplots()
    nomes = [n for n, _ in ranking]
    vals = [v for _, v in ranking]
    barras = ax.bar(nomes, vals, color=[PALETA_RANKING[i % len(PALETA_RANKING)] for i in range(len(nomes))])
    for b in barras:
        if b.get_height() > 0:
            ax.annotate(_moeda(b.get_height()), xy=(b.get_x() + b.get_width() / 2, b.get_height()),
                        xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7.5,
                        color="#1A1F1B")
    ax.set_ylim(0, max(vals) * 1.25 if max(vals) > 0 else 100)
    ax.set_title(titulo, fontsize=10.5)
    ax.tick_params(axis="x", rotation=15, labelsize=8)
    _eixo_reais(ax)
    fig.tight_layout()
    return _svg(fig)


def linhas_mensais(series, titulo, vazio="Selecione um vendedor / Sem registros.", legenda_embaixo=False,
                   largura=9.5, altura=2.7):
    """Evolução mês a mês: series = [(nome, [12 valores], cor), ...]."""
    if not series:
        return _vazio(vazio, largura, altura)
    fig = Figure(figsize=(largura, altura), dpi=100)
    ax = fig.subplots()
    for nome, valores, cor in series:
        ax.plot(MESES_CURTOS, valores, marker="o", label=nome, color=cor, linewidth=2, markersize=4.5)
    ax.set_title(titulo, fontsize=10.5)
    _eixo_reais(ax)
    if legenda_embaixo:
        ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=6, frameon=False)
    else:
        ax.legend(fontsize=7.5, loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)
    fig.tight_layout()
    return _svg(fig)


def despesas_mensais(series, titulo):
    """Gráfico da aba Despesas > Gráficos: series = [(tipo, [12 valores]), ...]."""
    com_cor = [(t, v, PALETA_DESPESAS[i % len(PALETA_DESPESAS)]) for i, (t, v) in enumerate(series)]
    return linhas_mensais(com_cor, titulo, vazio="Sem registros para as opções selecionadas.",
                          legenda_embaixo=True, largura=10, altura=3.1)


def dre(series, titulo):
    fig = Figure(figsize=(10, 3.2), dpi=100)
    ax = fig.subplots()
    ax.plot(MESES_CURTOS, series["receita"], marker="o", label="Receita Bruta", color=VERDE, linewidth=3)
    ax.plot(MESES_CURTOS, series["despesas"], marker="o", label="Despesas", color=VERMELHO, linewidth=3)
    ax.plot(MESES_CURTOS, series["lucro"], marker="s", label="Lucro Líquido", color=AZUL, linewidth=2, linestyle="--")
    ax.set_title(titulo, fontsize=11)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False)
    _eixo_reais(ax)
    fig.tight_layout()
    return _svg(fig)
