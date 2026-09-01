"""Command line interface."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quartocourse import __version__, config, render, toolchain

_STARTER_CONFIG = """\
[course]
title = "My Course"
code = "ABC101"
author = "A. Lecturer"
institution = "Some University"

[source]
# Directory of .ipynb files, relative to this file.
notebooks = "notebooks"
# Optional. Enables the GitHub / Colab links in the slide and PDF footers.
# repo = "https://github.com/you/my-course-notebooks"
# ref = "main"

[output]
slides = "build/slides"
notes = "build/notes"

# Optional. Omit the whole block to use the neutral defaults.
# [brand]
# font = '"Your Sans", sans-serif'   # CSS stack, slides
# pdf_font = "Your Sans"             # single Typst family, PDF
# accent = "#1f3a5f"
# body_font_size = "32px"
# css = ["extra.css"]

# Optional. Honour nbconvert slideshow metadata (slide_type). On by default;
# a no-op for notebooks that carry none.
# [compat]
# slide_type = true

# Optional. Rewrite absolute asset URLs to a local directory, so a build can
# use assets that exist locally but are not deployed yet.
# [render.url_rewrites]
# "https://example.edu/courses/" = "_local/"
# [render.mounts]
# _local = "../static/courses"
"""


def _add_target(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "target",
        nargs="?",
        default=".",
        type=Path,
        help="course.toml, or a directory containing one (default: .)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quartocourse",
        description="Render Jupyter notebooks into reveal.js slides and "
        "Typst PDF lecture notes via Quarto.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    render_p = sub.add_parser("render", help="render a course's notebooks")
    _add_target(render_p)
    render_p.add_argument(
        "-n", "--notebook", type=Path, help="render only this notebook"
    )
    group = render_p.add_mutually_exclusive_group()
    group.add_argument(
        "--slides-only", action="store_true", help="skip the PDF notes"
    )
    group.add_argument(
        "--notes-only", action="store_true", help="skip the reveal.js slides"
    )

    sub.add_parser("doctor", help="check the Quarto toolchain")

    init_p = sub.add_parser("init", help="write a starter course.toml")
    _add_target(init_p)

    return parser


def _cmd_render(args) -> int:
    cfg = config.load(args.target)
    quarto, version = toolchain.check()

    formats = render.FORMATS
    if args.slides_only:
        formats = (render.SLIDES,)
    elif args.notes_only:
        formats = (render.NOTES,)

    print(f"course   {cfg.course.title}")
    print(f"quarto   {'.'.join(str(p) for p in version)} ({quarto})")
    # Flush the block: stdout is block-buffered when piped, so without this
    # an error on stderr overtakes it.
    print(f"source   {cfg.source.notebooks}", flush=True)

    outputs = render.render_course(cfg, quarto, formats, only=args.notebook)
    print(f"\nWrote {len(outputs)} file(s):")
    for path in outputs:
        print(f"  {path}")
    return 0


def _cmd_init(args) -> int:
    target = Path(args.target)
    # A target naming a .toml is the file to write; anything else is the
    # course directory to write it into, whether or not it exists yet.
    # Branching on is_dir() alone would turn `init ./my-course` -- the first
    # thing anyone runs -- into a file literally named my-course.
    dest = target if target.suffix == ".toml" else target / config.CONFIG_FILENAME
    if dest.exists():
        print(f"{dest} already exists", file=sys.stderr)
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_STARTER_CONFIG)
    print(f"Wrote {dest}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "render":
            return _cmd_render(args)
        if args.command == "doctor":
            return toolchain.doctor()
        if args.command == "init":
            return _cmd_init(args)
    except (config.ConfigError, toolchain.ToolchainError, render.RenderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
