# =============================================================================
# VITRINE ERP — LANÇADOR
# =============================================================================
# Uso:
#     python main.py                  -> pergunta qual filial abrir
#     python main.py --filial centro  -> abre direto a filial Centro
#     python main.py --regerar-demo   -> recria o banco fictício da filial
#
# Se o banco da filial ainda não existir, ele é criado com DADOS FICTÍCIOS
# (gerar_banco_demo.py), para o sistema abrir já com histórico para explorar.
# =============================================================================
import argparse
import os
import sys

import customtkinter as ctk

import nucleo_pdv
from config_filiais import FILIAIS, FILIAL_PADRAO
from gerar_banco_demo import gerar_banco_demo


def escolher_filial():
    """Janela simples para escolher a filial (usada quando nenhuma foi informada)."""
    if len(FILIAIS) == 1:
        return next(iter(FILIAIS))
    escolha = {"filial": None}
    janela = ctk.CTk()
    janela.title("Vitrine ERP")
    janela.geometry("420x320")
    janela.resizable(False, False)
    ctk.CTkLabel(janela, text="VITRINE ERP", font=ctk.CTkFont(size=26, weight="bold")).pack(pady=(28, 2))
    ctk.CTkLabel(janela, text="Escolha a filial", font=ctk.CTkFont(size=15),
                 text_color=nucleo_pdv.Tema.CINZA_TEXTO).pack(pady=(0, 18))

    def _abrir(chave):
        escolha["filial"] = chave
        janela.destroy()

    for chave, cfg in FILIAIS.items():
        ctk.CTkButton(janela, text=cfg["nome_loja"].split(" - ")[-1], width=260, height=46,
                      font=ctk.CTkFont(size=16, weight="bold"), fg_color=nucleo_pdv.Tema.VERDE,
                      hover_color=nucleo_pdv.Tema.VERDE_HOVER, corner_radius=nucleo_pdv.Tema.RAIO_BOTAO,
                      command=lambda c=chave: _abrir(c)).pack(pady=6)
    janela.mainloop()
    return escolha["filial"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Vitrine ERP - PDV/ERP desktop para varejo")
    parser.add_argument("--filial", choices=sorted(FILIAIS), help="filial a abrir (padrão: pergunta)")
    parser.add_argument("--regerar-demo", action="store_true", help="recria o banco com dados fictícios")
    args = parser.parse_args(argv)

    filial = args.filial or escolher_filial()
    if filial is None:  # janela de escolha fechada sem escolher
        return
    cfg = FILIAIS.get(filial) or FILIAIS[FILIAL_PADRAO]

    caminho_banco = os.path.join(nucleo_pdv.BASE_DIR, cfg["arquivo_banco"])
    if args.regerar_demo or not os.path.exists(caminho_banco):
        gerar_banco_demo(caminho_banco, filial, cfg["equipe_inicial"])

    nucleo_pdv.iniciar_aplicativo(**cfg)


if __name__ == "__main__":
    main(sys.argv[1:])
