
import numpy as np
import pandas as pd
import polars as po
from loguru import logger

from . import options
from .skytype import SkyType

logger.disable(__name__)
logger = logger.opt(colors=True)


def calculate_with_pandas(data: pd.DataFrame, mirror_ghi: bool = True) -> pd.DataFrame:

    data = data.assign(
        Kcs=data["ghi"].divide(data["ghics"]).where(data["sza"] < 87., np.nan).clip(0.),
        ghi_mirrored=mirror_ghi_with_pandas(data) if mirror_ghi else data["ghi"],
    )

    data = data.assign(
        mean_ghi=data["ghi_mirrored"].rolling(options.DT, center=True).mean(),
    )

    data = data.assign(
        Km=data["mean_ghi"].divide(data["ghicda"]).where(data["daytime"], np.nan).clip(0.),
        diff_abs=(data["ghi_mirrored"] - data["mean_ghi"]).diff().abs(),
    )

    data = data.assign(
        Kv=data["diff_abs"].rolling(options.DT, center=True).sum()/pd.Timedelta(options.DT).total_seconds(),
        Kvf=data["diff_abs"].rolling(options.DT_F, center=True).sum()/pd.Timedelta(options.DT_F).total_seconds(),
    )

    return data.drop(columns=["diff_abs", "ghi_mirrored"])


def mirror_ghi_with_pandas(data: pd.DataFrame) -> pd.Series:
    from scipy.interpolate import interp1d

    logger.info("with mirrored ghi")

    ghi = data["ghi"]
    cosz = data["cosz"]
    tst = data["tst"]

    ghi_mirror = ghi.copy()

    def interpolate(xi, yi, x):
        kwargs = {"kind": "linear", "bounds_error": False, "fill_value": np.nan}
        return interp1d(xi, yi, **kwargs)(x)

    for _, this_ghi in ghi.groupby(tst.dt.date):

        this_cosz = cosz.loc[this_ghi.index]
        daytime = this_cosz > 0
        nighttime = this_cosz <= 0
        am = tst.loc[this_ghi.index].dt.hour < 12
        pm = tst.loc[this_ghi.index].dt.hour >= 12

        # fill gaps shorter than DT to improve the rolling averages
        this_ghi_filled = this_ghi # this_ghi.interpolate("time", limit=pd.Timedelta(4, "h").seconds // 60)
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


def classify_with_pandas(data: pd.DataFrame, full_output: bool = False) -> pd.Series | pd.DataFrame:

    clouden = (
        (
            data["daytime"] &
            (data["sza"] < 80.) &
            (data["Kcs"] > options.CLOUDEN_MIN_KCS) &
            (data["Kv"] > options.CLOUDEN_MIN_KV) &
            (data["Kvf"] > options.CLOUDEN_MIN_KVF)
        )
    )

    cloudless = (
        (
            data["daytime"] &
            (data["sza"] < 75.) &
            (data["Km"] > options.CLOUDLESS_MIN_KM) &
            (data["Kcs"] > options.CLOUDLESS_MIN_KCS) &
            (data["Kcs"] < options.CLOUDLESS_MAX_KCS) &
            (data["Kv"] < options.CLOUDLESS_MAX_KV)
        ) |
        (
            data["daytime"] &
            (data["sza"] >= 75.) &
            (data["Km"] > options.CLOUDLESS_MIN_KM) &
            (data["Kcs"] > 0.80) &
            (data["Kcs"] < 1.20) &
            (data["Kv"] < options.CLOUDLESS_MAX_KV)
        )
    )

    overcast = (
        data["daytime"] &
        (data["Km"] < options.OVERCAST_MAX_KM) &
        (data["Kv"] < options.OVERCAST_MAX_KV)
    )

    cloudy = data["daytime"] & ~cloudless & ~overcast & ~clouden

    thinclouds = (
        cloudy &
        (data["Km"] > options.THINCLOUDS_MIN_KM) &
        (data["Kv"] >= options.THINCLOUDS_MIN_KV) &
        (data["Kv"] < options.THINCLOUDS_MAX_KV)
    )

    thickclouds = (
        cloudy &
        (data["Km"] < options.THICKCLOUDS_MAX_KM) &
        (data["Kv"] >= options.THICKCLOUDS_MIN_KV) &
        (data["Kv"] < options.THICKCLOUDS_MAX_KV)
    )

    scatterclouds = cloudy & ~thickclouds & ~thinclouds

    sky_type = pd.Series(
        index=data.index,
        data=SkyType.UNKNOWN,
        name="sky_type"
    )

    sky_type.loc[overcast] = SkyType.OVERCAST
    sky_type.loc[thickclouds] = SkyType.THICK_CLOUDS
    sky_type.loc[scatterclouds] = SkyType.SCATTER_CLOUDS
    sky_type.loc[thinclouds] = SkyType.THIN_CLOUDS
    sky_type.loc[cloudless] = SkyType.CLOUDLESS
    sky_type.loc[clouden] = SkyType.CLOUD_ENHANCEMENT

    isna = data["ghi"].isna() | data["Km"].isna() | data["Kv"].isna() | data["Kvf"].isna()
    sky_type.loc[isna] = SkyType.UNKNOWN

    if full_output:
        return pd.concat([
            clouden.rename("clouden"),
            cloudless.rename("cloudless"),
            cloudy.rename("cloudy"),
            scatterclouds.rename("scatterclouds"),
            thinclouds.rename("thinclouds"),
            thickclouds.rename("thickclouds"),
            overcast.rename("overcast"),
            sky_type.rename("sky_type")
        ], axis=1)

    return sky_type


def calculate_with_polars(data: po.DataFrame, mirror_ghi: bool = True) -> po.DataFrame:

    def rolling(column: str, size: int, reduce: str = "mean") -> po.Expr:
        # pandas y polars usan dos estrategias diferentes a la hora de centrar el intervalo
        # del metodo rolling cuando se usa el argumento center=True. Para replicar los resultados
        # de pandas con polars tengo que hacer center=False y aplicar el offset por mi mismo
        # usando el metodo shift
        offset = - (size // 2)
        kwargs = {"window_size": size, "min_samples": 1, "center": False}
        return getattr(po.col(column), f"rolling_{reduce}")(**kwargs).shift(offset)

    one_minute = pd.Timedelta("1min")

    dt_coarse = pd.Timedelta(options.DT)
    dt_coarse_seconds = dt_coarse.total_seconds()
    coarse_window_size = int(dt_coarse // one_minute)

    dt_fine = pd.Timedelta(options.DT_F)
    dt_fine_seconds = dt_fine.total_seconds()
    fine_window_size = int(dt_fine // one_minute)

    return data.with_columns(
        Kcs=po.when(po.col("sza") < 87.).then(po.col("ghi") / po.col("ghics")).otherwise(None).clip(lower_bound=0.),
        ghi_mirrored=mirror_ghi_with_polars(data) if mirror_ghi else po.col("ghi")
    ).with_columns(
        mean_ghi=rolling("ghi_mirrored", coarse_window_size, "mean")
    ).with_columns(
        Km=po.when(po.col("daytime")).then(po.col("mean_ghi") / po.col("ghicda")).otherwise(None).clip(lower_bound=0),
        diff_abs=(po.col("ghi_mirrored") - po.col("mean_ghi")).diff().abs()
    ).with_columns(
        Kv=rolling("diff_abs", coarse_window_size, "sum") / dt_coarse_seconds,
        Kvf=rolling("diff_abs", fine_window_size, "sum") / dt_fine_seconds
    ).drop(["diff_abs", "ghi_mirrored"]) # columnas temporales


# def mirror_ghi_with_polars(df: po.DataFrame) -> po.Series:

#     def process_day(group: po.DataFrame) -> po.DataFrame:

#         # máscaras. Usamos numpy para scipy.interpolate.interp1d
#         cosz = group.get_column("cosz").to_numpy()
#         daytime = cosz > 0.
#         nighttime = ~daytime
#         hours = group.get_column("tst").dt.hour().to_numpy()
#         am = hours < 12
#         pm = hours >= 12

#         # # 1. Interpolación temporal simple para huecos cortos (limit=4h)
#         # # Polars no tiene interpolate(limit=...), usamos pandas para esta parte específica
#         # # o lo manejamos con una serie temporal de Polars si es necesario.
#         # # Aquí asumimos que ya viene pre-procesado o usamos un helper.
#         # s_ghi = group.select(
#         #     po.col("ghi").interpolate().alias("filled")
#         # ).get_column("filled").to_numpy()

#         s_ghi = group.get_column("ghi").to_numpy()
#         s_ghi[nighttime] = np.nan

#         # Función auxiliar de interpolación
#         def apply_mirror(mask_day, mask_night):
#             if mask_day.any() and mask_night.any():
#                 xi = cosz[mask_day]
#                 yi = s_ghi[mask_day]
#                 # Eliminamos NaNs para que interp1d no falle
#                 valid = ~np.isnan(yi) & ~np.isnan(xi)
#                 if valid.any():
#                     f = interp1d(xi[valid], yi[valid], kind="linear", 
#                                  bounds_error=False, fill_value=np.nan)
#                     # El mirroring usa -cosz para el lado nocturno
#                     s_ghi[mask_night] = -f(-cosz[mask_night])

#         # 2. Mirroring AM y PM
#         apply_mirror(am & daytime, am & nighttime)
#         apply_mirror(pm & daytime, pm & nighttime)

#         return group.with_columns(ghi_mirror=po.Series(s_ghi))

#     # Aplicamos la lógica por grupo de fecha
#     result = (
#         df.with_columns(date = po.col("tst").dt.date())
#         .group_by("date", maintain_order=True)
#         .map_groups(process_day)
#     )
    
#     return result.get_column("ghi_mirror")


def mirror_ghi_with_polars(data: po.DataFrame) -> po.Series:

    logger.info("with mirrored ghi")

    # 1. Creamos las columnas base y condiciones lógicas iniciales
    df_processed = data.with_columns([
        po.col("tst").dt.date().alias("date"),
        po.col("tst").dt.hour().alias("hour"),
        (po.col("cosz") > 0).alias("daytime"),
        (po.col("cosz") <= 0).alias("nighttime"),
    ]).with_columns([
        (po.col("hour") < 12).alias("am"),
        (po.col("hour") >= 12).alias("pm"),
        # Se anula GHI en la noche (this_ghi_filled.loc[nighttime] = np.nan)
        po.when(po.col("nighttime")).then(None).otherwise(po.col("ghi")).alias("ghi_filled")
    ])

    # 2. Función interna que procesará cada día (grupo) de forma eficiente
    def process_day(day_df: po.DataFrame) -> po.DataFrame:
        # Extraemos arrays de numpy para la interpolación (Operación en memoria ultra rápida)
        cosz = day_df["cosz"].to_numpy()
        ghi_filled = day_df["ghi_filled"].to_numpy()
        
        am = day_df["am"].to_numpy()
        pm = day_df["pm"].to_numpy()
        daytime = day_df["daytime"].to_numpy()
        nighttime = day_df["nighttime"].to_numpy()

        # Máscaras combinadas
        am_daytime = am & daytime
        am_nighttime = am & nighttime
        pm_daytime = pm & daytime
        pm_nighttime = pm & nighttime

        # Copia para rellenar el "espejo"
        ghi_mirror = ghi_filled.copy()

        # Interpolación AM
        if np.any(am_daytime) and np.any(am_nighttime):
            # numpy.interp requiere que el eje X (cosz) esté ordenado de forma ascendente
            sort_idx = np.argsort(cosz[am_daytime])
            xi = cosz[am_daytime][sort_idx]
            yi = ghi_filled[am_daytime][sort_idx]
            
            # Evaluamos en -cosz de la noche y guardamos el negativo del resultado
            interp_vals = np.interp(-cosz[am_nighttime], xi, yi, left=np.nan, right=np.nan)
            ghi_mirror[am_nighttime] = -interp_vals

        # Interpolación PM
        if np.any(pm_daytime) and np.any(pm_nighttime):
            sort_idx = np.argsort(cosz[pm_daytime])
            xi = cosz[pm_daytime][sort_idx]
            yi = ghi_filled[pm_daytime][sort_idx]
            
            interp_vals = np.interp(-cosz[pm_nighttime], xi, yi, left=np.nan, right=np.nan)
            ghi_mirror[pm_nighttime] = -interp_vals

        # Devolvemos una serie temporal polars con el resultado
        return po.DataFrame({"ghi_mirror": ghi_mirror})

    # 3. Aplicamos el procesamiento por día en paralelo usando group_by
    # Maintain_order garantiza que el resultado no se desordene
    result_df = df_processed.group_by("date", maintain_order=True).map_groups(process_day)

    return result_df["ghi_mirror"]


def classify_with_polars(df: po.DataFrame, full_output: bool = False) -> po.DataFrame:

    is_clouden = (
        po.col("daytime") &
        (po.col("sza") < 80.0) &
        (po.col("Kcs") > options.CLOUDEN_MIN_KCS) &
        (po.col("Kv") > options.CLOUDEN_MIN_KV) & 
        (po.col("Kvf") > options.CLOUDEN_MIN_KVF)
    )

    is_cloudless = (
        (
            po.col("daytime") &
            (po.col("sza") < 75.0) & 
            (po.col("Km") > options.CLOUDLESS_MIN_KM) & 
            (po.col("Kcs") > options.CLOUDLESS_MIN_KCS) &
            (po.col("Kcs") < options.CLOUDLESS_MAX_KCS) & 
            (po.col("Kv") < options.CLOUDLESS_MAX_KV)
        ) |
        (
            po.col("daytime") &
            (po.col("sza") >= 75.0) & 
            (po.col("Km") > options.CLOUDLESS_MIN_KM) & 
            (po.col("Kcs") > 0.80) &
            (po.col("Kcs") < 1.20) & 
            (po.col("Kv") < options.CLOUDLESS_MAX_KV)
        )
    )

    is_overcast = (
        po.col("daytime") &
        (po.col("Km") < options.OVERCAST_MAX_KM) &
        (po.col("Kv") < options.OVERCAST_MAX_KV)
    )

    is_cloudy = po.col("daytime") & ~is_cloudless & ~is_overcast & ~is_clouden

    is_thinclouds = (
        is_cloudy &
        (po.col("Km") > options.THINCLOUDS_MIN_KM) &
        (po.col("Kv") >= options.THINCLOUDS_MIN_KV) & 
        (po.col("Kv") < options.THINCLOUDS_MAX_KV)
    )

    is_thickclouds = (
        is_cloudy &
        (po.col("Km") < options.THICKCLOUDS_MAX_KM) &
        (po.col("Kv") >= options.THICKCLOUDS_MIN_KV) & 
        (po.col("Kv") < options.THICKCLOUDS_MAX_KV)
    )
    
    is_scatterclouds = is_cloudy & ~is_thickclouds & ~is_thinclouds

    mask = po.col("ghi").is_null() | po.col("Km").is_null() | po.col("Kv").is_null() | po.col("Kvf").is_null()

    sky_type = df.with_columns(
        po.when(is_overcast).then(SkyType.OVERCAST)
        .when(is_thickclouds).then(SkyType.THICK_CLOUDS)
        .when(is_scatterclouds).then(SkyType.SCATTER_CLOUDS)
        .when(is_thinclouds).then(SkyType.THIN_CLOUDS)
        .when(is_cloudless).then(SkyType.CLOUDLESS)
        .when(is_clouden).then(SkyType.CLOUD_ENHANCEMENT)
        .otherwise(SkyType.UNKNOWN)
        .alias("sky_type")
    ).select(
        po.col("times_utc"),
        sky_type=po.when(mask).then(SkyType.UNKNOWN).otherwise(po.col("sky_type"))
    )

    if full_output:

        sky_flags = df.select(
            po.col("times_utc"),
            clouden=is_clouden,
            cloudless=is_cloudless,
            cloudy=is_cloudy,
            scatterclouds=is_scatterclouds,
            thinclouds=is_thinclouds,
            thickclouds=is_thickclouds,
            overcast=is_overcast,
        )

        sky_type = po.concat([sky_flags, sky_type], how="align")

    return sky_type
