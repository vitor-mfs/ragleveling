
import httpx
import pytest

from ragleveling.config import Settings
from ragleveling.divinepride import (
    ChaveAusente,
    DivinePrideClient,
    DivinePrideError,
    extrair_nome,
    extrair_spawns,
)
from ragleveling.ratelimit import RateLimiter


def _cliente(tmp_path, handler, chave="k", esperas=None):
    transporte = httpx.MockTransport(handler)
    http = httpx.Client(transport=transporte, base_url="https://www.divine-pride.net")
    settings = Settings(cache_dir=tmp_path, divine_pride_api_key=chave)
    return DivinePrideClient(
        settings,
        client=http,
        limiter=RateLimiter(0),
        sleep=(esperas.append if esperas is not None else lambda _: None),
    )


# --- normalização do payload ---


def test_extrair_nome():
    assert extrair_nome({"name": "Pierrotzoist"}) == "Pierrotzoist"
    assert extrair_nome({}) is None


@pytest.mark.parametrize("chave", ["spawn", "spawns", "monsterSpawn"])
def test_extrair_spawns_aceita_nomes_diferentes_da_lista(chave):
    payload = {chave: [{"mapname": "clock_01", "amount": 30, "respawnTime": 5000}]}
    spawn = extrair_spawns(payload)[0]
    assert (spawn["map"], spawn["amount"], spawn["respawn_s"]) == ("clock_01", 30, 5.0)


@pytest.mark.parametrize("campo", ["mapname", "map", "mapName", "mapId"])
def test_extrair_spawns_aceita_nomes_diferentes_do_mapa(campo):
    payload = {"spawn": [{campo: "clock_01", "amount": 12}]}
    assert extrair_spawns(payload)[0]["map"] == "clock_01"


def test_respawn_em_milissegundos_vira_segundos():
    payload = {"spawn": [{"mapname": "m", "amount": 1, "respawnTime": 300000}]}
    assert extrair_spawns(payload)[0]["respawn_s"] == 300.0


def test_respawn_guarda_o_valor_cru_para_conferencia():
    payload = {"spawn": [{"mapname": "m", "amount": 1, "respawnTime": 5000}]}
    assert extrair_spawns(payload)[0]["respawn_bruto"] == 5000


def test_respawn_ja_em_segundos_fica_como_esta():
    payload = {"spawn": [{"mapname": "m", "amount": 1, "respawnTime": 5}]}
    assert extrair_spawns(payload)[0]["respawn_s"] == 5.0


def test_spawn_sem_quantidade_vira_zero():
    payload = {"spawn": [{"mapname": "m"}]}
    assert extrair_spawns(payload)[0]["amount"] == 0


def test_payload_sem_spawn_nao_e_erro():
    assert extrair_spawns({"name": "X"}) == []
    assert extrair_spawns({"spawn": "nada disso"}) == []


def test_item_de_spawn_invalido_e_ignorado():
    payload = {"spawn": [{"amount": 5}, "lixo", {"mapname": "ok", "amount": 3}]}
    assert [s["map"] for s in extrair_spawns(payload)] == ["ok"]


# --- cliente ---


def test_monstro_consulta_e_guarda_em_cache(tmp_path):
    chamadas = []

    def handler(request):
        chamadas.append(request)
        return httpx.Response(200, json={"name": "Grote", "spawn": []})

    cliente = _cliente(tmp_path, handler)
    assert cliente.monstro(20941)["name"] == "Grote"
    assert cliente.monstro(20941)["name"] == "Grote"  # segunda vem do cache
    assert len(chamadas) == 1
    assert "apiKey=k" in str(chamadas[0].url)


def test_regiao_e_idioma_vao_em_headers(tmp_path):
    """A API ignora `?server=`: a região é o header `x-server`."""
    chamadas = []

    def handler(request):
        chamadas.append(request)
        return httpx.Response(200, json={"name": "Poring"})

    cliente = _cliente(tmp_path, handler)
    cliente.monstro(1002)
    pedido = chamadas[0]
    assert pedido.headers["x-server"] == "LATAM"
    assert pedido.headers["accept-language"] == "pt"
    assert "server=" not in str(pedido.url)


def test_retry_after_manda_no_tempo_de_espera(tmp_path):
    esperas = []
    respostas = [
        httpx.Response(429, json={}, headers={"Retry-After": "7"}),
        httpx.Response(200, json={"name": "Grote"}),
    ]
    cliente = _cliente(tmp_path, lambda r: respostas.pop(0), esperas=esperas)
    assert cliente.monstro(1)["name"] == "Grote"
    assert esperas == [7.0]


def test_refresh_ignora_o_cache(tmp_path):
    chamadas = []

    def handler(request):
        chamadas.append(1)
        return httpx.Response(200, json={"name": "Grote"})

    cliente = _cliente(tmp_path, handler)
    cliente.monstro(1)
    cliente.monstro(1, refresh=True)
    assert len(chamadas) == 2


def test_cache_corrompido_refaz_a_consulta(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"name": "Grote"})

    cliente = _cliente(tmp_path, handler)
    caminho = cliente._caminho_cache(7)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("{isso não é json", encoding="utf-8")
    assert cliente.monstro(7)["name"] == "Grote"


def test_sem_chave(tmp_path):
    cliente = _cliente(tmp_path, lambda r: httpx.Response(200, json={}), chave=None)
    with pytest.raises(ChaveAusente, match="DIVINE_PRIDE_API_KEY"):
        cliente.monstro(1)


@pytest.mark.parametrize(
    ("status", "excecao", "trecho"),
    [(404, DivinePrideError, "não existe"), (403, ChaveAusente, "recusada"), (500, DivinePrideError, "500")],
)
def test_erros_http(tmp_path, status, excecao, trecho):
    cliente = _cliente(tmp_path, lambda r: httpx.Response(status, json={}))
    with pytest.raises(excecao, match=trecho):
        cliente.monstro(1)


def test_429_tenta_de_novo_antes_de_desistir(tmp_path):
    from ragleveling.divinepride import ESPERAS_APOS_429

    tentativas = []
    esperas = []

    def handler(request):
        tentativas.append(1)
        return httpx.Response(429, json={})

    cliente = _cliente(tmp_path, handler, esperas=esperas)
    with pytest.raises(DivinePrideError, match="continuou respondendo 429"):
        cliente.monstro(1)
    assert len(tentativas) == len(ESPERAS_APOS_429) + 1
    assert esperas == list(ESPERAS_APOS_429)


def test_429_seguido_de_sucesso(tmp_path):
    respostas = [httpx.Response(429, json={}), httpx.Response(200, json={"name": "Grote"})]
    cliente = _cliente(tmp_path, lambda r: respostas.pop(0))
    assert cliente.monstro(1)["name"] == "Grote"


def test_resposta_nao_json(tmp_path):
    cliente = _cliente(tmp_path, lambda r: httpx.Response(200, text="<html>"))
    with pytest.raises(DivinePrideError, match="não é JSON"):
        cliente.monstro(1)


def test_respeita_o_limitador(tmp_path):
    esperas = []
    limiter = RateLimiter(1.0, sleep=esperas.append, monotonic=lambda: 0.0)
    http = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"name": "x"})),
        base_url="https://www.divine-pride.net",
    )
    cliente = DivinePrideClient(
        Settings(cache_dir=tmp_path, divine_pride_api_key="k"), client=http, limiter=limiter
    )
    cliente.monstro(1)
    cliente.monstro(2)
    assert esperas == [1.0]  # a segunda chamada esperou o intervalo


def test_agregar_soma_o_mesmo_mapa_e_guarda_o_menor_respawn():
    from ragleveling.divinepride import agregar_spawns

    spawns = [
        {"map": "nif_dun02", "amount": 70, "respawn_s": 5.0},
        {"map": "nif_dun02", "amount": 5, "respawn_s": 10.0},
        {"map": "nif_dun02", "amount": 5, "respawn_s": 10.0},
        {"map": "outro", "amount": 3, "respawn_s": 0.0},
    ]
    agregados = {s["map"]: s for s in agregar_spawns(spawns)}
    assert agregados["nif_dun02"] == {"map": "nif_dun02", "amount": 80, "respawn_s": 5.0}
    assert agregados["outro"]["amount"] == 3


def test_agregar_lista_vazia():
    from ragleveling.divinepride import agregar_spawns

    assert agregar_spawns([]) == []


def test_skill_consulta_o_endpoint_de_habilidade(tmp_path):
    chamadas = []

    def handler(request):
        chamadas.append(str(request.url))
        return httpx.Response(200, json={"id": 26, "databaseName": "AL_TELEPORT"})

    cliente = _cliente(tmp_path, handler)
    assert cliente.skill(26)["databaseName"] == "AL_TELEPORT"
    assert cliente.skill(26)["databaseName"] == "AL_TELEPORT"  # cache
    assert len(chamadas) == 1 and "/api/database/Skill/26" in chamadas[0]
