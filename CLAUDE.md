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
pytest && ruff check .                       # 125 testes
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

## Estado atual

Índice local cobre **150–285** (816 monstros, 547 com spawn, 122 mapas, 205
skills com nome canônico). A página web tem os 405 não-chefe com spawn dessa
faixa. Níveis abaixo de 150 ainda não foram indexados — é decisão do dono,
pelo custo (~1.000 requisições) e pelo aviso da API sobre varredura.

## Próximos passos

1. Cobrir as faixas que faltam, se o dono decidir.
2. Migrar `spots`/`rota` para o índice: a `expPenaltyTable` já dá a EXP por
   nível; falta a tabela de EXP necessária por nível do jogador.
3. A coluna "Perigo" usa a classificação por nome `NPC_*`; nomes novos (ex.:
   `NPC_WIDE*`) podem precisar de regex novo em `difficulty.CATEGORIAS_SKILL`.

## Artefato

Versão web publicada como artefato privado em
https://claude.ai/artifact/BW9hLWn4vKytW7cmudrcAW — para atualizá-lo de outra
sessão, publique passando essa URL em `url`.

## Estilo

Código, commits, documentação e saída da CLI em **português**. Comentário só
onde explica uma decisão que o código não mostra. Nada de dado inventado.
