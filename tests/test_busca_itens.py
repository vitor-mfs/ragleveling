import pytest

from ragleveling import busca_itens as b

# As linhas abaixo são cópias de descrições e scripts reais do LATAM no Divine Pride.

CARTA_ACIDUS = """Dano físico contra as raças Bruto e Doram +5%.
--------------------------
Conjunto
[Carta Ferus Esqueleto]
Dano físico contra as raças Bruto e Doram +5% adicional.
--------------------------
Tipo: Carta
Equipa em: Aces. Direito
Peso: 1"""

CARTA_CAIDOS = """HP máx. +500.
SP máx. +50.
Resistência a raça Anjo -50%.
-------------------------
Conjunto
[Carta Guerreiro Orc]
Resistência as raças Humano e Humanoide +15%.
-------------------------
Conjunto
[Carta Familiar]
ATQ +15.
Dano físico contra oponentes de propriedade Sombrio +20%.
-------------------------
Tipo: Carta"""

ACOITE = """Arma purificada que contém o poder da fé verdadeira.
--------------------------
A cada 3 refinos:
ATQ +12.
--------------------------
Dano de [Temporal de Flechas] +10%.
Refino +7 ou mais:
Dano de [Temporal de Flechas] +20% adicional.
Refino +9 ou mais:
Recarga de [Temporal de Flechas] -2,5 segundos.
Refino +12 ou mais:
Dano físico à distância +15%.
--------------------------
Grau D ou mais:
Refino +11 ou mais:
Dano físico contra oponentes de todas as propriedades +15%.
Grau C ou mais:
Dano de [Temporal de Flechas] +15% adicional."""

CRUZ_DIVINA = """DES +4.
Resistência as raças Morto-Vivo e Demônio +15%.
-------------------------
Conjunto
[Anel Espiritual]
DES +2 adicional.
Dano mágico +10%.
Resistência as raças Morto-Vivo e Demônio +10% adicional."""


def _e(descricao):
    return b.efeitos_da_descricao(descricao)


# --- interpretar ---


@pytest.mark.parametrize(
    ("frase", "efeito", "categoria", "alvos"),
    [
        ("aumentar dano em insetos", "aumentar", "raca", ("inseto",)),
        ("reduzir dano de dragões", "reduzir", "raca", ("dragao",)),
        ("Reduzir dano de Dragões", "reduzir", "raca", ("dragao",)),
        ("aumentar dano contra demônios", "aumentar", "raca", ("demonio",)),
        ("aumentar dano em mortos-vivos", "aumentar", "raca", ("morto-vivo",)),
        ("aumentar dano em humanoides", "aumentar", "raca", ("humanoide",)),
        ("aumentar dano em humanos", "aumentar", "raca", ("humano",)),
        ("aumentar dano em insetos e dragões", "aumentar", "raca", ("inseto", "dragao")),
        ("aumentar resistência a dragões", "reduzir", "raca", ("dragao",)),
        ("proteção contra anjos", "reduzir", "raca", ("anjo",)),
        ("aumentar dano em monstros de tamanho grande", "aumentar", "tamanho", ("grande",)),
        ("aumentar dano contra monstros pequenos", "aumentar", "tamanho", ("pequeno",)),
        ("aumentar dano contra propriedade fogo", "aumentar", "elemento", ("fogo",)),
        ("reduzir dano de fogo", "reduzir", "elemento", ("fogo",)),
        ("aumentar dano em monstros sagrados", "aumentar", "elemento", ("sagrado",)),
        ("reduzir dano de propriedade morto-vivo", "reduzir", "elemento", ("maldito",)),
        ("aumentar dano da habilidade lâminas retalhadoras", "aumentar", "habilidade", ("laminas retalhadoras",)),
        ("aumentar dano de Lâminas Retalhadoras", "aumentar", "habilidade", ("laminas retalhadoras",)),
        ("aumentar dano da skill Temporal de Flechas", "aumentar", "habilidade", ("temporal de flechas",)),
    ],
)
def test_interpretar(frase, efeito, categoria, alvos):
    consulta = b.interpretar(frase)
    assert (consulta.efeito, consulta.categoria, consulta.alvos) == (efeito, categoria, alvos)


def test_interpretar_dano_fisico_e_magico():
    assert b.interpretar("aumentar dano mágico em demônios").dano == "magico"
    assert b.interpretar("aumentar dano físico em demônios").dano == "fisico"
    assert b.interpretar("aumentar dano em demônios").dano == "qualquer"


@pytest.mark.parametrize("frase", ["", "   ", "dano em insetos", "aumentar dano", "aumentar a sorte"])
def test_interpretar_recusa_o_que_nao_entende(frase):
    with pytest.raises(b.FraseNaoEntendida):
        b.interpretar(frase)


def test_humano_nao_vira_humanoide():
    assert b.interpretar("aumentar dano em humanoides").alvos == ("humanoide",)
    assert b.interpretar("aumentar dano em humanos").alvos == ("humano",)


# --- efeitos da descrição ---


def test_dano_contra_varias_racas():
    efeito = _e(CARTA_ACIDUS)[0]
    assert (efeito.tipo, efeito.categoria, efeito.alvos, efeito.valor, efeito.dano) == (
        "dano", "raca", ("bruto", "doram"), 5.0, "fisico"
    )  # fmt: skip
    assert efeito.condicao == ""


def test_linha_de_conjunto_fica_com_a_condicao():
    base, conjunto = _e(CARTA_ACIDUS)
    assert base.condicao == "" and conjunto.condicao == "Conjunto"
    assert conjunto.texto.endswith("adicional.")


def test_nome_do_outro_item_do_conjunto_nao_vira_efeito():
    assert all("[" not in e.texto for e in _e(CARTA_ACIDUS))


def test_resistencia_negativa_e_fraqueza():
    anjo = _e(CARTA_CAIDOS)[0]
    assert (anjo.tipo, anjo.categoria, anjo.alvos, anjo.valor) == ("resistencia", "raca", ("anjo",), -50.0)


def test_resistencia_a_varias_racas():
    efeito = _e(CRUZ_DIVINA)[0]
    assert (efeito.tipo, efeito.alvos, efeito.valor) == ("resistencia", ("morto-vivo", "demonio"), 15.0)


def test_dano_contra_propriedade_e_tamanho():
    efeitos = _e(CARTA_CAIDOS)
    sombrio = next(e for e in efeitos if e.categoria == "elemento")
    assert (sombrio.alvos, sombrio.valor, sombrio.condicao) == (("sombrio",), 20.0, "Conjunto")
    pequeno = _e("Dano físico contra oponentes de tamanho Pequeno +15%.")[0]
    assert (pequeno.categoria, pequeno.alvos, pequeno.valor) == ("tamanho", ("pequeno",), 15.0)


def test_dano_contra_todas_as_racas_vale_para_qualquer_raca():
    efeito = _e("Dano físico contra todas as raças de monstros +3%.")[0]
    assert (efeito.categoria, efeito.alvos) == ("raca", (b.TODOS,))


def test_dano_de_habilidade_entre_colchetes():
    efeito = _e("Dano de [Lâminas Retalhadoras] +10%.")[0]
    assert (efeito.categoria, efeito.alvos, efeito.valor) == ("habilidade", ("laminas retalhadoras",), 10.0)


def test_condicoes_de_refino_e_grau_se_aninham_e_se_substituem():
    efeitos = _e(ACOITE)
    habilidade = [e for e in efeitos if e.categoria == "habilidade"]
    assert [(e.valor, e.condicao) for e in habilidade] == [
        (10.0, ""),
        (20.0, "Refino +7 ou mais"),
        (15.0, "Grau C ou mais"),
    ]
    todas = next(e for e in efeitos if e.categoria == "elemento")
    assert todas.condicao == "Grau D ou mais · Refino +11 ou mais"
    distancia = next(e for e in efeitos if e.categoria == "geral")
    assert (distancia.alvos, distancia.condicao) == (("distancia",), "Refino +12 ou mais")


def test_linha_que_nao_e_efeito_conhecido_e_ignorada():
    assert (
        _e("HP máx. +500.\nTipo: Carta\nPeso: 1\nAo receber danos físicos ou mágicos, 5% de chance de ativar [X].")
        == []
    )
    assert _e("") == []


def test_dano_fisico_e_magico_na_mesma_linha_vale_para_os_dois():
    efeito = _e("Dano físico e mágico contra as raças Bruto e Inseto +3%.")[0]
    assert (efeito.dano, efeito.alvos, efeito.valor) == ("qualquer", ("bruto", "inseto"), 3.0)
    assert _e("Dano físico e mágico contra os tamanhos Médio e Grande +15%.")[0].alvos == ("medio", "grande")
    assert _e("Dano físico e mágico contra todos os tamanhos +5%.")[0].alvos == (b.TODOS,)


def test_varias_habilidades_na_mesma_linha():
    efeito = _e("Dano de [Lâminas Destruidoras] e [Lâminas Retalhadoras] +10% adicional.")[0]
    assert efeito.alvos == ("laminas destruidoras", "laminas retalhadoras")
    assert _e("Dano de [Retaliação], [Lâminas de Loki] e [Lâminas Retalhadoras] +5%.")[0].alvos == (
        "retaliacao",
        "laminas de loki",
        "laminas retalhadoras",
    )


def test_dano_dos_ataques_de_uma_propriedade():
    efeito = _e("Dano mágico de propriedade Veneno, Maldito, Sombrio e Fantasma +5%.")[0]
    assert (efeito.categoria, efeito.dano) == ("elemento-ataque", "magico")
    assert set(efeito.alvos) == {"veneno", "maldito", "sombrio", "fantasma"}
    assert _e("Dano mágico de todas as propriedades +5%.")[0].alvos == (b.TODOS,)


@pytest.mark.parametrize(
    ("linha", "alvos"),
    [
        ("Dano físico +25%.", ("fisico", "distancia", "corpo-a-corpo")),
        ("Dano mágico +10%.", ("magico",)),
        ("Dano crítico +20%.", ("critico",)),
        ("Dano físico à distância +11%.", ("distancia",)),
        ("Dano físico corpo a corpo +6%.", ("corpo-a-corpo",)),
        ("Dano físico à distância e corpo a corpo +2%.", ("distancia", "corpo-a-corpo")),
        ("Dano físico e mágico +4%.", ("fisico", "distancia", "corpo-a-corpo", "magico")),
    ],
)
def test_dano_geral(linha, alvos):
    efeito = _e(linha)[0]
    assert (efeito.categoria, efeito.alvos) == ("geral", alvos)


def test_dano_geral_negativo_nao_atende():
    assert not b.atende(_e("Dano mágico -10%.")[0], b.interpretar("aumentar dano mágico"))


# --- efeitos dos scripts ---


@pytest.mark.parametrize(
    ("texto", "tipo", "categoria", "alvos", "valor", "dano"),
    [
        ("Increase damage dealt to Insect race monsters by 10%", "dano", "raca", ("inseto",), 10, "fisico"),
        ("Increase damage dealt to Demi-Human race monsters by 5%", "dano", "raca", ("humanoide",), 5, "fisico"),
        ("Increase damage dealt to Human Player race monsters by 5%", "dano", "raca", ("humano",), 5, "fisico"),
        ("Increase damage dealt to Doram Player race monsters by 5%", "dano", "raca", ("doram",), 5, "fisico"),
        ("Increase damage dealt to All race monsters by 5%", "dano", "raca", (b.TODOS,), 5, "fisico"),
        ("Increases magic attack damage to Demon race by 75%", "dano", "raca", ("demonio",), 75, "magico"),
        ("Increases magic attack damage to All race by 5%", "dano", "raca", (b.TODOS,), 5, "magico"),
        ("Increase physical damage dealt on Small size monsters by 15%", "dano", "tamanho", ("pequeno",), 15, "fisico"),
        ("Increase damage dealt to a Dark property by 25%", "dano", "elemento", ("sombrio",), 25, "qualquer"),
        ("Increase damage dealt to a Undead property by 5%", "dano", "elemento", ("maldito",), 5, "qualquer"),
        ("Reduce damage dealt to a Holy property by 10%", "dano", "elemento", ("sagrado",), -10, "qualquer"),
        ("Reduce damage taken from Undead monsters by 15%", "resistencia", "raca", ("morto-vivo",), 15, "qualquer"),
        ("Increase damage taken from Angel monsters by 50%", "resistencia", "raca", ("anjo",), -50, "qualquer"),
        ("Increase damage taken from All monsters by 5%", "resistencia", "raca", (b.TODOS,), -5, "qualquer"),
        ("Reduce damage taken from a Dark property by 3%", "resistencia", "elemento", ("sombrio",), 3, "qualquer"),
        ("Increase damage of WM_SEVERE_RAINSTORM_MELEE by 10%", "dano", "habilidade", ("wm_severe_rainstorm_melee",), 10, "qualquer"),  # noqa: E501
    ],
)  # fmt: skip
def test_efeitos_dos_scripts(texto, tipo, categoria, alvos, valor, dano):
    (efeito,) = b.efeitos_dos_scripts([texto])
    assert (efeito.tipo, efeito.categoria, efeito.alvos, efeito.valor, efeito.dano) == (
        tipo,
        categoria,
        alvos,
        valor,
        dano,
    )
    assert efeito.fonte == "script" and efeito.condicao == ""


@pytest.mark.parametrize(
    "texto",
    [
        "STR +1",
        "Max HP +temp * 10",
        "Increases magical damage taken from Holy property monsters by 10%",  # o sentido não está claro: fica de fora
        "Pierces 5 + Refine% of DEF on Dragon race targets when performing a physical attack",
        "Increases experience for a All monster race by 5%",
    ],
)
def test_script_que_a_busca_nao_conhece_e_ignorado(texto):
    assert b.efeitos_dos_scripts([texto]) == []


def test_scripts_aceitam_texto_lista_e_objetos():
    frase = "Increase damage dealt to Insect race monsters by 10%"
    for formato in (frase, [frase], [{"text": frase}], [{"functionId": 21, "description": frase, "x": 1}]):
        assert len(b.efeitos_dos_scripts(formato)) == 1, formato
    assert b.efeitos_dos_scripts(None) == []
    assert b.efeitos_dos_scripts([{"id": 3}]) == []


# --- buscar ---


def _item(item_id, nome, descricao="", scripts=(), locais=()):
    return {"id": item_id, "name": nome, "description": descricao, "scripts": list(scripts), "locations": list(locais)}


def _indice():
    return {
        "items": [
            _item(1, "Carta Inseto", "Dano físico contra a raça Inseto +20%.", locais=["armadura"]),
            _item(2, "Luva", scripts=["Increase damage dealt to Insect race monsters by 10%"], locais=["acessorio"]),
            _item(3, "Capa", "Dano físico contra todas as raças de monstros +3%.", locais=["capa"]),
            _item(4, "Elmo", "Refino +9 ou mais:\nDano físico contra a raça Inseto +40%.", locais=["topo"]),
            _item(5, "Anel Fraco", "Resistência a raça Inseto -10%.", locais=["acessorio"]),
            _item(6, "Escudo", "Resistência as raças Dragão e Inseto +15%.", locais=["escudo"]),
            _item(7, "Magia", "Dano mágico contra a raça Inseto +30%.", locais=["meio"]),
            _item(8, "Outra Coisa", "Dano físico contra a raça Dragão +50%."),
        ]
    }


def _ids(resultados):
    return [r.item["id"] for r in resultados]


def test_ordena_do_maior_bonus_e_deixa_o_condicionado_para_o_fim():
    achados = b.buscar(_indice(), "aumentar dano em insetos")
    # 30, 20, 10, 3 sem condição; o Elmo (40) só com refino +9, então por último.
    assert _ids(achados) == [7, 1, 2, 3, 4]
    assert achados[-1].efeito.condicao == "Refino +9 ou mais"


def test_resistencia_nao_entra_em_aumentar_dano_nem_o_contrario():
    assert 5 not in _ids(b.buscar(_indice(), "aumentar dano em insetos"))
    assert _ids(b.buscar(_indice(), "reduzir dano de insetos")) == [6]  # o Anel Fraco tem -10: é fraqueza
    assert _ids(b.buscar(_indice(), "reduzir dano de dragões")) == [6]


def test_dano_fisico_e_magico_separam_os_resultados():
    assert _ids(b.buscar(_indice(), "aumentar dano mágico em insetos")) == [7]
    assert _ids(b.buscar(_indice(), "aumentar dano físico em insetos")) == [1, 2, 3, 4]


def test_filtra_por_local():
    assert _ids(b.buscar(_indice(), "aumentar dano em insetos", local="topo")) == [4]
    assert b.buscar(_indice(), "aumentar dano em insetos", local="baixo") == []


def test_limite():
    assert _ids(b.buscar(_indice(), "aumentar dano em insetos", limite=2)) == [7, 1]


def test_o_script_que_repete_a_descricao_nao_vira_efeito_extra():
    item = _item(
        9, "Dupla", "Dano físico contra a raça Inseto +10%.", ["Increase damage dealt to Insect race monsters by 10%"]
    )
    (achado,) = b.buscar({"items": [item]}, "aumentar dano em insetos")
    assert achado.efeito.fonte == "descricao" and achado.tambem == ()


def test_efeito_condicionado_diferente_aparece_em_tambem():
    item = _item(
        9,
        "Conjunto",
        "Dano físico contra a raça Inseto +10%.\n----\nConjunto\n[Outro]\nDano físico contra a raça Inseto +20%.",
    )
    (achado,) = b.buscar({"items": [item]}, "aumentar dano em insetos")
    assert (achado.valor, achado.efeito.condicao) == (10.0, "")
    assert [(e.valor, e.condicao) for e in achado.tambem] == [(20.0, "Conjunto")]


def test_habilidade_pelo_nome_em_portugues_da_descricao():
    item = _item(1, "Carta", "Dano de [Lâminas Retalhadoras] +20%.")
    for frase in ("aumentar dano da habilidade lâminas retalhadoras", "aumentar dano da habilidade lamina retalhadora"):
        assert _ids(b.buscar({"items": [item]}, frase)) == [1]
    assert b.buscar({"items": [item]}, "aumentar dano da habilidade Temporal de Flechas") == []


def test_habilidade_pelo_nome_interno_dos_scripts_precisa_do_apelido():
    item = _item(1, "Luva", scripts=["Increase damage of GC_CROSSRIPPERSLASHER by 20%"])
    sem = b.interpretar("aumentar dano da habilidade lâminas retalhadoras")
    assert b.buscar({"items": [item]}, sem) == []
    com = b.Consulta(sem.efeito, sem.categoria, sem.alvos, sem.dano, apelidos=("GC_CROSSRIPPERSLASHER",))
    assert _ids(b.buscar({"items": [item]}, com)) == [1]


def test_item_sem_descricao_nem_scripts_nao_quebra():
    assert b.buscar({"items": [{"id": 1, "name": "Vazio"}]}, "aumentar dano em insetos") == []
    assert b.buscar({}, "aumentar dano em insetos") == []


@pytest.mark.parametrize(
    ("frase", "funcoes"),
    [
        ("aumentar dano em insetos", (21, 411)),
        ("aumentar dano físico em insetos", (21,)),
        ("aumentar dano mágico em insetos", (411,)),
        ("reduzir dano de dragões", (25,)),
        ("aumentar dano contra propriedade fogo", (27,)),
        ("reduzir dano de fogo", (23,)),
        ("aumentar dano em monstros grandes", (29,)),
        ("aumentar dano da habilidade lâminas retalhadoras", (33,)),
    ],
)
def test_funcoes_do_site(frase, funcoes):
    assert b.funcoes_do_site(b.interpretar(frase)) == funcoes


def test_rotulo_da_consulta():
    assert b.interpretar("aumentar dano em insetos").rotulo == "Aumentar dano em raça Inseto"
    assert b.interpretar("reduzir dano de dragões").rotulo == "Reduzir dano de raça Dragão"
    assert b.interpretar("aumentar dano mágico contra demônios").rotulo == "Aumentar dano mágico em raça Demônio"
    assert b.interpretar("aumentar dano da habilidade lâminas retalhadoras").rotulo.endswith("laminas retalhadoras")


def test_interpretar_dano_geral():
    assert b.interpretar("aumentar dano mágico").categoria == "geral"
    assert b.interpretar("aumentar dano mágico").alvos == ("magico",)
    assert b.interpretar("aumentar dano crítico").alvos == ("critico",)
    assert b.interpretar("aumentar dano à distância").alvos == ("distancia",)
    assert b.interpretar("aumentar dano corpo a corpo").alvos == ("corpo-a-corpo",)
    assert b.interpretar("aumentar dano físico").alvos == ("fisico",)


def test_dano_a_distancia_inclui_o_dano_fisico_sem_restricao():
    indice = {
        "items": [
            _item(1, "Geral", "Dano físico +10%."),
            _item(2, "Arco", "Dano físico à distância +15%."),
            _item(3, "Espada", "Dano físico corpo a corpo +20%."),
        ]
    }
    assert _ids(b.buscar(indice, "aumentar dano à distância")) == [2, 1]
    assert _ids(b.buscar(indice, "aumentar dano corpo a corpo")) == [3, 1]
    assert _ids(b.buscar(indice, "aumentar dano físico")) == [1]


def test_reduzir_dano_sem_alvo_pede_o_alvo():
    with pytest.raises(b.FraseNaoEntendida, match="de quem"):
        b.interpretar("reduzir dano mágico")


def test_propriedade_ao_aumentar_dano_distingue_alvo_de_ataque():
    assert b.interpretar("aumentar dano contra monstros de fogo").como == "alvo"
    assert b.interpretar("aumentar dano mágico de fogo").como == "ataque"
    assert b.interpretar("aumentar dano de fogo").como == ""
    assert b.interpretar("reduzir dano de fogo").como == ""
    indice = {
        "items": [
            _item(1, "Carta", "Dano físico contra oponentes de propriedade Fogo +20%."),
            _item(2, "Cajado", "Dano mágico de propriedade Fogo +15%."),
        ]
    }
    assert _ids(b.buscar(indice, "aumentar dano contra monstros de fogo")) == [1]
    assert _ids(b.buscar(indice, "aumentar dano mágico de fogo")) == [2]
    assert _ids(b.buscar(indice, "aumentar dano de fogo")) == [1, 2]


def test_varias_habilidades_na_descricao_atendem_a_busca_por_qualquer_uma():
    item = _item(1, "Carta", "Dano de [Lâminas Destruidoras] e [Lâminas Retalhadoras] +10%.")
    assert _ids(b.buscar({"items": [item]}, "aumentar dano da habilidade lâminas retalhadoras")) == [1]
    assert _ids(b.buscar({"items": [item]}, "aumentar dano da habilidade lâminas destruidoras")) == [1]
