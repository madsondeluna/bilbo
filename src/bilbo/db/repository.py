"""Database repository: CRUD operations for BILBO models."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine, select

from bilbo.db.schema import (
    AuditReportRecord,
    ForceFieldMappingRecord,
    LipidRecord,
    MembranePresetRecord,
    PeptideRecord,
    PresetLeafletRecord,
    SourceManifestRecord,
)
from bilbo.models.forcefield import ForceFieldMapping
from bilbo.models.lipid import Lipid
from bilbo.models.peptide import Peptide
from bilbo.models.preset import MembranePreset
from bilbo.models.source import SourceManifest

_engine = None


def get_engine(db_path: Optional[Path] = None):
    import os

    global _engine
    if _engine is None:
        if db_path is None:
            env_path = os.environ.get("BILBO_DB_PATH")
            db_path = Path(env_path) if env_path else Path.home() / ".bilbo" / "bilbo.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{db_path}", echo=False)
        SQLModel.metadata.create_all(_engine)
    return _engine


def reset_engine(db_path: Optional[Path] = None):
    global _engine
    _engine = None
    return get_engine(db_path)


def upsert_lipid(lipid: Lipid, session: Session) -> None:
    raw = lipid.model_dump_json()
    record = session.get(LipidRecord, lipid.id)
    if record is None:
        record = LipidRecord(
            id=lipid.id,
            name=lipid.name,
            lipid_class=lipid.lipid_class,
            headgroup=lipid.headgroup,
            net_charge=lipid.net_charge,
            tags=json.dumps(lipid.tags),
            curation_status=lipid.curation_status,
            source=lipid.source,
            notes=json.dumps(lipid.notes),
            raw_json=raw,
        )
    else:
        record.name = lipid.name
        record.lipid_class = lipid.lipid_class
        record.headgroup = lipid.headgroup
        record.net_charge = lipid.net_charge
        record.tags = json.dumps(lipid.tags)
        record.curation_status = lipid.curation_status
        record.source = lipid.source
        record.notes = json.dumps(lipid.notes)
        record.raw_json = raw
    session.add(record)

    for ff_key, ffm in lipid.force_fields.items():
        stmt = select(ForceFieldMappingRecord).where(
            ForceFieldMappingRecord.lipid_id == lipid.id,
            ForceFieldMappingRecord.force_field == ffm.force_field,
        )
        ffr = session.exec(stmt).first()
        if ffr is None:
            ffr = ForceFieldMappingRecord(
                lipid_id=lipid.id,
                force_field=ffm.force_field,
                residue_name=ffm.residue_name,
                topology_file=ffm.topology_file,
                status=ffm.status,
                notes=ffm.notes,
            )
        else:
            ffr.residue_name = ffm.residue_name
            ffr.topology_file = ffm.topology_file
            ffr.status = ffm.status
            ffr.notes = ffm.notes
        session.add(ffr)


def get_lipid(lipid_id: str, session: Session) -> Optional[Lipid]:
    record = session.get(LipidRecord, lipid_id)
    if record is None:
        return None
    return Lipid.model_validate_json(record.raw_json)


def list_lipids(session: Session) -> list[Lipid]:
    records = session.exec(select(LipidRecord)).all()
    return [Lipid.model_validate_json(r.raw_json) for r in records]


def upsert_preset(preset: MembranePreset, session: Session) -> None:
    raw = preset.model_dump_json()
    record = session.get(MembranePresetRecord, preset.id)
    if record is None:
        record = MembranePresetRecord(
            id=preset.id,
            description=preset.description,
            organism=preset.organism,
            membrane_type=preset.membrane_type,
            symmetry=preset.symmetry,
            evidence_level=preset.evidence_level,
            warnings=json.dumps(preset.warnings),
            raw_json=raw,
        )
    else:
        record.description = preset.description
        record.organism = preset.organism
        record.membrane_type = preset.membrane_type
        record.symmetry = preset.symmetry
        record.evidence_level = preset.evidence_level
        record.warnings = json.dumps(preset.warnings)
        record.raw_json = raw
    session.add(record)

    stmt = select(PresetLeafletRecord).where(PresetLeafletRecord.preset_id == preset.id)
    for old in session.exec(stmt).all():
        session.delete(old)

    for leaflet_name, comp in preset.leaflets.items():
        for lid, pct in comp.items():
            session.add(
                PresetLeafletRecord(
                    preset_id=preset.id,
                    leaflet=leaflet_name,
                    lipid_id=lid,
                    percentage=pct,
                )
            )


def get_preset(preset_id: str, session: Session) -> Optional[MembranePreset]:
    record = session.get(MembranePresetRecord, preset_id)
    if record is None:
        return None
    return MembranePreset.model_validate_json(record.raw_json)


def list_presets(session: Session) -> list[MembranePreset]:
    records = session.exec(select(MembranePresetRecord)).all()
    return [MembranePreset.model_validate_json(r.raw_json) for r in records]


def upsert_forcefield_mapping(ffm: ForceFieldMapping, session: Session) -> None:
    stmt = select(ForceFieldMappingRecord).where(
        ForceFieldMappingRecord.lipid_id == ffm.lipid_id,
        ForceFieldMappingRecord.force_field == ffm.force_field,
    )
    record = session.exec(stmt).first()
    if record is None:
        record = ForceFieldMappingRecord(
            lipid_id=ffm.lipid_id,
            force_field=ffm.force_field,
            residue_name=ffm.residue_name,
            topology_file=ffm.topology_file,
            status=ffm.status,
            notes=ffm.notes,
        )
    else:
        record.residue_name = ffm.residue_name
        record.topology_file = ffm.topology_file
        record.status = ffm.status
        record.notes = ffm.notes
    session.add(record)


def list_forcefield_mappings(session: Session) -> list[ForceFieldMapping]:
    records = session.exec(select(ForceFieldMappingRecord)).all()
    return [
        ForceFieldMapping(
            lipid_id=r.lipid_id,
            force_field=r.force_field,
            residue_name=r.residue_name,
            topology_file=r.topology_file,
            status=r.status,
            notes=r.notes,
        )
        for r in records
    ]


def upsert_peptide(peptide: Peptide, session: Session) -> None:
    raw = peptide.model_dump_json()
    record = session.get(PeptideRecord, peptide.id)
    if record is None:
        record = PeptideRecord(
            id=peptide.id,
            name=peptide.name,
            sequence=peptide.sequence,
            structure_file=peptide.structure_file,
            structure_format=peptide.structure_format,
            net_charge=peptide.net_charge,
            residue_count=peptide.residue_count,
            source=peptide.source,
            curation_status=peptide.curation_status,
            raw_json=raw,
        )
    else:
        record.name = peptide.name
        record.sequence = peptide.sequence
        record.structure_file = peptide.structure_file
        record.structure_format = peptide.structure_format
        record.net_charge = peptide.net_charge
        record.residue_count = peptide.residue_count
        record.source = peptide.source
        record.curation_status = peptide.curation_status
        record.raw_json = raw
    session.add(record)


def get_peptide(peptide_id: str, session: Session) -> Optional[Peptide]:
    record = session.get(PeptideRecord, peptide_id)
    if record is None:
        return None
    return Peptide.model_validate_json(record.raw_json)


def list_peptides(session: Session) -> list[Peptide]:
    records = session.exec(select(PeptideRecord)).all()
    return [Peptide.model_validate_json(r.raw_json) for r in records]


def save_audit_report(errors: list[str], warnings: list[str], session: Session) -> None:
    now = datetime.now(timezone.utc).isoformat()
    record = AuditReportRecord(
        ran_at=now,
        errors_json=json.dumps(errors),
        warnings_json=json.dumps(warnings),
    )
    session.add(record)


def save_source_manifest(manifest: SourceManifest, session: Session) -> None:
    raw = manifest.model_dump_json()
    record = SourceManifestRecord(
        source_name=manifest.source_name,
        source_url=manifest.source_url,
        retrieved_at=manifest.retrieved_at,
        license=manifest.license,
        version=manifest.version,
        commit_hash=manifest.commit_hash,
        raw_json=raw,
    )
    session.add(record)
