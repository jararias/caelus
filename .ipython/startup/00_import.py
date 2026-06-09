from IPython import get_ipython
from IPython.core.magic import register_line_magic

ipython = get_ipython()
ipython.run_line_magic("load_ext", "autoreload")
ipython.run_line_magic("autoreload", "2")

import copy  # noqa: E402
import numpy as np  # noqa: E402
import pylab as pl  # noqa: E402
import pandas as pd  # noqa: E402
import polars as po  # noqa: E402
import seaborn as sns  # noqa: E402
import caelus  # noqa: E402

from pandas.plotting import register_matplotlib_converters  # noqa: E402
register_matplotlib_converters()

pl.ion()

flag = ("\033[91m\u2718\033[0m" if caelus.__version__ == "0.0.0"  # red cross
        else "\033[92m\u2714\033[0m")  # green tick
print(f"`caelus` imported with __version__ = {caelus.__version__} {flag}")  # noqa: T201
del(flag)

caelus.enable_logger(level="DEBUG")
site_metadata = caelus.data.load_metadata("car")
latitude = site_metadata.get("latitude")
longitude = site_metadata.get("longitude")
testdata = caelus.data.load("car", 2014)

def classify(period=None, **kwargs):
    data = testdata if period is None else testdata.loc[period]
    kwargs.setdefault("engine", "polars")
    kwargs.setdefault("full_output", False)
    return caelus.classify(data, latitude, longitude, **kwargs)

def compare(period="2014-01", palette="flare", **kwargs):
    pd_results = classify(period=period, **(kwargs | {"engine": "pandas", "full_output": True}))
    po_results = classify(period=period, **(kwargs | {"engine": "polars", "full_output": True}))
    fig, axes = pl.subplots(2, 3, figsize=(16, 10), layout="constrained")
    for k, varname in enumerate(("Kcs", "mean_ghi", "Km", "Kv", "Kvf")):
        ax = axes.flatten()[k]
        ax.plot(pd_results[varname], po_results[varname], "r.")
        ax.set(xlabel="pandas", ylabel="polars", title=varname)
        xmin, xmax, ymin, ymax = ax.axis()
        vmin, vmax = min(xmin, ymin), max(xmax, ymax)
        ax.axis([vmin, vmax, vmin, vmax])
    ax = axes.flatten()[k+1]
    crosstab = pd.crosstab(po_results["sky_type"].rename("polars"),
                           pd_results["sky_type"].rename("pandas"))
    base_cmap = sns.color_palette(palette, as_cmap=True)
    custom_cmap = copy.copy(base_cmap)
    custom_cmap.set_under("white")
    sns.heatmap(crosstab, annot=True, fmt="d", cmap=custom_cmap, vmin=0.5, ax=ax)