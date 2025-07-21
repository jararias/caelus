
import pandas as pd

from loguru import logger

from .skytype import SkyType


logger.disable(__name__)


def sky_segmentation(sky_type):
    """
    Detects changes of sky type and assigns incremental labels (integers)
    to all time steps corresponding to the new sky type (segments).

    For instance, given the following sequence of sky types:

        [2, 2, 2, 4, 4, 5, 5, 5, 5, 5, 3, 4, 4]

    the segmentation is:

        [0, 0, 0, 1, 1, 2, 2, 2, 2, 2, 3, 4, 4]
    """
    sky_segments = (
        (sky_type != sky_type.shift(-1)).shift(1, fill_value=0).cumsum())
    sky_segments = pd.DataFrame(data={'segment': sky_segments})
    sky_segments['sky_type'] = sky_type
    return sky_segments


def reduce_sky_segments(sky_segments):
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
        return x['sky_type'].unique().item()

    grouper = sky_segments.groupby('segment')[sky_segments.columns]
    sky_patches = grouper.apply(reduce_sky_type).to_frame(name='sky_type')
    sky_patches['segment_len'] = grouper.count()
    sky_patches['prev_sky_type'] = sky_patches['sky_type'].shift(1)
    sky_patches['prev_segment_len'] = sky_patches['segment_len'].shift(1)
    sky_patches['next_sky_type'] = sky_patches['sky_type'].shift(-1)
    sky_patches['next_segment_len'] = sky_patches['segment_len'].shift(-1)
    return sky_patches


def clean_spurious_sky_patches(sky_type, min_sky_patch_len=15, max_iter=20):
    """
    Removes spurious sky patches in the following sky transitions:
      1. From scatter_clouds or thick_clouds to anything different from
         cloud_enhancements
      2. Between thin_clouds and cloudless skies, and viceversa
    A sky patch is spurious when its length is shorter than `min_sky_path_len`
    """
    logger.info('clean spurious sky patches...')

    remaining_iter = max_iter
    polished_sky_type = sky_type.copy()

    while remaining_iter:

        sky_segments = sky_segmentation(polished_sky_type)
        sky_patches = reduce_sky_segments(sky_segments)

        sky_patches['polished'] = sky_patches['sky_type']

        is_known = sky_patches['sky_type'] != SkyType.UNKNOWN

        is_spurious = (
            (sky_patches['segment_len'] < min_sky_patch_len) &
            (
                (sky_patches['prev_segment_len'] >= min_sky_patch_len) |
                (sky_patches['next_segment_len'] >= min_sky_patch_len)
            )
        )

        # remove spurious transitions from scatter_clouds or thick_clouds
        # to anything different from cloud_enhancements
        condition = (
            is_known & is_spurious &
            (sky_patches['prev_sky_type'] == sky_patches['next_sky_type']) &
            (sky_patches['sky_type'] != SkyType.CLOUD_ENHANCEMENT) &
            (
                (sky_patches['prev_sky_type'] == SkyType.SCATTER_CLOUDS) |
                (sky_patches['prev_sky_type'] == SkyType.THICK_CLOUDS)
            )
        )
        sky_patches.loc[condition, 'polished'] = sky_patches['prev_sky_type']

        # remove spurious transitions thin_clouds <=> cloudless transitions
        condition = (
            is_known & is_spurious &
            (sky_patches['prev_sky_type'] == sky_patches['next_sky_type']) &
            (
                (sky_patches['sky_type'] == SkyType.THIN_CLOUDS) |
                (sky_patches['sky_type'] == SkyType.CLOUDLESS)
            ) &
            (
                (sky_patches['prev_sky_type'] == SkyType.THIN_CLOUDS) |
                (sky_patches['prev_sky_type'] == SkyType.CLOUDLESS)
            )
        )
        sky_patches.loc[condition, 'polished'] = sky_patches['prev_sky_type']

        new_polished_sky_type = pd.Series(
            index=polished_sky_type.index, name='polished',
            data=sky_patches.loc[sky_segments['segment'], 'polished'].values
        )

        updated_values = sum(polished_sky_type != new_polished_sky_type)
        polished_sky_type = new_polished_sky_type

        if not updated_values:
            break

        remaining_iter -= 1

        logger.debug(
            f'iter={max_iter-remaining_iter}: {updated_values} '
            f'updated values, {remaining_iter} iterations remaining')

    updated_values = sum(sky_type != polished_sky_type)
    logger.info(
        f'  {max_iter-remaining_iter} iterations: '
        f'{updated_values} updated values')

    return polished_sky_type


def clean_scatter_clouds_flanked_by_thin_clouds(sky_type, dt, sza, Km, Kv):
    """
    Convert to thin_clouds all scatter_clouds patches that are longer than
    25 minutes and shorter than 35 minutes, and that are flanked by thin_clouds,
    unless they meet the conditions set below in the code (and that are also
    in section 3.2 in the paper)
    """
    logger.info('clean scatter_clouds flanked by thin_clouds...')

    sky_segments = sky_segmentation(sky_type)
    sky_patches = reduce_sky_segments(sky_segments)

    rollwin = Kv.rolling(dt, center=True)
    A = rollwin.mean() / rollwin.max()

    # CONDITIONS TO REMAIN AS SCATTER_CLOUDS: these conditions select mostly
    # scatter_clouds, but also other sky types, such as cloud_enhancements.
    # However, they are applied below only to sky patches that are scatter_clouds
    candidates = (sza < 70.) & (Km > 0.7) & (Kv > 0.1) & (A > 0.9)

    candidate_segments = sky_segments.loc[candidates, 'segment'].unique()
    sky_patches = sky_patches.loc[candidate_segments]

    # Amongst all "candidate segments", selects only the ones that
    # are scatter_clouds, not too long or too short, and that are
    # flanked by thin_clouds on both sides
    target_sky_patches = (
        (sky_patches['sky_type'] == SkyType.SCATTER_CLOUDS) &
        (
            (sky_patches['segment_len'] > 25) &
            (sky_patches['segment_len'] < 35)
        ) &
        (
            (sky_patches['prev_sky_type'] == SkyType.THIN_CLOUDS) &
            (sky_patches['next_sky_type'] == SkyType.THIN_CLOUDS)
        )
    )

    # all `target_sky_patches` are scatter_clouds...
    sky_patches = sky_patches.loc[target_sky_patches]

    new_sky_type = sky_type.copy()
    target_segments = sky_segments['segment'].isin(sky_patches.index)

    # convert all the `target_sky_patches` to thin_clouds, but keep as
    # scatter_clouds those that verify the conditions in `candidates`
    new_sky_type.loc[target_segments] = SkyType.THIN_CLOUDS
    new_sky_type.loc[target_segments & candidates] = SkyType.SCATTER_CLOUDS

    logger.info(f'  {len(sky_patches)} sky patches updated '
                f'({(target_segments & candidates).sum()} time steps)')

    return new_sky_type


def clean_cloudless_to_thin_clouds_transitions(sky_type, Kv):
    """
    Downgrade cloudless patches that are potentially thin_clouds. Normally,
    it benefits the predictions with gisplit
    """
    logger.info('reviewing cloudless => thin_clouds transitions')

    sky_segments = sky_segmentation(sky_type)
    sky_patches = reduce_sky_segments(sky_segments)

    cloudless_candidates = (
        (sky_patches['sky_type'] == SkyType.CLOUDLESS)
        & (sky_patches['prev_sky_type'] == SkyType.THIN_CLOUDS)
        & (sky_patches['next_sky_type'] == SkyType.THIN_CLOUDS)
        & (sky_patches['segment_len'] < 20)  # +++ UPDATED > TO <
        & (
            (
                (sky_patches['prev_segment_len'] +
                 sky_patches['next_segment_len']) >
                0.5*sky_patches['segment_len']
            )
          )
    )

    n_updates = 0
    new_sky_type = sky_type.copy()
    for segment in sky_patches.loc[cloudless_candidates].index:
        domain = sky_segments['segment'] == segment
        q25 = Kv.loc[domain].quantile(q=0.25)
        segment_data = sky_segments.loc[domain]
        logger.debug(f'segment {segment}: [{segment_data.index[0]}, '
                     f'{segment_data.index[-1]}], {len(segment_data)} steps')
        if q25 >= 0.01:
            new_sky_type.loc[domain] = SkyType.THIN_CLOUDS
            n_updates += 1

    logger.info(f'  {n_updates} segments updated')

    return new_sky_type


def clean_thin_clouds_to_scatter_clouds_transitions(sky_type, Kv):
    """
    Downgrade thin_clouds patches that are potentially scatter_clouds.
    Normally, it improves the predictions with gisplit
    """
    logger.info('reviewing thin_clouds => scatter_clouds transitions')

    sky_segments = sky_segmentation(sky_type)
    sky_patches = reduce_sky_segments(sky_segments)

    cloudless_candidates = (
        (sky_patches['sky_type'] == SkyType.THIN_CLOUDS)
        & (sky_patches['prev_sky_type'] == SkyType.SCATTER_CLOUDS)
        & (sky_patches['next_sky_type'] == SkyType.SCATTER_CLOUDS)
        & (sky_patches['segment_len'] > 20)
        & (
            (
                (sky_patches['prev_segment_len'] +
                 sky_patches['next_segment_len']) >
                0.5*sky_patches['segment_len']
            )
          )
    )

    n_updates = 0
    new_sky_type = sky_type.copy()
    for segment in sky_patches.loc[cloudless_candidates].index:
        domain = sky_segments['segment'] == segment
        q75 = Kv.loc[domain].quantile(q=0.75)
        segment_data = sky_segments.loc[domain]
        logger.debug(f'segment {segment}: [{segment_data.index[0]}, '
                     f'{segment_data.index[-1]}], {len(segment_data)} steps')
        if q75 >= 0.04:
            new_sky_type.loc[domain] = SkyType.SCATTER_CLOUDS
            n_updates += 1

    logger.info(f'  {n_updates} segments updated')

    return new_sky_type
