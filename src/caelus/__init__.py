import importlib.metadata

from . import data
from .classifier import classify, REQUIRED_TO_CLASSIFY
from .logtools import enable_logger

try:
    __version__ = importlib.metadata.version("caelus-solar")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["data", "classify", "__version__", "REQUIRED_TO_CLASSIFY"]

enable_logger(level="INFO")
