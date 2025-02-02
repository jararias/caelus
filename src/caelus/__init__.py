
import sys

from loguru import logger

from . import data, diagnostics
from .classifier import classify

__version__ = "0.2.0"

REQUIRED_TO_CLASSIFY = {"longitude", "sza", "eth", "ghi", "ghics", "ghicda"}
