"""Reference model."""

from typing import Optional

from pydantic import BaseModel, model_validator


class Reference(BaseModel):
    id: str
    source_type: str = "manual"
    doi: Optional[str] = None
    url: Optional[str] = None
    pmid: Optional[str] = None
    manual_citation: Optional[str] = None
    accessed_at: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def require_at_least_one_identifier(self) -> "Reference":
        if not any([self.doi, self.url, self.pmid, self.manual_citation]):
            raise ValueError(
                f"Reference '{self.id}' must have at least one of: doi, url, pmid, manual_citation"
            )
        return self
