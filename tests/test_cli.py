"""CLI smoke tests using Typer test runner."""

import json
import pytest
from pathlib import Path
from typer.testing import CliRunner

from bilbo.cli import app
from bilbo.db.repository import reset_engine

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "bilbo_test.db"
    import bilbo.db.repository as repo_mod
    monkeypatch.setattr(repo_mod, "_engine", None)
    reset_engine(db_path)
    yield
    monkeypatch.setattr(repo_mod, "_engine", None)


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "bilbo" in result.output.lower()


def test_cli_lipid_validate(popc_yaml):
    result = runner.invoke(app, ["lipid", "validate", str(popc_yaml)])
    assert result.exit_code == 0
    assert "Valid" in result.output


def test_cli_preset_validate(ecoli_preset_yaml):
    result = runner.invoke(app, ["preset", "validate", str(ecoli_preset_yaml)])
    assert result.exit_code == 0
    assert "Valid" in result.output


def test_cli_extract_mappings(forcefield_csv, tmp_path):
    result = runner.invoke(app, ["extract", "mappings", str(forcefield_csv)])
    assert result.exit_code == 0
    assert "mapping" in result.output.lower()


def test_cli_extract_topologies(topology_dir):
    result = runner.invoke(app, ["extract", "topologies", str(topology_dir)])
    assert result.exit_code == 0


def test_cli_membrane_build_ecoli(lipid_yaml_dir, preset_yaml_dir, forcefield_csv, tmp_path):
    runner.invoke(app, ["lipid", "add", str(lipid_yaml_dir)])
    runner.invoke(app, ["preset", "add", str(preset_yaml_dir / "ecoli_inner_membrane_default.yaml")])
    runner.invoke(app, ["extract", "mappings", str(forcefield_csv)])

    result = runner.invoke(app, [
        "membrane", "build-preset",
        "--preset", "ecoli_inner_membrane_default",
        "--force-field", "charmm36",
        "--engine", "gromacs",
        "--lipids-per-leaflet", "64",
        "--sorting", "random",
        "--seed", "42",
        "--output", str(tmp_path / "builds/ecoli_test"),
    ])
    assert result.exit_code == 0

    build_dir = tmp_path / "builds/ecoli_test"
    assert (build_dir / "build_report.json").exists()
    assert (build_dir / "topol.top").exists()
    assert (build_dir / "view_vmd.tcl").exists()
    assert (build_dir / "view_pymol.pml").exists()
    assert (build_dir / "upper_leaflet.csv").exists()
    assert (build_dir / "lower_leaflet.csv").exists()
    assert (build_dir / "manifest.json").exists()
    assert (build_dir / "report.md").exists()

    report = json.loads((build_dir / "build_report.json").read_text())
    assert report["realized_composition"]["upper"]["POPE"] == 45
    assert report["realized_composition"]["upper"]["POPG"] == 13
    assert report["realized_composition"]["upper"]["CL"] == 6


def test_cli_peptide_validate(tmp_path):
    yaml_content = """id: TEST01
name: test peptide
sequence: ACGT
curation_status: pending_review
"""
    p = tmp_path / "test_pep.yaml"
    p.write_text(yaml_content, encoding="utf-8")
    result = runner.invoke(app, ["peptide", "validate", str(p)])
    assert result.exit_code == 0


def test_cli_membrane_add_peptide(lipid_yaml_dir, preset_yaml_dir, forcefield_csv, amp01_pdb, tmp_path):
    runner.invoke(app, ["lipid", "add", str(lipid_yaml_dir)])
    runner.invoke(app, ["preset", "add", str(preset_yaml_dir / "ecoli_inner_membrane_default.yaml")])
    runner.invoke(app, ["extract", "mappings", str(forcefield_csv)])
    runner.invoke(app, [
        "membrane", "build-preset",
        "--preset", "ecoli_inner_membrane_default",
        "--force-field", "charmm36",
        "--engine", "gromacs",
        "--lipids-per-leaflet", "16",
        "--sorting", "random",
        "--seed", "42",
        "--output", str(tmp_path / "build"),
    ])

    result = runner.invoke(app, [
        "membrane", "place",
        str(tmp_path / "build"),
        "--peptide", str(amp01_pdb),
        "--leaflet", "upper",
        "--orientation", "parallel",
        "--x", "0",
        "--y", "0",
        "--depth", "1.8",
        "--rotation-deg", "90",
        "--tilt-deg", "0",
    ])
    assert result.exit_code == 0
    assert (tmp_path / "build" / "geometry_report.json").exists()


def test_cli_export_complex_preview(lipid_yaml_dir, preset_yaml_dir, forcefield_csv, amp01_pdb, tmp_path):
    runner.invoke(app, ["lipid", "add", str(lipid_yaml_dir)])
    runner.invoke(app, ["preset", "add", str(preset_yaml_dir / "ecoli_inner_membrane_default.yaml")])
    runner.invoke(app, ["extract", "mappings", str(forcefield_csv)])
    runner.invoke(app, [
        "membrane", "build-preset",
        "--preset", "ecoli_inner_membrane_default",
        "--force-field", "charmm36",
        "--engine", "gromacs",
        "--lipids-per-leaflet", "16",
        "--sorting", "random",
        "--seed", "42",
        "--output", str(tmp_path / "build"),
    ])
    runner.invoke(app, [
        "membrane", "place",
        str(tmp_path / "build"),
        "--peptide", str(amp01_pdb),
        "--leaflet", "upper",
        "--orientation", "parallel",
        "--depth", "1.8",
    ])

    result = runner.invoke(app, ["export", "complex-preview", str(tmp_path / "build")])
    assert result.exit_code == 0


def test_cli_export_vmd_script(lipid_yaml_dir, preset_yaml_dir, forcefield_csv, tmp_path):
    _run_build(lipid_yaml_dir, preset_yaml_dir, forcefield_csv, tmp_path)
    result = runner.invoke(app, ["export", "vmd-script", str(tmp_path / "build")])
    assert result.exit_code == 0


def test_cli_export_pymol_script(lipid_yaml_dir, preset_yaml_dir, forcefield_csv, tmp_path):
    _run_build(lipid_yaml_dir, preset_yaml_dir, forcefield_csv, tmp_path)
    result = runner.invoke(app, ["export", "pymol-script", str(tmp_path / "build")])
    assert result.exit_code == 0


def test_cli_view_leaflet_map(lipid_yaml_dir, preset_yaml_dir, forcefield_csv, tmp_path):
    _run_build(lipid_yaml_dir, preset_yaml_dir, forcefield_csv, tmp_path)
    result = runner.invoke(app, ["view", "leaflet-map", str(tmp_path / "build")])
    assert result.exit_code == 0


def _run_build(lipid_yaml_dir, preset_yaml_dir, forcefield_csv, tmp_path):
    runner.invoke(app, ["lipid", "add", str(lipid_yaml_dir)])
    runner.invoke(app, ["preset", "add", str(preset_yaml_dir / "ecoli_inner_membrane_default.yaml")])
    runner.invoke(app, ["extract", "mappings", str(forcefield_csv)])
    runner.invoke(app, [
        "membrane", "build-preset",
        "--preset", "ecoli_inner_membrane_default",
        "--force-field", "charmm36",
        "--engine", "gromacs",
        "--lipids-per-leaflet", "16",
        "--sorting", "random",
        "--seed", "42",
        "--output", str(tmp_path / "build"),
    ])
