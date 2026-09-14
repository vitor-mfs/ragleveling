import json

import httpx
import pytest

from ragleveling.config import Settings
from ragleveling.divinepride import DivinePrideClient
from ragleveling.dp_index import (
    TIPOS_CHEFE,
    VERSAO_INDICE_DP,
    carregar,
    completar,
    gravar,
    listar_por_nivel,
    parse_listagem,
    total_de_resultados,
)
from ragleveling.ratelimit import RateLimiter

LINHA = """
<tr onclick="window.location='/database/monster/{id}'">
  <td><a href="/database/monster/{id}">{nome}</a></td>
  <td>{nivel}</td>
  <td><span class="hp-full">{hp}</span> <span class="hp-compact">22.4m</span></td>
  <td>{base}</td><td>{job}</td><td>{elemento}</td><td>{raca}</td><td>{tamanho}</td><td>{tipo}</td>
</tr>
"""


def _pagina(linhas, total=None):
    corpo = "".join(linhas)
    rodape = f"<div>{total} results</div>" if total is not None else ""
    return f"<table><tbody>{corpo}</tbody></table>{rodape}"


def _linha(**kwargs):
    base = {
        "id": 20175, "nome": "Extra Joker", "nivel": 255, "hp": "22.410.484",
        "base": "1.393.537 1.4m", "job": "974.990 975k", "elemento": "Dark 4",
        "raca": "Demon", "tamanho": "Large", "tipo": "Normal",
    }
    base.update(kwargs)
    return LINHA.format(**base)


def test_parse_listagem_le_todos_os_campos():
    monstro = parse_listagem(_pagina([_linha()]))[0]
    assert monstro == {
        "id": 20175,
        "name": "Extra Joker",
        "level": 255,
        "hp": 22410484,
        "base_exp": 1393537,
        "job_exp": 974990,
        "element": "Dark",
        "element_level": 4,
        "race": "Demon",
        "size": "Large",
        "type": "Normal",
    }


def test_parse_listagem_ignora_linha_incompleta():
    quebrada = "<tr onclick=\"window.location='/database/monster/1'\"><td>Só o nome</td></tr>"
    assert parse_listagem(_pagina([quebrada])) == []


def test_parse_listagem_sem_tabela():
    assert parse_listagem("<html><body>nada aqui</body></html>") == []


def test_elemento_sem_nivel_vira_1():
    monstro = parse_listagem(_pagina([_linha(elemento="Neutral")]))[0]
    assert (monstro["element"], monstro["element_level"]) == ("Neutral", 1)


def test_total_de_resultados():
    assert total_de_resultados(_pagina([_linha()], total="447")) == 447
    assert total_de_resultados("<html></html>") is None


def _listagem_paginada(paginas):
    def handler(request):
        pagina = int(request.url.params.get("page", 1))
        conteudo = paginas[pagina - 1] if pagina <= len(paginas) else _pagina([])
        return httpx.Response(200, text=conteudo)

    return handler


def test_listar_por_nivel_percorre_as_paginas(tmp_path):
    cheia = _pagina([_linha(id=1000 + i) for i in range(50)], total="60")
    ultima = _pagina([_linha(id=2000 + i) for i in range(10)], total="60")
    client = httpx.Client(
        transport=httpx.MockTransport(_listagem_paginada([cheia, ultima])),
        base_url="https://www.divine-pride.net",
    )
    monstros = listar_por_nivel(
        236, 255, settings=Settings(cache_dir=tmp_path), client=client, limiter=RateLimiter(0)
    )
    assert len(monstros) == 60


def test_listar_por_nivel_para_na_pagina_vazia(tmp_path):
    cheia = _pagina([_linha(id=1000 + i) for i in range(50)])
    client = httpx.Client(
        transport=httpx.MockTransport(_listagem_paginada([cheia])),
        base_url="https://www.divine-pride.net",
    )
    monstros = listar_por_nivel(
        236, 255, settings=Settings(cache_dir=tmp_path), client=client, limiter=RateLimiter(0)
    )
    assert len(monstros) == 50


def test_listar_por_nivel_propaga_erro_http(tmp_path):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),
        base_url="https://www.divine-pride.net",
    )
    with pytest.raises(RuntimeError, match="500"):
        listar_por_nivel(1, 2, settings=Settings(cache_dir=tmp_path), client=client, limiter=RateLimiter(0))


PAYLOAD = {
    "name": "Extra Joker",
    "spriteName": "EXTRA_JOKER",
    "def": 445,
    "mDef": 172,
    "attackRange": "12.247 - 18.134",
    "spawns": [
        {"mapName": "clock_01", "quantity": 70, "respawnTime": 5000},
        {"mapName": "clock_01", "quantity": 5, "respawnTime": 10000},
    ],
    "skills": [
        {"skillId": 26, "state": "Idling"},
        {"skillId": 26, "state": "Moving"},
        {"skillId": 173, "state": "Attack"},
    ],
    "elementResistances": [
        {"element": "Neutral", "percentage": 100},
        {"element": "Earth", "percentage": 200},
        {"element": "Fire", "percentage": 25},
    ],
}


def _cliente_api(tmp_path, payload=None):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload or PAYLOAD)),
        base_url="https://www.divine-pride.net",
    )
    settings = Settings(cache_dir=tmp_path, divine_pride_api_key="k")
    return DivinePrideClient(settings, client=client, limiter=RateLimiter(0))


def test_completar_junta_listagem_e_api(tmp_path):
    basico = parse_listagem(_pagina([_linha()]))
    indice = completar(basico, _cliente_api(tmp_path))

    monstro = indice["monsters"][0]
    assert monstro["name"] == "Extra Joker"
    assert (monstro["defense"], monstro["magic_defense"]) == (445, 172)
    assert monstro["attack"] == 18134
    assert monstro["boss"] is False
    assert monstro["resist"]["Earth"] == 200

    assert indice["spawns"]["20175"] == [{"map": "clock_01", "amount": 75, "respawn_ms": 5000}]
    assert [s["id"] for s in indice["skills"]["20175"]] == [26, 173]
    assert indice["fonte"] == "divine-pride"


def test_completar_marca_chefe_pelo_tipo(tmp_path):
    basico = parse_listagem(_pagina([_linha(tipo="MVP")]))
    monstro = completar(basico, _cliente_api(tmp_path))["monsters"][0]
    assert monstro["boss"] is True and monstro["mvp"] is True
    assert "MVP" in TIPOS_CHEFE


def test_completar_sem_spawn_nao_cria_entrada(tmp_path):
    basico = parse_listagem(_pagina([_linha()]))
    indice = completar(basico, _cliente_api(tmp_path, {"name": "X", "spawns": []}))
    assert indice["spawns"] == {}


def test_gravar_e_carregar(tmp_path, monkeypatch):
    settings = Settings(cache_dir=tmp_path)
    indice = completar(parse_listagem(_pagina([_linha()])), _cliente_api(tmp_path))
    gravar(settings, indice)
    monkeypatch.setenv("RAGLEVELING_SPAWNS_EXTRA", str(tmp_path / "nao_existe.yaml"))
    lido = carregar(settings)
    assert lido["version"] == VERSAO_INDICE_DP
    assert lido["monsters"][0]["name"] == "Extra Joker"


def test_carregar_sem_indice(tmp_path):
    from ragleveling.rathena import SyncError

    with pytest.raises(SyncError, match="dp-index"):
        carregar(Settings(cache_dir=tmp_path))


def test_carregar_versao_antiga(tmp_path):
    from ragleveling.rathena import SyncError

    settings = Settings(cache_dir=tmp_path)
    settings.index_dp_path.parent.mkdir(parents=True, exist_ok=True)
    settings.index_dp_path.write_text(json.dumps({"version": 0}), encoding="utf-8")
    with pytest.raises(SyncError, match="versão antiga"):
        carregar(settings)


def test_fundir_soma_faixas(tmp_path):
    from ragleveling.dp_index import fundir

    antigo = {
        "version": VERSAO_INDICE_DP,
        "monsters": [{"id": 1, "level": 100, "name": "Antigo"}],
        "spawns": {"1": [{"map": "a", "amount": 5, "respawn_ms": 0}]},
        "skills": {"1": [{"id": 26, "state": "Idling"}]},
    }
    novo = {
        "version": VERSAO_INDICE_DP,
        "monsters": [{"id": 2, "level": 250, "name": "Novo"}],
        "spawns": {"2": [{"map": "b", "amount": 9, "respawn_ms": 0}]},
        "skills": {},
    }
    junto = fundir(antigo, novo)
    assert [m["id"] for m in junto["monsters"]] == [1, 2]
    assert set(junto["spawns"]) == {"1", "2"}
    assert junto["skills"]["1"][0]["id"] == 26


def test_fundir_prefere_o_novo_no_mesmo_id():
    from ragleveling.dp_index import fundir

    antigo = {"monsters": [{"id": 1, "level": 10, "name": "Velho"}], "spawns": {}, "skills": {}}
    novo = {"monsters": [{"id": 1, "level": 10, "name": "Atual"}], "spawns": {}, "skills": {}}
    assert fundir(antigo, novo)["monsters"][0]["name"] == "Atual"


def test_gravar_acumula_por_padrao(tmp_path):
    settings = Settings(cache_dir=tmp_path)
    primeiro = completar(parse_listagem(_pagina([_linha(id=1, nivel=200)])), _cliente_api(tmp_path))
    gravar(settings, primeiro)
    segundo = completar(parse_listagem(_pagina([_linha(id=2, nivel=250)])), _cliente_api(tmp_path))
    final = gravar(settings, segundo)
    assert {m["id"] for m in final["monsters"]} == {1, 2}


def test_gravar_sem_acumular_substitui(tmp_path):
    settings = Settings(cache_dir=tmp_path)
    gravar(settings, completar(parse_listagem(_pagina([_linha(id=1)])), _cliente_api(tmp_path)))
    final = gravar(
        settings,
        completar(parse_listagem(_pagina([_linha(id=2)])), _cliente_api(tmp_path)),
        acumular=False,
    )
    assert {m["id"] for m in final["monsters"]} == {2}


def test_nome_em_coreano_cai_no_nome_da_listagem(tmp_path):
    basico = parse_listagem(_pagina([_linha(nome="Strong Opois")]))
    coreano = {**PAYLOAD, "name": "강인한 오포이스"}
    monstro = completar(basico, _cliente_api(tmp_path, coreano))["monsters"][0]
    assert monstro["name"] == "Strong Opois"


def test_sem_traducao_em_lugar_nenhum_usa_o_sprite(tmp_path):
    basico = parse_listagem(_pagina([_linha(nome="수상한 아윈 훈련병")]))
    coreano = {**PAYLOAD, "name": "수상한 아윈 훈련병", "spriteName": "EP19_AWIN_TRAINEE"}
    monstro = completar(basico, _cliente_api(tmp_path, coreano))["monsters"][0]
    assert monstro["name"] == "Ep19 Awin Trainee"
