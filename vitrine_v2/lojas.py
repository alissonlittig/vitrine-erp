# Lojas da demonstração (nomes fictícios). O mesmo programa abre qualquer filial.
from dados import Filial

FILIAIS = {
    "centro": Filial(codigo="centro", nome_loja="Vitrine Cosméticos - Filial Centro",
                     equipe_inicial=["ANA", "BEATRIZ", "CAMILA", "DANIELA", "FERNANDO"],
                     participantes_desafio_iniciais=["ANA", "CAMILA", "DANIELA"]),
    "jardins": Filial(codigo="jardins", nome_loja="Vitrine Cosméticos - Filial Jardins",
                      equipe_inicial=["ANA", "BEATRIZ", "CAMILA", "DANIELA", "FERNANDO"],
                      participantes_desafio_iniciais=["ANA", "CAMILA"]),
}
NOMES_CURTOS = {"centro": "Centro", "jardins": "Jardins"}
