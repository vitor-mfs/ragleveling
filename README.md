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

- O índice cobre só as faixas que você rodou no `dp-index`.
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
