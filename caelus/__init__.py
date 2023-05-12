
import sys

from loguru import logger

from .version import version as __version__

from . import data, diagnostics
from .classifier import classify
