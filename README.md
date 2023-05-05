# CAELUS: Classification Algorithm for the Evaluation of the cLoUdiness Situations

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.7897639.svg)](https://doi.org/10.5281/zenodo.7897639)


This is a Python implementation of the CAELUS sky classification algorithm, described in Ruiz-Arias and Gueymard (2023) (under review). It also provides easy access to the related [data](https://doi.org/10.5281/zenodo.7897639).

#### Installation

```python
python3 -m pip install git+https://github.com/jararias/caelus
```

#### Load data

The data that has been used to develop, validate and benchmark CAELUS is publicly available in a zenodo.org [data repository](https://doi.org/10.5281/zenodo.7897639). `caelus` can access to individual site-and-year files easily. For instance, to load the data taken during 2014 in the BSRN station in Carpentras, France, one can do the following:

```python
import caelus

# `car` is the BSRN's acronymn for the Carpentras station.
# `data` is a pandas DataFrame with the following variables:
# longitude, solar zenith angle (sza), extraterrestrial solar
# irradiance (eth), GHI, DIF, clear-sky GHI (ghics), GHI in
# a clean and dry atmosphere (ghicda), and sky_type
data = caelus.data.load('car', year=2014)
```

The first 5 data rows with `sza < 85deg` are:

<table border="1" class="dataframe">  <thead>    <tr style="text-align: right;">      <th></th>      <th>longitude</th>      <th>sza</th>      <th>eth</th>      <th>ghi</th>      <th>dif</th>      <th>ghics</th>      <th>ghicda</th>      <th>sky_type</th>    </tr>    <tr>      <th>times_utc</th>      <th></th>      <th></th>      <th></th>      <th></th>      <th></th>      <th></th>      <th></th>      <th></th>    </tr>  </thead>  <tbody>    <tr>      <th>2015-01-01 07:55:30</th>      <td>5.059</td>      <td>84.8945</td>      <td>125.26</td>      <td>24.0</td>      <td>23.0</td>      <td>57.55</td>      <td>87.60</td>      <td>5</td>    </tr>    <tr>      <th>2015-01-01 07:56:30</th>      <td>5.059</td>      <td>84.7556</td>      <td>128.66</td>      <td>25.0</td>      <td>25.0</td>      <td>59.62</td>      <td>90.27</td>      <td>5</td>    </tr>    <tr>      <th>2015-01-01 07:57:30</th>      <td>5.059</td>      <td>84.6171</td>      <td>132.05</td>      <td>34.0</td>      <td>26.0</td>      <td>61.69</td>      <td>92.94</td>      <td>5</td>    </tr>    <tr>      <th>2015-01-01 07:58:30</th>      <td>5.059</td>      <td>84.4790</td>      <td>135.43</td>      <td>48.0</td>      <td>27.0</td>      <td>63.78</td>      <td>95.61</td>      <td>5</td>    </tr>    <tr>      <th>2015-01-01 07:59:30</th>      <td>5.059</td>      <td>84.3413</td>      <td>138.79</td>      <td>54.0</td>      <td>28.0</td>      <td>65.87</td>      <td>98.29</td>      <td>5</td>    </tr>  </tbody></table>

The first time to access data for a site and year, it will take a while because it has to be downloaded. Afterwards, it is locally available for subsequent requests. By default, the data is archived in the file `<site_name>/<site_name>_bsrn_<year>.zip` (i.e., `car/car_bsrn_2014.zip` in the example above) in `$HOME/CAELUS-DATA`, where `$HOME` is the user directory. The user can change the local path to archive the data. For instance:

```python
from pathlib import Path
caelus.options.LOCAL_DATABASE = Path(/another/path/for/the/local/database)
```

This change is not persistent and has to be made every time that `caelus` is imported. To make it persistent, you have to edit the module `options.py` which is in `$INSTALL_DIR/caelus`, where `$INSTALL_DIR` is the installation directory of the `caelus`, and update the variable `LOCAL_DATABASE`.

#### Dealing with logging

By default, logging messages are disabled. To enable them:

```python
from loguru import logger
logger.enable('caelus')
```

Normally, the logging level is `DEBUG`. To change it:

```python
import sys
logger.remove()
logger.add(sys.stderr, level='INFO')
```

#### Classifying data

With the variables already available in the `data` DataFrame, the classification is simple to make:

```python
sky_type = caelus.classify(data)
````

`sky_type` is a Pandas Series of integers from 1 to 7, which represent the 6 sky classes (from 2 to 7), being 1 reserved for _UNKNOWN_ situations (e.g., `sza > 85deg`). The equivalence between the integer labels and the actual sky conditions are mapped in the SkyType enumerate type, as you could see by running the following code snippet:

```python
for n in range(1, 8):
    print(n, caelus.skytype.SkyType(n))
```

#### Comparing results

One would expect that the `sky_type` column included in the `data` DataFrame is identical to the `sky_type` Series just obtained with `caelus.classify`. However, there are few points with slightly different sky types, that mostly occur at sunrise and sunset, as you would see running the following:

```python
print(data.loc[data.sky_type != sky_type])
```

The reason is that the precision of the data was slightly decreased to reduce the volume of data in the repository, but this was done after the `sky_type` in `data` were evaluated. The precision decrease still keeps reasonable precision level. For instance, GHI and DIF are archived with two significant digits. However, it was sufficient to induce some tiny discrepancies between the `sky_type` uploaded to the data repository, and the `sky_type` just evaluated as above, even though the two of them were obtained with the same piece of code.

#### Diagnostic plots

The libray provides functions to make some diagnostic plots:

```python
caelus.diagnostics.histogram(sky_type)
caelus.diagnostics.pie_chart(sky_type)
caelus.diagnostics.density_ktk(data, sky_type)
```
