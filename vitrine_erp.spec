# -*- mode: python ; coding: utf-8 -*-
# Gera dist/VitrineERP/VitrineERP.exe (modo pasta: abre mais rápido e gera menos
# alertas de antivírus que o modo "arquivo único").
#     pyinstaller --clean vitrine_erp.spec
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
d, b, h = collect_all("customtkinter")
datas += d; binaries += b; hiddenimports += h

a = Analysis(["main.py"], pathex=[], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             hookspath=[], runtime_hooks=[], excludes=["pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VitrineERP", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VitrineERP")
