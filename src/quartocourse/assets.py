"""Access to the packaged Quarto assets.

The payload lives in the `_assets` data package rather than an `assets/`
directory, because `quartocourse.assets` already names this module and
importlib.resources would resolve to this file's parent instead.

Quarto needs real filesystem paths, and package data may live inside a zip,
so callers stage what they need into a directory rather than passing a
resource path straight to the CLI. Staged paths are absolute, which is
what Quarto's metadata file needs: relative paths in it resolve against
the input notebook, not against the metadata file.
"""
from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

SLIDES_CSS = "slides.css"
REVEAL_TITLE_SLIDE_LUA = "reveal-title-slide.lua"
TYPST_FORMAT_LUA = "typst-format.lua"


def _resource(name: str):
    return resources.files("quartocourse._assets").joinpath(name)


def read_bytes(name: str) -> bytes:
    return _resource(name).read_bytes()


def read_text(name: str) -> str:
    return _resource(name).read_text(encoding="utf-8")


def stage(name: str, dest_dir: Path) -> Path:
    """Materialise a packaged asset into dest_dir and return its path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    dest.write_bytes(read_bytes(name))
    return dest


def stage_external(source: Path, dest_dir: Path) -> Path:
    """Copy a user-supplied asset (e.g. an extra stylesheet) into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source.name
    shutil.copyfile(source, dest)
    return dest
