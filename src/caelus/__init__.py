
import importlib.metadata

from . import data, diagnostics
from .classifier import classify
from .logtools import enable_logger, disable_logger

try:
    __version__ = importlib.metadata.version("caelus")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["data", "diagnostics", "classify", "__version__", "REQUIRED_TO_CLASSIFY"]
