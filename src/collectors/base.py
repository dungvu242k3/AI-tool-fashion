"""
Base collector interface with common logging, retries, and error handling.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class BaseCollector(ABC):
    """Abstract base class for all data collectors."""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"collector.{name}")

    @abstractmethod
    def collect(self, niche: Dict[str, Any]) -> List[Any]:
        """
        Collect trend or product data for a given niche configuration.

        Args:
            niche: Dictionary containing niche name and seed parameters.

        Returns:
            List of collected items or records.
        """
        pass
