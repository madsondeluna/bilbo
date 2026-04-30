"""Lipid model."""

from typing import Any, Optional

from pydantic import BaseModel, field_validator, model_validator

from bilbo.models.forcefield import ForceFieldMapping
from bilbo.models.reference import Reference

CURATION_STATUSES = {"pending_review", "pending_manual_review", "downloaded", "curated", "validated"}


class Lipid(BaseModel):
    id: str
    name: str = ""
    lipid_class: str
    headgroup: Optional[str] = None
    net_charge: Optional[float] = None
    tails: Optional[Any] = None
    tags: list[str] = []
    force_fields: dict[str, ForceFieldMapping] = {}
    references: list[Reference] = []
    curation_status: str = "pending_review"
    source: Optional[str] = None
    notes: list[str] = []

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Lipid id cannot be empty")
        return v

    @field_validator("lipid_class")
    @classmethod
    def lipid_class_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("lipid_class cannot be empty")
        return v

    @model_validator(mode="after")
    def validate_curated_fields(self) -> "Lipid":
        non_pending = self.curation_status not in ("pending_review", "pending_manual_review")
        if non_pending and self.net_charge is None:
            raise ValueError(
                f"Lipid '{self.id}' with curation_status='{self.curation_status}' "
                "requires net_charge"
            )
        if non_pending and not self.force_fields:
            raise ValueError(
                f"Lipid '{self.id}' with curation_status='{self.curation_status}' "
                "requires at least one force field mapping"
            )
        return self

    def has_references(self) -> bool:
        return len(self.references) > 0

    def is_buildable(self) -> bool:
        return self.curation_status == "validated"
