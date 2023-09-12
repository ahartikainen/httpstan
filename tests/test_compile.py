"""Test compiling functions."""
import re

import aiohttp
import pytest

import httpstan.compile


def test_compile() -> None:
    program_code = "parameters {real y;} model {y ~ normal(0,1);}"
    cpp_code, warnings = httpstan.compile.compile(program_code, "test_model")
    assert "Code generated by stanc" in cpp_code and warnings == ""


def test_compile_syntax_error() -> None:
    # program code is missing a `{`
    program_code = "parameters {real y;} model y ~ normal(0,1);}"
    with pytest.raises(ValueError, match=r"Syntax error in"):
        httpstan.compile.compile(program_code, "test_model")


def test_compile_semantic_error() -> None:
    program_code = "parameters {real z;} model {z ~ no_such_distribution();}"
    with pytest.raises(ValueError, match=r"Semantic error in"):
        httpstan.compile.compile(program_code, "test_model")


@pytest.mark.asyncio
async def test_build_invalid_distribution(api_url: str) -> None:
    """Check that compiler error is returned to client."""

    program_code = "parameters {real z;} model {z ~ no_such_distribution();}"
    payload = {"program_code": program_code}
    models_url = f"{api_url}/models"
    async with aiohttp.ClientSession() as session:
        async with session.post(models_url, json=payload) as resp:
            assert resp.status == 400
            response_payload = await resp.json()
    assert "message" in response_payload
    assert "Semantic error in" in response_payload["message"]


def test_compile_filename() -> None:
    program_code = "parameters {real y;} model {y ~ normal(0,1);}"
    cpp_code, _ = httpstan.compile.compile(program_code, "test_model")
    assert re.search(r"httpstan_\S+/test_model.stan", cpp_code)


@pytest.mark.asyncio
async def test_build_unknown_arg(api_url: str) -> None:
    """Check that compiler error is returned to client.

    This error can be detected by schema validation.

    """

    program_code = "parameters {real z;} model {z ~ no_such_distribution();}"
    payload = {"unknown_arg": "abcdef", "program_code": program_code}
    models_url = f"{api_url}/models"
    async with aiohttp.ClientSession() as session:
        async with session.post(models_url, json=payload) as resp:
            assert resp.status == 422
            response_payload = await resp.json()
    assert "json" in response_payload and "unknown_arg" in response_payload["json"]


@pytest.mark.asyncio
async def test_build_integer_division_warning(api_url: str) -> None:
    """Test building which succeeds but which generates an integer division warning."""

    # prints integer division warning
    program_code = "parameters {real y;} model {y ~ normal(0,1/5);}"

    payload = {"program_code": program_code}
    models_url = f"{api_url}/models"
    async with aiohttp.ClientSession() as session:
        async with session.post(models_url, json=payload) as resp:
            assert resp.status == 201
            response_payload = await resp.json()
    assert "compiler_output" in response_payload
    assert "stanc_warnings" in response_payload
    assert "int division" in response_payload["stanc_warnings"]
