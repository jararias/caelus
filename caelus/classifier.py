
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

from loguru import logger

from . import options
from .skytype import SkyType
from .filters import (
    clean_spurious_sky_patches,
    clean_scatter_clouds_flanked_by_thin_clouds,
    clean_cloudless_to_thin_clouds_transitions,
    clean_thin_clouds_to_scatter_clouds_transitions
)


logger.disable(__name__)


def classify(data, enable_ghi_mirroring=True, full_output=False):
    """
    Classifies a 1-min GHI time series into the following six sky types: overcast,
    thick clouds, scattered clouds, thin clouds, cloudless or cloud enhancement. If
    the classification is not possible (e.g., when sza > 85 degrees) a special type
    `unknown` is used. See the SkyType class to see the integer labels of each sky
    type. It only works for sza > 85.

    Parameters:
    -----------

    data: Pandas DataFrame
      the 1-min input time series. The DataFrame must contain: solar zenith angle
      (sza, in degrees), extraterrestrial horizontal solar irradiance (eth, in W/m2),
      global horizontal irradiance (ghi, in W/m2), clear sky global horizontal solar
      irradiance (ghics, in W/m2), and clean-and-dry atmosphere global horizontal
      solar irradiance (ghicda, in W/m2)

    enable_ghi_mirroring: bool
      extrapolation of ghi data beyond sunrise and sunset to mitigate border effects
      in the classification for low sun altitudes

    full_output: bool
      when set to False, the output DataFrame only has the column `sky_type` with the
      classification results. When set to True, it has additional columns with internal
      variability indices used during the classification process.

    Returns:
    --------

    A Pandas DataFrame.

    The column `sky_type` contains the integer label for each sky type class. The label
    is directly traceable to the members of the SkyType class. Additionally, it may contain
    other columns (see the `full_output` input argument)

    """

    required = ['sza', 'eth', 'ghi', 'ghics', 'ghicda']
    if missing := list(set(required).difference(data.columns)):
        raise ValueError(f'missing required variables: {", ".join(missing)}')

    if enable_ghi_mirroring is True:
        if 'longitude' not in data.columns:
            raise ValueError('missing required variable: longitude')

    daytime = data['sza'] <= options.MAX_SZA

    Kcs = (data['ghi'].divide(data['ghics'])
           .where(data['sza'] < 87., np.nan).clip(0.))

    ghi = data.ghi
    if enable_ghi_mirroring is True:
        ghi = ghi_mirroring(data)

    mean_ghi = ghi.rolling(options.DT, center=True).mean()
    Km = mean_ghi.divide(data['ghicda']).where(daytime, np.nan).clip(0.)

    Kv = (
        (ghi - mean_ghi).diff().abs().rolling(options.DT, center=True)
        .sum()/pd.Timedelta(options.DT).total_seconds()
    )

    Kvf = (
        (ghi - mean_ghi).diff().abs().rolling(options.DT_F, center=True)
        .sum()/pd.Timedelta(options.DT_F).total_seconds()
    )

    # Thresholding...

    sza = data['sza']
    clouden = (
        (
            daytime &
            (sza < 80.) &
            (Kcs > options.CLOUDEN_MIN_KCS) &
            (Kv > options.CLOUDEN_MIN_KV) & (Kvf > options.CLOUDEN_MIN_KVF)
        )
    )

    cloudless = (
        (
            daytime &
            (sza < 75.) &
            (Km > options.CLOUDLESS_MIN_KM) &
            (Kcs > options.CLOUDLESS_MIN_KCS) & (Kcs < options.CLOUDLESS_MAX_KCS) &
            (Kv < options.CLOUDLESS_MAX_KV)
        ) |
        (
            daytime &
            (sza >= 75.) &
            (Km > options.CLOUDLESS_MIN_KM) &
            (Kcs > 0.80) & (Kcs < 1.20) &
            (Kv < options.CLOUDLESS_MAX_KV)
        )
    )

    overcast = (
        daytime &
        (Km < options.OVERCAST_MAX_KM) &
        (Kv < options.OVERCAST_MAX_KV)
    )

    cloudy = daytime & ~cloudless & ~overcast & ~clouden

    thinclouds = (
        cloudy &
        (Km > options.THINCLOUDS_MIN_KM) &
        (Kv >= options.THINCLOUDS_MIN_KV) & (Kv < options.THINCLOUDS_MAX_KV)
    )

    thickclouds = (
        cloudy &
        (Km < options.THICKCLOUDS_MAX_KM) &
        (Kv >= options.THICKCLOUDS_MIN_KV) & (Kv < options.THICKCLOUDS_MAX_KV)
    )

    scatterclouds = cloudy & ~thickclouds & ~thinclouds

    sky_type = pd.Series(
        index=data.index,
        data=SkyType.UNKNOWN,
        name='sky_type'
    )

    sky_type.loc[overcast] = SkyType.OVERCAST
    sky_type.loc[thickclouds] = SkyType.THICK_CLOUDS
    sky_type.loc[scatterclouds] = SkyType.SCATTER_CLOUDS
    sky_type.loc[thinclouds] = SkyType.THIN_CLOUDS
    sky_type.loc[cloudless] = SkyType.CLOUDLESS
    sky_type.loc[clouden] = SkyType.CLOUD_ENHANCEMENT

    # clean the sky classification...

    if options.CLEAN_SPURIOUS_SKY_PATCHES is True:
        sky_type.loc[:] = clean_spurious_sky_patches(
            sky_type, min_sky_patch_len=15, max_iter=50
        )

    if options.CLEAN_SCATTER_CLOUDS_FLANKED_BY_THIN_CLOUDS is True:
        sky_type.loc[:] = clean_scatter_clouds_flanked_by_thin_clouds(
            sky_type, options.DT, sza, Km, Kv
        )

    if options.CLEAN_CLOUDLESS_TO_THIN_CLOUDS_TRANSITIONS is True:
        sky_type.loc[:] = clean_cloudless_to_thin_clouds_transitions(
            sky_type, Kv
        )

    if options.CLEAN_THIN_CLOUDS_TO_SCATTER_CLOUDS_TRANSITIONS is True:
        sky_type.loc[:] = clean_thin_clouds_to_scatter_clouds_transitions(
            sky_type, Kv
        )

    sky_type.loc[~daytime] = SkyType.UNKNOWN
    sky_type.loc[data['ghi'].isna()] = SkyType.UNKNOWN

    sky_type = sky_type.astype(int)

    if full_output is True:
        sky_type = sky_type.to_frame(name='sky_type')
        sky_type['Km'] = Km
        sky_type['Kv'] = Kv
        sky_type['Kvf'] = Kvf
    return sky_type


def ghi_mirroring(data):

    def true_solar_time(times_utc, longitude):
        # eq. of time
        doy = (times_utc.day_of_year.astype(float) +
            (times_utc.hour + (times_utc.minute + times_utc.second/60)/60)/24)
        n_days = pd.Series(index=times_utc, data=366.).where(times_utc.is_leap_year, 365.)
        angle = (2.*np.pi / n_days) * doy
        # this is a fit to match the NREL's SPA equation of time
        eot = (0.00986571
            + 0.58688718*np.cos(  angle) - 7.34538133*np.sin(  angle)
            - 3.31493999*np.cos(2*angle) - 9.35366541*np.sin(2*angle)    
            - 0.08151750*np.cos(3*angle) - 0.30892409*np.sin(3*angle)
            - 0.13532889*np.cos(4*angle) - 0.17336220*np.sin(4*angle))  # minutes

        dt64_s = np.datetime64(1, 's')
        utc_f = np.array(times_utc, dtype=dt64_s).astype('float64')
        tst_f = utc_f + (4. * longitude + eot) * 60.
        return pd.to_datetime(np.array(tst_f, dtype=dt64_s))

    def interpolate(xi, yi, x):
        kwargs = dict(kind='linear', bounds_error=False, fill_value=np.nan)
        return interp1d(xi, yi, **kwargs)(x)

    required = ['sza', 'longitude', 'ghi']
    if missing := list(set(required).difference(data.columns)):
        raise ValueError(f'missing required variables: {", ".join(missing)}')

    ghi = data['ghi']
    ghi_mirror = ghi.copy()
    cosz = pd.Series(index=ghi.index, data=np.cos(np.radians(data['sza'])))
    tst = pd.Series(
        index=ghi.index, data=true_solar_time(ghi.index, data['longitude']))

    for (_, this_ghi) in ghi.groupby(tst.dt.date):

        this_cosz = cosz.loc[this_ghi.index]
        daytime = this_cosz > 0
        nighttime = this_cosz <= 0
        am = tst.loc[this_ghi.index].dt.hour < 12
        pm = tst.loc[this_ghi.index].dt.hour >= 12

        # fill gaps shorter than DT to improve the rolling averages
        this_ghi_filled = this_ghi.interpolate(
            'time', limit=pd.Timedelta(4, 'H').seconds // 60)
        this_ghi_filled.loc[nighttime] = np.nan

        if len(this_cosz.loc[am & daytime]):
            this_ghi_filled.loc[am & nighttime] = -interpolate(
                this_cosz.loc[am & daytime],
                this_ghi_filled.loc[am & daytime],
                -this_cosz.loc[am & nighttime]
            )

        if len(this_cosz.loc[pm & daytime]):
            this_ghi_filled.loc[pm & nighttime] = -interpolate(
                this_cosz.loc[pm & daytime],
                this_ghi_filled.loc[pm & daytime],
                -this_cosz.loc[pm & nighttime]
            )

        ghi_mirror.loc[this_ghi.index] = this_ghi_filled

    return ghi_mirror
