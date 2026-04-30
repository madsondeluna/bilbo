"""Terminal visualizer for leaflet grid using Rich."""

import csv
import json
from pathlib import Path

from rich.console import Console

SYMBOL_MAP = {
    "POPC": "P",
    "POPE": "E",
    "POPG": "G",
    "POPS": "S",
    "CHOL": "C",
    "CL": "L",
    "SM": "M",
    "PI": "I",
    "DOPC": "D",
    "DOPE": "O",
    "DPPC": "Q",
}


def _get_symbol(lipid_id: str, used: dict[str, str]) -> str:
    if lipid_id in SYMBOL_MAP:
        sym = SYMBOL_MAP[lipid_id]
    else:
        sym = lipid_id[:2].upper()
    if sym in used.values() and used.get(lipid_id) != sym:
        sym = lipid_id[:2].upper()
        if sym in used.values():
            sym = lipid_id[:1].upper() + str(len(used))
    used[lipid_id] = sym
    return sym


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def render_leaflet_map(build_dir: Path, console: Console | None = None) -> None:
    if console is None:
        console = Console()

    report_path = build_dir / "build_report.json"
    upper_path = build_dir / "upper_leaflet.csv"
    lower_path = build_dir / "lower_leaflet.csv"

    if not upper_path.exists() or not lower_path.exists():
        console.print(f"[red]Leaflet CSV files not found in {build_dir}[/red]")
        return

    report = {}
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))

    console.print("\n[bold]BILBO Leaflet Map[/bold]")
    if report:
        console.print(f"  Preset: {report.get('preset_id', '?')}")
        console.print(f"  Force field: {report.get('force_field', '?')}")
        console.print(f"  Seed: {report.get('seed', '?')}")
        console.print(f"  Sorting: {report.get('sorting_mode', '?')}")

    symbol_map: dict[str, str] = {}

    for leaflet_name, csv_path in (("upper", upper_path), ("lower", lower_path)):
        rows = _read_csv(csv_path)
        if not rows:
            continue

        xs = [float(r["x"]) for r in rows]
        ys = [float(r["y"]) for r in rows]
        x_vals = sorted(set(round(x, 3) for x in xs))
        y_vals = sorted(set(round(y, 3) for y in ys))

        grid: dict[tuple, str] = {}
        for r in rows:
            key = (round(float(r["x"]), 3), round(float(r["y"]), 3))
            sym = _get_symbol(r["lipid_id"], symbol_map)
            grid[key] = sym

        console.print(f"\n[bold]{leaflet_name.upper()} LEAFLET[/bold]")
        for y in y_vals:
            row_str = ""
            for x in x_vals:
                row_str += grid.get((x, y), ".") + " "
            console.print(row_str.rstrip())

    console.print("\n[bold]Legend[/bold]")
    for lid, sym in symbol_map.items():
        console.print(f"  {sym} = {lid}")

    if report.get("warnings"):
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in report["warnings"]:
            console.print(f"  [yellow]{w}[/yellow]")
