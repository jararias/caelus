import platform
from setuptools import setup
from setuptools.config import read_configuration


cfg = read_configuration('setup.cfg')

with open(f"{cfg['metadata']['name']}/version.py", 'w') as fh:
    fh.write("# THIS FILE IS GENERATED BY `setup.py`\n")
    fh.write(f"version = '{cfg['metadata']['version']}'\n")
    fh.write(f"platform_machine = '{platform.machine()}'\n")

with open('requirements.txt') as fh:
    requirements = fh.read().splitlines()

setup(install_requires=requirements)
