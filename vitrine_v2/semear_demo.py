"""Monta o banco de DEMONSTRAÇÃO da interface nova: migra o banco fictício (gerar_banco_demo.py) e cadastra um
catálogo inventado com estoque. Nada aqui vem de loja real.

  python gerar_banco_demo.py centro
  python vitrine_v2/semear_demo.py --origem demo_centro.db --destino demo_dados/centro.db
  python vitrine_v2/vitrine_v2.py --banco demo_dados/centro.db
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dados as D  # noqa: E402
import migrar  # noqa: E402
from lojas import FILIAIS  # noqa: E402

CATALOGO = [  # (nome, categoria, preço)
    ("Perfume Flor de Laranjeira 100ml", "PERFUMARIA", 119.9), ("Perfume Âmbar Noturno 50ml", "PERFUMARIA", 149.9),
    ("Body Splash Baunilha 200ml", "PERFUMARIA", 59.9), ("Colônia Brisa do Mar 120ml", "PERFUMARIA", 79.9),
    ("Batom Matte Rosé", "OUTROS", 34.9), ("Batom Cremoso Vermelho", "OUTROS", 34.9),
    ("Base Líquida Tom 20", "OUTROS", 69.9), ("Máscara de Cílios Volume", "OUTROS", 42.5),
    ("Shampoo Reparador 300ml", "OUTROS", 38.9), ("Condicionador Reparador 300ml", "OUTROS", 38.9),
    ("Creme Hidratante Corporal 400g", "OUTROS", 29.9), ("Protetor Solar FPS 50", "OUTROS", 54.9),
    ("Sabonete Líquido Lavanda", "OUTROS", 19.9), ("Esmalte Nude", "OUTROS", 8.9),
    ("Kit Presente Aurora", "OUTROS", 99.9), ("Óleo Capilar Argan 60ml", "OUTROS", 44.9),
]


def ean13(base12):
    s = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(base12))
    return base12 + str((10 - s % 10) % 10)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--origem", required=True)
    ap.add_argument("--destino", required=True)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.destino)), exist_ok=True)
    fil = FILIAIS["centro"]
    r = migrar.migrar(a.origem, a.destino, fil)
    assert r["ok"], r
    d = D.Dados(a.destino, fil)
    rnd = random.Random(7)
    cods = []
    for n, (nome, cat, preco) in enumerate(CATALOGO, 1):
        cod = ean13(f"78911110{n:04d}")
        assert d.cadastrar_produto(cod, nome, cat, f"{preco:.2f}".replace(".", ","))["ok"]
        cods.append(cod)
    d.movimentar("entrada", [{"codigo": c, "qtd": rnd.choice([3, 6, 12, 18, 24])} for c in cods], "estoque inicial da demo")
    for c in cods[-3:]:
        d.definir_minimo(c, 5)
    d.movimentar("contagem", [{"codigo": cods[2], "qtd": 2}, {"codigo": cods[7], "qtd": 0}], "contagem da demo")
    d.fechar()
    print("demo pronta:", a.destino, "-", len(cods), "produtos")
