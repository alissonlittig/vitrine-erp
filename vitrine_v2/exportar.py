# =============================================================================
# NOVA INTERFACE — EXPORTAR EXCEL / PDF
# =============================================================================
# Mesmo resultado das funções exportar_tabela_excel / exportar_tabela_pdf do
# nucleo_pdv.py: exporta exatamente as colunas e linhas que estão na tela.
# (A janela "Salvar como" é aberta pelo app.py; aqui só se grava o arquivo.)
import re
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _titulo_aba(texto):
    # O Excel não aceita \ / * ? : [ ] no nome da aba (no sistema atual, "Maio/2026" dava erro)
    return (re.sub(r"[\\/*?:\[\]]", "-", texto or "Relatório")[:31]) or "Relatório"


def excel(caminho, colunas, linhas, titulo):
    wb = Workbook()
    ws = wb.active
    ws.title = _titulo_aba(titulo)
    ws.append(list(colunas))
    for celula in ws[1]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill(start_color="1DB954", end_color="1DB954", fill_type="solid")
        celula.alignment = Alignment(horizontal="center")
    for linha in linhas:
        ws.append(list(linha))
    for coluna in ws.columns:
        maior = max((len(str(c.value)) for c in coluna if c.value is not None), default=8)
        ws.column_dimensions[coluna[0].column_letter].width = min(max(maior + 2, 10), 40)
    wb.save(caminho)


def pdf(caminho, colunas, linhas, titulo):
    largura, _ = landscape(A4)
    margem = 28
    larg_col = (largura - 2 * margem) / len(colunas)
    doc = SimpleDocTemplate(caminho, pagesize=landscape(A4), leftMargin=margem, rightMargin=margem,
                            topMargin=margem, bottomMargin=margem)
    estilos = getSampleStyleSheet()
    dados = [list(colunas)] + [[str(v) for v in linha] for linha in linhas]
    tabela = Table(dados, colWidths=[larg_col] * len(colunas), repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1DB954")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    doc.build([Paragraph(titulo, estilos["Title"]),
               Paragraph(f"Gerado em {datetime.now():%d/%m/%Y às %H:%M}", estilos["Normal"]),
               Spacer(1, 12), tabela])
