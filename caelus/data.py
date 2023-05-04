
import json
import functools
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd
from loguru import logger

from .options import (
    LOCAL_DATABASE,
    REMOTE_FILE_PATTERN
)


logger.disable(__name__)


if not LOCAL_DATABASE.exists():
    LOCAL_DATABASE.mkdir(parents=True, exist_ok=True)

if not (file_name := LOCAL_DATABASE / 'metadata.json').exists():
    remote_file_name = REMOTE_FILE_PATTERN.format('metadata.json')
    pd.read_json(remote_file_name).to_json(file_name)
METADATA = json.load(open(file_name, 'r'))


@functools.cache
def load(site_name, year):

    localdir = LOCAL_DATABASE / site_name
    if not localdir.exists():
        localdir.mkdir(parents=True, exist_ok=True)

    if not (file_name := localdir / f'{site_name}_bsrn_{year}.zip').exists():
        remote_file_name = REMOTE_FILE_PATTERN.format(file_name.name)
        logger.info(f'Downloading file {file_name}')
        data = pd.read_csv(
            remote_file_name,
            parse_dates=[0,],
            compression='zip'
        ).set_index('times_utc')

        csv_file_name = file_name.with_suffix('.csv')
        data.to_csv(csv_file_name, index_label='times_utc')
        with ZipFile(file_name, 'w') as zipf:
            zipf.write(csv_file_name,
                       arcname=csv_file_name.name,
                       compress_type=ZIP_DEFLATED)
        csv_file_name.unlink()

    df = pd.read_csv(file_name, parse_dates=[0,]).set_index('times_utc')
    df.insert(0, 'longitude', METADATA.get(site_name).get('longitude'))
    return df


# def to_local_repo(site_name, year):
#     from . import classify  # pylint: disable=import-outside-toplevel

#     data = load(site_name, year)
#     data['sky_type'] = classify(data)

#     # drop unnecessary variables/precision to keep the data repository to a minimum
#     data = data.drop(columns=['longitude', 'difcs', 'aod550', 'albedo'])
#     data['sza'] = data['sza'].round(4)
#     data['eth'] = data['eth'].round(2)
#     data['ghics'] = data['ghics'].round(2)
#     data['ghicda'] = data['ghicda'].round(2)

#     localdir = LOCAL_DATABASE / site_name
#     if not localdir.exists():
#         localdir.mkdir(parents=True, exist_ok=True)

#     zip_file_name = localdir / f'{site_name}_bsrn_{year}.zip'
#     csv_file_name = zip_file_name.with_suffix('.csv')

#     data.to_csv(csv_file_name, index_label='times_utc')
#     with ZipFile(zip_file_name, 'w') as zipf:
#         zipf.write(csv_file_name, arcname=csv_file_name.name, compress_type=ZIP_DEFLATED)
#     csv_file_name.unlink()