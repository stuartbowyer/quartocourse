"""Drift guards for the pinned Quarto version.

PINNED_VERSION, the `quarto` extra and the supported range are three
statements of the same fact in two files. Nothing enforces that at import
time, and a mismatch surfaces only as an opaque pandoc or Lua failure at
render time -- see the toolchain module docstring.
"""
import tomllib
from pathlib import Path

from quartocourse import toolchain

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


class TestPinnedVersion:
    def test_matches_the_quarto_extra_in_pyproject(self):
        raw = tomllib.loads(PYPROJECT.read_text())
        extra = raw["project"]["optional-dependencies"]["quarto"]
        assert extra == [f"quarto-cli=={toolchain.PINNED_VERSION}"]

    def test_falls_inside_the_supported_range(self):
        pinned = tuple(int(p) for p in toolchain.PINNED_VERSION.split("."))
        assert toolchain.MIN_VERSION <= pinned < toolchain.BELOW_VERSION
