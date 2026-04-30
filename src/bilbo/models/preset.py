"""MembranePreset model."""

from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

from bilbo.models.reference import Reference

# Hierarchy of evidence quality with their citation requirements.
# "example"  : demo/test data; no citation required.
# "inferred" : derived from review articles or databases; at least one reference required.
# "curated"  : manually curated from primary literature; requires doi or pmid.
# "validated": composition matches MD observables (e.g. thickness, APL); requires doi or pmid.
EVIDENCE_LEVELS: dict[str, dict[str, bool]] = {
    "example":   {"requires_reference": False, "requires_doi_or_pmid": False},
    "inferred":  {"requires_reference": True,  "requires_doi_or_pmid": False},
    "curated":   {"requires_reference": True,  "requires_doi_or_pmid": True},
    "validated": {"requires_reference": True,  "requires_doi_or_pmid": True},
}


class LeafletComposition(BaseModel):
    lipids: dict[str, float]

    @field_validator("lipids")
    @classmethod
    def check_sum(cls, v: dict[str, float]) -> dict[str, float]:
        total = sum(v.values())
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Leaflet composition must sum to 100, got {total}")
        return v

    def lipid_ids(self) -> list[str]:
        return list(self.lipids.keys())


class MembranePreset(BaseModel):
    id: str
    description: str = ""
    organism: Optional[str] = None
    membrane_type: Optional[str] = None
    symmetry: str = "symmetric"
    leaflets: dict[str, dict[str, float]]
    references: list[Reference] = []
    warnings: list[str] = []
    evidence_level: Optional[str] = None

    @field_validator("symmetry")
    @classmethod
    def validate_symmetry(cls, v: str) -> str:
        if v not in ("symmetric", "asymmetric"):
            raise ValueError(f"symmetry must be 'symmetric' or 'asymmetric', got '{v}'")
        return v

    @model_validator(mode="after")
    def validate_leaflets(self) -> "MembranePreset":
        if "upper" not in self.leaflets:
            raise ValueError(f"Preset '{self.id}' is missing 'upper' leaflet")
        if "lower" not in self.leaflets:
            raise ValueError(f"Preset '{self.id}' is missing 'lower' leaflet")
        for name, comp in self.leaflets.items():
            total = sum(comp.values())
            if abs(total - 100.0) > 0.01:
                raise ValueError(
                    f"Leaflet '{name}' in preset '{self.id}' must sum to 100, got {total}"
                )
        return self

    @model_validator(mode="after")
    def validate_evidence_level(self) -> "MembranePreset":
        if self.evidence_level is None:
            return self
        if self.evidence_level not in EVIDENCE_LEVELS:
            allowed = ", ".join(f"'{k}'" for k in EVIDENCE_LEVELS)
            raise ValueError(
                f"Preset '{self.id}': evidence_level '{self.evidence_level}' is not valid. "
                f"Allowed values: {allowed}"
            )
        rules = EVIDENCE_LEVELS[self.evidence_level]
        if rules["requires_reference"] and not self.references:
            raise ValueError(
                f"Preset '{self.id}': evidence_level='{self.evidence_level}' "
                "requires at least one reference."
            )
        if rules["requires_doi_or_pmid"]:
            has_citable = any(r.doi or r.pmid for r in self.references)
            if not has_citable:
                raise ValueError(
                    f"Preset '{self.id}': evidence_level='{self.evidence_level}' "
                    "requires at least one reference with a doi or pmid."
                )
        return self

    def all_lipid_ids(self) -> list[str]:
        ids: list[str] = []
        for comp in self.leaflets.values():
            for lid in comp:
                if lid not in ids:
                    ids.append(lid)
        return ids

    def has_references(self) -> bool:
        return len(self.references) > 0
