# =============================================================================
#  VITRINE ERP — SISTEMA DE VENDAS, CAIXA, DESPESAS E GESTÃO (PDV/ERP DESKTOP)
#  "Motor" do sistema, compartilhado por todas as filiais. Este arquivo não
#  abre nada sozinho: ele só define iniciar_aplicativo(...), chamada pelo
#  lançador (main.py) com a configuração de cada filial (config_filiais.py):
#  nome da loja, arquivo de banco, equipe inicial, regras de comissão etc.
#  Uma correção feita aqui vale para todas as filiais ao mesmo tempo.
#
#  Stack: Python 3 · CustomTkinter · SQLite (modo WAL) · Matplotlib ·
#  OpenPyXL (Excel) · ReportLab (PDF) · PyInstaller (executável Windows).
# =============================================================================

# -----------------------------------------------------------------------------
# 1. IMPORTAÇÕES E CONFIGURAÇÃO INICIAL DO WINDOWS / APARÊNCIA
# -----------------------------------------------------------------------------
import os
import sys
import platform
import ctypes
import sqlite3
import traceback
import calendar
import time
from datetime import datetime, timedelta

import customtkinter as ctk
from tkinter import messagebox, ttk, filedialog

import matplotlib
matplotlib.use("TkAgg")  # garante que o gráfico sempre usa o mesmo motor gráfico do Tkinter
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from openpyxl import Workbook
from openpyxl.styles import Font as ExcelFont, Alignment as ExcelAlign

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors as rl_colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

# 1.1. Ativa a resolução máxima do Windows (evita telas "borradas")
if platform.system() == "Windows":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

# 1.2. Trava o zoom do CustomTkinter para evitar bordas serrilhadas
ctk.set_window_scaling(1.0)
ctk.set_widget_scaling(1.0)

# 1.3. Tema padrão (escuro, verde) — os detalhes finos de cor ficam na classe Tema, abaixo
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


# -----------------------------------------------------------------------------
# 2. CAMINHOS DO SISTEMA
# -----------------------------------------------------------------------------
# Antes, o banco de dados era aberto com um caminho "solto" (só o nome do
# arquivo), o que funciona na maioria das vezes, mas pode falhar se o programa
# for aberto a partir de um atalho com "Iniciar em" configurado errado, ou
# pelo terminal do VSCode a partir de outra pasta. Agora fixamos o caminho
# sempre na pasta onde está o .exe (ou o interface.py, quando rodado direto
# no VSCode) — o nome do arquivo do banco continua o mesmo de sempre, então
# o histórico de vendas já existente é aberto normalmente.
def _diretorio_base():
    if getattr(sys, "frozen", False):
        # Rodando como .exe gerado pelo PyInstaller
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _diretorio_base()
DB_PADRAO = "vendas.db"  # cada filial define o seu em config_filiais.py
LOG_PATH = os.path.join(BASE_DIR, "erros_sistema.log")
ICON_PATH = os.path.join(BASE_DIR, "icone.ico")


# -----------------------------------------------------------------------------
# 3. REGISTRO DE ERROS — para o sistema NUNCA travar sem avisar
# -----------------------------------------------------------------------------
# Toda vez que algo inesperado acontece (ex: banco de dados aberto em outro
# programa, disco cheio, permissão negada), o erro é gravado neste arquivo de
# texto e o usuário vê um aviso amigável — em vez do programa simplesmente
# fechar sozinho ou travar sem explicação.
def registrar_erro(origem, excecao):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now():%d/%m/%Y %H:%M:%S}] Erro em: {origem}\n")
            f.write("".join(traceback.format_exception(type(excecao), excecao, excecao.__traceback__)))
            f.write("-" * 80 + "\n")
    except Exception:
        pass  # se nem o log der certo, não há mais nada a fazer além de seguir em frente


class ErroBancoDados(Exception):
    """Erro amigável usado quando algo falha ao ler/gravar no banco de dados."""
    pass


def alerta_erro_banco(titulo="Erro"):
    messagebox.showerror(
        titulo,
        "Não foi possível acessar o banco de dados agora.\n\n"
        "Motivos comuns: o arquivo do banco de dados está aberto em outro "
        "programa, ou o disco está cheio/sem permissão de escrita.\n\n"
        "Feche outros programas que possam estar usando o arquivo e tente novamente.\n"
        "Detalhes técnicos foram salvos em 'erros_sistema.log'."
    )


# -----------------------------------------------------------------------------
# 4. TEMA VISUAL CENTRALIZADO
# -----------------------------------------------------------------------------
# Antes, cada botão/tela definia suas próprias cores e cantos "na mão", o que
# deixava o visual inconsistente (cantos retos em uns lugares, arredondados em
# outros) e dificultava trocar uma cor no sistema inteiro. Agora existe um
# único lugar para isso — se um dia quiser mudar a cor principal do sistema,
# basta alterar as constantes abaixo.
class Tema:
    VERDE = "#1DB954"
    VERDE_HOVER = "#159a44"
    VERDE_ESCURO = "#0b3d0b"
    AZUL = "#2f6fed"
    AZUL_HOVER = "#1f4fa8"
    VERMELHO = "#e53935"
    VERMELHO_HOVER = "#b71c1c"
    AMARELO = "#f2b705"
    TEXTO_PADRAO = ("gray10", "#DCE4EE")  # cor padrão de texto do CustomTkinter (claro, escuro)
    # Texto secundário: (modo claro, modo escuro). No modo escuro o cinza antigo
    # (#8a8a8a) ficava no limite de contraste sobre o fundo cinza dos cartões.
    CINZA_TEXTO = ("#5f5f5f", "#b8b8b8")

    # Tabelas (ttk.Treeview) no mesmo tom escuro do resto do sistema.
    TABELA_FUNDO = "#242424"
    TABELA_TEXTO = "#e8e8e8"
    TABELA_CABECALHO = "#1a1a1a"
    TABELA_CABECALHO_HOVER = "#333333"
    LINHA_PAR = "#2b2b2b"
    LINHA_IMPAR = "#242424"
    TOTAL_FUNDO = "#3a3a3a"

    RAIO = 12
    RAIO_BOTAO = 8

    TITULO = ("Segoe UI", 28, "bold")
    SUBTITULO = ("Segoe UI", 16, "bold")
    LABEL = ("Segoe UI", 14, "bold")
    TEXTO = ("Segoe UI", 13)


# Gráficos (Matplotlib) no mesmo tema escuro das telas: fundo, textos, eixos,
# grade e legenda. Vale para todos os gráficos do sistema.
plt.rcParams.update({
    "figure.facecolor": "#2b2b2b", "axes.facecolor": "#2b2b2b", "savefig.facecolor": "#2b2b2b",
    "text.color": "#e8e8e8", "axes.labelcolor": "#e8e8e8", "axes.titlecolor": "#e8e8e8",
    "xtick.color": "#cfcfcf", "ytick.color": "#cfcfcf", "axes.edgecolor": "#555555",
    "grid.color": "#4a4a4a", "legend.facecolor": "#333333", "legend.edgecolor": "#555555",
    "legend.labelcolor": "#e8e8e8",
})


# (A estilização das tabelas -- ttk.Style() -- precisa de uma janela já criada,
# então ela é aplicada dentro de iniciar_aplicativo(), mais abaixo, logo depois
# que a janela principal é montada.)


# -----------------------------------------------------------------------------
# 5. FUNÇÕES UTILITÁRIAS (formatação e validação simples, sem depender da tela)
# -----------------------------------------------------------------------------
def formatar_moeda(valor):
    if not valor:
        return "-"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def valor_dre(valor):
    """Número no formato brasileiro SEM o 'R$' (ex.: 100.757,82), para tabelas largas."""
    if not valor:
        return "-"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def moeda_sempre(valor):
    """Igual a formatar_moeda, mas mostra 'R$ 0,00' em vez de '-' (útil no caixa)."""
    valor = valor or 0.0
    texto = f"R$ {abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"- {texto}" if valor < -0.004 else texto


def dividir_em_parcelas(valor, parcelas):
    """Divide um valor em N parcelas com centavos EXATOS; a diferença de
    arredondamento vai para a 1ª parcela. Ex.: 431,50 em 3x -> [143,84, 143,83, 143,83]
    (a soma sempre bate com o total, ao contrário de 431,50 / 3 = 143,8333...)."""
    centavos = round(valor * 100)
    base = int(centavos / parcelas)  # truncado em direção ao zero (funciona para negativos)
    resto = centavos - base * parcelas
    return [(base + (resto if i == 0 else 0)) / 100 for i in range(parcelas)]


def texto_para_valor(texto):
    """Converte um valor digitado (ex.: '150,00', '1.500', 'R$ 1.500,00') em número.
    Retorna None se inválido. Usa as regras brasileiras de milhar/decimal."""
    return ler_valor_monetario(texto)


def texto_para_data(texto):
    """Converte um texto 'DD/MM/AAAA' em data. Retorna None se inválido."""
    if texto is None:
        return None
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y")
    except (ValueError, AttributeError):
        return None


# Nome "limpo" do vendedor, usado em TODOS os relatórios. Junta variações
# digitadas errado no passado ("ANA-PAULA", "ANA'") ao nome certo, sem
# alterar nada gravado no banco (a correção é feita só na hora de ler).
SQL_NOME_VENDEDOR = "TRIM(REPLACE(REPLACE(UPPER(vendedor), '-', ''), '''', ''))"


# --- Senha da Área de Gestão --------------------------------------------------
# Guardamos só um hash PBKDF2-SHA256 com sal aleatório (formato
# "pbkdf2_sha256$iteracoes$sal_hex$hash_hex"). Mesmo quem abrir o código ou o
# executável não consegue ler a senha.
def gerar_hash_senha(senha, iteracoes=200_000):
    import hashlib
    import secrets
    sal = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, iteracoes)
    return f"pbkdf2_sha256${iteracoes}${sal.hex()}${dk.hex()}"


def verificar_senha(senha_digitada, hash_armazenado):
    import hashlib
    import hmac
    try:
        algoritmo, iteracoes, sal_hex, hash_hex = hash_armazenado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", (senha_digitada or "").encode("utf-8"),
                                 bytes.fromhex(sal_hex), int(iteracoes))
        return hmac.compare_digest(dk.hex(), hash_hex)  # comparação em tempo constante
    except (ValueError, AttributeError):
        return False


def normalizar_nome_vendedor(nome):
    return (nome or "").upper().replace("-", "").replace("'", "").strip()


# --- Regras do Desafio (bonificação mensal por vendedora) -------------------
META_DIARIA_DESAFIO = 5          # unidades do produto do dia, por vendedora
BONIFICACAO_MAXIMA_DESAFIO = 100.0  # R$ pagos a quem atinge 100% no mês


def calcular_conclusao_desafio(dias_com_desafio, vendido_no_mes,
                               meta_diaria=META_DIARIA_DESAFIO, bonificacao_maxima=BONIFICACAO_MAXIMA_DESAFIO):
    """Calcula o resultado mensal do desafio de UMA vendedora.

    Exemplo (25 dias com desafio, meta 5/dia -> meta do mês = 125):
        vendeu 125 -> 100%  -> R$ 100,00 | 25 de 25 dias
        vendeu 100 ->  80%  -> R$  80,00 | 20 de 25 dias
        vendeu 130 -> 100%  -> R$ 100,00 (teto)
    Vale o total do mês: 3 num dia + 7 no outro = 10 = 2 dias concluídos.
    """
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


# --- Comissão no DRE ----------------------------------------------------------
PERCENTUAL_COMISSAO = 0.01  # 1% sobre o valor recebido (mesma regra do Dashboard)
TIPO_DESPESA_COMISSAO = "COMISSÕES"


def novo_mapa_meses():
    return {f"{i:02d}": 0.0 for i in range(1, 13)}


def ano_mes_de_data_flexivel(data_texto):
    """Extrai (ano, mês) de uma data que pode estar em DD/MM/AAAA ou AAAA-MM-DD."""
    if not data_texto:
        return None, None
    d = str(data_texto).strip()
    if "/" in d and len(d) >= 10:
        return d[-4:], d[3:5]
    if "-" in d and len(d) >= 10:
        return d[:4], d[5:7]
    return None, None


# -----------------------------------------------------------------------------
# 6. CAMADA DE BANCO DE DADOS
# -----------------------------------------------------------------------------
# Antes, o programa abria e fechava uma conexão nova com o banco a CADA ação
# (cada clique, cada tecla Enter, cada atualização de tela) — funciona, mas é
# mais lento e mais sujeito a falhar caso o arquivo esteja momentaneamente
# bloqueado (ex: por um antivírus). Agora existe UMA única conexão, mantida
# aberta durante todo o uso do programa, em modo WAL (que permite ler e
# gravar ao mesmo tempo com muito menos chance de erro de "banco travado").
#
# Tabelas novas são criadas com CREATE TABLE IF NOT EXISTS: um banco de uma
# versão anterior abre normalmente, sem precisar de migração manual.
class BancoDados:
    def __init__(self, caminho, equipe_inicial=None):
        self.caminho = caminho
        self.conexao = sqlite3.connect(caminho, check_same_thread=False)
        self.conexao.row_factory = sqlite3.Row
        try:
            self.conexao.execute("PRAGMA journal_mode=WAL")
            self.conexao.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error:
            pass
        self._criar_estrutura(equipe_inicial or [])

    def _criar_estrutura(self, equipe_inicial):
        cur = self.conexao.cursor()
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

        # Índices: aceleram os filtros por vendedor/data sem alterar nenhum dado existente.
        cur.execute("CREATE INDEX IF NOT EXISTS idx_vendas_vendedor ON vendas(vendedor)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_vendas_data_venda ON vendas(data_venda)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_vendas_data_vencimento ON vendas(data_vencimento)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_despesas_data ON despesas(data_despesa)")

        # --- Tabelas NOVAS (Fechamento de Caixa e Desafio do Dia) ---------------
        # Só são criadas se ainda não existirem; nenhuma tabela antiga é alterada.
        # As datas seguem o mesmo formato do resto do sistema (DD/MM/AAAA).
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
        if cur.fetchone()[0] == 0 and equipe_inicial:
            cur.executemany("INSERT INTO vendedores (nome, status) VALUES (?, 'Ativo')",
                             [(pessoa,) for pessoa in equipe_inicial])
        self.conexao.commit()

    def executar(self, sql, parametros=(), commit=False):
        try:
            cur = self.conexao.cursor()
            cur.execute(sql, parametros)
            if commit:
                self.conexao.commit()
            return cur
        except sqlite3.Error as e:
            registrar_erro(f"SQL -> {sql} | params={parametros}", e)
            if commit:
                try:
                    self.conexao.rollback()
                except sqlite3.Error:
                    pass
            raise ErroBancoDados(str(e)) from e

    def executar_muitos(self, sql, lista_parametros, commit=True):
        try:
            cur = self.conexao.cursor()
            cur.executemany(sql, lista_parametros)
            if commit:
                self.conexao.commit()
            return cur
        except sqlite3.Error as e:
            registrar_erro(f"SQL (muitos) -> {sql}", e)
            if commit:
                try:
                    self.conexao.rollback()
                except sqlite3.Error:
                    pass
            raise ErroBancoDados(str(e)) from e

    def consultar_um(self, sql, parametros=()):
        return self.executar(sql, parametros).fetchone()

    def consultar_todos(self, sql, parametros=()):
        return self.executar(sql, parametros).fetchall()

    def transacao(self, comandos):
        """Executa vários comandos (lista de (sql, parametros)) de uma vez só:
        ou todos são gravados, ou nenhum é (evita fechamento salvo pela metade)."""
        try:
            cur = self.conexao.cursor()
            cur.execute("BEGIN")
            for sql, parametros in comandos:
                cur.execute(sql, parametros)
            self.conexao.commit()
        except sqlite3.Error as e:
            registrar_erro("transacao -> " + " | ".join(sql for sql, _ in comandos), e)
            try:
                self.conexao.rollback()
            except sqlite3.Error:
                pass
            raise ErroBancoDados(str(e)) from e

    def fechar(self):
        try:
            self.conexao.close()
        except sqlite3.Error:
            pass


# (A conexão "banco" é criada dentro de iniciar_aplicativo(), pois cada filial
# usa seu próprio arquivo de banco e sua própria equipe inicial.
# As funções obter_vendedores_ativos() e obter_todos_historico(), que dependem
# dessa conexão, também são definidas lá dentro.)


# -----------------------------------------------------------------------------
# 7. EXPORTAÇÃO DE RELATÓRIOS (EXCEL / PDF) — recurso novo
# -----------------------------------------------------------------------------
# Estas funções pegam o que já está sendo exibido numa tabela na tela e geram
# um arquivo Excel (.xlsx) ou PDF, prontos para imprimir ou mandar por e-mail
# (ex: para o contador). Foram feitas de forma genérica para funcionar em
# qualquer tabela do sistema (Histórico, Despesas, DRE, Dashboard).
def _linhas_da_tabela(tree):
    return [tree.item(i, "values") for i in tree.get_children()]


def _titulos_da_tabela(tree):
    return [tree.heading(c)["text"] for c in tree["columns"]]


def exportar_tabela_excel(tree, nome_sugerido, titulo_relatorio=None):
    linhas = _linhas_da_tabela(tree)
    if not linhas:
        messagebox.showwarning("Exportar", "Não há dados para exportar nesta tela.")
        return
    caminho = filedialog.asksaveasfilename(
        title="Salvar relatório em Excel",
        defaultextension=".xlsx",
        filetypes=[("Planilha Excel", "*.xlsx")],
        initialfile=nome_sugerido,
    )
    if not caminho:
        return
    try:
        colunas = _titulos_da_tabela(tree)
        wb = Workbook()
        ws = wb.active
        ws.title = (titulo_relatorio or nome_sugerido)[:31]

        ws.append(colunas)
        for celula in ws[1]:
            celula.font = ExcelFont(bold=True, color="FFFFFF")
            celula.fill = __import__("openpyxl.styles", fromlist=["PatternFill"]).PatternFill(
                start_color="1DB954", end_color="1DB954", fill_type="solid")
            celula.alignment = ExcelAlign(horizontal="center")

        for linha in linhas:
            ws.append(list(linha))

        for coluna_celulas in ws.columns:
            maior = max((len(str(c.value)) for c in coluna_celulas if c.value is not None), default=8)
            ws.column_dimensions[coluna_celulas[0].column_letter].width = min(max(maior + 2, 10), 40)

        wb.save(caminho)
        messagebox.showinfo("Exportar", f"Relatório salvo com sucesso em:\n{caminho}")
    except Exception as e:
        registrar_erro("exportar_tabela_excel", e)
        messagebox.showerror("Erro ao exportar", "Não foi possível salvar o arquivo Excel.\nVerifique se ele não está aberto em outro programa.")


def exportar_tabela_pdf(tree, nome_sugerido, titulo_relatorio):
    linhas = _linhas_da_tabela(tree)
    if not linhas:
        messagebox.showwarning("Exportar", "Não há dados para exportar nesta tela.")
        return
    caminho = filedialog.asksaveasfilename(
        title="Salvar relatório em PDF",
        defaultextension=".pdf",
        filetypes=[("Documento PDF", "*.pdf")],
        initialfile=nome_sugerido,
    )
    if not caminho:
        return
    try:
        colunas = _titulos_da_tabela(tree)
        largura_pagina, altura_pagina = landscape(A4)
        margem = 28
        largura_util = largura_pagina - 2 * margem
        largura_coluna = largura_util / len(colunas)

        doc = SimpleDocTemplate(caminho, pagesize=landscape(A4),
                                 leftMargin=margem, rightMargin=margem, topMargin=margem, bottomMargin=margem)
        estilos = getSampleStyleSheet()
        dados_tabela = [colunas] + [[str(v) for v in linha] for linha in linhas]

        tabela = Table(dados_tabela, colWidths=[largura_coluna] * len(colunas), repeatRows=1)
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1DB954")),
            ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#f2f2f2")]),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

        elementos = [
            Paragraph(titulo_relatorio, estilos["Title"]),
            Paragraph(f"Gerado em {datetime.now():%d/%m/%Y às %H:%M}", estilos["Normal"]),
            Spacer(1, 12),
            tabela,
        ]
        doc.build(elementos)
        messagebox.showinfo("Exportar", f"Relatório salvo com sucesso em:\n{caminho}")
    except Exception as e:
        registrar_erro("exportar_tabela_pdf", e)
        messagebox.showerror("Erro ao exportar", "Não foi possível salvar o arquivo PDF.\nVerifique se ele não está aberto em outro programa.")


def nova_tabela(pai, **kw):
    """Cria uma tabela (ttk.Treeview) já com as cores do tema escuro: zebra e
    linha de TOTAL em destaque. Antes cada tela configurava isso na mão e
    algumas esqueciam (ex.: a linha TOTAL do gráfico de despesas)."""
    t = ttk.Treeview(pai, **kw)
    t.tag_configure("linha_par", background=Tema.LINHA_PAR)
    t.tag_configure("linha_impar", background=Tema.LINHA_IMPAR)
    t.tag_configure("tag_TOTAL", foreground="white", background=Tema.TOTAL_FUNDO, font=("Segoe UI", 12, "bold"))
    return t


def ler_valor_monetario(texto):
    """Lê um valor em reais do jeito que as pessoas digitam no Brasil.

    Aceita: '150', '150,5', '150,50', '1.500', '1.500,00', 'R$ 1.500,00'.
    Retorna None se não for um número válido. Sem isso, "1.500" seria lido
    como 1,5 (o ponto seria tratado como decimal).)"""
    if texto is None:
        return None
    s = str(texto).strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    negativo = s.startswith("-")
    s = s.lstrip("-")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")          # 1.500,00 -> 1500.00
    elif s.count(".") == 1 and len(s.split(".")[1]) == 3:
        s = s.replace(".", "")                            # 1.500 -> 1500 (milhar)
    elif s.count(".") > 1:
        s = s.replace(".", "")                            # 1.500.000 -> 1500000
    try:
        v = round(float(s), 2)
    except ValueError:
        return None
    return -v if negativo else v


def criar_botoes_exportar(pai, tree, nome_arquivo, titulo_relatorio):
    """Cria o par de botões 'Exportar Excel' / 'Exportar PDF' já ligados a uma tabela."""
    frame = ctk.CTkFrame(pai, fg_color="transparent")
    ctk.CTkButton(frame, text="📊 Exportar Excel", font=ctk.CTkFont(size=14, weight="bold"),
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, height=36, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: exportar_tabela_excel(tree, nome_arquivo, titulo_relatorio)).pack(side="left", padx=5)
    ctk.CTkButton(frame, text="📄 Exportar PDF", font=ctk.CTkFont(size=14, weight="bold"),
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, height=36, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: exportar_tabela_pdf(tree, nome_arquivo, titulo_relatorio)).pack(side="left", padx=5)
    return frame


def iniciar_aplicativo(nome_loja, equipe_inicial, hash_senha_gestao, arquivo_banco=DB_PADRAO,
                       nome_sistema="VITRINE ERP", minutos_bloqueio_gestao=5,
                       excluidos_desafio=(), inicio_comissao_automatica=None,
                       sem_comissao=(), excluidos_bonificacao=(), _gancho_de_teste=None):
    """Monta e roda o sistema inteiro para UMA filial.

    nome_loja: texto mostrado no título da janela (ex: "Aurora Cosméticos -
    Filial Centro").
    equipe_inicial: lista de nomes usada para popular a tabela de vendedores
    SOMENTE quando o banco de dados é criado do zero (arquivo novo, vazio).
    hash_senha_gestao: hash PBKDF2 da senha da "Área de Gestão" (Dashboard,
    Equipe, Desafios, Bonificações e DRE), gerado com gerar_hash_senha(). A
    senha em si nunca fica gravada no código nem no executável.
    arquivo_banco: nome do arquivo SQLite desta filial (na pasta do programa).
    nome_sistema: nome exibido no topo do menu lateral.
    inicio_comissao_automatica: mês ("MM/AAAA") a partir do qual o DRE calcula a
    linha COMISSÕES sozinho (1% do recebido no mês, igual à aba "Comissões (A
    Pagar)" do Dashboard). ANTES desse mês, o DRE continua usando os lançamentos
    manuais de COMISSÕES feitos em Despesas (o histórico não é sobrescrito). A
    partir dele, lançamentos manuais de COMISSÕES são ignorados no DRE, para a
    comissão não ser contada duas vezes. None = automática desde sempre.
    sem_comissao: quem não recebe comissão (ex.: o sócio que também vende).
    excluidos_bonificacao: quem não aparece na tela de Bonificações.
    excluidos_desafio: vendedoras/vendedores que NÃO participam do Desafio
    (não aparecem no lançamento nem recebem bonificação).
    minutos_bloqueio_gestao: depois de quantos minutos SEM USO (nenhuma tecla,
    clique ou movimento do mouse) a Área de Gestão se tranca sozinha.
    _gancho_de_teste: uso interno (testes automatizados); deixe sempre None
    no uso normal do programa.
    """
    # =========================================================================
    # 8. JANELA PRINCIPAL
    # =========================================================================
    janela = ctk.CTk()
    janela.title(nome_loja)
    janela.geometry("1280x720")
    janela.minsize(1100, 650)
    try:
        janela.iconbitmap(ICON_PATH)
    except Exception:
        pass  # ícone é só estética; se não existir, o sistema segue normalmente

    # Maximiza a janela ao abrir (melhor aproveitamento da tela, mais "profissional")
    try:
        janela.state("zoomed")
    except Exception:
        pass


    def ao_fechar_programa():
        """Fecha a conexão do banco de forma organizada antes de encerrar o programa."""
        plt.close("all")
        banco.fechar()
        janela.destroy()
        if _gancho_de_teste is None:
            # Contorna um bug conhecido do customtkinter: mesmo depois do destroy(),
            # ele deixa "tarefas" internas agendadas (ex.: checagem de escala/DPI da
            # tela) que tentam rodar DEPOIS que a janela já não existe mais. Isso
            # aparece como uma mensagem de erro ("bgerror... invalid command name")
            # bem na hora de fechar o programa -- é só cosmético (os dados já foram
            # salvos e o banco já foi fechado corretamente acima), mas assusta.
            # Encerrar o processo aqui, logo após o destroy(), evita essa mensagem.
            os._exit(0)


    janela.protocol("WM_DELETE_WINDOW", ao_fechar_programa)


    def tratar_erro_de_tela(exc_tipo, exc_valor, exc_tb):
        """Rede de segurança: qualquer erro não previsto em um clique/tela é
        registrado em arquivo e mostrado de forma amigável, em vez de travar o
        programa ou fechá-lo sozinho."""
        registrar_erro("ação na interface", exc_valor)
        try:
            if isinstance(exc_valor, ErroBancoDados):
                alerta_erro_banco()
            else:
                messagebox.showerror(
                    "Ops! Algo deu errado",
                    "Aconteceu um erro inesperado, mas o programa não vai fechar.\n\n"
                    "Os detalhes foram salvos no arquivo 'erros_sistema.log', na mesma "
                    "pasta do sistema. Se o problema continuar, envie esse arquivo para o suporte."
                )
        except Exception:
            pass


    janela.report_callback_exception = tratar_erro_de_tela

    # --- Estilização das tabelas (ttk.Style precisa de uma janela já criada) ---
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Treeview", rowheight=32, background=Tema.TABELA_FUNDO, fieldbackground=Tema.TABELA_FUNDO,
                    foreground=Tema.TABELA_TEXTO, bordercolor=Tema.TABELA_CABECALHO, borderwidth=0,
                    lightcolor=Tema.TABELA_FUNDO, darkcolor=Tema.TABELA_FUNDO, font=("Segoe UI", 12))
    style.configure("Treeview.Heading", font=("Segoe UI", 13, "bold"), background=Tema.TABELA_CABECALHO,
                    foreground=Tema.TABELA_TEXTO, bordercolor=Tema.TABELA_CABECALHO, relief="flat",
                    lightcolor=Tema.TABELA_CABECALHO, darkcolor=Tema.TABELA_CABECALHO)
    style.map("Treeview.Heading", background=[("active", Tema.TABELA_CABECALHO_HOVER)])
    style.map("Treeview", background=[("selected", Tema.VERDE)], foreground=[("selected", "white")])
    for _orient in ("Vertical", "Horizontal"):
        style.configure(f"{_orient}.TScrollbar", background="#4a4a4a", troughcolor=Tema.TABELA_FUNDO,
                        bordercolor=Tema.TABELA_FUNDO, lightcolor="#4a4a4a", darkcolor="#4a4a4a",
                        arrowcolor=Tema.TABELA_TEXTO, gripcount=0)
        style.map(f"{_orient}.TScrollbar", background=[("active", "#5a5a5a")])


    # --- Banco de dados desta filial (arquivo e equipe iniciais definidos pelo launcher) ---
    banco = BancoDados(os.path.join(BASE_DIR, arquivo_banco), equipe_inicial)
    _sem_comissao = [normalizar_nome_vendedor(n) for n in sem_comissao]  # quem não recebe comissão
    _excluidos_desafio = {normalizar_nome_vendedor(n) for n in excluidos_desafio}  # fora do Desafio
    _excluidos_bonificacao = {normalizar_nome_vendedor(n) for n in excluidos_bonificacao}  # fora das Bonificações

    # Mês a partir do qual a comissão é automática e as bonificações são lançadas
    # na Gestão (antes disso, o DRE usa os lançamentos manuais de COMISSÕES).
    inicio_comissao_automatica = inicio_comissao_automatica or "01/1900"  # None = sempre automática
    _mes_ini_com, _ano_ini_com = (inicio_comissao_automatica.split("/") + ["", ""])[:2]
    _chave_inicio_comissao = f"{_ano_ini_com}{_mes_ini_com.zfill(2)}"

    def _comissao_automatica_no_mes(ano, mes):
        """True se o mês (ano 'AAAA', mes 'MM') já está no regime automático (>= inicio_comissao_automatica)."""
        return f"{ano}{mes}" >= _chave_inicio_comissao


    def obter_vendedores_ativos():
        linhas = banco.consultar_todos("SELECT nome FROM vendedores WHERE status = 'Ativo' ORDER BY nome")
        ativos = [row[0] for row in linhas]
        return ativos if ativos else ["Nenhum Vendedor Ativo"]


    def obter_todos_historico():
        linhas = banco.consultar_todos(
            "SELECT DISTINCT vendedor FROM vendas UNION SELECT nome FROM vendedores WHERE status = 'Ativo'")
        todos = set()
        for row in linhas:
            if row[0]:
                todos.add(normalizar_nome_vendedor(row[0]))
        return sorted(todos)


    # =============================================================================
    # 9. VARIÁVEIS GLOBAIS E CONTAINERS GERAIS
    # =============================================================================
    opcoes_produtos = ["PERFUMARIA", "OUTROS"]
    opcoes_pagamento = ["DINHEIRO", "PIX", "DÉBITO", "RECEBIMENTO", "CRÉDITO A V.", "CRÉDITO 2X", "CRÉDITO 3X"]
    opcoes_despesas = ["PRÓ LABORE", "SALÁRIOS", "COMISSÕES", "ALUGUEL", "IMPOSTOS", "MARKETING",
                       "TELEFONE", "INTERNET", "ÁGUA", "LUZ", "IPTU", "TAXA DE LIXO", "PAG. DE EMPRÉSTIMOS",
                       "MAT. DE LIMPEZA E ESCRITÓRIO", "LANCHE", "CONTADOR", "COMPRAS DE PRODUTO",
                       "TAXA DE ENTREGA", "MEDICAMENTOS LOJA", "SISTEMA SINTEGRA", "OUTROS CUSTOS"]

    var_vendedor = ctk.StringVar(value="Selecione")
    var_produto = ctk.StringVar(value="Selecione")
    var_pagamento = ctk.StringVar(value="Selecione")
    var_tipo_despesa = ctk.StringVar(value="OUTROS CUSTOS")

    frame_menu_lateral = ctk.CTkFrame(janela, width=240, corner_radius=0)
    frame_menu_lateral.pack(side="left", fill="y")
    frame_menu_lateral.pack_propagate(False)

    frame_conteudo = ctk.CTkFrame(janela, corner_radius=0, fg_color="transparent")
    frame_conteudo.pack(side="right", fill="both", expand=True)

    tela_registrar = ctk.CTkFrame(frame_conteudo, fg_color="transparent", corner_radius=0)
    tela_historico = ctk.CTkFrame(frame_conteudo, fg_color="transparent", corner_radius=0)
    tela_dashboard = ctk.CTkFrame(frame_conteudo, fg_color="transparent", corner_radius=0)
    tela_diario = ctk.CTkFrame(frame_conteudo, fg_color="transparent", corner_radius=0)
    tela_equipe = ctk.CTkFrame(frame_conteudo, fg_color="transparent", corner_radius=0)
    tela_despesas = ctk.CTkFrame(frame_conteudo, fg_color="transparent", corner_radius=0)
    tela_dre = ctk.CTkFrame(frame_conteudo, fg_color="transparent", corner_radius=0)
    tela_gestao = ctk.CTkFrame(frame_conteudo, fg_color="transparent", corner_radius=0)
    tela_desafio = ctk.CTkFrame(frame_conteudo, fg_color="transparent", corner_radius=0)
    tela_bonificacoes = ctk.CTkFrame(frame_conteudo, fg_color="transparent", corner_radius=0)

    # Telas que só podem ser abertas de dentro da Área de Gestão (após a senha).
    # Despesas fica de FORA de propósito (decisão do negócio: o caixa lança despesas).
    TELAS_PROTEGIDAS = [tela_dashboard, tela_equipe, tela_dre, tela_desafio, tela_bonificacoes]
    _estado_gestao = {
        "desbloqueado": False,                 # vira True depois da senha certa
        "ultima_atividade": time.monotonic(),  # última tecla/clique/movimento do mouse
        "tela_atual": None,
    }


    def _pedir_senha_gestao(ao_acertar):
        """Mostra um pop-up pedindo a senha; só chama `ao_acertar()` se acertar."""
        top_senha = ctk.CTkToplevel(janela)
        top_senha.title("Área Restrita")
        janela.update_idletasks()
        x = janela.winfo_rootx() + (janela.winfo_width() - 380) // 2
        y = janela.winfo_rooty() + (janela.winfo_height() - 230) // 3
        top_senha.geometry(f"380x230+{max(x, 0)}+{max(y, 0)}")  # centralizado na janela principal
        top_senha.transient(janela)
        top_senha.grab_set()

        ctk.CTkLabel(top_senha, text="🔒 Área de Gestão", font=Tema.SUBTITULO).pack(pady=(25, 5))
        ctk.CTkLabel(top_senha, text="Digite a senha para continuar:", font=Tema.LABEL).pack(pady=(0, 10))

        entry_senha_gestao = ctk.CTkEntry(top_senha, show="*", justify="center",
                                           font=ctk.CTkFont(size=16), corner_radius=Tema.RAIO_BOTAO)
        entry_senha_gestao.pack(pady=5)
        entry_senha_gestao.focus()

        label_erro_senha = ctk.CTkLabel(top_senha, text="", font=Tema.LABEL, text_color=Tema.VERMELHO)
        label_erro_senha.pack(pady=(5, 0))

        def conferir_senha(event=None):
            if verificar_senha(entry_senha_gestao.get(), hash_senha_gestao):
                top_senha.destroy()
                ao_acertar()
            else:
                label_erro_senha.configure(text="Senha incorreta. Tente novamente.")
                entry_senha_gestao.delete(0, "end")

        entry_senha_gestao.bind("<Return>", conferir_senha)
        ctk.CTkButton(top_senha, text="ENTRAR", fg_color=Tema.VERDE, hover_color=Tema.VERDE_HOVER,
                      font=ctk.CTkFont(size=16, weight="bold"), height=40, command=conferir_senha,
                      corner_radius=Tema.RAIO_BOTAO).pack(pady=15)


    def _atualizar_botao_gestao():
        """Mostra no menu se a Gestão está aberta (🔓) ou trancada (🔒)."""
        try:
            botao_gestao.configure(text="🔓 Gestão" if _estado_gestao["desbloqueado"] else "🔒 Gestão")
        except NameError:
            pass  # o botão ainda não foi criado (início do programa)


    def abrir_area_gestao():
        """Comando do botão 'Gestão' do menu lateral: pede senha se estiver trancada, senão vai direto."""
        if _estado_gestao["desbloqueado"]:
            mostrar_tela(tela_gestao)
        else:
            def _ao_acertar_senha():
                _estado_gestao["desbloqueado"] = True
                _estado_gestao["ultima_atividade"] = time.monotonic()
                _atualizar_botao_gestao()
                mostrar_tela(tela_gestao)
            _pedir_senha_gestao(_ao_acertar_senha)


    def bloquear_area_gestao():
        """Tranca a Área de Gestão de novo (sem precisar fechar o programa) e volta pro início."""
        _estado_gestao["desbloqueado"] = False
        _atualizar_botao_gestao()
        mostrar_tela(tela_registrar)


    # --- Bloqueio automático por inatividade -------------------------------
    # Qualquer tecla, clique, rolagem ou movimento do mouse conta como "uso".
    # A cada 10 segundos o sistema confere: se a Gestão está aberta e ninguém
    # mexeu no programa por `minutos_bloqueio_gestao` minutos, ela se tranca.
    # Se a pessoa estava numa tela protegida (Dashboard, DRE...), volta para
    # Registrar Venda; se estava em outra tela, continua onde estava.
    def _registrar_atividade(event=None):
        _estado_gestao["ultima_atividade"] = time.monotonic()

    for _evento in ("<KeyPress>", "<ButtonPress>", "<MouseWheel>", "<Motion>"):
        janela.bind_all(_evento, _registrar_atividade, add="+")


    def _verificar_bloqueio_automatico():
        if _estado_gestao["desbloqueado"]:
            parado_seg = time.monotonic() - _estado_gestao["ultima_atividade"]
            if parado_seg >= minutos_bloqueio_gestao * 60:
                _estado_gestao["desbloqueado"] = False
                _atualizar_botao_gestao()
                tela = _estado_gestao["tela_atual"]
                if tela in TELAS_PROTEGIDAS or tela is tela_gestao:
                    mostrar_tela(tela_registrar)
                    exibir_feedback(lbl_feedback, "🔒 Gestão bloqueada por inatividade", Tema.AMARELO, segundos=10)
        janela.after(10_000, _verificar_bloqueio_automatico)


    def _criar_botao_voltar_gestao(tela_pai):
        """Cria um botão '← Voltar' no topo das telas que só existem dentro da Área de Gestão."""
        ctk.CTkButton(tela_pai, text="← Voltar para Área de Gestão", font=ctk.CTkFont(size=13, weight="bold"),
                      fg_color="transparent", text_color=Tema.AZUL, hover_color=("gray85", "gray20"),
                      height=30, width=240, anchor="w", corner_radius=Tema.RAIO_BOTAO,
                      command=lambda: mostrar_tela(tela_gestao)).pack(anchor="w", padx=20, pady=(15, 0))


    def _criar_cartao_kpi(pai, titulo):
        """Cria um 'cartão' com um número BEM grande e legível (tipo um resumo de painel),
        para quem só quer bater o olho e já entender o resultado, sem precisar ler a tabela
        inteira. Devolve o label do valor, para ser atualizado depois com o número de verdade."""
        cartao = ctk.CTkFrame(pai, corner_radius=Tema.RAIO, fg_color=("gray86", "gray17"))
        cartao.pack(side="left", fill="both", expand=True, padx=8)
        ctk.CTkLabel(cartao, text=titulo, font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=Tema.CINZA_TEXTO).pack(pady=(16, 2))
        label_valor = ctk.CTkLabel(cartao, text="R$ 0,00", font=ctk.CTkFont(size=28, weight="bold"))
        label_valor.pack(pady=(0, 16))
        return label_valor


    # --- Pequenos "blocos de montar" reutilizados nas telas abaixo ---
    def rotulo_secao(pai, texto):
        return ctk.CTkLabel(pai, text=texto, font=Tema.TITULO, text_color="white")


    def exibir_feedback(label, texto, cor, segundos=3):
        """Mostra uma mensagem de aviso/sucesso por alguns segundos e depois some sozinha."""
        label.configure(text=texto, text_color=cor)
        janela.after(int(segundos * 1000), lambda: label.configure(text=""))


    def inserir_linhas_zebra(tree, linhas, formatador=lambda l: tuple(l), tag_extra=None):
        """Insere linhas numa tabela alternando a cor de fundo (efeito 'zebra').

        Importante: o resultado de `formatador` precisa ser sempre uma tupla
        ou lista "de verdade" (nunca o objeto sqlite3.Row original) -- o
        Tkinter só separa os valores em colunas quando recebe list/tuple; um
        sqlite3.Row passado direto vira um texto só (tipo "<sqlite3.Row
        object at 0x...>"), que é exibido quebrado pela tabela.
        """
        for i, linha in enumerate(linhas):
            tags = ["linha_par" if i % 2 == 0 else "linha_impar"]
            if tag_extra:
                tags.append(tag_extra(linha))
            tree.insert("", "end", values=tuple(formatador(linha)), tags=tuple(tags))


    # =============================================================================
    # TELA 1: REGISTRAR VENDA
    # =============================================================================
    rotulo_secao(tela_registrar, "REGISTRAR NOVA VENDA").pack(pady=(40, 30))
    frame_form = ctk.CTkFrame(tela_registrar, fg_color="transparent", corner_radius=0)
    frame_form.pack()

    f_label_venda = ctk.CTkFont(size=24, weight="bold")
    f_menu_venda = ctk.CTkFont(size=22, weight="bold")
    f_drop_venda = ctk.CTkFont(size=20, weight="bold")

    ctk.CTkLabel(frame_form, text="Funcionário:", font=f_label_venda, text_color="white").pack(pady=(10, 0))
    menu_vendedor = ctk.CTkOptionMenu(frame_form, values=[], variable=var_vendedor, width=350, height=45,
                                       font=f_menu_venda, dropdown_font=f_drop_venda, text_color="white",
                                       fg_color=Tema.VERDE, button_color=Tema.VERDE_HOVER, corner_radius=Tema.RAIO_BOTAO)
    menu_vendedor.pack(pady=5)

    ctk.CTkLabel(frame_form, text="Tipo de Produto:", font=f_label_venda, text_color="white").pack(pady=(15, 0))
    ctk.CTkOptionMenu(frame_form, values=opcoes_produtos, variable=var_produto, width=350, height=45,
                       font=f_menu_venda, dropdown_font=f_drop_venda, text_color="white",
                       fg_color=Tema.VERDE, button_color=Tema.VERDE_HOVER, corner_radius=Tema.RAIO_BOTAO).pack(pady=5)

    ctk.CTkLabel(frame_form, text="Forma de Pagamento:", font=f_label_venda, text_color="white").pack(pady=(15, 0))
    ctk.CTkOptionMenu(frame_form, values=opcoes_pagamento, variable=var_pagamento, width=350, height=45,
                       font=f_menu_venda, dropdown_font=f_drop_venda, text_color="white",
                       fg_color=Tema.VERDE, button_color=Tema.VERDE_HOVER, corner_radius=Tema.RAIO_BOTAO).pack(pady=5)

    ctk.CTkLabel(frame_form, text="Valor Total (R$):", font=ctk.CTkFont(size=24, weight="bold"), text_color="white").pack(pady=(25, 0))
    entry_valor = ctk.CTkEntry(frame_form, placeholder_text="0,00", font=ctk.CTkFont(size=34, weight="bold"),
                                width=250, height=55, justify="center", text_color="white", corner_radius=Tema.RAIO_BOTAO)
    entry_valor.pack(pady=10)

    ctk.CTkLabel(frame_form, text="Data da Venda (DD/MM/AAAA):", font=f_label_venda, text_color="white").pack(pady=(15, 0))
    entry_data_venda_manual = ctk.CTkEntry(frame_form, font=f_menu_venda, width=350, height=45, justify="center",
                                            text_color="white", corner_radius=Tema.RAIO_BOTAO)
    entry_data_venda_manual.insert(0, datetime.now().strftime("%d/%m/%Y"))
    entry_data_venda_manual.pack(pady=5)

    lbl_feedback = ctk.CTkLabel(frame_form, text="", font=ctk.CTkFont(size=18, weight="bold"))
    lbl_feedback.pack(pady=5)


    def salvar_venda(event=None):
        vend, prod, pag = var_vendedor.get(), var_produto.get(), var_pagamento.get()
        val_texto = entry_valor.get().strip()
        data_digitada = entry_data_venda_manual.get().strip()

        if vend in ("Selecione", "Nenhum Vendedor Ativo") or prod == "Selecione" or pag == "Selecione" or val_texto == "":
            exibir_feedback(lbl_feedback, "⚠️ Preencha todos os campos!", Tema.VERMELHO)
            return

        val_total = texto_para_valor(val_texto)
        data_base = texto_para_data(data_digitada)
        if val_total is None or data_base is None:
            exibir_feedback(lbl_feedback, "⚠️ Valor ou Data inválida!", Tema.VERMELHO)
            return
        if val_total == 0:
            exibir_feedback(lbl_feedback, "⚠️ O valor não pode ser zero!", Tema.VERMELHO)
            return

        d_venda = data_base.strftime("%d/%m/%Y")
        h_venda = datetime.now().strftime("%I:%M:%S %p").lstrip("0")

        try:
            if pag in ["DINHEIRO", "RECEBIMENTO", "PIX", "DÉBITO"]:
                banco.executar(
                    'INSERT INTO vendas (valor, vendedor, data_venda, data_vencimento, horario, tipo_produto, tipo_pagamento) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (val_total, vend, d_venda, d_venda, h_venda, prod, pag), commit=True)
            elif pag == "CRÉDITO A V.":
                d_venc = (data_base + timedelta(days=30)).strftime("%d/%m/%Y")
                banco.executar(
                    'INSERT INTO vendas (valor, vendedor, data_venda, data_vencimento, horario, tipo_produto, tipo_pagamento) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (val_total, vend, d_venda, d_venc, h_venda, prod, pag), commit=True)
            elif pag in ["CRÉDITO 2X", "CRÉDITO 3X"]:
                parcelas = 2 if pag == "CRÉDITO 2X" else 3
                valores_parcelas = dividir_em_parcelas(val_total, parcelas)
                linhas = []
                for i in range(1, parcelas + 1):
                    d_venc = (data_base + timedelta(days=30 * i)).strftime("%d/%m/%Y")
                    linhas.append((valores_parcelas[i - 1], vend, d_venda, d_venc, h_venda, prod, f"{pag} ({i}/{parcelas})"))
                banco.executar_muitos(
                    'INSERT INTO vendas (valor, vendedor, data_venda, data_vencimento, horario, tipo_produto, tipo_pagamento) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)', linhas)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Registrar Venda")
            return

        exibir_feedback(lbl_feedback, "✔️ Venda registrada com sucesso!", Tema.VERDE)
        entry_valor.delete(0, "end")
        entry_data_venda_manual.delete(0, "end")
        entry_data_venda_manual.insert(0, datetime.now().strftime("%d/%m/%Y"))
        entry_valor.focus()


    btn_salvar = ctk.CTkButton(frame_form, text="SALVAR VENDA", font=ctk.CTkFont(size=24, weight="bold"), height=60,
                                width=350, command=salvar_venda, corner_radius=Tema.RAIO_BOTAO,
                                fg_color=Tema.VERDE, hover_color=Tema.VERDE_HOVER)
    btn_salvar.pack(pady=(15, 10))

    entry_valor.bind("<Return>", salvar_venda)
    entry_data_venda_manual.bind("<Return>", salvar_venda)


    # =============================================================================
    # TELA 2: HISTÓRICO DE VENDAS
    # =============================================================================
    ctk.CTkLabel(tela_historico, text="HISTÓRICO DE VENDAS E EDIÇÃO", font=Tema.SUBTITULO).pack(pady=(20, 10))
    frame_filtros_h = ctk.CTkFrame(tela_historico, fg_color="transparent", corner_radius=0)
    frame_filtros_h.pack(pady=5, padx=20, fill="x")

    var_filtro_h = ctk.StringVar(value="Todos")
    var_ordem_h = ctk.StringVar(value="Mais Recentes")

    ctk.CTkLabel(frame_filtros_h, text="Vendedor:", font=Tema.LABEL).pack(side="left", padx=(0, 5))
    menu_filtro_h = ctk.CTkOptionMenu(frame_filtros_h, values=[], variable=var_filtro_h, font=ctk.CTkFont(size=14),
                                       command=lambda _: atualizar_historico())
    menu_filtro_h.pack(side="left", padx=5)

    ctk.CTkLabel(frame_filtros_h, text="Ordem:", font=Tema.LABEL).pack(side="left", padx=(15, 5))
    ctk.CTkOptionMenu(frame_filtros_h, values=["Mais Recentes", "Mais Antigas"], variable=var_ordem_h,
                       font=ctk.CTkFont(size=14), command=lambda _: atualizar_historico()).pack(side="left", padx=5)

    ctk.CTkLabel(frame_filtros_h, text="Data Específica:", font=Tema.LABEL).pack(side="left", padx=(15, 5))
    entry_data_h = ctk.CTkEntry(frame_filtros_h, placeholder_text="DD/MM/AAAA", font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
    entry_data_h.pack(side="left", padx=5)
    entry_data_h.bind("<Return>", lambda e: atualizar_historico())
    entry_data_h.bind("<FocusOut>", lambda e: atualizar_historico())

    lbl_contagem_h = ctk.CTkLabel(frame_filtros_h, text="", font=ctk.CTkFont(size=13), text_color=Tema.CINZA_TEXTO)
    lbl_contagem_h.pack(side="right", padx=10)

    frame_tab_h = ctk.CTkFrame(tela_historico, corner_radius=0)
    frame_tab_h.pack(pady=10, padx=20, fill="both", expand=True)
    scroll_h = ttk.Scrollbar(frame_tab_h, orient="vertical")
    scroll_h.pack(side="right", fill="y")
    colunas_h = ("id", "vendedor", "produto", "valor", "pagamento", "horario", "data_venda", "vencimento")
    tabela_h = nova_tabela(frame_tab_h, columns=colunas_h, show="headings", yscrollcommand=scroll_h.set)
    scroll_h.configure(command=tabela_h.yview)

    for c, texto in zip(colunas_h, ["ID", "Vendedor", "Produto", "Valor (R$)", "Forma Pagamento", "Horário", "Vendido em", "Vencimento"]):
        tabela_h.heading(c, text=texto)
        tabela_h.column(c, width=120, anchor="center")
    tabela_h.column("id", width=60)
    tabela_h.column("pagamento", width=180)
    tabela_h.pack(side="left", fill="both", expand=True)


    def atualizar_historico():
        for item in tabela_h.get_children():
            tabela_h.delete(item)
        vend, ordem, data = var_filtro_h.get(), var_ordem_h.get(), entry_data_h.get().strip()
        dir_sql = "DESC" if ordem == "Mais Recentes" else "ASC"

        query = "SELECT id, vendedor, tipo_produto, valor, tipo_pagamento, horario, data_venda, data_vencimento FROM vendas WHERE 1=1"
        params = []
        if vend != "Todos":
            query += f" AND {SQL_NOME_VENDEDOR} = ?"
            params.append(vend)
        if data != "":
            query += " AND data_venda = ?"
            params.append(data)

        query += f" ORDER BY substr(data_venda, 7, 4) {dir_sql}, substr(data_venda, 4, 2) {dir_sql}, substr(data_venda, 1, 2) {dir_sql}, id {dir_sql} LIMIT 1000"

        try:
            resultados = banco.consultar_todos(query, params)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Histórico")
            return

        inserir_linhas_zebra(tabela_h, resultados, formatador=lambda l: (l[0], normalizar_nome_vendedor(l[1]) or l[1], l[2], f"{l[3]:.2f}", l[4], l[5], l[6], l[7]))
        aviso = " (mostrando as 1.000 mais recentes)" if len(resultados) >= 1000 else ""
        lbl_contagem_h.configure(text=f"{len(resultados)} venda(s) encontrada(s){aviso}")


    def editar_venda():
        selecao = tabela_h.selection()
        if not selecao:
            messagebox.showwarning("Aviso", "Selecione uma linha para editar.")
            return

        dados_linha = tabela_h.item(selecao[0], "values")
        id_venda, vend_atual, prod_atual, val_atual_str, pag_atual = dados_linha[0], dados_linha[1], dados_linha[2], dados_linha[3], dados_linha[4]

        top_edit = ctk.CTkToplevel(janela)
        top_edit.title(f"Editar Venda ID {id_venda}")
        top_edit.geometry("450x520")
        top_edit.grab_set()

        ctk.CTkLabel(top_edit, text="Vendedor:", font=Tema.LABEL).pack(pady=(20, 0))
        var_vend_e = ctk.StringVar(value=vend_atual)
        ctk.CTkOptionMenu(top_edit, values=obter_todos_historico(), variable=var_vend_e, font=ctk.CTkFont(size=14)).pack(pady=5)

        ctk.CTkLabel(top_edit, text="Produto:", font=Tema.LABEL).pack(pady=(10, 0))
        var_prod_e = ctk.StringVar(value=prod_atual)
        ctk.CTkOptionMenu(top_edit, values=opcoes_produtos, variable=var_prod_e, font=ctk.CTkFont(size=14)).pack(pady=5)

        ctk.CTkLabel(top_edit, text="Pagamento:", font=Tema.LABEL).pack(pady=(10, 0))
        var_pag_e = ctk.StringVar(value=pag_atual)
        ctk.CTkOptionMenu(top_edit, values=opcoes_pagamento, variable=var_pag_e, font=ctk.CTkFont(size=14)).pack(pady=5)

        ctk.CTkLabel(top_edit, text="Valor (R$):", font=Tema.LABEL).pack(pady=(10, 0))
        entry_val_e = ctk.CTkEntry(top_edit, justify="center", font=ctk.CTkFont(size=16), corner_radius=Tema.RAIO_BOTAO)
        entry_val_e.insert(0, val_atual_str)
        entry_val_e.pack(pady=5)

        def salvar_edicao(event=None):
            novo_valor = texto_para_valor(entry_val_e.get())
            if novo_valor is None:
                messagebox.showerror("Erro", "Valor inválido!")
                return
            if novo_valor == 0:
                messagebox.showerror("Erro", "O valor não pode ser zero!")
                return
            try:
                banco.executar("UPDATE vendas SET vendedor = ?, tipo_produto = ?, tipo_pagamento = ?, valor = ? WHERE id = ?",
                                (var_vend_e.get(), var_prod_e.get(), var_pag_e.get(), novo_valor, id_venda), commit=True)
            except ErroBancoDados:
                alerta_erro_banco("Erro ao Salvar Edição")
                return
            top_edit.destroy()
            atualizar_historico()

        entry_val_e.bind("<Return>", salvar_edicao)
        ctk.CTkButton(top_edit, text="SALVAR ALTERAÇÕES", fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER,
                      font=ctk.CTkFont(size=16, weight="bold"), height=40, command=salvar_edicao,
                      corner_radius=Tema.RAIO_BOTAO).pack(pady=30)


    def deletar_venda():
        selecao = tabela_h.selection()
        if not selecao:
            messagebox.showwarning("Aviso", "Selecione uma linha para eliminar.")
            return
        id_venda = tabela_h.item(selecao[0], "values")[0]
        if messagebox.askyesno("Confirmar", f"Eliminar a venda ID {id_venda}? Isso afetará o Dashboard."):
            try:
                banco.executar("DELETE FROM vendas WHERE id = ?", (id_venda,), commit=True)
            except ErroBancoDados:
                alerta_erro_banco("Erro ao Eliminar Venda")
                return
            atualizar_historico()


    frame_botoes_h = ctk.CTkFrame(tela_historico, fg_color="transparent", corner_radius=0)
    frame_botoes_h.pack(pady=10)
    ctk.CTkButton(frame_botoes_h, text="✏️ Editar Selecionada", font=ctk.CTkFont(size=16, weight="bold"),
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, height=40, command=editar_venda,
                  corner_radius=Tema.RAIO_BOTAO).pack(side="left", padx=10)
    ctk.CTkButton(frame_botoes_h, text="🗑️ Eliminar Selecionada", font=ctk.CTkFont(size=16, weight="bold"),
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, height=40, command=deletar_venda,
                  corner_radius=Tema.RAIO_BOTAO).pack(side="left", padx=10)
    criar_botoes_exportar(frame_botoes_h, tabela_h, "historico_de_vendas", "Histórico de Vendas").pack(side="left", padx=10)


    # =============================================================================
    # TELA 3: DASHBOARD BI DE VENDAS
    # =============================================================================
    _criar_botao_voltar_gestao(tela_dashboard)
    ctk.CTkLabel(tela_dashboard, text="DASHBOARD DE INTELIGÊNCIA", font=Tema.SUBTITULO).pack(pady=(20, 0))

    frame_filtros_d = ctk.CTkFrame(tela_dashboard, fg_color="transparent", corner_radius=0)
    frame_filtros_d.pack(pady=(10, 0), padx=20, fill="x")

    # Começa vazio de propósito: assim que a tela for aberta pela primeira vez,
    # a lógica em mostrar_tela() escolhe um ANO REAL (o mais recente com dados,
    # ou seja, o ano vigente) em vez de cair em "Todos" por padrão. "Todos"
    # continua existindo na lista para quem quiser somar todos os anos de propósito.
    var_ano_d = ctk.StringVar(value="")
    menu_ano_d = ctk.CTkOptionMenu(frame_filtros_d, variable=var_ano_d, width=120, font=ctk.CTkFont(size=14))
    ctk.CTkLabel(frame_filtros_d, text="Ano:", font=Tema.LABEL).pack(side="left", padx=(0, 5))
    menu_ano_d.pack(side="left", padx=5)

    frame_opcoes_v = ctk.CTkFrame(tela_dashboard, fg_color="transparent", corner_radius=0)
    frame_opcoes_v.pack(pady=(10, 5), padx=20, fill="x")
    ctk.CTkLabel(frame_opcoes_v, text="Analisar Equipe:", font=Tema.LABEL).pack(side="left", padx=(0, 10))

    dict_vars_vendedores = {}


    def definir_marcacoes(todos=True, apenas_ativos=False):
        ativos = obter_vendedores_ativos()
        for v, var in dict_vars_vendedores.items():
            if todos:
                var.set(True)
            elif apenas_ativos:
                var.set(v in ativos)
        processar_dashboard()


    ctk.CTkButton(frame_opcoes_v, text="Marcar Todos", width=80, height=30, font=ctk.CTkFont(size=14),
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, command=lambda: definir_marcacoes(True, False),
                  corner_radius=Tema.RAIO_BOTAO).pack(side="left", padx=5)
    ctk.CTkButton(frame_opcoes_v, text="Somente Ativos", width=120, height=30, font=ctk.CTkFont(size=14),
                  fg_color=Tema.VERDE, hover_color=Tema.VERDE_HOVER, command=lambda: definir_marcacoes(False, True),
                  corner_radius=Tema.RAIO_BOTAO).pack(side="left", padx=5)

    scroll_vendedores = ctk.CTkScrollableFrame(tela_dashboard, height=50, orientation="horizontal", fg_color="transparent")
    scroll_vendedores.pack(pady=(0, 5), padx=20, fill="x")


    def atualizar_checkboxes_vendedores():
        for w in scroll_vendedores.winfo_children():
            w.destroy()
        todos = obter_todos_historico()
        for v in todos:
            if v not in dict_vars_vendedores:
                dict_vars_vendedores[v] = ctk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(scroll_vendedores, text=v, variable=dict_vars_vendedores[v],
                                  font=ctk.CTkFont(size=14), command=processar_dashboard,
                                  fg_color=Tema.VERDE, hover_color=Tema.VERDE_HOVER)
            cb.pack(side="left", padx=10)


    abas_d = ctk.CTkTabview(tela_dashboard)
    abas_d.pack(fill="both", expand=True, padx=20, pady=5)
    aba_v = abas_d.add("Vendedores (Faturado)")
    aba_p = abas_d.add("Produtos (Faturado)")
    aba_pag = abas_d.add("Pagamento (Faturado)")
    aba_rec = abas_d.add("Caixa (Recebido)")
    aba_c = abas_d.add("Comissões (A Pagar)")
    cols_d = ["Nome", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez", "TOTAL"]


    def criar_aba(pai, titulo, alt_grafico):
        # A TABELA vem primeiro e ocupa o espaço que sobrar (números grandes e visíveis,
        # sem precisar ficar rolando a tela) -- o GRÁFICO fica embaixo, numa faixa menor
        # e de altura fixa, só para dar a visão geral da tendência ao longo do ano.
        ft = ctk.CTkFrame(pai, corner_radius=0)
        ft.pack(pady=(5, 5), fill="both", expand=True)
        t = nova_tabela(ft, columns=cols_d, show="headings")
        t.heading("Nome", text=f"{titulo} · R$")
        t.column("Nome", width=190, minwidth=170, anchor="w")
        for c in cols_d[1:]:
            t.heading(c, text=c)
            t.column(c, width=118 if c == "TOTAL" else 100, minwidth=90, anchor="e")
        t.pack(fill="both", expand=True)

        fg = ctk.CTkFrame(pai, height=alt_grafico, corner_radius=0)
        fg.pack(pady=(0, 5), fill="x")
        fg.pack_propagate(False)
        return fg, t


    fg_v, t_v = criar_aba(aba_v, "VENDEDOR", 240)
    fg_p, t_p = criar_aba(aba_p, "PRODUTO", 240)
    fg_pag, t_pag = criar_aba(aba_pag, "PAGAMENTO", 240)
    fg_rec, t_rec = criar_aba(aba_rec, "RECEBIMENTOS", 240)
    fg_c, t_c = criar_aba(aba_c, "COMISSÃO (1%)", 240)

    TABS_DASHBOARD = {
        "Vendedores (Faturado)": (t_v, "dashboard_vendedores", "Faturamento por Vendedor"),
        "Produtos (Faturado)": (t_p, "dashboard_produtos", "Faturamento por Produto"),
        "Pagamento (Faturado)": (t_pag, "dashboard_pagamento", "Faturamento por Forma de Pagamento"),
        "Caixa (Recebido)": (t_rec, "dashboard_caixa", "Recebimentos (Caixa)"),
        "Comissões (A Pagar)": (t_c, "dashboard_comissoes", "Comissões a Pagar"),
    }


    def exportar_aba_dashboard_ativa(tipo):
        aba_atual = abas_d.get()
        tree, nome_arquivo, titulo = TABS_DASHBOARD[aba_atual]
        if tipo == "excel":
            exportar_tabela_excel(tree, nome_arquivo, titulo)
        else:
            exportar_tabela_pdf(tree, nome_arquivo, titulo)


    frame_exportar_dash = ctk.CTkFrame(tela_dashboard, fg_color="transparent")
    frame_exportar_dash.pack(pady=(0, 5), padx=20, anchor="e")
    ctk.CTkButton(frame_exportar_dash, text="📊 Exportar aba atual (Excel)", font=ctk.CTkFont(size=13, weight="bold"),
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, height=32, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: exportar_aba_dashboard_ativa("excel")).pack(side="left", padx=5)
    ctk.CTkButton(frame_exportar_dash, text="📄 Exportar aba atual (PDF)", font=ctk.CTkFont(size=13, weight="bold"),
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, height=32, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: exportar_aba_dashboard_ativa("pdf")).pack(side="left", padx=5)

    cores_extra_g = ["#FF69B4", "#1E90FF", "#32CD32", "#9370DB", "#DAA520", "#FF4500", "#00CED1", "#FF1493"]
    # Cores de TEXTO nas tabelas: tons claros, legíveis sobre o fundo escuro.
    cores_extra_t = ["#FF8AC6", "#6FB4FF", "#6EE07A", "#B9A3F5", "#F2C94C", "#FF8A65", "#4DD9E0", "#FF6FB5"]

    c_p_g = {"PERFUMARIA": "#FF1493", "OUTROS": "#A9A9A9"}
    c_p_t = {"PERFUMARIA": "#FF8AC6", "OUTROS": "#C8C8C8", "TOTAL": "white"}
    c_pag_g = {"DINHEIRO": "#2E8B57", "PIX": "#00CED1", "DÉBITO": "#4682B4", "RECEBIMENTO": "#DAA520",
               "CRÉDITO A V.": "#9370DB", "CRÉDITO 2X": "#8A2BE2", "CRÉDITO 3X": "#4B0082"}
    c_pag_t = {"DINHEIRO": "#6EE07A", "PIX": "#4DD9E0", "DÉBITO": "#6FB4FF", "RECEBIMENTO": "#F2C94C",
               "CRÉDITO A V.": "#B9A3F5", "CRÉDITO 2X": "#D08CFF", "CRÉDITO 3X": "#9FA8DA", "TOTAL": "white"}

    for k, cor in c_p_t.items():
        t_p.tag_configure(f"tag_{k}", foreground=cor)
    for k, cor in c_pag_t.items():
        t_pag.tag_configure(f"tag_{k}", foreground=cor)


    def processar_dashboard(*args):
        plt.close("all")
        ano = var_ano_d.get()

        vend_selecionados = [v for v, var in dict_vars_vendedores.items() if var.get()]

        for f in [fg_v, fg_p, fg_pag, fg_rec, fg_c]:
            for w in f.winfo_children():
                w.destroy()
        for t in [t_v, t_p, t_pag, t_rec, t_c]:
            for item in t.get_children():
                t.delete(item)

        todos_vendedores = obter_todos_historico()
        # Cor fixa por posição na lista (a mesma vendedora mantém a cor entre telas).
        c_v_g, c_v_t = {}, {"TOTAL": "white"}

        for i, v in enumerate(todos_vendedores):
            if v not in c_v_g:
                c_v_g[v] = cores_extra_g[i % len(cores_extra_g)]
                c_v_t[v] = cores_extra_t[i % len(cores_extra_t)]
                t_v.tag_configure(f"tag_{v}", foreground=c_v_t[v])
                t_rec.tag_configure(f"tag_{v}", foreground=c_v_t[v])
                t_c.tag_configure(f"tag_{v}", foreground=c_v_t[v])

        param_v = []
        f_venda = ""
        if ano != "Todos":
            f_venda += " AND substr(data_venda, 7, 4) = ?"
            param_v.append(ano)

        if not vend_selecionados:
            f_venda += " AND 1=0"
        else:
            placeholders = ",".join("?" for _ in vend_selecionados)
            f_venda += f" AND {SQL_NOME_VENDEDOR} IN ({placeholders})"
            param_v.extend(vend_selecionados)

        param_c = []
        f_caixa = ""
        if ano != "Todos":
            f_caixa += " AND substr(data_vencimento, 7, 4) = ?"
            param_c.append(ano)

        if not vend_selecionados:
            f_caixa += " AND 1=0"
        else:
            placeholders = ",".join("?" for _ in vend_selecionados)
            f_caixa += f" AND {SQL_NOME_VENDEDOR} IN ({placeholders})"
            param_c.extend(vend_selecionados)

        try:
            d_v = banco.consultar_todos(
                f"SELECT {SQL_NOME_VENDEDOR}, UPPER(tipo_produto), UPPER(tipo_pagamento), "
                f"substr(data_venda, 4, 2), SUM(valor) FROM vendas WHERE 1=1 {f_venda} GROUP BY 1, 2, 3, 4", param_v)
            d_c = banco.consultar_todos(
                f"SELECT {SQL_NOME_VENDEDOR}, substr(data_vencimento, 4, 2), SUM(valor) "
                f"FROM vendas WHERE 1=1 {f_caixa} GROUP BY 1, 2", param_c)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Dashboard")
            return

        m_v = {v: novo_mapa_meses() for v in vend_selecionados}
        m_p = {p: novo_mapa_meses() for p in opcoes_produtos}
        m_pag = {pag: novo_mapa_meses() for pag in opcoes_pagamento}
        t_v_m = novo_mapa_meses()
        t_v_g = 0.0

        for vd, pd, pg, m_num, val in d_v:
            vd, pd, pg = vd.strip(), pd.strip(), pg.strip()
            if "CRÉDITO 2X" in pg:
                pg = "CRÉDITO 2X"
            if "CRÉDITO 3X" in pg:
                pg = "CRÉDITO 3X"

            if vd in vend_selecionados and m_num in m_v.get(vd, {}):
                m_v[vd][m_num] += val
            if pd in opcoes_produtos and m_num in m_p.get(pd, {}):
                m_p[pd][m_num] += val
            if pg in opcoes_pagamento and m_num in m_pag.get(pg, {}):
                m_pag[pg][m_num] += val
            if m_num in t_v_m:
                t_v_m[m_num] += val
            t_v_g += val

        m_rec = {v: novo_mapa_meses() for v in vend_selecionados}
        t_c_m = novo_mapa_meses()
        t_c_g = 0.0
        for vd, m_num, val in d_c:
            vd = vd.strip()
            if vd in vend_selecionados and m_num in m_rec.get(vd, {}):
                m_rec[vd][m_num] += val
            if m_num in t_c_m:
                t_c_m[m_num] += val
            t_c_g += val

        m_com = {v: {m: val * 0.01 for m, val in m_rec[v].items()} for v in vend_selecionados}
        t_com_m = novo_mapa_meses()
        t_com_g = 0.0

        def inserir_tab(tab, nomes, matriz, dict_cor, is_comiss=False):
            nonlocal t_com_g
            c = 0
            for n in nomes:
                if is_comiss and n in _sem_comissao:
                    continue
                vals = list(matriz[n].values())
                tab.insert("", "end", values=[n] + [valor_dre(v) for v in vals] + [valor_dre(sum(vals))],
                           tags=(f"tag_{n}" if n in dict_cor else "tag_TOTAL", "linha_par" if c % 2 == 0 else "linha_impar"))
                if is_comiss:
                    for m, v in matriz[n].items():
                        t_com_m[m] += v
                    t_com_g += sum(vals)
                c += 1

        inserir_tab(t_v, vend_selecionados, m_v, c_v_t)
        inserir_tab(t_p, opcoes_produtos, m_p, c_p_t)
        inserir_tab(t_pag, opcoes_pagamento, m_pag, c_pag_t)
        inserir_tab(t_rec, vend_selecionados, m_rec, c_v_t)
        inserir_tab(t_c, vend_selecionados, m_com, c_v_t, True)

        t_v.insert("", "end", values=["TOTAL FATURADO"] + [valor_dre(t_v_m[f"{i:02d}"]) for i in range(1, 13)] + [valor_dre(t_v_g)], tags=("tag_TOTAL",))
        t_p.insert("", "end", values=["TOTAL FATURADO"] + [valor_dre(t_v_m[f"{i:02d}"]) for i in range(1, 13)] + [valor_dre(t_v_g)], tags=("tag_TOTAL",))
        t_pag.insert("", "end", values=["TOTAL FATURADO"] + [valor_dre(t_v_m[f"{i:02d}"]) for i in range(1, 13)] + [valor_dre(t_v_g)], tags=("tag_TOTAL",))
        t_rec.insert("", "end", values=["TOTAL RECEBIDO"] + [valor_dre(t_c_m[f"{i:02d}"]) for i in range(1, 13)] + [valor_dre(t_c_g)], tags=("tag_TOTAL",))
        t_c.insert("", "end", values=["TOTAL A PAGAR"] + [valor_dre(t_com_m[f"{i:02d}"]) for i in range(1, 13)] + [valor_dre(t_com_g)], tags=("tag_TOTAL",))

        def desenhar_grafico_linhas(matriz, frame_destino, nomes_validos, dict_cor, titulo_grafico, is_comissao=False):
            fig, ax = plt.subplots(figsize=(6, 2.5), dpi=100)
            meses_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
            tem_dado = False
            for nome in nomes_validos:
                if is_comissao and nome in _sem_comissao:
                    continue
                valores_linha = list(matriz[nome].values())
                if sum(valores_linha) > 0:
                    ax.plot(meses_labels, valores_linha, marker="o", label=nome, color=dict_cor.get(nome, "#e8e8e8"), linewidth=2)
                    tem_dado = True
            if tem_dado:
                ax.set_title(f"{titulo_grafico} - {'Todos os Anos' if ano == 'Todos' else ano}", fontsize=10)
                ax.set_ylabel("Valor (R$)")
                ax.legend(fontsize=7, loc="center left", bbox_to_anchor=(1, 0.5))
                ax.grid(axis="y", linestyle="--", alpha=0.5)
                ax.ticklabel_format(style="plain", axis="y")
            else:
                ax.text(0.5, 0.5, "Selecione um vendedor / Sem registros.", ha="center", va="center")
                ax.axis("off")

            fig.subplots_adjust(right=0.75)
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=frame_destino)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)

        desenhar_grafico_linhas(m_v, fg_v, vend_selecionados, c_v_g, "Evolução Mensal de Faturamento")
        desenhar_grafico_linhas(m_p, fg_p, opcoes_produtos, c_p_g, "Evolução Mensal de Volume por Produto")
        desenhar_grafico_linhas(m_pag, fg_pag, opcoes_pagamento, c_pag_g, "Evolução Mensal por Pagamento")
        desenhar_grafico_linhas(m_rec, fg_rec, vend_selecionados, c_v_g, "Evolução Mensal do Fluxo de Caixa")
        desenhar_grafico_linhas(m_com, fg_c, vend_selecionados, c_v_g, "Evolução de Comissões", is_comissao=True)


    menu_ano_d.configure(command=processar_dashboard)


    # =============================================================================
    # TELA 4: FECHAMENTO DE CAIXA (substitui o antigo "Relatório Diário")
    # =============================================================================
    # Confere SOMENTE o dinheiro da gaveta:
    #   Esperado = troco inicial + vendas em DINHEIRO do dia + suprimentos - sangrias
    #   Diferença = contado - esperado  (negativo = FALTA, positivo = SOBRA)
    # O fechamento fica salvo por dia (pode ser reaberto e corrigido). A aba
    # "Histórico de Fechamentos" lista os dias fechados de um mês. Os números do
    # sistema (vendas, sangrias...) são sempre recalculados na hora, então se
    # uma venda for corrigida depois, o histórico mostra o valor corrigido.
    ctk.CTkLabel(tela_diario, text="FECHAMENTO DE CAIXA", font=Tema.SUBTITULO).pack(pady=(15, 0))
    abas_caixa = ctk.CTkTabview(tela_diario, command=lambda: _ao_trocar_aba_caixa())
    abas_caixa.pack(fill="both", expand=True, padx=20, pady=(0, 10))
    aba_fech_dia = abas_caixa.add("Fechamento do Dia")
    aba_hist_fech = abas_caixa.add("Histórico de Fechamentos")
    aba_rel_diario = abas_caixa.add("Relatório Diário")

    area_caixa = ctk.CTkScrollableFrame(aba_fech_dia, fg_color="transparent", corner_radius=0)
    area_caixa.pack(fill="both", expand=True)

    # --- Barra superior: data, navegação entre dias, situação e exportação ---
    frame_topo_cx = ctk.CTkFrame(area_caixa, fg_color="transparent", corner_radius=0)
    frame_topo_cx.pack(fill="x", padx=10, pady=5)

    ctk.CTkLabel(frame_topo_cx, text="Data:", font=Tema.LABEL).pack(side="left", padx=(0, 5))
    entry_data_cx = ctk.CTkEntry(frame_topo_cx, width=130, font=ctk.CTkFont(size=14), justify="center",
                                 corner_radius=Tema.RAIO_BOTAO)
    entry_data_cx.insert(0, datetime.now().strftime("%d/%m/%Y"))
    entry_data_cx.pack(side="left", padx=5)

    def _ir_para_data_cx(texto_data):
        entry_data_cx.delete(0, "end")
        entry_data_cx.insert(0, texto_data)
        carregar_fechamento()

    def _mudar_dia_cx(delta):
        base = texto_para_data(entry_data_cx.get()) or datetime.now()
        _ir_para_data_cx((base + timedelta(days=delta)).strftime("%d/%m/%Y"))

    for _txt, _cmd in (("◀", lambda: _mudar_dia_cx(-1)),
                       ("Hoje", lambda: _ir_para_data_cx(datetime.now().strftime("%d/%m/%Y"))),
                       ("▶", lambda: _mudar_dia_cx(1))):
        ctk.CTkButton(frame_topo_cx, text=_txt, width=60 if _txt == "Hoje" else 36, height=30,
                      font=ctk.CTkFont(size=13, weight="bold"), fg_color=("gray75", "gray30"),
                      hover_color=("gray65", "gray40"), corner_radius=Tema.RAIO_BOTAO,
                      command=_cmd).pack(side="left", padx=2)

    lbl_status_cx = ctk.CTkLabel(frame_topo_cx, text="", font=ctk.CTkFont(size=14, weight="bold"))
    lbl_status_cx.pack(side="left", padx=15)

    frame_exportar_cx = ctk.CTkFrame(frame_topo_cx, fg_color="transparent")
    frame_exportar_cx.pack(side="right")

    # --- Corpo: movimentos da gaveta (esquerda) + conferência (direita) ---
    frame_corpo_cx = ctk.CTkFrame(area_caixa, fg_color="transparent", corner_radius=0)
    frame_corpo_cx.pack(fill="x", padx=10, pady=(10, 5))

    card_gaveta = ctk.CTkFrame(frame_corpo_cx, corner_radius=Tema.RAIO, fg_color=("gray86", "gray17"))
    card_gaveta.pack(side="left", fill="both", expand=True, padx=(0, 10))
    card_conf = ctk.CTkFrame(frame_corpo_cx, corner_radius=Tema.RAIO, fg_color=("gray86", "gray17"), width=440)
    card_conf.pack(side="left", fill="y", padx=(10, 0))
    card_conf.pack_propagate(False)

    # ---- Card da gaveta: troco inicial, suprimento, sangria ----
    ctk.CTkLabel(card_gaveta, text="💵 GAVETA", font=Tema.SUBTITULO).pack(pady=(14, 8), padx=16, anchor="w")

    f_troco = ctk.CTkFrame(card_gaveta, fg_color="transparent")
    f_troco.pack(fill="x", padx=16, pady=4)
    ctk.CTkLabel(f_troco, text="Troco inicial:", font=Tema.LABEL).pack(side="left")
    entry_troco_cx = ctk.CTkEntry(f_troco, width=130, justify="center", placeholder_text="0,00",
                                  font=ctk.CTkFont(size=15), corner_radius=Tema.RAIO_BOTAO)
    entry_troco_cx.pack(side="left", padx=10)

    ctk.CTkLabel(card_gaveta, text="Sangria ou suprimento:", font=Tema.TEXTO,
                 text_color=Tema.CINZA_TEXTO).pack(anchor="w", padx=16, pady=(12, 0))
    f_mov = ctk.CTkFrame(card_gaveta, fg_color="transparent")
    f_mov.pack(fill="x", padx=16, pady=(2, 4))
    entry_valor_mov_cx = ctk.CTkEntry(f_mov, width=130, justify="center", placeholder_text="Valor (R$)",
                                      font=ctk.CTkFont(size=15), corner_radius=Tema.RAIO_BOTAO)
    entry_valor_mov_cx.pack(side="left")
    f_mov_btn = ctk.CTkFrame(f_mov, fg_color="transparent")
    f_mov_btn.pack(side="left", fill="x", expand=True, padx=(10, 0))

    tabela_mov_cx = nova_tabela(card_gaveta, columns=("hora", "tipo", "valor"), show="headings", height=5)
    for c, t_, w in (("hora", "Hora", 90), ("tipo", "Tipo", 160), ("valor", "Valor", 160)):
        tabela_mov_cx.heading(c, text=t_)
        tabela_mov_cx.column(c, width=w, anchor="center")
    tabela_mov_cx.pack(fill="x", padx=16, pady=(8, 4))
    f_remover_mov = ctk.CTkFrame(card_gaveta, fg_color="transparent")
    f_remover_mov.pack(fill="x", padx=16, pady=(0, 14))

    # ---- Card de conferência do dinheiro ----
    ctk.CTkLabel(card_conf, text="🧾 CONFERÊNCIA DO DINHEIRO", font=Tema.SUBTITULO).pack(pady=(14, 8), padx=16, anchor="w")
    f_resumo_gaveta = ctk.CTkFrame(card_conf, fg_color="transparent")
    f_resumo_gaveta.pack(fill="x", padx=16)
    labels_resumo_gaveta = {}
    for chave, rotulo in (("troco", "Troco inicial"), ("dinheiro", "+ Vendas em dinheiro"),
                          ("suprimento", "+ Suprimentos"), ("sangria", "− Sangrias"),
                          ("esperado", "= Esperado na gaveta")):
        linha_f = ctk.CTkFrame(f_resumo_gaveta, fg_color="transparent")
        linha_f.pack(fill="x", pady=2)
        destaque = chave == "esperado"
        lbl_rot = ctk.CTkLabel(linha_f, text=rotulo, font=ctk.CTkFont(size=15, weight="bold" if destaque else "normal"))
        lbl_rot.pack(side="left")
        lbl = ctk.CTkLabel(linha_f, text="R$ 0,00", font=ctk.CTkFont(size=16 if destaque else 15, weight="bold"),
                           text_color=Tema.VERDE if destaque else Tema.TEXTO_PADRAO)
        lbl.pack(side="right")
        labels_resumo_gaveta[chave] = lbl
        if chave == "dinheiro":
            labels_resumo_gaveta["rotulo_dinheiro"] = lbl_rot

    ctk.CTkFrame(card_conf, height=2, fg_color=Tema.VERDE).pack(fill="x", padx=16, pady=10)
    f_contado = ctk.CTkFrame(card_conf, fg_color="transparent")
    f_contado.pack(fill="x", padx=16, pady=2)
    ctk.CTkLabel(f_contado, text="Contado na gaveta:", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
    entry_contado_cx = ctk.CTkEntry(f_contado, width=150, justify="right", placeholder_text="0,00",
                                    font=ctk.CTkFont(size=18, weight="bold"), corner_radius=Tema.RAIO_BOTAO)
    entry_contado_cx.pack(side="right")
    f_dif = ctk.CTkFrame(card_conf, fg_color="transparent")
    f_dif.pack(fill="x", padx=16, pady=(10, 2))
    ctk.CTkLabel(f_dif, text="Diferença:", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
    lbl_diferenca_cx = ctk.CTkLabel(f_dif, text="—", font=ctk.CTkFont(size=22, weight="bold"))
    lbl_diferenca_cx.pack(side="right")

    ctk.CTkLabel(card_conf, text="Observação:", font=Tema.TEXTO).pack(anchor="w", padx=16, pady=(14, 0))
    entry_obs_cx = ctk.CTkEntry(card_conf, placeholder_text="Ex.: faltou R$ 2,00 de troco",
                                font=ctk.CTkFont(size=13), corner_radius=Tema.RAIO_BOTAO)
    entry_obs_cx.pack(fill="x", padx=16, pady=(2, 10))
    lbl_feedback_cx = ctk.CTkLabel(card_conf, text="", font=ctk.CTkFont(size=14, weight="bold"))
    lbl_feedback_cx.pack(padx=16)
    f_salvar_cx = ctk.CTkFrame(card_conf, fg_color="transparent")
    f_salvar_cx.pack(fill="x", padx=16, pady=(4, 14), side="bottom")

    # --- Gráficos do dia (todas as vendas do dia, sem filtro) ---
    frame_graficos_container = ctk.CTkFrame(area_caixa, fg_color="transparent", corner_radius=0, height=300)
    frame_graficos_container.pack(fill="x", padx=10, pady=(10, 20))
    frame_graficos_container.pack_propagate(False)
    frame_grafico_horas = ctk.CTkFrame(frame_graficos_container, corner_radius=Tema.RAIO)
    frame_grafico_horas.pack(side="left", fill="both", expand=True, padx=(0, 10))
    frame_grafico_vendedores = ctk.CTkFrame(frame_graficos_container, corner_radius=Tema.RAIO)
    frame_grafico_vendedores.pack(side="right", fill="both", expand=True, padx=(10, 0))

    # Estado do dia carregado (usado no recálculo ao digitar e na exportação)
    estado_caixa = {"data": None, "dinheiro": 0.0, "qtd_dinheiro": 0, "suprimento": 0.0, "sangria": 0.0,
                    "fechado_em": None, "alterado": False}

    def _data_cx_valida():
        d = texto_para_data(entry_data_cx.get())
        if d is None:
            exibir_feedback(lbl_feedback_cx, "⚠️ Data inválida! Use DD/MM/AAAA", Tema.VERMELHO)
            return None
        texto = d.strftime("%d/%m/%Y")
        if entry_data_cx.get().strip() != texto:  # normaliza "1/9/2026" -> "01/09/2026"
            entry_data_cx.delete(0, "end")
            entry_data_cx.insert(0, texto)
        return texto

    def _texto_diferenca(dif):
        if abs(dif) < 0.005:
            return "OK", Tema.VERDE
        if dif < 0:
            return f"Falta {moeda_sempre(-dif)}", Tema.VERMELHO
        return f"Sobra {moeda_sempre(dif)}", Tema.AMARELO

    def _atualizar_status_cx():
        if estado_caixa["alterado"]:
            lbl_status_cx.configure(text="● Alterações não salvas", text_color=Tema.AMARELO)
        elif estado_caixa["fechado_em"]:
            lbl_status_cx.configure(text=f"✔ Fechado em {estado_caixa['fechado_em']}", text_color=Tema.VERDE)
        else:
            lbl_status_cx.configure(text="Caixa em aberto", text_color=Tema.CINZA_TEXTO)

    def _marcar_alterado(event=None):
        if estado_caixa["data"] and not estado_caixa["alterado"]:
            estado_caixa["alterado"] = True
            _atualizar_status_cx()
        recalcular_caixa()

    def _esperado_dinheiro():
        troco = ler_valor_monetario(entry_troco_cx.get()) or 0.0
        return troco, troco + estado_caixa["dinheiro"] + estado_caixa["suprimento"] - estado_caixa["sangria"]

    def recalcular_caixa():
        """Recalcula esperado/diferença a partir do que está digitado (sem ir ao banco)."""
        troco, esperado = _esperado_dinheiro()
        for chave, valor in (("troco", troco), ("dinheiro", estado_caixa["dinheiro"]),
                             ("suprimento", estado_caixa["suprimento"]), ("sangria", estado_caixa["sangria"]),
                             ("esperado", esperado)):
            labels_resumo_gaveta[chave].configure(text=moeda_sempre(valor))
        labels_resumo_gaveta["rotulo_dinheiro"].configure(
            text=f"+ Vendas em dinheiro ({estado_caixa['qtd_dinheiro']})")

        texto_contado = entry_contado_cx.get().strip()
        if texto_contado == "":
            lbl_diferenca_cx.configure(text="—", text_color=Tema.CINZA_TEXTO)
            return
        contado = ler_valor_monetario(texto_contado)
        if contado is None:
            lbl_diferenca_cx.configure(text="valor inválido", text_color=Tema.VERMELHO)
            return
        txt, cor = _texto_diferenca(contado - esperado)
        lbl_diferenca_cx.configure(text=txt, text_color=cor)

    def _carregar_movimentos_cx(data):
        for item in tabela_mov_cx.get_children():
            tabela_mov_cx.delete(item)
        movs = banco.consultar_todos(
            "SELECT id, horario, tipo, valor FROM movimentos_caixa WHERE data = ? ORDER BY id", (data,))
        estado_caixa["suprimento"] = sum(m["valor"] for m in movs if m["tipo"] == "SUPRIMENTO")
        estado_caixa["sangria"] = sum(m["valor"] for m in movs if m["tipo"] == "SANGRIA")
        for i, m in enumerate(movs):
            sinal = "+" if m["tipo"] == "SUPRIMENTO" else "−"
            tabela_mov_cx.insert("", "end", iid=str(m["id"]),
                                 values=(m["horario"] or "", m["tipo"].title(), f"{sinal} {moeda_sempre(m['valor'])}"),
                                 tags=("linha_par" if i % 2 == 0 else "linha_impar",))

    def carregar_fechamento(event=None, manter_digitado=False):
        """Carrega o dia escolhido. manter_digitado=True só atualiza os números do
        sistema (ex.: ao voltar para a tela), sem apagar o que a pessoa digitou."""
        data = _data_cx_valida()
        if data is None:
            return
        if (estado_caixa["alterado"] and estado_caixa["data"] and data != estado_caixa["data"]
                and not messagebox.askyesno("Alterações não salvas",
                                            f"O fechamento de {estado_caixa['data']} tem alterações não salvas.\n"
                                            "Descartar e abrir outro dia?")):
            entry_data_cx.delete(0, "end")
            entry_data_cx.insert(0, estado_caixa["data"])
            return
        manter_digitado = manter_digitado and data == estado_caixa["data"]
        try:
            din = banco.consultar_um(
                "SELECT COALESCE(SUM(valor), 0), COUNT(*) FROM vendas "
                "WHERE data_venda = ? AND UPPER(TRIM(tipo_pagamento)) = 'DINHEIRO'", (data,))
            fech = banco.consultar_um("SELECT troco_inicial, observacao, fechado_em FROM fechamento_caixa WHERE data = ?", (data,))
            contado = banco.consultar_um(
                "SELECT valor_contado FROM fechamento_contagem WHERE data = ? AND forma_pagamento = 'DINHEIRO'", (data,))
            _carregar_movimentos_cx(data)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Fechamento de Caixa")
            return

        estado_caixa.update({"data": data, "dinheiro": din[0] or 0.0, "qtd_dinheiro": din[1] or 0,
                             "fechado_em": fech["fechado_em"] if fech else None})
        if not manter_digitado:
            estado_caixa["alterado"] = False
            entry_troco_cx.delete(0, "end")
            if fech and fech["troco_inicial"]:
                entry_troco_cx.insert(0, f"{fech['troco_inicial']:.2f}".replace(".", ","))
            entry_obs_cx.delete(0, "end")
            if fech and fech["observacao"]:
                entry_obs_cx.insert(0, fech["observacao"])
            entry_contado_cx.delete(0, "end")
            if contado is not None:
                entry_contado_cx.insert(0, f"{contado['valor_contado']:.2f}".replace(".", ","))

        _atualizar_status_cx()
        recalcular_caixa()
        _desenhar_graficos_dia(data)

    def adicionar_movimento_cx(tipo):
        data = _data_cx_valida()
        if data is None:
            return
        valor = ler_valor_monetario(entry_valor_mov_cx.get())
        if valor is None or valor <= 0:
            exibir_feedback(lbl_feedback_cx, "⚠️ Digite um valor maior que zero!", Tema.VERMELHO)
            return
        try:
            banco.executar("INSERT INTO movimentos_caixa (data, tipo, valor, descricao, horario) VALUES (?, ?, ?, '', ?)",
                           (data, tipo, valor, datetime.now().strftime("%H:%M")), commit=True)
            _carregar_movimentos_cx(data)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Registrar " + tipo.title())
            return
        entry_valor_mov_cx.delete(0, "end")
        exibir_feedback(lbl_feedback_cx, f"✔️ {tipo.title()} de {moeda_sempre(valor)} registrada", Tema.VERDE)
        _marcar_alterado()

    def remover_movimento_cx():
        selecao = tabela_mov_cx.selection()
        if not selecao:
            messagebox.showwarning("Aviso", "Selecione uma sangria/suprimento na lista.")
            return
        valores = tabela_mov_cx.item(selecao[0], "values")
        if messagebox.askyesno("Confirmar", f"Remover {valores[1].lower()} de {valores[2]}?"):
            try:
                banco.executar("DELETE FROM movimentos_caixa WHERE id = ?", (int(selecao[0]),), commit=True)
                _carregar_movimentos_cx(estado_caixa["data"])
            except ErroBancoDados:
                alerta_erro_banco("Erro ao Remover Movimento")
                return
            _marcar_alterado()

    def salvar_fechamento(event=None):
        data = _data_cx_valida()
        if data is None or data != estado_caixa["data"]:
            carregar_fechamento()
            return
        troco_txt = entry_troco_cx.get().strip()
        troco = ler_valor_monetario(troco_txt) if troco_txt else 0.0
        if troco is None or troco < 0:
            exibir_feedback(lbl_feedback_cx, "⚠️ Troco inicial inválido!", Tema.VERMELHO)
            return
        contado_txt = entry_contado_cx.get().strip()
        contado = ler_valor_monetario(contado_txt) if contado_txt else None
        if contado_txt and (contado is None or contado < 0):
            exibir_feedback(lbl_feedback_cx, "⚠️ Valor contado inválido!", Tema.VERMELHO)
            return
        if contado is None and not messagebox.askyesno(
                "Confirmar", "O valor \"Contado na gaveta\" está vazio.\nSalvar o fechamento mesmo assim?"):
            return

        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        comandos = [
            ("INSERT INTO fechamento_caixa (data, troco_inicial, observacao, fechado_em) VALUES (?, ?, ?, ?) "
             "ON CONFLICT(data) DO UPDATE SET troco_inicial = excluded.troco_inicial, "
             "observacao = excluded.observacao, fechado_em = excluded.fechado_em",
             (data, troco, entry_obs_cx.get().strip(), agora)),
            ("DELETE FROM fechamento_contagem WHERE data = ?", (data,)),
        ]
        if contado is not None:
            comandos.append(("INSERT INTO fechamento_contagem (data, forma_pagamento, valor_contado) VALUES (?, 'DINHEIRO', ?)",
                             (data, contado)))
        try:
            banco.transacao(comandos)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Salvar Fechamento")
            return
        estado_caixa["fechado_em"] = agora
        estado_caixa["alterado"] = False
        _atualizar_status_cx()
        exibir_feedback(lbl_feedback_cx, "✔️ Fechamento salvo!", Tema.VERDE)

    # Botões (criados aqui porque dependem das funções acima)
    ctk.CTkButton(f_mov_btn, text="+ Suprimento", font=ctk.CTkFont(size=14, weight="bold"), height=34,
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: adicionar_movimento_cx("SUPRIMENTO")).pack(side="left", expand=True, fill="x", padx=(0, 4))
    ctk.CTkButton(f_mov_btn, text="− Sangria", font=ctk.CTkFont(size=14, weight="bold"), height=34,
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: adicionar_movimento_cx("SANGRIA")).pack(side="left", expand=True, fill="x", padx=(4, 0))
    ctk.CTkButton(f_remover_mov, text="Remover selecionado", font=ctk.CTkFont(size=12), height=26,
                  fg_color="transparent", border_width=1, border_color=Tema.VERMELHO, text_color=Tema.VERMELHO,
                  hover_color=("gray80", "gray25"), corner_radius=Tema.RAIO_BOTAO,
                  command=remover_movimento_cx).pack(side="right")
    ctk.CTkButton(f_salvar_cx, text="SALVAR FECHAMENTO", font=ctk.CTkFont(size=18, weight="bold"), height=48,
                  fg_color=Tema.VERDE, hover_color=Tema.VERDE_HOVER, corner_radius=Tema.RAIO_BOTAO,
                  command=salvar_fechamento).pack(fill="x")

    entry_data_cx.bind("<Return>", carregar_fechamento)
    for _entrada in (entry_troco_cx, entry_obs_cx, entry_contado_cx):
        _entrada.bind("<KeyRelease>", _marcar_alterado)
    entry_contado_cx.bind("<Return>", salvar_fechamento)

    def _desenhar_graficos_dia(data):
        """Gráficos do dia: vendas por horário e ranking da equipe (todas as vendas)."""
        for f in (frame_grafico_horas, frame_grafico_vendedores):
            for w in f.winfo_children():
                w.destroy()
        try:
            vendas_dia = banco.consultar_todos("SELECT horario, valor FROM vendas WHERE data_venda = ?", (data,))
            ranking = banco.consultar_todos(
                f"SELECT {SQL_NOME_VENDEDOR}, SUM(valor) FROM vendas WHERE data_venda = ? "
                "GROUP BY 1 ORDER BY 2 DESC", (data,))
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Gráficos do Dia")
            return

        horas = {f"{h:02d}:00": 0.0 for h in range(6, 21)}
        for h_str, val in vendas_dia:
            h_fmt = None
            for formato in ("%I:%M:%S %p", "%H:%M:%S", "%H:%M"):
                try:
                    h_fmt = datetime.strptime(h_str or "", formato).strftime("%H:00")
                    break
                except ValueError:
                    continue
            if h_fmt:  # vendas antigas sem horário ficam fora deste gráfico
                horas[h_fmt] = horas.get(h_fmt, 0.0) + (val or 0.0)

        fundo, texto = "#2b2b2b", Tema.TABELA_TEXTO

        def _estilo(fig, ax):
            fig.patch.set_facecolor(fundo)
            ax.set_facecolor(fundo)
            ax.tick_params(colors=texto, labelsize=8)
            ax.title.set_color(texto)
            for lado in ax.spines.values():
                lado.set_color("#555555")

        plt.close("all")
        fig_h, ax_h = plt.subplots(figsize=(5, 2.8), dpi=100)
        _estilo(fig_h, ax_h)
        chaves = sorted(horas)
        valores = [horas[k] for k in chaves]
        ax_h.bar(chaves, valores, color=Tema.VERDE)
        ax_h.set_title("Vendas por horário", fontsize=11)
        ax_h.ticklabel_format(style="plain", axis="y")
        ax_h.tick_params(axis="x", rotation=45)
        ax_h.set_ylim(0, max(valores) * 1.25 if max(valores, default=0) > 0 else 100)
        fig_h.tight_layout()
        canvas_h = FigureCanvasTkAgg(fig_h, master=frame_grafico_horas)
        canvas_h.draw()
        canvas_h.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)

        fig_v, ax_v = plt.subplots(figsize=(5, 2.8), dpi=100)
        _estilo(fig_v, ax_v)
        nomes = [(r[0] or "SEM NOME") for r in ranking]
        vals = [r[1] or 0.0 for r in ranking]
        if nomes:
            paleta = ["#FF8AC6", "#6FB4FF", "#6EE07A", "#B9A3F5", "#F2C94C", "#FF8A65", "#4DD9E0"]
            barras = ax_v.bar(nomes, vals, color=[paleta[i % len(paleta)] for i in range(len(nomes))])
            for b in barras:
                ax_v.annotate(formatar_moeda(b.get_height()), xy=(b.get_x() + b.get_width() / 2, b.get_height()),
                              xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8, color=texto)
            ax_v.set_ylim(0, max(vals) * 1.25 if max(vals) > 0 else 100)
            ax_v.ticklabel_format(style="plain", axis="y")
        else:
            ax_v.text(0.5, 0.5, "Sem vendas neste dia.", ha="center", va="center", color=texto)
            ax_v.axis("off")
        ax_v.set_title("Ranking da equipe no dia", fontsize=11)
        fig_v.tight_layout()
        canvas_v = FigureCanvasTkAgg(fig_v, master=frame_grafico_vendedores)
        canvas_v.draw()
        canvas_v.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)

    def _exportar_fechamento(tipo):
        if not estado_caixa["data"]:
            messagebox.showwarning("Exportar", "Não há fechamento carregado para exportar.")
            return
        colunas = ["Item", "Valor"]
        tabela_temporaria = nova_tabela(janela, columns=colunas, show="headings")
        for c in colunas:
            tabela_temporaria.heading(c, text=c)
        linhas = [("Troco inicial", labels_resumo_gaveta["troco"].cget("text")),
                  (labels_resumo_gaveta["rotulo_dinheiro"].cget("text"), labels_resumo_gaveta["dinheiro"].cget("text")),
                  ("+ Suprimentos", labels_resumo_gaveta["suprimento"].cget("text")),
                  ("− Sangrias", labels_resumo_gaveta["sangria"].cget("text")),
                  ("= Esperado na gaveta", labels_resumo_gaveta["esperado"].cget("text")),
                  ("Contado na gaveta", moeda_sempre(ler_valor_monetario(entry_contado_cx.get()))
                   if entry_contado_cx.get().strip() else "—"),
                  ("Diferença", lbl_diferenca_cx.cget("text"))]
        for item_id in tabela_mov_cx.get_children():
            hora, tp, valor = tabela_mov_cx.item(item_id, "values")
            linhas.append((f"{tp} às {hora}", valor))
        if entry_obs_cx.get().strip():
            linhas.append(("Observação", entry_obs_cx.get().strip()))
        for linha in linhas:
            tabela_temporaria.insert("", "end", values=linha)
        nome_arquivo = f"fechamento_caixa_{estado_caixa['data'].replace('/', '-')}"
        if tipo == "excel":
            exportar_tabela_excel(tabela_temporaria, nome_arquivo, "Fechamento de Caixa")
        else:
            exportar_tabela_pdf(tabela_temporaria, nome_arquivo, f"Fechamento de Caixa - {estado_caixa['data']}")
        tabela_temporaria.destroy()

    ctk.CTkButton(frame_exportar_cx, text="📊 Excel", font=ctk.CTkFont(size=13, weight="bold"), width=90,
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, height=32, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: _exportar_fechamento("excel")).pack(side="left", padx=5)
    ctk.CTkButton(frame_exportar_cx, text="📄 PDF", font=ctk.CTkFont(size=13, weight="bold"), width=90,
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, height=32, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: _exportar_fechamento("pdf")).pack(side="left", padx=5)

    # -------------------------------------------------------------------------
    # ABA: HISTÓRICO DE FECHAMENTOS
    # -------------------------------------------------------------------------
    _MESES_CX = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
                 "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    frame_filtro_hist_cx = ctk.CTkFrame(aba_hist_fech, fg_color="transparent")
    frame_filtro_hist_cx.pack(fill="x", padx=10, pady=(5, 5))
    ctk.CTkLabel(frame_filtro_hist_cx, text="Mês:", font=Tema.LABEL).pack(side="left", padx=(0, 5))
    var_mes_hist_cx = ctk.StringVar(value=_MESES_CX[datetime.now().month - 1])
    ctk.CTkOptionMenu(frame_filtro_hist_cx, values=_MESES_CX, variable=var_mes_hist_cx, width=140,
                      font=ctk.CTkFont(size=14), command=lambda _: atualizar_historico_fechamentos()).pack(side="left", padx=5)
    ctk.CTkLabel(frame_filtro_hist_cx, text="Ano:", font=Tema.LABEL).pack(side="left", padx=(15, 5))
    var_ano_hist_cx = ctk.StringVar(value=str(datetime.now().year))
    menu_ano_hist_cx = ctk.CTkOptionMenu(frame_filtro_hist_cx, values=[str(datetime.now().year)], variable=var_ano_hist_cx,
                                         width=100, font=ctk.CTkFont(size=14),
                                         command=lambda _: atualizar_historico_fechamentos())
    menu_ano_hist_cx.pack(side="left", padx=5)
    lbl_resumo_hist_cx = ctk.CTkLabel(frame_filtro_hist_cx, text="", font=Tema.LABEL)
    lbl_resumo_hist_cx.pack(side="left", padx=20)
    frame_exportar_hist_cx = ctk.CTkFrame(frame_filtro_hist_cx, fg_color="transparent")
    frame_exportar_hist_cx.pack(side="right")

    ctk.CTkLabel(aba_hist_fech, text="Dê dois cliques em um dia para abrir o fechamento dele.",
                 font=Tema.TEXTO, text_color=Tema.CINZA_TEXTO).pack(anchor="w", padx=12)
    frame_tab_hist_cx = ctk.CTkFrame(aba_hist_fech, corner_radius=0)
    frame_tab_hist_cx.pack(fill="both", expand=True, padx=10, pady=(4, 5))
    scroll_hist_cx = ttk.Scrollbar(frame_tab_hist_cx, orient="vertical")
    scroll_hist_cx.pack(side="right", fill="y")
    scroll_hist_cx_x = ttk.Scrollbar(frame_tab_hist_cx, orient="horizontal")
    scroll_hist_cx_x.pack(side="bottom", fill="x")
    colunas_hist_cx = ("data", "troco", "dinheiro", "suprimento", "sangria", "esperado", "contado", "diferenca",
                       "fechado", "obs")
    tabela_hist_cx = nova_tabela(frame_tab_hist_cx, columns=colunas_hist_cx, show="headings",
                                 yscrollcommand=scroll_hist_cx.set, xscrollcommand=scroll_hist_cx_x.set)
    scroll_hist_cx.configure(command=tabela_hist_cx.yview)
    scroll_hist_cx_x.configure(command=tabela_hist_cx.xview)
    for c, t_, w in (("data", "Data", 115), ("troco", "Troco", 115), ("dinheiro", "Vendas dinheiro", 150),
                     ("suprimento", "Suprimentos", 130), ("sangria", "Sangrias", 130), ("esperado", "Esperado", 135),
                     ("contado", "Contado", 135), ("diferenca", "Diferença", 160), ("fechado", "Fechado em", 170),
                     ("obs", "Observação", 260)):
        tabela_hist_cx.heading(c, text=t_)
        tabela_hist_cx.column(c, width=w, minwidth=w, stretch=(c == "obs"), anchor="w" if c == "obs" else "center")
    tabela_hist_cx.tag_configure("falta", foreground="#FF8A80")
    tabela_hist_cx.tag_configure("sobra", foreground="#F2C94C")
    tabela_hist_cx.pack(side="left", fill="both", expand=True)

    def atualizar_historico_fechamentos(*args):
        mes = f"{_MESES_CX.index(var_mes_hist_cx.get()) + 1:02d}"
        ano = var_ano_hist_cx.get()
        filtro = "substr({c}, 4, 2) = ? AND substr({c}, 7, 4) = ?"
        try:
            fechamentos = banco.consultar_todos(
                "SELECT data, troco_inicial, observacao, fechado_em FROM fechamento_caixa WHERE "
                + filtro.format(c="data") + " ORDER BY substr(data, 1, 2)", (mes, ano))
            contados = {r[0]: r[1] for r in banco.consultar_todos(
                "SELECT data, valor_contado FROM fechamento_contagem WHERE forma_pagamento = 'DINHEIRO' AND "
                + filtro.format(c="data"), (mes, ano))}
            dinheiro = {r[0]: r[1] for r in banco.consultar_todos(
                "SELECT data_venda, SUM(valor) FROM vendas WHERE UPPER(TRIM(tipo_pagamento)) = 'DINHEIRO' AND "
                + filtro.format(c="data_venda") + " GROUP BY data_venda", (mes, ano))}
            movs = {}
            for r in banco.consultar_todos(
                    "SELECT data, tipo, SUM(valor) FROM movimentos_caixa WHERE " + filtro.format(c="data")
                    + " GROUP BY data, tipo", (mes, ano)):
                movs[(r[0], r[1])] = r[2]
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Histórico de Fechamentos")
            return

        for item in tabela_hist_cx.get_children():
            tabela_hist_cx.delete(item)
        soma_dif, dias_com_dif = 0.0, 0
        for i, f in enumerate(fechamentos):
            d = f["data"]
            troco = f["troco_inicial"] or 0.0
            din = dinheiro.get(d, 0.0) or 0.0
            sup = movs.get((d, "SUPRIMENTO"), 0.0)
            san = movs.get((d, "SANGRIA"), 0.0)
            esperado = troco + din + sup - san
            contado = contados.get(d)
            tags = ["linha_par" if i % 2 == 0 else "linha_impar"]
            if contado is None:
                txt_dif = "não contado"
            else:
                dif = contado - esperado
                txt_dif, _ = _texto_diferenca(dif)
                soma_dif += dif
                if abs(dif) >= 0.005:
                    dias_com_dif += 1
                    tags.append("falta" if dif < 0 else "sobra")
            tabela_hist_cx.insert("", "end", iid=d, values=(
                d, moeda_sempre(troco), moeda_sempre(din), moeda_sempre(sup), moeda_sempre(san), moeda_sempre(esperado),
                moeda_sempre(contado) if contado is not None else "—", txt_dif, f["fechado_em"] or "",
                f["observacao"] or ""), tags=tuple(tags))
        if fechamentos:
            txt_total, _ = _texto_diferenca(soma_dif)
            tabela_hist_cx.insert("", "end", iid="__total__", values=(
                "TOTAL", "", "", "", "", "", "", txt_total, "", ""), tags=("tag_TOTAL",))
        lbl_resumo_hist_cx.configure(
            text=f"{len(fechamentos)} dia(s) fechado(s) · {dias_com_dif} com diferença" if fechamentos
            else "Nenhum fechamento salvo neste mês.")

    def _abrir_fechamento_do_historico(event=None):
        selecao = tabela_hist_cx.selection()
        if not selecao or selecao[0] == "__total__":
            return
        abas_caixa.set("Fechamento do Dia")
        _ir_para_data_cx(selecao[0])

    tabela_hist_cx.bind("<Double-1>", _abrir_fechamento_do_historico)

    def _ao_trocar_aba_caixa():
        if abas_caixa.get() == "Relatório Diário":
            atualizar_diario()
        if abas_caixa.get() == "Histórico de Fechamentos":
            anos = _anos_distintos([("SELECT DISTINCT data FROM fechamento_caixa", ())])
            atual = str(datetime.now().year)
            if atual not in anos:
                anos = sorted(anos + [atual], reverse=True)
            menu_ano_hist_cx.configure(values=anos)
            if var_ano_hist_cx.get() not in anos:
                var_ano_hist_cx.set(anos[0])
            atualizar_historico_fechamentos()

    def _exportar_hist_cx(tipo):
        periodo = f"{var_mes_hist_cx.get()}_{var_ano_hist_cx.get()}"
        if tipo == "excel":
            exportar_tabela_excel(tabela_hist_cx, f"historico_fechamentos_{periodo}", "Histórico de Fechamentos")
        else:
            exportar_tabela_pdf(tabela_hist_cx, f"historico_fechamentos_{periodo}",
                                f"Histórico de Fechamentos - {var_mes_hist_cx.get()}/{var_ano_hist_cx.get()}")

    ctk.CTkButton(frame_exportar_hist_cx, text="📊 Excel", font=ctk.CTkFont(size=13, weight="bold"), width=90,
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, height=32, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: _exportar_hist_cx("excel")).pack(side="left", padx=5)
    ctk.CTkButton(frame_exportar_hist_cx, text="📄 PDF", font=ctk.CTkFont(size=13, weight="bold"), width=90,
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, height=32, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: _exportar_hist_cx("pdf")).pack(side="left", padx=5)


    # =============================================================================
    # ABA "RELATÓRIO DIÁRIO" (dentro do Fechamento de Caixa)
    # =============================================================================
    # É o antigo Relatório Diário, de volta: faturamento (pela data da venda) e
    # recebimento (pela data de vencimento) do dia, com TODAS as formas de
    # pagamento, mais os filtros de produto/pagamento e o "cruzamento" entre eles.
    # Os cálculos são exatamente os mesmos da versão anterior.
    area_diario = ctk.CTkScrollableFrame(aba_rel_diario, fg_color="transparent", corner_radius=0)
    area_diario.pack(fill="both", expand=True)
    frame_filtros_r = ctk.CTkFrame(area_diario, fg_color="transparent", corner_radius=0)
    frame_filtros_r.pack(pady=5, padx=20, fill="x")

    var_prod_r, var_pag_r = ctk.StringVar(value=opcoes_produtos[0]), ctk.StringVar(value=opcoes_pagamento[0])

    ctk.CTkLabel(frame_filtros_r, text="Data:", font=Tema.LABEL).pack(side="left", padx=(0, 5))
    entry_data_r = ctk.CTkEntry(frame_filtros_r, width=120, font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
    entry_data_r.insert(0, datetime.now().strftime("%d/%m/%Y"))
    entry_data_r.pack(side="left", padx=5)
    entry_data_r.bind("<Return>", lambda e: atualizar_diario())
    entry_data_r.bind("<FocusOut>", lambda e: atualizar_diario())

    ctk.CTkLabel(frame_filtros_r, text="Produto:", font=Tema.LABEL).pack(side="left", padx=(15, 5))
    ctk.CTkOptionMenu(frame_filtros_r, values=opcoes_produtos, variable=var_prod_r, width=150, font=ctk.CTkFont(size=14),
                       command=lambda _: atualizar_diario()).pack(side="left", padx=5)

    ctk.CTkLabel(frame_filtros_r, text="Pagamento:", font=Tema.LABEL).pack(side="left", padx=(15, 5))
    ctk.CTkOptionMenu(frame_filtros_r, values=opcoes_pagamento, variable=var_pag_r, width=150, font=ctk.CTkFont(size=14),
                       command=lambda _: atualizar_diario()).pack(side="left", padx=5)

    frame_exportar_diario = ctk.CTkFrame(frame_filtros_r, fg_color="transparent")
    frame_exportar_diario.pack(side="right")

    frame_tab_r = ctk.CTkFrame(area_diario, fg_color="transparent", corner_radius=0)
    frame_tab_r.pack(fill="x", padx=20, pady=(15, 10))
    f_esq = ctk.CTkFrame(frame_tab_r, fg_color="transparent", corner_radius=0)
    f_esq.pack(side="left", fill="x", expand=True, padx=(0, 10))
    f_dir = ctk.CTkFrame(frame_tab_r, fg_color="transparent", corner_radius=0)
    f_dir.pack(side="right", fill="x", expand=True, padx=(10, 0))

    frame_graficos_container_r = ctk.CTkFrame(area_diario, fg_color="transparent", corner_radius=0, height=380)
    frame_graficos_container_r.pack(fill="x", padx=20, pady=(0, 20))
    frame_graficos_container_r.pack_propagate(False)

    frame_grafico_horas_r = ctk.CTkFrame(frame_graficos_container_r, corner_radius=Tema.RAIO)
    frame_grafico_horas_r.pack(side="left", fill="both", expand=True, padx=(0, 10))

    frame_grafico_vendedores_r = ctk.CTkFrame(frame_graficos_container_r, corner_radius=Tema.RAIO)
    frame_grafico_vendedores_r.pack(side="right", fill="both", expand=True, padx=(10, 0))

    # Guarda o último resultado calculado, para a exportação Excel/PDF poder reutilizá-lo
    estado_diario = {}


    def construir_cartao_resumo(pai, titulo, cor_destaque, data, tp, pag, vt, vtp, vpag, vambos):
        """Substitui a antiga grade 'estilo Excel' por um cartão moderno, mais fácil de ler."""
        for w in pai.winfo_children():
            w.destroy()

        cartao = ctk.CTkFrame(pai, corner_radius=Tema.RAIO, fg_color=("#f7f7f7", "#1c1c1c"),
                               border_width=2, border_color=cor_destaque)
        cartao.pack(fill="both", expand=True)

        ctk.CTkLabel(cartao, text=titulo, font=Tema.SUBTITULO, text_color=cor_destaque).pack(pady=(16, 2))
        ctk.CTkLabel(cartao, text=data, font=Tema.TEXTO).pack(pady=(0, 10))

        def linha(rotulo, valor, destaque=False):
            f = ctk.CTkFrame(cartao, fg_color="transparent")
            f.pack(fill="x", padx=22, pady=5)
            ctk.CTkLabel(f, text=rotulo, font=("Segoe UI", 15, "bold") if destaque else Tema.LABEL, anchor="w").pack(side="left")
            ctk.CTkLabel(f, text=valor, font=("Segoe UI", 17, "bold") if destaque else ("Segoe UI", 14, "bold"),
                         text_color=cor_destaque if destaque else None, anchor="e").pack(side="right")

        linha("TOTAL GERAL DO DIA:", formatar_moeda(vt), destaque=True)
        ctk.CTkFrame(cartao, height=2, fg_color=cor_destaque).pack(fill="x", padx=22, pady=8)
        linha(f"{tp}:", formatar_moeda(vtp))
        linha(f"{pag}:", formatar_moeda(vpag))
        linha(f"{tp} + {pag}:", formatar_moeda(vambos))
        ctk.CTkLabel(cartao, text="").pack(pady=6)  # respiro inferior


    def atualizar_diario():
        plt.close("all")
        d, t, p = entry_data_r.get().strip(), var_prod_r.get(), var_pag_r.get()

        def b_val(col_d):
            try:
                vt = (banco.consultar_um(f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ?", (d,))[0]) or 0.0

                vtp = (banco.consultar_um(
                    f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ? AND UPPER(tipo_produto) = ?", (d, t))[0]) or 0.0

                if "CRÉDITO" in p:
                    vpag = (banco.consultar_um(
                        f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ? AND UPPER(tipo_pagamento) LIKE ?", (d, p + "%"))[0]) or 0.0
                    vambos = (banco.consultar_um(
                        f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ? AND UPPER(tipo_produto) = ? AND UPPER(tipo_pagamento) LIKE ?",
                        (d, t, p + "%"))[0]) or 0.0
                else:
                    vpag = (banco.consultar_um(
                        f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ? AND UPPER(tipo_pagamento) = ?", (d, p))[0]) or 0.0
                    vambos = (banco.consultar_um(
                        f"SELECT SUM(valor) FROM vendas WHERE {col_d} = ? AND UPPER(tipo_produto) = ? AND UPPER(tipo_pagamento) = ?",
                        (d, t, p))[0]) or 0.0

                return vt, vtp, vpag, vambos
            except ErroBancoDados:
                alerta_erro_banco("Erro ao Carregar Relatório Diário")
                return 0.0, 0.0, 0.0, 0.0

        valores_venda = b_val("data_venda")
        valores_recebido = b_val("data_vencimento")

        construir_cartao_resumo(f_esq, "VENDA DIÁRIA (Faturado)", Tema.VERDE, d, t, p, *valores_venda)
        construir_cartao_resumo(f_dir, "RECEBIMENTO DIÁRIO (Caixa)", Tema.AZUL, d, t, p, *valores_recebido)

        estado_diario.clear()
        estado_diario.update({"data": d, "produto": t, "pagamento": p,
                               "venda": valores_venda, "recebido": valores_recebido})

        for w in frame_grafico_horas_r.winfo_children():
            w.destroy()
        for w in frame_grafico_vendedores_r.winfo_children():
            w.destroy()

        if "CRÉDITO" in p:
            query_horas = "SELECT horario, valor FROM vendas WHERE data_venda = ? AND UPPER(tipo_produto) = ? AND UPPER(tipo_pagamento) LIKE ?"
            query_vend = (f"SELECT {SQL_NOME_VENDEDOR}, SUM(valor) FROM vendas WHERE data_venda = ? "
                          "AND UPPER(tipo_produto) = ? AND UPPER(tipo_pagamento) LIKE ? GROUP BY 1 ORDER BY 2 DESC")
            params_graf = (d, t, p + "%")
        else:
            query_horas = "SELECT horario, valor FROM vendas WHERE data_venda = ? AND UPPER(tipo_produto) = ? AND UPPER(tipo_pagamento) = ?"
            query_vend = (f"SELECT {SQL_NOME_VENDEDOR}, SUM(valor) FROM vendas WHERE data_venda = ? "
                          "AND UPPER(tipo_produto) = ? AND UPPER(tipo_pagamento) = ? GROUP BY 1 ORDER BY 2 DESC")
            params_graf = (d, t, p)

        try:
            vendas_dia = banco.consultar_todos(query_horas, params_graf)
            vendas_vendedores = banco.consultar_todos(query_vend, params_graf)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Gráficos do Dia")
            return

        horas_dict = {f"{h:02d}:00": 0.0 for h in range(6, 21)}
        for h_str, val in vendas_dia:
            try:
                h_fmt = datetime.strptime(h_str, "%I:%M:%S %p").strftime("%H:00")
            except (ValueError, TypeError):
                try:
                    h_fmt = datetime.strptime(h_str, "%H:%M").strftime("%H:00")
                except (ValueError, TypeError):
                    h_fmt = "Outros"
            horas_dict[h_fmt] = horas_dict.get(h_fmt, 0) + val

        horas_ordenadas = sorted(horas_dict.keys())
        valores_horas = [horas_dict[h] for h in horas_ordenadas]

        def _estilo_escuro(fig, ax):
            fig.patch.set_facecolor("#2b2b2b")
            ax.set_facecolor("#2b2b2b")
            ax.tick_params(colors=Tema.TABELA_TEXTO)
            ax.title.set_color(Tema.TABELA_TEXTO)
            ax.yaxis.label.set_color(Tema.TABELA_TEXTO)
            for lado in ax.spines.values():
                lado.set_color("#555555")

        fig_h, ax_h = plt.subplots(figsize=(5, 3), dpi=100)
        _estilo_escuro(fig_h, ax_h)
        barras_h = ax_h.bar(horas_ordenadas, valores_horas, color=Tema.VERDE)
        ax_h.set_title(f"Vendas por Horário ({t} / {p})", fontsize=11)
        ax_h.set_ylabel("Faturamento (R$)")
        ax_h.ticklabel_format(style="plain", axis="y")
        plt.xticks(rotation=45, ha="right", fontsize=7)

        for bar in barras_h:
            altura = bar.get_height()
            if altura > 0:
                ax_h.annotate(formatar_moeda(altura), xy=(bar.get_x() + bar.get_width() / 2, altura),
                              xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=8, rotation=90, color=Tema.TABELA_TEXTO)

        teto_grafico = max(valores_horas) if valores_horas else 0
        ax_h.set_ylim(0, teto_grafico * 1.45 if teto_grafico > 0 else 100)

        fig_h.tight_layout()
        canvas_h = FigureCanvasTkAgg(fig_h, master=frame_grafico_horas_r)
        canvas_h.draw()
        canvas_h.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)

        nomes_vd = [(row[0] or "SEM NOME").strip() for row in vendas_vendedores]
        valores_vd = [row[1] for row in vendas_vendedores]
        paleta = ["#FF8AC6", "#6FB4FF", "#6EE07A", "#B9A3F5", "#F2C94C", "#FF8A65", "#4DD9E0"]

        fig_v, ax_v = plt.subplots(figsize=(5, 3), dpi=100)
        _estilo_escuro(fig_v, ax_v)
        if nomes_vd:
            cores_barras = [paleta[i % len(paleta)] for i in range(len(nomes_vd))]
            barras_v = ax_v.bar(nomes_vd, valores_vd, color=cores_barras)
            ax_v.set_title(f"Ranking da Equipe ({t} / {p})", fontsize=11)
            ax_v.ticklabel_format(style="plain", axis="y")
            plt.xticks(rotation=15, ha="right", fontsize=8)

            for bar in barras_v:
                altura = bar.get_height()
                if altura > 0:
                    ax_v.annotate(formatar_moeda(altura), xy=(bar.get_x() + bar.get_width() / 2, altura),
                                  xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8, color=Tema.TABELA_TEXTO)

            ax_v.set_ylim(0, max(valores_vd) * 1.25)
        else:
            ax_v.text(0.5, 0.5, "Sem vendas para os filtros selecionados.", ha="center", va="center", color=Tema.TABELA_TEXTO)
            ax_v.axis("off")

        fig_v.tight_layout()
        canvas_v = FigureCanvasTkAgg(fig_v, master=frame_grafico_vendedores_r)
        canvas_v.draw()
        canvas_v.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)


    def _exportar_diario(tipo):
        if not estado_diario:
            messagebox.showwarning("Exportar", "Não há dados calculados para exportar.")
            return
        e = estado_diario
        colunas = ["Relatório", "Data", "Produto", "Pagamento", "Total Geral", "Total Produto", "Total Pagamento", "Total Cruzado"]
        linhas = [
            ("Venda Diária (Faturado)", e["data"], e["produto"], e["pagamento"], *[formatar_moeda(v) for v in e["venda"]]),
            ("Recebimento Diário (Caixa)", e["data"], e["produto"], e["pagamento"], *[formatar_moeda(v) for v in e["recebido"]]),
        ]
        # Reaproveita as funções de exportação criando uma tabela "de mentira" na memória
        tabela_temporaria = nova_tabela(janela, columns=colunas, show="headings")
        for c in colunas:
            tabela_temporaria.heading(c, text=c)
        for linha in linhas:
            tabela_temporaria.insert("", "end", values=linha)
        nome_arquivo = f"relatorio_diario_{e['data'].replace('/', '-')}"
        if tipo == "excel":
            exportar_tabela_excel(tabela_temporaria, nome_arquivo, "Relatório Diário")
        else:
            exportar_tabela_pdf(tabela_temporaria, nome_arquivo, "Relatório Diário")
        tabela_temporaria.destroy()


    ctk.CTkButton(frame_exportar_diario, text="📊 Excel", font=ctk.CTkFont(size=13, weight="bold"), width=90,
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, height=32, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: _exportar_diario("excel")).pack(side="left", padx=5)
    ctk.CTkButton(frame_exportar_diario, text="📄 PDF", font=ctk.CTkFont(size=13, weight="bold"), width=90,
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, height=32, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: _exportar_diario("pdf")).pack(side="left", padx=5)



    # =============================================================================
    # TELA 5: GESTÃO DE EQUIPE
    # =============================================================================
    _criar_botao_voltar_gestao(tela_equipe)
    ctk.CTkLabel(tela_equipe, text="CONFIGURAÇÕES DA EQUIPE", font=Tema.SUBTITULO).pack(pady=(20, 10))
    frame_add_eq = ctk.CTkFrame(tela_equipe, fg_color="transparent", corner_radius=0)
    frame_add_eq.pack(pady=10, padx=20, fill="x")

    ctk.CTkLabel(frame_add_eq, text="Nome do Novo Vendedor:", font=Tema.LABEL).pack(side="left", padx=(0, 5))
    entry_novo_vendedor = ctk.CTkEntry(frame_add_eq, width=220, font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
    entry_novo_vendedor.pack(side="left", padx=5)


    def adicionar_vendedor(event=None):
        novo_nome = entry_novo_vendedor.get().strip().upper()
        if not novo_nome:
            messagebox.showwarning("Aviso", "Digite um nome!")
            return
        # Antes, o programa tentava inserir e "torcia" para dar erro de nome
        # duplicado para então reativar -- funcionava, mas registrava um erro
        # no log toda vez que alguém reativava um vendedor (mesmo sem problema
        # nenhum). Agora verificamos antes, de forma direta.
        try:
            existente = banco.consultar_um("SELECT status FROM vendedores WHERE nome = ?", (novo_nome,))
            if existente is None:
                banco.executar("INSERT INTO vendedores (nome, status) VALUES (?, 'Ativo')", (novo_nome,), commit=True)
                messagebox.showinfo("Sucesso", f"Vendedor {novo_nome} cadastrado!")
            elif existente["status"] == "Ativo":
                messagebox.showinfo("Aviso", f"{novo_nome} já está cadastrado(a) e ativo(a).")
            else:
                banco.executar("UPDATE vendedores SET status = 'Ativo' WHERE nome = ?", (novo_nome,), commit=True)
                messagebox.showinfo("Sucesso", f"Vendedor {novo_nome} reativado!")
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Cadastrar Vendedor")
            return
        entry_novo_vendedor.delete(0, "end")
        atualizar_lista_equipe()


    entry_novo_vendedor.bind("<Return>", adicionar_vendedor)
    ctk.CTkButton(frame_add_eq, text="➕ Adicionar", font=ctk.CTkFont(size=16, weight="bold"), height=35,
                  fg_color=Tema.VERDE, hover_color=Tema.VERDE_HOVER, command=adicionar_vendedor,
                  corner_radius=Tema.RAIO_BOTAO).pack(side="left", padx=15)

    frame_tab_eq = ctk.CTkFrame(tela_equipe, corner_radius=0)
    frame_tab_eq.pack(pady=10, padx=20, fill="both", expand=True)
    scroll_eq = ttk.Scrollbar(frame_tab_eq, orient="vertical")
    scroll_eq.pack(side="right", fill="y")
    tabela_eq = nova_tabela(frame_tab_eq, columns=("ID", "Nome", "Status"), show="headings", yscrollcommand=scroll_eq.set)
    scroll_eq.configure(command=tabela_eq.yview)

    tabela_eq.heading("ID", text="ID")
    tabela_eq.column("ID", width=60, anchor="center")
    tabela_eq.heading("Nome", text="Nome do Vendedor")
    tabela_eq.column("Nome", width=350, anchor="w")
    tabela_eq.heading("Status", text="Status")
    tabela_eq.column("Status", width=120, anchor="center")
    tabela_eq.pack(side="left", fill="both", expand=True)


    def atualizar_lista_equipe():
        for item in tabela_eq.get_children():
            tabela_eq.delete(item)
        try:
            resultados = banco.consultar_todos("SELECT id, nome, status FROM vendedores ORDER BY status ASC, nome ASC")
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Equipe")
            return
        inserir_linhas_zebra(tabela_eq, resultados)


    def desativar_vendedor():
        selecao = tabela_eq.selection()
        if not selecao:
            messagebox.showwarning("Aviso", "Selecione um vendedor.")
            return
        id_vend, nome_vend, status_vend = tabela_eq.item(selecao[0], "values")
        if status_vend == "Inativo":
            messagebox.showinfo("Aviso", "Este vendedor já está inativo!")
            return
        if messagebox.askyesno("Confirmar", f"Tem certeza que deseja DESATIVAR '{nome_vend}'?"):
            try:
                banco.executar("UPDATE vendedores SET status = 'Inativo' WHERE id = ?", (id_vend,), commit=True)
            except ErroBancoDados:
                alerta_erro_banco("Erro ao Desativar Vendedor")
                return
            messagebox.showinfo("Sucesso", "Vendedor desativado!")
            atualizar_lista_equipe()


    ctk.CTkButton(tela_equipe, text="Desligar / Desativar Selecionado", font=ctk.CTkFont(size=16, weight="bold"),
                  height=40, fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, command=desativar_vendedor,
                  corner_radius=Tema.RAIO_BOTAO).pack(pady=10)


    # =============================================================================
    # TELA 6: GESTÃO DE DESPESAS
    # =============================================================================
    ctk.CTkLabel(tela_despesas, text="GESTÃO DE DESPESAS", font=Tema.SUBTITULO).pack(pady=(20, 10))

    abas_despesas = ctk.CTkTabview(tela_despesas)
    abas_despesas.pack(fill="both", expand=True, padx=20, pady=5)

    aba_reg_desp = abas_despesas.add("Registrar Despesa")
    aba_hist_desp = abas_despesas.add("Histórico de Despesas")
    aba_graf_desp = abas_despesas.add("Gráficos")

    # --- 6.1. ABA REGISTRAR DESPESA ---
    frame_form_desp = ctk.CTkFrame(aba_reg_desp, fg_color="transparent", corner_radius=0)
    frame_form_desp.pack(pady=30)

    f_label_desp = ctk.CTkFont(size=18, weight="bold")

    ctk.CTkLabel(frame_form_desp, text="Descrição Detalhada:", font=f_label_desp).pack(pady=(10, 0))
    entry_desc_desp = ctk.CTkEntry(frame_form_desp, width=380, height=40, font=ctk.CTkFont(size=16), corner_radius=Tema.RAIO_BOTAO)
    entry_desc_desp.pack(pady=5)

    ctk.CTkLabel(frame_form_desp, text="Valor Total (R$):", font=f_label_desp).pack(pady=(15, 0))
    entry_valor_desp = ctk.CTkEntry(frame_form_desp, placeholder_text="0,00", width=220, height=40,
                                     font=ctk.CTkFont(size=18, weight="bold"), justify="center", corner_radius=Tema.RAIO_BOTAO)
    entry_valor_desp.pack(pady=5)

    ctk.CTkLabel(frame_form_desp, text="Qtd. Parcelas (1 para à vista):", font=f_label_desp).pack(pady=(15, 0))
    entry_parcelas_desp = ctk.CTkEntry(frame_form_desp, width=220, height=40, font=ctk.CTkFont(size=16), justify="center", corner_radius=Tema.RAIO_BOTAO)
    entry_parcelas_desp.insert(0, "1")
    entry_parcelas_desp.pack(pady=5)

    ctk.CTkLabel(frame_form_desp, text="Data Inicial (DD/MM/AAAA):", font=f_label_desp).pack(pady=(15, 0))
    entry_data_desp = ctk.CTkEntry(frame_form_desp, width=220, height=40, font=ctk.CTkFont(size=16), justify="center", corner_radius=Tema.RAIO_BOTAO)
    entry_data_desp.insert(0, datetime.now().strftime("%d/%m/%Y"))
    entry_data_desp.pack(pady=5)

    ctk.CTkLabel(frame_form_desp, text="Tipo de Despesa:", font=f_label_desp).pack(pady=(15, 0))
    menu_tipo_despesa = ctk.CTkOptionMenu(frame_form_desp, values=opcoes_despesas, variable=var_tipo_despesa,
                                           width=380, height=40, font=ctk.CTkFont(size=16, weight="bold"))
    menu_tipo_despesa.pack(pady=5)

    lbl_feedback_desp = ctk.CTkLabel(frame_form_desp, text="", font=ctk.CTkFont(size=16, weight="bold"))
    lbl_feedback_desp.pack(pady=5)


    def _confirmar_comissao_manual(tipo, datas):
        """Avisa que despesas COMISSÕES a partir do início automático não entram no DRE.
        Devolve True se pode salvar."""
        if tipo != TIPO_DESPESA_COMISSAO:
            return True
        if not any(_comissao_automatica_no_mes(d.strftime("%Y"), d.strftime("%m")) for d in datas):
            return True
        return messagebox.askyesno(
            "Atenção: comissão manual",
            f"Desde {inicio_comissao_automatica} a comissão é calculada AUTOMATICAMENTE no DRE, e "
            "bonificações são lançadas em Gestão → Bonificações.\n\n"
            f"Esta despesa do tipo {TIPO_DESPESA_COMISSAO} fica salva em Despesas, mas NÃO entra no DRE.\n\n"
            "Salvar mesmo assim?")

    def salvar_despesa(event=None):
        desc = entry_desc_desp.get().strip()
        val_texto = entry_valor_desp.get().strip()
        data = entry_data_desp.get().strip()
        tipo = var_tipo_despesa.get()

        if not desc or not val_texto or not data:
            exibir_feedback(lbl_feedback_desp, "⚠️ Preencha todos os campos!", Tema.VERMELHO)
            return

        val_total = texto_para_valor(val_texto)
        if val_total is None:
            exibir_feedback(lbl_feedback_desp, "⚠️ Digite um valor numérico válido!", Tema.VERMELHO)
            return
        if val_total == 0:
            exibir_feedback(lbl_feedback_desp, "⚠️ O valor não pode ser zero!", Tema.VERMELHO)
            return

        try:
            parcelas_texto = entry_parcelas_desp.get().strip()
            parcelas = int(parcelas_texto) if parcelas_texto else 1
            if parcelas < 1 or parcelas > 24:
                raise ValueError()
        except ValueError:
            exibir_feedback(lbl_feedback_desp, "⚠️ Parcelas devem ser entre 1 e 24!", Tema.VERMELHO)
            return

        data_inicial = texto_para_data(data)
        if data_inicial is None:
            exibir_feedback(lbl_feedback_desp, "⚠️ Data inválida! Use DD/MM/AAAA", Tema.VERMELHO)
            return

        valores_parcelas = dividir_em_parcelas(val_total, parcelas)
        # Se for à vista (1), lança agora. Se for parcelado (>1), empurra 1 mês pra frente.
        deslocamento_mes = 1 if parcelas > 1 else 0

        linhas = []
        for i in range(parcelas):
            m = data_inicial.month + i + deslocamento_mes
            y = data_inicial.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            dia = min(data_inicial.day, calendar.monthrange(y, m)[1])
            data_vencimento = datetime(y, m, dia).strftime("%d/%m/%Y")

            desc_final = desc.upper()
            if parcelas > 1:
                desc_final += f" ({i + 1}/{parcelas})"

            linhas.append((desc_final, valores_parcelas[i], tipo, data_vencimento))

        if not _confirmar_comissao_manual(tipo, [texto_para_data(l[3]) for l in linhas]):
            return

        try:
            banco.executar_muitos("INSERT INTO despesas (descricao, valor, tipo, data_despesa) VALUES (?, ?, ?, ?)", linhas)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Salvar Despesa")
            return

        exibir_feedback(lbl_feedback_desp, "✔️ Despesa salva com sucesso!", Tema.VERDE)
        entry_desc_desp.delete(0, "end")
        entry_valor_desp.delete(0, "end")
        entry_parcelas_desp.delete(0, "end")
        entry_parcelas_desp.insert(0, "1")
        entry_desc_desp.focus()
        atualizar_historico_despesas()


    entry_desc_desp.bind("<Return>", salvar_despesa)
    entry_valor_desp.bind("<Return>", salvar_despesa)
    entry_parcelas_desp.bind("<Return>", salvar_despesa)
    entry_data_desp.bind("<Return>", salvar_despesa)

    ctk.CTkButton(frame_form_desp, text="SALVAR DESPESA", font=ctk.CTkFont(size=20, weight="bold"), height=55, width=380,
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, command=salvar_despesa,
                  corner_radius=Tema.RAIO_BOTAO).pack(pady=(20, 10))


    # --- 6.2. ABA HISTÓRICO ---
    frame_filtros_hist_desp = ctk.CTkFrame(aba_hist_desp, fg_color="transparent", corner_radius=0)
    frame_filtros_hist_desp.pack(pady=5, padx=20, fill="x")

    ctk.CTkLabel(frame_filtros_hist_desp, text="Data Específica:", font=Tema.LABEL).pack(side="left", padx=(0, 5))
    entry_data_filtro_desp = ctk.CTkEntry(frame_filtros_hist_desp, placeholder_text="DD/MM/AAAA", font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
    entry_data_filtro_desp.pack(side="left", padx=5)

    frame_tab_desp = ctk.CTkFrame(aba_hist_desp, corner_radius=0)
    frame_tab_desp.pack(pady=10, padx=20, fill="both", expand=True)

    scroll_desp = ttk.Scrollbar(frame_tab_desp, orient="vertical")
    scroll_desp.pack(side="right", fill="y")
    tabela_despesas = nova_tabela(frame_tab_desp, columns=("ID", "Descrição", "Valor", "Tipo", "Data"), show="headings", yscrollcommand=scroll_desp.set)
    scroll_desp.configure(command=tabela_despesas.yview)

    for c, t_, w in zip(("ID", "Descrição", "Valor", "Tipo", "Data"), ("ID", "Descrição", "Valor (R$)", "Tipo", "Data"), (60, 300, 120, 220, 120)):
        tabela_despesas.heading(c, text=t_)
        tabela_despesas.column(c, width=w, anchor="center" if c != "Descrição" else "w")
    tabela_despesas.pack(side="left", fill="both", expand=True)


    def atualizar_historico_despesas(event=None):
        for item in tabela_despesas.get_children():
            tabela_despesas.delete(item)
        data_filtro = entry_data_filtro_desp.get().strip()

        query = "SELECT id, descricao, valor, tipo, data_despesa FROM despesas WHERE 1=1"
        params = []
        if data_filtro != "":
            query += " AND data_despesa = ?"
            params.append(data_filtro)
        query += " ORDER BY id DESC"

        try:
            resultados = banco.consultar_todos(query, params)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Despesas")
            return

        inserir_linhas_zebra(tabela_despesas, resultados, formatador=lambda l: (l[0], l[1], f"{l[2]:.2f}", l[3], l[4]))


    entry_data_filtro_desp.bind("<Return>", atualizar_historico_despesas)
    entry_data_filtro_desp.bind("<FocusOut>", atualizar_historico_despesas)


    def deletar_despesa():
        selecao = tabela_despesas.selection()
        if not selecao:
            return
        id_desp = tabela_despesas.item(selecao[0], "values")[0]
        if messagebox.askyesno("Confirmar", "Deseja apagar esta despesa?"):
            try:
                banco.executar("DELETE FROM despesas WHERE id = ?", (id_desp,), commit=True)
            except ErroBancoDados:
                alerta_erro_banco("Erro ao Apagar Despesa")
                return
            atualizar_historico_despesas()
            processar_grafico_despesas("")
            processar_dre("")


    def editar_despesa():
        selecao = tabela_despesas.selection()
        if not selecao:
            messagebox.showwarning("Aviso", "Selecione uma despesa para editar.")
            return

        dados_linha = tabela_despesas.item(selecao[0], "values")
        id_desp, desc_atual, val_atual_str, tipo_atual, data_atual = dados_linha[0], dados_linha[1], dados_linha[2], dados_linha[3], dados_linha[4]

        top_edit_d = ctk.CTkToplevel(janela)
        top_edit_d.title(f"Editar Despesa ID {id_desp}")
        top_edit_d.geometry("450x560")
        top_edit_d.grab_set()

        ctk.CTkLabel(top_edit_d, text="Descrição:", font=Tema.LABEL).pack(pady=(20, 0))
        entry_desc_e = ctk.CTkEntry(top_edit_d, justify="center", width=350, font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
        entry_desc_e.insert(0, desc_atual)
        entry_desc_e.pack(pady=5)

        ctk.CTkLabel(top_edit_d, text="Valor (R$):", font=Tema.LABEL).pack(pady=(10, 0))
        entry_val_e = ctk.CTkEntry(top_edit_d, justify="center", width=200, font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
        entry_val_e.insert(0, val_atual_str)
        entry_val_e.pack(pady=5)

        ctk.CTkLabel(top_edit_d, text="Tipo de Despesa:", font=Tema.LABEL).pack(pady=(10, 0))
        var_tipo_e = ctk.StringVar(value=tipo_atual)
        ctk.CTkOptionMenu(top_edit_d, values=opcoes_despesas, variable=var_tipo_e, font=ctk.CTkFont(size=14), width=350).pack(pady=5)

        ctk.CTkLabel(top_edit_d, text="Data (DD/MM/AAAA):", font=Tema.LABEL).pack(pady=(10, 0))
        entry_data_e = ctk.CTkEntry(top_edit_d, justify="center", width=200, font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
        entry_data_e.insert(0, data_atual)
        entry_data_e.pack(pady=5)

        def salvar_edicao_despesa(event=None):
            novo_valor = texto_para_valor(entry_val_e.get())
            nova_data = texto_para_data(entry_data_e.get())
            if novo_valor is None or nova_data is None:
                messagebox.showerror("Erro", "Valor ou Data inválida!")
                return
            if novo_valor == 0:
                messagebox.showerror("Erro", "O valor não pode ser zero!")
                return
            if not _confirmar_comissao_manual(var_tipo_e.get(), [nova_data]):
                return
            try:
                banco.executar("UPDATE despesas SET descricao = ?, valor = ?, tipo = ?, data_despesa = ? WHERE id = ?",
                                (entry_desc_e.get().strip().upper(), novo_valor, var_tipo_e.get(), entry_data_e.get().strip(), id_desp),
                                commit=True)
            except ErroBancoDados:
                alerta_erro_banco("Erro ao Salvar Edição da Despesa")
                return

            top_edit_d.destroy()
            atualizar_historico_despesas()
            processar_grafico_despesas("")
            processar_dre("")

        entry_data_e.bind("<Return>", salvar_edicao_despesa)
        ctk.CTkButton(top_edit_d, text="SALVAR ALTERAÇÕES", fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER,
                      font=ctk.CTkFont(size=16, weight="bold"), height=40, command=salvar_edicao_despesa,
                      corner_radius=Tema.RAIO_BOTAO).pack(pady=30)


    frame_botoes_desp = ctk.CTkFrame(aba_hist_desp, fg_color="transparent", corner_radius=0)
    frame_botoes_desp.pack(pady=10)

    ctk.CTkButton(frame_botoes_desp, text="✏️ Editar Selecionada", font=ctk.CTkFont(size=16, weight="bold"),
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, height=40, command=editar_despesa,
                  corner_radius=Tema.RAIO_BOTAO).pack(side="left", padx=10)
    ctk.CTkButton(frame_botoes_desp, text="🗑️ Apagar Selecionada", font=ctk.CTkFont(size=16, weight="bold"),
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, height=40, command=deletar_despesa,
                  corner_radius=Tema.RAIO_BOTAO).pack(side="left", padx=10)
    criar_botoes_exportar(frame_botoes_desp, tabela_despesas, "historico_de_despesas", "Histórico de Despesas").pack(side="left", padx=10)

    # --- 6.3. ABA GRÁFICOS ---
    # Mesmo motivo do var_ano_d do Dashboard: começa vazio para que mostrar_tela()
    # escolha o ano vigente (mais recente com dados) como padrão, em vez de "Todos"
    # -- que somava o mesmo mês-calendário de TODOS os anos numa célula só, inflando
    # os totais de aluguel/luz/etc. "Todos" continua disponível na lista de anos.
    var_ano_graf_desp = ctk.StringVar(value="")
    dict_vars_tipos_desp = {t: ctk.BooleanVar(value=True) for t in opcoes_despesas}

    frame_filtro_graf_desp = ctk.CTkFrame(aba_graf_desp, fg_color="transparent", corner_radius=0)
    frame_filtro_graf_desp.pack(fill="x", padx=10, pady=(5, 0))

    menu_ano_graf_desp = ctk.CTkOptionMenu(frame_filtro_graf_desp, variable=var_ano_graf_desp, font=ctk.CTkFont(size=14))
    ctk.CTkLabel(frame_filtro_graf_desp, text="Ano:", font=Tema.LABEL).pack(side="left", padx=(0, 5))
    menu_ano_graf_desp.pack(side="left", padx=5)

    frame_opcoes_graf_desp = ctk.CTkFrame(aba_graf_desp, fg_color="transparent", corner_radius=0)
    frame_opcoes_graf_desp.pack(fill="x", padx=10, pady=(5, 5))

    scroll_tipos_desp = ctk.CTkScrollableFrame(aba_graf_desp, height=50, orientation="horizontal", fg_color="transparent")
    scroll_tipos_desp.pack(fill="x", padx=10, pady=(0, 5))

    # A TABELA vem primeiro e ocupa o espaço que sobrar (números grandes e visíveis, sem
    # precisar rolar a tela) -- o GRÁFICO fica embaixo, numa faixa menor e de altura fixa,
    # só para dar a visão geral da tendência ao longo do ano.
    frame_tab_graf_desp = ctk.CTkFrame(aba_graf_desp, corner_radius=0)
    frame_tab_graf_desp.pack(fill="both", expand=True, padx=10, pady=(5, 5))

    tabela_graf_desp = nova_tabela(frame_tab_graf_desp, columns=cols_d, show="headings")
    tabela_graf_desp.heading("Nome", text="TIPO DE DESPESA · R$")
    tabela_graf_desp.column("Nome", width=240, minwidth=200, anchor="w")
    for c in cols_d[1:]:
        tabela_graf_desp.heading(c, text=c)
        tabela_graf_desp.column(c, width=100 if c != "TOTAL" else 118, minwidth=85, anchor="e")
    tabela_graf_desp.pack(fill="both", expand=True)

    frame_graf_desp_container = ctk.CTkFrame(aba_graf_desp, height=260, fg_color="transparent", corner_radius=0)
    frame_graf_desp_container.pack(fill="x", padx=10, pady=(0, 5))
    frame_graf_desp_container.pack_propagate(False)


    def processar_grafico_despesas(*args):
        for w in frame_graf_desp_container.winfo_children():
            w.destroy()
        plt.close("all")

        ano_sel = var_ano_graf_desp.get()
        tipos_selecionados = [t for t, var in dict_vars_tipos_desp.items() if var.get()]

        try:
            dados = banco.consultar_todos("SELECT UPPER(tipo), valor, data_despesa FROM despesas WHERE data_despesa IS NOT NULL")
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Gráfico de Despesas")
            return

        m_despesas = {tipo: novo_mapa_meses() for tipo in tipos_selecionados}

        for tipo, val, data_d in dados:
            if not tipo:
                tipo = "OUTROS CUSTOS"
            tipo = str(tipo).strip()
            if tipo not in tipos_selecionados:
                continue

            ano_d, mes_d = ano_mes_de_data_flexivel(data_d)
            if ano_d is None:
                continue
            if ano_sel != "Todos" and ano_d != ano_sel:
                continue

            try:
                val = float(val)
            except (TypeError, ValueError):
                val = 0.0

            if mes_d in m_despesas[tipo]:
                m_despesas[tipo][mes_d] += val

        fig, ax = plt.subplots(figsize=(10, 2.6), dpi=100)
        meses_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        paleta = ["#FF69B4", "#1E90FF", "#32CD32", "#9370DB", "#DAA520", "#FF4500", "#00CED1", "#8A2BE2",
                  "#008080", "#D2691E", "#FF1493", "#2E8B57", "#4B0082", "#A52A2A", "#5F9EA0", "#D2B48C",
                  "#FF8C00", "#9932CC", "#8B0000", "#4682B4", "#696969"]

        tem_dado = False
        cor_index = 0

        for item in tabela_graf_desp.get_children():
            tabela_graf_desp.delete(item)
        linha_count = 0
        total_geral_meses = novo_mapa_meses()
        total_geral_absoluto = 0.0

        for tipo, meses_dict in m_despesas.items():
            valores = list(meses_dict.values())
            soma_linha = sum(valores)

            if soma_linha > 0:
                cor = paleta[cor_index % len(paleta)]
                ax.plot(meses_labels, valores, marker="o", label=tipo, color=cor, linewidth=2, markersize=6)
                tem_dado = True
                cor_index += 1

                linha_val = [tipo] + [valor_dre(v) for v in valores] + [valor_dre(soma_linha)]
                tabela_graf_desp.insert("", "end", values=linha_val, tags=("linha_par" if linha_count % 2 == 0 else "linha_impar",))
                linha_count += 1

                for m_key, v in meses_dict.items():
                    total_geral_meses[m_key] += v
                total_geral_absoluto += soma_linha

        if tem_dado:
            linha_total = ["TOTAL DE DESPESAS"] + [valor_dre(total_geral_meses[f"{i:02d}"]) for i in range(1, 13)] + [valor_dre(total_geral_absoluto)]
            tabela_graf_desp.insert("", "end", values=linha_total, tags=("tag_TOTAL",))

            titulo = f"Evolução Mensal de Despesas - {ano_sel if ano_sel != 'Todos' else 'Todos os Anos'}"
            ax.set_title(titulo, fontsize=11, fontweight="bold")
            ax.set_ylabel("Valor (R$)")
            # Legenda embaixo do gráfico (em várias colunas), em vez de numa coluna só do
            # lado direito -- com o gráfico mais baixo (para dar espaço pra tabela em cima),
            # uma legenda vertical com muitos tipos de despesa não cabia direito.
            ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=6)
            ax.grid(axis="y", linestyle="--", alpha=0.5)
            ax.ticklabel_format(style="plain", axis="y")
        else:
            ax.text(0.5, 0.5, "Sem registros para as opções selecionadas.", ha="center", va="center")
            ax.axis("off")

        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=frame_graf_desp_container)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)


    def marcar_todos_desp(estado):
        for var in dict_vars_tipos_desp.values():
            var.set(estado)
        processar_grafico_despesas()


    menu_ano_graf_desp.configure(command=processar_grafico_despesas)

    ctk.CTkButton(frame_opcoes_graf_desp, text="Marcar Todos", width=90, height=30, font=ctk.CTkFont(size=14),
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, command=lambda: marcar_todos_desp(True),
                  corner_radius=Tema.RAIO_BOTAO).pack(side="left", padx=5)
    ctk.CTkButton(frame_opcoes_graf_desp, text="Desmarcar Todos", width=90, height=30, font=ctk.CTkFont(size=14),
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, command=lambda: marcar_todos_desp(False),
                  corner_radius=Tema.RAIO_BOTAO).pack(side="left", padx=5)
    criar_botoes_exportar(frame_opcoes_graf_desp, tabela_graf_desp, "grafico_de_despesas", "Evolução Mensal de Despesas").pack(side="left", padx=5)

    for t in opcoes_despesas:
        ctk.CTkCheckBox(scroll_tipos_desp, text=t, variable=dict_vars_tipos_desp[t], font=ctk.CTkFont(size=14),
                         command=processar_grafico_despesas, fg_color=Tema.VERDE, hover_color=Tema.VERDE_HOVER).pack(side="left", padx=5)


    # =============================================================================
    # TELA 7: DRE ANUAL
    # =============================================================================
    _criar_botao_voltar_gestao(tela_dre)
    ctk.CTkLabel(tela_dre, text="DRE ANUAL - DEMONSTRAÇÃO DO RESULTADO", font=Tema.SUBTITULO).pack(pady=(20, 10))

    frame_filtros_dre = ctk.CTkFrame(tela_dre, fg_color="transparent", corner_radius=0)
    frame_filtros_dre.pack(pady=5, padx=20, fill="x")

    var_ano_dre = ctk.StringVar(value="Selecione o Ano")
    menu_ano_dre = ctk.CTkOptionMenu(frame_filtros_dre, variable=var_ano_dre, font=ctk.CTkFont(size=14))
    ctk.CTkLabel(frame_filtros_dre, text="Selecione o Ano de Referência:", font=Tema.LABEL).pack(side="left", padx=(0, 5))
    menu_ano_dre.pack(side="left", padx=5)

    # Resumo em números GRANDES, para bater o olho antes de ir na tabela detalhada.
    frame_kpis_dre = ctk.CTkFrame(tela_dre, fg_color="transparent", corner_radius=0)
    frame_kpis_dre.pack(fill="x", padx=20, pady=(5, 10))
    label_kpi_dre_receita = _criar_cartao_kpi(frame_kpis_dre, "RECEITA BRUTA")
    label_kpi_dre_despesas = _criar_cartao_kpi(frame_kpis_dre, "TOTAL DESPESAS")
    label_kpi_dre_lucro = _criar_cartao_kpi(frame_kpis_dre, "LUCRO LÍQUIDO")
    label_kpi_dre_margem = _criar_cartao_kpi(frame_kpis_dre, "MARGEM DE LUCRO")

    frame_tab_dre = ctk.CTkFrame(tela_dre, height=300, corner_radius=0)
    frame_tab_dre.pack(fill="x", padx=20, pady=(0, 10))
    frame_tab_dre.pack_propagate(False)

    colunas_dre = ["Categoria", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez", "TOTAL ANO", "%"]
    # Valores das células sem o "R$" (o cabeçalho avisa que tudo está em R$):
    # assim "100.757,82" cabe inteiro na coluna, sem cortar os centavos.
    scroll_dre_y = ttk.Scrollbar(frame_tab_dre, orient="vertical")
    scroll_dre_x = ttk.Scrollbar(frame_tab_dre, orient="horizontal")
    tabela_dre = nova_tabela(frame_tab_dre, columns=colunas_dre, show="headings",
                             yscrollcommand=scroll_dre_y.set, xscrollcommand=scroll_dre_x.set)
    scroll_dre_y.configure(command=tabela_dre.yview)
    scroll_dre_x.configure(command=tabela_dre.xview)
    tabela_dre.heading("Categoria", text="CATEGORIA (R$)")
    tabela_dre.column("Categoria", width=230, minwidth=200, anchor="w", stretch=True)
    for c in colunas_dre[1:]:
        tabela_dre.heading(c, text=c)
        largura = {"TOTAL ANO": 135, "%": 65}.get(c, 112)
        tabela_dre.column(c, width=largura, minwidth=largura, anchor="e" if c != "%" else "center", stretch=False)
    # Em telas menores, a barra horizontal aparece embaixo da tabela.
    scroll_dre_y.pack(side="right", fill="y")
    scroll_dre_x.pack(side="bottom", fill="x")
    tabela_dre.pack(side="left", fill="both", expand=True)

    tabela_dre.tag_configure("linha_receita", foreground="#7EE2A0", background="#1E3A2A")
    tabela_dre.tag_configure("linha_despesa", foreground=Tema.TABELA_TEXTO, background=Tema.LINHA_IMPAR)
    tabela_dre.tag_configure("linha_despesa_alt", foreground=Tema.TABELA_TEXTO, background=Tema.LINHA_PAR)
    tabela_dre.tag_configure("linha_total_despesa", foreground="#FF8A80", background="#3D2323")
    tabela_dre.tag_configure("linha_lucro", foreground="#8AB4FF", background="#1F2D45")
    tabela_dre.tag_configure("linha_prejuizo", foreground="#FF8A80", background="#3D2323")

    _nota_comissao = (f"COMISSÕES: até o mês anterior a {inicio_comissao_automatica}, valores lançados em Despesas; "
                      f"a partir de {inicio_comissao_automatica}, 1% automático sobre o recebido no mês")
    if inicio_comissao_automatica == "01/1900":
        _nota_comissao = "COMISSÕES: 1% automático sobre o valor recebido no mês"
    _nota_comissao += f" (sem {', '.join(sem_comissao)})." if sem_comissao else "."
    for _nota in (_nota_comissao,
                  "BONIFICAÇÕES: lançadas em Gestão → Bonificações + bonificação dos Desafios do mês."):
        ctk.CTkLabel(tela_dre, text=_nota, font=ctk.CTkFont(size=12), text_color=Tema.CINZA_TEXTO,
                     anchor="w", justify="left").pack(anchor="w", padx=22)
    frame_botoes_dre = ctk.CTkFrame(tela_dre, fg_color="transparent")
    frame_botoes_dre.pack(padx=20, anchor="e")
    criar_botoes_exportar(frame_botoes_dre, tabela_dre, "dre_anual", "DRE Anual").pack()

    frame_graf_dre_container = ctk.CTkFrame(tela_dre, fg_color="transparent", corner_radius=0)
    frame_graf_dre_container.pack(fill="both", expand=True, padx=20, pady=5)


    def _resetar_cartoes_kpi_dre():
        for lbl in (label_kpi_dre_receita, label_kpi_dre_despesas, label_kpi_dre_lucro, label_kpi_dre_margem):
            lbl.configure(text="—", text_color=("black", "white"))


    def _comissao_automatica_por_mes(ano):
        """1% do valor com vencimento em cada mês do ano (= aba 'Comissões (A Pagar)'
        do Dashboard com todas as vendedoras marcadas), só nos meses automáticos."""
        meses = novo_mapa_meses()
        filtro_excl = ""
        params = [ano]
        if _sem_comissao:
            filtro_excl = f" AND {SQL_NOME_VENDEDOR} NOT IN ({','.join('?' for _ in _sem_comissao)})"
            params += _sem_comissao
        linhas = banco.consultar_todos(
            "SELECT substr(data_vencimento, 4, 2), SUM(valor) FROM vendas "
            f"WHERE substr(data_vencimento, 7, 4) = ?{filtro_excl} GROUP BY 1", params)
        for mes, soma in linhas:
            if mes in meses and _comissao_automatica_no_mes(ano, mes):
                meses[mes] = round((soma or 0.0) * PERCENTUAL_COMISSAO, 2)
        return meses

    def _bonificacoes_por_mes(ano):
        """Linha BONIFICAÇÕES do DRE: bonificações lançadas na Gestão (pelo mês de
        referência) + bonificação dos Desafios do mês (mesmo cálculo da aba
        'Conclusão Mensal')."""
        meses = novo_mapa_meses()
        for mes, soma in banco.consultar_todos(
                "SELECT mes, SUM(valor) FROM bonificacoes WHERE ano = ? GROUP BY mes", (ano,)):
            if mes in meses:
                meses[mes] += soma or 0.0

        dias_por_mes = {r[0]: r[1] for r in banco.consultar_todos(
            "SELECT substr(data, 4, 2), COUNT(*) FROM desafios WHERE substr(data, 7, 4) = ? GROUP BY 1", (ano,))}
        for mes, vendedor, qtd in banco.consultar_todos(
                "SELECT substr(d.data, 4, 2), r.vendedor, SUM(r.quantidade) FROM desafio_resultados r "
                "JOIN desafios d ON d.id = r.desafio_id WHERE substr(d.data, 7, 4) = ? GROUP BY 1, 2", (ano,)):
            if mes in meses and normalizar_nome_vendedor(vendedor) not in _excluidos_desafio:
                meses[mes] += calcular_conclusao_desafio(dias_por_mes.get(mes, 0), qtd or 0)["bonificacao"]
        return {m: round(v, 2) for m, v in meses.items()}

    def processar_dre(*args):
        for item in tabela_dre.get_children():
            tabela_dre.delete(item)
        for w in frame_graf_dre_container.winfo_children():
            w.destroy()
        plt.close("all")

        ano_sel = var_ano_dre.get()
        if ano_sel == "Selecione o Ano":
            _resetar_cartoes_kpi_dre()
            return

        try:
            vendas_brutas = banco.consultar_todos("SELECT data_venda, valor FROM vendas")
            despesas_brutas = banco.consultar_todos("SELECT tipo, data_despesa, valor FROM despesas")
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar DRE")
            _resetar_cartoes_kpi_dre()
            return

        # 1. RECEITAS (VENDAS)
        receita_meses = novo_mapa_meses()
        for data_v, val in vendas_brutas:
            ano_v, mes_v = ano_mes_de_data_flexivel(data_v)
            if ano_v == ano_sel and mes_v in receita_meses:
                receita_meses[mes_v] += val

        # 2. DESPESAS
        despesas_tipo_meses = {}
        total_despesa_meses = novo_mapa_meses()

        for tipo, data_d, val in despesas_brutas:
            if not data_d:
                continue
            tipo = tipo.strip().upper() if tipo else "OUTROS CUSTOS"
            ano_d, mes_d = ano_mes_de_data_flexivel(data_d)
            if ano_d == ano_sel and mes_d in total_despesa_meses:
                # Comissão manual só vale ANTES do início da comissão automática.
                if tipo == TIPO_DESPESA_COMISSAO and _comissao_automatica_no_mes(ano_d, mes_d):
                    continue
                if tipo not in despesas_tipo_meses:
                    despesas_tipo_meses[tipo] = novo_mapa_meses()
                despesas_tipo_meses[tipo][mes_d] += val or 0.0
                total_despesa_meses[mes_d] += val or 0.0

        # 3. COMISSÃO AUTOMÁTICA (1% do recebido no mês, sem quem não comissiona)
        #    e BONIFICAÇÕES (lançadas na Gestão + Desafios)
        try:
            comissao_auto = _comissao_automatica_por_mes(ano_sel)
            bonificacoes_mes = _bonificacoes_por_mes(ano_sel)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Comissões/Bonificações do DRE")
            _resetar_cartoes_kpi_dre()
            return
        if any(bonificacoes_mes.values()):
            linha_bonif = despesas_tipo_meses.setdefault("BONIFICAÇÕES", novo_mapa_meses())
            for mes_b, val_b in bonificacoes_mes.items():
                linha_bonif[mes_b] += val_b
                total_despesa_meses[mes_b] += val_b
        if any(comissao_auto.values()):
            linha_com = despesas_tipo_meses.setdefault(TIPO_DESPESA_COMISSAO, novo_mapa_meses())
            for mes_c, val_c in comissao_auto.items():
                linha_com[mes_c] += val_c
                total_despesa_meses[mes_c] += val_c

        # --- Preenchimento da Tabela ---
        total_ano_receita = sum(receita_meses.values())
        tabela_dre.insert("", "end", values=["RECEITA BRUTA"] + [valor_dre(receita_meses[f"{i:02d}"]) for i in range(1, 13)] + [valor_dre(total_ano_receita), "100%"], tags=("linha_receita",))

        c = 0
        for tipo in sorted(despesas_tipo_meses.keys()):
            valores = list(despesas_tipo_meses[tipo].values())
            total_tipo = sum(valores)
            pct = f"{(total_tipo / total_ano_receita * 100):.1f}%" if total_ano_receita > 0 else "0.0%"
            tag = "linha_despesa_alt" if c % 2 == 0 else "linha_despesa"
            tabela_dre.insert("", "end", values=[tipo] + [valor_dre(v) for v in valores] + [valor_dre(total_tipo), pct], tags=(tag,))
            c += 1

        total_ano_despesas = sum(total_despesa_meses.values())
        pct_desp = f"{(total_ano_despesas / total_ano_receita * 100):.1f}%" if total_ano_receita > 0 else "0.0%"
        tabela_dre.insert("", "end", values=["TOTAL DESPESAS"] + [valor_dre(total_despesa_meses[f"{i:02d}"]) for i in range(1, 13)] + [valor_dre(total_ano_despesas), pct_desp], tags=("linha_total_despesa",))

        lucro_meses = {m: receita_meses[m] - total_despesa_meses[m] for m in receita_meses}
        total_ano_lucro = total_ano_receita - total_ano_despesas
        pct_lucro = f"{(total_ano_lucro / total_ano_receita * 100):.1f}%" if total_ano_receita > 0 else "0.0%"
        tag_lucro = "linha_lucro" if total_ano_lucro >= 0 else "linha_prejuizo"

        tabela_dre.insert("", "end", values=["LUCRO LÍQUIDO"] + [valor_dre(lucro_meses[f"{i:02d}"]) for i in range(1, 13)] + [valor_dre(total_ano_lucro), pct_lucro], tags=(tag_lucro,))

        # --- Atualiza os cartões de resumo (números grandes) ---
        label_kpi_dre_receita.configure(text=formatar_moeda(total_ano_receita), text_color=Tema.VERDE)
        label_kpi_dre_despesas.configure(text=formatar_moeda(total_ano_despesas), text_color=Tema.VERMELHO)
        cor_lucro = Tema.VERDE if total_ano_lucro >= 0 else Tema.VERMELHO
        label_kpi_dre_lucro.configure(text=formatar_moeda(total_ano_lucro), text_color=cor_lucro)
        label_kpi_dre_margem.configure(text=pct_lucro, text_color=cor_lucro)

        fig, ax = plt.subplots(figsize=(10, 3.5), dpi=100)
        meses_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        ax.plot(meses_labels, list(receita_meses.values()), marker="o", label="Receita Bruta", color=Tema.VERDE, linewidth=3)
        ax.plot(meses_labels, list(total_despesa_meses.values()), marker="o", label="Despesas", color=Tema.VERMELHO, linewidth=3)
        ax.plot(meses_labels, list(lucro_meses.values()), marker="s", label="Lucro Líquido", color=Tema.AZUL, linewidth=2, linestyle="--")
        ax.set_title(f"DRE Anual - {ano_sel}", fontsize=12, fontweight="bold")
        ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=frame_graf_dre_container)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        janela.update_idletasks()


    menu_ano_dre.configure(command=processar_dre)


    # =============================================================================
    # TELA 7B: DESAFIOS (dentro da Área de Gestão, com senha)
    # =============================================================================
    # Regras do negócio (os cálculos ficam em calcular_conclusao_desafio):
    #   * Todo dia com desafio tem 1 produto escolhido e meta de 5 unidades por
    #     vendedora (META_DIARIA_DESAFIO).
    #   * A meta do MÊS é a mesma para todas: dias com desafio × 5.
    #   * Vale o total do mês: vender 3 num dia e 7 no outro soma 10 = 2 dias.
    #   * Bonificação = R$ 100 × % atingido, com teto de 100% (R$ 100,00).
    #   * Participam as vendedoras ATIVAS, menos as listadas em
    #     `excluidos_desafio` (definidos por filial em config_filiais.py).
    _criar_botao_voltar_gestao(tela_desafio)
    ctk.CTkLabel(tela_desafio, text="🏆 DESAFIOS", font=Tema.SUBTITULO).pack(pady=(15, 5))

    abas_desafio = ctk.CTkTabview(tela_desafio, command=lambda: _ao_trocar_aba_desafio())
    abas_desafio.pack(fill="both", expand=True, padx=20, pady=(0, 10))
    aba_lancar_desafio = abas_desafio.add("Lançar Desafio do Dia")
    aba_mensal_desafio = abas_desafio.add("Conclusão Mensal")

    def _participantes_desafio(extras=()):
        """Vendedoras ativas que participam + quem já tem resultado lançado (ex.: desligada no meio do mês)."""
        nomes = [n for n in obter_vendedores_ativos()
                 if n != "Nenhum Vendedor Ativo" and normalizar_nome_vendedor(n) not in _excluidos_desafio]
        nomes += sorted(n for n in extras if n not in nomes and normalizar_nome_vendedor(n) not in _excluidos_desafio)
        return nomes

    def _obter_desafio(data_texto):
        """Devolve (desafio, {vendedor: quantidade}) do dia, ou (None, {})."""
        desafio = banco.consultar_um("SELECT id, data, produto FROM desafios WHERE data = ?", (data_texto,))
        if desafio is None:
            return None, {}
        resultados = {r["vendedor"]: r["quantidade"] for r in banco.consultar_todos(
            "SELECT vendedor, quantidade FROM desafio_resultados WHERE desafio_id = ?", (desafio["id"],))}
        return desafio, resultados

    # -------------------------------------------------------------------------
    # ABA 1: LANÇAR DESAFIO DO DIA
    # -------------------------------------------------------------------------
    area_lancar = ctk.CTkScrollableFrame(aba_lancar_desafio, fg_color="transparent", corner_radius=0)
    area_lancar.pack(fill="both", expand=True)

    card_cad_desafio = ctk.CTkFrame(area_lancar, corner_radius=Tema.RAIO, fg_color=("gray86", "gray17"))
    card_cad_desafio.pack(fill="x", padx=10, pady=(5, 10))
    ctk.CTkLabel(card_cad_desafio, text="1. Produto do desafio", font=Tema.LABEL).pack(anchor="w", padx=16, pady=(12, 6))

    f_cad = ctk.CTkFrame(card_cad_desafio, fg_color="transparent")
    f_cad.pack(fill="x", padx=16, pady=(0, 6))
    ctk.CTkLabel(f_cad, text="Data:", font=Tema.TEXTO).pack(side="left")
    entry_data_desafio = ctk.CTkEntry(f_cad, width=120, justify="center", font=ctk.CTkFont(size=14),
                                      corner_radius=Tema.RAIO_BOTAO)
    entry_data_desafio.insert(0, datetime.now().strftime("%d/%m/%Y"))
    entry_data_desafio.pack(side="left", padx=(5, 4))

    def _mudar_dia_desafio(delta):
        base = texto_para_data(entry_data_desafio.get()) or datetime.now()
        entry_data_desafio.delete(0, "end")
        entry_data_desafio.insert(0, (base + timedelta(days=delta)).strftime("%d/%m/%Y"))
        carregar_desafio_gestao()

    for _txt, _delta in (("◀", -1), ("▶", 1)):
        ctk.CTkButton(f_cad, text=_txt, width=34, height=30, font=ctk.CTkFont(size=13, weight="bold"),
                      fg_color=("gray75", "gray30"), hover_color=("gray65", "gray40"), corner_radius=Tema.RAIO_BOTAO,
                      command=lambda d=_delta: _mudar_dia_desafio(d)).pack(side="left", padx=2)

    ctk.CTkLabel(f_cad, text="Produto:", font=Tema.TEXTO).pack(side="left", padx=(15, 0))
    entry_produto_desafio = ctk.CTkEntry(f_cad, width=300, placeholder_text="Ex.: CREME HASKELL",
                                         font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
    entry_produto_desafio.pack(side="left", padx=(5, 15))
    ctk.CTkLabel(f_cad, text=f"Meta fixa: {META_DIARIA_DESAFIO} por vendedora", font=Tema.LABEL,
                 text_color=Tema.CINZA_TEXTO).pack(side="left")

    f_cad_btn = ctk.CTkFrame(card_cad_desafio, fg_color="transparent")
    f_cad_btn.pack(fill="x", padx=16, pady=(0, 12))
    lbl_feedback_desafio = ctk.CTkLabel(f_cad_btn, text="", font=ctk.CTkFont(size=14, weight="bold"))
    lbl_feedback_desafio.pack(side="left")

    card_res_desafio = ctk.CTkFrame(area_lancar, corner_radius=Tema.RAIO, fg_color=("gray86", "gray17"))
    card_res_desafio.pack(fill="x", padx=10, pady=(0, 10))
    lbl_titulo_res_desafio = ctk.CTkLabel(card_res_desafio, text="2. Quantidade vendida por vendedora", font=Tema.LABEL)
    lbl_titulo_res_desafio.pack(anchor="w", padx=16, pady=(12, 6))
    grade_res_desafio = ctk.CTkFrame(card_res_desafio, fg_color="transparent")
    grade_res_desafio.pack(fill="x", padx=16, pady=(0, 6))
    grade_res_desafio.grid_columnconfigure(2, weight=1)
    f_res_btn = ctk.CTkFrame(card_res_desafio, fg_color="transparent")
    f_res_btn.pack(fill="x", padx=16, pady=(0, 12))

    estado_desafio = {"id": None, "entradas": {}}

    def _data_desafio_valida():
        d = texto_para_data(entry_data_desafio.get())
        if d is None:
            exibir_feedback(lbl_feedback_desafio, "⚠️ Data inválida! Use DD/MM/AAAA", Tema.VERMELHO)
            return None
        texto = d.strftime("%d/%m/%Y")
        if entry_data_desafio.get().strip() != texto:
            entry_data_desafio.delete(0, "end")
            entry_data_desafio.insert(0, texto)
        return texto

    def _montar_grade_resultados(desafio, resultados):
        for w in grade_res_desafio.winfo_children():
            w.destroy()
        for w in f_res_btn.winfo_children():
            w.destroy()
        estado_desafio["entradas"] = {}
        if desafio is None:
            estado_desafio["id"] = None
            lbl_titulo_res_desafio.configure(text="2. Quantidade vendida por vendedora")
            ctk.CTkLabel(grade_res_desafio, text="Salve o produto do desafio deste dia para lançar as quantidades.",
                         font=Tema.TEXTO, text_color=Tema.CINZA_TEXTO).grid(row=0, column=0, sticky="w")
            return

        meta = META_DIARIA_DESAFIO
        estado_desafio["id"] = desafio["id"]
        lbl_titulo_res_desafio.configure(text=f"2. Quantidade vendida por vendedora — {desafio['produto']}")
        nomes = _participantes_desafio(extras=resultados.keys())
        if not nomes:
            ctk.CTkLabel(grade_res_desafio, text="Nenhuma vendedora ativa participa do desafio.",
                         font=Tema.TEXTO, text_color=Tema.CINZA_TEXTO).grid(row=0, column=0, sticky="w")
            return
        for i, nome in enumerate(nomes):
            ctk.CTkLabel(grade_res_desafio, text=nome, font=Tema.LABEL, width=140, anchor="w").grid(
                row=i, column=0, sticky="w", pady=4)
            entrada = ctk.CTkEntry(grade_res_desafio, width=70, justify="center", font=ctk.CTkFont(size=14),
                                   corner_radius=Tema.RAIO_BOTAO)
            entrada.insert(0, str(resultados.get(nome, 0)))
            entrada.grid(row=i, column=1, padx=10, pady=4)
            barra = ctk.CTkProgressBar(grade_res_desafio, height=14, corner_radius=7)
            barra.grid(row=i, column=2, sticky="ew", padx=10)
            lbl = ctk.CTkLabel(grade_res_desafio, text="", font=Tema.LABEL, width=80, anchor="e")
            lbl.grid(row=i, column=3, sticky="e")

            def _atualizar_linha(event=None, entrada=entrada, barra=barra, lbl=lbl):
                txt = entrada.get().strip()
                qtd = int(txt) if txt.isdigit() else 0
                bateu = qtd >= meta
                barra.configure(progress_color=Tema.VERDE if bateu else Tema.AMARELO)
                barra.set(min(qtd / meta, 1.0))
                lbl.configure(text=f"{'✔ ' if bateu else ''}{qtd}/{meta}",
                              text_color=Tema.VERDE if bateu else Tema.TEXTO_PADRAO)

            entrada.bind("<KeyRelease>", _atualizar_linha)
            _atualizar_linha()
            estado_desafio["entradas"][nome] = entrada

        ctk.CTkButton(f_res_btn, text="SALVAR QUANTIDADES", font=ctk.CTkFont(size=16, weight="bold"), height=42,
                      fg_color=Tema.VERDE, hover_color=Tema.VERDE_HOVER, corner_radius=Tema.RAIO_BOTAO,
                      command=salvar_resultados_desafio).pack(side="right")

    def carregar_desafio_gestao(event=None):
        data = _data_desafio_valida()
        if data is None:
            return
        try:
            desafio, resultados = _obter_desafio(data)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Desafio")
            return
        entry_produto_desafio.delete(0, "end")
        if desafio:
            entry_produto_desafio.insert(0, desafio["produto"])
        _montar_grade_resultados(desafio, resultados)

    def salvar_desafio(event=None):
        data = _data_desafio_valida()
        if data is None:
            return
        produto = entry_produto_desafio.get().strip().upper()
        if not produto:
            exibir_feedback(lbl_feedback_desafio, "⚠️ Informe o nome do produto!", Tema.VERMELHO)
            return
        try:
            banco.executar(
                "INSERT INTO desafios (data, produto, meta_quantidade, criado_em) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(data) DO UPDATE SET produto = excluded.produto",
                (data, produto, META_DIARIA_DESAFIO, datetime.now().strftime("%d/%m/%Y %H:%M")), commit=True)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Salvar Desafio")
            return
        carregar_desafio_gestao()
        exibir_feedback(lbl_feedback_desafio, f"✔️ Desafio de {data} salvo!", Tema.VERDE)

    def excluir_desafio():
        data = _data_desafio_valida()
        if data is None or estado_desafio["id"] is None:
            exibir_feedback(lbl_feedback_desafio, "⚠️ Não há desafio cadastrado nesta data.", Tema.VERMELHO)
            return
        if not messagebox.askyesno("Confirmar",
                                   f"Excluir o desafio de {data} e as quantidades lançadas?\n"
                                   "Esse dia deixa de contar na meta do mês."):
            return
        try:
            banco.transacao([("DELETE FROM desafio_resultados WHERE desafio_id = ?", (estado_desafio["id"],)),
                             ("DELETE FROM desafios WHERE id = ?", (estado_desafio["id"],))])
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Excluir Desafio")
            return
        carregar_desafio_gestao()
        exibir_feedback(lbl_feedback_desafio, "✔️ Desafio excluído.", Tema.VERDE)

    def salvar_resultados_desafio():
        if estado_desafio["id"] is None:
            return
        comandos = []
        for nome, entrada in estado_desafio["entradas"].items():
            txt = entrada.get().strip() or "0"
            if not txt.isdigit():
                messagebox.showerror("Erro", f"Quantidade inválida para {nome}. Use um número inteiro (0, 1, 2...).")
                return
            comandos.append(("INSERT INTO desafio_resultados (desafio_id, vendedor, quantidade) VALUES (?, ?, ?) "
                             "ON CONFLICT(desafio_id, vendedor) DO UPDATE SET quantidade = excluded.quantidade",
                             (estado_desafio["id"], nome, int(txt))))
        try:
            banco.transacao(comandos)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Salvar Quantidades do Desafio")
            return
        carregar_desafio_gestao()
        exibir_feedback(lbl_feedback_desafio, "✔️ Quantidades salvas!", Tema.VERDE)

    ctk.CTkButton(f_cad_btn, text="Excluir desafio", font=ctk.CTkFont(size=14, weight="bold"), height=38,
                  fg_color="transparent", border_width=2, border_color=Tema.VERMELHO, text_color=Tema.VERMELHO,
                  hover_color=("gray80", "gray25"), corner_radius=Tema.RAIO_BOTAO,
                  command=excluir_desafio).pack(side="right", padx=(8, 0))
    ctk.CTkButton(f_cad_btn, text="SALVAR PRODUTO", font=ctk.CTkFont(size=16, weight="bold"), height=38,
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, corner_radius=Tema.RAIO_BOTAO,
                  command=salvar_desafio).pack(side="right")

    entry_data_desafio.bind("<Return>", carregar_desafio_gestao)
    entry_produto_desafio.bind("<Return>", salvar_desafio)

    # -------------------------------------------------------------------------
    # ABA 2: CONCLUSÃO MENSAL (cálculo automático da bonificação)
    # -------------------------------------------------------------------------
    MESES_NOMES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
                   "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

    frame_filtro_mensal = ctk.CTkFrame(aba_mensal_desafio, fg_color="transparent")
    frame_filtro_mensal.pack(fill="x", padx=10, pady=(5, 5))
    ctk.CTkLabel(frame_filtro_mensal, text="Mês:", font=Tema.LABEL).pack(side="left", padx=(0, 5))
    var_mes_desafio = ctk.StringVar(value=MESES_NOMES[datetime.now().month - 1])
    ctk.CTkOptionMenu(frame_filtro_mensal, values=MESES_NOMES, variable=var_mes_desafio, width=140,
                      font=ctk.CTkFont(size=14), command=lambda _: processar_conclusao_mensal()).pack(side="left", padx=5)
    ctk.CTkLabel(frame_filtro_mensal, text="Ano:", font=Tema.LABEL).pack(side="left", padx=(15, 5))
    var_ano_desafio = ctk.StringVar(value=str(datetime.now().year))
    menu_ano_desafio = ctk.CTkOptionMenu(frame_filtro_mensal, values=[str(datetime.now().year)], variable=var_ano_desafio,
                                         width=100, font=ctk.CTkFont(size=14),
                                         command=lambda _: processar_conclusao_mensal())
    menu_ano_desafio.pack(side="left", padx=5)
    frame_exportar_mensal = ctk.CTkFrame(frame_filtro_mensal, fg_color="transparent")
    frame_exportar_mensal.pack(side="right")

    frame_kpis_desafio = ctk.CTkFrame(aba_mensal_desafio, fg_color="transparent")
    frame_kpis_desafio.pack(fill="x", padx=2, pady=(5, 10))
    kpi_dias_desafio = _criar_cartao_kpi(frame_kpis_desafio, "DIAS COM DESAFIO")
    kpi_meta_desafio = _criar_cartao_kpi(frame_kpis_desafio, "META DO MÊS (POR VENDEDORA)")
    kpi_total_desafio = _criar_cartao_kpi(frame_kpis_desafio, "TOTAL DE BONIFICAÇÕES")

    frame_tab_mensal = ctk.CTkFrame(aba_mensal_desafio, corner_radius=0, height=250)
    frame_tab_mensal.pack(fill="x", padx=10, pady=(0, 8))
    frame_tab_mensal.pack_propagate(False)
    colunas_mensal = ("vendedora", "vendido", "meta", "dias", "pct", "bonus")
    tabela_mensal_desafio = nova_tabela(frame_tab_mensal, columns=colunas_mensal, show="headings")
    for c, t_, w in (("vendedora", "Vendedora", 180), ("vendido", "Vendido no mês", 140), ("meta", "Meta do mês", 120),
                     ("dias", "Dias concluídos", 150), ("pct", "% concluída", 120), ("bonus", "Bonificação", 140)):
        tabela_mensal_desafio.heading(c, text=t_)
        tabela_mensal_desafio.column(c, width=w, anchor="w" if c == "vendedora" else "center")
    tabela_mensal_desafio.tag_configure("bateu_100", foreground="#6EE07A")
    tabela_mensal_desafio.pack(fill="both", expand=True)

    ctk.CTkLabel(aba_mensal_desafio, text="Detalhe por dia", font=Tema.LABEL).pack(anchor="w", padx=12, pady=(4, 2))
    frame_tab_diario_desafio = ctk.CTkFrame(aba_mensal_desafio, corner_radius=0)
    frame_tab_diario_desafio.pack(fill="both", expand=True, padx=10, pady=(0, 5))
    scroll_diario_desafio = ttk.Scrollbar(frame_tab_diario_desafio, orient="vertical")
    scroll_diario_desafio.pack(side="right", fill="y")
    tabela_diario_desafio = nova_tabela(frame_tab_diario_desafio, columns=("data", "produto"), show="headings",
                                        yscrollcommand=scroll_diario_desafio.set)
    scroll_diario_desafio.configure(command=tabela_diario_desafio.yview)
    tabela_diario_desafio.pack(side="left", fill="both", expand=True)

    estado_mensal_desafio = {"titulo": ""}

    def processar_conclusao_mensal(*args):
        mes = f"{MESES_NOMES.index(var_mes_desafio.get()) + 1:02d}"
        ano = var_ano_desafio.get()
        try:
            desafios_mes = banco.consultar_todos(
                "SELECT id, data, produto FROM desafios WHERE substr(data, 4, 2) = ? AND substr(data, 7, 4) = ? "
                "ORDER BY substr(data, 1, 2)", (mes, ano))
            resultados = banco.consultar_todos(
                "SELECT r.desafio_id, r.vendedor, r.quantidade FROM desafio_resultados r "
                "JOIN desafios d ON d.id = r.desafio_id WHERE substr(d.data, 4, 2) = ? AND substr(d.data, 7, 4) = ?",
                (mes, ano))
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Conclusão Mensal")
            return

        por_dia = {}          # desafio_id -> {vendedora: qtd}
        total_vendedora = {}  # vendedora -> total vendido no mês
        for r in resultados:
            por_dia.setdefault(r["desafio_id"], {})[r["vendedor"]] = r["quantidade"]
            total_vendedora[r["vendedor"]] = total_vendedora.get(r["vendedor"], 0) + r["quantidade"]

        # Quem participou do mês = quem teve quantidade lançada (mesmo que 0) naquele
        # mês. Assim, olhar um mês antigo não mostra quem foi contratada depois.
        # Mês ainda sem nenhum lançamento: mostra as participantes atuais.
        if total_vendedora:
            nomes = sorted(n for n in total_vendedora if normalizar_nome_vendedor(n) not in _excluidos_desafio)
        else:
            nomes = _participantes_desafio()
        dias = len(desafios_mes)

        # --- Tabela de conclusão ---
        for item in tabela_mensal_desafio.get_children():
            tabela_mensal_desafio.delete(item)
        total_bonus = 0.0
        total_vendido = 0
        for i, nome in enumerate(nomes):
            r = calcular_conclusao_desafio(dias, total_vendedora.get(nome, 0))
            total_bonus += r["bonificacao"]
            total_vendido += r["vendido"]
            tags = ["linha_par" if i % 2 == 0 else "linha_impar"]
            if r["percentual"] >= 100:
                tags.append("bateu_100")
            tabela_mensal_desafio.insert("", "end", values=(
                nome, r["vendido"], r["meta"], f"{r['dias_concluidos']} de {dias}",
                f"{r['percentual']:.1f}%".replace(".", ","), moeda_sempre(r["bonificacao"])), tags=tuple(tags))
        if nomes:
            tabela_mensal_desafio.insert("", "end", values=(
                "TOTAL", total_vendido, "", "", "", moeda_sempre(total_bonus)), tags=("tag_TOTAL",))

        kpi_dias_desafio.configure(text=str(dias), text_color=Tema.TEXTO_PADRAO)
        kpi_meta_desafio.configure(text=f"{dias * META_DIARIA_DESAFIO} un.", text_color=Tema.TEXTO_PADRAO)
        kpi_total_desafio.configure(text=moeda_sempre(total_bonus), text_color=Tema.VERDE)

        # --- Tabela de detalhe por dia (uma coluna por vendedora) ---
        colunas = ["data", "produto"] + nomes
        tabela_diario_desafio.configure(columns=colunas)
        tabela_diario_desafio.heading("data", text="Data")
        tabela_diario_desafio.column("data", width=120, minwidth=120, anchor="center", stretch=False)
        tabela_diario_desafio.heading("produto", text="Produto")
        tabela_diario_desafio.column("produto", width=260, anchor="w")
        for nome in nomes:
            tabela_diario_desafio.heading(nome, text=nome)
            tabela_diario_desafio.column(nome, width=110, anchor="center")
        for item in tabela_diario_desafio.get_children():
            tabela_diario_desafio.delete(item)
        for i, d in enumerate(desafios_mes):
            qtds = por_dia.get(d["id"], {})
            tabela_diario_desafio.insert("", "end", values=[d["data"], d["produto"]] + [qtds.get(n, 0) for n in nomes],
                                         tags=("linha_par" if i % 2 == 0 else "linha_impar",))
        estado_mensal_desafio["titulo"] = f"{var_mes_desafio.get()}/{ano}"

    def _anos_desafio():
        anos = _anos_distintos([("SELECT DISTINCT data FROM desafios", ())])
        atual = str(datetime.now().year)
        if atual not in anos:
            anos.insert(0, atual)
        return sorted(anos, reverse=True)

    def _ao_trocar_aba_desafio():
        if abas_desafio.get() == "Conclusão Mensal":
            anos = _anos_desafio()
            menu_ano_desafio.configure(values=anos)
            if var_ano_desafio.get() not in anos:
                var_ano_desafio.set(anos[0])
            processar_conclusao_mensal()

    def _exportar_mensal_desafio(tipo, tabela):
        periodo = estado_mensal_desafio["titulo"] or "periodo"
        nome = ("conclusao_desafios_" if tabela is tabela_mensal_desafio else "desafios_por_dia_") + periodo.replace("/", "_")
        titulo = ("Conclusão dos Desafios - " if tabela is tabela_mensal_desafio else "Desafios por Dia - ") + periodo
        if tipo == "excel":
            exportar_tabela_excel(tabela, nome, titulo[:31])
        else:
            exportar_tabela_pdf(tabela, nome, titulo)

    for _texto, _tipo, _tab, _cor, _hover in (
            ("📊 Excel (resumo)", "excel", tabela_mensal_desafio, Tema.AZUL, Tema.AZUL_HOVER),
            ("📄 PDF (resumo)", "pdf", tabela_mensal_desafio, Tema.VERMELHO, Tema.VERMELHO_HOVER),
            ("📊 Excel (por dia)", "excel", tabela_diario_desafio, Tema.AZUL, Tema.AZUL_HOVER)):
        ctk.CTkButton(frame_exportar_mensal, text=_texto, font=ctk.CTkFont(size=13, weight="bold"), height=32,
                      fg_color=_cor, hover_color=_hover, corner_radius=Tema.RAIO_BOTAO,
                      command=lambda t=_tipo, tb=_tab: _exportar_mensal_desafio(t, tb)).pack(side="left", padx=4)


    # =============================================================================
    # TELA 7C: BONIFICAÇÕES (dentro da Área de Gestão, com senha)
    # =============================================================================
    # Bonificações pagas à parte para algumas funcionárias, conforme os critérios
    # da gerência. Ficam SEPARADAS da comissão de 1% (que é automática) e
    # NÃO passam pela tela de Despesas.
    #   * Cada lançamento = vendedora + mês de referência + valor + motivo.
    #   * No DRE, entram na linha "BONIFICAÇÕES" do mês de referência, somadas à
    #     bonificação dos Desafios daquele mês (calculada automaticamente).
    #   * Só aceita meses a partir de `inicio_comissao_automatica` (09/2026): os
    #     meses anteriores já têm a bonificação embutida nos lançamentos manuais
    #     de COMISSÕES e ficam como estão (sem contar duas vezes).
    _criar_botao_voltar_gestao(tela_bonificacoes)
    ctk.CTkLabel(tela_bonificacoes, text="🎁 BONIFICAÇÕES", font=Tema.SUBTITULO).pack(pady=(15, 5))

    area_bonif = ctk.CTkScrollableFrame(tela_bonificacoes, fg_color="transparent", corner_radius=0)
    area_bonif.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    _MESES_BONIF = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
                    "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

    def _anos_permitidos_bonif():
        """Do ano de início da comissão automática até o ano que vem."""
        inicio = int(_ano_ini_com) if _ano_ini_com.isdigit() else datetime.now().year
        return [str(a) for a in range(datetime.now().year + 1, inicio - 1, -1)]

    def _mes_permitido_bonif(mes_nome, ano):
        mes = f"{_MESES_BONIF.index(mes_nome) + 1:02d}"
        return _comissao_automatica_no_mes(ano, mes), mes

    # --- 1. Lançar bonificação ---
    card_lanc_bonif = ctk.CTkFrame(area_bonif, corner_radius=Tema.RAIO, fg_color=("gray86", "gray17"))
    card_lanc_bonif.pack(fill="x", padx=10, pady=(5, 10))
    ctk.CTkLabel(card_lanc_bonif, text="Lançar bonificação", font=Tema.LABEL).pack(anchor="w", padx=16, pady=(12, 6))

    f_lanc_bonif = ctk.CTkFrame(card_lanc_bonif, fg_color="transparent")
    f_lanc_bonif.pack(fill="x", padx=16, pady=(0, 6))
    ctk.CTkLabel(f_lanc_bonif, text="Vendedora:", font=Tema.TEXTO).pack(side="left")
    var_vend_bonif = ctk.StringVar(value="Selecione")
    menu_vend_bonif = ctk.CTkOptionMenu(f_lanc_bonif, values=[], variable=var_vend_bonif, width=170,
                                        font=ctk.CTkFont(size=14))
    menu_vend_bonif.pack(side="left", padx=(5, 15))
    ctk.CTkLabel(f_lanc_bonif, text="Mês de referência:", font=Tema.TEXTO).pack(side="left")
    var_mes_lanc_bonif = ctk.StringVar(value=_MESES_BONIF[datetime.now().month - 1])
    ctk.CTkOptionMenu(f_lanc_bonif, values=_MESES_BONIF, variable=var_mes_lanc_bonif, width=130,
                      font=ctk.CTkFont(size=14)).pack(side="left", padx=(5, 5))
    var_ano_lanc_bonif = ctk.StringVar(value=str(datetime.now().year))
    ctk.CTkOptionMenu(f_lanc_bonif, values=_anos_permitidos_bonif(), variable=var_ano_lanc_bonif, width=90,
                      font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 15))
    ctk.CTkLabel(f_lanc_bonif, text="Valor (R$):", font=Tema.TEXTO).pack(side="left")
    entry_valor_bonif = ctk.CTkEntry(f_lanc_bonif, width=110, justify="center", placeholder_text="0,00",
                                     font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
    entry_valor_bonif.pack(side="left", padx=(5, 0))

    f_lanc_bonif2 = ctk.CTkFrame(card_lanc_bonif, fg_color="transparent")
    f_lanc_bonif2.pack(fill="x", padx=16, pady=(0, 12))
    ctk.CTkLabel(f_lanc_bonif2, text="Motivo:", font=Tema.TEXTO).pack(side="left")
    entry_motivo_bonif = ctk.CTkEntry(f_lanc_bonif2, placeholder_text="Ex.: meta de perfumaria batida",
                                      font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
    entry_motivo_bonif.pack(side="left", fill="x", expand=True, padx=(5, 15))
    lbl_feedback_bonif = ctk.CTkLabel(f_lanc_bonif2, text="", font=ctk.CTkFont(size=14, weight="bold"))
    lbl_feedback_bonif.pack(side="left", padx=(0, 10))

    ctk.CTkLabel(card_lanc_bonif,
                 text=(f"Aceita meses a partir de {inicio_comissao_automatica}. No DRE, a linha BONIFICAÇÕES soma "
                       "estes lançamentos com a bonificação dos Desafios do mês."),
                 font=ctk.CTkFont(size=12), text_color=Tema.CINZA_TEXTO).pack(anchor="w", padx=16, pady=(0, 10))

    # --- 2. Lançamentos do período ---
    f_filtro_bonif = ctk.CTkFrame(area_bonif, fg_color="transparent")
    f_filtro_bonif.pack(fill="x", padx=10, pady=(5, 5))
    ctk.CTkLabel(f_filtro_bonif, text="Ver lançamentos de:", font=Tema.LABEL).pack(side="left", padx=(6, 5))
    var_mes_filtro_bonif = ctk.StringVar(value=_MESES_BONIF[datetime.now().month - 1])
    ctk.CTkOptionMenu(f_filtro_bonif, values=["Ano inteiro"] + _MESES_BONIF, variable=var_mes_filtro_bonif,
                      width=140, font=ctk.CTkFont(size=14),
                      command=lambda _: atualizar_lista_bonificacoes()).pack(side="left", padx=5)
    var_ano_filtro_bonif = ctk.StringVar(value=str(datetime.now().year))
    ctk.CTkOptionMenu(f_filtro_bonif, values=_anos_permitidos_bonif(), variable=var_ano_filtro_bonif, width=90,
                      font=ctk.CTkFont(size=14), command=lambda _: atualizar_lista_bonificacoes()).pack(side="left", padx=5)
    lbl_total_bonif = ctk.CTkLabel(f_filtro_bonif, text="", font=Tema.LABEL, text_color=Tema.VERDE)
    lbl_total_bonif.pack(side="left", padx=20)
    frame_exportar_bonif = ctk.CTkFrame(f_filtro_bonif, fg_color="transparent")
    frame_exportar_bonif.pack(side="right")

    frame_tab_bonif = ctk.CTkFrame(area_bonif, corner_radius=0, height=330)
    frame_tab_bonif.pack(fill="x", padx=10, pady=(0, 6))
    frame_tab_bonif.pack_propagate(False)
    scroll_bonif = ttk.Scrollbar(frame_tab_bonif, orient="vertical")
    scroll_bonif.pack(side="right", fill="y")
    tabela_bonif = nova_tabela(frame_tab_bonif, columns=("id", "vendedora", "mes", "valor", "motivo", "lancado"),
                               show="headings", yscrollcommand=scroll_bonif.set)
    scroll_bonif.configure(command=tabela_bonif.yview)
    for c, t_, w in (("id", "ID", 60), ("vendedora", "Vendedora", 160), ("mes", "Mês ref.", 100),
                     ("valor", "Valor", 130), ("motivo", "Motivo", 340), ("lancado", "Lançado em", 175)):
        tabela_bonif.heading(c, text=t_)
        tabela_bonif.column(c, width=w, minwidth=w if c != "motivo" else 200,
                            anchor="w" if c in ("motivo", "vendedora") else "center", stretch=(c == "motivo"))
    tabela_bonif.pack(side="left", fill="both", expand=True)

    f_botoes_bonif = ctk.CTkFrame(area_bonif, fg_color="transparent")
    f_botoes_bonif.pack(pady=(4, 10))

    def _vendedoras_bonif():
        """Vendedoras ativas que podem receber bonificação (sem as de `excluidos_bonificacao`)."""
        return [n for n in obter_vendedores_ativos()
                if n != "Nenhum Vendedor Ativo" and normalizar_nome_vendedor(n) not in _excluidos_bonificacao]

    def atualizar_lista_bonificacoes(*args):
        ano = var_ano_filtro_bonif.get()
        mes_nome = var_mes_filtro_bonif.get()
        sql = "SELECT id, vendedor, mes, ano, valor, motivo, criado_em FROM bonificacoes WHERE ano = ?"
        params = [ano]
        if mes_nome != "Ano inteiro":
            sql += " AND mes = ?"
            params.append(f"{_MESES_BONIF.index(mes_nome) + 1:02d}")
        sql += " ORDER BY mes, vendedor, id"
        try:
            linhas = banco.consultar_todos(sql, params)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Bonificações")
            return
        for item in tabela_bonif.get_children():
            tabela_bonif.delete(item)
        total = 0.0
        for i, r in enumerate(linhas):
            total += r["valor"] or 0.0
            tabela_bonif.insert("", "end", iid=str(r["id"]), values=(
                r["id"], r["vendedor"], f"{r['mes']}/{r['ano']}", moeda_sempre(r["valor"]), r["motivo"] or "",
                r["criado_em"] or ""), tags=("linha_par" if i % 2 == 0 else "linha_impar",))
        if linhas:
            tabela_bonif.insert("", "end", iid="__total__", values=("", "TOTAL", "", moeda_sempre(total), "", ""),
                                tags=("tag_TOTAL",))
        periodo = ano if mes_nome == "Ano inteiro" else f"{mes_nome}/{ano}"
        lbl_total_bonif.configure(text=f"{len(linhas)} lançamento(s) · {moeda_sempre(total)} em {periodo}")

    def carregar_tela_bonificacoes():
        nomes = _vendedoras_bonif()
        menu_vend_bonif.configure(values=nomes or ["Nenhum Vendedor Ativo"])
        if var_vend_bonif.get() not in nomes:
            var_vend_bonif.set("Selecione")
        atualizar_lista_bonificacoes()

    def _validar_bonif(vendedora, mes_nome, ano, valor_txt):
        """Devolve (mes, valor) ou None (e mostra o motivo)."""
        if vendedora in ("Selecione", "Nenhum Vendedor Ativo", ""):
            return None, "⚠️ Escolha a vendedora!"
        if normalizar_nome_vendedor(vendedora) in _excluidos_bonificacao:
            return None, f"⚠️ {vendedora} não participa das bonificações."
        permitido, mes = _mes_permitido_bonif(mes_nome, ano)
        if not permitido:
            return None, f"⚠️ Só são aceitos meses a partir de {inicio_comissao_automatica}."
        valor = ler_valor_monetario(valor_txt)
        if valor is None or valor <= 0:
            return None, "⚠️ Digite um valor maior que zero!"
        return (mes, valor), None

    def salvar_bonificacao(event=None):
        vendedora = var_vend_bonif.get()
        ok, erro = _validar_bonif(vendedora, var_mes_lanc_bonif.get(), var_ano_lanc_bonif.get(), entry_valor_bonif.get())
        if erro:
            exibir_feedback(lbl_feedback_bonif, erro, Tema.VERMELHO, segundos=5)
            return
        mes, valor = ok
        ano = var_ano_lanc_bonif.get()
        if valor >= 1000 and not messagebox.askyesno(
                "Confirmar valor", f"Confirma a bonificação de {moeda_sempre(valor)} para {vendedora} ({mes}/{ano})?"):
            return
        try:
            banco.executar("INSERT INTO bonificacoes (vendedor, mes, ano, valor, motivo, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
                           (vendedora, mes, ano, valor, entry_motivo_bonif.get().strip().upper(),
                            datetime.now().strftime("%d/%m/%Y %H:%M")), commit=True)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Salvar Bonificação")
            return
        entry_valor_bonif.delete(0, "end")
        entry_motivo_bonif.delete(0, "end")
        # Mostra o período do lançamento na lista, para conferir na hora.
        var_mes_filtro_bonif.set(var_mes_lanc_bonif.get())
        var_ano_filtro_bonif.set(ano)
        atualizar_lista_bonificacoes()
        exibir_feedback(lbl_feedback_bonif, f"✔️ {moeda_sempre(valor)} para {vendedora} salvo!", Tema.VERDE)

    def _selecao_bonif():
        selecao = tabela_bonif.selection()
        if not selecao or selecao[0] == "__total__":
            messagebox.showwarning("Aviso", "Selecione uma bonificação na lista.")
            return None
        return int(selecao[0])

    def excluir_bonificacao():
        id_bonif = _selecao_bonif()
        if id_bonif is None:
            return
        v = tabela_bonif.item(str(id_bonif), "values")
        if not messagebox.askyesno("Confirmar", f"Excluir a bonificação de {v[3]} para {v[1]} ({v[2]})?"):
            return
        try:
            banco.executar("DELETE FROM bonificacoes WHERE id = ?", (id_bonif,), commit=True)
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Excluir Bonificação")
            return
        atualizar_lista_bonificacoes()

    def editar_bonificacao():
        id_bonif = _selecao_bonif()
        if id_bonif is None:
            return
        try:
            r = banco.consultar_um("SELECT vendedor, mes, ano, valor, motivo FROM bonificacoes WHERE id = ?", (id_bonif,))
        except ErroBancoDados:
            alerta_erro_banco("Erro ao Carregar Bonificação")
            return
        if r is None:
            return

        top = ctk.CTkToplevel(janela)
        top.title(f"Editar Bonificação ID {id_bonif}")
        top.geometry("430x470")
        top.grab_set()
        ctk.CTkLabel(top, text="Vendedora:", font=Tema.LABEL).pack(pady=(18, 0))
        nomes = _vendedoras_bonif()
        if r["vendedor"] not in nomes:
            nomes.append(r["vendedor"])  # vendedora desativada depois do lançamento
        var_v = ctk.StringVar(value=r["vendedor"])
        ctk.CTkOptionMenu(top, values=nomes, variable=var_v, width=220, font=ctk.CTkFont(size=14)).pack(pady=5)
        ctk.CTkLabel(top, text="Mês de referência:", font=Tema.LABEL).pack(pady=(10, 0))
        f_m = ctk.CTkFrame(top, fg_color="transparent")
        f_m.pack(pady=5)
        var_m = ctk.StringVar(value=_MESES_BONIF[int(r["mes"]) - 1])
        ctk.CTkOptionMenu(f_m, values=_MESES_BONIF, variable=var_m, width=130, font=ctk.CTkFont(size=14)).pack(side="left", padx=4)
        anos = _anos_permitidos_bonif()
        if r["ano"] not in anos:
            anos.append(r["ano"])
        var_a = ctk.StringVar(value=r["ano"])
        ctk.CTkOptionMenu(f_m, values=anos, variable=var_a, width=90, font=ctk.CTkFont(size=14)).pack(side="left", padx=4)
        ctk.CTkLabel(top, text="Valor (R$):", font=Tema.LABEL).pack(pady=(10, 0))
        e_val = ctk.CTkEntry(top, width=160, justify="center", font=ctk.CTkFont(size=15), corner_radius=Tema.RAIO_BOTAO)
        e_val.insert(0, f"{r['valor']:.2f}".replace(".", ","))
        e_val.pack(pady=5)
        ctk.CTkLabel(top, text="Motivo:", font=Tema.LABEL).pack(pady=(10, 0))
        e_mot = ctk.CTkEntry(top, width=340, font=ctk.CTkFont(size=14), corner_radius=Tema.RAIO_BOTAO)
        e_mot.insert(0, r["motivo"] or "")
        e_mot.pack(pady=5)
        lbl_erro = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color=Tema.VERMELHO)
        lbl_erro.pack()

        def _salvar(event=None):
            ok, erro = _validar_bonif(var_v.get(), var_m.get(), var_a.get(), e_val.get())
            if erro:
                lbl_erro.configure(text=erro)
                return
            mes, valor = ok
            try:
                banco.executar("UPDATE bonificacoes SET vendedor = ?, mes = ?, ano = ?, valor = ?, motivo = ? WHERE id = ?",
                               (var_v.get(), mes, var_a.get(), valor, e_mot.get().strip().upper(), id_bonif), commit=True)
            except ErroBancoDados:
                alerta_erro_banco("Erro ao Salvar Bonificação")
                return
            top.destroy()
            atualizar_lista_bonificacoes()

        e_val.bind("<Return>", _salvar)
        ctk.CTkButton(top, text="SALVAR ALTERAÇÕES", fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER,
                      font=ctk.CTkFont(size=16, weight="bold"), height=40, corner_radius=Tema.RAIO_BOTAO,
                      command=_salvar).pack(pady=15)

    ctk.CTkButton(f_lanc_bonif2, text="SALVAR BONIFICAÇÃO", font=ctk.CTkFont(size=15, weight="bold"), height=38,
                  fg_color=Tema.VERDE, hover_color=Tema.VERDE_HOVER, corner_radius=Tema.RAIO_BOTAO,
                  command=salvar_bonificacao).pack(side="right")
    entry_valor_bonif.bind("<Return>", salvar_bonificacao)
    entry_motivo_bonif.bind("<Return>", salvar_bonificacao)

    ctk.CTkButton(f_botoes_bonif, text="✏️ Editar Selecionada", font=ctk.CTkFont(size=15, weight="bold"), height=38,
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, corner_radius=Tema.RAIO_BOTAO,
                  command=editar_bonificacao).pack(side="left", padx=8)
    ctk.CTkButton(f_botoes_bonif, text="🗑️ Excluir Selecionada", font=ctk.CTkFont(size=15, weight="bold"), height=38,
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, corner_radius=Tema.RAIO_BOTAO,
                  command=excluir_bonificacao).pack(side="left", padx=8)

    def _exportar_bonif(tipo):
        mes_nome, ano = var_mes_filtro_bonif.get(), var_ano_filtro_bonif.get()
        periodo = ano if mes_nome == "Ano inteiro" else f"{mes_nome}_{ano}"
        if tipo == "excel":
            exportar_tabela_excel(tabela_bonif, f"bonificacoes_{periodo}", "Bonificações")
        else:
            exportar_tabela_pdf(tabela_bonif, f"bonificacoes_{periodo}", f"Bonificações - {periodo.replace('_', '/')}")

    ctk.CTkButton(frame_exportar_bonif, text="📊 Excel", font=ctk.CTkFont(size=13, weight="bold"), width=90, height=32,
                  fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: _exportar_bonif("excel")).pack(side="left", padx=5)
    ctk.CTkButton(frame_exportar_bonif, text="📄 PDF", font=ctk.CTkFont(size=13, weight="bold"), width=90, height=32,
                  fg_color=Tema.VERMELHO, hover_color=Tema.VERMELHO_HOVER, corner_radius=Tema.RAIO_BOTAO,
                  command=lambda: _exportar_bonif("pdf")).pack(side="left", padx=5)


    # =============================================================================
    # TELA 8: ÁREA DE GESTÃO (hub protegido por senha)
    # =============================================================================
    ctk.CTkLabel(tela_gestao, text="🔒 ÁREA DE GESTÃO", font=Tema.SUBTITULO).pack(pady=(40, 5))
    ctk.CTkLabel(tela_gestao, text="Selecione uma das telas abaixo:", font=Tema.LABEL,
                 text_color=Tema.CINZA_TEXTO).pack(pady=(0, 25))

    frame_cartoes_gestao = ctk.CTkFrame(tela_gestao, fg_color="transparent", corner_radius=0)
    frame_cartoes_gestao.pack(pady=10)

    _CARTOES_GESTAO = [
        ("📊 Dashboard BI", tela_dashboard),
        ("🏆 Desafios", tela_desafio),
        ("🎁 Bonificações", tela_bonificacoes),
        ("⚙️ Equipe", tela_equipe),
        ("📈 DRE Anual", tela_dre),
    ]
    for texto_cartao, tela_alvo in _CARTOES_GESTAO:
        ctk.CTkButton(frame_cartoes_gestao, text=texto_cartao, font=ctk.CTkFont(size=18, weight="bold"),
                      width=280, height=70, fg_color=Tema.AZUL, hover_color=Tema.AZUL_HOVER,
                      corner_radius=Tema.RAIO_BOTAO, command=lambda t=tela_alvo: mostrar_tela(t)).pack(pady=10)

    ctk.CTkButton(tela_gestao, text="🔒 Bloquear Área de Gestão", font=ctk.CTkFont(size=14, weight="bold"),
                  fg_color="transparent", border_width=2, border_color=Tema.VERMELHO, text_color=Tema.VERMELHO,
                  hover_color=("gray90", "gray20"), height=38, width=260, corner_radius=Tema.RAIO_BOTAO,
                  command=bloquear_area_gestao).pack(pady=(35, 10))


    # =============================================================================
    # 10. O CÉREBRO DO SISTEMA (TROCA DE TELAS)
    # =============================================================================
    TELAS = [tela_registrar, tela_historico, tela_dashboard, tela_diario, tela_equipe, tela_despesas, tela_dre,
             tela_gestao, tela_desafio, tela_bonificacoes]
    BOTOES_NAV = {}  # preenchido depois de criar os botões do menu lateral, na seção 11


    def _anos_distintos(consultas):
        """Recebe uma lista de (sql, params) e devolve os anos (AAAA) encontrados nos resultados."""
        anos = set()
        for sql, params in consultas:
            try:
                linhas = banco.consultar_todos(sql, params)
            except ErroBancoDados:
                continue
            for row in linhas:
                if row[0]:
                    ano, _ = ano_mes_de_data_flexivel(row[0])
                    if ano:
                        anos.add(ano)
        return sorted(anos, reverse=True)


    def _ano_padrao(anos):
        """Ano que a tela abre selecionado: o ANO VIGENTE, se houver dados nele.
        (Antes abria no ano mais recente com dados, que podia ser o ano que vem
        por causa de despesas parceladas ou parcelas de cartão.)"""
        atual = str(datetime.now().year)
        return atual if atual in anos else anos[0]

    def mostrar_tela(tela_escolhida):
        for tela in TELAS:
            tela.pack_forget()
        tela_escolhida.pack(fill="both", expand=True)
        _estado_gestao["tela_atual"] = tela_escolhida

        # O botão "🔒 Gestão" do menu lateral fica destacado tanto quando a
        # pessoa está no próprio hub (tela_gestao) quanto em qualquer uma das
        # telas protegidas abertas a partir dele (Dashboard, Equipe, etc.).
        tela_para_destaque = tela_gestao if tela_escolhida in TELAS_PROTEGIDAS else tela_escolhida
        for tela, btn in BOTOES_NAV.items():
            if tela is tela_para_destaque:
                btn.configure(fg_color=Tema.VERDE, text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=("black", "white"))

        ativos = obter_vendedores_ativos()
        todos = obter_todos_historico()

        if tela_escolhida == tela_registrar:
            menu_vendedor.configure(values=ativos)
            if var_vendedor.get() not in ativos:
                var_vendedor.set("Selecione")

        elif tela_escolhida == tela_historico:
            menu_filtro_h.configure(values=["Todos"] + todos)
            atualizar_historico()

        elif tela_escolhida == tela_dashboard:
            anos_disp = _anos_distintos([
                ("SELECT DISTINCT data_venda FROM vendas WHERE data_venda IS NOT NULL", ()),
                ("SELECT DISTINCT data_vencimento FROM vendas WHERE data_vencimento IS NOT NULL", ()),
            ])
            if not anos_disp:
                anos_disp = [datetime.now().strftime("%Y")]
            anos_disp.insert(0, "Todos")

            menu_ano_d.configure(values=anos_disp)
            if var_ano_d.get() not in anos_disp:
                # anos_disp = ["Todos", ano_mais_recente, ...] (ordem decrescente) --
                # prioriza o ano mais recente com dados (o ano vigente, na prática)
                # em vez de cair em "Todos" por padrão.
                var_ano_d.set(_ano_padrao(anos_disp[1:]) if len(anos_disp) > 1 else anos_disp[0])

            atualizar_checkboxes_vendedores()
            processar_dashboard()

        elif tela_escolhida == tela_diario:
            carregar_fechamento(manter_digitado=True)
            _ao_trocar_aba_caixa()

        elif tela_escolhida == tela_equipe:
            atualizar_lista_equipe()

        elif tela_escolhida == tela_desafio:
            carregar_desafio_gestao()
            _ao_trocar_aba_desafio()

        elif tela_escolhida == tela_bonificacoes:
            carregar_tela_bonificacoes()

        elif tela_escolhida == tela_despesas:
            anos_desp = _anos_distintos([("SELECT DISTINCT data_despesa FROM despesas WHERE data_despesa IS NOT NULL", ())])
            if not anos_desp:
                anos_desp = [datetime.now().strftime("%Y")]
            anos_desp.insert(0, "Todos")

            menu_ano_graf_desp.configure(values=anos_desp)
            if var_ano_graf_desp.get() not in anos_desp:
                # Mesmo raciocínio do Dashboard: prioriza o ano mais recente com
                # dados (o ano vigente) em vez de "Todos" por padrão.
                var_ano_graf_desp.set(_ano_padrao(anos_desp[1:]) if len(anos_desp) > 1 else anos_desp[0])

            atualizar_historico_despesas()
            processar_grafico_despesas()

        elif tela_escolhida == tela_dre:
            anos_dre_lista = _anos_distintos([
                ("SELECT DISTINCT data_despesa FROM despesas WHERE data_despesa IS NOT NULL", ()),
                ("SELECT DISTINCT data_venda FROM vendas WHERE data_venda IS NOT NULL", ()),
            ])
            if not anos_dre_lista:
                anos_dre_lista = [datetime.now().strftime("%Y")]

            menu_ano_dre.configure(values=anos_dre_lista)
            if var_ano_dre.get() not in anos_dre_lista:
                var_ano_dre.set(_ano_padrao(anos_dre_lista))

            processar_dre()


    # =============================================================================
    # 11. MENU LATERAL (BOTÕES DE NAVEGAÇÃO)
    # =============================================================================
    logo_label = ctk.CTkLabel(frame_menu_lateral, text=nome_sistema, font=ctk.CTkFont(size=24, weight="bold"))
    logo_label.pack(pady=(20, 5))
    sublogo_label = ctk.CTkLabel(frame_menu_lateral, text="Sistema ERP", font=ctk.CTkFont(size=14), text_color=Tema.CINZA_TEXTO)
    sublogo_label.pack(pady=(0, 20))

    # Itens "normais" do menu, sem senha -- cada um leva direto pra sua tela.
    _ITENS_MENU = [
        ("💰 Registrar Venda", tela_registrar),
        ("📜 Histórico", tela_historico),
        ("🧾 Fechamento de Caixa", tela_diario),
        ("💸 Despesas", tela_despesas),
    ]

    for texto_botao, tela_destino in _ITENS_MENU:
        botao = ctk.CTkButton(frame_menu_lateral, text=texto_botao, font=ctk.CTkFont(size=16, weight="bold"), height=55,
                               fg_color="transparent", text_color=("black", "white"), anchor="w",
                               corner_radius=Tema.RAIO_BOTAO, command=lambda t=tela_destino: mostrar_tela(t))
        botao.pack(fill="x", pady=2, padx=10)
        BOTOES_NAV[tela_destino] = botao

    # Item protegido por senha: agrupa Dashboard BI, Equipe, Desafio do Dia e
    # DRE Anual (Despesas fica no menu livre, de propósito). O comando não é `mostrar_tela` direto -- passa primeiro pelo
    # pedido de senha (só na 1ª vez, enquanto o programa estiver aberto).
    botao_gestao = ctk.CTkButton(frame_menu_lateral, text="🔒 Gestão", font=ctk.CTkFont(size=16, weight="bold"), height=55,
                                  fg_color="transparent", text_color=("black", "white"), anchor="w",
                                  corner_radius=Tema.RAIO_BOTAO, command=abrir_area_gestao)
    botao_gestao.pack(fill="x", pady=2, padx=10)
    BOTOES_NAV[tela_gestao] = botao_gestao


    # =============================================================================
    # 12. INICIALIZAÇÃO (dispara a tela inicial e entra no laço de eventos)
    # =============================================================================
    processar_grafico_despesas("")
    mostrar_tela(tela_registrar)
    janela.after(10_000, _verificar_bloqueio_automatico)

    if _gancho_de_teste is not None:
        _gancho_de_teste(locals())
        return  # nos testes automatizados não entramos no laço de eventos

    janela.mainloop()
