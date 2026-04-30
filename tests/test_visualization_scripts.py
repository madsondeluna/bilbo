"""Tests for VMD and PyMOL script exporters."""

import pytest
from pathlib import Path

from bilbo.exporters.vmd_script import write_vmd_script
from bilbo.exporters.pymol_script import write_pymol_script


def test_vmd_script_references_preview_pdb(tmp_path):
    out = tmp_path / "view_vmd.tcl"
    write_vmd_script(out)
    content = out.read_text()
    assert "preview.pdb" in content


def test_pymol_script_references_preview_pdb(tmp_path):
    out = tmp_path / "view_pymol.pml"
    write_pymol_script(out)
    content = out.read_text()
    assert "preview.pdb" in content


def test_vmd_script_has_upper_lower_selections(tmp_path):
    out = tmp_path / "view_vmd.tcl"
    write_vmd_script(out)
    content = out.read_text()
    assert "chain U" in content
    assert "chain L" in content


def test_pymol_script_has_upper_lower_selections(tmp_path):
    out = tmp_path / "view_pymol.pml"
    write_pymol_script(out)
    content = out.read_text()
    assert "upper_leaflet" in content
    assert "lower_leaflet" in content
