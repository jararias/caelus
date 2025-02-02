
import csv
from pathlib import Path

import pandas as pd
import typer
from typing_extensions import Annotated

from . import classify, REQUIRED_TO_CLASSIFY

DATE_TIME_COLUMNS = {"Year", "Month", "Day", "Hour", "Minute", "Second"}

def load_data(path):
    df = pd.read_csv(path)
    
    if DATE_TIME_COLUMNS.issubset(df.columns):
        times = pd.to_datetime(df.get(list(DATE_TIME_COLUMNS)))
        cols_to_drop = list(DATE_TIME_COLUMNS)
    elif "times" in df.columns:
        times = pd.to_datetime(df["times"])
        cols_to_drop = ["times"]
    else:
        raise AttributeError(
            'expected a column "times" with the UTC row timestamps or, alternatively, '
            'the columns "Year", "Month", "Day", "Hour", "Minute", "Second"')

    df = (df.drop(columns=cols_to_drop, axis=1)
          .set_index(times)
          .sort_index(axis=0))

    if not REQUIRED_TO_CLASSIFY.issubset(df.columns):
        raise AttributeError(
            "there are missing columns that are required. The required columns are "
            f"{REQUIRED_TO_CLASSIFY}. The provided columns are {set(df.columns)}")

    return df

csvfile_argument = typer.Argument(
    show_default=False,
    help=("csv input file. Must have a column 'times' with the UTC timestamps for "
          "each row or, alternatively, the columns 'Year', 'Month', 'Day', 'Hour', "
          "'Minute' and 'Second'. In addition, the following columns are required: "
          "'longitude', 'sza', 'eth', 'ghi', 'ghics', 'ghicda'.")
)

outfile_argument = typer.Argument(
    show_default=False,
    help="csv output file",
)

@typer.run
def main(
    csvfile: Annotated[Path, csvfile_argument],
    output: Annotated[Path, outfile_argument],
):

    if not csvfile.exists():
        raise FileNotFoundError(f'missing input file "{csvfile}"')

    data = load_data(csvfile)
    sky_type = classify(data).to_frame("value")

    with open(csvfile, "r") as f:
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        header = [s.strip() for s in f.readline().split(dialect.delimiter)]
        if DATE_TIME_COLUMNS.issubset(header):
            sky_type = sky_type.assign(
                Year=sky_type.index.year,
                Month=sky_type.index.month,
                Day=sky_type.index.day,
                Hour=sky_type.index.hour,
                Minute=sky_type.index.minute,
                Second=sky_type.index.second,
                sky_type=sky_type.value,
            ).drop(columns=["value"])
        else:
            sky_type = (sky_type
                        .reset_index()
                        .rename(columns={"index": "times", "value": "sky_type"}))
    sky_type.to_csv(output,
                    index=False,
                    sep=dialect.delimiter,
                    lineterminator=dialect.lineterminator)
