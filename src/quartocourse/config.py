"""Course configuration.

A course is described by one TOML file (conventionally `course.toml`).
Everything institution-, site- or person-specific lives there; nothing in
this package carries branding of its own.

All relative paths in the file resolve against the file's own directory, so
a course is relocatable.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = "course.toml"

# Neutral defaults. A course that sets no [brand] block still renders a
# presentable deck -- that is the test of whether the package is genuinely
# unbranded.
DEFAULT_FONT = (
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, '
    '"Helvetica Neue", Arial, sans-serif'
)
DEFAULT_ACCENT = "#1f3a5f"
DEFAULT_BODY_FONT_SIZE = "32px"


class ConfigError(Exception):
    """Raised for a malformed or incomplete course.toml."""


@dataclass(frozen=True)
class Course:
    title: str
    code: str = ""
    author: str = ""
    institution: str = ""


@dataclass(frozen=True)
class Source:
    notebooks: Path
    repo: str = ""
    ref: str = "main"
    # Path of `notebooks` within its git repo ("" at the root, else ending
    # in "/"), so repo links resolve when notebooks live in a subdirectory.
    repo_prefix: str = ""


@dataclass(frozen=True)
class Output:
    slides: Path
    notes: Path


@dataclass(frozen=True)
class Brand:
    # CSS font stack for the slides.
    font: str = DEFAULT_FONT
    # Single Typst font family for the PDF. Empty leaves Quarto's default in
    # place. Kept separate from `font` because Typst takes one family name,
    # not a stack, and because a brand font is often licensed and therefore
    # absent on a colleague's machine.
    pdf_font: str = ""
    accent: str = DEFAULT_ACCENT
    body_font_size: str = DEFAULT_BODY_FONT_SIZE
    # Extra stylesheets layered after the built-in one.
    css: tuple[Path, ...] = ()


@dataclass(frozen=True)
class Render:
    # Some hosts (Wikimedia among them) refuse downloads without a UA, and
    # return a rate-limit page that Quarto happily saves as if it were the
    # image. Identify ourselves.
    user_agent: str = (
        "Mozilla/5.0 (compatible; quartocourse/1.0; "
        "+https://github.com/stuartbowyer/quartocourse)"
    )
    # Fixed version string for the slide footer. Empty means derive it
    # (date + notebooks-repo short SHA).
    version: str = ""
    # Absolute URL prefix -> path relative to the notebook at render time.
    # Lets a build use assets that are in the working tree but not yet
    # deployed, and avoids network round-trips for ones that are.
    url_rewrites: dict[str, str] = field(default_factory=dict)
    # Name -> directory symlinked in beside the notebook, so the rewritten
    # relative paths above resolve to the working-tree copy.
    mounts: dict[str, Path] = field(default_factory=dict)
    # Regexes that must not appear in any published output. Checked whether or
    # not notebooks are executed; a match fails the render.
    forbid: tuple[str, ...] = ()


@dataclass(frozen=True)
class Execute:
    # Run each notebook at render time and publish only the outputs of cells
    # tagged `show` or `answer` (see execute.py). Off renders the saved
    # outputs as they are, and the tags are ignored.
    enabled: bool = False
    # Interpreter for the kernel; it needs ipykernel and the notebooks' own
    # dependencies. Defaults to the interpreter running quartocourse.
    python: Path = Path(sys.executable)
    # Per cell, in seconds.
    timeout: int = 600
    # A code cell containing this is an exercise left blank for students: it
    # may error, and its output is hidden unless tagged.
    blank: str = "____"
    # "immediate" shows published outputs in the slides as soon as the slide
    # appears; "click" reveals each on the next click. Answers always wait.
    reveal_outputs: str = "immediate"


@dataclass(frozen=True)
class Compat:
    # Honour nbconvert's slideshow metadata (`slide_type`) if the notebooks
    # carry it. A no-op for notebooks that do not, so it is on by default:
    # the alternative is that such a deck renders wrongly and the reader has
    # to work out why before discovering the switch.
    slide_type: bool = True


@dataclass(frozen=True)
class Config:
    path: Path
    root: Path
    course: Course
    source: Source
    output: Output
    brand: Brand
    render: Render
    execute: Execute
    compat: Compat

    def github_url(self, notebook_filename: str) -> str:
        """Blob URL for a notebook, pinned to the course's published ref."""
        if not self.source.repo:
            return ""
        base = self.source.repo.rstrip("/").removesuffix(".git")
        path = f"{self.source.repo_prefix}{notebook_filename}"
        return f"{base}/blob/{self.source.ref}/{path}"

    def colab_url(self, notebook_filename: str) -> str:
        url = self.github_url(notebook_filename)
        if not url:
            return ""
        return url.replace("github.com", "colab.research.google.com/github")


def _require(table: dict, key: str, where: str):
    if key not in table or table[key] in (None, ""):
        raise ConfigError(f"{where}: missing required key '{key}'")
    return table[key]


def _repo_prefix(directory: Path) -> str:
    """`directory`'s path within its git repo; "" if at the root or not in git."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-prefix"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def resolve_config_path(target: Path) -> Path:
    """Accept either a course.toml or a directory containing one."""
    target = Path(target).expanduser().resolve()
    if target.is_dir():
        candidate = target / CONFIG_FILENAME
        if not candidate.is_file():
            raise ConfigError(f"no {CONFIG_FILENAME} in {target}")
        return candidate
    if not target.is_file():
        raise ConfigError(f"{target} does not exist")
    return target


def load(target: Path) -> Config:
    path = resolve_config_path(target)
    root = path.parent
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc

    def rel(p: str) -> Path:
        return (root / p).resolve() if not Path(p).is_absolute() else Path(p)

    course_t = raw.get("course", {})
    course = Course(
        title=_require(course_t, "title", f"{path} [course]"),
        code=course_t.get("code", ""),
        author=course_t.get("author", ""),
        institution=course_t.get("institution", ""),
    )

    source_t = raw.get("source", {})
    notebooks = rel(source_t.get("notebooks", "notebooks"))
    if not notebooks.is_dir():
        raise ConfigError(
            f"{path} [source]: notebooks directory not found: {notebooks}\n"
            "  (if it is a git submodule, run: git submodule update --init)"
        )
    repo = source_t.get("repo", "")
    source = Source(
        notebooks=notebooks,
        repo=repo,
        ref=source_t.get("ref", "main"),
        repo_prefix=_repo_prefix(notebooks) if repo else "",
    )

    output_t = raw.get("output", {})
    output = Output(
        slides=rel(output_t.get("slides", "build/slides")),
        notes=rel(output_t.get("notes", "build/notes")),
    )

    brand_t = raw.get("brand", {})
    brand = Brand(
        font=brand_t.get("font", DEFAULT_FONT),
        pdf_font=brand_t.get("pdf_font", ""),
        accent=brand_t.get("accent", DEFAULT_ACCENT),
        body_font_size=brand_t.get("body_font_size", DEFAULT_BODY_FONT_SIZE),
        css=tuple(rel(c) for c in brand_t.get("css", [])),
    )
    for extra in brand.css:
        if not extra.is_file():
            raise ConfigError(f"{path} [brand]: css file not found: {extra}")

    render_t = raw.get("render", {})
    render = Render(
        user_agent=render_t.get("user_agent", Render.user_agent),
        version=render_t.get("version", ""),
        url_rewrites=dict(render_t.get("url_rewrites", {})),
        mounts={k: rel(v) for k, v in render_t.get("mounts", {}).items()},
        forbid=tuple(render_t.get("forbid", [])),
    )
    for pattern in render.forbid:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigError(
                f"{path} [render]: forbid pattern {pattern!r} is invalid: {exc}"
            ) from exc
    for name, target_dir in render.mounts.items():
        # The name becomes a symlink beside the staged notebook and a
        # directory swept from the output directory after each render, so
        # anything with a separator or a `..` in it would escape both.
        if not name or name in (".", "..") or "/" in name or "\\" in name:
            raise ConfigError(
                f"{path} [render.mounts]: '{name}' is not a usable mount name; "
                "it must be a single directory name"
            )
        if not target_dir.is_dir():
            raise ConfigError(
                f"{path} [render.mounts]: '{name}' -> {target_dir} is not a directory"
            )

    execute_t = raw.get("execute", {})
    # Not resolved: a venv's bin/python is a symlink, and following it would
    # start the base interpreter without the venv's packages.
    python = Path(execute_t.get("python", Execute.python))
    execute = Execute(
        enabled=bool(execute_t.get("enabled", False)),
        python=python if python.is_absolute() else root / python,
        timeout=int(execute_t.get("timeout", Execute.timeout)),
        blank=execute_t.get("blank", Execute.blank),
        reveal_outputs=execute_t.get("reveal_outputs", Execute.reveal_outputs),
    )
    if execute.reveal_outputs not in ("immediate", "click"):
        raise ConfigError(
            f"{path} [execute]: reveal_outputs must be \"immediate\" or \"click\""
        )
    if execute.enabled and not execute.python.is_file():
        raise ConfigError(
            f"{path} [execute]: python interpreter not found: {execute.python}"
        )
    if execute.timeout <= 0:
        raise ConfigError(f"{path} [execute]: timeout must be positive")

    compat_t = raw.get("compat", {})
    compat = Compat(slide_type=bool(compat_t.get("slide_type", True)))

    return Config(
        path=path,
        root=root,
        course=course,
        source=source,
        output=output,
        brand=brand,
        render=render,
        execute=execute,
        compat=compat,
    )


def notebooks(cfg: Config) -> list[Path]:
    """Every notebook in the course, in filename order."""
    return sorted(cfg.source.notebooks.glob("*.ipynb"))
