"""BaseExtractor ABC."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, path: Path) -> Any:
        pass
