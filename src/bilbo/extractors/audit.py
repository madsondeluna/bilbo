"""Audit extractor: validates library consistency."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bilbo.extractors.base import BaseExtractor
from bilbo.models.forcefield import ACCEPTED_FORCE_FIELDS
from bilbo.models.lipid import Lipid
from bilbo.models.preset import MembranePreset


@dataclass
class AuditResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return len(self.errors) == 0


class AuditExtractor(BaseExtractor):
    def extract(self, path: Path) -> AuditResult:
        raise NotImplementedError("Use audit_library() instead")

    def audit_library(
        self,
        lipids: list[Lipid],
        presets: list[MembranePreset],
        topology_scan_result: Any = None,
    ) -> AuditResult:
        result = AuditResult()
        lipid_map = {lip.id: lip for lip in lipids}

        for lip in lipids:
            if not lip.has_references():
                result.warnings.append(f"Lipid '{lip.id}' has no references.")
            if lip.net_charge is None:
                result.warnings.append(f"Lipid '{lip.id}' has no net_charge.")
            if lip.tails is None and lip.lipid_class not in ("sterol",):
                result.warnings.append(f"Lipid '{lip.id}' has no tails defined.")
            if not lip.force_fields:
                result.warnings.append(f"Lipid '{lip.id}' has no force field mappings.")
            for ff_key, ffm in lip.force_fields.items():
                if ffm.force_field not in ACCEPTED_FORCE_FIELDS:
                    result.errors.append(
                        f"Lipid '{lip.id}' has unknown force field '{ffm.force_field}'."
                    )

        for preset in presets:
            if not preset.has_references():
                result.warnings.append(f"Preset '{preset.id}' has no references.")
            for leaflet_name, comp in preset.leaflets.items():
                total = sum(comp.values())
                if abs(total - 100.0) > 0.01:
                    result.errors.append(
                        f"Preset '{preset.id}' leaflet '{leaflet_name}' sums to {total}, not 100."
                    )
                for lid in comp:
                    if lid not in lipid_map:
                        result.errors.append(
                            f"Preset '{preset.id}' uses missing lipid '{lid}'."
                        )
                    elif lipid_map[lid].curation_status in (
                        "downloaded",
                        "pending_review",
                    ):
                        result.errors.append(
                            f"Preset '{preset.id}': lipid '{lid}' has status "
                            f"'{lipid_map[lid].curation_status}' and cannot enter a build."
                        )

        if topology_scan_result is not None:
            for lip in lipids:
                for ff_key, ffm in lip.force_fields.items():
                    rname = ffm.residue_name
                    if (
                        rname
                        and topology_scan_result.topology_files_scanned
                        and rname not in topology_scan_result.found_residues
                    ):
                        result.warnings.append(
                            f"Lipid '{lip.id}' residue '{rname}' not found in scanned topologies."
                        )

        return result
