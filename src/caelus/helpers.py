
import copy
from typing import Any, Sequence

import pandas as pd


def ensure_tz_aware_datetime_index(times: Any, utc: bool = False) -> pd.DatetimeIndex:
    """Return a timezone-aware DatetimeIndex from arbitrary time-like input.

    Parameters
    ----------
    times : Any
        Scalar, sequence, or pandas time-like object.
    utc : bool, default False
        If ``True``, convert the resulting index to UTC.

    Returns
    -------
    pd.DatetimeIndex
        Time index guaranteed to be timezone-aware.
    """
    times_dti = copy.deepcopy(times)

    # 1. convert to DatetimeIndex, if not already
    if not isinstance(times_dti, pd.DatetimeIndex):
        if isinstance(times, str) or not isinstance(times, Sequence):
            times_dti = [times_dti]
        times_dti = pd.to_datetime(times_dti)

    # 2. ensure tz-aware, if not already
    if times_dti.tz is None:
        times_dti = times_dti.tz_localize("UTC")

    # 3. convert to UTC, if requested
    if utc:
        return times_dti.tz_convert("UTC")
    return times_dti