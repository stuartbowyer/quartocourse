"""Rendering orchestration: notebook -> reveal.js slides and Typst PDF notes."""
from __future__ import annotations

import html
import json
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from quartocourse import execute, metadata, preprocess
from quartocourse.config import Config, notebooks

SLIDES = "slides"
NOTES = "notes"
FORMATS = (SLIDES, NOTES)

_QUARTO_FORMAT = {SLIDES: "revealjs", NOTES: "typst"}


class RenderError(Exception):
    """A quarto render failed."""


def version_string(cfg: Config) -> str:
    """Footer version: date, plus the notebooks repo's short SHA if there is one."""
    if cfg.render.version:
        return cfg.render.version
    stamp = date.today().strftime("v.%Y-%m-%d")
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cfg.source.notebooks,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return stamp
    if sha.returncode != 0:
        return stamp
    return f"{stamp}_{sha.stdout.strip()}"


def slides_footer(cfg: Config, notebook: Path, version: str) -> str:
    """Four-column HTML footer: institution | author > code - title > lecture |
    version | Colab badge. Laid out by slides.css."""
    course = cfg.course
    lecture = html.escape(notebook.stem.replace("_", " "))
    trail = " &rsaquo; ".join(
        part
        for part in (
            html.escape(course.author),
            " &mdash; ".join(
                html.escape(p) for p in (course.code, course.title) if p
            ),
            f"<em>{lecture}</em>",
        )
        if part
    )
    cols = [
        f'<span class="col"><strong>{html.escape(course.institution)}</strong></span>'
        if course.institution
        else "",
        f'<span class="col">{trail}</span>',
        f'<span class="col col-version">{html.escape(version)}</span>',
    ]
    colab = cfg.colab_url(notebook.name)
    if colab:
        cols.append(
            '<span class="col col-colab">'
            f'<a href="{html.escape(colab)}" target="_blank">'
            '<img src="https://colab.research.google.com/assets/colab-badge.svg" '
            'alt="Open in Colab"/></a></span>'
        )
    return "".join(c for c in cols if c)


def typst_header(cfg: Config, notebook: Path, version: str = "") -> str:
    """Typst snippet setting the document font and the running header/footer.

    Header: course code/title left, lecture name right, so a reader flipping
    through knows where they are. Footer: institution and author left, page
    number centre, Colab badge right. The first page's footer also carries the
    version, so a downloaded or printed copy can be dated.

    Injected globally via include-in-header so every page after the TOC
    carries it. `article()` in Quarto's Typst template only overrides the
    font when its own params are set, so a single `set text` rule here is
    inherited by body, headings and cover title alike.
    """
    course = cfg.course
    lines: list[str] = []
    if cfg.brand.pdf_font:
        lines.append(f'#set text(font: "{cfg.brand.pdf_font}")')

    accent = f'rgb("{cfg.brand.accent}")'
    lecture = notebook.stem.replace("_", " ")
    code_title = " — ".join(p for p in (course.code, course.title) if p)
    institution_author = " · ".join(
        p for p in (course.institution, course.author) if p
    )

    footer_left = f"[{institution_author}]"
    if version:
        # A Typst string, not markup: the version's underscore would otherwise
        # start emphasis.
        quoted = json.dumps(version)
        sep = " · " if institution_author else ""
        footer_left = (
            f"[{institution_author}"
            f"#if counter(page).get().first() == 1 [{sep}#{quoted}]]"
        )

    colab = cfg.colab_url(notebook.name)
    # A text link rather than the Colab badge image: Typst's image() reads
    # local files only -- it cannot fetch a URL -- so an image here would mean
    # shipping a copy of Google's badge inside this package. The slides, being
    # HTML, link the badge from Google directly.
    badge = f'link("{colab}")[#underline[Open in Colab]]' if colab else "[]"

    lines.append(
        "#set page(\n"
        "  header: context [\n"
        f"    #set text(size: 8pt, fill: {accent})\n"
        "    #grid(\n"
        "      columns: (1fr, 1fr),\n"
        "      align: (left + horizon, right + horizon),\n"
        f"      [{code_title}],\n"
        f'      [#text(style: "italic")[{lecture}]],\n'
        "    )\n"
        "  ],\n"
        "  footer: context [\n"
        f"    #set text(size: 7pt, fill: {accent})\n"
        "    #grid(\n"
        "      columns: (1fr, auto, 1fr),\n"
        "      align: (left + horizon, center + horizon, right + horizon),\n"
        f"      {footer_left},\n"
        "      [#counter(page).display()],\n"
        f"      {badge},\n"
        "    )\n"
        "  ],\n"
        ")"
    )
    return "\n".join(lines)


def _run_quarto(
    quarto: Path,
    notebook: Path,
    fmt: str,
    output_dir: Path,
    metadata_file: Path,
    cfg: Config,
) -> None:
    """Render one notebook to one format, flat into output_dir.

    Sweeps Quarto's helper directories before and after. Both outputs embed
    their assets -- Typst inlines them, revealjs via embed-resources -- so
    these are pure build residue, and a stale one from an earlier run would
    otherwise linger in the published output.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    transient = [output_dir / f"{notebook.stem}_files"]
    transient += [output_dir / name for name in cfg.render.mounts]
    for d in transient:
        shutil.rmtree(d, ignore_errors=True)

    cmd = [
        str(quarto),
        "render",
        str(notebook),
        "--to",
        fmt,
        "--metadata-file",
        str(metadata_file),
        "--output-dir",
        str(output_dir),
        "--request-header",
        f"User-Agent:{cfg.render.user_agent}",
    ]
    # See toolchain.doctor: flush before the child writes to the same fd.
    print(f"   quarto render {notebook.name} -> {fmt}", flush=True)
    result = subprocess.run(cmd)
    for d in transient:
        shutil.rmtree(d, ignore_errors=True)
    if result.returncode != 0:
        raise RenderError(
            f"quarto render failed for {notebook.name} -> {fmt} "
            f"(exit {result.returncode})"
        )


def render_notebook(
    cfg: Config, notebook: Path, quarto: Path, formats=FORMATS, version: str = ""
) -> list[Path]:
    """Render one notebook to the requested formats. Returns output paths."""
    version = version or version_string(cfg)
    outputs: list[Path] = []

    # One temporary tree per notebook, removed on the way out. Both the
    # staged notebook and the staged assets have to outlive every quarto
    # call, so the lifetime is owned here rather than by the functions that
    # populate them.
    with tempfile.TemporaryDirectory(prefix="quartocourse-") as tmp:
        work = Path(tmp)
        source = json.loads(notebook.read_text())
        if cfg.execute.enabled:
            # Run once, so the slides and the notes show the same results.
            run_dir = work / "run"
            preprocess.stage_mounts(cfg, run_dir)
            print(f"   executing {notebook.name}", flush=True)
            source = execute.execute_notebook(
                source, cfg, run_dir, work, notebook.name
            )

        def stage(slides: bool) -> Path:
            variant = (
                execute.for_format(
                    source, slides, cfg.execute.reveal_outputs == "click"
                )
                if cfg.execute.enabled
                else source
            )
            execute.check_forbidden(variant, cfg.render.forbid, notebook.name)
            fmt = SLIDES if slides else NOTES
            return preprocess.prepare_notebook(
                variant, notebook.name, cfg, work / fmt
            )

        staged = metadata.stage_assets(cfg, work / "assets")

        if SLIDES in formats:
            meta = metadata.slides_metadata(
                cfg, staged, slides_footer(cfg, notebook, version)
            )
            meta_file = metadata.write(meta, work, "slides.yml")
            _run_quarto(
                quarto, stage(slides=True), _QUARTO_FORMAT[SLIDES],
                cfg.output.slides, meta_file, cfg,
            )
            outputs.append(cfg.output.slides / f"{notebook.stem}.html")

        if NOTES in formats:
            meta = metadata.notes_metadata(
                cfg, staged, notebook, typst_header(cfg, notebook, version)
            )
            meta_file = metadata.write(meta, work, "notes.yml")
            _run_quarto(
                quarto, stage(slides=False), _QUARTO_FORMAT[NOTES],
                cfg.output.notes, meta_file, cfg,
            )
            outputs.append(cfg.output.notes / f"{notebook.stem}.pdf")

    return outputs


def _match_notebook(
    cfg: Config, only: Path, all_notebooks: list[Path]
) -> Path:
    """Resolve a --notebook argument against the course, not just the cwd.

    A path written relative to the course -- `notebooks/01_Intro.ipynb`, the
    form the README uses -- would otherwise resolve against the caller's
    directory and miss whenever the command is run from outside the course.
    A bare filename works for the same reason.
    """
    only = Path(only).expanduser()
    for candidate in (only, cfg.source.notebooks / only, cfg.root / only):
        resolved = candidate.resolve()
        if resolved in all_notebooks:
            return resolved
    raise RenderError(
        f"{only} does not name a notebook in {cfg.source.notebooks}\n"
        f"  available: {', '.join(n.name for n in all_notebooks)}"
    )


def render_course(
    cfg: Config, quarto: Path, formats=FORMATS, only: Path | None = None
) -> list[Path]:
    """Render every notebook in the course (or just `only`)."""
    all_notebooks = notebooks(cfg)
    if not all_notebooks:
        raise RenderError(f"no .ipynb files in {cfg.source.notebooks}")

    if only is not None:
        all_notebooks = [_match_notebook(cfg, only, all_notebooks)]

    version = version_string(cfg)
    outputs: list[Path] = []
    for notebook in all_notebooks:
        print(f"\n-> {notebook.name}")
        outputs.extend(render_notebook(cfg, notebook, quarto, formats, version))
    return outputs
