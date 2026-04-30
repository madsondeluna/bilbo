"""Tests for topology scanner."""

import pytest
from pathlib import Path

from bilbo.extractors.topology_scanner import TopologyScanner


def test_topology_scanner_finds_popc_in_itp(topology_dir):
    scanner = TopologyScanner()
    result = scanner.scan(topology_dir)
    assert "POPC" in result.found_residues


def test_topology_scanner_reports_missing_residue(topology_dir):
    scanner = TopologyScanner()
    result = scanner.scan(topology_dir, residues_to_check=["POPC", "NOTEXIST"])
    assert "POPC" in result.found_residues
    assert "NOTEXIST" in result.missing_residues


def test_topology_scanner_counts_files(topology_dir):
    scanner = TopologyScanner()
    result = scanner.scan(topology_dir)
    assert len(result.topology_files_scanned) >= 1


def test_topology_scanner_promotes_mapping_to_validated_when_residue_found(topology_dir):
    scanner = TopologyScanner()
    result = scanner.scan(topology_dir, residues_to_check=["POPC"])
    assert "POPC" in result.found_residues
    assert "POPC" not in result.missing_residues
