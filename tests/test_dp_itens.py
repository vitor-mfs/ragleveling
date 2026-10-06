import json

import httpx
import pytest

from ragleveling import dp_itens
from ragleveling.config import Settings
from ragleveling.divinepride import ChaveAusente, DivinePrideClient
from ragleveling.ratelimit import RateLimiter

# --- listagem ---


def _linha(item_id, *, tipo="Armor", subtipo="Headgear", nivel="50", servidores=("bRO", "LATAM"), com_nivel=True):
    """Uma linha da listagem, no mesmo markup do site (com os selos colados, sem espaço entre eles)."""
    selos = "".join(f'<span class="badge badge-secondary">{s}</span>' for s in servidores)
    nivel_td = f"<td>{nivel}</td>" if com_nivel else ""
    return f"""
    <tr onclick="window.location='/database/item/{item_id}'" style="cursor: pointer;">
        <td class="font-semibold"><div><img src="x.png" alt="" /><a href="/database/item/{item_id}"></a></div></td>
        <td><span class="badge badge-primary">{tipo}</span></td>
        <td>{subtipo}</td>
        {nivel_td}
        <td>5</td>
        <td><div>{selos}</div></td>
    </tr>"""


COLUNAS = ("Name", "Type", "SubType", "Required Level", "Sell Price", "Server")


def _pagina(linhas, *, pagina=1, de=1, total=None, colunas=COLUNAS):
    cabecalho = "".join(f"<th>{c}</th>" for c in colunas)
    total = total if total is not None else len(linhas)
    return f"""<html><body>
    <span class="text-muted">{total} results</span>
    <table><thead><tr>{cabecalho}</tr></thead><tbody>{"".join(linhas)}</tbody></table>
    <span>Page {pagina} of {de}</span>
    </body></html>"""


def test_parse_listagem_le_id_tipo_nivel_e_selos():
    html = _pagina([_linha(2201, subtipo="Headgear", nivel="10")])
    item = dp_itens.parse_listagem(html)[0]
    assert item["id"] == 2201
    assert (item["type"], item["subtype"], item["required_level"]) == ("Armor", "Headgear", 10)
    assert item["servers"] == ["bRO", "LATAM"]
    assert item["name"] == ""  # a listagem quase nunca traz o nome


def test_parse_listagem_le_as_colunas_pelo_cabecalho():
    # Arma tem uma coluna ATK a mais; carta não tem nível requerido.
    arma = """<tr onclick="window.location='/database/item/1174'"><td></td><td>Weapon</td><td>Katar</td>
        <td>150</td><td>40</td><td>5</td><td>LATAM</td></tr>"""
    html = _pagina(
        [arma], colunas=("Name", "Type", "SubType", "ATK", "Required Level", "Sell Price", "Server")
    )
    assert dp_itens.parse_listagem(html)[0]["required_level"] == 40

    carta = _linha(4493, tipo="Card", subtipo="Unknown", com_nivel=False)
    html = _pagina([carta], colunas=("Name", "Type", "SubType", "Sell Price", "Server"))
    item = dp_itens.parse_listagem(html)[0]
    assert item["required_level"] == 0
    assert item["servers"] == ["bRO", "LATAM"]


def test_parse_listagem_ignora_linhas_sem_id():
    html = _pagina([_linha(1), "<tr><td>propaganda</td></tr>"])
    assert [i["id"] for i in dp_itens.parse_listagem(html)] == [1]


def _cliente_http(paginas, pedidos):
    def handler(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        pagina = int(request.url.params.get("page", 1))
        if pagina > len(paginas):
            return httpx.Response(200, text=_pagina([], pagina=pagina, de=len(paginas)))
        return httpx.Response(200, text=paginas[pagina - 1])

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://www.divine-pride.net")


def _listar(tmp_path, paginas, **kwargs):
    pedidos: list[httpx.Request] = []
    settings = Settings(cache_dir=tmp_path)
    itens = dp_itens.listar(
        "armor",
        settings=settings,
        client=_cliente_http(paginas, pedidos),
        limiter=RateLimiter(0),
        **kwargs,
    )
    return itens, pedidos


def test_listar_so_traz_itens_com_o_selo_do_servidor(tmp_path):
    pagina = _pagina([_linha(1), _linha(2, servidores=("bRO", "iRO")), _linha(3, servidores=("LATAM",))])
    itens, _ = _listar(tmp_path, [pagina])
    assert [i["id"] for i in itens] == [1, 3]


def test_listar_segue_as_paginas_ate_a_ultima(tmp_path):
    cheia = _pagina([_linha(i) for i in range(1, 21)], pagina=1, de=2, total=23)
    resto = _pagina([_linha(i) for i in range(21, 24)], pagina=2, de=2, total=23)
    itens, pedidos = _listar(tmp_path, [cheia, resto])
    assert len(itens) == 23
    assert len(pedidos) == 2


def test_listar_para_na_ultima_pagina_mesmo_cheia(tmp_path):
    cheia = _pagina([_linha(i) for i in range(1, 21)], pagina=1, de=1, total=20)
    _, pedidos = _listar(tmp_path, [cheia])
    assert len(pedidos) == 1


def test_listar_repassa_filtros_e_cabecalhos_do_servidor(tmp_path):
    pagina = _pagina([_linha(1)])
    _, pedidos = _listar(tmp_path, [pagina], subtipos=["Headgear", "Shield"], funcao=21, descricao="inseto", busca="x")
    pedido = pedidos[0]
    assert pedido.url.path == "/database/item/armor"
    assert pedido.url.params.get_list("subTypes") == ["Headgear", "Shield"]
    assert pedido.url.params["function"] == "21"
    assert pedido.url.params["description"] == "inseto"
    assert pedido.url.params["query"] == "x"


def test_listar_respeita_o_limite(tmp_path):
    cheia = _pagina([_linha(i) for i in range(1, 21)], pagina=1, de=5, total=100)
    itens, pedidos = _listar(tmp_path, [cheia, cheia, cheia], limite=7)
    assert len(itens) == 7
    assert len(pedidos) == 1


def test_listar_recusa_categoria_desconhecida(tmp_path):
    with pytest.raises(ValueError, match="categoria"):
        dp_itens.listar("hat", settings=Settings(cache_dir=tmp_path))


def test_listar_falha_com_erro_http(tmp_path):
    http = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(503)), base_url="https://www.divine-pride.net"
    )
    with pytest.raises(RuntimeError, match="503"):
        dp_itens.listar("armor", settings=Settings(cache_dir=tmp_path), client=http, limiter=RateLimiter(0))


# --- local de equipar ---


@pytest.mark.parametrize(
    ("bruto", "tipo", "esperado"),
    [
        # nomes vistos nas páginas reais do Divine Pride
        ("Upper", "Armor", "topo"),
        ("Middle", "Armor", "meio"),
        ("Body", "Armor", "armadura"),
        ("Garment", "Armor", "capa"),
        ("Shoes", "Armor", "calcado"),
        ("Accessory", "Armor", "acessorio"),
        ("Left Hand", "Armor", "escudo"),
        ("Bothhand", "Weapon", "arma"),
        ("Upper (Costume)", "Costume", "traje-topo"),
        ("Shadow Armor", "Shadow Equipment", "sombra-armadura"),
        ("Right Shadow Accessory", "Shadow Equipment", "sombra-brinco"),
        # o mesmo padrão nos nomes que faltam
        ("Lower", "Armor", "baixo"),
        ("Lower (Costume)", "Costume", "traje-baixo"),
        ("Left Shadow Accessory", "Shadow Equipment", "sombra-pingente"),
        ("Shadow Weapon", "Shadow Equipment", "sombra-arma"),
        ("Right Hand", "Weapon", "arma"),
        # a mão esquerda de uma adaga é arma, não escudo
        ("Left Hand", "Weapon", "arma"),
        # nomes em português
        ("Armadura", "Armor", "armadura"),
        ("Calçado", "Armor", "calcado"),
    ],
)
def test_normalizar_local(bruto, tipo, esperado):
    assert dp_itens.normalizar_local(bruto, tipo) == esperado


@pytest.mark.parametrize("bruto", ["None", "", "  ", "Algo Novo", "Left Shadow"])
def test_normalizar_local_nao_chuta(bruto):
    assert dp_itens.normalizar_local(bruto) is None


def test_local_com_varios_valores():
    assert dp_itens.locais_do_item(["Upper, Middle"], "Armor", "Headgear") == ["topo", "meio"]
    assert dp_itens.locais_do_item(["Upper", "Upper", "Lower"], "Armor", "Headgear") == ["topo", "baixo"]


def test_sem_local_no_payload_o_subtipo_serve_de_pista():
    assert dp_itens.locais_do_item([], "Armor", "Shield") == ["escudo"]
    assert dp_itens.locais_do_item([], "Armor", "Garment") == ["capa"]
    assert dp_itens.locais_do_item([], "Weapon", "Katar") == ["arma"]


def test_headgear_sem_local_fica_sem_local():
    # Topo, meio ou baixo só o local diz; o subtipo não distingue.
    assert dp_itens.locais_do_item([], "Armor", "Headgear") == []
    assert dp_itens.locais_do_item([], "Card", "Unknown") == []


@pytest.mark.parametrize(
    ("digitado", "canonico"),
    [("Calçado", "calcado"), ("acessório", "acessorio"), ("TOPO", "topo"), ("traje topo", "traje-topo"), ("x", None)],
)
def test_local_digitado(digitado, canonico):
    assert dp_itens.local_digitado(digitado) == canonico


# --- normalização do payload ---

PAYLOAD_OCULOS = {
    "id": 2201,
    "name": "Óculos Escuros",
    "aegisName": "Sunglasses",
    "iconUrl": "https://static.divine-pride.net/images/items/item/2201.png",
    "type": "Armor",
    "subType": "Headgear",
    "location": "Middle",
    "description": "^777777Óculos^000000 escuros.\r\nDEF: ^0000FF1^000000\r\nPeso: 10",
    "weight": 100,
    "allJobsAllowed": False,
    "allowedJobIds": [1, 2, 3],
    "scripts": [{"script": "bonus bStr,1;"}],
}


def test_normalizar_item_completo():
    item = dp_itens.normalizar_item(PAYLOAD_OCULOS, {"id": 2201, "required_level": 10})
    assert item["name"] == "Óculos Escuros"
    assert item["aegis_name"] == "Sunglasses"
    assert (item["type"], item["subtype"]) == ("Armor", "Headgear")
    assert item["locations"] == ["meio"]
    assert item["location_raw"] == ["Middle"]
    assert item["required_level"] == 10
    assert item["weight"] == 100
    assert item["job_ids"] == [1, 2, 3] and item["all_jobs"] is False
    assert item["scripts"] == [{"script": "bonus bStr,1;"}]


def test_descricao_sai_sem_codigos_de_cor_e_com_quebras_normais():
    item = dp_itens.normalizar_item(PAYLOAD_OCULOS, {"id": 2201})
    assert item["description"] == "Óculos escuros.\nDEF: 1\nPeso: 10"


@pytest.mark.parametrize("chave", ["location", "locations", "equipLocation"])
def test_local_aceita_nomes_diferentes_do_campo(chave):
    payload = {"type": "Armor", "subType": "Headgear", chave: "Upper"}
    assert dp_itens.normalizar_item(payload, {"id": 1})["locations"] == ["topo"]


def test_local_aceita_lista_de_textos_e_de_objetos():
    for valor in (["Upper", "Middle"], [{"name": "Upper"}, {"name": "Middle"}]):
        payload = {"type": "Armor", "subType": "Headgear", "location": valor}
        assert dp_itens.normalizar_item(payload, {"id": 1})["locations"] == ["topo", "meio"]


def test_normalizar_item_nao_quebra_com_payload_vazio():
    item = dp_itens.normalizar_item({}, {"id": 7, "type": "Armor", "subtype": "Shield", "required_level": 0})
    assert item["name"] == "7"
    assert item["description"] == ""
    assert item["scripts"] == [] and item["job_ids"] == []
    assert item["locations"] == ["escudo"]  # pelo subtipo da listagem


@pytest.mark.parametrize(
    ("payload", "basico", "esperado"),
    [
        ({"name": "라펠트", "aegisName": "Elegant_Flower"}, {"id": 1, "name": ""}, "Elegant Flower"),
        ({"name": "6510", "aegisName": "Elegant_Flower"}, {"id": 6510, "name": ""}, "Elegant Flower"),
        ({"name": "", "aegisName": "X"}, {"id": 1, "name": "Flor"}, "Flor"),
        ({"name": "Flor"}, {"id": 1, "name": "Flower"}, "Flor"),
    ],
)
def test_nome_cai_para_listagem_e_depois_para_o_aegis(payload, basico, esperado):
    assert dp_itens.normalizar_item(payload, basico)["name"] == esperado


def test_nivel_vem_da_listagem_e_cai_para_o_payload():
    assert dp_itens.normalizar_item({"requiredLevel": 99}, {"id": 1, "required_level": 10})["required_level"] == 10
    assert dp_itens.normalizar_item({"requiredLevel": 99}, {"id": 1, "required_level": 0})["required_level"] == 99


def test_sem_local_so_vale_para_equipamento():
    def item(tipo, locais):
        return {"type": tipo, "locations": locais}

    assert dp_itens.sem_local(item("Armor", []))
    assert dp_itens.sem_local(item("Shadow Equipment", []))
    assert not dp_itens.sem_local(item("Armor", ["topo"]))
    assert not dp_itens.sem_local(item("Card", []))


# --- completar, gravar e filtrar ---


def _cliente_api(tmp_path, respostas, pedidos=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if pedidos is not None:
            pedidos.append(request.url.path)
        item_id = int(request.url.path.rsplit("/", 1)[1])
        status, corpo = respostas.get(item_id, (404, {}))
        return httpx.Response(status, json=corpo)

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://www.divine-pride.net")
    settings = Settings(cache_dir=tmp_path, divine_pride_api_key="k")
    return DivinePrideClient(settings, client=http, limiter=RateLimiter(0), sleep=lambda _: None)


def test_item_consulta_a_rota_de_item_e_guarda_em_cache(tmp_path):
    pedidos: list[str] = []
    cliente = _cliente_api(tmp_path, {2201: (200, PAYLOAD_OCULOS)}, pedidos)
    assert cliente.item(2201)["name"] == "Óculos Escuros"
    cliente.item(2201)
    assert pedidos == ["/api/database/Item/2201"]  # a segunda veio do cache
    assert json.loads((cliente.cache_dir / "item-2201.json").read_text(encoding="utf-8"))["id"] == 2201


def test_completar_monta_o_indice_e_separa_as_falhas(tmp_path):
    cliente = _cliente_api(tmp_path, {2201: (200, PAYLOAD_OCULOS)})
    basicos = [{"id": 2201, "required_level": 10}, {"id": 999, "required_level": 0}]
    indice, falhas = dp_itens.completar(basicos, cliente)
    assert indice["version"] == dp_itens.VERSAO_INDICE_ITENS
    assert indice["servidor"] == "LATAM"
    assert [i["id"] for i in indice["items"]] == [2201]
    assert [f["id"] for f in falhas] == [999]


def test_completar_para_quando_a_chave_e_recusada(tmp_path):
    cliente = _cliente_api(tmp_path, {1: (401, {})})
    with pytest.raises(ChaveAusente):
        dp_itens.completar([{"id": 1}], cliente)


def _indice():
    def item(item_id, nome, tipo, subtipo, locais, descricao="", aegis=""):
        return {
            "id": item_id, "name": nome, "aegis_name": aegis, "type": tipo, "subtype": subtipo,
            "locations": locais, "location_raw": [], "required_level": 0, "weight": 0,
            "description": descricao, "all_jobs": True, "job_ids": [], "scripts": [], "icon_url": "",
        }  # fmt: skip

    return {
        "version": dp_itens.VERSAO_INDICE_ITENS,
        "items": [
            item(1, "Óculos Escuros", "Armor", "Headgear", ["meio"], "Aumenta o dano em insetos em 5%.", "Sunglasses"),
            item(2, "Chapéu de Bruxa", "Armor", "Headgear", ["topo"], "Reduz o dano de dragões.", "Witch_Hat"),
            item(3, "Escudo Forte", "Armor", "Shield", ["escudo"], "Aumenta a DEF."),
            item(4, "Carta Poring", "Card", "Unknown", [], "Aumenta a Sorte em 2."),
        ],
    }


def test_filtrar_por_local():
    assert [i["id"] for i in dp_itens.filtrar(_indice(), local="meio")] == [1]
    assert [i["id"] for i in dp_itens.filtrar(_indice(), local="escudo")] == [3]


def test_filtrar_por_tipo_casa_tipo_ou_subtipo():
    assert [i["id"] for i in dp_itens.filtrar(_indice(), tipo="headgear")] == [2, 1]  # ordem alfabética: Chapéu, Óculos
    assert [i["id"] for i in dp_itens.filtrar(_indice(), tipo="card")] == [4]


def test_filtrar_por_nome_ignora_acento_e_caixa_e_olha_o_aegis():
    assert [i["id"] for i in dp_itens.filtrar(_indice(), nome="oculos")] == [1]
    assert [i["id"] for i in dp_itens.filtrar(_indice(), nome="WITCH")] == [2]


def test_filtrar_por_texto_exige_todas_as_palavras_na_descricao():
    assert [i["id"] for i in dp_itens.filtrar(_indice(), texto="dano insetos")] == [1]
    assert [i["id"] for i in dp_itens.filtrar(_indice(), texto="dragoes")] == [2]
    assert dp_itens.filtrar(_indice(), texto="dano sorte") == []


def test_filtrar_combina_filtros_e_por_id():
    assert dp_itens.filtrar(_indice(), local="topo", texto="insetos") == []
    assert [i["id"] for i in dp_itens.filtrar(_indice(), item_id=3)] == [3]


def test_gravar_acumula_e_o_novo_tem_a_palavra_final(tmp_path):
    settings = Settings(cache_dir=tmp_path)
    antigo = _indice()
    dp_itens.gravar(settings, antigo)

    novo = {**_indice(), "items": [{**_indice()["items"][0], "name": "Óculos Novos"}]}
    gravado = dp_itens.gravar(settings, novo)

    assert [i["id"] for i in gravado["items"]] == [1, 2, 3, 4]
    assert dp_itens.carregar(settings)["items"][0]["name"] == "Óculos Novos"


def test_gravar_recomecar_substitui(tmp_path):
    settings = Settings(cache_dir=tmp_path)
    dp_itens.gravar(settings, _indice())
    dp_itens.gravar(settings, {**_indice(), "items": [_indice()["items"][0]]}, acumular=False)
    assert len(dp_itens.carregar(settings)["items"]) == 1


def test_carregar_sem_indice_ou_de_versao_antiga(tmp_path):
    settings = Settings(cache_dir=tmp_path)
    with pytest.raises(dp_itens.IndiceIndisponivel, match="dp-itens"):
        dp_itens.carregar(settings)

    settings.items_index_path.write_text(json.dumps({"version": 0, "items": []}), encoding="utf-8")
    with pytest.raises(dp_itens.IndiceIndisponivel, match="versão antiga"):
        dp_itens.carregar(settings)
