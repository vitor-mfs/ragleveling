# ragleveling — contexto do projeto

Ferramenta para decidir **onde upar** no Ragnarok Online Renewal (servidor LATAM).
Você informa nível e classe; a saída são os monstros da faixa, do mais fácil ao
mais difícil, com o mapa de cada um e o elemento a usar contra ele.

## Como rodar

```bash
uv venv && uv pip install -e ".[dev]"
ragleveling sync                                          # baixa os dados do rAthena (~30 s)
ragleveling cacar --nivel 60 --classe "Cavaleiro Rúnico"
pytest && ruff check .                                    # 121 testes
```

## Arquitetura

| Módulo | Responsabilidade |
| --- | --- |
| `rathena.py` | Baixa e parseia mob_db, mob_skill_db, attr_fix e os 103 scripts de spawn; monta `~/.cache/ragleveling/index.json` |
| `divinepride.py` | Cliente da API do Divine Pride (1 req/s, cache em disco) e gravação do complemento de spawns |
| `elements.py` | Tabela `attr_fix`: qual elemento rende mais contra cada defesa |
| `difficulty.py` | Score de HP, DEF/MDEF, ataque e habilidades, normalizado **dentro da consulta** |
| `jobs.py` | Classe PT-BR → chave do rAthena, perfil de dano, como aplicar o elemento |
| `hunt.py` | O fluxo principal: filtra a faixa, ranqueia, monta os alvos |
| `exp.py`, `router.py`, `catalog.py` | Penalidade de EXP e a rota nível a nível (parte antiga, ainda sobre catálogo YAML próprio) |
| `web/` + `scripts/export_web.py` | A mesma consulta rodando no navegador sobre dados exportados |

## Decisões já tomadas

- **Faixa padrão −5 a +15** do base level (zona sem penalidade até o bônus de 150%).
- **Dificuldade** = HP + DEF/MDEF + ataque + nº de habilidades + peso das perigosas,
  min-max dentro dos candidatos: 0 é o mais fácil daquela lista, 100 o mais difícil.
- **Classe** decide se o ranking olha DEF ou MDEF e como aplicar o elemento
  (magia / flecha / munição / carta-endow). `--perfil` sobrescreve.
- Sempre fora: chefes, MVPs, instâncias, castelos/arenas/quest e spawns com menos
  de 5 exemplares no mapa.
- Licença: projeto MIT; `web/data.js` é derivado do rAthena (GPL-3.0) e está
  versionado por decisão do dono do repo, que é privado. Se o repo virar público
  ou o artefato for compartilhado, isso precisa ser resolvido —
  `git rm --cached web/data.js` + `.gitignore` resolve, o arquivo é regenerável.

## Onde as coisas podem enganar

- **Duas formas de linha de spawn** no rAthena: com e sem coordenadas. Ler só uma
  delas deixava todo monstro de 195+ sem mapa (o teto era 194). Há testes de
  regressão em `tests/test_rathena.py`.
- **Monstros órfãos**: 63 monstros de 150+ existem no `mob_db` mas nenhum script
  declara onde nascem — inclusive os do `clock_01` (253+). `ragleveling faltando`
  lista quem são; `data/spawns_extra.yaml` complementa à mão ou via `dp-spawns`.
- **O Divine Pride lista o mesmo mapa várias vezes** (70 com respawn de 5 s,
  mais três grupos de 5 com respawn de 10 s). `agregar_spawns` soma as
  quantidades e guarda o menor respawn; sem isso só a última linha sobrevivia.
- **Rate limit**: 1,0 s exato ainda leva 429. O intervalo padrão é 1,5 s
  (`RAGLEVELING_DP_RATE`) e o cliente espera 5 s, 15 s e 30 s antes de desistir.
- **Nome localizado não existe na API**: `name` vem em coreano em qualquer
  `server`. A página web mostra em inglês, o mesmo que o rAthena já dá.

## Estado atual

O ambiente tem acesso ao `divine-pride.net`, a API foi validada e os spawns que
faltavam já estão importados em `data/spawns_extra.yaml`: 26 monstros em 6
mapas, entre eles os 253+ de `nif_dun02`. Os outros 37 órfãos são mobs de
instância (`Senior *`, `MD_*`) que realmente não nascem em mapa aberto.

## Próximos passos

1. **Usar o `expPenaltyTable` do Divine Pride** no lugar da tabela genérica de
   `exp.py`: ele dá a penalidade real por nível de jogador, monstro a monstro.
2. **Usar `elementResistances`** no lugar do `attr_fix`: já vem calculada e
   embute modificadores por monstro que a tabela genérica não tem.
3. **Busca por faixa de nível** na listagem `/database/monster`, para alcançar o
   que nem existe no `mob_db`.
4. Migrar `spots`/`rota` do catálogo YAML para o índice, e a `exp_table` oficial
   para estimar horas de verdade.

Nomes em PT-BR continuam sem fonte: a API só devolve coreano.

## Artefato

A versão web está publicada como artefato privado em
https://claude.ai/artifact/BW9hLWn4vKytW7cmudrcAW
Para atualizá-lo de outra sessão, publique passando essa URL em `url` —
sem isso um artefato novo é criado em vez de atualizar esse.

## Estilo

Código, commits, documentação e saída da CLI em **português**. Comentário só
onde explica uma decisão que o código não mostra. Nada de dado inventado: número
que não pôde ser verificado é marcado como tal.
