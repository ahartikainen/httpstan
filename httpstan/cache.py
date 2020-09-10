"""Cache management.

Functions in this module manage the Stan model cache and related caches.
"""
import gzip
import logging
import os
import pathlib

import appdirs

import httpstan

logger = logging.getLogger("httpstan")


def model_directory(model_name: str) -> str:
    """Get the path to a model's directory. Directory may not exist."""
    cache_path = appdirs.user_cache_dir("httpstan", version=httpstan.__version__)
    model_id = model_name.split("/")[1]
    return os.path.join(cache_path, "models", model_id)


def dump_services_extension_module_compiler_output(compiler_output: str, model_name: str) -> None:
    """Dump compiler output from building a model-specific stan::services extension module."""
    # may raise KeyError
    model_directory_ = pathlib.Path(model_directory(model_name))
    if not model_directory_.exists():
        raise KeyError(f"Directory for `{model_name}` at `{model_directory}` does not exist.")
    with open(model_directory_ / "stderr.log", "w") as fh:
        fh.write(compiler_output)


def load_services_extension_module_compiler_output(model_name: str) -> str:
    """Load compiler output from building a model-specific stan::services extension module."""
    # may raise KeyError
    model_directory_ = pathlib.Path(model_directory(model_name))
    if not model_directory_.exists():
        raise KeyError(f"Directory for `{model_name}` at `{model_directory}` does not exist.")
    with open(model_directory_ / "stderr.log") as fh:
        return fh.read()


def dump_fit(fit_bytes: bytes, name: str) -> None:
    """Store Stan fit in filesystem-based cache.

    The Stan fit is passed via ``fit_bytes``.

    This function is a coroutine.

    This function uses gzip to compress the cache.

    Arguments:
        name: Stan fit name
        fit_bytes: Bytes of the Stan fit.

    """
    cache_path = appdirs.user_cache_dir("httpstan", version=httpstan.__version__)
    # fits are stored under their "parent" models
    fit_path = os.path.join(*([cache_path] + name.split("/")[:-1]))
    fit_filename = os.path.join(fit_path, f'{name.split("/")[-1]}.dat.gz')
    os.makedirs(fit_path, exist_ok=True)
    with gzip.open(fit_filename, mode="wb") as fh:
        fh.write(fit_bytes)


def load_fit(name: str) -> bytes:
    """Load Stan fit from the filesystem-based cache.

    This function is a coroutine.

    This function uses gzip to decompress the cache.

    Arguments:
        name: Stan fit name
        model_name: Stan model name

    Returns
        bytes: Bytes of fit.

    """
    cache_path = appdirs.user_cache_dir("httpstan", version=httpstan.__version__)
    # fits are stored under their "parent" models
    fit_path = os.path.join(*([cache_path] + name.split("/")[:-1]))
    fit_filename = os.path.join(fit_path, f'{name.split("/")[-1]}.dat.gz')
    try:
        with gzip.open(fit_filename, mode="rb") as fh:
            return fh.read()
    except FileNotFoundError:
        raise KeyError(f"Fit `{name}` not found.")
