"""CHARMM-GUI Individual Lipid Molecule Library downloader/indexer."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bilbo.downloaders.base import BaseDownloader
from bilbo.extractors.charmm_gui_archive import CharmmGuiArchiveExtractor
from bilbo.models.source import SourceLipidEntry, SourceManifest

CHARMM_GUI_URL = "https://www.charmm-gui.org/?doc=input/membrane.bilayer"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CharmmGuiDownloader(BaseDownloader):
    def index(
        self,
        path: Path,
        lipid_filter: Optional[list[str]] = None,
        output_dir: Optional[Path] = None,
    ) -> SourceManifest:
        extractor = CharmmGuiArchiveExtractor()
        entries = extractor.extract(path)

        lipid_entries = []
        for entry in entries:
            lid = entry["lipid_archive_name"]
            if lipid_filter and lid not in lipid_filter:
                continue
            lipid_entries.append(
                SourceLipidEntry(
                    lipid_id=lid,
                    source_lipid_name=lid,
                    category=entry.get("category"),
                    files=[],
                    status="pending_review",
                    curation_status="pending_review",
                    notes=[
                        f"has_download_link={entry.get('has_download_link', False)}",
                        f"has_pubchem_link={entry.get('has_pubchem_link', False)}",
                    ],
                )
            )

        manifest = SourceManifest(
            source_name="charmm_gui",
            source_url=CHARMM_GUI_URL,
            retrieved_at=_now_iso(),
            lipids=lipid_entries,
            warnings=[
                "CHARMM-GUI data indexed from local HTML file. Download requires manual access.",
                "All entries marked pending_review. Manual curation required before use in builds.",
            ],
        )

        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = output_dir / "charmm_gui_manifest.json"
            manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

        return manifest

    def fetch(
        self,
        output_dir: Path,
        html_path: Optional[Path] = None,
        lipid_filter: Optional[list[str]] = None,
        do_download: bool = False,
        **kwargs,
    ) -> SourceManifest:
        if html_path is None:
            raise ValueError(
                "CHARMM-GUI fetch requires a saved HTML file (--html). "
                "Download the page manually from: " + CHARMM_GUI_URL
            )

        manifest = self.index(html_path, lipid_filter=lipid_filter, output_dir=output_dir)

        if do_download:
            manifest.warnings.append(
                "Download flag set but no direct download links were resolved from the HTML index. "
                "Please download lipid files manually from CHARMM-GUI."
            )

        return manifest
