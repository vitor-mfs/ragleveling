# ragleveling — contexto do projeto

Ferramenta para decidir **onde upar** no Ragnarok Online Renewal (servidor LATAM).
Você informa nível e classe; a saída são os monstros da faixa, do mais fácil ao
mais difícil, com o mapa de cada um e o elemento a usar contra ele.

**Toda a base vem do Divine Pride.** O rAthena foi removido por decisão do dono
do projeto (commit "Remove o rAthena"): o `mob_db` dele não acompanha os
episódios recentes e a tabela de EXP genérica não bate com a do servidor.

## Como rodar

```bash
uv venv && uv pip install -e ".[dev]"
export DIVINE_PRIDE_API_KEY=...
ragleveling dp-index --de 150 --ate 285      # monta o índice por faixa, acumulando
ragleveling cacar --nivel 240 --classe "Cavaleiro Dragão"
ragleveling dp-itens -c armor -s Headgear --funcao 21   # índice de itens (recortes, não categoria inteira)
ragleveling itens --local meio --completo               # busca por local + descrição completa
pytest && ruff check .                       # 383 testes
python scripts/export_web.py                 # web/data.js para a página
```

## Arquitetura

| Módulo | Responsabilidade |
| --- | --- |
| `divinepride.py` | Cliente da API: `monstro(id)`, `skill(id)`, cache em disco, headers `x-server`/`Accept-Language`, retry com `Retry-After` |
| `dp_index.py` | Monta o índice: listagem HTML por faixa de nível → API por id → `~/.cache/ragleveling/index-dp.json` (versão 2) |
| `elements.py` | Ranking de elementos a partir de `elementResistances` do monstro; sem resistência, tudo 100% |
| `exp.py` | `exp_rate_do_monstro` lê a `expPenaltyTable` (pontos de mudança, vale o anterior); a tabela genérica só serve à rota legada |
| `difficulty.py` | Score de HP, DEF/MDEF, ataque e habilidades (classificadas pelo nome canônico `NPC_*`), normalizado dentro da consulta |
| `jobs.py` | Classe PT-BR → chave, perfil de dano, como aplicar o elemento |
| `hunt.py` | O fluxo principal sobre o índice |
| `dp_itens.py` | Itens do LATAM: listagem HTML por categoria (só quem tem o selo do servidor) → API `Item/<id>` → `~/.cache/ragleveling/index-itens-dp.json` (versão 1); `normalizar_local` (nome do site → `topo`, `meio`, `escudo`...) e `filtrar` |
| `busca_itens.py` | Busca por frase sobre o índice de itens: `interpretar` (frase → `Consulta`), `efeitos_do_item` (descrição pt + scripts → `Efeito`s com condição), `buscar` (ranking), `funcoes_do_site` (recorte para `--indexar`) |
| `router.py`, `catalog.py` | Rota nível a nível sobre catálogo YAML próprio (legado, não usa o índice) |
| `web/` + `scripts/export_web.py` | A mesma consulta no navegador |

## Decisões já tomadas

- Faixa padrão −5 a +15; sempre fora chefes, MVPs, instâncias, castelos/arenas e
  spawns com menos de 5 exemplares.
- Dificuldade min-max dentro dos candidatos: 0 é o mais fácil daquela lista.
- Classe decide DEF ou MDEF e o meio de aplicar o elemento; `--perfil` sobrescreve.
- Região `LATAM` e idioma `pt` por padrão (`RAGLEVELING_DP_SERVER`, `RAGLEVELING_DP_LANG`).
- Nome do monstro: API em `pt` → listagem em `en` → `spriteName` humanizado. A
  listagem é consultada em inglês de propósito, para servir de reserva.
- Licença MIT; `web/data.js` é cópia parcial do banco do Divine Pride, para uso
  pessoal — o repo é privado por isso.

## Onde as coisas podem enganar

- **A API ignora `?server=`**: região e idioma vão em headers. Sem eles ela
  responde como `kROM`, em coreano.
- **`attackRange` é o dano min–max**; o alcance é `range`.
- **O Divine Pride lista o mesmo mapa em várias linhas**; `agregar_spawns` soma.
- **`expPenaltyTable` é esparsa**: só os níveis em que o percentual muda. No
  LATAM o pico é 140% em +10 e cai a 40% em +16 — bem diferente da tabela
  clássica do Renewal.
- **Rate limit**: 1,0 s exato ainda leva 429; padrão 1,5 s. A documentação
  proíbe varrer o banco inteiro (revoga a chave): só a faixa pedida, com cache.
- **Índice versão 2**: ao mudar o formato, suba `VERSAO_INDICE_DP`; o `carregar`
  avisa e o `dp-index` refaz das faixas a partir do cache.

## Itens (em andamento)

Primeira etapa pronta: indexar por recorte, filtrar por local e mostrar a
descrição completa. A busca em linguagem natural ("aumentar dano em insetos",
"reduzir dano de dragões", "dano da habilidade X") **ainda não existe** — o índice
já guarda `scripts` (efeitos) e `description` para ela.

- A listagem de itens vem com `Accept-Language: pt` de propósito: assim o site já
  devolve só o recorte LATAM (17.322 itens; sem isso, 23.815 de todos os
  servidores). O selo `LATAM` por linha continua sendo conferido em código.
- A listagem aceita `subTypes`, `function` (id do filtro "Função" do site),
  `description` e `query` — é o que torna possível indexar só o que interessa.
  `query` busca nome, não id.
- As colunas da listagem mudam por categoria; ler pelo cabeçalho, nunca pela posição.
  O nome na listagem quase sempre vem vazio: o nome é o da API.
- **Local de equipar:** os nomes do site foram conferidos (`Upper`, `Middle`, `Body`,
  `Left Hand`, `Bothhand`, `Upper (Costume)`, `Right Shadow Accessory`...), mas o
  **campo do JSON da API para o local nunca foi visto com chave real** (a doc só
  mostra um item de cura). Rode `ragleveling dp-item <id>` num equipamento para
  conferir; sem local no payload, o `dp-itens` avisa quantos equipamentos ficaram
  sem local. Carta tem `Location: None` no site — "cartas para arma/armadura" ainda
  não é um filtro.

### Busca por frase (feita)

`ragleveling buscar "aumentar dano em insetos" [--local] [--completo] [--indexar]`. Artefato de
teste (amostra de 224 itens do site): https://claude.ai/artifact/LkgLyJ6c8CPta3nZretfY3 — o motor
JS dele é um porte de `busca_itens.py`; conferido contra o Python com fixtures (frases, efeitos do
corpus e buscas) e deve ser refeito junto sempre que o Python mudar.

- **O script do Divine Pride não traz condição** ("These information ignore any conditions"): lista
  todos os degraus de refino/grau soltos. Se a descrição pt fala do mesmo efeito (`_ja_dito`), o
  script é descartado; senão (item sem descrição) ele entra, marcado "só script, sem condições".
  Sem isso um bônus de Refino +11 aparecia como "vale sempre" (achado confirmado em 17 itens).
- Scripts reais conferidos no site (não na API): função 21 dano físico contra raça, 411 dano mágico
  contra raça, 25/26 resistência/fraqueza racial, 27 dano **físico** contra propriedade, 689 mágico,
  582 mágico dos ataques da propriedade, 23/28 resistência à propriedade, 29/30 tamanho, 33 dano de
  habilidade (nome em português **ou** interno), 17 `ATK %`/`MATK %`, 51/919/35 alcance, corpo a
  corpo e crítico. Valor em fórmula (`5 + Refine%`, `temp * 3`) é ignorado de propósito.
- Descrição pt: `Dano físico contra as raças X e Y +N%`, `Resistência a raça X ±N%`, `Dano de [A] [B] e
  [C] +N%` (separador pode ser só espaço), `Dano mágico de propriedade X`. Cabeçalhos terminados em `:`
  (`Refino +7 ou mais:`, `Grau D ou mais:`, `A cada N refinos:`) e blocos `Conjunto` viram a condição.
  `adicional` = soma ao que já havia (marcado, mas o ranking compara o valor da linha).
- "Todas as raças de monstros" não inclui humano nem doram.
- Nome de habilidade com palavra de raça/propriedade ("Lanças de Fogo"): ganha da propriedade quando o
  índice conhece a habilidade ou a frase tem mais palavras que o vocabulário.
- **Ainda não verificado:** o formato do campo `scripts` na **API** (o site mostra o texto em inglês;
  a API pode devolver outra coisa). `dp-item <id>` mostra o que chega e o que foi entendido.
- Conhecido e deixado de fora: buff temporário ("Efeito:") tratado como condição comum; frase que mistura
  duas categorias (raça e propriedade); `adicional` não é somado; prosa antiga ("Inflige 5% a mais...").

## Estado atual

Índice local cobre **1–285** por decisão do dono, ciente do aviso da API sobre
varredura: 2.449 monstros, 1.267 com spawn em 457 mapas, 205 skills com nome
canônico. A página web tem os 973 não-chefe com spawn. Refazer uma faixa vem do
cache; só monstros novos no site custam requisição.

## Próximos passos

1. Migrar `spots`/`rota` para o índice: a `expPenaltyTable` já dá a EXP por
   nível; falta a tabela de EXP necessária por nível do jogador.
2. A coluna "Perigo" usa a classificação por nome `NPC_*`; nomes novos (ex.:
   `NPC_WIDE*`) podem precisar de regex novo em `difficulty.CATEGORIAS_SKILL`.

## Artefato

Versão web publicada como artefato privado em
https://claude.ai/artifact/BW9hLWn4vKytW7cmudrcAW — para atualizá-lo de outra
sessão, publique passando essa URL em `url`.

## Estilo

Código, commits, documentação e saída da CLI em **português**. Comentário só
onde explica uma decisão que o código não mostra. Nada de dado inventado.
