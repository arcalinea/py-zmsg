# -*- coding: utf-8 -*-

import re
from setuptools import setup

version = re.search(
    '^__version__\s*=\s*"(.*)"',
    open('zmsg/zmsg.py').read(),
    re.M
    ).group(1)

with open("README.md", "rb") as f:
    long_descr = f.read().decode("utf-8")

setup(
    name = "py-zmsg",
    packages = ["zmsg"],
    entry_points = {
        "console_scripts": ['zmsg = zmsg.zmsg:main']
        },
    version = version,
    description = "Python command line application to send and receive messages in the encrypted memo field of Zcash shielded transactions.",
    long_description = long_descr,
    author = "arcalinea",
    author_email = "arcalinea@z.cash",
    url = "http://github.com/arcalinea/zmsg",
    )
