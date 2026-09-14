# ragleveling

Onde upar no Ragnarok Online Renewal. Você diz o **nível** e a **classe**; o
ragleveling devolve os monstros da sua faixa, do mais fácil ao mais difícil,
com o mapa de cada um e o elemento que você deve usar contra ele.

```bash
ragleveling sync                                  # uma vez: baixa os dados do jogo
ragleveling cacar --nivel 60 --classe "Cavaleiro Rúnico"
```

```
                  Cavaleiro Rúnico base 60 — 8 alvos (melee)
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━┳━━━━━━━┳━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Monstro        ┃  Lv (Δ) ┃ EXP ┃    HP ┃ DEF ┃ Dif. ┃ Mapa (qtd)       ┃ Usar         ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━╇━━━━━━━╇━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ Goblin         │ 56 (-4) │ 477 │ 1.877 │  64 │    7 │ prt_fild11 (60)  │ Vento 150%   │
│ Alligator      │ 57 (-3) │ 488 │ 1.939 │  62 │    7 │ cmd_fild03 (194) │ Vento 150%   │
│ Tri Joint      │ 66 (+6) │ 689 │ 2.186 │  22 │    8 │ beach_dun2 (20)  │ Fogo 150%    │
│ Matyr          │ 58 (-2) │ 499 │ 2.002 │  63 │    9 │ in_sphinx2 (32)  │ Sagrado 125% │
└────────────────┴─────────┴─────┴───────┴─────┴──────┴──────────────────┴──────────────┘
Elemento: carta de Vento na arma ou Encantar Arma.
```

## Instalação

```bash
uv venv && uv pip install -e ".[dev]"
ragleveling sync
```

O `sync` baixa ~110 arquivos do rAthena (uns 30 segundos), sem chave de API e
sem limite de requisições, e monta um índice em `~/.cache/ragleveling`.

## Como cada coluna é decidida

| Coluna | De onde vem |
| --- | --- |
| **Faixa de nível** | `-5` a `+15` do seu base level: a zona sem penalidade de EXP, até o bônus máximo de 150%. Ajustável. |
| **EXP** | EXP base do monstro já multiplicada pela penalidade/bônus de nível do Renewal. |
| **Dif.** | Vida, defesa, ataque, quantas habilidades o monstro tem e quão perigosas são (invocação, status, cura, área). Normalizado **dentro da sua consulta**: 0 é o mais fácil daquela lista, 100 o mais difícil — comparar scores de duas consultas não significa nada. |
| **DEF ou MDEF** | Muda conforme o perfil da classe: físico olha DEF, mágico olha MDEF. |
| **Mapa (qtd)** | Mapa com mais exemplares e quantos são; `+N` indica outros mapas. |
| **Usar** | Elemento de ataque mais eficaz contra a defesa elemental do monstro, pela tabela oficial do Renewal, e quanto de dano ele causa. |

O rodapé diz como aplicar esse elemento, e isso depende da classe: magia para
conjurador, flecha para arco, munição para arma de fogo, carta ou Encantar Arma
para corpo a corpo.

Ficam sempre de fora **chefes e MVPs**, monstros sem EXP e monstros que só
nascem em mapa fechado.

### Opções do `cacar`

| Flag | O que faz |
| --- | --- |
| `--nivel`, `-n` | Seu base level. Obrigatório. |
| `--classe`, `-c` | Aceita PT-BR com ou sem acento, inglês e a chave do rAthena: `"Cavaleiro Rúnico"`, `cacador`, `Arch_Bishop`. |
| `--perfil` | `melee`, `ranged` ou `magic`, quando seu build foge do padrão da classe. |
| `--faixa-min` / `--faixa-max` | Diferença de nível aceita (padrão `-5` e `+15`). |
| `--ordenar` | `dificuldade` (padrão), `exp` ou `nivel`. |
| `--min-spawn` | Mínimo de exemplares no mapa para ele contar (padrão 5). |
| `--instancias` | Inclui mapas de instância e memorial. |
| `--todos-mapas` | Inclui castelos, arenas, baús de WoE e mapas de quest. |
| `--limite`, `-l` | Quantos monstros mostrar (padrão 15). |

## Versão web

`web/` é a mesma consulta rodando no navegador, sem instalar nada: uma página
estática com os monstros embutidos.

```bash
ragleveling sync
python scripts/export_web.py    # gera web/data.js (~230 KB, 984 monstros)
```

A página faz a mesma conta da CLI — penalidade de EXP, score de dificuldade,
tabela elemental — em JavaScript, sobre esse arquivo. Clicar numa linha abre
todos os mapas do monstro, suas habilidades e os elementos a evitar.

## De onde vêm os dados

| Fonte (rAthena) | O que dá |
| --- | --- |
| `db/re/mob_db.yml` | 2.675 monstros: nível, HP, ATK, DEF, MDEF, elemento, raça, EXP, se é chefe |
| `db/re/mob_skill_db.txt` | as habilidades de cada monstro |
| `db/re/attr_fix.yml` | a tabela oficial de dano por elemento |
| `npc/**/mobs/*.txt` | em que mapa cada monstro nasce, quantos e o respawn |

Os scripts de spawn aparecem em duas formas — com e sem coordenadas — e as
dungeons dos episódios recentes usam a forma curta. Ler só uma delas deixava os
monstros de 195+ sem mapa e, portanto, fora de qualquer consulta.

### Quando o rAthena ainda não portou o mapa

O rAthena leva tempo para acompanhar os episódios novos. Acontece de o mapa já
existir no `map_index.txt` e os monstros já existirem no `mob_db.yml`, mas
nenhum script dizer quantos nascem e onde — é o caso do `clock_01`, cujos
monstros (Blue Moon Loli Ruri, Pierrotzoist, Disguiser, Grote, todos 253+)
estão no banco sem mapa nenhum. Sem mapa, o ragleveling descarta o monstro.

Veja quem está nessa situação:

```bash
ragleveling faltando --nivel-min 200
```

E preencha o que faltar em `data/spawns_extra.yaml`, com os números da página do
mapa no Divine Pride:

```yaml
mapas:
  clock_01:
    fonte: https://www.divine-pride.net/database/map/clock_01
    spawns:
      - { monster_id: 20940, amount: 30, respawn_s: 5 }
```

Vale na hora, sem rodar `sync` de novo. Todo spawn vindo daí aparece marcado —
`*` na CLI, `manual` no detalhe da web — para não se confundir com o que veio do
servidor.

A API do Divine Pride **não** responde "quais monstros existem no nível 70" —
ela só busca por ID. Por isso o índice vem do rAthena, que é a mesma base de
números que o Divine Pride publica. A consequência: nomes de monstro e de mapa
saem como o servidor os chama (`Bloody Knight`, `ein_dun02`). A tradução PT-BR
depende do Divine Pride e ainda não está implementada.

## Rotas de level up

Além da busca por nível, o ragleveling monta uma **rota** completa a partir de
um catálogo próprio, estimando EXP/hora e quando trocar de mapa:

```bash
ragleveling spots --nivel 60 --dps 800
ragleveling rota --de 15 --ate 99 --dps 800
```

1. **Penalidade de nível** — a EXP de um kill é multiplicada pela tabela do
   Renewal (`src/ragleveling/exp.py`).
2. **Ritmo real de kills** — `HP ÷ DPS` dá o tempo de kill; somado ao tempo de
   deslocamento, vira kills/hora. Se o mapa não repõe monstros nesse ritmo, o
   teto passa a ser o respawn (`quantidade × 3600 ÷ respawn`), e o spot é
   marcado com `*`.
3. **EXP/hora** = EXP por kill × kills/hora, com os rates do servidor.
4. **Rota** — o melhor spot é recalculado a cada nível; níveis consecutivos no
   mesmo lugar viram um trecho, e só se troca de mapa quando o novo ganha do
   atual por mais que a histerese (padrão 10%).

Flags que mudam o resultado: `--dps` (dano efetivo por segundo **no campo**, já
com ASPD, cast, erros e pausas de SP), `--seek` (segundos entre um alvo e o
próximo), `--crowding` (fatia do mapa que sobra para você), `--criterio`
(`base`, `job` ou `total`), `--base-rate`/`--job-rate` e `--dados`.

Essa parte ainda usa o catálogo YAML de `data/` — cujos valores são
**ilustrativos**, não os oficiais do servidor. Unificá-la com o índice do
rAthena é o próximo passo.

```yaml
monsters:
  - { id: 1268, name: Sleeper, level: 76, hp: 12000, base_exp: 7400, job_exp: 5200 }
maps:
  - id: ein_dun02
    name: Mina de Einbroch
    spawns:
      - { monster_id: 1268, amount: 40, respawn_seconds: 20 }
exp_table:            # nível -> EXP base para sair DESSE nível
  70: 1234567
```

Sem `exp_table` a rota ainda ranqueia os spots — só não estima horas.

## Limitações atuais

- Nomes de monstro e mapa em inglês/ID (ver "De onde vêm os dados").
- A dificuldade não modela quanto **você** aguenta apanhar: é o monstro que é
  medido, não a luta.
- Raça, tamanho e cartas não entram no cálculo — só o elemento.
- O `cacar` e a `rota` ainda usam bases diferentes.
- MVPs e chefes ficam fora de tudo.

## Desenvolvimento

```bash
pytest
ruff check .
```

## Licença

MIT
