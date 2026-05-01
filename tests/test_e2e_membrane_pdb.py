"""End-to-end test: load lipids + preset, build membrane, verify outputs."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bilbo.cli import app

DATA_DIR = Path(__file__).parent.parent / "data" / "examples"
runner = CliRunner()


@pytest.fixture()
def bilbo_env(tmp_path, monkeypatch):
    db_path = tmp_path / "bilbo.db"
    monkeypatch.setenv("BILBO_DB_PATH", str(db_path))
    from bilbo.db import repository
    repository._engine = None
    yield tmp_path
    repository._engine = None


def _run(args: list[str]) -> None:
    result = runner.invoke(app, args, catch_exceptions=False)
    assert result.exit_code == 0, result.output


def test_membrane_pdb_end_to_end(bilbo_env, tmp_path):
    lipids_dir = DATA_DIR / "lipids"
    preset_file = DATA_DIR / "presets" / "ecoli_inner_membrane_default.yaml"
    output_dir = tmp_path / "build_ecoli"

    _run(["lipid", "add", str(lipids_dir / "POPE.yaml")])
    _run(["lipid", "add", str(lipids_dir / "POPG.yaml")])
    _run(["lipid", "add", str(lipids_dir / "CL.yaml")])

    _run(["preset", "add", str(preset_file)])

    _run([
        "membrane", "build-preset",
        "--preset", "ecoli_inner_membrane_default",
        "--force-field", "charmm36",
        "--engine", "gromacs",
        "--lipids-per-leaflet", "64",
        "--seed", "42",
        "--output", str(output_dir),
    ])

    assert (output_dir / "build_report.json").exists()
    assert (output_dir / "topol.top").exists()
    assert (output_dir / "upper_leaflet.csv").exists()
    assert (output_dir / "lower_leaflet.csv").exists()

    top = (output_dir / "topol.top").read_text(encoding="utf-8")
    assert '#include "charmm36.ff/forcefield.itp"' in top
    assert "[ molecules ]" in top

    # total molecules in topology must equal 2 * lipids_per_leaflet
    total = 0
    in_mol = False
    for line in top.splitlines():
        if line.strip() == "[ molecules ]":
            in_mol = True
            continue
        if in_mol and not line.startswith(";") and line.strip():
            parts = line.split()
            if len(parts) == 2:
                total += int(parts[1])
    assert total == 128, f"expected 128 total molecules, got {total}"
