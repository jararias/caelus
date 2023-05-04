# CAELUS: Classification Algorithm for the Evaluation of the cLoUdiness Situations

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.7897639.svg)](https://doi.org/10.5281/zenodo.7897639)


This is a Python implementation of the CAELUS sky classification algorithm (_link to paper_). It also provides easy access to the related in [data](https://doi.org/10.5281/zenodo.7897639).

#### Installation

```python
python3 -m pip install git+https://github.com/jararias/caelus
```

#### Load data

The library provides easy access to the dataset described in the paper, that are available in the CAELUS [data repository](https://doi.org/10.5281/zenodo.7897639) in zenodo.org. For instance, to load the data taken during 2014 in the BSRN station in Carpentras, France, one can do the following:

```python
import caelus  # import caelus

# `car` is the BSRN's acronymn for the Carpentras station.
# `data` is a pandas DataFrame with the following variables:
# longitude, solar zenith angle (sza), extraterrestrial solar
# irradiance (eth), GHI, DIF, clear-sky GHI (ghics), GHI in
# a clean and dry atmosphere (ghicda), and sky_type
data = caelus.data.load('car', year=2014)
data
```

To load the data, this function first look for the file `car/car_bsrn_2014.zip` in `$HOME/CAELUS-DATA`, where `$HOME` is the user directory. If it is not there, it downloads the file from the zenodo.org repository, so that it is locally available for subsequent requests. The local data path `$HOME/CAELUS-DATA` is set in the module `caelus.options`. The user can change it in real time or hardcode it by editing the file `$INSTALL_DIR/caelus/options.py`, where `$INSTALL_DIR` is the Python path where `caelus` is installed.

#### Dealing with logging

By default, logging messages are disabled. To enable them:

```python
from loguru import logger

logger.enable('caelus')
```

Normally, by default, the logging level is `DEBUG`. To change to `INFO`:

```python
import sys
logger.remove()
logger.add(sys.stderr, level='INFO')
```

#### Classifying data

With the variables already in the `data` DataFrame is very simple to make the classification:

```python
sky_type = caelus.classify(data)  # Pandas Series
````

`sky_type` is a Pandas Series of integers from 1 to 7, which represent the 6 sky classes (from 2 to 7), being 1 reserved for _UNKNOWN_ situations (e.g., `sza > 85deg`). The equivalence between the integer labels and the actual sky conditions are mapped in the SkyType enumerate type:

```python
for n in range(1, 8):
    print(n, caelus.skytype.SkyType(n))
```

#### Comparing results

One would expect that the `sky_type` column included in the `data` DataFrame is identical to the `sky_type` Series just obtained with `caelus.classify`. However, there are few points with slightly different sky types, that mostly occur at sunrise and sunset, as you may see with the following sentence:

```python
data.loc[data.sky_type != sky_type]
```

The reason is that the precision of the data in the repository was slightly decreased to reduce the volume of data, but still keeping reasonable precision level. For instance, GHI and DIF are archived with two significant digits. Nonetheless, these small truncation errors were sufficient to induce some tiny discrepancies between the two sky types.

#### Diagnostic plots

The libray provides functions to make some diagnostic plots:

```python
caelus.diagnostics.histogram(sky_type)
caelus.diagnostics.pie_chart(sky_type)
caelus.diagnostics.density_ktk(data, sky_type)
```
