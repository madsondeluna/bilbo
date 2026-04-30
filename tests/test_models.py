"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from bilbo.models.lipid import Lipid
from bilbo.models.forcefield import ForceFieldMapping
from bilbo.models.preset import MembranePreset
from bilbo.models.source import SourceManifest
from bilbo.models.build import BuildReport
from bilbo.models.reference import Reference


def _make_valid_lipid(**kwargs):
    defaults = dict(
        id="POPC",
        name="POPC full name",
        lipid_class="glycerophospholipid",
        net_charge=0,
        force_fields={
            "charmm36": ForceFieldMapping(
                lipid_id="POPC",
                force_field="charmm36",
                residue_name="POPC",
                status="validated",
            )
        },
        references=[Reference(id="ref1", manual_citation="Test ref")],
        curation_status="validated",
    )
    defaults.update(kwargs)
    return Lipid(**defaults)


def test_valid_lipid():
    lip = _make_valid_lipid()
    assert lip.id == "POPC"
    assert lip.curation_status == "validated"


def test_reject_lipid_without_id():
    with pytest.raises(ValidationError):
        Lipid(id="", lipid_class="glycerophospholipid", net_charge=0, curation_status="validated")


def test_warn_lipid_without_reference():
    lip = _make_valid_lipid(references=[])
    assert not lip.has_references()


def test_valid_forcefield_mapping():
    ffm = ForceFieldMapping(
        lipid_id="POPC",
        force_field="charmm36",
        residue_name="POPC",
        status="validated",
    )
    assert ffm.force_field == "charmm36"


def test_reject_unknown_forcefield():
    with pytest.raises(ValidationError):
        ForceFieldMapping(
            lipid_id="POPC",
            force_field="unknown_ff",
            residue_name="POPC",
        )


def test_valid_preset():
    preset = MembranePreset(
        id="test_preset",
        leaflets={
            "upper": {"POPC": 70, "CHOL": 30},
            "lower": {"POPE": 60, "POPS": 40},
        },
        references=[Reference(id="ref1", manual_citation="Test")],
    )
    assert preset.id == "test_preset"
    assert "upper" in preset.leaflets


def test_reject_preset_without_upper_leaflet():
    with pytest.raises(ValidationError):
        MembranePreset(
            id="bad_preset",
            leaflets={"lower": {"POPE": 100}},
        )


def test_reject_preset_with_leaflet_sum_not_100():
    with pytest.raises(ValidationError):
        MembranePreset(
            id="bad_preset",
            leaflets={
                "upper": {"POPC": 50, "CHOL": 30},
                "lower": {"POPE": 100},
            },
        )


def test_valid_source_manifest():
    manifest = SourceManifest(source_name="test_source")
    assert manifest.source_name == "test_source"
    assert manifest.lipids == []


def _preset_base(**kwargs) -> dict:
    return dict(
        id="p",
        leaflets={"upper": {"POPE": 100}, "lower": {"POPE": 100}},
        **kwargs,
    )


def test_evidence_level_example_needs_no_reference():
    p = MembranePreset(**_preset_base(evidence_level="example"))
    assert p.evidence_level == "example"


def test_evidence_level_inferred_requires_reference():
    with pytest.raises(ValidationError, match="requires at least one reference"):
        MembranePreset(**_preset_base(evidence_level="inferred"))


def test_evidence_level_inferred_accepts_manual_citation():
    p = MembranePreset(**_preset_base(
        evidence_level="inferred",
        references=[Reference(id="r1", manual_citation="Some review")],
    ))
    assert p.evidence_level == "inferred"


def test_evidence_level_curated_requires_doi_or_pmid():
    with pytest.raises(ValidationError, match="doi or pmid"):
        MembranePreset(**_preset_base(
            evidence_level="curated",
            references=[Reference(id="r1", manual_citation="No DOI here")],
        ))


def test_evidence_level_curated_accepts_doi():
    p = MembranePreset(**_preset_base(
        evidence_level="curated",
        references=[Reference(id="r1", doi="10.1000/test")],
    ))
    assert p.evidence_level == "curated"


def test_evidence_level_validated_accepts_pmid():
    p = MembranePreset(**_preset_base(
        evidence_level="validated",
        references=[Reference(id="r1", pmid="12345678")],
    ))
    assert p.evidence_level == "validated"


def test_evidence_level_invalid_value_rejected():
    with pytest.raises(ValidationError, match="not valid"):
        MembranePreset(**_preset_base(evidence_level="made_up"))


def test_evidence_level_none_always_accepted():
    p = MembranePreset(**_preset_base())
    assert p.evidence_level is None


def test_build_report_reproducibility_fields():
    report = BuildReport(
        preset_id="test",
        force_field="charmm36",
        engine="gromacs",
        lipids_per_leaflet=64,
        sorting_mode="random",
        seed=42,
        desired_composition={"upper": {"POPE": 100}},
        realized_composition={"upper": {"POPE": 64}},
        bilbo_version="0.1.0",
        preset_snapshot='{"id": "test"}',
        template_hashes={"POPE.pdb": "abc123"},
    )
    j = report.model_dump_json()
    restored = BuildReport.model_validate_json(j)
    assert restored.bilbo_version == "0.1.0"
    assert restored.preset_snapshot == '{"id": "test"}'
    assert restored.template_hashes == {"POPE.pdb": "abc123"}


def test_build_report_serialization():
    report = BuildReport(
        preset_id="test",
        force_field="charmm36",
        engine="gromacs",
        lipids_per_leaflet=64,
        sorting_mode="random",
        seed=42,
        desired_composition={"upper": {"POPC": 100}},
        realized_composition={"upper": {"POPC": 64}},
    )
    j = report.model_dump_json()
    restored = BuildReport.model_validate_json(j)
    assert restored.preset_id == "test"
    assert restored.lipids_per_leaflet == 64
