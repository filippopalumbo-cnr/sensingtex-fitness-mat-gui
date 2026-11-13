"""Offline pressure-mat descriptors. No hardware or GUI imports are required."""

__version__ = "0.1.0"

from .config import ExtractionConfig
from .core import ExtractionResult, extract_arrays, extract_file

__all__ = ["ExtractionConfig", "ExtractionResult", "extract_arrays", "extract_file"]
