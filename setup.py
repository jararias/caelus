import os
import codecs
from setuptools import setup


def read_content(fname):
    CURDIR = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(CURDIR, fname), "rb", "utf-8") as f:
        return f.read()


name = 'caelus'
version = '0.1.0'
author = 'Jose A Ruiz-Arias'
author_email = 'jararias@uma.es'
url = ''
description = (
    'Classification Algorithm for the Evaluation of the cLoUdless Situations'
)
keywords = ["solar irradiance", "sky classification", "variability", "python"]
classifiers = [
    "Natural Language :: English",
    "Intended Audience :: Developers",
    "Intended Audience :: Science/Research",
    "Programming Language :: Python :: 3.10",
    "Development Status :: 4 - Beta",
]

with open(f'{name}/_version.py', 'w') as f:
    f.write(f'__version__ = "{version}"\n')

setup(
    name=name,
    version=version,
    author=author,
    author_email=author_email,
    url=url,
    description=description,
    long_description=read_content('README.md'),
    long_description_content_type='text/markdown',
    keywords=keywords,
    classifiers=classifiers,
    packages=[name],
    install_requires=['numpy', 'pandas', 'scipy', 'loguru'],
)

if os.path.exists(f'{name}/_version.py'):
    os.remove(f'{name}/_version.py')
