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
- **A normalização do payload do Divine Pride nunca foi validada** contra o
  serviço real: a rede das sessões anteriores não alcançava o site. Ela aceita
  vários nomes por campo e não quebra por campo ausente, mas é palpite até
  alguém conferir. `ragleveling dp-check <id>` mostra o que chegou.
- **Unidade do respawn** do Divine Pride é ambígua (s ou ms). Assumimos ms a
  partir de 1000. `dp-check` mostra o valor cru ao lado do convertido.

## Próximo passo (é aqui que paramos)

O ambiente foi configurado com **Network access: Custom** incluindo
`divine-pride.net`, para que a sessão possa ler o site direto. Na ordem:

1. Confirmar o acesso: `curl -s -o /dev/null -w '%{http_code}' https://www.divine-pride.net/`
2. `ragleveling dp-check 20940` (Blue Moon Loli Ruri) — conferir o payload real e
   corrigir `_CHAVES_*` / `_respawn_em_segundos` em `divinepride.py` se preciso.
3. `ragleveling dp-spawns --nivel-min 200` — importar os mapas que faltam e
   confirmar que `cacar --nivel 250` passa a devolver os monstros do `clock_01`.
4. Implementar a busca por faixa de nível na listagem `/database/monster`, para
   alcançar também o que nem existe no `mob_db`.
5. Nomes em PT-BR de monstro e mapa (a API devolve no idioma do servidor `bRO`).

Depois disso, duas dívidas antigas: migrar `spots`/`rota` do catálogo YAML para o
índice do rAthena, e a `exp_table` oficial para estimar horas de verdade.

## Artefato

A versão web está publicada como artefato privado em
https://claude.ai/code/artifact/550d508f-d8fa-4c1f-9fb2-98b8332050fb
Para atualizá-lo de outra sessão, publique passando essa URL em `url` —
sem isso um artefato novo é criado em vez de atualizar esse.

## Estilo

Código, commits, documentação e saída da CLI em **português**. Comentário só
onde explica uma decisão que o código não mostra. Nada de dado inventado: número
que não pôde ser verificado é marcado como tal.
