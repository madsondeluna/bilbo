"""Extract lipid catalog from a saved CHARMM-GUI Individual Lipid Molecule Library HTML page."""

import json
import re
from pathlib import Path
from typing import Any

import yaml

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[assignment,misc]

from bilbo.extractors.base import BaseExtractor

KNOWN_CATEGORIES = [
    "Sterols",
    "PA lipids",
    "PC lipids",
    "PE lipids",
    "PG lipids",
    "PS lipids",
    "PI lipids",
    "CL lipids",
    "SM and ceramide lipids",
    "Bacterial lipids",
    "Fatty acids",
]


def _parse_html(html_text: str) -> list[dict[str, Any]]:
    if BeautifulSoup is None:
        raise ImportError(
            "beautifulsoup4 is required for CHARMM-GUI archive extraction. "
            "Install with: pip install beautifulsoup4"
        )
    soup = BeautifulSoup(html_text, "html.parser")
    entries: list[dict[str, Any]] = []
    current_category = "Unknown"

    for element in soup.find_all(["h2", "h3", "h4", "tr", "li"]):
        tag = element.name
        text = element.get_text(strip=True)

        if tag in ("h2", "h3", "h4"):
            for cat in KNOWN_CATEGORIES:
                if cat.lower() in text.lower():
                    current_category = cat
                    break

        if tag in ("tr", "li"):
            links = element.find_all("a")
            has_download = any("download" in (a.get("href", "") + a.get_text()).lower() for a in links)
            has_pubchem = any("pubchem" in (a.get("href", "") + a.get_text()).lower() for a in links)

            name_cell = element.find("td")
            if name_cell is None and tag == "li":
                name_text = re.sub(r"\s+", " ", text).strip()
            elif name_cell:
                name_text = name_cell.get_text(strip=True)
            else:
                continue

            if not name_text or len(name_text) < 2:
                continue

            entries.append(
                {
                    "lipid_archive_name": name_text,
                    "category": current_category,
                    "has_download_link": has_download,
                    "has_pubchem_link": has_pubchem,
                    "source": "charmm_gui",
                    "curation_status": "pending_review",
                }
            )

    return entries


class CharmmGuiArchiveExtractor(BaseExtractor):
    def extract(self, path: Path) -> list[dict[str, Any]]:
        path = Path(path)
        html_text = path.read_text(encoding="utf-8", errors="ignore")
        return _parse_html(html_text)

    def extract_and_save(self, html_path: Path, output_dir: Path) -> dict[str, Path]:
        entries = self.extract(html_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        yaml_path = output_dir / "charmm_gui_lipids_raw.yaml"
        json_path = output_dir / "charmm_gui_lipids_raw.json"

        yaml_path.write_text(
            yaml.dump(entries, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        json_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

        return {"yaml": yaml_path, "json": json_path}
