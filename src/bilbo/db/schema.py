"""SQLite schema via SQLModel."""

from typing import Optional

from sqlmodel import Field, SQLModel


class LipidRecord(SQLModel, table=True):
    __tablename__ = "lipids"

    id: str = Field(primary_key=True)
    name: str = ""
    lipid_class: str = ""
    headgroup: Optional[str] = None
    net_charge: Optional[float] = None
    tags: str = "[]"
    curation_status: str = "pending_review"
    source: Optional[str] = None
    notes: str = "[]"
    raw_json: str = "{}"


class ForceFieldMappingRecord(SQLModel, table=True):
    __tablename__ = "forcefield_mappings"

    id: Optional[int] = Field(default=None, primary_key=True)
    lipid_id: str = Field(index=True)
    force_field: str
    residue_name: str
    topology_file: Optional[str] = None
    status: str = "requires_mapping_check"
    notes: Optional[str] = None


class MembranePresetRecord(SQLModel, table=True):
    __tablename__ = "membrane_presets"

    id: str = Field(primary_key=True)
    description: str = ""
    organism: Optional[str] = None
    membrane_type: Optional[str] = None
    symmetry: str = "symmetric"
    evidence_level: Optional[str] = None
    warnings: str = "[]"
    raw_json: str = "{}"


class PresetLeafletRecord(SQLModel, table=True):
    __tablename__ = "preset_leaflet_compositions"

    id: Optional[int] = Field(default=None, primary_key=True)
    preset_id: str = Field(index=True)
    leaflet: str
    lipid_id: str
    percentage: float


class ReferenceRecord(SQLModel, table=True):
    __tablename__ = "references"

    id: str = Field(primary_key=True)
    source_type: str = "manual"
    doi: Optional[str] = None
    url: Optional[str] = None
    pmid: Optional[str] = None
    manual_citation: Optional[str] = None
    accessed_at: Optional[str] = None
    notes: Optional[str] = None
    owner_type: Optional[str] = None
    owner_id: Optional[str] = None


class SourceManifestRecord(SQLModel, table=True):
    __tablename__ = "source_manifests"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_name: str
    source_url: Optional[str] = None
    retrieved_at: Optional[str] = None
    license: Optional[str] = None
    version: Optional[str] = None
    commit_hash: Optional[str] = None
    raw_json: str = "{}"


class AuditReportRecord(SQLModel, table=True):
    __tablename__ = "audit_reports"

    id: Optional[int] = Field(default=None, primary_key=True)
    ran_at: str
    errors_json: str = "[]"
    warnings_json: str = "[]"


class PeptideRecord(SQLModel, table=True):
    __tablename__ = "peptides"

    id: str = Field(primary_key=True)
    name: str = ""
    sequence: Optional[str] = None
    structure_file: Optional[str] = None
    structure_format: Optional[str] = None
    net_charge: Optional[float] = None
    residue_count: Optional[int] = None
    source: Optional[str] = None
    curation_status: str = "pending_review"
    raw_json: str = "{}"


class PeptidePlacementRecord(SQLModel, table=True):
    __tablename__ = "peptide_placements"

    id: Optional[int] = Field(default=None, primary_key=True)
    peptide_id: str
    placement_id: str
    build_dir: str
    raw_json: str = "{}"
