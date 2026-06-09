
import functools

import numpy as np
import pandas as pd
import polars as po
from loguru import logger

from . import options
from .skytype import SkyType

logger.disable(__name__)
logger = logger.opt(colors=True)


@functools.singledispatch
def apply(sky_type, df_indices, full_output) -> pd.Series | po.DataFrame:
    raise NotImplementedError(f"apply not implemented for sky_type of type {type(sky_type)}")


@apply.register
def _(sky_type: pd.Series | pd.DataFrame, df_indices: pd.DataFrame, full_output: bool = True) -> pd.Series:

    if options.CLEAN_SPURIOUS_SKY_PATCHES:
        kwargs = {"min_sky_patch_len": 15, "max_iter": 50}
        if full_output:
            sky_type.loc[:, "sky_type"] = clean_spurious_sky_patches_with_pandas(sky_type["sky_type"], **kwargs)
        else:
            sky_type.loc[:] = clean_spurious_sky_patches_with_pandas(sky_type, **kwargs)

    if options.CLEAN_SCATTER_CLOUDS_FLANKED_BY_THIN_CLOUDS:
        if full_output:
            sky_type.loc[:, "sky_type"] = clean_scatter_clouds_flanked_by_thin_clouds_with_pandas(
                sky_type["sky_type"], df_indices)
        else:
            sky_type.loc[:] = clean_scatter_clouds_flanked_by_thin_clouds_with_pandas(sky_type, df_indices)

    if options.CLEAN_CLOUDLESS_TO_THIN_CLOUDS_TRANSITIONS:
        if full_output:
            sky_type.loc[:, "sky_type"] = clean_cloudless_to_thin_clouds_transitions_with_pandas(
                sky_type["sky_type"], df_indices)
        else:
            sky_type.loc[:] = clean_cloudless_to_thin_clouds_transitions_with_pandas(sky_type, df_indices)

    if options.CLEAN_THIN_CLOUDS_TO_SCATTER_CLOUDS_TRANSITIONS:
        if full_output:
            sky_type.loc[:, "sky_type"] = clean_thin_clouds_to_scatter_clouds_transitions_with_pandas(
                sky_type["sky_type"], df_indices)
        else:
            sky_type.loc[:] = clean_thin_clouds_to_scatter_clouds_transitions_with_pandas(sky_type, df_indices)

    mask = df_indices[["ghi", "Km", "Kv", "Kvf"]].isna().any(axis=1)
    if full_output:
        sky_type.loc[mask, "sky_type"] = SkyType.UNKNOWN
    else:
        sky_type.loc[mask] = SkyType.UNKNOWN

    return sky_type


@apply.register
def _(sky_type: po.DataFrame, df_indices: po.DataFrame, full_output: bool = True) -> po.DataFrame:

    if options.CLEAN_SPURIOUS_SKY_PATCHES:
        kwargs = {"min_sky_patch_len": 15, "max_iter": 50}
        if full_output:
            sky_type = sky_type.with_columns(
                sky_type=clean_spurious_sky_patches_with_polars(
                    sky_type.select(po.col("times_utc", "sky_type")), **kwargs)["sky_type"]
            )
        else:
            sky_type = clean_spurious_sky_patches_with_polars(sky_type, **kwargs)

    if options.CLEAN_SCATTER_CLOUDS_FLANKED_BY_THIN_CLOUDS:
        if full_output:
            sky_type = sky_type.with_columns(
                sky_type=clean_scatter_clouds_flanked_by_thin_clouds_with_polars(
                    sky_type.select(po.col("times_utc", "sky_type")), df_indices)["sky_type"]
            )
        else:
            sky_type = clean_scatter_clouds_flanked_by_thin_clouds_with_polars(sky_type, df_indices)

    if options.CLEAN_CLOUDLESS_TO_THIN_CLOUDS_TRANSITIONS:
        if full_output:
            sky_type = sky_type.with_columns(
                sky_type=clean_cloudless_to_thin_clouds_transitions_with_polars(
                    sky_type.select(po.col("times_utc", "sky_type")), df_indices)["sky_type"]
            )
        else:
            sky_type = clean_cloudless_to_thin_clouds_transitions_with_polars(sky_type, df_indices)

    if options.CLEAN_THIN_CLOUDS_TO_SCATTER_CLOUDS_TRANSITIONS:
        if full_output:
            sky_type = sky_type.with_columns(
                sky_type=clean_thin_clouds_to_scatter_clouds_transitions_with_polars(
                    sky_type.select(po.col("times_utc", "sky_type")), df_indices)["sky_type"]
            )
        else:
            sky_type = clean_thin_clouds_to_scatter_clouds_transitions_with_polars(sky_type, df_indices)

    mask = po.col("ghi").is_null() | po.col("Km").is_null() | po.col("Kv").is_null() | po.col("Kvf").is_null()
    return (
        po.concat([sky_type, df_indices], how="align")
        .with_columns(sky_type=po.when(mask).then(SkyType.UNKNOWN).otherwise(po.col("sky_type")))
        .select(sky_type.columns)
    )


def sky_segmentation_with_pandas(sky_type: pd.DataFrame | pd.Series) -> pd.DataFrame:
    """
    Detects changes of sky type and assigns incremental labels (integers)
    to all time steps corresponding to the new sky type (segments).

    For instance, given the following sequence of sky types:

        [2, 2, 2, 4, 4, 5, 5, 5, 5, 5, 3, 4, 4]

    the segmentation is:

        [0, 0, 0, 1, 1, 2, 2, 2, 2, 2, 3, 4, 4]
    """
    sky_segments = (sky_type != sky_type.shift(-1)).shift(1, fill_value=0).cumsum()
    sky_segments = pd.DataFrame(data={"segment": sky_segments})
    sky_segments["sky_type"] = sky_type
    return sky_segments[["sky_type", "segment"]].astype({"sky_type": np.int32, "segment": np.uint32})


def sky_segmentation_with_polars(sky_type: po.DataFrame) -> po.DataFrame:
    """
    Detects changes of sky type and assigns incremental labels (integers)
    to all time steps corresponding to the new sky type (segments).

    For instance, given the following sequence of sky types:

        [2, 2, 2, 4, 4, 5, 5, 5, 5, 5, 3, 4, 4]

    the segmentation is:

        [0, 0, 0, 1, 1, 2, 2, 2, 2, 2, 3, 4, 4]
    """
    return sky_type.with_columns(po.col("sky_type").rle_id().alias("segment"))


def reduce_sky_segments_with_pandas(sky_segments: pd.DataFrame) -> pd.DataFrame:
    """
    Summarizes the series of segments into a table of sky patches.

    Each entry in the table (i.e., each row) is referred to as a patch.
    A patch is made up by the segment label, its sky type, its length,
    and the previous and next sky types, and their own lengths.

    For instance, for the example shown in sky_segmentation, the sky
    patches are:

    segment  sky_type  segment      prev         prev      next         next
                           len  sky_type  segment_len  sky_type  segment_len
    0               2        3       NaN          NaN         1            2
    1               4        2         2            3         5            5
    2               5        5         4            2         3            1
    3               3        1         5            5         4            2
    4               4        2         3            1       NaN          NaN
    """

    def reduce_sky_type(x):
        return x["sky_type"].unique().item()

    grouper = sky_segments.groupby("segment")  # [sky_segments.columns]
    sky_patches = grouper.apply(reduce_sky_type, include_groups=False).to_frame(name="sky_type")
    sky_patches["segment_len"] = grouper.count()
    sky_patches["prev_sky_type"] = sky_patches["sky_type"].shift(1)
    sky_patches["prev_segment_len"] = sky_patches["segment_len"].shift(1)
    sky_patches["next_sky_type"] = sky_patches["sky_type"].shift(-1)
    sky_patches["next_segment_len"] = sky_patches["segment_len"].shift(-1)
    return sky_patches


def reduce_sky_segments_with_polars(sky_segments: po.DataFrame) -> po.DataFrame:
    """
    Summarizes the series of segments into a table of sky patches.

    Each entry in the table (i.e., each row) is referred to as a patch.
    A patch is made up by the segment label, its sky type, its length,
    and the previous and next sky types, and their own lengths.

    For instance, for the example shown in sky_segmentation, the sky
    patches are:

    segment  sky_type  segment      prev         prev      next         next
                           len  sky_type  segment_len  sky_type  segment_len
    0               2        3       NaN          NaN         1            2
    1               4        2         2            3         5            5
    2               5        5         4            2         3            1
    3               3        1         5            5         4            2
    4               4        2         3            1       NaN          NaN
    """
    return (
        sky_segments
        .group_by("segment", maintain_order=True)
        .agg([
            po.col("sky_type").first(),  # tomamos el tipo de cielo del segmento
            po.len().alias("segment_len") # longitud del segmento
        ])
        .with_columns([
            # información del segmento anterior
            po.col("sky_type").shift(1).alias("prev_sky_type"),
            po.col("segment_len").shift(1).alias("prev_segment_len"),
            # información del segmento siguiente
            po.col("sky_type").shift(-1).alias("next_sky_type"),
            po.col("segment_len").shift(-1).alias("next_segment_len")
        ])
    )


def clean_spurious_sky_patches_with_pandas(sky_type: pd.Series, min_sky_patch_len: int = 15, max_iter: int = 20) -> pd.Series:
    """
    Removes spurious sky patches in the following sky transitions:
      1. From scatter_clouds or thick_clouds to anything different from cloud_enhancements
      2. Between thin_clouds and cloudless skies, and viceversa
    A sky patch is spurious when its length is shorter than `min_sky_path_len`
    """
    logger.info("clean spurious sky patches...")

    polished_sky_type = sky_type.copy()

    remaining_iter = max_iter
    while remaining_iter:
        i_iter = max_iter - remaining_iter

        sky_segments = sky_segmentation_with_pandas(polished_sky_type)
        sky_patches = reduce_sky_segments_with_pandas(sky_segments)

        sky_patches["polished"] = sky_patches["sky_type"]

        is_known = sky_patches["sky_type"] != SkyType.UNKNOWN

        logger.debug(f"i={i_iter+1}: len(sky_patches)={len(sky_patches)} "
                     f"len(known_sky_patches)={len(sky_patches.loc[is_known])}")

        is_spurious = (
            (sky_patches["segment_len"] < min_sky_patch_len) &
            (
                (sky_patches["prev_segment_len"] >= min_sky_patch_len) |
                (sky_patches["next_segment_len"] >= min_sky_patch_len)
            )
        )

        logger.debug(f"i={i_iter+1}: len(spurious)={len(sky_patches.loc[is_spurious])}")

        # remove spurious transitions from scatter_clouds or thick_clouds
        # to anything different from cloud_enhancements
        cond_on_scatter_and_thick_clouds = (
            is_known & is_spurious &
            (sky_patches["prev_sky_type"] == sky_patches["next_sky_type"]) &
            (sky_patches["sky_type"] != SkyType.CLOUD_ENHANCEMENT) &
            (
                (sky_patches["prev_sky_type"] == SkyType.SCATTER_CLOUDS) |
                (sky_patches["prev_sky_type"] == SkyType.THICK_CLOUDS)
            )
        )
        sky_patches.loc[cond_on_scatter_and_thick_clouds, "polished"] = sky_patches["prev_sky_type"]

        # logging block...
        len_cond = len(sky_patches.loc[cond_on_scatter_and_thick_clouds])
        logger.debug(f"i={i_iter+1}: len(cond_on_scatter_and_thick_clouds)={len_cond}")
        n_updates = sum(sky_patches["polished"] != sky_patches["sky_type"])
        logger.debug(f"i={i_iter+1}: {n_updates} instances updated!")

        # remove spurious transitions thin_clouds <=> cloudless transitions
        cond_on_thin_and_cloudless = (
            is_known & is_spurious &
            (sky_patches["prev_sky_type"] == sky_patches["next_sky_type"]) &
            (
                (sky_patches["sky_type"] == SkyType.THIN_CLOUDS) |
                (sky_patches["sky_type"] == SkyType.CLOUDLESS)
            ) &
            (
                (sky_patches["prev_sky_type"] == SkyType.THIN_CLOUDS) |
                (sky_patches["prev_sky_type"] == SkyType.CLOUDLESS)
            )
        )
        sky_patches.loc[cond_on_thin_and_cloudless, "polished"] = sky_patches["prev_sky_type"]

        # logging block...
        logger.debug(f"i={i_iter+1}: len(cond_on_thin_and_cloudless)="
                     f"{len(sky_patches.loc[cond_on_thin_and_cloudless])}")
        updates = sum(sky_patches["polished"] != sky_patches["sky_type"])
        logger.debug(f"i={i_iter+1}: {updates} instances updated!")

        new_polished_sky_type = pd.Series(
            index=polished_sky_type.index, name="polished",
            data=sky_patches.loc[sky_segments["segment"], "polished"].values
        )

        updated_values = sum(polished_sky_type != new_polished_sky_type)
        polished_sky_type = new_polished_sky_type

        logger.debug(f"i={i_iter+1}: {updated_values} instances updated in total in the loop!")

        if not updated_values:
            break

        remaining_iter -= 1

    updated_values = sum(sky_type != polished_sky_type)
    logger.debug(f"{updated_values} instances updated in total in all loops!")

    return polished_sky_type


def clean_spurious_sky_patches_with_polars(sky_type: po.DataFrame, min_sky_patch_len: int = 15, max_iter: int = 20) -> po.DataFrame:
    """
    Removes spurious sky patches in the following sky transitions:
      1. From scatter_clouds or thick_clouds to anything different from cloud_enhancements
      2. Between thin_clouds and cloudless skies, and viceversa
    A sky patch is spurious when its length is shorter than `min_sky_path_len`
    """
    logger.info("clean spurious sky patches...")

    polished_sky_type_df = sky_type.clone().with_columns(sky_type=po.col("sky_type").cast(po.Int32))

    for i in range(max_iter):

        # lazy dataframe for optimization
        polished_sky_type_lf = polished_sky_type_df.lazy()
        
        # sky segmentation (as in sky_segmentation)
        sky_segments_lf = polished_sky_type_lf.with_columns(po.col("sky_type").cast(po.Int32).rle_id().alias("segment"))

        # reduced sky segments (as in reduce_sky_segments)
        sky_patches_lf = (
            sky_segments_lf.group_by("segment", maintain_order=True)
            .agg([
                po.col("sky_type").first(),
                po.len().alias("segment_len")
            ])
            .with_columns([
                po.col("sky_type").shift(1).fill_null(SkyType.UNKNOWN).alias("prev_sky_type"),
                po.col("segment_len").shift(1).fill_null(SkyType.UNKNOWN).alias("prev_segment_len"),
                po.col("sky_type").shift(-1).fill_null(SkyType.UNKNOWN).alias("next_sky_type"),
                po.col("segment_len").shift(-1).fill_null(SkyType.UNKNOWN).alias("next_segment_len")
            ])
        )

        sky_patches_lf = sky_patches_lf.with_columns(polished=po.col("sky_type").cast(po.Int32))

        # cleaning logic

        is_known_sky_type = po.col("sky_type").ne(SkyType.UNKNOWN).fill_null(False)
        logger.debug(f"i={i+1}: len(patches_lf)={sky_patches_lf.select(po.len()).collect().item()} "
                     f"len(known_patches_lf)={sky_patches_lf.filter(is_known_sky_type).select(po.len()).collect().item()}")

        is_spurious = (
            (po.col("segment_len") < min_sky_patch_len) &
            (
                po.col("prev_segment_len").ge(min_sky_patch_len).fill_null(False) | 
                po.col("next_segment_len").ge(min_sky_patch_len).fill_null(False)
            )
        ).fill_null(False)
        logger.debug(f"i={i+1}: len(spurious)={sky_patches_lf.filter(is_spurious).select(po.len()).collect().item()}")

        cond_on_scatter_and_thick_clouds = (
            is_known_sky_type & is_spurious &
            po.col("prev_sky_type").eq(po.col("next_sky_type")).fill_null(False) &
            po.col("sky_type").ne(SkyType.CLOUD_ENHANCEMENT).fill_null(False) &
            po.col("prev_sky_type").is_in([SkyType.SCATTER_CLOUDS, SkyType.THICK_CLOUDS]).fill_null(False)
        )

        sky_patches_lf = sky_patches_lf.with_columns(
            polished = po.when(cond_on_scatter_and_thick_clouds)
                       .then(po.col("prev_sky_type"))
                       .otherwise(po.col("polished")))

        # logging block...
        len_cond = sky_patches_lf.filter(cond_on_scatter_and_thick_clouds).select(po.len()).collect().item()
        logger.debug(f"i={i+1}: len(cond_on_scatter_and_thick_clouds)={len_cond}")
        n_updates = sky_patches_lf.filter(po.col("polished").ne(po.col("sky_type"))).select(po.len()).collect().item()
        logger.debug(f"i={i+1}: {n_updates} instances updated!")

        cond_on_thin_and_cloudless = (
            is_known_sky_type & is_spurious &
            po.col("prev_sky_type").eq(po.col("next_sky_type")).fill_null(False) &
            po.col("sky_type").is_in([SkyType.THIN_CLOUDS, SkyType.CLOUDLESS]).fill_null(False) &
            po.col("prev_sky_type").is_in([SkyType.THIN_CLOUDS, SkyType.CLOUDLESS]).fill_null(False)
        )

        sky_patches_lf = sky_patches_lf.with_columns(
            polished = po.when(cond_on_thin_and_cloudless)
                       .then(po.col("prev_sky_type"))
                       .otherwise(po.col("polished")))

        # logging block...
        len_cond = sky_patches_lf.filter(cond_on_thin_and_cloudless).select(po.len()).collect().item()
        logger.debug(f"i={i+1}: len(cond_on_thin_and_cloudless)={len_cond}")
        n_updates = sky_patches_lf.filter(po.col("polished").ne(po.col("sky_type"))).select(po.len()).collect().item()
        logger.debug(f"i={i+1}: {n_updates} instances updated!")

        new_polished_sky_type_df = (sky_segments_lf.join(sky_patches_lf, on="segment")
                                    .select(po.col("times_utc", "polished"))
                                    .collect())

        n_updates = (polished_sky_type_df
                     .join(new_polished_sky_type_df, on="times_utc", how="left")
                     .filter(po.col("sky_type").ne(po.col("polished")))
                     .select(po.len()).item())
        polished_sky_type_df = new_polished_sky_type_df.rename({"polished": "sky_type"})

        logger.debug(f"i={i+1}: {n_updates} instances updated in total in the loop!")

        if not n_updates:
            break

    n_updates = (polished_sky_type_df
                 .join(sky_type.rename({"sky_type": "original_sky_type"}), on="times_utc", how="left")
                 .filter(po.col("sky_type").ne(po.col("original_sky_type")))
                 .select(po.len()).item())
    logger.debug(f"{n_updates} instances updated in total in all loops!")

    return polished_sky_type_df


def clean_scatter_clouds_flanked_by_thin_clouds_with_pandas(sky_type: pd.Series, df_indices: pd.DataFrame) -> pd.Series:
    """
    Convert to thin_clouds all scatter_clouds patches that are longer than
    25 minutes and shorter than 35 minutes, and that are flanked by thin_clouds,
    unless they meet the conditions set below in the code (and that are also
    in section 3.2 in the paper)
    """

    logger.info("clean scatter_clouds flanked by thin_clouds...")

    dt = options.DT  # a string for pandas timedelta, typically, "30min"

    sky_segments = sky_segmentation_with_pandas(sky_type)
    sky_patches = reduce_sky_segments_with_pandas(sky_segments)

    rollwin = df_indices["Kv"].rolling(dt, center=True)
    A = rollwin.mean() / rollwin.max()

    # CONDITIONS TO REMAIN AS SCATTER_CLOUDS: these conditions select mostly
    # scatter_clouds, but also other sky types, such as cloud_enhancements.
    # However, they are applied below only to sky patches that are scatter_clouds
    candidates = (df_indices["sza"] < 70.) & (df_indices["Km"] > 0.7) & (df_indices["Kv"] > 0.1) & (A > 0.9)

    candidate_segments = sky_segments.loc[candidates, "segment"].unique()
    sky_patches = sky_patches.loc[candidate_segments]

    # Amongst all "candidate segments", selects only the ones that
    # are scatter_clouds, not too long or too short, and that are
    # flanked by thin_clouds on both sides
    target_sky_patches = (
        (sky_patches["sky_type"] == SkyType.SCATTER_CLOUDS) &
        (
            (sky_patches["segment_len"] > 25) &
            (sky_patches["segment_len"] < 35)
        ) &
        (
            (sky_patches["prev_sky_type"] == SkyType.THIN_CLOUDS) &
            (sky_patches["next_sky_type"] == SkyType.THIN_CLOUDS)
        )
    )

    # all `target_sky_patches` are scatter_clouds...
    sky_patches = sky_patches.loc[target_sky_patches]

    new_sky_type = sky_type.copy()
    target_segments = sky_segments["segment"].isin(sky_patches.index)

    # convert all the `target_sky_patches` to thin_clouds, but keep as
    # scatter_clouds those that verify the conditions in `candidates`
    new_sky_type.loc[target_segments] = SkyType.THIN_CLOUDS
    new_sky_type.loc[target_segments & candidates] = SkyType.SCATTER_CLOUDS

    logger.info(f"  {len(sky_patches)} sky patches updated "
                f"({(target_segments & candidates).sum()} time steps)")

    return new_sky_type


def clean_scatter_clouds_flanked_by_thin_clouds_with_polars(sky_type: po.DataFrame, df_indices: po.DataFrame) -> po.DataFrame:
    """
    Convert to thin_clouds all scatter_clouds patches that are longer than
    25 minutes and shorter than 35 minutes, and that are flanked by thin_clouds,
    unless they meet the conditions set below in the code (and that are also
    in section 3.2 in the paper)
    """

    logger.info("clean scatter_clouds flanked by thin_clouds...")

    dt = pd.Timedelta(options.DT)
    window_size = int(dt // pd.Timedelta("1min"))
    offset = - (window_size // 2)

    # 1. Unir índices y sky_type por tiempo (asegura alineación)
    df = sky_type.join(df_indices, on="times_utc", how="left")

    # 2. Calcular condiciones de candidatos y ventana móvil (A)
    # Nota: Usamos rolling_mean/max sobre una columna temporal

    df = df.with_columns(
        A=(po.col("Kv").rolling_mean(window_size=window_size, center=False).shift(offset) /
           po.col("Kv").rolling_max(window_size=window_size, center=False).shift(offset)),
        segment=po.col("sky_type").rle_id()
    ).with_columns(
        candidates = ((po.col("sza") < 70.0) & (po.col("Km") > 0.7) & (po.col("Kv") > 0.1) & (po.col("A") > 0.9)).fill_null(False)
    ).drop("A")

    # 3. Calcular métricas por segmento (sky_patches)
    sky_patches = (
        df.group_by("segment", maintain_order=True)
        .agg(
            sky_type=po.col("sky_type").first(),
            segment_len=po.len(),
            has_candidate=po.col("candidates").any() # Si algún punto del segmento es candidato
        )
        .with_columns(
            prev_sky_type=po.col("sky_type").shift(1).fill_null(SkyType.UNKNOWN),
            next_sky_type=po.col("sky_type").shift(-1).fill_null(SkyType.UNKNOWN)
        )
    )

    # 4. Identificar parches objetivo (Target Sky Patches)
    # Usamos .eq() para evitar problemas con nulos en los bordes
    is_target_patch = (
        po.col("sky_type").eq(SkyType.SCATTER_CLOUDS) &
        (po.col("segment_len") > 25) &
        (po.col("segment_len") < 35) &
        po.col("prev_sky_type").eq(SkyType.THIN_CLOUDS) &
        po.col("next_sky_type").eq(SkyType.THIN_CLOUDS)
    ).fill_null(False)

    # Solo nos interesan los IDs de segmentos que cumplen esto
    target_segments_ids = sky_patches.filter(is_target_patch & po.col("has_candidate")).get_column("segment")

    # 5. Aplicar la lógica de reemplazo
    # - Si el segmento está en la lista de objetivos:
    #    - Si el punto individual NO es candidato -> THIN_CLOUDS
    #    - Si el punto individual ES candidato -> SCATTER_CLOUDS (se mantiene)
    # - Si no es objetivo -> Se mantiene igual
    
    result_df = df.with_columns(
        sky_type = po.when(po.col("segment").is_in(target_segments_ids))
                   .then(
                       po.when(po.col("candidates"))
                       .then(po.col("sky_type"))
                       .otherwise(SkyType.THIN_CLOUDS)
                   )
                   .otherwise(po.col("sky_type"))
    )

    # Limpieza final para devolver solo las columnas originales
    return result_df.select(sky_type.columns)


def clean_cloudless_to_thin_clouds_transitions_with_pandas(sky_type: pd.Series, df_indices: pd.DataFrame) -> pd.Series:
    """
    Downgrade cloudless patches that are potentially thin_clouds. Normally,
    it benefits the predictions with gisplit
    """
    logger.info("reviewing cloudless => thin_clouds transitions")

    sky_segments = sky_segmentation_with_pandas(sky_type)
    sky_patches = reduce_sky_segments_with_pandas(sky_segments)

    cloudless_candidates = (
        (sky_patches["sky_type"] == SkyType.CLOUDLESS)
        & (sky_patches["prev_sky_type"] == SkyType.THIN_CLOUDS)
        & (sky_patches["next_sky_type"] == SkyType.THIN_CLOUDS)
        & (sky_patches["segment_len"] < 20)
        & (
            (
                (sky_patches["prev_segment_len"] +
                 sky_patches["next_segment_len"]) >
                0.5*sky_patches["segment_len"]
            )
          )
    )

    n_updates = 0
    new_sky_type = sky_type.copy()
    for segment in sky_patches.loc[cloudless_candidates].index:
        domain = sky_segments["segment"] == segment
        q25 = df_indices["Kv"].loc[domain].quantile(q=0.25)
        segment_data = sky_segments.loc[domain]
        logger.debug(f"segment {segment}: [{segment_data.index[0]}, "
                     f"{segment_data.index[-1]}], {len(segment_data)} steps")
        if q25 >= 0.01:
            new_sky_type.loc[domain] = SkyType.THIN_CLOUDS
            n_updates += 1

    logger.debug(f"  {n_updates} segments updated")

    return new_sky_type


def clean_cloudless_to_thin_clouds_transitions_with_polars(sky_type: po.DataFrame, df_indices: po.DataFrame) -> po.DataFrame:
    
    logger.info("reviewing cloudless => thin_clouds transitions")

    # 1. Preparar datos: Unir sky_type con los índices (Kv) y crear segmentos
    df = sky_type.join(df_indices.select(["times_utc", "Kv"]), on="times_utc", how="left")
    df = df.with_columns(segment=po.col("sky_type").rle_id())

    # 2. Reducir segmentos a parches y calcular métricas necesarias (incluido el cuantil)
    sky_patches = (
        df.group_by("segment", maintain_order=True)
        .agg(
            sky_type=po.col("sky_type").first(),
            segment_len=po.len(),
            kv_q25=po.col("Kv").quantile(0.25) # Calculamos q25 por segmento
        )
        .with_columns(
            prev_sky_type=po.col("sky_type").shift(1).fill_null(SkyType.UNKNOWN),
            prev_segment_len=po.col("segment_len").shift(1).fill_null(SkyType.UNKNOWN),
            next_sky_type=po.col("sky_type").shift(-1).fill_null(SkyType.UNKNOWN),
            next_segment_len=po.col("segment_len").shift(-1).fill_null(SkyType.UNKNOWN)
        )
    )

    # 3. Definir la condición de candidatos (Cloudless rodeado de Thin Clouds)
    # Usamos .eq() y fill_null(False) para seguridad en los bordes
    cloudless_candidates_mask = (
        po.col("sky_type").eq(SkyType.CLOUDLESS) &
        po.col("prev_sky_type").eq(SkyType.THIN_CLOUDS) &
        po.col("next_sky_type").eq(SkyType.THIN_CLOUDS) &
        (po.col("segment_len") < 20) &
        (
            (po.col("prev_segment_len").fill_null(0) + po.col("next_segment_len").fill_null(0)) > 
            (0.5 * po.col("segment_len"))
        ) &
        (po.col("kv_q25") >= 0.01) # El criterio del cuantil que estaba en tu bucle for
    ).fill_null(False)

    # 4. Obtener los IDs de los segmentos que deben actualizarse
    segments_to_update = sky_patches.filter(cloudless_candidates_mask).get_column("segment")

    # 5. Aplicar la actualización masiva (sin bucles for)
    result = df.with_columns(
        sky_type = po.when(po.col("segment").is_in(segments_to_update))
                   .then(SkyType.THIN_CLOUDS)
                   .otherwise(po.col("sky_type"))
    )

    logger.debug(f"  {len(segments_to_update)} segments updated")

    return result.select(sky_type.columns)


def clean_thin_clouds_to_scatter_clouds_transitions_with_pandas(sky_type: pd.DataFrame, df_indices: pd.DataFrame) -> pd.Series:
    """
    Downgrade thin_clouds patches that are potentially scatter_clouds.
    Normally, it improves the predictions with gisplit
    """
    logger.info("reviewing thin_clouds => scatter_clouds transitions")

    sky_segments = sky_segmentation_with_pandas(sky_type)
    sky_patches = reduce_sky_segments_with_pandas(sky_segments)

    cloudless_candidates = (
        (sky_patches["sky_type"] == SkyType.THIN_CLOUDS)
        & (sky_patches["prev_sky_type"] == SkyType.SCATTER_CLOUDS)
        & (sky_patches["next_sky_type"] == SkyType.SCATTER_CLOUDS)
        & (sky_patches["segment_len"] > 20)
        & (
            (
                (sky_patches["prev_segment_len"] +
                 sky_patches["next_segment_len"]) >
                0.5*sky_patches["segment_len"]
            )
          )
    )

    n_updates = 0
    new_sky_type = sky_type.copy()
    for segment in sky_patches.loc[cloudless_candidates].index:
        domain = sky_segments["segment"] == segment
        q75 = df_indices["Kv"].loc[domain].quantile(q=0.75)
        segment_data = sky_segments.loc[domain]
        logger.debug(f"segment {segment}: [{segment_data.index[0]}, "
                     f"{segment_data.index[-1]}], {len(segment_data)} steps")
        if q75 >= 0.04:
            new_sky_type.loc[domain] = SkyType.SCATTER_CLOUDS
            n_updates += 1

    logger.debug(f"  {n_updates} segments updated")

    return new_sky_type


def clean_thin_clouds_to_scatter_clouds_transitions_with_polars(sky_type: po.DataFrame, df_indices: po.DataFrame) -> po.DataFrame:
    
    logger.info("reviewing thin_clouds => scatter_clouds transitions")

    # 1. Unir datos y generar IDs de segmentos
    df = sky_type.join(df_indices.select(["times_utc", "Kv"]), on="times_utc", how="left")
    df = df.with_columns(segment = po.col("sky_type").rle_id())

    # 2. Resumir parches calculando el cuantil 0.75 por segmento
    sky_patches = (
        df.group_by("segment", maintain_order=True)
        .agg([
            po.col("sky_type").first(),
            po.len().alias("segment_len"),
            po.col("Kv").quantile(0.75).alias("kv_q75")
        ])
        .with_columns([
            po.col("sky_type").shift(1).alias("prev_sky_type"),
            po.col("segment_len").shift(1).alias("prev_segment_len"),
            po.col("sky_type").shift(-1).alias("next_sky_type"),
            po.col("segment_len").shift(-1).alias("next_segment_len")
        ])
    )

    # 3. Definir la máscara de candidatos (Thin Clouds rodeado de Scatter)
    # Usamos .eq() y fill_null para evitar que los bordes del dataset den null
    candidates_mask = (
        po.col("sky_type").eq(SkyType.THIN_CLOUDS) &
        po.col("prev_sky_type").eq(SkyType.SCATTER_CLOUDS) &
        po.col("next_sky_type").eq(SkyType.SCATTER_CLOUDS) &
        (po.col("segment_len") > 20) &
        (
            (po.col("prev_segment_len").fill_null(0) + po.col("next_segment_len").fill_null(0)) > 
            (0.5 * po.col("segment_len"))
        ) &
        (po.col("kv_q75") >= 0.04)
    ).fill_null(False)

    # 4. Identificar segmentos a actualizar
    segments_to_update = sky_patches.filter(candidates_mask).get_column("segment")

    # 5. Aplicar cambios
    result = df.with_columns(
        sky_type = po.when(po.col("segment").is_in(segments_to_update))
                   .then(SkyType.SCATTER_CLOUDS)
                   .otherwise(po.col("sky_type"))
    )

    logger.debug(f"  {len(segments_to_update)} segments updated")

    # Devolvemos solo las columnas originales (times_utc y sky_type)
    return result.select(sky_type.columns)
