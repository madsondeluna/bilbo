"""Shared pytest fixtures."""

import pytest
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "examples"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def lipid_yaml_dir() -> Path:
    return DATA_DIR / "lipids"


@pytest.fixture
def preset_yaml_dir() -> Path:
    return DATA_DIR / "presets"


@pytest.fixture
def forcefield_csv() -> Path:
    return DATA_DIR / "forcefields" / "charmm36_mapping.csv"


@pytest.fixture
def topology_dir() -> Path:
    return DATA_DIR / "topologies"


@pytest.fixture
def charmm_gui_html() -> Path:
    return FIXTURES_DIR / "charmm_gui_lipid_archive_fixture.html"


@pytest.fixture
def amp01_pdb() -> Path:
    return DATA_DIR / "peptides" / "AMP01.pdb"


@pytest.fixture
def ecoli_preset_yaml() -> Path:
    return DATA_DIR / "presets" / "ecoli_inner_membrane_default.yaml"


@pytest.fixture
def popc_yaml() -> Path:
    return DATA_DIR / "lipids" / "POPC.yaml"
