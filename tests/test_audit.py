"""Tests for the audit extractor."""

import pytest
from bilbo.extractors.audit import AuditExtractor
from bilbo.models.lipid import Lipid
from bilbo.models.preset import MembranePreset
from bilbo.models.forcefield import ForceFieldMapping
from bilbo.models.reference import Reference


def _validated_lipid(lipid_id: str) -> Lipid:
    return Lipid(
        id=lipid_id,
        lipid_class="glycerophospholipid",
        net_charge=0,
        force_fields={
            "charmm36": ForceFieldMapping(
                lipid_id=lipid_id,
                force_field="charmm36",
                residue_name=lipid_id,
                status="validated",
            )
        },
        references=[Reference(id=f"ref_{lipid_id}", manual_citation="Test")],
        curation_status="validated",
    )


def test_audit_clean_library():
    lipids = [_validated_lipid("POPC"), _validated_lipid("POPE")]
    preset = MembranePreset(
        id="test",
        leaflets={"upper": {"POPC": 50, "POPE": 50}, "lower": {"POPC": 50, "POPE": 50}},
        references=[Reference(id="r1", manual_citation="Test")],
    )
    result = AuditExtractor().audit_library(lipids, [preset])
    assert result.ok()


def test_audit_flags_missing_lipid():
    lipids = [_validated_lipid("POPC")]
    preset = MembranePreset(
        id="test",
        leaflets={"upper": {"POPC": 50, "MISSING": 50}, "lower": {"POPC": 100}},
        references=[Reference(id="r1", manual_citation="Test")],
    )
    result = AuditExtractor().audit_library(lipids, [preset])
    assert not result.ok()
    assert any("MISSING" in e for e in result.errors)


def test_audit_warns_lipid_no_references():
    lip = Lipid(
        id="NOREF",
        lipid_class="glycerophospholipid",
        net_charge=0,
        force_fields={
            "charmm36": ForceFieldMapping(
                lipid_id="NOREF", force_field="charmm36", residue_name="NOREF", status="validated"
            )
        },
        curation_status="validated",
    )
    result = AuditExtractor().audit_library([lip], [])
    assert any("NOREF" in w for w in result.warnings)


def test_audit_blocks_pending_review_in_preset():
    lip = Lipid(id="PEND", lipid_class="glycerophospholipid", curation_status="pending_review")
    preset = MembranePreset(
        id="test",
        leaflets={"upper": {"PEND": 100}, "lower": {"PEND": 100}},
        references=[Reference(id="r1", manual_citation="Test")],
    )
    result = AuditExtractor().audit_library([lip], [preset])
    assert not result.ok()
