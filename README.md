# ragleveling

Criador de **rotas de level up** para Ragnarok Online Renewal.

Você informa o nível do personagem e o quanto ele mata por segundo; o
ragleveling cruza isso com a fórmula de EXP do Renewal, os monstros e os
spawns de cada mapa, e devolve onde upar — nível por nível, do atual até o alvo.

## Como ele pensa

1. **Penalidade de nível** — a EXP de um kill é multiplicada pela tabela do
   Renewal, em função de `nível do monstro - nível do personagem`: monstro muito
   abaixo rende 10%, monstro 15 níveis acima rende 150% (`src/ragleveling/exp.py`).
2. **Ritmo real de kills** — `HP do monstro ÷ DPS` dá o tempo de kill; somado ao
   tempo de deslocamento entre alvos, vira kills/hora. Se o mapa não repõe
   monstros nesse ritmo, o teto passa a ser o respawn (`amount × 3600 ÷ respawn`),
   e o spot é marcado com `*`.
3. **EXP/hora** = EXP por kill × kills/hora, com os rates do servidor aplicados.
4. **Rota** — o melhor spot é recalculado a cada nível; níveis consecutivos no
   mesmo lugar viram um trecho. A troca de mapa só acontece quando o novo spot
   ganha do atual por mais que a histerese (padrão 10%), para a rota não mandar
   você mudar de mapa por 1% de ganho.

Os números mostrados em cada trecho da rota são os do **nível inicial** do trecho.

## Instalação

```bash
uv venv && uv pip install -e ".[dev]"
```

## Uso

Ranquear spots para o nível atual:

```bash
ragleveling spots --nivel 60 --dps 800
```

Montar a rota até o nível alvo:

```bash
ragleveling rota --de 15 --ate 99 --dps 800 --criterio base
```

Opções que mudam o resultado:

| Flag | O que faz |
| --- | --- |
| `--dps` | Dano efetivo por segundo **no campo** — já contando ASPD, cast, erros e pausas de SP. É a entrada que mais mexe no resultado. |
| `--seek` | Segundos andando/procurando entre um alvo e o próximo (padrão 2). |
| `--crowding` | Fatia do mapa que sobra para você: `1.0` mapa vazio, `0.5` dividindo com outro. |
| `--gap` | Diferença máxima de nível aceita (padrão 25) — segura a rota longe de mapa que te mata. |
| `--criterio` | `base`, `job` ou `total`: o que a rota otimiza. |
| `--histerese` | Ganho mínimo para valer uma troca de mapa (padrão `0.10`). |
| `--base-rate` / `--job-rate` | Rates do servidor. LATAM oficial é 1x. |
| `--dados` | Arquivo ou pasta de catálogo YAML (padrão: `./data`). |

## Catálogo

`data/exemplo.yaml` é uma **demonstração**: os valores de EXP, HP e respawn são
ilustrativos, não são os oficiais do servidor. Antes de confiar numa rota,
troque por dados conferidos no [Divine Pride](https://www.divine-pride.net) ou
pelo dump do seu servidor.

```yaml
monsters:
  - id: 1268
    name: Sleeper
    level: 76
    hp: 12000
    base_exp: 7400
    job_exp: 5200
    mvp: false        # MVPs são ignorados pela rota

maps:
  - id: ein_dun02
    name: Mina de Einbroch
    spawns:
      - { monster_id: 1268, amount: 40, respawn_seconds: 20 }

exp_table:            # nível -> EXP base para sair DESSE nível
  70: 1234567
```

Sem `exp_table` a rota ainda ranqueia os spots — só não estima horas.
O catálogo pode ser um arquivo único ou uma pasta com vários YAMLs, que são
somados.

## Limitações atuais

- Não modela dano recebido, elemento, raça, tamanho ou skills em área — o `--dps`
  é o único proxy da sua capacidade de matar.
- Não considera custo de consumíveis, teleporte, nem EXP de quest.
- MVPs ficam fora da rota.
- A tabela de penalidade do Renewal é o padrão do rAthena; confirme contra o seu
  servidor antes de usar em decisão séria.

## Desenvolvimento

```bash
pytest
ruff check .
```

## Licença

MIT
