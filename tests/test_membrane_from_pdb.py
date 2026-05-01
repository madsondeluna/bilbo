"""Tests for bilbo membrane build command (build from PDB files)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bilbo.cli import app

runner = CliRunner()


def _make_pdb(path: Path, n_atoms: int = 20, z_min: float = 0.0, z_max: float = 30.0) -> Path:
    """Write a minimal PDB with n_atoms spanning z_min..z_max."""
    lines = []
    for i in range(n_atoms):
        z = z_min + (z_max - z_min) * i / max(n_atoms - 1, 1)
        line = (
            f"ATOM  {i+1:5d}  C   LIP A   1    "
            f"   1.000   1.000{z:8.3f}  1.00  0.00           C  "
        )
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_from_pdb_symmetric_build(tmp_path):
    pdb = _make_pdb(tmp_path / "POPE.pdb")
    out = tmp_path / "build"
    result = runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", f"{pdb}:32",
        "--output", str(out),
    ], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert (out / "preview_allatom.pdb").exists()
    assert (out / "upper_leaflet.csv").exists()
    assert (out / "lower_leaflet.csv").exists()
    assert (out / "manifest.json").exists()
    assert (out / "build_report.json").exists()


def test_from_pdb_asymmetric_build(tmp_path):
    pope = _make_pdb(tmp_path / "POPE.pdb")
    popg = _make_pdb(tmp_path / "POPG.pdb")
    out = tmp_path / "build"
    result = runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", f"{pope}:50",
        "--upper-pdb", f"{popg}:14",
        "--lower-pdb", f"{pope}:64",
        "--output", str(out),
    ], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert (out / "preview_allatom.pdb").exists()


def test_from_pdb_build_report_contents(tmp_path):
    pdb = _make_pdb(tmp_path / "MYPOP.pdb")
    out = tmp_path / "build"
    runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", f"{pdb}:20",
        "--seed", "7",
        "--output", str(out),
    ], catch_exceptions=False)
    report = json.loads((out / "build_report.json").read_text())
    assert report["preset_id"] == "_from_pdb_"
    assert report["seed"] == 7
    assert "MYPOP" in report["realized_composition"]["upper"]
    assert report["realized_composition"]["upper"]["MYPOP"] == 20
    assert report["realized_composition"]["lower"]["MYPOP"] == 20
    assert "MYPOP.pdb" in report["template_hashes"]


def test_from_pdb_allatom_preview_has_atoms(tmp_path):
    pdb = _make_pdb(tmp_path / "POPE.pdb", n_atoms=15)
    out = tmp_path / "build"
    runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", f"{pdb}:8",
        "--output", str(out),
    ], catch_exceptions=False)
    preview = (out / "preview_allatom.pdb").read_text(encoding="utf-8")
    atom_lines = [ln for ln in preview.splitlines() if ln.startswith(("ATOM", "HETATM"))]
    assert len(atom_lines) > 0


def test_from_pdb_custom_spacing(tmp_path):
    pdb = _make_pdb(tmp_path / "POPE.pdb")
    out = tmp_path / "build"
    result = runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", f"{pdb}:16",
        "--spacing", "1.0",
        "--output", str(out),
    ], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    csv = (out / "upper_leaflet.csv").read_text()
    rows = [line.split(",") for line in csv.strip().splitlines()[1:]]
    x_vals = [float(r[0]) for r in rows]
    assert any(x > 0.9 for x in x_vals)


def test_from_pdb_custom_bilayer_gap(tmp_path):
    pdb = _make_pdb(tmp_path / "POPE.pdb", z_min=0.0, z_max=20.0)
    out = tmp_path / "build"
    result = runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", f"{pdb}:4",
        "--bilayer-gap", "10.0",
        "--output", str(out),
    ], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    preview = (out / "preview_allatom.pdb").read_text(encoding="utf-8")
    atom_lines = [ln for ln in preview.splitlines() if ln.startswith("ATOM")]
    z_vals = [float(ln[46:54]) for ln in atom_lines]
    upper_z = [z for z in z_vals if z > 0]
    lower_z = [z for z in z_vals if z < 0]
    assert upper_z and lower_z
    assert min(upper_z) >= 5.0 - 0.01


def test_from_pdb_missing_file(tmp_path):
    out = tmp_path / "build"
    result = runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", str(tmp_path / "GHOST.pdb") + ":10",
        "--output", str(out),
    ])
    assert result.exit_code != 0


def test_from_pdb_too_few_atoms(tmp_path):
    pdb = _make_pdb(tmp_path / "TINY.pdb", n_atoms=5)
    out = tmp_path / "build"
    result = runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", f"{pdb}:10",
        "--output", str(out),
    ])
    assert result.exit_code != 0


def test_from_pdb_bad_z_extent_too_small(tmp_path):
    pdb = _make_pdb(tmp_path / "FLAT.pdb", n_atoms=20, z_min=0.0, z_max=2.0)
    out = tmp_path / "build"
    result = runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", f"{pdb}:10",
        "--output", str(out),
    ])
    assert result.exit_code != 0


def test_from_pdb_bad_z_extent_too_large(tmp_path):
    pdb = _make_pdb(tmp_path / "HUGE.pdb", n_atoms=20, z_min=0.0, z_max=100.0)
    out = tmp_path / "build"
    result = runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", f"{pdb}:10",
        "--output", str(out),
    ])
    assert result.exit_code != 0


def test_from_pdb_invalid_count_format(tmp_path):
    pdb = _make_pdb(tmp_path / "POPE.pdb")
    out = tmp_path / "build"
    result = runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", f"{pdb}:notanumber",
        "--output", str(out),
    ])
    assert result.exit_code != 0


def test_from_pdb_missing_colon_separator(tmp_path):
    pdb = _make_pdb(tmp_path / "POPE.pdb")
    out = tmp_path / "build"
    result = runner.invoke(app, [
        "membrane", "build",
        "--upper-pdb", str(pdb),
        "--output", str(out),
    ])
    assert result.exit_code != 0
