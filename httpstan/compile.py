"""Runs the `stanc` binary in a subprocess to compile a Stan program."""

import importlib.resources as resources
import os
import subprocess
import tempfile
from pathlib import Path


def compile(program_code: str, stan_model_name: str) -> tuple[str, str]:
    """Return C++ code for Stan model specified by `program_code`.

    Arguments:
        program_code
        stan_model_name

    Returns:
        (str, str): C++ code, stanc warnings

    Raises:
        ValueError: Syntax or semantic error in program code.

    """
    stanc_file = resources.files(__package__).joinpath("stanc")

    with resources.as_file(stanc_file) as stanc_binary, tempfile.TemporaryDirectory(prefix="httpstan_") as tmpdir:
        filepath = Path(tmpdir) / f"{stan_model_name}.stan"
        filepath.write_text(program_code, encoding="utf-8")

        run_args: list[str | os.PathLike[str]] = [
            str(stanc_binary),
            "--name",
            stan_model_name,
            "--warn-pedantic",
            "--print-cpp",
            str(filepath),
        ]
        completed_process = subprocess.run(run_args, capture_output=True, text=True, timeout=5)
    stderr = completed_process.stderr.strip()
    if completed_process.returncode != 0:
        raise ValueError(stderr)
    return completed_process.stdout.strip(), stderr
