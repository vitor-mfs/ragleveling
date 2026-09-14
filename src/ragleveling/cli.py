"""CLI do ragleveling."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .catalog import Catalog, carregar
from .config import get_settings
from .hunt import FAIXA_PADRAO, MIN_SPAWN_PADRAO
from .hunt import cacar as buscar_alvos
from .jobs import Perfil, canonical_job_key, display_name, perfil_de, sugerir
from .models import Character, ServerRates
from .rathena import SyncError, carregar_indice
from .rathena import sync as sincronizar
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
def sync(
    force: bool = typer.Option(False, "--force", "-f", help="Rebaixa tudo, ignorando o cache."),
) -> None:
    """Baixa monstros, habilidades, spawns e tabela elemental do rAthena."""
    settings = get_settings()
    console.print(f"[dim]cache: {settings.cache_dir}[/dim]")
    with console.status("baixando...") as status:
        try:
            resultado = sincronizar(settings, force=force, progresso=status.update)
        except SyncError as erro:
            console.print(f"[red]Falha no sync:[/red] {erro}")
            raise typer.Exit(code=1) from erro

    console.print(
        f"[green]Pronto em {resultado.segundos:.0f}s.[/green] "
        f"{resultado.arquivos_baixados} arquivos baixados, "
        f"{resultado.arquivos_reaproveitados} já em cache.\n"
        f"{resultado.monstros} monstros, {resultado.monstros_com_spawn} com spawn, "
        f"{resultado.mapas} mapas."
    )


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
        indice = carregar_indice(get_settings())
    except SyncError as erro:
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



if __name__ == "__main__":
    app()
