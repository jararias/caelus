from typing import Literal

import numpy as np
import pandas as pd
import polars as po
from loguru import logger

from . import filters, options, sky_indices
from .helpers import ensure_tz_aware_datetime_index
from .skytype import SkyType, _ordered_labels

logger.disable(__name__)
logger = logger.opt(colors=True)

REQUIRED_TO_CLASSIFY = {"ghi", "ghics"}


def classify(
    data: pd.DataFrame,
    latitude: float,
    longitude: float,
    engine: Literal["pandas", "polars"] = "polars",
    apply_filters: bool = True,
    categorical: bool = False,
    full_output: bool = False,
):
    """
    Classifies a 1-min GHI time series into the following six sky types: overcast,
    thick clouds, scattered clouds, thin clouds, cloudless or cloud enhancement. If
    the classification is not possible (e.g., when sza > 85 degrees) a special type
    `unknown` is used. See the SkyType class to see the integer labels of each sky
    type. It only works for sza > 85.

    Parameters:
    -----------

    data: Pandas DataFrame
      the 1-min input time series. The DataFrame must contain: global horizontal
      irradiance (`ghi`, in W/m2) and clear sky global horizontal solar irradiance
      (`ghics`, in W/m2).

    latitude: float(-90, 90)
      site's latitude

    longitude: float[-180, 180]
      site's longitude

    engine: str
      library used to perform the classification (polars or pandas). polars is
      much faster. Default: polars

    apply_filters: bool
      revise the sky classification to remove potential unrealistic assignments

    categorical: bool
      if True, the output column `sky_type` is returned as a categorical variable with
      self-describing categories (`UNKNOWN`, `OVERCAST`, `THICK_CLOUDS`, `SCATTERED_CLOUDS`,
      `THIN_CLOUDS`, `CLOUDLESS`, `CLOUD_ENHANCEMENT`). If False, it is returned as integer
      from 1 to 7.

    full_output: bool
      output data internally used to compute the sky type

    Returns:
    --------

    A Pandas DataFrame.

    The column `sky_type` contains the integer label for each sky type class. The label
    is directly traceable to the members of the SkyType class. Additionally, it may contain
    other columns (see the `full_output` input argument)

    """
    import sunwhere
    from spartasolar.atmosphere import merra2_cda

    if missing := list(REQUIRED_TO_CLASSIFY.difference(data.columns)):
        raise ValueError(f"missing required variables: {', '.join(missing)}")

    if engine not in ("pandas", "polars"):
        raise ValueError(f"expected engine in ['pandas', 'polars']. Got {engine=}")
    logger.info(f"using <red>{engine=}</red>")

    if not (-90.0 < latitude < 90.0):
        raise ValueError(f"{latitude=} out of bounds")

    if not (-180 <= longitude <= 180):
        raise ValueError(f"{longitude=} out of bounds")

    # ensure data_ index is tz-aware
    data_ = data.set_index(ensure_tz_aware_datetime_index(data.index)).copy()
    # remove missing timestamps by filling with nans
    time_step = (data_.index[1:] - data_.index[:-1]).unique().min()
    dense_times = pd.date_range(
        start=data_.index[0], end=data_.index[-1], freq=time_step, tz=data_.index.tz, inclusive="both"
    )
    dense_data = data_.reindex(dense_times)

    solpos = sunwhere.sites(times=dense_data.index, latitude=latitude, longitude=longitude)
    sza = solpos.sza.isel(site=0).to_pandas()
    csky_cda = merra2_cda.at_sites(times=dense_data.index, latitude=latitude, longitude=longitude).compute()

    # push all required data together in a pandas dataframe
    dense_data = dense_data.assign(
        sza=sza,
        daytime=sza <= options.MAX_SZA,
        cosz=solpos.cosz.isel(site=0).to_pandas(),
        tst=solpos.true_solar_time.isel(site=0).to_pandas(),
        ghicda=csky_cda.ghi.isel(site=0).to_pandas(),
    )

    result = _classify_from_ensured_dataframe(
        dense_data,
        engine=engine,
        apply_filters=apply_filters,
        categorical=categorical,
        full_output=full_output
    )

    # keep only the original timestamps
    result = result.reindex(data_.index)

    # restore original index, in particular, if it was tz-naive
    result.index = data.index

    return result

def _classify_from_ensured_dataframe(
    data: pd.DataFrame, engine: str, apply_filters: bool, categorical: bool, full_output: bool
) -> pd.DataFrame:

    mirror_ghi = False  # with True, polars and pandas differ. This is under investigation.
    # For now, I set it to False to ensure consistency between engines because this option
    # is not very much important. It only affects timestamps near the horizon.

    if engine == "pandas":
        df_indices = sky_indices.calculate_with_pandas(data, mirror_ghi=mirror_ghi)
        sky_type = sky_indices.classify_with_pandas(df_indices, full_output=full_output)
        if apply_filters:
            sky_type = filters.apply(sky_type, df_indices, full_output=full_output)

    else:  # polars
        # pandas to polars...
        df = po.from_pandas(data.rename_axis("times_utc", axis=0), include_index=True)

        df_indices = sky_indices.calculate_with_polars(df, mirror_ghi=mirror_ghi)
        sky_type = sky_indices.classify_with_polars(df_indices, full_output=full_output)
        if apply_filters:
            sky_type = filters.apply(sky_type, df_indices, full_output=full_output)

        # polars to pandas...
        df_indices = df_indices.to_pandas().set_index("times_utc").rename_axis(data.index.name, axis=0)
        sky_type = sky_type.to_pandas().set_index("times_utc").rename_axis(data.index.name, axis=0)
        if not full_output:
            sky_type = sky_type["sky_type"]

    sky_type = sky_type.astype(np.int8).rename("sky_type")

    try:
        sky_type = sky_type.asfreq(pd.infer_freq(sky_type.index))
    except Exception:
        sky_type = sky_type.asfreq(None)

    if categorical:
        sky_type = sky_type.map(lambda number: SkyType(number).name).astype("category")
        sky_type = sky_type.cat.set_categories(_ordered_labels, ordered=True)

    if full_output:
        return sky_type.join(df_indices).assign(engine=engine)
    return sky_type
