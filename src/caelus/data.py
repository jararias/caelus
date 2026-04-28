
import os
import json
import functools
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd
import platformdirs
from loguru import logger


REMOTE_FILE_PATTERN = "https://zenodo.org/record/7897639/files/{0}?download=1"
LOCAL_DATABASE = platformdirs.user_state_path("caelus", ensure_exists=True)
LOCAL_METADATA = LOCAL_DATABASE / "metadata.json"


@functools.cache
def load_metadata(site_name: str | None = None) -> dict:
    if not LOCAL_METADATA.exists():
        logger.info("Downloading metadata to local database")
        remote_file_name = REMOTE_FILE_PATTERN.format("metadata.json")
        pd.read_json(remote_file_name).to_json(LOCAL_METADATA)

    with LOCAL_METADATA.open("r", encoding="utf-8") as f_obj:
        metadata = json.load(f_obj)

    if site_name is None:
        return metadata

    return metadata.get(site_name, {})


@functools.cache
def load(site_name: str, year: int, minimalist: bool = True, refresh: bool = False):
    logger.info(f"Local database: {LOCAL_DATABASE}")

    file_name = LOCAL_DATABASE / site_name / f"{site_name}_bsrn_{year}.parquet"
    if refresh or not file_name.exists():
        if not file_name.parent.exists():
            file_name.parent.mkdir(parents=True, exist_ok=True)

        # download from server
        zip_file_name = file_name.with_suffix(".zip")
        remote_file_name = REMOTE_FILE_PATTERN.format(zip_file_name.name)
        logger.info(f"Downloading file {zip_file_name.name} to {file_name.parent}")
        data = pd.read_csv(remote_file_name, parse_dates=[0,], compression="zip").set_index("times_utc")

        # write to local
        if minimalist:
            data = data[["ghi", "dif", "ghics"]]
        data.to_parquet(file_name)

    # read from local
    return pd.read_parquet(file_name)


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
