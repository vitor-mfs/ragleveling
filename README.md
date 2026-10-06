# ragleveling

Onde upar no Ragnarok Online Renewal (servidor LATAM). Você diz o **nível** e a
**classe**; o ragleveling devolve os monstros da sua faixa, do mais fácil ao
mais difícil, com o mapa de cada um e o elemento que você deve usar contra ele.

Toda a base vem do [Divine Pride](https://www.divine-pride.net).

```bash
export DIVINE_PRIDE_API_KEY=...                  # https://www.divine-pride.net/account
ragleveling dp-index --de 150 --ate 285          # uma vez por faixa: monta o índice
ragleveling cacar --nivel 240 --classe "Cavaleiro Dragão"
```

```
                    Cavaleiro Dragão base 240 — 91 alvos (melee)
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━┳━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Monstro             ┃    Lv (Δ) ┃       EXP ┃      HP ┃ DEF ┃ Dif. ┃ Mapa (qtd)     ┃ Usar         ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━╇━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ Garden Cannon(Blue) │ 254 (+14) │ 1.034.891 │ 285.340 │ 264 │    1 │ hero_dun1 (25) │ Vento 175%   │
│ Garden Wolf         │ 253 (+13) │ 1.068.536 │ 316.070 │ 421 │    5 │ hero_dun1 (35) │ Fogo 175%    │
│ Jennifer            │ 255 (+15) │   883.156 │ 720.190 │ 277 │   18 │ clock_01 (95)  │ Sagrado 125% │
└─────────────────────┴───────────┴───────────┴─────────┴─────┴──────┴────────────────┴──────────────┘
Elemento: carta de Vento na arma ou Encantar Arma.
```

## Instalação

```bash
uv venv && uv pip install -e ".[dev]"
```

## Como o índice é montado

`dp-index` trabalha em duas etapas, sobre a faixa de níveis que você pedir:

1. A **listagem** do site (`/database/monster?minLevel=&maxLevel=`) devolve, de
   50 em 50, todos os monstros da faixa: id, nome, nível, HP, EXP, elemento,
   raça, tamanho e tipo. Não precisa de chave.
2. A **API** (`/api/database/Monster/<id>`) completa cada monstro com defesa,
   ataque, habilidades, resistências elementais, spawns e a tabela de
   penalidade de EXP. As habilidades vêm só com id; `GET Skill/<id>` dá o nome
   canônico (`NPC_SUMMONSLAVE`), consultado uma vez por habilidade.

A etapa 2 é uma requisição por monstro, com intervalo de 1,5 s: uns 5 minutos
para 200 monstros. Tudo fica em cache em `~/.cache/ragleveling`; rodar de novo
a mesma faixa não vai à rede, e faixas novas se somam às anteriores.

**Limites de uso.** A [documentação da API](https://www.divine-pride.net/tools/api-doc)
pede para guardar o que já foi consultado, respeitar o `Retry-After` e **não
varrer o banco inteiro** — enumeração em massa de ids leva à revogação da chave.
O `dp-index` só percorre a faixa pedida e o cliente faz o resto.

Região e idioma vão nos headers `x-server` e `Accept-Language`, com padrão
`LATAM` e `pt` (`RAGLEVELING_DP_SERVER`, `RAGLEVELING_DP_LANG`). Quando o
servidor não traduziu um monstro, o nome cai no inglês da listagem e, em último
caso, no nome de sprite (`EP19_AWIN_TRAINEE` → `Ep19 Awin Trainee`).

## Como cada coluna é decidida

| Coluna | De onde vem |
| --- | --- |
| **Faixa de nível** | `-5` a `+15` do seu base level, ajustável. |
| **EXP** | EXP base × o percentual da **tabela de penalidade do próprio monstro** (`expPenaltyTable`), no seu nível. No LATAM o pico é 140% em +10, e cai a 40% em +16. |
| **Dif.** | Vida, defesa, ataque, quantas habilidades o monstro tem e quão perigosas são (invocação, status, cura, área). Normalizado **dentro da sua consulta**: 0 é o mais fácil daquela lista, 100 o mais difícil. |
| **DEF ou MDEF** | Muda conforme o perfil da classe: físico olha DEF, mágico olha MDEF. |
| **Mapa (qtd)** | Mapa com mais exemplares e quantos são; `+N` indica outros mapas. |
| **Usar** | O elemento que mais rende contra a **resistência do próprio monstro** (`elementResistances`), com o percentual. |

O rodapé diz como aplicar o elemento — magia, flecha, munição ou carta/Encantar
Arma — conforme a classe. Chefes e MVPs ficam sempre de fora.

### Opções do `cacar`

| Flag | O que faz |
| --- | --- |
| `--nivel`, `-n` | Seu base level. Obrigatório. |
| `--classe`, `-c` | PT-BR com ou sem acento, inglês ou a chave do rAthena: `"Cavaleiro Rúnico"`, `cacador`, `Arch_Bishop`. |
| `--perfil` | `melee`, `ranged` ou `magic`, quando seu build foge do padrão da classe. |
| `--faixa-min` / `--faixa-max` | Diferença de nível aceita (padrão `-5` e `+15`). |
| `--ordenar` | `dificuldade` (padrão), `exp` ou `nivel`. |
| `--min-spawn` | Mínimo de exemplares no mapa para ele contar (padrão 5). |
| `--instancias` | Inclui mapas de instância e memorial. |
| `--todos-mapas` | Inclui castelos, arenas, baús de WoE e mapas de quest. |
| `--limite`, `-l` | Quantos monstros mostrar (padrão 15). |

`ragleveling dp-check <id>` mostra o que a API devolveu para um monstro: os
campos que vieram, o que foi entendido e onde o JSON cru ficou salvo.

## Itens

Busca de itens do LATAM, também sobre o Divine Pride. A listagem do site diz
quais itens existem no LATAM (o selo do servidor); a API completa cada um com
a descrição, as classes e os efeitos. Prefira recortes a categorias inteiras —
é uma requisição por item, e a API revoga a chave de quem varre o banco.

```bash
# itens de topo/meio/baixo que aumentam o dano contra uma raça (função 21 do site)
ragleveling dp-itens --categoria armor --subtipo Headgear --funcao 21
ragleveling itens --local meio --completo         # filtra por local e mostra a descrição inteira
ragleveling itens --local escudo --texto "dano insetos"
ragleveling dp-item 2201                          # o que a API devolveu para um item
```

| Opção do `dp-itens` | O que faz |
| --- | --- |
| `--categoria`, `-c` | `weapon`, `armor`, `card`, `costume`, `shadow`, `ammo`, `consumable`, `other`. Obrigatória; pode repetir. |
| `--subtipo`, `-s` | Subtipo do site (`Headgear`, `Shield`, `Garment`, `Shoes`, `Accessory`...). |
| `--funcao` | ID da função no filtro do site (21 = aumenta o dano contra uma raça). |
| `--descricao`, `--busca` | Texto na descrição / no nome, pelos filtros do próprio site. |
| `--limite`, `-l` | Para depois de N itens por categoria — bom para um teste curto. |

### Buscar por frase

```bash
ragleveling buscar "aumentar dano em insetos"
ragleveling buscar "reduzir dano de dragões" --local meio --completo
ragleveling buscar "aumentar dano da habilidade Lâminas Retalhadoras" --indexar
```

A frase diz o que se quer (aumentar o dano que você causa, ou reduzir o que recebe) e contra
quem: raça, propriedade (elemento), tamanho, uma habilidade ou o dano em geral (mágico, físico,
crítico, à distância, corpo a corpo). O resultado vem do maior bônus para o menor, com o que
vale sempre antes do que exige refino, conjunto ou grau.

- Os efeitos saem de duas fontes: a descrição em português e os scripts do Divine Pride. Quando a
  descrição fala do efeito, só ela vale: o script lista todos os degraus de refino soltos, sem
  condição. Item sem descrição só tem o script, e a tela avisa "só script, sem condições".
- "Resistência a raça Demônio -5%" é fraqueza e nunca entra em "reduzir dano de demônios".
- `--indexar` escolhe sozinho o recorte do site que a frase pede (filtro "Função") e consulta a API
  só para esses itens; acima de 30 min pede confirmação. Para habilidade usa o nome na descrição.
- A busca não entende EXP, HP, cura, recarga nem "ignorar defesa".

Acima de 30 minutos de consulta o `dp-itens` pede confirmação (`--sim` pula).
O `itens --local` aceita `topo`, `meio`, `baixo`, `armadura`, `arma`, `escudo`,
`capa`, `calcado`, `acessorio`, `carta` (o tipo do item, para listar só cartas), além de `traje-*` e `sombra-*`.

## Versão web

`web/` é a mesma consulta rodando no navegador, sem instalar nada:

```bash
python scripts/export_web.py    # gera web/data.js a partir do índice
```

Clicar numa linha abre todos os mapas do monstro, suas habilidades por
categoria, os elementos a evitar e a ficha.

## Rotas de level up (legado)

`spots` e `rota` montam uma rota completa estimando EXP/hora e quando trocar de
mapa, mas ainda sobre um catálogo YAML próprio (`data/exemplo.yaml`, valores
ilustrativos) e a tabela genérica de penalidade do Renewal. Migrá-los para o
índice do Divine Pride é o próximo passo.

## Limitações atuais

- O índice cobre só as faixas que você rodou no `dp-index` (o dono já rodou 1–285).
- A dificuldade não modela quanto **você** aguenta apanhar: é o monstro que é
  medido, não a luta.
- Raça, tamanho e cartas não entram no cálculo — só o elemento.
- `spots`/`rota` ainda não usam o índice.

## Desenvolvimento

```bash
pytest
ruff check .
```

## Licença

MIT. Os dados em `web/data.js` são uma cópia parcial do banco do Divine Pride,
gerada para uso pessoal; não os redistribua.
