"""CLI do ragleveling."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .catalog import Catalog, carregar
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


if __name__ == "__main__":
    app()
