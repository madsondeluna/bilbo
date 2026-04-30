"""Tests for CHARMM-GUI archive extractor."""

import pytest
from pathlib import Path

from bilbo.extractors.charmm_gui_archive import CharmmGuiArchiveExtractor


def test_charmm_gui_archive_fixture_extracts_categories(charmm_gui_html):
    extractor = CharmmGuiArchiveExtractor()
    entries = extractor.extract(charmm_gui_html)
    assert len(entries) > 0
    categories = {e["category"] for e in entries}
    assert len(categories) >= 1


def test_charmm_gui_archive_marks_pending_review(charmm_gui_html):
    extractor = CharmmGuiArchiveExtractor()
    entries = extractor.extract(charmm_gui_html)
    for entry in entries:
        assert entry["curation_status"] == "pending_review"


def test_charmm_gui_archive_extract_and_save(charmm_gui_html, tmp_path):
    extractor = CharmmGuiArchiveExtractor()
    paths = extractor.extract_and_save(charmm_gui_html, tmp_path)
    assert paths["yaml"].exists()
    assert paths["json"].exists()
    assert paths["yaml"].stat().st_size > 0
    assert paths["json"].stat().st_size > 0
