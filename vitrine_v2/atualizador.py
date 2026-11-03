# -*- coding: utf-8 -*-
"""Atualização automática (Velopack). Nunca bloqueia a interface e nunca derruba o programa.

Fluxo: ao abrir (após ~20 s) e a cada hora, consulta a fonte, BAIXA a versão nova em segundo plano e avisa
"Atualização pronta". Só aplica quando a pessoa clica em "Atualizar agora" (a tela recusa se houver venda
em andamento). Se fechar sem clicar, a versão baixada entra sozinha na próxima abertura.

Fonte e canal (em C:\\Vitrine\\config.json ou variáveis de ambiente):
  Padrao: o portao (portao_url + portao_chave do config.json) serve /atualizacoes/<chave>/ a partir do repo privado.
  update_fonte / VITRINE_UPDATE_FONTE : URL do GitHub (https://github.com/<dono>/<repo>), outra URL http(s)
                                           ou uma PASTA local com os arquivos publicados.
  update_canal / VITRINE_UPDATE_CANAL : "oficial" ou "teste" (o canal real é "<filial>-<canal>").
                                           Sem isso vale o canal em que o programa foi instalado.
"""
import os
import threading
import time
from datetime import datetime

try:
    import velopack
except ImportError:  # rodando pelo Python, sem o pacote
    velopack = None

FONTE_PADRAO = None  # sem fonte configurada, o atualizador fica desativado
CANAL_PADRAO = "oficial"
INTERVALO_S = 3600
ATRASO_INICIAL_S = 20


def iniciar_velopack():
    """Tem de ser a PRIMEIRA coisa do programa: o instalador/atualizador chama o exe com argumentos especiais."""
    if velopack is not None:
        velopack.App().run()


class Atualizador:
    def __init__(self, filial_codigo, cfg=None, registrar_erro=None):
        cfg = cfg or {}
        self._registrar = registrar_erro or (lambda origem, e: None)
        self.fonte = os.environ.get("VITRINE_UPDATE_FONTE") or cfg.get("update_fonte") or self._fonte_portao(cfg) or FONTE_PADRAO
        canal = os.environ.get("VITRINE_UPDATE_CANAL") or cfg.get("update_canal")
        self.canal = f"{filial_codigo}-{canal}" if canal else None
        self._intervalo = float(os.environ.get("VITRINE_UPDATE_INTERVALO") or INTERVALO_S)
        self._atraso = float(os.environ.get("VITRINE_UPDATE_ATRASO") or ATRASO_INICIAL_S)
        self._trava = threading.Lock()
        self._info = None
        self.um = None
        self.estado = {"ativo": False, "versao": "", "canal": "", "status": "desativado", "nova": "", "notas": "",
                       "ultima_checagem": "", "erro": ""}
        if velopack is None or not self.fonte:
            return
        try:
            self.um = velopack.UpdateManager(self._origem(), self._opcoes())
            self.estado.update(ativo=True, versao=self.um.get_current_version(), status="atualizado",
                               canal=self.canal or "")
            pendente = self.um.get_update_pending_restart()
            if pendente is not None:
                self._marcar_pronta(pendente.Version, pendente.NotesMarkdown, pendente)
        except Exception:  # noqa: BLE001  # programa não instalado pelo Setup (ex.: rodando do Python): sem update
            self.um = None

    @staticmethod
    def _fonte_portao(cfg):
        """Repo de releases e PRIVADO: as lojas baixam pelo portao (mesma chave da loja, no caminho da URL)."""
        url = (os.environ.get("VITRINE_PORTAO_URL") or cfg.get("portao_url") or "").strip().rstrip("/")
        chave = (os.environ.get("VITRINE_PORTAO_CHAVE") or cfg.get("portao_chave") or "").strip()
        return f"{url}/atualizacoes/{chave}" if url and chave else None

    def _origem(self):
        f = self.fonte.strip()
        if f.lower().startswith(("https://github.com/", "http://github.com/")):
            return velopack.GithubSource(f, None, False)
        return f  # outra URL http(s) ou pasta: o Velopack entende a string

    def _opcoes(self):
        if not self.canal:
            return None
        return velopack.UpdateOptions(True, 10, self.canal)  # com canal escolhido, trocar de canal pode "descer" versão

    def _marcar_pronta(self, versao, notas, info):
        self._info = info
        self.estado.update(status="pronta", nova=versao, notas=notas or "", erro="")

    def checar(self):
        """Consulta, baixa e deixa pronta. Seguro de chamar de qualquer thread. Devolve o estado."""
        if self.um is None or not self._trava.acquire(blocking=False):
            return self.estado
        try:
            self.estado["ultima_checagem"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            if self._info is not None:
                return self.estado
            info = self.um.check_for_updates()
            if info is None:
                self.estado.update(status="atualizado", erro="")
            else:
                alvo = info.TargetFullRelease
                self.estado.update(status="baixando", nova=alvo.Version)
                self.um.download_updates(info)  # confere SHA256 do pacote; falha = não aplica
                self._marcar_pronta(alvo.Version, alvo.NotesMarkdown, info)
        except Exception as e:  # noqa: BLE001  # sem internet, fonte fora do ar, pacote ruim: segue na versão atual
            self.estado.update(status="erro" if self._info is None else "pronta", erro=str(e)[:300])
            # sem rede/repo ainda é normal: fica só no estado, não vai para o log de erros
        finally:
            self._trava.release()
        return self.estado

    def iniciar_laco(self):
        if self.um is None:
            return

        def laco():
            time.sleep(self._atraso)
            while True:
                self.checar()
                time.sleep(self._intervalo)
        threading.Thread(target=laco, daemon=True, name="atualizador").start()

    def aplicar(self):
        """Fecha este programa, troca os arquivos e abre a versão nova. Quem chama já fez o backup e fechou o banco."""
        if self.um is None or self._info is None:
            raise RuntimeError("não há atualização pronta")
        self.um.apply_updates_and_restart(self._info)
