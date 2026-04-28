
import numpy as np
import pandas as pd
import polars as po
import sunwhere
from loguru import logger
from pysparta import SPARTA

from . import options, sky_indices, filters
from .skytype import SkyType


logger.disable(__name__)
logger = logger.opt(colors=True)

REQUIRED_TO_CLASSIFY = {"ghi", "ghics"}


def classify(
    data: pd.DataFrame,
    latitude: float,
    longitude: float,
    engine: str = "polars",
    apply_filters:  bool = True,
    full_output: bool = False
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
      irradiance (ghi, in W/m2) and clear sky global horizontal solar irradiance
      (ghics, in W/m2). It _must_ have a DatetimeIndex in UTC.

    latitude: float(-90, 90)
      site's latitude

    longitude: float[-180, 180]
      site's longitude

    engine: str
      library used to perform the classification (polars or pandas). polars is
      much faster. Default: polars

    apply_filters: bool
      revise the sky classification to remove potential unrealistic assignments

    full_output: bool
      output data internally used to compute the sky type

    Returns:
    --------

    A Pandas DataFrame.

    The column `sky_type` contains the integer label for each sky type class. The label
    is directly traceable to the members of the SkyType class. Additionally, it may contain
    other columns (see the `full_output` input argument)

    """

    mirror_ghi = False  # <<<<<< TODO

    if missing := list(REQUIRED_TO_CLASSIFY.difference(data.columns)):
        raise ValueError(f"missing required variables: {', '.join(missing)}")

    if not (-90. < latitude < 90.):
        raise ValueError(f"{latitude=} out of bounds")

    if not (-180 <= longitude <= 180):
        raise ValueError(f"{longitude=} out of bounds")

    if engine not in ("pandas", "polars"):
        raise ValueError(f"expected engine in ['pandas', 'polars']. Got {engine=}")
    logger.info(f"using <red>{engine=}</red>")

    # ensure dense dataframe...
    time_step = (data.index[1:] - data.index[:-1]).unique().min()
    dense_times = pd.date_range(data.index[0], data.index[-1], freq=time_step, inclusive="both")
    dense_data = data[["ghi", "ghics"]].reindex(dense_times)

    # I am assuming that data.index is a naive pd.DatetimeIndex in UTC!
    solpos = sunwhere.sites(times=dense_data.index, latitude=latitude, longitude=longitude)
    sza = solpos.sza.isel(location=0).to_pandas()

    csky = SPARTA(times=dense_data.index, sites={"latitude": latitude, "longitude": longitude}, atmos="merra2_cda")

    # push all required data together in a pandas dataframe
    dense_data = dense_data.assign(
        sza=sza,
        daytime=sza <= options.MAX_SZA,
        cosz=solpos.cosz.isel(location=0).to_pandas(),
        tst=solpos.true_solar_time.isel(location=0).to_pandas(),
        ghicda=csky.ghi.isel(location=0).to_pandas(),
    )

    if engine == "pandas":

        df_indices = sky_indices.calculate_with_pandas(dense_data, mirror_ghi=mirror_ghi)
        sky_type = sky_indices.classify_with_pandas(df_indices, full_output=full_output)
        if apply_filters:
            sky_type = filters.apply(sky_type, df_indices, full_output=full_output)

    else:  # polars

        # pandas to polars...
        df = po.from_pandas(dense_data.rename_axis("times_utc", axis=0), include_index=True)

        df_indices = sky_indices.calculate_with_polars(df, mirror_ghi=mirror_ghi)
        sky_type = sky_indices.classify_with_polars(df_indices, full_output=full_output)
        if apply_filters:
            sky_type = filters.apply(sky_type, df_indices, full_output=full_output)

        # polars to pandas...
        df_indices = df_indices.to_pandas().set_index("times_utc").rename_axis(dense_data.index.name, axis=0)
        sky_type = sky_type.to_pandas().set_index("times_utc").rename_axis(dense_data.index.name, axis=0)
        if not full_output:
            sky_type = sky_type["sky_type"]

    if full_output:
        return sky_type.join(df_indices).assign(engine=engine)
    return sky_type
