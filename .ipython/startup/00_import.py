from IPython import get_ipython
from IPython.core.magic import register_line_magic

ipython = get_ipython()
ipython.run_line_magic("load_ext", "autoreload")
ipython.run_line_magic("autoreload", "2")

import numpy as np  # noqa: E402
import pylab as pl  # noqa: E402
import pandas as pd  # noqa: E402

from pandas.plotting import register_matplotlib_converters  # noqa: E402
register_matplotlib_converters()

pl.ion()
