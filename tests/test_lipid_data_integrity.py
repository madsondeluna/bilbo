"""Validate consistency between CHARMM-GUI PDB templates and CHARMM36 ITP files.

Each lipid shipped with BILBO must satisfy:
  1. Atom count: PDB first-residue atom count == ITP [ atoms ] section count.
  2. Atom name order: atom names in PDB match ITP in the same sequential position.
  3. Residue name: PDB residue name matches the residue name used in the ITP [ atoms ] section.

These properties are necessary for GROMACS grompp to match coordinates to
topology without atom-count errors and without silently assigning wrong
force-field parameters.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CHARMM_GUI_DIR = Path(__file__).parent.parent / "data" / "examples" / "charmm_gui"
ITP_DIR = Path(__file__).parent.parent / "data" / "ff" / "charmm36_lipids"

# PDB stem → ITP stem when the file names differ.
# CHOL.pdb should be processed via CHL1.itp (CHARMM-GUI uses CHL1 as residue
# name in the ITP, while the example PDB still carries the old CHOL name).
_ITP_FOR_PDB: dict[str, str] = {
    "CHOL": "CHL1",
}

# Known residue name mismatches that cannot be fixed in the PDB file.
# Key: PDB stem. Value: (pdb_resname, itp_resname, reason).
# These are excluded from test_residue_name_pdb_matches_itp.
_RESNAME_EXCEPTIONS: dict[str, tuple[str, str, str]] = {
    "CL": (
        "CL",
        "TLCL1",
        "TLCL1 is 5 characters and does not fit in the 4-char PDB residue field. "
        "The PDB uses 'CL' (the moleculetype name) instead. GROMACS grompp issues a "
        "warning but not a fatal error; atom names and order are still correct.",
    ),
}

# ── helpers ───────────────────────────────────────────────────────────────────

def _pdb_first_residue_atoms(pdb_path: Path) -> list[str]:
    """Return ATOM/HETATM lines for the first residue only (mirrors _load_template)."""
    lines = [
        ln for ln in pdb_path.read_text(encoding="utf-8").splitlines()
        if ln.startswith(("ATOM", "HETATM"))
    ]
    if not lines:
        return lines
    first_seq = lines[0][22:26].strip()
    return [ln for ln in lines if ln[22:26].strip() == first_seq]


def _pdb_atom_names(atom_lines: list[str]) -> list[str]:
    return [ln[12:16].strip() for ln in atom_lines]


def _pdb_resname(atom_lines: list[str]) -> str:
    """Residue name from the first ATOM line (columns 17-20, strip)."""
    return atom_lines[0][17:21].strip()


def _itp_atoms(itp_path: Path) -> list[tuple[str, str]]:
    """Return list of (atom_name, residue_name) from the first [ atoms ] section."""
    text = itp_path.read_text(encoding="utf-8")
    # find the first [ atoms ] block
    m = re.search(r'\[\s*atoms\s*\](.*?)(?=\[|\Z)', text, re.DOTALL)
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split()
        # columns: nr type resnr residue atom cgnr charge mass ...
        if len(parts) < 5:
            continue
        residue_name = parts[3]
        atom_name = parts[4]
        rows.append((atom_name, residue_name))
    return rows


# ── parametrize all PDB templates ────────────────────────────────────────────

def _all_pdb_stems() -> list[str]:
    return sorted(
        p.stem for p in CHARMM_GUI_DIR.glob("*.pdb")
        if not p.name.startswith(".")
    )


@pytest.mark.parametrize("stem", _all_pdb_stems())
def test_itp_exists_for_pdb(stem: str):
    itp_stem = _ITP_FOR_PDB.get(stem, stem)
    itp_path = ITP_DIR / f"{itp_stem}.itp"
    assert itp_path.exists(), (
        f"No ITP found for PDB template {stem}.pdb. "
        f"Expected {itp_path}. "
        "Either add the ITP or register an alias in _ITP_FOR_PDB."
    )


@pytest.mark.parametrize("stem", _all_pdb_stems())
def test_atom_count_pdb_matches_itp(stem: str):
    itp_stem = _ITP_FOR_PDB.get(stem, stem)
    itp_path = ITP_DIR / f"{itp_stem}.itp"
    if not itp_path.exists():
        pytest.skip(f"ITP missing for {stem} (covered by test_itp_exists_for_pdb)")

    pdb_lines = _pdb_first_residue_atoms(CHARMM_GUI_DIR / f"{stem}.pdb")
    itp_rows = _itp_atoms(itp_path)

    assert len(pdb_lines) == len(itp_rows), (
        f"{stem}: PDB has {len(pdb_lines)} atoms, ITP has {len(itp_rows)} atoms. "
        "GROMACS grompp will fail with 'number of coordinates does not match topology'."
    )


@pytest.mark.parametrize("stem", _all_pdb_stems())
def test_atom_name_order_pdb_matches_itp(stem: str):
    """Atom names at each sequential position must match between PDB and ITP.

    A mismatch means the CHARMM36 force-field parameters (charges, LJ) would be
    assigned to the wrong atom, corrupting the physics silently.
    """
    itp_stem = _ITP_FOR_PDB.get(stem, stem)
    itp_path = ITP_DIR / f"{itp_stem}.itp"
    if not itp_path.exists():
        pytest.skip(f"ITP missing for {stem}")

    pdb_lines = _pdb_first_residue_atoms(CHARMM_GUI_DIR / f"{stem}.pdb")
    pdb_names = _pdb_atom_names(pdb_lines)
    itp_rows = _itp_atoms(itp_path)
    itp_names = [r[0] for r in itp_rows]

    if len(pdb_names) != len(itp_names):
        pytest.skip(f"Atom count mismatch for {stem} (covered by test_atom_count_pdb_matches_itp)")

    mismatches = [
        (i, pdb_names[i], itp_names[i])
        for i in range(len(pdb_names))
        if pdb_names[i] != itp_names[i]
    ]
    assert not mismatches, (
        f"{stem}: atom name mismatches at positions (0-indexed): "
        + "; ".join(f"[{i}] PDB={p!r} ITP={t!r}" for i, p, t in mismatches)
    )


@pytest.mark.parametrize("stem", _all_pdb_stems())
def test_residue_name_pdb_matches_itp(stem: str):
    """Residue name in PDB template must match the residue name in the ITP [ atoms ] section.

    A mismatch causes grompp to print warnings and may result in incorrect
    residue labeling in trajectory files, complicating analysis.
    """
    if stem in _RESNAME_EXCEPTIONS:
        _, _, reason = _RESNAME_EXCEPTIONS[stem]
        pytest.skip(f"Known exception: {reason}")

    itp_stem = _ITP_FOR_PDB.get(stem, stem)
    itp_path = ITP_DIR / f"{itp_stem}.itp"
    if not itp_path.exists():
        pytest.skip(f"ITP missing for {stem}")

    pdb_lines = _pdb_first_residue_atoms(CHARMM_GUI_DIR / f"{stem}.pdb")
    if not pdb_lines:
        pytest.skip(f"No ATOM lines in {stem}.pdb")

    itp_rows = _itp_atoms(itp_path)
    if not itp_rows:
        pytest.skip(f"No atoms parsed from {itp_stem}.itp")

    pdb_resname = _pdb_resname(pdb_lines)
    itp_resname = itp_rows[0][1]

    assert pdb_resname == itp_resname, (
        f"{stem}: PDB residue name {pdb_resname!r} != ITP residue name {itp_resname!r}. "
        "Fix the PDB template or the ITP to use a consistent name."
    )


# ── water model and ion ITP checks ───────────────────────────────────────────

FF_BASE_DIR = Path(__file__).parent.parent / "data" / "ff" / "charmm36_base"

_REQUIRED_WATER_ITPS = ["tip3p.itp", "spc.itp", "spce.itp"]
_REQUIRED_ION_ITPS = ["ions.itp"]


@pytest.mark.parametrize("itp_name", _REQUIRED_WATER_ITPS)
def test_water_itp_exists(itp_name: str):
    path = FF_BASE_DIR / itp_name
    assert path.exists(), (
        f"{itp_name} missing from {FF_BASE_DIR}. "
        "Without it, solvated systems will fail grompp with 'No such moleculetype SOL/WAT'."
    )


@pytest.mark.parametrize("itp_name", _REQUIRED_ION_ITPS)
def test_ion_itp_exists(itp_name: str):
    path = FF_BASE_DIR / itp_name
    assert path.exists(), (
        f"{itp_name} missing from {FF_BASE_DIR}. "
        "Without it, ionized systems will fail grompp with 'No such moleculetype NA/CL'."
    )


@pytest.mark.parametrize("itp_name", _REQUIRED_WATER_ITPS)
def test_water_itp_has_sol_moleculetype(itp_name: str):
    """Each water ITP must define the SOL moleculetype used by gmx solvate."""
    path = FF_BASE_DIR / itp_name
    if not path.exists():
        pytest.skip(f"{itp_name} missing")
    text = path.read_text(encoding="utf-8")
    # the moleculetype line must contain SOL (or WAT for some models)
    assert re.search(r'^\s*SOL\b', text, re.MULTILINE), (
        f"{itp_name}: no 'SOL' moleculetype found. "
        "gmx solvate writes 'SOL' residues; the ITP must declare 'SOL' as the moleculetype."
    )


def test_ions_itp_has_na_and_cl():
    path = FF_BASE_DIR / "ions.itp"
    if not path.exists():
        pytest.skip("ions.itp missing")
    text = path.read_text(encoding="utf-8")
    assert re.search(r'^\s*NA\b', text, re.MULTILINE), "ions.itp: no NA moleculetype"
    assert re.search(r'^\s*CL\b', text, re.MULTILINE), "ions.itp: no CL moleculetype"


# ── topology topology-include checks ─────────────────────────────────────────

def test_topology_includes_water_and_ions(tmp_path):
    """write_gromacs_topology must include water and ion ITPs so that solvation
    and genion steps succeed without manual topology editing."""
    from bilbo.builders.composition_expander import expand_composition
    from bilbo.builders.leaflet_layout import build_leaflet_layout
    from bilbo.exporters.gromacs_topology import write_gromacs_topology
    from bilbo.models.preset import MembranePreset
    from bilbo.models.reference import Reference

    preset = MembranePreset(
        id="test",
        leaflets={"upper": {"POPC": 100}, "lower": {"POPC": 100}},
        references=[Reference(id="r1", manual_citation="test")],
    )
    layouts = build_leaflet_layout(expand_composition(preset, 4), "random", 42)
    out = tmp_path / "topol.top"
    write_gromacs_topology(layouts, out)
    text = out.read_text()
    assert 'tip3p.itp' in text, "topol.top must #include tip3p.itp"
    assert 'ions.itp' in text, "topol.top must #include ions.itp"


# ── APL_REFERENCE completeness ────────────────────────────────────────────────

def test_apl_reference_covers_all_shipped_lipids():
    """Every lipid in charmm_gui/ must have an entry in APL_REFERENCE so that
    weighted_spacing can compute a valid grid spacing (instead of falling back
    to 0.7 nm, which causes severe lipid overlaps and Fmax=inf in EM)."""
    from bilbo.builders.apl_check import APL_REFERENCE

    missing = []
    for pdb_path in sorted(CHARMM_GUI_DIR.glob("*.pdb")):
        if pdb_path.name.startswith("."):
            continue
        stem = pdb_path.stem.upper()
        if stem not in APL_REFERENCE:
            missing.append(stem)

    assert not missing, (
        f"Lipids missing from APL_REFERENCE: {missing}. "
        "Add them to src/bilbo/builders/apl_check.py with a literature or CHARMM36 estimate."
    )


# ── MDP template checks ───────────────────────────────────────────────────────

MDP_TMPL_DIR = Path(__file__).parent.parent / "src" / "bilbo" / "exporters" / "mdp_templates"

_CALC_ENERGY_STEP = 100


@pytest.mark.parametrize("mdp_name", ["nvt.mdp", "npt.mdp", "prod.mdp"])
def test_mdp_nstcalcenergy_set(mdp_name: str):
    """nstcalcenergy must be set so nstenergy is always a multiple of it.

    Without an explicit nstcalcenergy, GROMACS defaults to 100. If nstenergy
    is not a multiple (e.g., nstenergy=50, nstcalcenergy=100), grompp raises a
    fatal error. Setting nstcalcenergy=100 in the template removes the need for
    -maxwarn on every grompp invocation.
    """
    path = MDP_TMPL_DIR / mdp_name
    if not path.exists():
        pytest.skip(f"{mdp_name} not found")
    text = path.read_text(encoding="utf-8")
    assert re.search(r'nstcalcenergy\s*=', text), (
        f"{mdp_name}: nstcalcenergy not set. "
        f"Add 'nstcalcenergy = {_CALC_ENERGY_STEP}' to ensure nstenergy is always a valid multiple."
    )
