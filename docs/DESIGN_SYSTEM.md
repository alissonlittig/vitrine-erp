# Vitrine ERP: Design System

Todos os valores visuais do sistema saem de um único lugar: a classe `Tema` em [`nucleo_pdv.py`](../nucleo_pdv.py). Se uma cor muda ali, muda no sistema inteiro: telas, tabelas, gráficos e exportações.

*All visual values live in one place, the `Tema` class. Change a token there and every screen, table, chart and export follows.*

## 1. Tokens de cor

| Token | Valor | Uso |
|---|---|---|
| `VERDE` | `#1DB954` | Ação principal (salvar, entrar), menu ativo, valores positivos, "OK" no caixa |
| `VERDE_HOVER` | `#159a44` | Hover das ações principais |
| `AZUL` | `#2f6fed` | Ações secundárias (editar, exportar Excel), recebimentos |
| `AZUL_HOVER` | `#1f4fa8` | Hover das ações secundárias |
| `VERMELHO` | `#e53935` | Ações destrutivas (excluir, sangria), despesas, prejuízo, "Falta" no caixa |
| `VERMELHO_HOVER` | `#b71c1c` | Hover das ações destrutivas |
| `AMARELO` | `#f2b705` | Alertas não bloqueantes (alterações não salvas, "Sobra" no caixa, meta em andamento) |
| `TEXTO_PADRAO` | `gray10` / `#DCE4EE` | Texto principal (modo claro / escuro) |
| `CINZA_TEXTO` | `#5f5f5f` / `#b8b8b8` | Texto secundário, legendas e dicas. Clareado no modo escuro para manter contraste sobre os cartões |

### Tabelas (ttk.Treeview)

| Token | Valor | Uso |
|---|---|---|
| `TABELA_FUNDO` | `#242424` | Fundo da tabela |
| `TABELA_CABECALHO` | `#1a1a1a` | Cabeçalho (hover: `#333333`) |
| `LINHA_PAR` / `LINHA_IMPAR` | `#2b2b2b` / `#242424` | Zebra |
| `TOTAL_FUNDO` | `#3a3a3a` | Linha de TOTAL, sempre em negrito |
| `TABELA_TEXTO` | `#e8e8e8` | Texto das células |

Tabelas são criadas sempre por `nova_tabela()`, que já aplica zebra e estilo de TOTAL. Nenhuma tela configura isso na mão.

### Gráficos (Matplotlib)

Um único `plt.rcParams.update(...)` aplica fundo `#2b2b2b`, texto `#e8e8e8`, grade `#4a4a4a` e legenda escura a todos os gráficos. As séries por vendedora usam uma paleta categórica fixa por posição, então a mesma pessoa mantém a cor entre telas.

## 2. Tipografia

| Token | Fonte | Uso |
|---|---|---|
| `TITULO` | Segoe UI 28 bold | Título da tela de venda |
| `SUBTITULO` | Segoe UI 16 bold | Título das telas e dos cartões |
| `LABEL` | Segoe UI 14 bold | Rótulos de campos e filtros |
| `TEXTO` | Segoe UI 13 | Texto corrido e dicas |

Números de destaque (cartões KPI) usam 28 bold; tabelas usam 12 (cabeçalho 13 bold).

## 3. Forma e espaçamento

| Token | Valor | Uso |
|---|---|---|
| `RAIO` | 12 px | Cartões e painéis |
| `RAIO_BOTAO` | 8 px | Botões, campos e menus |
| Margem de tela | 20 px | Padding lateral padrão |
| Altura de linha | 32 px | Linhas de tabela |

## 4. Componentes e padrões

| Componente | Variantes | Regras |
|---|---|---|
| Botão | Primário (verde), Secundário (azul), Destrutivo (vermelho), Contorno (borda vermelha) | Ação destrutiva sempre pede confirmação |
| Cartão KPI | Receita (verde), Despesa (vermelho), Resultado (verde/vermelho pelo sinal) | Número grande primeiro, rótulo em `CINZA_TEXTO` |
| Tabela | Padrão, com linha TOTAL | Valores monetários alinhados à direita; em tabelas largas, sem "R$" nas células (o cabeçalho indica a moeda) |
| Feedback | Sucesso (verde), Erro (vermelho), Aviso (amarelo) | Mensagem inline some sozinha em 3 s; erros de banco abrem um diálogo e vão para o `erros_sistema.log` |
| Barra de progresso | Em andamento (amarelo), Concluída (verde) | Usada no Desafio do Dia (x/5 por vendedora) |

## 5. Acessibilidade

- Status nunca depende só de cor: o caixa escreve "OK", "Falta R$ X" ou "Sobra R$ X", e o Desafio mostra "✔ 5/5".
- Texto secundário clareado (`#b8b8b8`) para manter contraste sobre fundos `#2b2b2b`.
- Fluxos de digitação funcionam só com teclado (Enter salva nas telas de venda, despesa, caixa e senha).
