"""Tests for downloaders (no internet access)."""

import json
import pytest
from pathlib import Path

from bilbo.downloaders.charmm_gui import CharmmGuiDownloader


def test_charmm_gui_indexer_from_local_html(charmm_gui_html, tmp_path):
    downloader = CharmmGuiDownloader()
    manifest = downloader.index(charmm_gui_html, output_dir=tmp_path)
    assert len(manifest.lipids) > 0
    manifest_file = tmp_path / "charmm_gui_manifest.json"
    assert manifest_file.exists()


def test_charmm_gui_downloader_does_not_download_without_flag(charmm_gui_html, tmp_path):
    downloader = CharmmGuiDownloader()
    manifest = downloader.fetch(output_dir=tmp_path, html_path=charmm_gui_html, do_download=False)
    assert all(len(e.files) == 0 for e in manifest.lipids)


def test_source_manifest_written(charmm_gui_html, tmp_path):
    downloader = CharmmGuiDownloader()
    downloader.index(charmm_gui_html, output_dir=tmp_path)
    assert (tmp_path / "charmm_gui_manifest.json").exists()


def test_downloaded_lipids_are_pending_review(charmm_gui_html, tmp_path):
    downloader = CharmmGuiDownloader()
    manifest = downloader.index(charmm_gui_html)
    for entry in manifest.lipids:
        assert entry.curation_status == "pending_review"


def test_source_audit_blocks_pending_review_from_build():
    from bilbo.models.lipid import Lipid
    from bilbo.models.preset import MembranePreset
    from bilbo.models.reference import Reference
    from bilbo.extractors.audit import AuditExtractor

    pending_lip = Lipid(
        id="FAKEPEND",
        lipid_class="glycerophospholipid",
        curation_status="pending_review",
    )
    preset = MembranePreset(
        id="test_preset",
        leaflets={
            "upper": {"FAKEPEND": 100},
            "lower": {"FAKEPEND": 100},
        },
        references=[Reference(id="r1", manual_citation="test")],
    )
    auditor = AuditExtractor()
    result = auditor.audit_library([pending_lip], [preset])
    assert not result.ok()
    assert any("pending_review" in e or "FAKEPEND" in e for e in result.errors)
