"""BaseDownloader ABC."""

from abc import ABC, abstractmethod
from pathlib import Path

from bilbo.models.source import SourceManifest


class BaseDownloader(ABC):
    @abstractmethod
    def fetch(self, output_dir: Path, **kwargs) -> SourceManifest:
        pass

    @abstractmethod
    def index(self, path: Path, **kwargs) -> SourceManifest:
        pass
