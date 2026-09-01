"""Locating and version-checking the Quarto toolchain.

Quarto's own distribution bundles the exact pandoc, typst, deno and dart-sass
it needs, so pinning Quarto pins the whole toolchain. The `quarto` extra in
pyproject.toml installs an exact version; this module verifies whatever is
actually on PATH matches, because a mismatch produces failures that are
essentially undiagnosable without knowing to look here:

  - quarto 1.9.x with pandoc < 3.8  ->  "Aeson exception: Unknown option
    syntax-highlighting" (quarto emits the new defaults key, pandoc rejects it)
  - quarto 1.8.x with pandoc 3.7.x  ->  jog.lua "Don't know how to traverse
    TableBody" whenever a document contains a table

Both surface as a wall of Haskell or Lua trace with no mention of versions.
"""
from __future__ import annotations

import os
import re
import sys
import shutil
import subprocess
from pathlib import Path

# The version pinned by the `quarto` extra. Keep in sync with pyproject.toml.
PINNED_VERSION = "1.9.37"

# Range this package's metadata and filters are known to work against.
MIN_VERSION = (1, 9, 37)
BELOW_VERSION = (1, 10, 0)

ENV_VAR = "QUARTOCOURSE_QUARTO"

_REPO_URL = "git+https://github.com/stuartbowyer/quartocourse"

_INSTALL_HINT = (
    "Install the pinned toolchain with either:\n"
    "  uv sync --extra quarto     (working on this repo)\n"
    f'  uv tool install "quartocourse[quarto] @ {_REPO_URL}"\n'
    f"or put Quarto {PINNED_VERSION} on PATH yourself, or point "
    f"${ENV_VAR} at the binary."
)


class ToolchainError(Exception):
    """Quarto is missing, unreadable, or the wrong version."""


def _fmt(v: tuple[int, ...]) -> str:
    return ".".join(str(p) for p in v)


def _bundled_quarto() -> Path | None:
    """The quarto installed alongside us by the `quarto` extra, if any.

    It sits in the same directory as the running interpreter -- the project
    venv under `uv sync`, or the tool venv under `uv tool install`. The latter
    matters: uv links only the target package's own executables onto PATH, so
    a tool-installed quarto is invisible to `shutil.which` and would otherwise
    be missed in favour of whatever system quarto happens to be around.
    """
    exe = Path(sys.executable).parent / "quarto"
    return exe if exe.is_file() else None


def find_quarto() -> Path:
    """$QUARTOCOURSE_QUARTO, else the quarto installed with us, else PATH."""
    override = os.environ.get(ENV_VAR)
    if override:
        exe = Path(override).expanduser()
        if not exe.is_file():
            raise ToolchainError(f"${ENV_VAR} is set to {exe}, which is not a file")
        return exe

    # The pinned one wins over an arbitrary system install -- pinning it is
    # the whole point of the extra.
    bundled = _bundled_quarto()
    if bundled:
        return bundled

    found = shutil.which("quarto")
    if not found:
        raise ToolchainError("quarto was not found on PATH.\n\n" + _INSTALL_HINT)
    return Path(found)


def version(exe: Path) -> tuple[int, ...]:
    try:
        out = subprocess.run(
            [str(exe), "--version"], capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolchainError(f"could not run '{exe} --version': {exc}") from exc
    if out.returncode != 0:
        raise ToolchainError(
            f"'{exe} --version' exited {out.returncode}: {out.stderr.strip()}"
        )
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", out.stdout)
    if not match:
        raise ToolchainError(f"could not parse a version from: {out.stdout.strip()!r}")
    return tuple(int(g) for g in match.groups())


def check() -> tuple[Path, tuple[int, ...]]:
    """Resolve Quarto and assert it is in the supported range.

    Returns (path, version). Raises ToolchainError with an actionable message.
    """
    exe = find_quarto()
    found = version(exe)
    if not (MIN_VERSION <= found < BELOW_VERSION):
        raise ToolchainError(
            f"Quarto {_fmt(found)} at {exe} is outside the supported range "
            f"(>= {_fmt(MIN_VERSION)}, < {_fmt(BELOW_VERSION)}).\n\n"
            + _INSTALL_HINT
        )
    return exe, found


def doctor() -> int:
    """Report toolchain status, then hand off to `quarto check`."""
    try:
        exe = find_quarto()
    except ToolchainError as exc:
        print(f"FAIL  {exc}")
        return 1

    print(f"quarto binary   {exe}")
    try:
        found = version(exe)
    except ToolchainError as exc:
        print(f"FAIL  {exc}")
        return 1

    supported = MIN_VERSION <= found < BELOW_VERSION
    print(f"quarto version  {_fmt(found)}")
    print(
        f"supported range >= {_fmt(MIN_VERSION)}, < {_fmt(BELOW_VERSION)}  "
        f"[{'OK' if supported else 'MISMATCH'}]"
    )
    if not supported:
        print()
        print(_INSTALL_HINT)
        return 1

    print()
    print("--- quarto check ---")
    # Our stdout is block-buffered when piped, but the subprocess writes
    # straight to the fd -- without a flush its output lands first.
    sys.stdout.flush()
    # quarto check verifies its own bundled pandoc/typst/deno/dart-sass.
    return subprocess.run([str(exe), "check"]).returncode
