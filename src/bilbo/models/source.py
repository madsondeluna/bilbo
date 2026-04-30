"""SourceManifest model."""

from typing import Optional

from pydantic import BaseModel


class SourceLipidEntry(BaseModel):
    lipid_id: str
    source_lipid_name: str
    category: Optional[str] = None
    files: list[str] = []
    force_field: Optional[str] = None
    residue_name: Optional[str] = None
    status: str = "pending_review"
    curation_status: str = "pending_review"
    notes: list[str] = []


class SourceManifest(BaseModel):
    source_name: str
    source_url: Optional[str] = None
    retrieved_at: Optional[str] = None
    license: Optional[str] = None
    version: Optional[str] = None
    commit_hash: Optional[str] = None
    files: list[str] = []
    lipids: list[SourceLipidEntry] = []
    warnings: list[str] = []
    errors: list[str] = []
