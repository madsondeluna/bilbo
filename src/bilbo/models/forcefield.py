"""ForceFieldMapping model."""

from typing import Optional

from pydantic import BaseModel, field_validator

ACCEPTED_FORCE_FIELDS = {"charmm36", "gromacs_charmm36"}
ACCEPTED_STATUSES = {
    "available",
    "partial",
    "missing",
    "requires_mapping_check",
    "pending_manual_review",
    "validated",
}


class ForceFieldMapping(BaseModel):
    lipid_id: str
    force_field: str
    residue_name: str
    topology_file: Optional[str] = None
    status: str = "requires_mapping_check"
    notes: Optional[str] = None

    @field_validator("force_field")
    @classmethod
    def validate_force_field(cls, v: str) -> str:
        if v not in ACCEPTED_FORCE_FIELDS:
            raise ValueError(
                f"Unknown force field '{v}'. Accepted: {sorted(ACCEPTED_FORCE_FIELDS)}"
            )
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ACCEPTED_STATUSES:
            raise ValueError(
                f"Unknown status '{v}'. Accepted: {sorted(ACCEPTED_STATUSES)}"
            )
        return v
