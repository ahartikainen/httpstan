import os
import subprocess
import sys
import unittest.mock
from typing import Any

sys.path.insert(0, os.path.abspath(".."))
import httpstan

extensions = [
    "autoapi.extension",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

source_suffix = ".rst"
master_doc = "index"
project = "httpstan"
copyright = "2019, httpstan Developers"


intersphinx_mapping = {
    "python": ("http://python.readthedocs.io/en/latest/", None),
}

# use `git describe` because `httpstan.__version__` is not available on readthedocs
version = release = subprocess.check_output(["git", "describe", "--abbrev=0", "--always"]).decode().strip()

autoapi_dirs = [os.path.join("..", "httpstan")]
autoapi_ignore = [
    "*lib*",
    "*include*",
    "*views.py",
]


################################################################################
# theme configuration
################################################################################

# on_rtd is whether we are on readthedocs.org
on_rtd = os.environ.get("READTHEDOCS", None) == "True"

if not on_rtd:
    html_theme = "sphinx_rtd_theme"
