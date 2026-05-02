"""BILBO CLI - Bilayer Lipid Builder and Organizer."""

import hashlib
import json
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table
from sqlmodel import Session

from bilbo.builders.apl_check import check_apl_balance, weighted_spacing
from bilbo.builders.composition_expander import expand_composition
from bilbo.builders.leaflet_layout import LeafletLayout, build_leaflet_layout, save_leaflet_csv
from bilbo.builders.peptide_placer import place_peptide
from bilbo.db.repository import (
    get_engine,
    get_lipid,
    get_peptide,
    get_preset,
    list_forcefield_mappings,
    list_lipids,
    list_peptides,
    list_presets,
    save_audit_report,
    save_source_manifest,
    upsert_forcefield_mapping,
    upsert_lipid,
    upsert_peptide,
    upsert_preset,
)
from bilbo.exporters.allatom_preview import write_allatom_preview
from bilbo.exporters.gromacs_topology import write_gromacs_topology
from bilbo.exporters.manifest import write_manifest
from bilbo.exporters.markdown_report import write_markdown_report
from bilbo.exporters.pymol_script import write_pymol_script
from bilbo.exporters.vmd_script import write_vmd_script
from bilbo.extractors.audit import AuditExtractor
from bilbo.extractors.charmm_gui_archive import CharmmGuiArchiveExtractor
from bilbo.extractors.forcefield_mapping import ForceFieldMappingExtractor
from bilbo.extractors.lipid_yaml import LipidYAMLExtractor
from bilbo.extractors.preset_yaml import PresetYAMLExtractor
from bilbo.extractors.reference_metadata import ReferenceMetadataExtractor
from bilbo.extractors.topology_scanner import TopologyScanner
from bilbo.models.build import BuildReport, PeptidePlacementRecord
from bilbo.models.preset import MembranePreset
from bilbo.models.peptide import PeptidePlacement
from bilbo.viewers.composition_tui import render_composition
from bilbo.viewers.leaflet_tui import render_leaflet_map


console = Console()
app = typer.Typer(
    name="bilbo",
    help="Bilayer Lipid Builder and Organizer",
    rich_markup_mode="rich",
    no_args_is_help=False,
    add_completion=False,
    context_settings={"max_content_width": 88},
)

lipid_app    = typer.Typer(help="Lipid library management",      add_completion=False)
preset_app   = typer.Typer(help="Membrane preset management",    add_completion=False)
compat_app   = typer.Typer(help="Force field compatibility",     add_completion=False)
sources_app  = typer.Typer(help="External source management",    add_completion=False)
extract_app  = typer.Typer(help="Data extraction",               add_completion=False)
peptide_app  = typer.Typer(help="Peptide library management",    add_completion=False)
membrane_app = typer.Typer(help="Membrane build and placement",  add_completion=False)
view_app     = typer.Typer(help="Terminal visualization",        add_completion=False)
export_app   = typer.Typer(help="Export previews and reports",   add_completion=False)

app.add_typer(lipid_app,    name="lipid")
app.add_typer(preset_app,   name="preset")
app.add_typer(compat_app,   name="compatibility")
app.add_typer(sources_app,  name="sources")
app.add_typer(extract_app,  name="extract")
app.add_typer(peptide_app,  name="peptide")
app.add_typer(membrane_app, name="membrane")
app.add_typer(view_app,     name="view")
app.add_typer(export_app,   name="export")

_MENU_W = 17  # column where all menu descriptions start (max cmd len + 4)


def _menu_style() -> "Style":
    from questionary import Style
    return Style([
        ("qmark",       ""),
        ("question",    "bold"),
        ("answer",      "fg:#e74c3c bold"),
        ("pointer",     "fg:#e74c3c bold"),
        ("highlighted", "fg:#e74c3c bold"),
        ("selected",    "fg:#e74c3c"),
        ("separator",   "fg:#555555"),
        ("instruction", "fg:#ffffff"),
        ("text",        ""),
    ])


def _bilbo_banner() -> None:
    try:
        ver = _pkg_version("bilbo-md")
    except Exception:
        ver = "dev"

    # Plain-text width of the membrane line (23 dots + 22 spaces = 45 chars)
    MW = 45
    PAD = "  "  # left margin

    H  = "[bold red]· · · · · · · · · · · · · · · · · · · · · · ·[/bold red]"
    To = "[yellow]| | | | | | | | | | | | | | | | | | | | | | |[/yellow]"
    Ti = "[yellow dim]| | | | | | | | | | | | | | | | | | | | | | |[/yellow dim]"

    def _c(plain_len: int, markup: str) -> str:
        """Center markup within membrane width, with left margin."""
        inner = (MW - plain_len) // 2
        return PAD + " " * inner + markup

    def _fmt_ver(v: str) -> str:
        parts = "[#e67e22]v[/#e67e22]"
        for ch in v:
            if ch == ".":
                parts += "[#e67e22].[/#e67e22]"
            else:
                parts += f"[white]{ch}[/white]"
        return parts

    title_plain = f"BILBO  v{ver}"
    title_markup = f"[bold white]BILBO[/bold white]  {_fmt_ver(ver)}"

    tagline_plain = "Bilayer  Lipid  Builder and  Organizer"
    tagline_markup = (
        "[bold red]Bi[/bold red][white]layer[/white]  "
        "[bold red]L[/bold red][white]ipid[/white]  "
        "[bold red]B[/bold red][white]uilder and[/white]  "
        "[bold red]O[/bold red][white]rganizer[/white]"
    )

    console.print()
    for row in (H, To, Ti, Ti, Ti):
        console.print(PAD + row)
    console.print()
    console.print(_c(len(title_plain), title_markup))
    console.print(_c(len(tagline_plain), tagline_markup))
    console.print()
    for row in (Ti, Ti, Ti, To, H):
        console.print(PAD + row)
    console.print()


def _version_callback(value: bool) -> None:
    if value:
        try:
            ver = _pkg_version("bilbo-md")
        except Exception:
            ver = "dev"
        typer.echo(f"bilbo {ver}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", "-v",
        callback=_version_callback,
        is_eager=True,
        hidden=True,
    ),
) -> None:
    _bootstrap_if_empty()
    if ctx.invoked_subcommand is None:
        _interactive_menu(ctx)
        raise typer.Exit()


def _print_top_help() -> None:
    import io
    import click
    from contextlib import redirect_stdout
    from typer.main import get_group

    grp = get_group(app)
    ctx = click.Context(grp, info_name="bilbo")
    buf = io.StringIO()
    with redirect_stdout(buf):
        ctx.get_help()
    raw = buf.getvalue()

    desc = (app.info.help or "").strip()
    lines = raw.splitlines()
    filtered: list[str] = []
    skip_section = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("Usage:") or (desc and s == desc):
            continue
        if s.startswith("╭─ Options") or s.startswith("+-"):
            skip_section = True
        if skip_section:
            if s.startswith("╰") or s.startswith("+-"):
                skip_section = False
            continue
        filtered.append(ln)
    while filtered and not filtered[0].strip():
        filtered.pop(0)
    typer.echo("\n".join(filtered).rstrip())


def main() -> None:
    import sys
    _bilbo_banner()
    if sys.argv[1:] in (["--help"], ["-h"]):
        _print_top_help()
        raise SystemExit(0)
    app(standalone_mode=True)


def _run_bilbo(args: list[str]) -> None:
    try:
        app(args, standalone_mode=True)
    except SystemExit:
        pass


def _interactive_menu(ctx: typer.Context) -> None:
    import sys

    if not sys.stdin.isatty():
        _print_top_help()
        return

    try:
        import questionary
    except ModuleNotFoundError:
        _print_top_help()
        return

    style = _menu_style()

    def _ch(cmd: str, desc: str = "") -> "questionary.Choice":
        label = f"{cmd:<{_MENU_W}}{desc}" if desc else cmd
        return questionary.Choice(label, value=cmd)

    choices = [
        _ch("drytest",       "run end-to-end all-atom test"),
        questionary.Separator(),
        _ch("membrane",      "build membranes and place peptides"),
        _ch("lipid",         "manage lipid library"),
        _ch("preset",        "manage membrane presets"),
        _ch("compatibility", "force field compatibility matrix"),
        questionary.Separator(),
        _ch("extract",       "data extraction tools"),
        _ch("export",        "export previews and reports"),
        questionary.Separator(),
        _ch("help",          "show full command reference"),
        _ch("quit",          "exit without running anything"),
    ]

    console.print("  What would you like to do?  [dim]↑↓  Enter[/dim]")
    answer = questionary.select(
        "",
        choices=choices,
        style=style,
        use_shortcuts=False,
        pointer=">",
        qmark="",
        instruction=" ",
    ).ask()

    if answer is None or answer == "quit":
        return

    if answer == "help":
        console.print(ctx.get_help())
        return

    if answer == "drytest":
        _run_bilbo(["drytest"])
        return

    if answer == "membrane":
        _membrane_menu()
        return

    _run_bilbo([answer, "--help"])


def _membrane_menu() -> None:
    import questionary

    style = _menu_style()

    def _ch(cmd: str, desc: str = "") -> "questionary.Choice":
        label = f"{cmd:<{_MENU_W}}{desc}" if desc else cmd
        return questionary.Choice(label, value=cmd)

    choices = [
        _ch("build",        "build directly from your own PDB files"),
        _ch("compose",      "build from a direct lipid composition"),
        _ch("build-preset", "build from a saved preset"),
        questionary.Separator(),
        questionary.Choice("back", value="back"),
    ]

    console.print("  membrane  [dim]↑↓  Enter[/dim]")
    answer = questionary.select(
        "",
        choices=choices,
        style=style,
        pointer=">",
        qmark="",
        instruction=" ",
    ).ask()

    if answer is None or answer == "back":
        return

    if answer == "build":
        _run_bilbo(["membrane", "build", "--help"])
    elif answer == "compose":
        _membrane_compose_wizard()
    elif answer == "build-preset":
        _run_bilbo(["membrane", "build-preset", "--help"])


def _membrane_compose_wizard() -> None:
    import questionary

    console.print()
    console.print("  [bold]membrane compose[/bold]  [dim]build from direct lipid composition[/dim]")
    console.print()

    style = _menu_style()

    upper = questionary.text(
        "Upper leaflet composition",
        default="POPE:70,POPG:20,CL:10",
        instruction="(e.g. POPE:70,POPG:20,CL:10)",
        qmark=" ",
        style=style,
    ).ask()
    if upper is None:
        return

    lower = questionary.text(
        "Lower leaflet composition",
        default=upper,
        instruction="(leave blank to mirror upper)",
        qmark=" ",
        style=style,
    ).ask()
    if lower is None:
        return

    n_str = questionary.text(
        "Lipids per leaflet",
        default="64",
        validate=lambda v: v.isdigit() and int(v) > 0 or "Must be a positive integer",
        qmark=" ",
        style=style,
    ).ask()
    if n_str is None:
        return

    output = questionary.text(
        "Output directory",
        default="builds/membrane",
        qmark=" ",
        style=style,
    ).ask()
    if output is None:
        return

    ff = questionary.select(
        "Force field",
        choices=["charmm36", "gromacs_charmm36"],
        default="charmm36",
        pointer=">",
        qmark=" ",
        style=style,
    ).ask()
    if ff is None:
        return

    cmd_parts = [
        "bilbo membrane compose",
        f'--upper "{upper}"',
        f'--lipids-per-leaflet {n_str}',
        f'--output {output}',
        f'--force-field {ff}',
    ]
    if lower != upper:
        cmd_parts.append(f'--lower "{lower}"')

    console.print()
    console.print("  [dim]Running:[/dim]")
    console.print(f"  [bold]{'  '.join(cmd_parts)}[/bold]")
    console.print()

    args = [
        "membrane", "compose",
        "--upper", upper,
        "--lipids-per-leaflet", n_str,
        "--output", output,
        "--force-field", ff,
    ]
    if lower != upper:
        args += ["--lower", lower]
    _run_bilbo(args)


def _drytest_step(runner, label: str, detail: str, args: list[str], env: dict) -> bool:
    console.print(f"  [dim]>[/dim] [bold]{label}[/bold]")
    console.print(f"    [dim]{detail}[/dim]")
    result = runner.invoke(app, args, env=env, catch_exceptions=False)
    if result.exit_code == 0:
        console.print("    [green]ok[/green]")
    else:
        console.print("    [red]FAIL[/red]")
        console.print(result.output)
    console.print()
    return result.exit_code == 0


@app.command("drytest")
def drytest(
    templates_dir: Path = typer.Option(
        None,
        "--templates-dir", "-t",
        help="Directory with CHARMM-GUI all-atom PDB templates (one per lipid, named by residue ID, e.g. POPE.pdb).",
    ),
) -> None:
    """End-to-end all-atom pipeline using CHARMM-GUI structural templates."""
    import os
    import shutil
    import tempfile

    from typer.testing import CliRunner

    from bilbo.db.repository import reset_engine

    _DATA = Path(__file__).parent.parent.parent / "data" / "examples"

    if templates_dir is None:
        templates_dir = _DATA / "charmm_gui"

    console.print()
    console.print("[bold]BILBO drytest[/bold]")
    console.print(f"[dim]Templates directory: {templates_dir}[/dim]")
    console.print()

    pdb_files = [p for p in sorted(templates_dir.glob("*.pdb")) if not p.name.startswith("._")]

    if not templates_dir.exists() or not pdb_files:
        console.print("  [yellow]No PDB templates found.[/yellow]")
        console.print()
        console.print("  CHARMM-GUI requires a free account. To obtain templates:")
        console.print("  1. Log in at [bold]charmm-gui.org[/bold]")
        console.print("  2. Navigate to: Input Generator > Membrane Builder > Lipid Library")
        console.print("  3. Download a PDB file for each lipid (POPE, POPG, CL, etc.)")
        console.print(f"  4. Place the .pdb files in:  [dim]{templates_dir}[/dim]")
        console.print("  5. Run this command again.")
        console.print()
        console.print("  [dim]Alternatively, provide a custom path:[/dim]")
        console.print("  [dim]  bilbo drytest allatom --templates-dir /path/to/pdbs[/dim]")
        console.print()
        raise typer.Exit(0)

    console.print(f"  [dim]Found {len(pdb_files)} template(s): {', '.join(p.stem for p in pdb_files)}[/dim]")
    console.print()

    _LIPIDS = _DATA / "lipids"
    _PRESET_FILE = _DATA / "presets" / "ecoli_inner_membrane_default.yaml"
    PRESET_ID = "ecoli_inner_membrane_default"
    FORCE_FIELD = "charmm36"
    ENGINE = "gromacs"
    LIPIDS_PER_LEAFLET = 64
    SEED = 42

    runner = CliRunner()

    console.print(f"[dim]Force field: {FORCE_FIELD}  |  Engine: {ENGINE}  |  Lipids/leaflet: {LIPIDS_PER_LEAFLET}  |  Seed: {SEED}[/dim]")
    console.print(f"[dim]Preset: {PRESET_ID}  |  Composition: POPE 70% · POPG 20% · CL 10% (symmetric)[/dim]")
    console.print("[dim]Representation: all-atom coordinates from CHARMM-GUI templates[/dim]")
    console.print()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "drytest.db"
        build_dir = tmp_path / "build"
        reset_engine(db_path)
        env = {**os.environ, "BILBO_DB_PATH": str(db_path)}

        ok = True
        ok = ok and _drytest_step(runner, "Load lipid POPE",
            f"1-palmitoyl-2-oleoyl-sn-glycero-3-phosphoethanolamine  |  headgroup: PE  |  charge: 0  |  validated ({FORCE_FIELD})",
            ["lipid", "add", str(_LIPIDS / "POPE.yaml")], env)
        ok = ok and _drytest_step(runner, "Load lipid POPG",
            f"1-palmitoyl-2-oleoyl-sn-glycero-3-phosphoglycerol  |  headgroup: PG  |  charge: -1  |  validated ({FORCE_FIELD})",
            ["lipid", "add", str(_LIPIDS / "POPG.yaml")], env)
        ok = ok and _drytest_step(runner, "Load lipid CL",
            f"Cardiolipin  |  headgroup: CL  |  charge: -2  |  validated ({FORCE_FIELD})",
            ["lipid", "add", str(_LIPIDS / "CL.yaml")], env)
        ok = ok and _drytest_step(runner, "Load preset",
            f"id: {PRESET_ID}  |  symmetric  |  POPE 70% · POPG 20% · CL 10%",
            ["preset", "add", str(_PRESET_FILE)], env)
        ok = ok and _drytest_step(runner, "Build membrane",
            f"preset: {PRESET_ID}  |  force-field: {FORCE_FIELD}  |  engine: {ENGINE}  |  lipids-per-leaflet: {LIPIDS_PER_LEAFLET}  |  seed: {SEED}",
            ["membrane", "build-preset",
             "--preset", PRESET_ID, "--force-field", FORCE_FIELD,
             "--engine", ENGINE, "--lipids-per-leaflet", str(LIPIDS_PER_LEAFLET),
             "--seed", str(SEED), "--output", str(build_dir)], env)
        ok = ok and _drytest_step(runner, "Export all-atom PDB preview",
            f"format: PDB  |  templates: {len(pdb_files)} CHARMM-GUI PDB(s)  |  output: preview_allatom.pdb",
            ["export", "allatom-preview", str(build_dir), "--templates-dir", str(templates_dir)], env)

        pdb = build_dir / "preview_allatom.pdb"
        if ok and pdb.exists():
            atom_count = sum(1 for ln in pdb.read_text().splitlines() if ln.startswith(("ATOM", "HETATM")))
            final_pdb = Path.cwd() / "drytest.pdb"
            shutil.copy(pdb, final_pdb)
            console.print(f"  [green]preview_allatom.pdb[/green]  {atom_count} atoms")
            console.print(f"  [dim]saved to:[/dim]  {final_pdb}")
            console.print()

        if ok:
            console.print("  [bold green]drytest passed[/bold green]")
        else:
            console.print("  [bold red]drytest failed[/bold red]")
            raise typer.Exit(1)
        console.print()


def _engine():
    return get_engine()


_EXAMPLES = Path(__file__).parent.parent.parent / "data" / "examples"


def _bootstrap_if_empty() -> None:
    lipids_dir   = _EXAMPLES / "lipids"
    mappings_csv = _EXAMPLES / "forcefields" / "charmm36_mapping.csv"
    presets_dir  = _EXAMPLES / "presets"

    if not lipids_dir.exists():
        return

    with Session(_engine()) as session:
        has_lipids   = bool(list_lipids(session))
        has_presets  = bool(list_presets(session))
        has_mappings = bool(list_forcefield_mappings(session))

    if has_lipids and has_presets and has_mappings:
        return

    console.print("[dim]Initializing library from bundled example data...[/dim]")

    if not has_lipids:
        lip_ext = LipidYAMLExtractor()
        for f in sorted(lipids_dir.glob("*.yaml")):
            if f.name.startswith("._"):
                continue
            try:
                result = lip_ext.extract(f)
                with Session(_engine()) as session:
                    for lip in result:
                        upsert_lipid(lip, session)
                    session.commit()
            except Exception as exc:
                console.print(f"[yellow]Bootstrap: skipped {f.name}: {exc}[/yellow]")

    if not has_mappings and mappings_csv.exists():
        ff_ext = ForceFieldMappingExtractor()
        try:
            result = ff_ext.extract(mappings_csv)
            with Session(_engine()) as session:
                for mapping in result:
                    upsert_forcefield_mapping(mapping, session)
                session.commit()
        except Exception as exc:
            console.print(f"[yellow]Bootstrap: skipped {mappings_csv.name}: {exc}[/yellow]")

    if not has_presets:
        preset_ext = PresetYAMLExtractor()
        for f in sorted(presets_dir.glob("*.yaml")):
            if f.name.startswith("._"):
                continue
            try:
                result = preset_ext.extract(f)
                with Session(_engine()) as session:
                    for preset in result:
                        upsert_preset(preset, session)
                    session.commit()
            except Exception as exc:
                console.print(f"[yellow]Bootstrap: skipped {f.name}: {exc}[/yellow]")


# ---------------------------------------------------------------------------
# Lipid commands
# ---------------------------------------------------------------------------

@lipid_app.command("add")
def lipid_add(path: Path = typer.Argument(..., help="YAML or JSON file")):
    """Add lipids from a YAML or JSON file to the library."""
    extractor = LipidYAMLExtractor()
    try:
        lipids = extractor.extract(path)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    with Session(_engine()) as session:
        for lip in lipids:
            upsert_lipid(lip, session)
        session.commit()
    console.print(f"[green]Added {len(lipids)} lipid(s) from {path}[/green]")


@lipid_app.command("list")
def lipid_list():
    """List all lipids in the library."""
    with Session(_engine()) as session:
        lipids = list_lipids(session)
    if not lipids:
        console.print("No lipids in library.")
        return
    table = Table(title="Lipid Library")
    table.add_column("ID")
    table.add_column("Class")
    table.add_column("Status")
    table.add_column("Force fields")
    for lip in lipids:
        table.add_row(
            lip.id,
            lip.lipid_class,
            lip.curation_status,
            ", ".join(lip.force_fields.keys()),
        )
    console.print(table)


@lipid_app.command("show")
def lipid_show(lipid_id: str = typer.Argument(...)):
    """Show details of a lipid."""
    with Session(_engine()) as session:
        lip = get_lipid(lipid_id, session)
    if lip is None:
        console.print(f"[red]Lipid '{lipid_id}' not found.[/red]")
        raise typer.Exit(1)
    console.print_json(lip.model_dump_json(indent=2))


@lipid_app.command("validate")
def lipid_validate(path: Path = typer.Argument(..., help="YAML or JSON file")):
    """Validate lipid file without adding to library."""
    extractor = LipidYAMLExtractor()
    try:
        lipids = extractor.extract(path)
        console.print(f"[green]Valid: {len(lipids)} lipid(s) in {path}[/green]")
    except ValueError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Preset commands
# ---------------------------------------------------------------------------

@preset_app.command("add")
def preset_add(path: Path = typer.Argument(...)):
    """Add presets from a YAML or JSON file."""
    extractor = PresetYAMLExtractor()
    try:
        presets = extractor.extract(path)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    with Session(_engine()) as session:
        for p in presets:
            upsert_preset(p, session)
        session.commit()
    console.print(f"[green]Added {len(presets)} preset(s) from {path}[/green]")


@preset_app.command("list")
def preset_list():
    """List all presets."""
    with Session(_engine()) as session:
        presets = list_presets(session)
    if not presets:
        console.print("No presets in library.")
        return
    table = Table(title="Membrane Presets")
    table.add_column("ID")
    table.add_column("Organism")
    table.add_column("Symmetry")
    table.add_column("Leaflets")
    for p in presets:
        table.add_row(
            p.id,
            p.organism or "-",
            p.symmetry,
            ", ".join(p.leaflets.keys()),
        )
    console.print(table)


@preset_app.command("show")
def preset_show(preset_id: str = typer.Argument(...)):
    """Show details of a preset."""
    with Session(_engine()) as session:
        p = get_preset(preset_id, session)
    if p is None:
        console.print(f"[red]Preset '{preset_id}' not found.[/red]")
        raise typer.Exit(1)
    console.print_json(p.model_dump_json(indent=2))


@preset_app.command("validate")
def preset_validate(path: Path = typer.Argument(...)):
    """Validate preset file without adding."""
    extractor = PresetYAMLExtractor()
    try:
        presets = extractor.extract(path)
        console.print(f"[green]Valid: {len(presets)} preset(s) in {path}[/green]")
    except ValueError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Compatibility commands
# ---------------------------------------------------------------------------

@compat_app.command("matrix")
def compat_matrix():
    """Show compatibility matrix of lipids vs force fields."""
    with Session(_engine()) as session:
        lipids = list_lipids(session)
    if not lipids:
        console.print("No lipids in library.")
        return
    all_ffs = set()
    for lip in lipids:
        all_ffs.update(lip.force_fields.keys())
    all_ffs_sorted = sorted(all_ffs)

    table = Table(title="Compatibility Matrix")
    table.add_column("Lipid")
    for ff in all_ffs_sorted:
        table.add_column(ff)

    for lip in lipids:
        row = [lip.id]
        for ff in all_ffs_sorted:
            if ff in lip.force_fields:
                row.append(lip.force_fields[ff].status)
            else:
                row.append("-")
        table.add_row(*row)
    console.print(table)


@compat_app.command("check")
def compat_check(
    preset: str = typer.Option(..., "--preset"),
    force_field: str = typer.Option(..., "--force-field"),
):
    """Check compatibility of a preset with a force field."""
    with Session(_engine()) as session:
        p = get_preset(preset, session)
        if p is None:
            console.print(f"[red]Preset '{preset}' not found.[/red]")
            raise typer.Exit(1)
        lipids = list_lipids(session)
    lipid_map = {lip.id: lip for lip in lipids}

    errors = []
    warnings = []
    for lid in p.all_lipid_ids():
        if lid not in lipid_map:
            errors.append(f"Lipid '{lid}' not in library.")
            continue
        lip = lipid_map[lid]
        if force_field not in lip.force_fields:
            errors.append(f"Lipid '{lid}' has no mapping for force field '{force_field}'.")
        else:
            st = lip.force_fields[force_field].status
            if st not in ("validated", "available"):
                warnings.append(f"Lipid '{lid}' force field status: '{st}'.")

    if errors:
        console.print("[red]Compatibility errors:[/red]")
        for e in errors:
            console.print(f"  [red]{e}[/red]")
        raise typer.Exit(1)
    if warnings:
        for w in warnings:
            console.print(f"[yellow]Warning: {w}[/yellow]")
    console.print(f"[green]Preset '{preset}' is compatible with '{force_field}'.[/green]")


# ---------------------------------------------------------------------------
# Sources commands
# ---------------------------------------------------------------------------

@sources_app.command("list")
def sources_list():
    """List available source downloaders."""
    from bilbo.downloaders.registry import CORE_SET, DOWNLOADERS
    console.print("[bold]Available sources:[/bold]")
    for name in DOWNLOADERS:
        console.print(f"  {name}")
    console.print("\n[bold]Core set:[/bold]")
    console.print("  " + ", ".join(CORE_SET))


@sources_app.command("fetch")
def sources_fetch(
    source: str = typer.Argument(..., help="Source name: charmm-gui, core-set"),
    html: Optional[Path] = typer.Option(None, "--html", help="Saved HTML file (charmm-gui)"),
    lipids: Optional[str] = typer.Option(None, "--lipids", help="Comma-separated lipid IDs"),
    output: Optional[Path] = typer.Option(None, "--output"),
    download: bool = typer.Option(False, "--download", help="Attempt file download"),
    force_fields: Optional[str] = typer.Option(None, "--force-fields"),
):
    """Fetch or index lipids from an external source."""
    from bilbo.downloaders.registry import CORE_SET, DOWNLOADERS

    if output is None:
        output = Path(f"data/sources/{source.replace('-', '_')}/")

    lipid_filter = [lid.strip() for lid in lipids.split(",")] if lipids else None

    if source == "core-set":
        ffs = [f.strip() for f in force_fields.split(",")] if force_fields else ["charmm36"]
        console.print(f"[bold]Core set:[/bold] {', '.join(CORE_SET)}")
        console.print(f"Force fields: {', '.join(ffs)}")
        console.print("Use 'bilbo sources fetch charmm-gui' to index.")
        return

    if source not in DOWNLOADERS:
        console.print(f"[red]Unknown source '{source}'. Available: {list(DOWNLOADERS.keys())}[/red]")
        raise typer.Exit(1)

    downloader_cls = DOWNLOADERS[source]
    downloader = downloader_cls()

    if source == "charmm-gui":
        if html is None:
            console.print("[red]--html is required for charmm-gui source.[/red]")
            raise typer.Exit(1)
        manifest = downloader.fetch(
            output_dir=output,
            html_path=html,
            lipid_filter=lipid_filter,
            do_download=download,
        )
    else:
        manifest = downloader.fetch(output_dir=output)

    with Session(_engine()) as session:
        save_source_manifest(manifest, session)
        session.commit()

    console.print(f"[green]Indexed {len(manifest.lipids)} lipid(s) from {source}[/green]")
    for w in manifest.warnings:
        console.print(f"[yellow]Warning: {w}[/yellow]")


@sources_app.command("index")
def sources_index(path: Path = typer.Argument(Path("data/sources"), help="Directory to scan")):
    """Scan local source directories and rebuild manifests."""
    console.print(f"Scanning {path} for source files...")
    count = 0
    for itp in path.rglob("*.itp"):
        console.print(f"  Found: {itp}")
        count += 1
    console.print(f"Found {count} topology file(s).")


@sources_app.command("audit")
def sources_audit():
    """Audit imported source entries."""
    with Session(_engine()) as session:
        lipids = list_lipids(session)
    pending = [lip for lip in lipids if lip.curation_status in ("pending_review", "downloaded")]
    console.print(f"Lipids with pending_review or downloaded status: {len(pending)}")
    for lip in pending:
        console.print(f"  [yellow]{lip.id}[/yellow] ({lip.curation_status})")


@sources_app.command("show")
def sources_show(lipid_id: str = typer.Argument(...)):
    """Show source information for a lipid."""
    with Session(_engine()) as session:
        lip = get_lipid(lipid_id, session)
    if lip is None:
        console.print(f"[red]Lipid '{lipid_id}' not found.[/red]")
        raise typer.Exit(1)
    console.print(f"ID: {lip.id}")
    console.print(f"Source: {lip.source}")
    console.print(f"Status: {lip.curation_status}")


# ---------------------------------------------------------------------------
# Extract commands
# ---------------------------------------------------------------------------

@extract_app.command("lipids")
def extract_lipids(path: Path = typer.Argument(...)):
    """Extract lipids from YAML/JSON and add to library."""
    lipid_add(path)


@extract_app.command("presets")
def extract_presets(path: Path = typer.Argument(...)):
    """Extract presets from YAML/JSON and add to library."""
    preset_add(path)


@extract_app.command("mappings")
def extract_mappings(path: Path = typer.Argument(...)):
    """Extract force field mappings from CSV/TSV."""
    extractor = ForceFieldMappingExtractor()
    try:
        mappings = extractor.extract(path)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    with Session(_engine()) as session:
        for ffm in mappings:
            upsert_forcefield_mapping(ffm, session)
        session.commit()
    console.print(f"[green]Extracted {len(mappings)} mapping(s) from {path}[/green]")


@extract_app.command("charmm-gui-archive")
def extract_charmm_gui(
    html_file: Path = typer.Argument(...),
    output_dir: Path = typer.Option(Path("/tmp/bilbo_charmm"), "--output-dir"),
):
    """Extract CHARMM-GUI lipid catalog from saved HTML."""
    extractor = CharmmGuiArchiveExtractor()
    try:
        paths = extractor.extract_and_save(html_file, output_dir)
        console.print("[green]Extracted to:[/green]")
        for fmt, p in paths.items():
            console.print(f"  {fmt}: {p}")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)


@extract_app.command("topologies")
def extract_topologies(path: Path = typer.Argument(...)):
    """Scan topology files and report residue names found."""
    scanner = TopologyScanner()
    result = scanner.scan(path)
    console.print(f"Files scanned: {len(result.topology_files_scanned)}")
    console.print(f"Residues found: {sorted(result.found_residues)}")

    with Session(_engine()) as session:
        mappings = list_forcefield_mappings(session)

    if mappings:
        residues_to_check = [m.residue_name for m in mappings]
        result2 = scanner.scan(path, residues_to_check=residues_to_check)
        if result2.missing_residues:
            console.print(f"[yellow]Missing residues:[/yellow] {sorted(result2.missing_residues)}")
        else:
            console.print("[green]All mapped residues found in topologies.[/green]")


@extract_app.command("references")
def extract_references(path: Path = typer.Argument(...)):
    """Extract and validate reference metadata."""
    extractor = ReferenceMetadataExtractor()
    try:
        refs = extractor.extract(path)
        console.print(f"[green]Valid: {len(refs)} reference(s) in {path}[/green]")
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)


@extract_app.command("audit")
def extract_audit():
    """Audit the full library for consistency issues."""
    with Session(_engine()) as session:
        lipids = list_lipids(session)
        presets = list_presets(session)

    auditor = AuditExtractor()
    result = auditor.audit_library(lipids, presets)

    if result.errors:
        console.print("[red]ERRORS:[/red]")
        for e in result.errors:
            console.print(f"  [red]{e}[/red]")
    if result.warnings:
        console.print("[yellow]WARNINGS:[/yellow]")
        for w in result.warnings:
            console.print(f"  [yellow]{w}[/yellow]")
    if result.ok() and not result.warnings:
        console.print("[green]Audit passed with no issues.[/green]")

    with Session(_engine()) as session:
        save_audit_report(result.errors, result.warnings, session)
        session.commit()

    if not result.ok():
        raise typer.Exit(1)


@extract_app.command("all")
def extract_all(path: Path = typer.Argument(Path("data/examples"), help="Data directory")):
    """Extract all data from a directory."""
    for subdir, extractor_fn in (
        ("lipids", extract_lipids),
        ("presets", extract_presets),
        ("forcefields", extract_mappings),
    ):
        subpath = path / subdir
        if subpath.exists():
            extractor_fn(subpath)


# ---------------------------------------------------------------------------
# Peptide commands
# ---------------------------------------------------------------------------

@peptide_app.command("add")
def peptide_add(path: Path = typer.Argument(...)):
    """Add peptide metadata from a YAML or structure file."""
    import yaml as _yaml
    from pydantic import ValidationError

    from bilbo.models.peptide import Peptide

    suffix = path.suffix.lower()
    if suffix == ".pdb":
        peptide_id = path.stem.upper()
        peptide = Peptide(
            id=peptide_id,
            name=peptide_id,
            structure_file=str(path),
            structure_format="pdb",
            curation_status="pending_review",
        )
    elif suffix in (".yaml", ".yml", ".json"):
        if suffix == ".json":
            import json as _json
            data = _json.loads(path.read_text(encoding="utf-8"))
        else:
            data = _yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            peptide = Peptide.model_validate(data)
        except ValidationError as exc:
            console.print(f"[red]Validation error:[/red] {exc}")
            raise typer.Exit(1)
    else:
        console.print(f"[red]Unsupported file type: {suffix}[/red]")
        raise typer.Exit(1)

    with Session(_engine()) as session:
        upsert_peptide(peptide, session)
        session.commit()
    console.print(f"[green]Added peptide '{peptide.id}'[/green]")


@peptide_app.command("list")
def peptide_list():
    """List all peptides in the library."""
    with Session(_engine()) as session:
        peptides = list_peptides(session)
    if not peptides:
        console.print("No peptides in library.")
        return
    table = Table(title="Peptide Library")
    table.add_column("ID")
    table.add_column("Format")
    table.add_column("Status")
    for pep in peptides:
        table.add_row(pep.id, pep.structure_format or "-", pep.curation_status)
    console.print(table)


@peptide_app.command("show")
def peptide_show(peptide_id: str = typer.Argument(...)):
    """Show details of a peptide."""
    with Session(_engine()) as session:
        pep = get_peptide(peptide_id, session)
    if pep is None:
        console.print(f"[red]Peptide '{peptide_id}' not found.[/red]")
        raise typer.Exit(1)
    console.print_json(pep.model_dump_json(indent=2))


@peptide_app.command("validate")
def peptide_validate(path: Path = typer.Argument(...)):
    """Validate peptide YAML file without adding."""
    import yaml as _yaml
    from pydantic import ValidationError

    from bilbo.models.peptide import Peptide

    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    elif suffix == ".json":
        import json as _json
        data = _json.loads(path.read_text(encoding="utf-8"))
    else:
        console.print(f"[red]Unsupported file type: {suffix}[/red]")
        raise typer.Exit(1)
    try:
        pep = Peptide.model_validate(data)
        console.print(f"[green]Valid peptide: {pep.id}[/green]")
    except ValidationError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Membrane build
# ---------------------------------------------------------------------------

@membrane_app.command("build-preset")
def membrane_build(
    preset: str = typer.Option(..., "--preset"),
    force_field: str = typer.Option(..., "--force-field"),
    engine: str = typer.Option("gromacs", "--engine"),
    lipids_per_leaflet: int = typer.Option(..., "--lipids-per-leaflet"),
    sorting: str = typer.Option("random", "--sorting"),
    seed: int = typer.Option(42, "--seed"),
    output: Path = typer.Option(..., "--output"),
    ff_dir: str = typer.Option("charmm36.ff", "--ff-dir", help="GROMACS force-field directory name (e.g. charmm36-jul2022.ff)."),
    allatom_dir: Path = typer.Option(None, "--allatom-dir", help="Directory with CHARMM-GUI PDB templates."),
    spacing: Optional[float] = typer.Option(None, "--spacing", help="Grid spacing in nm. Defaults to APL-weighted spacing from reference data."),
    bilayer_gap: float = typer.Option(6.0, "--bilayer-gap", help="Total gap at the bilayer center between the two monolayers (Angstrom)."),
):
    """Build a membrane preview from a named preset in the local library."""
    with Session(_engine()) as session:
        p = get_preset(preset, session)
        if p is None:
            console.print(f"[red]Preset '{preset}' not found. Add it first with 'bilbo preset add'.[/red]")
            raise typer.Exit(1)
        lipids = list_lipids(session)

    lipid_map = {lip.id: lip for lip in lipids}
    errors: list[str] = []
    warnings: list[str] = []

    for lid in p.all_lipid_ids():
        if lid not in lipid_map:
            errors.append(f"Lipid '{lid}' not found in library.")
        elif not lipid_map[lid].is_buildable():
            errors.append(
                f"Lipid '{lid}' has curation_status='{lipid_map[lid].curation_status}' "
                "and cannot enter a build (requires 'validated')."
            )
        elif force_field not in lipid_map[lid].force_fields:
            warnings.append(f"Lipid '{lid}' has no mapping for force field '{force_field}'.")

    if errors:
        for e in errors:
            console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    warnings.extend(check_apl_balance(p, lipids_per_leaflet))
    for w in warnings:
        console.print(f"[yellow]{w}[/yellow]")

    bilbo_ver = _pkg_version("bilbo-md")
    preset_snapshot = p.model_dump_json()

    _DATA = Path(__file__).parent.parent.parent / "data" / "examples"
    tmpl_dir = allatom_dir if allatom_dir else _DATA / "charmm_gui"
    all_lipid_ids = p.all_lipid_ids()
    lid_set = {lid.upper() for lid in all_lipid_ids}
    template_hashes: dict[str, str] = {}
    if tmpl_dir.exists():
        for pdb in sorted(tmpl_dir.glob("*.pdb")):
            if not pdb.name.startswith("._") and pdb.stem.upper() in lid_set:
                template_hashes[pdb.name] = hashlib.sha256(pdb.read_bytes()).hexdigest()

    expanded = expand_composition(p, lipids_per_leaflet)
    counts_by_leaflet = {ec.leaflet: ec.counts for ec in expanded}
    if spacing is not None:
        resolved_spacing = spacing
    else:
        resolved_spacing = weighted_spacing(counts_by_leaflet)
        if resolved_spacing is None:
            console.print(
                "[yellow]APL reference missing for one or more species; using default spacing 0.7 nm.[/yellow]"
            )
            resolved_spacing = 0.7
        else:
            console.print(f"[dim]APL-weighted grid spacing: {resolved_spacing:.3f} nm[/dim]")
    layouts = build_leaflet_layout(expanded, sorting, seed, spacing=resolved_spacing)

    output.mkdir(parents=True, exist_ok=True)

    generated_files: list[str] = []
    for leaflet_name, layout in layouts.items():
        csv_path = output / f"{leaflet_name}_leaflet.csv"
        save_leaflet_csv(layout, csv_path)
        generated_files.append(str(csv_path.name))

    desired = {lname: dict(comp) for lname, comp in p.leaflets.items()}
    realized = {ec.leaflet: ec.counts for ec in expanded}
    rounding_errors = {ec.leaflet: ec.rounding_errors for ec in expanded}

    report = BuildReport(
        preset_id=preset,
        force_field=force_field,
        engine=engine,
        lipids_per_leaflet=lipids_per_leaflet,
        sorting_mode=sorting,
        seed=seed,
        desired_composition=desired,
        realized_composition=realized,
        rounding_errors=rounding_errors,
        warnings=warnings,
        errors=errors,
        generated_files=generated_files,
        bilbo_version=bilbo_ver,
        preset_snapshot=preset_snapshot,
        template_hashes=template_hashes,
    )

    _write_build_outputs(output, layouts, all_lipid_ids, report, ff_dir=ff_dir)

    pdbs = [pdb for pdb in tmpl_dir.glob("*.pdb") if not pdb.name.startswith("._")] if tmpl_dir.exists() else []
    if pdbs:
        aa_out = output / "preview_allatom.pdb"
        n_atoms, clash_warns = write_allatom_preview(
            layouts, tmpl_dir, aa_out, z_half_gap=bilayer_gap / 2, seed=seed
        )
        found = {pdb.stem.upper() for pdb in pdbs}
        missing = [lid for lid in all_lipid_ids if lid.upper() not in found]
        console.print(f"[green]All-atom preview: {aa_out} ({n_atoms} atoms)[/green]")
        if missing:
            console.print(f"[yellow]  No template for: {', '.join(missing)} -- skipped.[/yellow]")
        for w in clash_warns:
            console.print(f"[yellow]  {w}[/yellow]")

    console.print(f"[green]Build complete: {output}[/green]")
    _print_realized(realized)


def _parse_composition(spec: str) -> dict[str, float]:
    """Parse 'POPE:70,POPG:20,CL:10' into {'POPE': 70.0, ...}, normalized to 100."""
    result: dict[str, float] = {}
    for part in spec.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            console.print(f"[red]Invalid lipid spec '{part}': expected LIPID:PERCENT[/red]")
            raise typer.Exit(1)
        lipid_id, pct_str = part.split(":", 1)
        lipid_id = lipid_id.strip().upper()
        try:
            pct = float(pct_str.strip())
        except ValueError:
            console.print(f"[red]Invalid percent '{pct_str}' for lipid '{lipid_id}'[/red]")
            raise typer.Exit(1)
        result[lipid_id] = pct
    if not result:
        console.print("[red]Empty composition.[/red]")
        raise typer.Exit(1)
    total = sum(result.values())
    if total <= 0:
        console.print("[red]Composition total must be > 0.[/red]")
        raise typer.Exit(1)
    # normalize to 100
    if abs(total - 100.0) > 0.01:
        result = {k: round(v / total * 100, 4) for k, v in result.items()}
    return result


@membrane_app.command("compose")
def membrane_compose(
    upper: str = typer.Option(
        ...,
        "--upper",
        help="Upper leaflet composition as LIPID:PCT,LIPID:PCT (e.g. POPE:70,POPG:20,CL:10). Values are normalized to 100.",
    ),
    lower: str = typer.Option(
        None,
        "--lower",
        help="Lower leaflet composition. Defaults to same as --upper (symmetric).",
    ),
    force_field: str = typer.Option("charmm36", "--force-field", help="Force field (e.g. charmm36)."),
    engine: str = typer.Option("gromacs", "--engine"),
    lipids_per_leaflet: int = typer.Option(..., "--lipids-per-leaflet"),
    sorting: str = typer.Option("random", "--sorting"),
    seed: int = typer.Option(42, "--seed"),
    output: Path = typer.Option(..., "--output"),
    allatom_dir: Path = typer.Option(None, "--allatom-dir", help="Custom directory for all-atom PDB templates (overrides default data/examples/charmm_gui/)."),
    ff_dir: str = typer.Option("charmm36.ff", "--ff-dir", help="GROMACS force-field directory name (e.g. charmm36-jul2022.ff)."),
    spacing: Optional[float] = typer.Option(None, "--spacing", help="Grid spacing in nm. Defaults to APL-weighted spacing from reference data."),
    bilayer_gap: float = typer.Option(6.0, "--bilayer-gap", help="Total gap at the bilayer center between the two monolayers (Angstrom)."),
) -> None:
    """Build a membrane from a direct lipid composition — no preset file required.

    Lipids must already be in the library (bilbo lipid add).
    Percentages are normalized to 100 automatically.
    Always exports an all-atom PDB preview using CHARMM-GUI templates.

    Example:

      bilbo membrane compose \\
        --upper POPE:70,POPG:20,CL:10 \\
        --lipids-per-leaflet 64 --output builds/ecoli
    """
    upper_comp = _parse_composition(upper)
    lower_comp = _parse_composition(lower) if lower else dict(upper_comp)

    symmetry = "symmetric" if upper_comp == lower_comp else "asymmetric"

    try:
        preset_obj = MembranePreset(
            id="_compose_",
            description="Ad-hoc composition (bilbo membrane compose)",
            symmetry=symmetry,
            leaflets={"upper": upper_comp, "lower": lower_comp},
        )
    except Exception as exc:
        console.print(f"[red]Composition error: {exc}[/red]")
        raise typer.Exit(1)

    with Session(_engine()) as session:
        lipids = list_lipids(session)

    lipid_map = {lip.id: lip for lip in lipids}
    errors: list[str] = []
    warnings: list[str] = []

    for lid in preset_obj.all_lipid_ids():
        if lid not in lipid_map:
            errors.append(f"Lipid '{lid}' not found in library. Add it with: bilbo lipid add <file>")
        elif not lipid_map[lid].is_buildable():
            errors.append(
                f"Lipid '{lid}' status='{lipid_map[lid].curation_status}' — requires 'validated'."
            )
        elif force_field not in lipid_map[lid].force_fields:
            warnings.append(f"Lipid '{lid}' has no mapping for force field '{force_field}'.")

    if errors:
        for e in errors:
            console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    warnings.extend(check_apl_balance(preset_obj, lipids_per_leaflet))
    for w in warnings:
        console.print(f"[yellow]{w}[/yellow]")

    console.print()
    console.print(f"  [dim]Symmetry: {symmetry}[/dim]")
    console.print(f"  [dim]Upper: {', '.join(f'{k} {v:.1f}%' for k, v in upper_comp.items())}[/dim]")
    if symmetry == "asymmetric":
        console.print(f"  [dim]Lower: {', '.join(f'{k} {v:.1f}%' for k, v in lower_comp.items())}[/dim]")
    console.print()

    bilbo_ver = _pkg_version("bilbo-md")
    preset_snapshot = preset_obj.model_dump_json()

    _DATA = Path(__file__).parent.parent.parent / "data" / "examples"
    tmpl_dir = allatom_dir if allatom_dir else _DATA / "charmm_gui"
    all_lipid_ids = preset_obj.all_lipid_ids()
    lid_set = {lid.upper() for lid in all_lipid_ids}
    template_hashes: dict[str, str] = {}
    if tmpl_dir.exists():
        for pdb in sorted(tmpl_dir.glob("*.pdb")):
            if not pdb.name.startswith("._") and pdb.stem.upper() in lid_set:
                template_hashes[pdb.name] = hashlib.sha256(pdb.read_bytes()).hexdigest()

    expanded = expand_composition(preset_obj, lipids_per_leaflet)
    counts_by_leaflet = {ec.leaflet: ec.counts for ec in expanded}
    if spacing is not None:
        resolved_spacing = spacing
    else:
        resolved_spacing = weighted_spacing(counts_by_leaflet)
        if resolved_spacing is None:
            console.print(
                "[yellow]APL reference missing for one or more species; using default spacing 0.7 nm.[/yellow]"
            )
            resolved_spacing = 0.7
        else:
            console.print(f"[dim]APL-weighted grid spacing: {resolved_spacing:.3f} nm[/dim]")
    layouts = build_leaflet_layout(expanded, sorting, seed, spacing=resolved_spacing)

    output.mkdir(parents=True, exist_ok=True)

    generated_files: list[str] = []
    for leaflet_name, layout in layouts.items():
        csv_path = output / f"{leaflet_name}_leaflet.csv"
        save_leaflet_csv(layout, csv_path)
        generated_files.append(str(csv_path.name))

    desired = {lname: dict(comp) for lname, comp in preset_obj.leaflets.items()}
    realized = {ec.leaflet: ec.counts for ec in expanded}
    rounding_errors = {ec.leaflet: ec.rounding_errors for ec in expanded}

    report = BuildReport(
        preset_id="_compose_",
        force_field=force_field,
        engine=engine,
        lipids_per_leaflet=lipids_per_leaflet,
        sorting_mode=sorting,
        seed=seed,
        desired_composition=desired,
        realized_composition=realized,
        rounding_errors=rounding_errors,
        warnings=warnings,
        errors=[],
        generated_files=generated_files,
        bilbo_version=bilbo_ver,
        preset_snapshot=preset_snapshot,
        template_hashes=template_hashes,
    )

    _write_build_outputs(output, layouts, all_lipid_ids, report, ff_dir=ff_dir)

    pdbs = [pdb for pdb in tmpl_dir.glob("*.pdb") if not pdb.name.startswith("._")] if tmpl_dir.exists() else []
    if not pdbs:
        console.print(f"[yellow]No all-atom templates found in {tmpl_dir}[/yellow]")
    else:
        aa_out = output / "preview_allatom.pdb"
        n_atoms, clash_warns = write_allatom_preview(
            layouts, tmpl_dir, aa_out, z_half_gap=bilayer_gap / 2, seed=seed
        )
        found = {pdb.stem.upper() for pdb in pdbs}
        missing = [lid for lid in all_lipid_ids if lid.upper() not in found]
        console.print(f"[green]All-atom preview: {aa_out} ({n_atoms} atoms)[/green]")
        if missing:
            console.print(f"[yellow]  No template for: {', '.join(missing)} -- skipped.[/yellow]")
        for w in clash_warns:
            console.print(f"[yellow]  {w}[/yellow]")

    console.print(f"[green]Build complete: {output}[/green]")
    _print_realized(realized)


def _parse_upper_lower_pdb(
    specs: list[str],
    flag: str,
) -> dict[str, tuple[Path, int]]:
    """Parse FILE.pdb:COUNT specs into {lipid_id: (path, count)}."""
    result: dict[str, tuple[Path, int]] = {}
    for spec in specs:
        if ":" not in spec:
            console.print(f"[red]{flag}: expected FILE.pdb:COUNT, got '{spec}'[/red]")
            raise typer.Exit(1)
        file_part, count_part = spec.rsplit(":", 1)
        pdb_path = Path(file_part.strip())
        try:
            count = int(count_part.strip())
        except ValueError:
            console.print(f"[red]{flag}: count must be an integer, got '{count_part}'[/red]")
            raise typer.Exit(1)
        if count <= 0:
            console.print(f"[red]{flag}: count must be > 0 for '{pdb_path.name}'[/red]")
            raise typer.Exit(1)
        lipid_id = pdb_path.stem.upper()
        result[lipid_id] = (pdb_path, count)
    return result


def _validate_pdb_for_from_pdb(pdb_path: Path, lipid_id: str) -> None:
    """Raise SystemExit if pdb_path fails basic structural checks."""
    if not pdb_path.exists():
        console.print(f"[red]PDB file not found: {pdb_path}[/red]")
        raise typer.Exit(1)
    lines = [
        ln for ln in pdb_path.read_text(encoding="utf-8").splitlines()
        if ln.startswith(("ATOM", "HETATM"))
    ]
    if len(lines) <= 10:
        console.print(f"[red]{lipid_id}: PDB has {len(lines)} ATOM/HETATM records (minimum 10).[/red]")
        raise typer.Exit(1)
    z_vals = [float(ln[46:54]) for ln in lines]
    z_extent = max(z_vals) - min(z_vals)
    if not (5.0 <= z_extent <= 60.0):
        console.print(
            f"[red]{lipid_id}: PDB z-extent is {z_extent:.1f} A "
            f"(expected 5–60 A for a single lipid template).[/red]"
        )
        raise typer.Exit(1)


@membrane_app.command("build")
def membrane_from_pdb(
    upper_pdb: list[str] = typer.Option(
        ...,
        "--upper-pdb",
        help="Upper leaflet lipid as FILE.pdb:COUNT. Repeat for multiple species.",
    ),
    lower_pdb: list[str] = typer.Option(
        None,
        "--lower-pdb",
        help="Lower leaflet lipid as FILE.pdb:COUNT. Defaults to same as upper (symmetric).",
    ),
    seed: int = typer.Option(42, "--seed", help="Random seed for lipid placement."),
    sorting: str = typer.Option("random", "--sorting", help="Sorting mode: random or domain_enriched."),
    spacing: Optional[float] = typer.Option(
        None, "--spacing", help="Grid spacing in nm. Defaults to APL-weighted spacing from reference data."
    ),
    bilayer_gap: float = typer.Option(
        6.0, "--bilayer-gap", help="Total gap at the bilayer center between the two monolayers (Angstrom)."
    ),
    output: Path = typer.Option(..., "--output", help="Output directory."),
) -> None:
    """Build a bilayer preview directly from your own PDB files.

    No database access or preset file required. Each PDB is used as a structural
    template for one lipid species. Lipid IDs are derived from the file stem
    (uppercase).

    Example:

      bilbo membrane build \\
        --upper-pdb POPE.pdb:50 --upper-pdb POPG.pdb:14 \\
        --lower-pdb POPE.pdb:64 \\
        --seed 42 --spacing 0.7 --bilayer-gap 6.0 \\
        --output builds/my_membrane
    """
    from bilbo.builders.composition_expander import ExpandedComposition

    upper_specs = _parse_upper_lower_pdb(upper_pdb, "--upper-pdb")
    lower_specs = _parse_upper_lower_pdb(lower_pdb, "--lower-pdb") if lower_pdb else dict(upper_specs)

    for lipid_id, (pdb_path, _) in upper_specs.items():
        _validate_pdb_for_from_pdb(pdb_path, lipid_id)
    for lipid_id, (pdb_path, _) in lower_specs.items():
        if lipid_id not in upper_specs or lower_specs[lipid_id][0] != upper_specs[lipid_id][0]:
            _validate_pdb_for_from_pdb(pdb_path, lipid_id)

    template_index: dict[str, Path] = {}
    for lipid_id, (pdb_path, _) in upper_specs.items():
        template_index[lipid_id] = pdb_path
    for lipid_id, (pdb_path, _) in lower_specs.items():
        template_index[lipid_id] = pdb_path

    all_lipid_ids = sorted(template_index.keys())

    template_hashes: dict[str, str] = {
        f"{lid}.pdb": hashlib.sha256(path.read_bytes()).hexdigest()
        for lid, path in template_index.items()
    }

    upper_counts = {lid: cnt for lid, (_, cnt) in upper_specs.items()}
    lower_counts = {lid: cnt for lid, (_, cnt) in lower_specs.items()}
    upper_total = sum(upper_counts.values())
    lower_total = sum(lower_counts.values())

    expanded = [
        ExpandedComposition(leaflet="upper", counts=upper_counts, rounding_errors={}),
        ExpandedComposition(leaflet="lower", counts=lower_counts, rounding_errors={}),
    ]
    counts_by_leaflet = {"upper": upper_counts, "lower": lower_counts}
    if spacing is not None:
        resolved_spacing = spacing
    else:
        resolved_spacing = weighted_spacing(counts_by_leaflet)
        if resolved_spacing is None:
            console.print(
                "[yellow]APL reference missing for one or more species; using default spacing 0.7 nm.[/yellow]"
            )
            resolved_spacing = 0.7
        else:
            console.print(f"[dim]APL-weighted grid spacing: {resolved_spacing:.3f} nm[/dim]")
    # APL plausibility check. spacing² (nm² -> Å²) should be within the
    # physiologically observed range for phospholipid bilayers (~35-80 Å²;
    # Kucerka et al. Biophys J 2011). Values outside that range indicate a
    # spacing parameter that will produce physically unreasonable structures.
    apl_angstrom2 = (resolved_spacing * 10.0) ** 2
    if apl_angstrom2 < 35.0:
        console.print(
            f"[yellow]Warning: --spacing {resolved_spacing} nm gives an APL of {apl_angstrom2:.1f} A^2, "
            "below the physiological minimum (~35 A^2 for phospholipids). "
            "Lipids will overlap severely.[/yellow]"
        )
    elif apl_angstrom2 > 80.0:
        console.print(
            f"[yellow]Warning: --spacing {resolved_spacing} nm gives an APL of {apl_angstrom2:.1f} A^2, "
            "above the physiological maximum (~80 A^2 for phospholipids). "
            "The bilayer will have unrealistically large inter-lipid gaps.[/yellow]"
        )
    layouts = build_leaflet_layout(expanded, sorting, seed, spacing=resolved_spacing)

    output.mkdir(parents=True, exist_ok=True)
    generated_files: list[str] = []

    for leaflet_name, layout in layouts.items():
        csv_path = output / f"{leaflet_name}_leaflet.csv"
        save_leaflet_csv(layout, csv_path)
        generated_files.append(csv_path.name)

    symmetry = "symmetric" if upper_counts == lower_counts else "asymmetric"
    upper_pct = {lid: cnt / upper_total * 100 for lid, cnt in upper_counts.items()}
    lower_pct = {lid: cnt / lower_total * 100 for lid, cnt in lower_counts.items()}

    try:
        bilbo_ver = _pkg_version("bilbo-md")
    except Exception:
        bilbo_ver = "dev"

    report = BuildReport(
        preset_id="_from_pdb_",
        force_field="none",
        engine="none",
        lipids_per_leaflet=upper_total,
        sorting_mode=sorting,
        seed=seed,
        desired_composition={"upper": upper_pct, "lower": lower_pct},
        realized_composition={"upper": upper_counts, "lower": lower_counts},
        warnings=[],
        errors=[],
        generated_files=generated_files,
        bilbo_version=bilbo_ver,
        template_hashes=template_hashes,
    )

    aa_out = output / "preview_allatom.pdb"
    n_atoms, clash_warns = write_allatom_preview(
        layouts,
        output,
        aa_out,
        z_half_gap=bilayer_gap / 2,
        template_index=template_index,
        seed=seed,
    )
    generated_files.append("preview_allatom.pdb")
    report.generated_files = generated_files

    console.print(f"[green]All-atom preview: {aa_out} ({n_atoms} atoms)[/green]")
    for w in clash_warns:
        console.print(f"[yellow]  {w}[/yellow]")

    write_manifest(
        output,
        generated_files,
        bilbo_version=bilbo_ver,
        template_hashes=template_hashes,
    )

    output.joinpath("build_report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )

    console.print(f"[green]Build complete ({symmetry}): {output}[/green]")
    console.print(f"  upper: {upper_total} lipids  lower: {lower_total} lipids")


def _write_build_outputs(
    output: Path,
    layouts: dict[str, LeafletLayout],
    lipid_ids: list[str],
    report: BuildReport,
    ff_dir: str = "charmm36.ff",
) -> None:
    vmd_path = output / "view_vmd.tcl"
    write_vmd_script(vmd_path, lipid_ids=lipid_ids)
    report.generated_files.append("view_vmd.tcl")

    pymol_path = output / "view_pymol.pml"
    write_pymol_script(pymol_path, lipid_ids=lipid_ids)
    report.generated_files.append("view_pymol.pml")

    if report.engine == "gromacs":
        top_path = output / "topol.top"
        write_gromacs_topology(layouts, top_path, ff_dir=ff_dir)
        report.generated_files.append("topol.top")
        console.print(f"[green]GROMACS topology: {top_path}[/green]")

    md_path = output / "report.md"
    write_markdown_report(report, md_path)
    report.generated_files.append("report.md")

    write_manifest(
        output,
        report.generated_files,
        bilbo_version=report.bilbo_version,
        template_hashes=report.template_hashes or None,
    )
    output.joinpath("build_report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )


def _print_realized(realized: dict[str, dict[str, int]]) -> None:
    for leaflet, comp in realized.items():
        total = sum(comp.values())
        console.print(f"  {leaflet}: {total} lipids")


@membrane_app.command("place")
def membrane_add_peptide(
    build_dir: Path = typer.Argument(...),
    peptide: Optional[Path] = typer.Option(None, "--peptide"),
    placement: Optional[Path] = typer.Option(None, "--placement"),
    leaflet: str = typer.Option("upper", "--leaflet"),
    orientation: str = typer.Option("parallel", "--orientation"),
    x: float = typer.Option(0.0, "--x"),
    y: float = typer.Option(0.0, "--y"),
    depth: float = typer.Option(0.0, "--depth"),
    rotation_deg: float = typer.Option(0.0, "--rotation-deg"),
    tilt_deg: float = typer.Option(0.0, "--tilt-deg"),
    azimuth_deg: float = typer.Option(0.0, "--azimuth-deg"),
    allow_overlap: bool = typer.Option(False, "--allow-overlap"),
    output: Optional[Path] = typer.Option(None, "--output"),
):
    """Position a peptide on the membrane preview."""
    out_dir = output or build_dir

    if placement is not None:
        data = yaml.safe_load(placement.read_text(encoding="utf-8"))
        pp = PeptidePlacement.model_validate(data)
        if peptide is not None:
            pp.input_structure = str(peptide)
    elif peptide is not None:
        pp = PeptidePlacement(
            peptide_id=peptide.stem.upper(),
            placement_id=f"{peptide.stem}_placement",
            input_structure=str(peptide),
            leaflet=leaflet,
            orientation=orientation,
            x=x,
            y=y,
            depth=depth,
            rotation_deg=rotation_deg,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            allow_overlap=allow_overlap,
        )
    else:
        console.print("[red]Provide --peptide and/or --placement.[/red]")
        raise typer.Exit(1)

    report_path = build_dir / "build_report.json"
    if not report_path.exists():
        console.print(f"[red]build_report.json not found in {build_dir}. Run 'bilbo membrane build' first.[/red]")
        raise typer.Exit(1)

    report = BuildReport.model_validate_json(report_path.read_text(encoding="utf-8"))

    # Compute actual membrane surface z from the all-atom preview so that
    # surface placement aligns to the real headgroup positions, not hardcoded defaults.
    surface_z: dict[str, float] | None = None
    preview_pdb = build_dir / "preview_allatom.pdb"
    if preview_pdb.exists():
        upper_z: list[float] = []
        lower_z: list[float] = []
        for ln in preview_pdb.read_text(encoding="utf-8").splitlines():
            if ln.startswith(("ATOM", "HETATM")) and len(ln) > 54:
                chain = ln[21]
                z = float(ln[46:54])
                if chain == "U":
                    upper_z.append(z)
                elif chain == "L":
                    lower_z.append(z)
        if upper_z and lower_z:
            surface_z = {"upper": max(upper_z), "lower": min(lower_z)}

    placement_result = place_peptide(pp, surface_z=surface_z)

    ppr = PeptidePlacementRecord(
        peptide_id=pp.peptide_id,
        placement_id=pp.placement_id,
        orientation=placement_result.orientation,
        leaflet=placement_result.leaflet,
        translation_vector=placement_result.translation_vector,
        rotation_matrix=placement_result.rotation_matrix,
        tilt_deg=placement_result.tilt_deg,
        rotation_deg=placement_result.rotation_deg,
        azimuth_deg=placement_result.azimuth_deg,
        anchor_mode=placement_result.anchor_mode,
        collision_count=placement_result.collision_count,
        minimum_distance_to_membrane=placement_result.minimum_distance_to_membrane,
        warnings=placement_result.warnings,
    )
    report.peptide_placements.append(ppr)
    report.geometry_warnings.extend(placement_result.warnings)

    placements_path = out_dir / "peptide_placements.json"
    placements_data = [pp_r.model_dump() for pp_r in report.peptide_placements]
    placements_path.write_text(json.dumps(placements_data, indent=2), encoding="utf-8")

    geometry_report = {
        "peptide_id": placement_result.peptide_id,
        "placement_id": placement_result.placement_id,
        "input_structure": placement_result.input_structure,
        "orientation": placement_result.orientation,
        "leaflet": placement_result.leaflet,
        "translation_vector": placement_result.translation_vector,
        "rotation_matrix": placement_result.rotation_matrix,
        "tilt_deg": placement_result.tilt_deg,
        "rotation_deg": placement_result.rotation_deg,
        "azimuth_deg": placement_result.azimuth_deg,
        "anchor_mode": placement_result.anchor_mode,
        "collision_count": placement_result.collision_count,
        "minimum_distance_to_membrane": placement_result.minimum_distance_to_membrane,
        "warnings": placement_result.warnings,
    }
    geo_path = out_dir / "geometry_report.json"
    geo_path.write_text(json.dumps(geometry_report, indent=2), encoding="utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path_out = out_dir / "build_report.json"
    report_path_out.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    # Build system.pdb: membrane preview + transformed peptide coordinates.
    membrane_pdb = build_dir / "preview_allatom.pdb"
    if membrane_pdb.exists() and placement_result.transformed_coords is not None:
        coords = placement_result.transformed_coords
        pep_atom_lines = [
            ln for ln in Path(pp.input_structure).read_text(encoding="utf-8").splitlines()
            if ln.startswith(("ATOM", "HETATM"))
        ]
        # Assign a chain letter not already used in the membrane.
        existing_placements = len(report.peptide_placements)
        chain_letters = "PQRSTUVWXYZ"
        pep_chain = chain_letters[(existing_placements - 1) % len(chain_letters)]

        membrane_lines = [
            ln for ln in membrane_pdb.read_text(encoding="utf-8").splitlines()
            if ln.startswith(("REMARK", "CRYST1", "ATOM", "HETATM"))
        ]
        pep_out_lines: list[str] = []
        for i, ln in enumerate(pep_atom_lines):
            if i >= len(coords):
                break
            x, y, z = coords[i]
            rebuilt = (
                ln[:21]
                + pep_chain
                + ln[22:30]
                + f"{x:8.3f}{y:8.3f}{z:8.3f}"
                + (ln[54:] if len(ln) > 54 else "")
            )
            pep_out_lines.append(rebuilt)

        serial = 1
        system_lines: list[str] = []
        for ln in membrane_lines:
            if ln.startswith(("ATOM", "HETATM")):
                system_lines.append(f"{ln[:6]}{serial:5d}{ln[11:]}")
                serial += 1
            else:
                system_lines.append(ln)
        for ln in pep_out_lines:
            system_lines.append(f"{ln[:6]}{serial:5d}{ln[11:]}")
            serial += 1
        system_lines.append("END")

        system_path = out_dir / "system.pdb"
        system_path.write_text("\n".join(system_lines) + "\n", encoding="utf-8")
        console.print(f"[green]System PDB: {system_path} ({serial - 1} atoms)[/green]")

    for w in placement_result.warnings:
        console.print(f"[yellow]Warning: {w}[/yellow]")
    console.print(f"[green]Peptide '{pp.peptide_id}' placed in {out_dir}[/green]")


def _load_layouts_from_csvs(
    upper_csv: Path,
    lower_csv: Path,
) -> dict[str, LeafletLayout]:
    import csv
    import math

    def read_csv(p: Path):
        positions = []
        if not p.exists():
            return []
        with p.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                from bilbo.builders.leaflet_layout import LipidPosition
                positions.append(
                    LipidPosition(
                        x=float(row["x"]),
                        y=float(row["y"]),
                        leaflet=row["leaflet"],
                        lipid_id=row["lipid_id"],
                    )
                )
        return positions

    layouts = {}
    for name, csv_path in (("upper", upper_csv), ("lower", lower_csv)):
        positions = read_csv(csv_path)
        if positions:
            n = len(positions)
            nx = math.ceil(math.sqrt(n))
            ny = math.ceil(n / nx)
            layouts[name] = LeafletLayout(positions=positions, grid_nx=nx, grid_ny=ny, spacing=0.7)

    return layouts


# ---------------------------------------------------------------------------
# View commands
# ---------------------------------------------------------------------------

@view_app.command("leaflet-map")
def view_leaflet_map(build_dir: Path = typer.Argument(...)):
    """Render leaflet grid in terminal."""
    render_leaflet_map(build_dir, console)


@view_app.command("composition")
def view_composition(build_dir: Path = typer.Argument(...)):
    """Render build composition in terminal."""
    render_composition(build_dir, console)


# ---------------------------------------------------------------------------
# Export commands
# ---------------------------------------------------------------------------

def _require_build(build_dir: Path) -> tuple[dict[str, LeafletLayout], BuildReport]:
    report_path = build_dir / "build_report.json"
    if not report_path.exists():
        console.print(f"[red]build_report.json not found in {build_dir}.[/red]")
        raise typer.Exit(1)
    report = BuildReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    layouts = _load_layouts_from_csvs(
        build_dir / "upper_leaflet.csv",
        build_dir / "lower_leaflet.csv",
    )
    return layouts, report


@export_app.command("vmd-script")
def export_vmd(build_dir: Path = typer.Argument(...)):
    """Export VMD visualization script."""
    layouts, report = _require_build(build_dir)
    has_peptide = (build_dir / "complex_preview.pdb").exists()
    pdb_file = "complex_preview.pdb" if has_peptide else "preview.pdb"
    out = build_dir / "view_vmd.tcl"
    write_vmd_script(out, pdb_filename=pdb_file, has_peptide=has_peptide)
    console.print(f"[green]Written: {out}[/green]")


@export_app.command("pymol-script")
def export_pymol(build_dir: Path = typer.Argument(...)):
    """Export PyMOL visualization script."""
    layouts, report = _require_build(build_dir)
    has_peptide = (build_dir / "complex_preview.pdb").exists()
    pdb_file = "complex_preview.pdb" if has_peptide else "preview.pdb"
    lipid_ids = report.desired_composition.get("upper", {}).keys()
    out = build_dir / "view_pymol.pml"
    write_pymol_script(out, pdb_filename=pdb_file, lipid_ids=list(lipid_ids), has_peptide=has_peptide)
    console.print(f"[green]Written: {out}[/green]")


@export_app.command("complex-preview")
def export_complex(build_dir: Path = typer.Argument(...)):
    """Export complex membrane+peptide preview files."""
    layouts, report = _require_build(build_dir)
    geo_path = build_dir / "geometry_report.json"
    if not geo_path.exists():
        console.print("[red]No geometry_report.json found. Run 'bilbo membrane place' first.[/red]")
        raise typer.Exit(1)
    console.print("[green]Complex preview files already written by membrane place.[/green]")


@export_app.command("allatom-preview")
def export_allatom(
    build_dir: Path = typer.Argument(...),
    templates_dir: Path = typer.Option(
        None,
        "--templates-dir", "-t",
        help="Directory of CHARMM-GUI PDB templates (one per lipid, named by residue).",
    ),
) -> None:
    """Export all-atom PDB preview using CHARMM-GUI structural templates."""
    _DATA = Path(__file__).parent.parent.parent / "data" / "examples"
    if templates_dir is None:
        templates_dir = _DATA / "charmm_gui"
    real_pdbs = [p for p in templates_dir.glob("*.pdb") if not p.name.startswith("._")]
    if not templates_dir.exists() or not real_pdbs:
        console.print(f"[red]No PDB templates found in {templates_dir}[/red]")
        console.print("Download lipid PDB files from CHARMM-GUI and place them there.")
        raise typer.Exit(1)
    layouts, report = _require_build(build_dir)
    out = build_dir / "preview_allatom.pdb"
    n, clash_warns = write_allatom_preview(layouts, templates_dir, out, seed=report.seed)
    console.print(f"[green]Written: {out} ({n} atoms)[/green]")
    for w in clash_warns:
        console.print(f"[yellow]  {w}[/yellow]")


@export_app.command("manifest")
def export_manifest(build_dir: Path = typer.Argument(...)):
    """Write build manifest."""
    _, report = _require_build(build_dir)
    out = write_manifest(build_dir, report.generated_files)
    console.print(f"[green]Written: {out}[/green]")


@export_app.command("report")
def export_report(
    build_dir: Path = typer.Argument(...),
    format: str = typer.Option("json", "--format"),
):
    """Export build report as JSON or Markdown."""
    _, report = _require_build(build_dir)
    if format == "json":
        out = build_dir / "build_report.json"
        out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]Written: {out}[/green]")
    elif format == "markdown":
        out = build_dir / "report.md"
        write_markdown_report(report, out)
        console.print(f"[green]Written: {out}[/green]")
    else:
        console.print(f"[red]Unknown format '{format}'. Use 'json' or 'markdown'.[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
