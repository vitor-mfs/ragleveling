"""CLI do ragleveling."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__, dp_index, dp_itens
from .catalog import Catalog, carregar
from .config import get_settings, url_divine_pride_item
from .divinepride import (
    DivinePrideClient,
    DivinePrideError,
    agregar_spawns,
    extrair_nome,
    extrair_spawns,
)
from .dp_index import IndiceIndisponivel
from .hunt import FAIXA_PADRAO, MIN_SPAWN_PADRAO
from .hunt import cacar as buscar_alvos
from .jobs import Perfil, canonical_job_key, display_name, perfil_de, sugerir
from .models import Character, ServerRates
from .router import avaliar_spots, montar_rota

app = typer.Typer(add_completion=False, help="Criador de rotas de level up para Ragnarok Online Renewal.")
console = Console()

def _dados_padrao() -> Path:
    """Catálogo padrão: `./data` do diretório atual, senão o `data/` do repositório."""
    local = Path.cwd() / "data"
    if local.is_dir():
        return local
    return Path(__file__).resolve().parents[2] / "data"


def _catalogo(caminho: Path | None) -> Catalog:
    origem = caminho or _dados_padrao()
    try:
        return carregar(origem)
    except (FileNotFoundError, ValueError) as erro:
        console.print(f"[red]Erro ao carregar o catálogo de {origem}:[/red] {erro}")
        raise typer.Exit(code=1) from erro


def _personagem(base: int, job: int, dps: float, seek: float, gap: int, classe: str) -> Character:
    try:
        return Character(base_level=base, job_level=job, job=classe, dps=dps, seek_seconds=seek, max_level_gap=gap)
    except ValueError as erro:
        console.print(f"[red]Personagem inválido:[/red] {erro}")
        raise typer.Exit(code=1) from erro


def _fmt(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


@app.command()
def versao() -> None:
    """Mostra a versão."""
    console.print(f"ragleveling {__version__}")


@app.command()
def spots(
    nivel: int = typer.Option(..., "--nivel", "-n", help="Base level atual."),
    dps: float = typer.Option(..., "--dps", help="Dano efetivo por segundo no campo."),
    job_level: int = typer.Option(1, "--job-level", "-j"),
    classe: str = typer.Option("desconhecido", "--classe", "-c"),
    seek: float = typer.Option(2.0, "--seek", help="Segundos andando entre um alvo e o próximo."),
    gap: int = typer.Option(25, "--gap", help="Diferença máxima de nível aceita."),
    crowding: float = typer.Option(1.0, "--crowding", help="Fatia do mapa só sua (1.0 = mapa vazio)."),
    criterio: str = typer.Option("base", "--criterio", help="base | job | total"),
    base_rate: float = typer.Option(1.0, "--base-rate"),
    job_rate: float = typer.Option(1.0, "--job-rate"),
    limite: int = typer.Option(15, "--limite", "-l"),
    dados: Path | None = typer.Option(None, "--dados", "-d", help="Arquivo ou pasta de catálogo YAML."),
) -> None:
    """Ranqueia os melhores mapas/monstros para o nível atual."""
    catalog = _catalogo(dados)
    char = _personagem(nivel, job_level, dps, seek, gap, classe)
    rates = ServerRates(base_exp=base_rate, job_exp=job_rate)

    try:
        resultado = avaliar_spots(catalog, char, rates, crowding, criterio=criterio)
    except ValueError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(code=1) from erro

    if not resultado:
        console.print("[yellow]Nenhum spot viável. Aumente --gap ou amplie o catálogo.[/yellow]")
        raise typer.Exit(code=1)

    tabela = Table(title=f"Melhores spots — base level {nivel}")
    tabela.add_column("Mapa")
    tabela.add_column("Monstro")
    tabela.add_column("Lv", justify="right")
    tabela.add_column("Δ", justify="right")
    tabela.add_column("EXP rate", justify="right")
    tabela.add_column("Kills/h", justify="right")
    tabela.add_column("Base/h", justify="right")
    tabela.add_column("Job/h", justify="right")

    for spot in resultado[:limite]:
        tabela.add_row(
            spot.map_name,
            spot.monster_name + (" *" if spot.limited_by_respawn else ""),
            str(spot.monster_level),
            f"{spot.level_diff:+d}",
            f"{spot.exp_rate:.0%}",
            _fmt(spot.kills_per_hour),
            _fmt(spot.base_exp_per_hour),
            _fmt(spot.job_exp_per_hour),
        )

    console.print(tabela)
    console.print("[dim]* ritmo limitado pelo respawn do mapa, não pelo seu dano.[/dim]")


@app.command()
def rota(
    de: int = typer.Option(..., "--de", help="Base level inicial."),
    ate: int = typer.Option(..., "--ate", help="Base level alvo."),
    dps: float = typer.Option(..., "--dps", help="Dano efetivo por segundo no campo."),
    job_level: int = typer.Option(1, "--job-level", "-j"),
    classe: str = typer.Option("desconhecido", "--classe", "-c"),
    seek: float = typer.Option(2.0, "--seek"),
    gap: int = typer.Option(25, "--gap"),
    crowding: float = typer.Option(1.0, "--crowding"),
    criterio: str = typer.Option("base", "--criterio", help="base | job | total"),
    histerese: float = typer.Option(0.10, "--histerese", help="Ganho mínimo para valer a troca de mapa."),
    base_rate: float = typer.Option(1.0, "--base-rate"),
    job_rate: float = typer.Option(1.0, "--job-rate"),
    dados: Path | None = typer.Option(None, "--dados", "-d"),
) -> None:
    """Monta a rota de level up de um nível até outro."""
    catalog = _catalogo(dados)
    char = _personagem(de, job_level, dps, seek, gap, classe)
    rates = ServerRates(base_exp=base_rate, job_exp=job_rate)

    try:
        pernas = montar_rota(catalog, char, ate, rates, crowding, criterio=criterio, histerese=histerese)
    except ValueError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(code=1) from erro

    tabela = Table(title=f"Rota {de} → {ate}")
    tabela.add_column("Níveis")
    tabela.add_column("Mapa")
    tabela.add_column("Monstro")
    tabela.add_column("Base/h", justify="right")
    tabela.add_column("Job/h", justify="right")
    tabela.add_column("Horas", justify="right")

    total = 0.0
    sem_estimativa = False
    for perna in pernas:
        if perna.hours is None:
            sem_estimativa = True
            horas = "—"
        else:
            total += perna.hours
            horas = f"{perna.hours:.1f}"
        tabela.add_row(
            f"{perna.from_level}–{perna.to_level}",
            perna.spot.map_name,
            perna.spot.monster_name,
            _fmt(perna.spot.base_exp_per_hour),
            _fmt(perna.spot.job_exp_per_hour),
            horas,
        )

    console.print(tabela)
    if sem_estimativa:
        console.print("[yellow]Sem `exp_table` no catálogo: dá para ranquear os spots, mas não estimar horas.[/yellow]")
    else:
        console.print(f"[bold]Tempo total estimado: {total:.1f} h[/bold]")


@app.command()
def cacar(
    nivel: int = typer.Option(..., "--nivel", "-n", help="Seu base level."),
    classe: str = typer.Option(..., "--classe", "-c", help='Sua classe, ex: "Cavaleiro Rúnico".'),
    perfil: str | None = typer.Option(None, "--perfil", help="Sobrescreve o perfil: melee, ranged ou magic."),
    faixa_min: int = typer.Option(FAIXA_PADRAO[0], "--faixa-min", help="Diferença mínima de nível."),
    faixa_max: int = typer.Option(FAIXA_PADRAO[1], "--faixa-max", help="Diferença máxima de nível."),
    ordenar: str = typer.Option("dificuldade", "--ordenar", help="dificuldade | exp | nivel"),
    limite: int = typer.Option(15, "--limite", "-l"),
    instancias: bool = typer.Option(False, "--instancias", help="Inclui mapas de instância."),
    todos_mapas: bool = typer.Option(False, "--todos-mapas", help="Inclui castelos, arenas e mapas de quest."),
    min_spawn: int = typer.Option(
        MIN_SPAWN_PADRAO, "--min-spawn", help="Mínimo de exemplares no mapa para ele contar."
    ),
) -> None:
    """Monstros para upar no seu nível, do mais fácil ao mais difícil."""
    chave = canonical_job_key(classe)
    if chave is None:
        palpites = sugerir(classe)
        dica = f" Você quis dizer: {', '.join(display_name(k) for k in palpites)}?" if palpites else ""
        console.print(f"[red]Classe não reconhecida:[/red] {classe}.{dica}")
        raise typer.Exit(code=1)

    perfil_escolhido = None
    if perfil is not None:
        try:
            perfil_escolhido = Perfil(perfil.strip().casefold())
        except ValueError as erro:
            console.print("[red]Perfil inválido.[/red] Use melee, ranged ou magic.")
            raise typer.Exit(code=1) from erro

    try:
        indice = dp_index.carregar(get_settings())
    except IndiceIndisponivel as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(code=1) from erro

    try:
        alvos = buscar_alvos(
            indice,
            nivel,
            chave,
            perfil=perfil_escolhido,
            faixa=(faixa_min, faixa_max),
            limite=limite,
            ordenar_por=ordenar,
            incluir_instancias=instancias,
            todos_mapas=todos_mapas,
            min_spawn=min_spawn,
        )
    except ValueError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(code=1) from erro

    if not alvos:
        console.print("[yellow]Nenhum monstro na faixa. Amplie --faixa-min/--faixa-max.[/yellow]")
        raise typer.Exit(code=1)

    perfil_final = perfil_escolhido or perfil_de(chave)
    coluna_def = "MDEF" if perfil_final is Perfil.MAGIC else "DEF"
    mostrar_perigos = any(alvo.dificuldade.perigos for alvo in alvos)

    tabela = Table(
        title=f"{classe.strip()} base {nivel} — {len(alvos)} alvos ({perfil_final.value})",
        caption="dificuldade: 0 = mais fácil desta lista, 100 = mais difícil",
    )
    tabela.add_column("Monstro", no_wrap=True)
    tabela.add_column("Lv (Δ)", justify="right", no_wrap=True)
    tabela.add_column("EXP", justify="right")
    tabela.add_column("HP", justify="right")
    tabela.add_column(coluna_def, justify="right")
    tabela.add_column("Dif.", justify="right", no_wrap=True)
    if mostrar_perigos:
        tabela.add_column("Perigo")
    tabela.add_column("Mapa (qtd)", no_wrap=True)
    tabela.add_column("Usar", no_wrap=True)

    cores = {"fácil": "green", "médio": "yellow", "difícil": "red"}
    for alvo in alvos:
        principal = alvo.mapa_principal
        mapa = f"{principal.map_id} ({principal.amount})" if principal else "—"
        if len(alvo.spawns) > 1:
            mapa += f" +{len(alvo.spawns) - 1}"
        defesa = alvo.magic_defense if perfil_final is Perfil.MAGIC else alvo.defense
        cor = cores[alvo.dificuldade.rotulo]
        elemento, pct = alvo.elemento_sugerido
        linha = [
            f"[link={alvo.url}]{alvo.name}[/link]",
            f"{alvo.level} ({alvo.level_diff:+d})",
            _fmt(alvo.exp_efetiva),
            _fmt(alvo.hp),
            str(defesa),
            f"[{cor}]{alvo.dificuldade.score:.0f}[/{cor}]",
        ]
        if mostrar_perigos:
            linha.append(alvo.dificuldade.perigos or "—")
        linha.extend([mapa, f"{elemento} {pct}%"])
        tabela.add_row(*linha)

    console.print(tabela)
    console.print(
        f"[dim]Nomes são links para o Divine Pride. Elemento: {alvos[0].como_aplicar}. "
        f"Fora da lista: chefes e MVPs, "
        f"instâncias (--instancias), castelos/arenas/quest (--todos-mapas) e "
        f"mapas com menos de {min_spawn} exemplares (--min-spawn).[/dim]"
    )



@app.command("dp-check")
def dp_check(
    monster_id: int = typer.Argument(..., help="ID do monstro no Divine Pride."),
    refresh: bool = typer.Option(False, "--refresh", help="Ignora o cache e consulta de novo."),
) -> None:
    """Mostra o que a API do Divine Pride devolve para um monstro.

    Serve para conferir o formato do JSON: quais campos vieram e o que o
    ragleveling entendeu deles.
    """
    settings = get_settings()
    try:
        with DivinePrideClient(settings) as cliente:
            payload = cliente.monstro(monster_id, refresh=refresh)
            destino = cliente._caminho_cache(monster_id)
    except DivinePrideError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(code=1) from erro

    console.print(f"[bold]Campos no topo do payload:[/bold] {', '.join(sorted(payload))}")
    console.print(f"[bold]Nome:[/bold] {extrair_nome(payload) or '[red]não encontrado[/red]'}")

    spawns = agregar_spawns(extrair_spawns(payload))
    if spawns:
        tabela = Table(title=f"{len(spawns)} mapas entendidos")
        tabela.add_column("Mapa")
        tabela.add_column("Qtd", justify="right")
        tabela.add_column("Respawn (s)", justify="right")
        tabela.add_column("Campo cru", justify="right")
        for spawn in spawns:
            tabela.add_row(
                spawn["map"],
                str(spawn["amount"]),
                f"{spawn['respawn_s']:g}",
                str(spawn.get("respawn_bruto", "—")),
            )
        console.print(tabela)
    else:
        console.print("[yellow]Nenhum spawn entendido no payload.[/yellow]")

    console.print(f"[dim]JSON cru salvo em {destino}[/dim]")


@app.command("dp-index")
def dp_index_cmd(
    de: int = typer.Option(..., "--de", help="Nível mínimo do monstro."),
    ate: int = typer.Option(..., "--ate", help="Nível máximo do monstro."),
    refresh: bool = typer.Option(False, "--refresh", help="Ignora o cache das consultas."),
    so_normais: bool = typer.Option(
        True, "--so-normais/--com-chefes", help="Descarta chefes e MVPs antes de consultar."
    ),
    acumular: bool = typer.Option(
        True, "--acumular/--recomecar", help="Soma ao índice existente em vez de substituí-lo."
    ),
) -> None:
    """Monta (ou amplia) o índice de monstros a partir do Divine Pride.

    A listagem do site dá os monstros da faixa e a API completa cada um com
    defesa, habilidades, resistências, spawns e a tabela de EXP. A segunda
    etapa é uma requisição por monstro no limite da API, então uma faixa larga
    leva minutos; o que já foi consultado vem do cache.
    """
    if de > ate:
        console.print("[red]O nível mínimo não pode ser maior que o máximo.[/red]")
        raise typer.Exit(code=1)

    settings = get_settings()
    try:
        with console.status("consultando a listagem...") as status:
            basicos = dp_index.listar_por_nivel(de, ate, settings=settings, progresso=status.update)
    except (RuntimeError, httpx.HTTPError) as erro:
        console.print(f"[red]Falha ao ler a listagem:[/red] {erro}")
        raise typer.Exit(code=1) from erro

    if not basicos:
        console.print(f"[yellow]A listagem não devolveu nada entre {de} e {ate}.[/yellow]")
        raise typer.Exit(code=1)

    if so_normais:
        antes = len(basicos)
        basicos = [m for m in basicos if m.get("type") not in dp_index.TIPOS_CHEFE]
        chefes = antes - len(basicos)
    else:
        chefes = 0

    minutos = len(basicos) * settings.divine_pride_rate_limit / 60
    console.print(
        f"{len(basicos)} monstros entre {de} e {ate}"
        + (f" ({chefes} chefes de fora)" if chefes else "")
        + f" — completar leva cerca de {minutos:.0f} min."
    )

    try:
        with DivinePrideClient(settings) as cliente, console.status("completando...") as status:
            indice = dp_index.completar(basicos, cliente, progresso=status.update, refresh=refresh)
    except DivinePrideError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(code=1) from erro

    indice = dp_index.gravar(settings, indice, acumular=acumular)
    com_spawn = len(indice["spawns"])
    mapas = {s["map"] for lista in indice["spawns"].values() for s in lista}
    console.print(
        f"[green]{len(indice['monsters'])} monstros, {com_spawn} com spawn em {len(mapas)} mapas[/green]"
        f" → {settings.index_path}\nUse: ragleveling cacar --nivel <n> --classe <classe>"
    )


#: Acima disso, `dp-itens` pede confirmação antes de consultar a API: a
#: documentação do Divine Pride revoga a chave de quem varre o banco.
MINUTOS_SEM_CONFIRMAR = 30

_CATEGORIAS_AJUDA = " | ".join(dp_itens.CATEGORIAS)
_LOCAIS_AJUDA = ", ".join(k for k in dp_itens.LOCAIS if "-" not in k) + ", traje-*, sombra-*"


@app.command("dp-item")
def dp_item(
    item_id: int = typer.Argument(..., help="ID do item no Divine Pride."),
    refresh: bool = typer.Option(False, "--refresh", help="Ignora o cache e consulta de novo."),
) -> None:
    """Mostra o que a API do Divine Pride devolve para um item.

    Serve para conferir o formato do JSON: quais campos vieram e o que o
    ragleveling entendeu deles — em especial o local de equipar.
    """
    settings = get_settings()
    try:
        with DivinePrideClient(settings) as cliente:
            payload = cliente.item(item_id, refresh=refresh)
            destino = cliente.cache_dir / f"item-{item_id}.json"
    except DivinePrideError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(code=1) from erro

    item = dp_itens.normalizar_item(payload, {"id": item_id})
    console.print(f"[bold]Campos no topo do payload:[/bold] {', '.join(sorted(payload))}")
    console.print(f"[bold]Nome:[/bold] {escape(item['name'])}")
    console.print(f"[bold]Tipo:[/bold] {item['type']} / {item['subtype'] or '—'}")

    if item["location_raw"]:
        entendidos = [
            f"{bruto} → {dp_itens.normalizar_local(bruto, item['type']) or '[red]não entendido[/red]'}"
            for bruto in item["location_raw"]
        ]
        console.print(f"[bold]Local no payload:[/bold] {'; '.join(entendidos)}")
    else:
        pista = ", ".join(item["locations"]) or "nenhuma"
        console.print(f"[yellow]O payload não traz local.[/yellow] Pelo subtipo: {pista}")

    console.print(Panel(Text(item["description"] or "(sem descrição)"), title="Descrição", title_align="left"))
    console.print(f"[dim]JSON cru salvo em {destino}[/dim]")


@app.command("dp-itens")
def dp_itens_cmd(
    categoria: list[str] = typer.Option(
        ..., "--categoria", "-c", help=f"Categoria da listagem; pode repetir. {_CATEGORIAS_AJUDA}"
    ),
    subtipo: list[str] = typer.Option(
        [], "--subtipo", "-s", help="Subtipo do site (Headgear, Shield, Garment...); pode repetir."
    ),
    funcao: int | None = typer.Option(
        None, "--funcao", help="ID da função no filtro do site (21 = aumenta o dano contra uma raça)."
    ),
    descricao: str | None = typer.Option(None, "--descricao", help="Texto que a descrição do item deve ter."),
    busca: str | None = typer.Option(None, "--busca", help="Trecho do nome do item."),
    limite: int | None = typer.Option(None, "--limite", "-l", help="Para depois de N itens por categoria."),
    refresh: bool = typer.Option(False, "--refresh", help="Ignora o cache das consultas."),
    acumular: bool = typer.Option(
        True, "--acumular/--recomecar", help="Soma ao índice existente em vez de substituí-lo."
    ),
    sim: bool = typer.Option(False, "--sim", "-y", help="Não pede confirmação em consultas longas."),
) -> None:
    """Monta (ou amplia) o índice de itens do LATAM a partir do Divine Pride.

    A listagem do site dá os itens que têm o selo do servidor (LATAM) e a API
    completa cada um com descrição, classes e efeitos. É uma requisição por item
    no limite da API: prefira recortes (--subtipo, --funcao, --descricao) a
    categorias inteiras. O que já foi consultado vem do cache.
    """
    invalidas = [c for c in categoria if c not in dp_itens.CATEGORIAS]
    if invalidas:
        console.print(f"[red]Categoria inválida:[/red] {', '.join(invalidas)}. Use: {', '.join(dp_itens.CATEGORIAS)}.")
        raise typer.Exit(code=1)

    settings = get_settings()
    basicos: dict[int, dict] = {}
    try:
        with console.status("consultando a listagem...") as status:
            for cat in dict.fromkeys(categoria):
                achados = dp_itens.listar(
                    cat,
                    subtipos=subtipo,
                    funcao=funcao,
                    descricao=descricao,
                    busca=busca,
                    limite=limite,
                    settings=settings,
                    progresso=status.update,
                )
                for item in achados:
                    basicos.setdefault(item["id"], item)
    except (RuntimeError, ValueError, httpx.HTTPError) as erro:
        console.print(f"[red]Falha ao ler a listagem:[/red] {erro}")
        raise typer.Exit(code=1) from erro

    if not basicos:
        servidor = settings.divine_pride_server
        console.print(f"[yellow]A listagem não devolveu itens do {servidor} para esse recorte.[/yellow]")
        raise typer.Exit(code=1)

    try:
        with DivinePrideClient(settings) as cliente:
            faltam = sum(1 for i in basicos if refresh or not (cliente.cache_dir / f"item-{i}.json").is_file())
            minutos = faltam * settings.divine_pride_rate_limit / 60
            console.print(
                f"{len(basicos)} itens do {settings.divine_pride_server}; "
                f"{faltam} ainda sem consulta — cerca de {minutos:.0f} min."
            )
            if minutos > MINUTOS_SEM_CONFIRMAR and not sim:
                typer.confirm("Consultar a API para todos?", abort=True)

            with console.status("completando...") as status:
                indice, falhas = dp_itens.completar(basicos.values(), cliente, progresso=status.update, refresh=refresh)
    except DivinePrideError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(code=1) from erro

    indice = dp_itens.gravar(settings, indice, acumular=acumular)
    console.print(f"[green]{len(indice['items'])} itens no índice[/green] → {settings.items_index_path}")

    if falhas:
        ids = ", ".join(str(f["id"]) for f in falhas[:10])
        console.print(f"[yellow]{len(falhas)} itens a API não devolveu (ex.: {ids}).[/yellow]")

    sem_local = [i for i in indice["items"] if dp_itens.sem_local(i)]
    if sem_local:
        brutos = Counter(b for i in sem_local for b in i["location_raw"])
        detalhe = ", ".join(f"{nome!r} ({qtd})" for nome, qtd in brutos.most_common(8))
        causa = (
            f"Locais não reconhecidos: {detalhe}."
            if detalhe
            else "O payload não trouxe local; veja `ragleveling dp-item <id>`."
        )
        aviso = f"{len(sem_local)} equipamentos sem local entendido"
        console.print(f"[yellow]{aviso}[/yellow] — o filtro --local não os acha. {causa}")
    console.print("Use: ragleveling itens --local <local>")


@app.command()
def itens(
    local: str | None = typer.Option(
        None, "--local", "-L", help=f"Onde equipa: {_LOCAIS_AJUDA}."
    ),
    tipo: str | None = typer.Option(None, "--tipo", "-t", help="Tipo ou subtipo: armor, weapon, card, headgear..."),
    nome: str | None = typer.Option(None, "--nome", "-n", help="Trecho do nome."),
    texto: str | None = typer.Option(None, "--texto", help="Palavras que a descrição deve ter."),
    item_id: int | None = typer.Option(None, "--id", help="Um item específico (já mostra a descrição completa)."),
    completo: bool = typer.Option(False, "--completo", "-d", help="Mostra a descrição completa de cada item."),
    limite: int = typer.Option(30, "--limite", "-l"),
) -> None:
    """Busca no índice de itens, filtrando por local de equipar, e mostra a descrição."""
    local_canonico = None
    if local is not None:
        local_canonico = dp_itens.local_digitado(local)
        if local_canonico is None:
            console.print(f"[red]Local inválido:[/red] {local}. Use: {', '.join(dp_itens.LOCAIS)}.")
            raise typer.Exit(code=1)

    try:
        indice = dp_itens.carregar(get_settings())
    except dp_itens.IndiceIndisponivel as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(code=1) from erro

    achados = dp_itens.filtrar(indice, local=local_canonico, tipo=tipo, nome=nome, texto=texto, item_id=item_id)
    if not achados:
        console.print("[yellow]Nenhum item com esses filtros no índice.[/yellow]")
        raise typer.Exit(code=1)

    mostrados = achados[:limite]
    if item_id is not None or completo:
        for item in mostrados:
            locais = ", ".join(dp_itens.LOCAIS[k] for k in item["locations"]) or "—"
            nivel = f" · nível {item['required_level']}" if item["required_level"] else ""
            console.print(
                Panel(
                    Text(item["description"] or "(sem descrição)"),
                    title=f"{item['name']} ({item['id']})",
                    subtitle=f"{item['type']} / {item['subtype'] or '—'} · {locais}{nivel}",
                    title_align="left",
                )
            )
    else:
        tabela = Table(title=f"{len(achados)} itens")
        tabela.add_column("Item", no_wrap=True)
        tabela.add_column("Local")
        tabela.add_column("Lv", justify="right")
        tabela.add_column("Tipo")
        for item in mostrados:
            tabela.add_row(
                f"[link={url_divine_pride_item(item['id'])}]{escape(item['name'])}[/link]",
                ", ".join(dp_itens.LOCAIS[k] for k in item["locations"]) or "—",
                str(item["required_level"] or "—"),
                f"{item['type']} / {item['subtype'] or '—'}",
            )
        console.print(tabela)
        console.print("[dim]Nomes são links para o Divine Pride. Use --completo para a descrição de cada item.[/dim]")

    if len(achados) > len(mostrados):
        console.print(f"[dim]Mostrando {len(mostrados)} de {len(achados)}; aumente --limite.[/dim]")


if __name__ == "__main__":
    app()
