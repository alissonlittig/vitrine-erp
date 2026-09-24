# =============================================================================
# CONFIGURAÇÃO DAS FILIAIS
# =============================================================================
# Cada filial roda o MESMO motor (nucleo_pdv.py) com a sua própria
# configuração e o seu próprio arquivo de banco de dados. Para abrir uma nova
# filial, basta acrescentar uma entrada neste dicionário.
#
# Todos os nomes abaixo são FICTÍCIOS (versão de demonstração/portfólio).
#
# Senha de demonstração da Área de Gestão: demo123
# Para trocar, gere um novo hash com:
#     python -c "import nucleo_pdv as n; print(n.gerar_hash_senha('nova_senha'))"
# e cole o resultado em HASH_SENHA_DEMO. A senha em si nunca fica no código.
# =============================================================================

HASH_SENHA_DEMO = (
    "pbkdf2_sha256$200000$deb49fe2c6199650e69eeec85e27699f"
    "$8c3e3a790abed675573709987a39ea111ac6626b58328a7f79ffb1c372a2d97a"
)

# Regras de negócio comuns às filiais
REGRAS_COMUNS = {
    "hash_senha_gestao": HASH_SENHA_DEMO,
    "nome_sistema": "VITRINE ERP",
    "minutos_bloqueio_gestao": 5,          # Gestão se tranca sozinha após 5 min sem uso
    "inicio_comissao_automatica": None,    # comissão de 1% calculada automaticamente desde sempre
    "sem_comissao": ("FERNANDO",),         # sócio que também vende não recebe comissão
    "excluidos_desafio": ("FERNANDO",),    # nem participa do Desafio do Dia
    "excluidos_bonificacao": ("FERNANDO",),
}

FILIAIS = {
    "centro": {
        "nome_loja": "Aurora Cosméticos - Filial Centro",
        "arquivo_banco": "demo_centro.db",
        "equipe_inicial": ["ANA", "BEATRIZ", "CAMILA", "DANIELA", "FERNANDO"],
        **REGRAS_COMUNS,
    },
    "jardins": {
        "nome_loja": "Aurora Cosméticos - Filial Jardins",
        "arquivo_banco": "demo_jardins.db",
        "equipe_inicial": ["BRUNA", "CLARA", "ELISA", "FERNANDO"],
        **REGRAS_COMUNS,
    },
}

FILIAL_PADRAO = "centro"
