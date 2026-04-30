"""Peptide and PeptidePlacement models."""

from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

from bilbo.models.reference import Reference

ACCEPTED_STRUCTURE_FORMATS = {"pdb", "xyz", "fasta_simplified"}
ACCEPTED_ANCHOR_MODES = {"center_of_mass", "n_terminus", "c_terminus", "residue_index"}
ACCEPTED_LEAFLETS = {"upper", "lower", "center", "transmembrane"}
ACCEPTED_ORIENTATIONS = {"parallel", "perpendicular", "tilted", "transmembrane", "custom"}


class Peptide(BaseModel):
    id: str
    name: str = ""
    sequence: Optional[str] = None
    structure_file: Optional[str] = None
    structure_format: Optional[str] = None
    net_charge: Optional[float] = None
    residue_count: Optional[int] = None
    source: Optional[str] = None
    references: list[Reference] = []
    curation_status: str = "pending_review"
    notes: list[str] = []

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Peptide id cannot be empty")
        return v

    @field_validator("structure_format")
    @classmethod
    def validate_structure_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ACCEPTED_STRUCTURE_FORMATS:
            raise ValueError(
                f"structure_format must be one of {sorted(ACCEPTED_STRUCTURE_FORMATS)}, got '{v}'"
            )
        return v

    def has_3d_structure(self) -> bool:
        return self.structure_file is not None and self.structure_format in ("pdb", "xyz")

    def is_fasta_simplified(self) -> bool:
        return self.structure_format == "fasta_simplified"


class PeptidePlacement(BaseModel):
    peptide_id: str
    placement_id: str
    input_structure: Optional[str] = None
    anchor_mode: str = "center_of_mass"
    leaflet: str = "upper"
    x: float = 0.0
    y: float = 0.0
    z: Optional[float] = None
    depth: float = 0.0
    tilt_deg: float = 0.0
    rotation_deg: float = 0.0
    azimuth_deg: float = 0.0
    orientation: str = "parallel"
    center_on_membrane: bool = True
    allow_overlap: bool = False
    collision_cutoff: float = 1.5
    notes: list[str] = []

    @field_validator("anchor_mode")
    @classmethod
    def validate_anchor_mode(cls, v: str) -> str:
        if v not in ACCEPTED_ANCHOR_MODES:
            raise ValueError(f"anchor_mode must be one of {sorted(ACCEPTED_ANCHOR_MODES)}")
        return v

    @field_validator("leaflet")
    @classmethod
    def validate_leaflet(cls, v: str) -> str:
        if v not in ACCEPTED_LEAFLETS:
            raise ValueError(f"leaflet must be one of {sorted(ACCEPTED_LEAFLETS)}")
        return v

    @field_validator("orientation")
    @classmethod
    def validate_orientation(cls, v: str) -> str:
        if v not in ACCEPTED_ORIENTATIONS:
            raise ValueError(f"orientation must be one of {sorted(ACCEPTED_ORIENTATIONS)}")
        return v

    @model_validator(mode="after")
    def validate_angles(self) -> "PeptidePlacement":
        if not (0 <= self.tilt_deg <= 180):
            raise ValueError(f"tilt_deg must be between 0 and 180, got {self.tilt_deg}")
        if not (0 <= self.rotation_deg <= 360):
            raise ValueError(f"rotation_deg must be between 0 and 360, got {self.rotation_deg}")
        if not (0 <= self.azimuth_deg <= 360):
            raise ValueError(f"azimuth_deg must be between 0 and 360, got {self.azimuth_deg}")
        return self
