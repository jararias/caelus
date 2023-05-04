
import sys

from loguru import logger

try:
    from ._version import __version__  # pylint: disable=import-error
except ModuleNotFoundError:
    logger.warning(
        'missing module caelus._version. Perhaps installed editable?'
    )

from . import data, diagnostics
from .classifier import classify


logger.disable(__name__)
