"""Downloader registry and core set definitions."""

from bilbo.downloaders.charmm_gui import CharmmGuiDownloader

CORE_SET = [
    "POPC", "POPE", "POPG", "POPS",
    "DOPC", "DOPE", "DOPG", "DOPS",
    "DPPC", "DLPC", "DMPC", "DSPC",
    "CHOL", "SM", "PI", "PIP2", "CL",
]

DOWNLOADERS = {
    "charmm-gui": CharmmGuiDownloader,
}
