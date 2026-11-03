# =============================================================================
# NOVA INTERFACE — Vitrine (versão completa, em teste)
# =============================================================================
# Interface em HTML/CSS/JS (pasta web/) numa janela pywebview; banco e regras
# em Python (dados.py), iguais às do sistema atual (nucleo_pdv.py).
#
# BANCO OFICIAL: pasta local do PC (padrão C:\Vitrine\dados\<filial>.db), NUNCA no OneDrive.
# Mudar a pasta: C:\Vitrine\config.json {"pasta_dados": "...", "pasta_backup": "..."} ou --pasta-dados.
# Na 1ª vez, se o banco oficial não existe, o banco antigo (cosmeticos_vendas.db ao lado do programa, ou o
# escolhido) é MIGRADO por migrar.py (só leitura no original, conferência antes/depois, relatório em CSV).
#
# Não rode este arquivo direto: use o lançador da filial.
#   python demo_ui/nova_jardins.py                -> abre
#   ... --origem X.db                              -> migra a partir de X.db (se o oficial ainda não existe)
#   ... --banco-novo                               -> cria banco vazio (loja nova)
#   ... --banco X.db                               -> usa exatamente este arquivo (testes)
import argparse
import functools
import json
import os
import socket
import sqlite3
import sys
import threading
import time
from datetime import datetime

import dados as D
from estoque_dados import SITE_PRODUTOS
import exportar
import graficos
import migrar
import atualizador
import pedidos_dados
import sincro
from lojas import FILIAIS, NOMES_CURTOS

NOME_BANCO = "cosmeticos_vendas.db"  # nome do banco ANTIGO (origem da migração)
RAIZ_OFICIAL = r"C:\Vitrine"
MAX_ERROS_SENHA = 5
ESPERA_SENHA_S = 30
MSG_ERRO_INESPERADO = ("Aconteceu um erro inesperado, mas o programa não vai fechar. Os detalhes foram salvos no "
                       "arquivo 'erros_nova_interface.log', na pasta da cópia do banco.")


def _pasta_base():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _pasta_recursos():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


BASE = _pasta_base()


def _perfil():
    """perfil.json empacotado so no Setup de TESTE (raiz, Worker/chave de teste, canal, hash da senha). Oficial: nao existe."""
    try:
        with open(os.path.join(_pasta_recursos(), "perfil.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


PERFIL = _perfil()
if PERFIL.get("raiz"):
    RAIZ_OFICIAL = PERFIL["raiz"]
PASTA_WEB = os.path.join(_pasta_recursos(), "web")


# --- E8: portão WebView2 (sem ele o pywebview cairia no motor do Internet Explorer) ---
def webview2_instalado():
    import winreg
    guid = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    chaves = [(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
              (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
              (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}")]
    versao = None
    for raiz, caminho in chaves:
        try:
            with winreg.OpenKey(raiz, caminho) as k:
                pv, _ = winreg.QueryValueEx(k, "pv")
                if pv and pv != "0.0.0.0":
                    versao = pv
                    break
        except OSError:
            continue
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full") as k:
            dotnet_ok = winreg.QueryValueEx(k, "Release")[0] >= 394802
    except OSError:
        dotnet_ok = False
    return versao, dotnet_ok


def avisar_e_sair(titulo, texto):
    import tkinter
    from tkinter import messagebox
    raiz = tkinter.Tk()
    raiz.withdraw()
    messagebox.showerror(titulo, texto)
    raiz.destroy()
    sys.exit(1)


# --- cópia do banco ------------------------------------------------------------
def achar_origem(origem_arg):
    if origem_arg:
        return os.path.abspath(origem_arg)
    for pasta in (BASE, os.path.dirname(BASE), os.path.dirname(os.path.dirname(BASE))):
        candidato = os.path.join(pasta, NOME_BANCO)
        if os.path.exists(candidato):
            return candidato
    return None


def config_local():
    """C:\\Vitrine\\config.json (opcional): pasta_dados, pasta_backup."""
    try:
        with open(os.path.join(RAIZ_OFICIAL, "config.json"), encoding="utf-8") as f:
            return {**PERFIL, **json.load(f)}
    except (OSError, ValueError):
        return dict(PERFIL)


def no_onedrive(caminho):
    return "onedrive" in os.path.abspath(caminho).lower()


def escolher_origem():
    import tkinter
    from tkinter import filedialog
    raiz = tkinter.Tk()
    raiz.withdraw()
    origem = filedialog.askopenfilename(
        title="Escolha o cosmeticos_vendas.db ANTIGO para migrar (o original não é alterado)",
        filetypes=[("Banco do sistema", "*.db")])
    raiz.destroy()
    return os.path.abspath(origem) if origem else None


def preparar_banco(filial, banco, origem_arg, banco_novo, nuvem=False):
    """Garante que `banco` existe. Devolve texto de aviso para a tela (ou '').
    nuvem=True (computador ligado à nuvem, t105): sem banco antigo nesta máquina, cria vazio e baixa o histórico da loja."""
    if os.path.exists(banco):
        return ""
    if banco_novo:
        return "Banco novo e vazio criado."
    if nuvem and not achar_origem(origem_arg):
        return ""
    origem = achar_origem(origem_arg) or escolher_origem()
    if not origem:
        sys.exit(0)
    r = migrar.migrar(origem, banco, filial)
    if not r["ok"]:
        avisar_e_sair("Migração do banco", r["erro"] + "\n\nRelatório: " + str(r.get("relatorio", "")))
    return (f"Banco antigo migrado para {banco}: {r['vendas']} vendas, {r['linhas']} conferências iguais. "
            f"Relatório: {r['relatorio']}. O banco antigo não foi alterado.")


# --- API chamada pelo JavaScript ------------------------------------------------
def _api(protegido=False, trava=True):
    """Todo método da API passa por aqui: uma chamada por vez, erro nunca derruba a janela,
    e as telas da Gestão só respondem com a Gestão desbloqueada."""
    def deco(f):
        @functools.wraps(f)
        def envolvido(self, *args, **kwargs):
            if protegido and not self._gestao_aberta:
                return {"ok": False, "bloqueado": True, "erro": "🔒 A Área de Gestão está bloqueada."}
            try:
                if trava:
                    with self._trava:
                        return f(self, *args, **kwargs)
                return f(self, *args, **kwargs)
            except D.ErroBanco:
                return {"ok": False, "erro": D.MSG_ERRO_BANCO}
            except Exception as e:  # noqa: BLE001
                self._d.registrar_erro(f"API {f.__name__}", e)
                return {"ok": False, "erro": MSG_ERRO_INESPERADO}
        return envolvido
    return deco


class Api:
    def __init__(self, dados, filial, info):
        self._d = dados
        self._f = filial
        self._info = info
        self._trava = threading.RLock()
        self._gestao_aberta = False
        self._janela = None
        self._erros_senha = 0
        self._bloqueado_ate = 0
        self._atu = None
        self._sync = None
        self._pasta_backup = None
        self._lojas = {}  # codigo -> (filial, dados, sincronizador): todas as lojas abertas neste computador (t105)
        self._arq_ultima = None  # arquivo que guarda a última loja usada neste PC (só destaque na tela inicial)

    # --- comum -------------------------------------------------------------------
    @_api()
    def iniciar(self):
        return {"ok": True, "loja": self._f.nome_loja, "hoje": datetime.now().strftime("%d/%m/%Y"),
                "ano": str(datetime.now().year), "mes": D.MESES[datetime.now().month - 1],
                "vendedores": self._d.vendedores_ativos(), "pagamentos_botoes": D.PAGAMENTOS_BOTOES,
                "pagamentos": D.PAGAMENTOS, "produtos": D.PRODUTOS, "site_produtos": SITE_PRODUTOS, "tipos_despesa": D.TIPOS_DESPESA,
                "meses": D.MESES, "minutos_bloqueio": _minutos_bloqueio(self._f.minutos_bloqueio_gestao),
                "meta_desafio": D.META_DIARIA_DESAFIO, "inicio_comissao": self._f.inicio_comissao_automatica,
                "computador": socket.gethostname(), "filial_codigo": self._f.codigo,
                "estoque_outra": self._d.filial_outra, "ultima_loja": self._ultima_loja(),
                "versao": self._atu.estado["versao"] if self._atu else "", **self._info}

    # --- atualização automática ---------------------------------------------------
    @_api(trava=False)
    def atualizacao_estado(self):
        return {"ok": True, **(self._atu.estado if self._atu else {"ativo": False, "status": "desativado"})}

    @_api(trava=False)
    def atualizacao_aplicar(self):
        """Backup conferido do banco -> fecha o banco -> Velopack troca os arquivos e reabre. A tela já recusou se
        havia venda em andamento; aqui só segue se nenhuma gravação estiver em curso."""
        if not self._atu or self._atu.estado.get("status") != "pronta":
            return {"ok": False, "erro": "Não há atualização pronta."}
        if not self._trava.acquire(timeout=5):
            return {"ok": False, "erro": "O sistema está gravando algo agora. Tente de novo em instantes."}
        try:
            copia = self._d.backup_antes_de_atualizar()
            self._d.auditar("ATUALIZOU", f"{self._atu.estado['versao']} -> {self._atu.estado['nova']} (backup {copia})")
            self._d.fechar()
            self._atu.aplicar()
        except Exception as e:  # noqa: BLE001
            self._d.registrar_erro("aplicar atualização", e)
            return {"ok": False, "erro": "Não foi possível atualizar agora. O sistema segue como está; nada foi perdido."}
        finally:
            self._trava.release()
        return {"ok": True}

    @_api()
    def vendedores(self):
        return {"ok": True, "ativos": self._d.vendedores_ativos(), "todos": self._d.todos_historico()}

    @_api(trava=False)
    def exportar(self, tipo, p):
        import webview
        if not p.get("linhas"):
            return {"ok": False, "erro": "Não há dados para exportar nesta tela."}
        ext = ".xlsx" if tipo == "excel" else ".pdf"
        filtro = ("Planilha Excel (*.xlsx)",) if tipo == "excel" else ("Documento PDF (*.pdf)",)
        escolha = self._janela.create_file_dialog(webview.FileDialog.SAVE, save_filename=p["nome"] + ext,
                                                  file_types=filtro)
        if not escolha:
            return {"ok": False, "cancelado": True}
        caminho = escolha if isinstance(escolha, str) else escolha[0]
        if not caminho.lower().endswith(ext):
            caminho += ext
        try:
            if tipo == "excel":
                exportar.excel(caminho, p["colunas"], p["linhas"], p.get("titulo_excel") or p.get("titulo") or p["nome"])
            else:
                exportar.pdf(caminho, p["colunas"], p["linhas"], p.get("titulo") or p["nome"])
        except Exception as e:  # noqa: BLE001
            self._d.registrar_erro(f"exportar {tipo}", e)
            return {"ok": False, "erro": f"Não foi possível salvar o arquivo {'Excel' if tipo == 'excel' else 'PDF'}. "
                                         "Verifique se ele não está aberto em outro programa."}
        return {"ok": True, "mensagem": f"Relatório salvo em: {caminho}"}

    # --- estoque (F6) ---------------------------------------------------------------
    @_api()
    def bipar(self, codigo):
        return self._d.buscar_codigo(codigo)

    @_api()
    def estoque_consultar(self, busca="", so_alerta=False):
        return self._d.consultar_estoque(busca, so_alerta)

    @_api()
    def estoque_cadastrar(self, p):
        return self._d.cadastrar_produto(p.get("codigo"), p.get("nome"), p.get("categoria"), p.get("preco"))

    @_api()
    def estoque_editar(self, p):
        return self._d.editar_produto(p.get("codigo"), p.get("nome"), p.get("categoria"), p.get("preco"), p.get("ativo", True), p.get("site_id"), p.get("site"))

    @_api(trava=False)
    def sync_estado(self):
        return {"ok": True, **(self._sync.estado if self._sync else {"configurado": False, "status": "desligado"})}

    # --- várias lojas no mesmo computador (t105) ------------------------------------
    @_api(trava=False)
    def lojas(self):
        """Lojas que este computador abre (todas: decisão do Alisson, sem login) e o estado de cada réplica."""
        return {"ok": True, "atual": self._f.codigo, "lojas": [
            {"codigo": c, "nome": NOMES_CURTOS.get(c, c.capitalize()), "nome_loja": f.nome_loja,
             "sync": dict(s.estado) if s else {"configurado": False, "status": "desligado"}}
            for c, (f, d, s) in self._lojas.items()]}

    def _ultima_loja(self):
        try:
            with open(self._arq_ultima, encoding="utf-8") as f:
                return f.read().strip()
        except (OSError, TypeError):
            return ""

    @_api()
    def inicio(self):
        """Voltar à tela inicial: a Gestão fecha (pede a senha de novo)."""
        self._gestao_aberta = False
        return {"ok": True}

    @_api()
    def trocar_loja(self, codigo):
        """Troca a loja aberta na tela. As duas continuam sincronizando em 2º plano. A Gestão fecha (pede a senha de novo)."""
        if codigo not in self._lojas:
            return {"ok": False, "erro": "Loja não disponível neste computador."}
        try:  # lembra só para destacar na tela inicial; falhar aqui nunca impede de entrar
            with open(self._arq_ultima, "w", encoding="utf-8") as f:
                f.write(codigo)
        except (OSError, TypeError):
            pass
        if codigo == self._f.codigo:
            return {"ok": True}
        self._f, self._d, self._sync = self._lojas[codigo]
        self._gestao_aberta = False
        self._d.auditar("TROCOU_LOJA", f"abriu a loja {codigo}")
        if self._janela:
            try:
                self._janela.set_title(("VITRINE TESTE - " if PERFIL.get("teste") else "") + self._f.nome_loja)
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True}

    # --- pedidos online -----------------------------------------------------------
    @_api()
    def pedidos_listar(self, grupo=""):
        return self._d.pedidos_listar(grupo)

    @_api(trava=False)
    def pedidos_resumo(self):
        return self._d.pedidos_resumo()

    @_api()
    def pedidos_vistos(self):
        return self._d.pedidos_marcar_vistos()

    @_api(trava=False)
    def pedido_avancar(self, pedido_id, novo_status):
        """Muda o status no portão (precisa de internet). A baixa do estoque acontece quando 'entregue' volta pela sincronização."""
        if not self._sync or not self._sync.estado.get("configurado"):
            return {"ok": False, "erro": "A nuvem não está configurada neste computador."}
        ok, erro = self._sync.mudar_pedido(str(pedido_id), str(novo_status))
        return {"ok": True} if ok else {"ok": False, "erro": erro}

    @_api(trava=False)
    def bairros_listar(self):
        if not self._sync or not self._sync.estado.get("configurado"):
            return {"ok": False, "erro": "A nuvem não está configurada neste computador."}
        lista, erro = self._sync.bairros_entrega()
        if lista is None:
            return {"ok": False, "erro": erro}
        return {"ok": True, "bairros": [{"bairro": b["bairro"], "taxa": f"{b['taxa_cent'] / 100:.2f}".replace(".", ","),
                                         "prazo": b.get("prazo_txt") or "", "ativo": bool(b["ativo"])} for b in lista]}

    @_api(trava=False)
    def bairros_salvar(self, bairros):
        """Grava bairros e taxas. O portão não apaga bairro: para tirar da lista do site, desmarque 'Ativo'."""
        if not self._sync or not self._sync.estado.get("configurado"):
            return {"ok": False, "erro": "A nuvem não está configurada neste computador."}
        lista, erro = pedidos_dados.validar_bairros(bairros, D.ler_valor_monetario)
        if lista is None:
            return {"ok": False, "erro": erro}
        ok, erro = self._sync.gravar_bairros(lista)
        if ok:
            self._d.auditar("bairros de entrega", f"{len(lista)} bairro(s) gravado(s)")
        return {"ok": True, "total": len(lista)} if ok else {"ok": False, "erro": erro}

    @_api(trava=False)
    def pedido_whatsapp(self, pedido_id):
        """Abre o WhatsApp Web do próprio usuário com a mensagem pronta; quem aperta enviar é a pessoa da loja."""
        import urllib.parse
        import webbrowser
        r = self._d.con.execute("SELECT dados FROM pedidos_online WHERE id = ?", (str(pedido_id),)).fetchone()
        if not r:
            return {"ok": False, "erro": "Pedido não encontrado."}
        p = json.loads(r[0])
        txt = f"Olá, {p['cliente_nome']}! Aqui é da Vitrine, sobre o seu pedido {p['id']}."
        fone = "".join(c for c in p["cliente_whatsapp"] if c.isdigit())
        fone = fone[2:] if len(fone) > 11 and fone.startswith("55") else fone
        webbrowser.open("https://wa.me/55" + fone + "?text=" + urllib.parse.quote(txt))
        return {"ok": True}

    @_api()
    def estoque_movimentar(self, tipo, itens, obs=""):
        return self._d.movimentar(tipo, itens, obs)

    @_api()
    def estoque_minimo(self, codigo, minimo):
        return self._d.definir_minimo(codigo, minimo)

    @_api()
    def estoque_historico(self, codigo):
        return self._d.historico_movimentos(codigo)

    @_api()
    def estoque_novo_codigo(self):
        return {"ok": True, "codigo": self._d.novo_codigo_interno()}

    @_api()
    def transf_pedir(self, codigo, qtd, obs=""):
        return self._d.pedir_transferencia(codigo, qtd, obs)

    @_api()
    def transf_listar(self, status=""):
        return self._d.listar_transferencias(status)

    @_api()
    def transf_enviar(self, tid):
        return self._d.enviar_transferencia(tid)

    @_api()
    def transf_receber(self, tid):
        return self._d.receber_transferencia(tid)

    @_api()
    def transf_cancelar(self, tid):
        return self._d.cancelar_transferencia(tid)

    @_api(trava=False)
    def etiquetas(self, pedidos):
        import webview
        escolha = self._janela.create_file_dialog(webview.FileDialog.SAVE, save_filename="etiquetas.pdf",
                                                  file_types=("Documento PDF (*.pdf)",))
        if not escolha:
            return {"ok": False, "cancelado": True}
        caminho = escolha if isinstance(escolha, str) else escolha[0]
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        with self._trava:
            try:
                return self._d.etiquetas_pdf(caminho, pedidos)
            except OSError as e:
                self._d.registrar_erro("etiquetas", e)
                return {"ok": False, "erro": "Não foi possível salvar o PDF. Verifique se ele não está aberto em outro programa."}

    # --- venda -------------------------------------------------------------------
    @_api()
    def registrar_venda(self, p):
        return self._d.registrar_venda(p.get("vendedor"), p.get("produto"), p.get("pagamento"), p.get("valor"),
                                       p.get("data"), itens=p.get("itens") or None)

    @_api()
    def interpretar_valor(self, texto):
        v = D.ler_valor_monetario(texto)
        if v is None:
            return {"ok": False}
        return {"ok": True, "formatado": D.moeda_sempre(v), "zero": v == 0}

    @_api()
    def vendas_do_dia(self, data):
        return self._d.vendas_do_dia(data)

    # --- histórico ---------------------------------------------------------------
    @_api()
    def historico_vendas(self, vendedor, ordem, data):
        return self._d.historico_vendas(vendedor, ordem, data)

    @_api()
    def obter_venda(self, id_venda):
        return self._d.obter_venda(id_venda)

    @_api()
    def editar_venda(self, p):
        return self._d.editar_venda(p["id"], p.get("vendedor"), p.get("produto"), p.get("pagamento"), p.get("valor"))

    @_api()
    def excluir_venda(self, id_venda):
        return self._d.excluir_venda(id_venda)

    # --- caixa -------------------------------------------------------------------
    @_api()
    def carregar_fechamento(self, data):
        r = self._d.carregar_fechamento(data)
        if r["ok"]:
            horas, ranking = self._d.dados_graficos_dia(r["data"])
            r["grafico_horas"] = graficos.barras_horario(horas, "Vendas por horário")
            r["grafico_ranking"] = graficos.barras_ranking(ranking, "Ranking da equipe no dia")
        return r

    @_api()
    def calcular_caixa(self, p):
        return self._d.calcular_caixa(p.get("dinheiro"), p.get("qtd_dinheiro"), p.get("suprimento"), p.get("sangria"),
                                      p.get("troco"), p.get("contado"))

    @_api()
    def adicionar_movimento(self, p):
        return self._d.adicionar_movimento(p.get("data"), p.get("tipo"), p.get("valor"), p.get("motivo"))

    @_api()
    def remover_movimento(self, id_mov):
        return self._d.remover_movimento(id_mov)

    @_api()
    def salvar_fechamento(self, p):
        return self._d.salvar_fechamento(p.get("data"), p.get("troco"), p.get("contado"), p.get("observacao"),
                                         bool(p.get("confirmou_vazio")))

    @_api()
    def exportacao_fechamento(self, p):
        return self._d.exportacao_fechamento(p.get("data"), p.get("troco"), p.get("contado"), p.get("observacao"))

    @_api()
    def anos_fechamentos(self):
        return {"ok": True, "anos": self._d.anos_fechamentos()}

    @_api()
    def historico_fechamentos(self, mes, ano):
        return self._d.historico_fechamentos(mes, ano)

    @_api()
    def relatorio_diario(self, data, produto, pagamento):
        r = self._d.relatorio_diario(data, produto, pagamento)
        if r["ok"]:
            r["grafico_horas"] = graficos.barras_horario(r.pop("horas"), f"Vendas por Horário ({produto} / {pagamento})",
                                                         rotulos=True, rotulo_y="Faturamento (R$)")
            r["grafico_ranking"] = graficos.barras_ranking(r.pop("ranking"), f"Ranking da Equipe ({produto} / {pagamento})",
                                                           vazio="Sem vendas para os filtros selecionados.")
        return r

    # --- despesas ----------------------------------------------------------------
    @_api()
    def salvar_despesa(self, p):
        return self._d.salvar_despesa(p.get("descricao"), p.get("valor"), p.get("parcelas"), p.get("data"),
                                      p.get("tipo"), bool(p.get("confirmou")))

    @_api()
    def historico_despesas(self, data):
        return self._d.historico_despesas(data)

    @_api()
    def obter_despesa(self, id_desp):
        return self._d.obter_despesa(id_desp)

    @_api()
    def editar_despesa(self, p):
        return self._d.editar_despesa(p["id"], p.get("descricao"), p.get("valor"), p.get("tipo"), p.get("data"),
                                      bool(p.get("confirmou")))

    @_api()
    def excluir_despesa(self, id_desp):
        return self._d.excluir_despesa(id_desp)

    @_api()
    def anos_despesas(self):
        anos, padrao = self._d.anos_despesas()
        return {"ok": True, "anos": anos, "padrao": padrao}

    @_api()
    def grafico_despesas(self, ano, tipos):
        r = self._d.grafico_despesas(ano, tipos)
        r["grafico"] = graficos.despesas_mensais(r.pop("series"), r["titulo_grafico"])
        return r

    # --- gestão (senha) ------------------------------------------------------------
    @_api()
    def senha_definida(self):
        return {"ok": True, "definida": self._d.senha_definida()}

    @_api()
    def entrar_gestao(self, senha):
        agora = time.time()
        if agora < self._bloqueado_ate:
            return {"ok": False, "erro": f"Muitas tentativas. Aguarde {int(self._bloqueado_ate - agora) + 1} segundos."}
        if self._d.verificar_senha(senha):
            self._gestao_aberta = True
            self._erros_senha = 0
            return {"ok": True}
        self._erros_senha += 1
        if self._erros_senha >= MAX_ERROS_SENHA:
            self._erros_senha = 0
            self._bloqueado_ate = agora + ESPERA_SENHA_S
        return {"ok": False, "erro": "Senha incorreta. Tente novamente."}

    @_api(protegido=True)
    def auditoria_listar(self, busca=""):
        return self._d.auditoria_listar(busca)

    @_api(protegido=True)
    def trocar_senha(self, atual, nova, confirmacao):
        r = self._d.trocar_senha(atual, nova, confirmacao)
        if r.get("ok"):  # senha unica da Gestao: grava o mesmo hash na réplica de cada loja deste computador
            h = self._d.cfg_get("senha_gestao_hash")
            for _f, d, _s in self._lojas.values():
                if d is not self._d:
                    d.cfg_set("senha_gestao_hash", h)
        return r

    @_api()
    def sair_gestao(self):
        self._gestao_aberta = False
        return {"ok": True}

    @_api(protegido=True)
    def dashboard_inicio(self):
        anos, padrao = self._d.anos_dashboard()
        return {"ok": True, "anos": anos, "padrao": padrao, "todos": self._d.todos_historico(),
                "ativos": self._d.vendedores_ativos(), "cores": self._d.cores_vendedores()}

    @_api(protegido=True)
    def dashboard(self, ano, vendedores):
        r = self._d.dashboard(ano, vendedores)
        for aba in r["abas"]:
            aba["grafico"] = graficos.linhas_mensais(aba.pop("series"), aba["titulo_grafico"])
        return r

    @_api(protegido=True)
    def listar_equipe(self):
        return self._d.listar_equipe()

    @_api(protegido=True)
    def adicionar_vendedor(self, nome):
        return self._d.adicionar_vendedor(nome)

    @_api(protegido=True)
    def desativar_vendedor(self, id_vend):
        return self._d.desativar_vendedor(id_vend)

    @_api(protegido=True)
    def carregar_desafio(self, data):
        return self._d.carregar_desafio(data)

    @_api(protegido=True)
    def salvar_desafio(self, data, produto):
        return self._d.salvar_desafio(data, produto)

    @_api(protegido=True)
    def excluir_desafio(self, data):
        return self._d.excluir_desafio(data)

    @_api(protegido=True)
    def salvar_quantidades_desafio(self, desafio_id, quantidades):
        return self._d.salvar_quantidades_desafio(desafio_id, quantidades)

    @_api(protegido=True)
    def anos_desafio(self):
        return {"ok": True, "anos": self._d.anos_desafio()}

    @_api(protegido=True)
    def conclusao_mensal(self, mes, ano):
        return self._d.conclusao_mensal(mes, ano)

    @_api(protegido=True)
    def participantes_desafio(self):
        return self._d.participantes_desafio()

    @_api(protegido=True)
    def alterar_participacao(self, id_vend, participa):
        return self._d.alterar_participacao(id_vend, participa)

    @_api(protegido=True)
    def bonificacoes_inicio(self):
        return {"ok": True, "vendedoras": self._d.vendedoras_bonif(), "anos": self._d.anos_permitidos_bonif()}

    @_api(protegido=True)
    def listar_bonificacoes(self, mes, ano):
        return self._d.listar_bonificacoes(mes, ano)

    @_api(protegido=True)
    def salvar_bonificacao(self, p):
        return self._d.salvar_bonificacao(p.get("vendedora"), p.get("mes"), p.get("ano"), p.get("valor"),
                                          p.get("motivo"), bool(p.get("confirmou")))

    @_api(protegido=True)
    def obter_bonificacao(self, id_bonif):
        return self._d.obter_bonificacao(id_bonif)

    @_api(protegido=True)
    def editar_bonificacao(self, p):
        return self._d.editar_bonificacao(p["id"], p.get("vendedora"), p.get("mes"), p.get("ano"), p.get("valor"),
                                          p.get("motivo"))

    @_api(protegido=True)
    def excluir_bonificacao(self, id_bonif):
        return self._d.excluir_bonificacao(id_bonif)

    @_api(protegido=True)
    def anos_dre(self):
        anos, padrao = self._d.anos_dre()
        return {"ok": True, "anos": anos, "padrao": padrao}

    @_api(protegido=True)
    def dre(self, ano):
        r = self._d.dre(ano)
        r["grafico"] = graficos.dre(r.pop("series"), r["titulo_grafico"])
        return r


def _senha_do_perfil(d):
    """Setup de TESTE: grava so o HASH da senha da Gestao (veio no perfil), se o banco ainda nao tem senha."""
    h = PERFIL.get("senha_gestao_hash")
    if h and not d.senha_definida():
        d.cfg_set("senha_gestao_hash", h)


def main(filial, argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--origem", help="banco ANTIGO a migrar (só leitura), se o oficial ainda não existe")
    ap.add_argument("--banco", help="usa exatamente este arquivo (testes); padrão: <pasta de dados>\\<filial>.db")
    ap.add_argument("--pasta-dados", help=r"padrão: C:\Vitrine\dados")
    ap.add_argument("--pasta-backup", help=r"cópia datada extra; padrão: C:\Vitrine\backup_extra")
    ap.add_argument("--banco-novo", action="store_true", help="cria banco vazio se não existir (loja nova)")
    args = ap.parse_args(argv)

    versao, dotnet_ok = webview2_instalado()
    if not versao or not dotnet_ok:
        falta = "o Microsoft Edge WebView2 Runtime" if not versao else "o .NET Framework 4.6.2 ou mais novo"
        avisar_e_sair("Componente do Windows faltando",
                      f"Este computador não tem {falta}, que a nova interface precisa para abrir.\n\n"
                      "Nada foi alterado. Use o sistema atual normalmente e avise o suporte.")

    cfg = config_local()
    pasta_dados = args.pasta_dados or os.environ.get("VITRINE_DADOS") or cfg.get("pasta_dados") or \
        os.path.join(RAIZ_OFICIAL, "dados")
    pasta_backup = args.pasta_backup or cfg.get("pasta_backup") or os.path.join(RAIZ_OFICIAL, "backup_extra")
    banco = os.path.abspath(args.banco or os.path.join(pasta_dados, f"{filial.codigo}.db"))
    if no_onedrive(banco):
        avisar_e_sair("Pasta não permitida", f"O banco não pode ficar no OneDrive ({banco}): o OneDrive corrompe "
                      "banco de dados. Use uma pasta local, como C:\\Vitrine\\dados. Nada foi alterado.")
    url_nuvem = os.environ.get("VITRINE_PORTAO_URL") or cfg.get("portao_url")
    chave_nuvem = os.environ.get("VITRINE_PORTAO_CHAVE") or cfg.get("portao_chave")
    nuvem = bool(url_nuvem and chave_nuvem) and not args.banco
    if PERFIL:
        os.makedirs(os.path.dirname(banco), exist_ok=True)
    aviso = preparar_banco(filial, banco, args.origem, args.banco_novo, nuvem)

    conflitos = D.copias_de_conflito(banco)

    import webview  # só depois do portão E8

    try:
        filial_dados = D.Dados(banco, filial)
    except D.FilialDiferente as e:
        avisar_e_sair("Banco de outra filial", f"{e}\n\nNada foi alterado.")
    _senha_do_perfil(filial_dados)
    bk = filial_dados.backup_diario(pasta_backup)
    aviso = " ".join(x for x in [aviso] + bk["avisos"] if x)
    filial_dados.auditar("ABRIU", f"banco {banco}")
    api = Api(filial_dados, filial, {"banco": banco, "conflitos": conflitos, "aviso": aviso,
              # testes automáticos e a bateria não passam pela tela inicial
              "sem_inicio": bool(os.environ.get("VITRINE_SEM_INICIO"))})
    api._arq_ultima = os.path.join(pasta_dados, "ultima_loja.txt")
    janela_fechar_extra = []
    _backup_a_cada_hora(api, pasta_backup)
    api._atu = atualizador.Atualizador(filial.codigo, cfg, filial_dados.registrar_erro)
    api._atu.iniciar_laco()
    arquivo_disp = os.path.join(os.path.dirname(banco), "dispositivo.json")  # chave própria deste computador (automática)

    def sincronizador(caminho, codigo, d, intervalo=30):
        return sincro.Sincronizador(caminho, codigo, url_nuvem, chave_nuvem, versao=api._atu.estado["versao"], intervalo=intervalo,
                                    registrar_erro=d.registrar_erro, arquivo_disp=arquivo_disp if nuvem else None)
    api._sync = sincronizador(banco, filial.codigo, filial_dados)
    api._lojas[filial.codigo] = (filial, filial_dados, api._sync)
    # As outras lojas: réplica completa em <pasta de dados>\<loja>.db, baixada da nuvem (sem nuvem, só a loja deste PC).
    for codigo, f_outra in (FILIAIS.items() if nuvem else []):
        if codigo == filial.codigo:
            continue
        caminho = os.path.join(os.path.dirname(banco), f"{codigo}.db")
        try:
            d_outra = D.Dados(caminho, f_outra)
        except Exception as e:  # noqa: BLE001  -- a loja deste PC abre mesmo se a outra réplica falhar
            filial_dados.registrar_erro(f"abrir réplica {codigo}", e)
            continue
        _senha_do_perfil(d_outra)
        d_outra.backup_diario(pasta_backup)
        # t139: a outra loja só para consulta: puxa a cada 2 min (venda feita aqui nela continua subindo na hora)
        api._lojas[codigo] = (f_outra, d_outra, sincronizador(caminho, codigo, d_outra, intervalo=120))
        janela_fechar_extra.append(d_outra.fechar)
    for _f, _d, s in api._lojas.values():
        s.iniciar_laco()  # segundo plano: a tela nunca espera a rede
    if os.environ.get("VITRINE_TESTE_APLICAR"):  # só para testes automáticos: clica "Atualizar agora" sozinho
        threading.Thread(target=_teste_aplicar, args=(api,), daemon=True).start()
    janela = webview.create_window(
        ("VITRINE TESTE - " if PERFIL.get("teste") else "") + filial.nome_loja, url=os.path.join(PASTA_WEB, "index.html"),
        js_api=api, width=1366, height=768, min_size=(1100, 650), background_color="#F3F4F1")
    api._janela = janela
    janela.events.closed += filial_dados.fechar
    for fechar in janela_fechar_extra:
        janela.events.closed += fechar

    janela.events.loaded += lambda: _conferir_motor(janela)
    webview.start(gui="edgechromium", private_mode=True)


def _minutos_bloqueio(padrao):
    """Só para teste: VITRINE_BLOQUEIO_SEG troca os 5 min por N segundos. Sem a variável, vale o padrão."""
    try:
        return float(os.environ["VITRINE_BLOQUEIO_SEG"]) / 60
    except (KeyError, ValueError):
        return padrao


def _teste_aplicar(api):
    while True:
        time.sleep(3)
        if api._atu.estado.get("status") == "pronta":
            api._d.registrar_erro("TESTE aplicar (não é erro)", Exception(str(api.atualizacao_aplicar())))
            return


def _backup_a_cada_hora(api, pasta_backup):
    """O PC fica ligado dias seguidos: a cada hora confere se já existe o backup de hoje (só faz se faltar)."""
    def laco():
        while True:
            time.sleep(3600)
            try:
                with api._trava:
                    for _f, d, _s in (api._lojas.values() or [(None, api._d, None)]):
                        d.backup_diario(pasta_backup)
            except Exception as e:  # noqa: BLE001
                api._d.registrar_erro("backup horário", e)
    threading.Thread(target=laco, daemon=True).start()


def _conferir_motor(janela):
    """E8: se por qualquer motivo não carregou o motor Edge, não deixa usar."""
    try:
        ua = janela.evaluate_js("navigator.userAgent") or ""
    except Exception:
        ua = ""
    if "Edg/" not in ua:
        try:
            janela.evaluate_js("alert('A nova interface precisa do Microsoft Edge WebView2, que nao abriu neste "
                               "computador. Nada foi alterado: use o sistema atual e avise o suporte.')")
        finally:
            janela.destroy()
