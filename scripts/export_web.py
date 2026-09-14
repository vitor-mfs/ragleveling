"""Gera `web/data.js` a partir do índice local — os dados que a página web usa.

Rode depois de `ragleveling sync` (fonte rAthena):

    python scripts/export_web.py

Ou sobre o índice do Divine Pride, montado por `ragleveling dp-index`:

    python scripts/export_web.py --fonte dp

A página é estática: não há servidor para consultar o índice, então os monstros
que interessam (não-chefe, com EXP e com spawn) viajam junto com ela. As
habilidades vão pré-classificadas, porque a classificação não muda com o nível
do jogador — só a normalização do score, que é feita no navegador.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from ragleveling import dp_index  # noqa: E402
from ragleveling.config import get_settings  # noqa: E402
from ragleveling.difficulty import classificar_skills  # noqa: E402
from ragleveling.hunt import _MAPA_BLOQUEADO, _MAPA_INSTANCIA  # noqa: E402
from ragleveling.jobs import JOB_PROFILE, display_name  # noqa: E402
from ragleveling.rathena import carregar_indice  # noqa: E402

MAX_MAPAS = 6

_ESPACOS = re.compile(r"\s+")


def flags_do_mapa(map_id: str) -> int:
    """0 = campo aberto, 1 = instância, 2 = castelo/arena/quest."""
    if _MAPA_INSTANCIA.search(map_id):
        return 1
    if _MAPA_BLOQUEADO.match(map_id):
        return 2
    return 0


def juntar(rathena: dict, dp: dict) -> dict:
    """O Divine Pride manda onde tem o monstro; o rAthena entra onde não tem.

    Cada monstro sai marcado com a origem (`origem`: "dp" ou "rathena").
    """
    monstros = {m["id"]: {**m, "origem": "rathena"} for m in rathena["monsters"]}
    spawns = dict(rathena["spawns"])
    skills = dict(rathena["skills"])
    for monstro in dp["monsters"]:
        monstros[monstro["id"]] = {**monstro, "origem": "dp"}
        chave = str(monstro["id"])
        if chave in dp["spawns"]:
            spawns[chave] = dp["spawns"][chave]
        if chave in dp["skills"]:
            skills[chave] = dp["skills"][chave]
        else:
            skills.pop(chave, None)
    return {
        **rathena,
        "fonte": "ambas",
        "monsters": list(monstros.values()),
        "spawns": spawns,
        "skills": skills,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonte", choices=("rathena", "dp", "ambas"), default="rathena")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.fonte == "dp":
        indice = dp_index.carregar(settings)
    elif args.fonte == "rathena":
        indice = carregar_indice(settings)
    else:
        indice = juntar(carregar_indice(settings), dp_index.carregar(settings))
    skills = indice["skills"]

    monstros = []
    for monstro in indice["monsters"]:
        if monstro.get("boss") or not monstro.get("level") or not monstro.get("base_exp"):
            continue
        spawns_brutos = indice["spawns"].get(str(monstro["id"]), [])
        if not spawns_brutos:
            continue
        spawns = sorted(spawns_brutos, key=lambda s: s["amount"], reverse=True)[:MAX_MAPAS]
        categorias, peso = classificar_skills(skills.get(str(monstro["id"]), []))
        monstros.append(
            {
                "id": monstro["id"],
                "n": _ESPACOS.sub(" ", monstro["name"]).strip(),
                "l": monstro["level"],
                "hp": monstro.get("hp") or 0,
                "be": monstro.get("base_exp") or 0,
                "je": monstro.get("job_exp") or 0,
                "atk": monstro.get("attack") or 0,
                "def": monstro.get("defense") or 0,
                "mdef": monstro.get("magic_defense") or 0,
                "e": monstro.get("element", "Neutral"),
                "el": monstro.get("element_level") or 1,
                "r": monstro.get("race", "Formless"),
                "sz": monstro.get("size", "Medium"),
                "sw": round(peso, 1),
                "res": monstro.get("resist") or {},
                "src": "dp" if monstro.get("origem") == "dp" or indice.get("fonte") == "divine-pride" else "ra",
                "sc": categorias,
                "sp": [
                    [s["map"], s["amount"], s["respawn_ms"], flags_do_mapa(s["map"]), 1 if s.get("extra") else 0]
                    for s in spawns
                ],
            }
        )

    monstros.sort(key=lambda m: (m["l"], m["n"]))
    classes = sorted(
        ({"k": chave, "nome": display_name(chave), "perfil": perfil.value} for chave, perfil in JOB_PROFILE.items()),
        key=lambda c: c["nome"],
    )
    payload = {
        "fonte": indice.get("fonte", "rathena"),
        "gerado_em": indice.get("generated_at"),
        "monstros": monstros,
        "classes": classes,
        "attr_fix": indice["attr_fix"],
    }

    destino = RAIZ / "web" / "data.js"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        "window.RAGLEVELING_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    tamanho = destino.stat().st_size / 1024
    print(f"{len(monstros)} monstros -> {destino} ({tamanho:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
