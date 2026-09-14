"""Classes: nome em PT-BR, perfil de dano e como aplicar elemento.

O perfil decide duas coisas: se a dificuldade do monstro olha DEF (físico) ou
MDEF (mágico), e qual é o meio prático de aplicar o elemento recomendado —
flecha para quem usa arco, magia para conjurador, carta/endow para corpo a corpo.

Classes híbridas (Ninja, Justiceiro Estelar, Sacerdote) recebem o perfil mais
comum para upar; `--perfil` na CLI sobrescreve quando o seu build foge disso.
"""

from __future__ import annotations

import difflib
import unicodedata
from enum import StrEnum


class Perfil(StrEnum):
    """Como o personagem causa dano."""

    MELEE = "melee"
    RANGED = "ranged"
    MAGIC = "magic"


#: Chave do rAthena -> perfil de dano.
JOB_PROFILE: dict[str, Perfil] = {
    # Iniciantes
    "Novice": Perfil.MELEE,
    "Super_Novice": Perfil.MAGIC,
    "Hyper_Novice": Perfil.MAGIC,
    "Acolyte": Perfil.MELEE,
    "Swordman": Perfil.MELEE,
    "Mage": Perfil.MAGIC,
    "Archer": Perfil.RANGED,
    "Merchant": Perfil.MELEE,
    "Thief": Perfil.MELEE,
    # Segunda classe
    "Knight": Perfil.MELEE,
    "Priest": Perfil.MAGIC,
    "Wizard": Perfil.MAGIC,
    "Blacksmith": Perfil.MELEE,
    "Hunter": Perfil.RANGED,
    "Assassin": Perfil.MELEE,
    "Crusader": Perfil.MELEE,
    "Monk": Perfil.MELEE,
    "Sage": Perfil.MAGIC,
    "Rogue": Perfil.MELEE,
    "Alchemist": Perfil.MELEE,
    "Bard": Perfil.RANGED,
    "Dancer": Perfil.RANGED,
    "Gunslinger": Perfil.RANGED,
    "Ninja": Perfil.MAGIC,
    "Taekwon": Perfil.MELEE,
    "Star_Gladiator": Perfil.MELEE,
    "Soul_Linker": Perfil.MAGIC,
    # Transclasses
    "Lord_Knight": Perfil.MELEE,
    "High_Priest": Perfil.MAGIC,
    "High_Wizard": Perfil.MAGIC,
    "Whitesmith": Perfil.MELEE,
    "Sniper": Perfil.RANGED,
    "Assassin_Cross": Perfil.MELEE,
    "Paladin": Perfil.MELEE,
    "Champion": Perfil.MELEE,
    "Professor": Perfil.MAGIC,
    "Stalker": Perfil.MELEE,
    "Creator": Perfil.MELEE,
    "Clown": Perfil.RANGED,
    "Gypsy": Perfil.RANGED,
    # Terceira classe
    "Rune_Knight": Perfil.MELEE,
    "Royal_Guard": Perfil.MELEE,
    "Sorcerer": Perfil.MAGIC,
    "Warlock": Perfil.MAGIC,
    "Arch_Bishop": Perfil.MAGIC,
    "Mechanic": Perfil.MELEE,
    "Genetic": Perfil.MELEE,
    "Guillotine_Cross": Perfil.MELEE,
    "Shadow_Chaser": Perfil.MELEE,
    "Ranger": Perfil.RANGED,
    "Minstrel": Perfil.RANGED,
    "Wanderer": Perfil.RANGED,
    "Sura": Perfil.MELEE,
    "Rebellion": Perfil.RANGED,
    "Summoner": Perfil.MAGIC,
    "Star_Emperor": Perfil.MELEE,
    "Soul_Reaper": Perfil.MAGIC,
    "Kagerou": Perfil.MELEE,
    "Oboro": Perfil.MAGIC,
    # Quarta classe
    "Dragon_Knight": Perfil.MELEE,
    "Imperial_Guard": Perfil.MELEE,
    "Meister": Perfil.MELEE,
    "Shadow_Cross": Perfil.MELEE,
    "Abyss_Chaser": Perfil.MELEE,
    "Arch_Mage": Perfil.MAGIC,
    "Elemental_Master": Perfil.MAGIC,
    "Cardinal": Perfil.MAGIC,
    "Inquisitor": Perfil.MELEE,
    "Windhawk": Perfil.RANGED,
    "Troubadour": Perfil.RANGED,
    "Trouvere": Perfil.RANGED,
    "Sky_Emperor": Perfil.MELEE,
    "Soul_Ascetic": Perfil.MAGIC,
    "Spirit_Handler": Perfil.MAGIC,
    "Night_Watch": Perfil.RANGED,
    "Biolo": Perfil.MELEE,
}

#: Apelidos em PT-BR e variações comuns -> chave do rAthena.
JOB_ALIASES: dict[str, str] = {
    "aprendiz": "Novice",
    "novico": "Acolyte",
    "acolito": "Acolyte",
    "espadachim": "Swordman",
    "mago": "Mage",
    "arqueiro": "Archer",
    "mercador": "Merchant",
    "gatuno": "Thief",
    "super aprendiz": "Super_Novice",
    "cavaleiro": "Knight",
    "sacerdote": "Priest",
    "bruxo": "Wizard",
    "ferreiro": "Blacksmith",
    "cacador": "Hunter",
    "assassino": "Assassin",
    "templario": "Crusader",
    "cruzado": "Crusader",
    "monge": "Monk",
    "sabio": "Sage",
    "arruaceiro": "Rogue",
    "alquimista": "Alchemist",
    "bardo": "Bard",
    "odalisca": "Dancer",
    "justiceiro": "Gunslinger",
    "ninja": "Ninja",
    "taekwon": "Taekwon",
    "justiceiro estelar": "Star_Gladiator",
    "espiritualista": "Soul_Linker",
    "lorde": "Lord_Knight",
    "lord knight": "Lord_Knight",
    "sumo sacerdote": "High_Priest",
    "arquimago": "High_Wizard",
    "mestre ferreiro": "Whitesmith",
    "sniper": "Sniper",
    "assassino cruel": "Assassin_Cross",
    "paladino": "Paladin",
    "campeao": "Champion",
    "professor": "Professor",
    "stalker": "Stalker",
    "criador": "Creator",
    "menestrel": "Clown",
    "cigana": "Gypsy",
    "cavaleiro runico": "Rune_Knight",
    "runico": "Rune_Knight",
    "feiticeiro": "Sorcerer",
    "arcebispo": "Arch_Bishop",
    "mecanico": "Mechanic",
    "cruz da guilhotina": "Guillotine_Cross",
    "guarda real": "Royal_Guard",
    "trovador": "Minstrel",
    "maestro": "Minstrel",
    "andarilha": "Wanderer",
    "sura": "Sura",
    "geneticista": "Genetic",
    "sombra sinistra": "Shadow_Chaser",
    "renegado": "Shadow_Chaser",
    "ranger": "Ranger",
    "warlock": "Warlock",
    "rebelde": "Rebellion",
    "invocador": "Summoner",
    "doram": "Summoner",
    "imperador estelar": "Star_Emperor",
    "ceifador de almas": "Soul_Reaper",
    "kagerou": "Kagerou",
    "oboro": "Oboro",
    "cavaleiro dragao": "Dragon_Knight",
    "dragon knight": "Dragon_Knight",
    "guarda imperial": "Imperial_Guard",
    "mestre": "Meister",
    "meister": "Meister",
    "cruz sombria": "Shadow_Cross",
    "abismal": "Abyss_Chaser",
    "cacador do abismo": "Abyss_Chaser",
    "grao mago": "Arch_Mage",
    "arquimago supremo": "Arch_Mage",
    "mestre elemental": "Elemental_Master",
    "cardeal": "Cardinal",
    "inquisidor": "Inquisitor",
    "falcao do vento": "Windhawk",
    "trovador supremo": "Troubadour",
    "trouvere": "Trouvere",
    "imperador celeste": "Sky_Emperor",
    "asceta espiritual": "Soul_Ascetic",
    "hiper aprendiz": "Hyper_Novice",
    "guardiao espiritual": "Spirit_Handler",
    "vigia noturno": "Night_Watch",
    "biologo": "Biolo",
    "biolo": "Biolo",
}

#: Classes que aplicam elemento por munição, não por carta/endow.
_MUNICAO = {"Gunslinger", "Rebellion", "Night_Watch"}
_ARCO = {"Archer", "Hunter", "Sniper", "Ranger", "Windhawk"}


def normalize(texto: str) -> str:
    """Minúsculas, sem acento, com espaços e underscores unificados."""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(ch for ch in decomposto if not unicodedata.combining(ch))
    limpo = sem_acento.replace("_", " ").replace("-", " ").strip().casefold()
    return " ".join(limpo.split())


def canonical_job_key(nome: str) -> str | None:
    """Chave do rAthena para um nome digitado, ou None se não reconhecer."""
    if not nome or not nome.strip():
        return None
    cru = normalize(nome)
    formas = {normalize(chave): chave for chave in JOB_PROFILE}
    if cru in formas:
        return formas[cru]
    if cru in JOB_ALIASES:
        return JOB_ALIASES[cru]
    # "arcebispo trans", "Rune Knight T" — o perfil de dano é o mesmo da base.
    for marcador in ("transclasse", "trans", "t"):
        sufixo = " " + marcador
        if cru.endswith(sufixo):
            return canonical_job_key(cru[: -len(sufixo)])
    return None


def sugerir(nome: str, limite: int = 3) -> list[str]:
    """Classes parecidas com o que foi digitado, para a mensagem de erro."""
    candidatos = {normalize(chave): chave for chave in JOB_PROFILE}
    candidatos.update(JOB_ALIASES)
    achados = difflib.get_close_matches(normalize(nome), list(candidatos), n=limite, cutoff=0.5)
    vistos: list[str] = []
    for achado in achados:
        chave = candidatos[achado]
        if chave not in vistos:
            vistos.append(chave)
    return vistos


def perfil_de(chave: str) -> Perfil:
    """Perfil de dano de uma classe já canônica."""
    return JOB_PROFILE.get(chave, Perfil.MELEE)


def display_name(chave: str) -> str:
    """Nome PT-BR mais comum para uma chave."""
    for alias, alvo in JOB_ALIASES.items():
        if alvo == chave:
            return alias.title()
    return chave.replace("_", " ")


def como_aplicar_elemento(chave: str, elemento_pt: str) -> str:
    """Frase curta dizendo como essa classe coloca o elemento no dano."""
    perfil = perfil_de(chave)
    if perfil is Perfil.MAGIC:
        return f"magia de {elemento_pt}"
    if chave in _MUNICAO:
        return f"munição de {elemento_pt}"
    if chave in _ARCO or perfil is Perfil.RANGED:
        return f"flecha de {elemento_pt}"
    return f"carta de {elemento_pt} na arma ou Encantar Arma"
