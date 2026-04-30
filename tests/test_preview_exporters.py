"""Tests for all-atom preview and GROMACS topology exporters."""

import pytest
from pathlib import Path

from bilbo.builders.composition_expander import expand_composition
from bilbo.builders.leaflet_layout import build_leaflet_layout
from bilbo.exporters.allatom_preview import write_allatom_preview
from bilbo.exporters.gromacs_topology import write_gromacs_topology
from bilbo.models.preset import MembranePreset
from bilbo.models.reference import Reference


def _simple_preset():
    return MembranePreset(
        id="test",
        leaflets={
            "upper": {"POPE": 70, "POPG": 20, "CL": 10},
            "lower": {"POPE": 70, "POPG": 20, "CL": 10},
        },
        references=[Reference(id="r1", manual_citation="test")],
    )


def _build_layouts(n=10, sorting="domain_enriched"):
    preset = _simple_preset()
    expanded = expand_composition(preset, n)
    return build_leaflet_layout(expanded, sorting, 42)


def _make_pdb_template(path: Path, resname: str, n_atoms: int = 5) -> None:
    """Write a minimal single-residue PDB template for testing."""
    lines = []
    z_head = 20.0
    for i in range(n_atoms):
        z = z_head - i * 4.0
        lines.append(f"ATOM  {i+1:5d}  CA  {resname:<4s}A   1    "
                     f"   0.000   0.000{z:8.3f}  1.00  0.00")
    lines.append("END")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestAllAtomPreview:
    def test_writes_atom_records(self, tmp_path):
        layouts = _build_layouts(10)
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()
        for name in ("POPE", "POPG", "CL"):
            _make_pdb_template(tmpl_dir / f"{name}.pdb", name)
        out = tmp_path / "preview.pdb"
        n = write_allatom_preview(layouts, tmpl_dir, out)
        assert n > 0
        atom_lines = [l for l in out.read_text().splitlines() if l.startswith("ATOM")]
        assert len(atom_lines) == n

    def test_cryst1_record_present(self, tmp_path):
        layouts = _build_layouts(10)
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()
        for name in ("POPE", "POPG", "CL"):
            _make_pdb_template(tmpl_dir / f"{name}.pdb", name)
        out = tmp_path / "preview.pdb"
        write_allatom_preview(layouts, tmpl_dir, out)
        content = out.read_text()
        assert content.startswith("REMARK")
        assert "CRYST1" in content

    def test_upper_and_lower_chains(self, tmp_path):
        layouts = _build_layouts(10)
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()
        for name in ("POPE", "POPG", "CL"):
            _make_pdb_template(tmpl_dir / f"{name}.pdb", name)
        out = tmp_path / "preview.pdb"
        write_allatom_preview(layouts, tmpl_dir, out)
        content = out.read_text()
        chains = {line[21] for line in content.splitlines() if line.startswith("ATOM")}
        assert "U" in chains
        assert "L" in chains

    def test_missing_template_skipped(self, tmp_path):
        layouts = _build_layouts(10)
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()
        _make_pdb_template(tmpl_dir / "POPE.pdb", "POPE")
        out = tmp_path / "preview.pdb"
        n = write_allatom_preview(layouts, tmpl_dir, out)
        content = out.read_text()
        assert "Missing templates" in content
        assert n > 0

    def test_no_inter_leaflet_overlap(self, tmp_path):
        """Upper leaflet atoms must have z > 0, lower leaflet atoms z < 0."""
        layouts = _build_layouts(10)
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()
        for name in ("POPE", "POPG", "CL"):
            _make_pdb_template(tmpl_dir / f"{name}.pdb", name, n_atoms=10)
        out = tmp_path / "preview.pdb"
        write_allatom_preview(layouts, tmpl_dir, out)
        upper_z = []
        lower_z = []
        for line in out.read_text().splitlines():
            if not line.startswith("ATOM"):
                continue
            chain = line[21]
            z = float(line[46:54])
            if chain == "U":
                upper_z.append(z)
            elif chain == "L":
                lower_z.append(z)
        assert all(z > 0 for z in upper_z), "Upper leaflet has atoms at z <= 0"
        assert all(z < 0 for z in lower_z), "Lower leaflet has atoms at z >= 0"


class TestGromacsTopology:
    def test_writes_includes_and_molecules(self, tmp_path):
        layouts = _build_layouts(10, sorting="domain_enriched")
        out = tmp_path / "topol.top"
        lipids = write_gromacs_topology(layouts, out)
        content = out.read_text()
        assert '#include "charmm36.ff/forcefield.itp"' in content
        assert "[ system ]" in content
        assert "[ molecules ]" in content
        for lip in lipids:
            assert f'#include "charmm36.ff/{lip}.itp"' in content

    def test_molecules_sum_matches_layout(self, tmp_path):
        n_per_leaflet = 10
        layouts = _build_layouts(n_per_leaflet, sorting="domain_enriched")
        out = tmp_path / "topol.top"
        write_gromacs_topology(layouts, out)
        total_from_top = 0
        in_molecules = False
        for line in out.read_text().splitlines():
            if line.strip() == "[ molecules ]":
                in_molecules = True
                continue
            if in_molecules and line.startswith(";"):
                continue
            if in_molecules and line.strip():
                parts = line.split()
                if len(parts) == 2:
                    total_from_top += int(parts[1])
        total_from_layouts = sum(len(l.positions) for l in layouts.values())
        assert total_from_top == total_from_layouts

    def test_custom_ff_dir(self, tmp_path):
        layouts = _build_layouts(10)
        out = tmp_path / "topol.top"
        write_gromacs_topology(layouts, out, ff_dir="charmm36-jul2022.ff")
        content = out.read_text()
        assert '#include "charmm36-jul2022.ff/forcefield.itp"' in content

    def test_rle_order_matches_positions(self, tmp_path):
        """With random sorting, topology must still list molecules in layout order."""
        layouts = _build_layouts(20, sorting="random")
        out = tmp_path / "topol.top"
        write_gromacs_topology(layouts, out)
        in_upper = False
        top_order: list[str] = []
        for line in out.read_text().splitlines():
            if "; upper leaflet" in line:
                in_upper = True
                continue
            if "; lower leaflet" in line:
                break
            if in_upper and not line.startswith(";") and line.strip():
                parts = line.split()
                if len(parts) == 2:
                    top_order.extend([parts[0]] * int(parts[1]))
        layout_order = [p.lipid_id for p in layouts["upper"].positions]
        assert top_order == layout_order
