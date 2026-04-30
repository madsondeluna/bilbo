"""Terminal visualizer for build composition using Rich."""

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table


def render_composition(build_dir: Path, console: Console | None = None) -> None:
    if console is None:
        console = Console()

    report_path = build_dir / "build_report.json"
    if not report_path.exists():
        console.print(f"[red]build_report.json not found in {build_dir}[/red]")
        return

    report = json.loads(report_path.read_text(encoding="utf-8"))

    console.print("\n[bold]BILBO Build Composition[/bold]")
    console.print(f"  Preset: {report.get('preset_id', '?')}")
    console.print(f"  Force field: {report.get('force_field', '?')}")
    console.print(f"  Lipids per leaflet: {report.get('lipids_per_leaflet', '?')}")

    desired = report.get("desired_composition", {})
    realized = report.get("realized_composition", {})
    rounding = report.get("rounding_errors", {})

    for leaflet in desired:
        table = Table(title=f"{leaflet.upper()} Leaflet", show_lines=True)
        table.add_column("Lipid")
        table.add_column("Desired %", justify="right")
        table.add_column("Count", justify="right")
        table.add_column("Rounding error", justify="right")

        d_comp = desired.get(leaflet, {})
        r_comp = realized.get(leaflet, {})
        rnd = rounding.get(leaflet, {})

        for lid in d_comp:
            table.add_row(
                lid,
                f"{d_comp[lid]:.1f}",
                str(r_comp.get(lid, 0)),
                f"{rnd.get(lid, 0.0):.3f}",
            )

        console.print(table)

    warnings = report.get("warnings", [])
    errors = report.get("errors", [])
    generated = report.get("generated_files", [])

    if warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in warnings:
            console.print(f"  [yellow]{w}[/yellow]")

    if errors:
        console.print("\n[red]Errors:[/red]")
        for e in errors:
            console.print(f"  [red]{e}[/red]")

    if generated:
        console.print("\n[green]Generated files:[/green]")
        for f in generated:
            console.print(f"  {f}")
