"""Notebook preprocessing.

Everything here runs on a temporary copy of the notebook. Source notebooks are
never modified, which matters when they are a pinned submodule or a shared
teaching repository.

Two kinds of work happen:

  - Compatibility. Translating nbconvert's slideshow metadata into Quarto's
    own slide separators (see `apply_slide_types`).
  - Format fixes. Adjusting markdown that Pandoc and Typst would otherwise
    mishandle, and staging the sibling files they resolve relatively.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from quartocourse.config import Config

_HTML_TABLE = re.compile(r"<table\b[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE)
# Link/image targets that a URL rewrite may apply to.
_MD_TARGET = re.compile(r"(\]\(\s*)([^)\s]+)")
_HTML_URL_ATTR = re.compile(
    r"""((?:src|href)\s*=\s*["'])([^"']*)""", re.IGNORECASE
)
# A heading at or above slide level, which already begins a slide on its own.
_OPENS_A_SLIDE = re.compile(r"^\s*#{1,2}(?!#)\s")

# Quarto's markdown equivalents for each nbconvert slide type.
SLIDE_BREAK = "---"
FRAGMENT = ". . ."
NOTES_OPEN = "::: {.notes}"
NOTES_CLOSE = ":::"


def apply_url_rewrites(src: str, rewrites: dict[str, str]) -> str:
    """Rewrite absolute URL prefixes in link and image targets.

    Paired with `mounts`, which links the corresponding directory in beside
    the notebook, so the result resolves against a local copy. Useful when a
    notebook references assets by their published URL but they are not
    deployed yet, and it avoids a network round-trip for those that are.

    Only markdown targets -- `](here)` -- and `src=`/`href=` attributes in
    embedded HTML are touched, and only where the prefix starts the target.
    Prose that happens to quote the same URL is left alone; a plain substring
    replacement over the whole cell would silently edit it.
    """
    if not rewrites:
        return src

    def rewrite(url: str) -> str:
        for prefix, replacement in rewrites.items():
            if url.startswith(prefix):
                return replacement + url[len(prefix):]
        return url

    def sub(match: re.Match) -> str:
        return match.group(1) + rewrite(match.group(2))

    return _HTML_URL_ATTR.sub(sub, _MD_TARGET.sub(sub, src))


def wrap_html_tables(src: str) -> str:
    """Fence each <table>...</table> block as raw HTML so Pandoc keeps it whole.

    Pandoc's `markdown_in_html_blocks` extension otherwise parses cell
    contents as markdown and the table structure collapses, which the Typst
    writer renders as one running paragraph instead of a grid. With the fence
    in place the table survives as a single element, and the Typst filter can
    re-parse it into a proper table.
    """
    return _HTML_TABLE.sub(lambda m: f"\n```{{=html}}\n{m.group(0)}\n```\n", src)


def opens_a_slide(cell: dict) -> bool:
    """Whether the cell already begins a slide by itself.

    A markdown cell leading with an H1 or H2 breaks the slide through Quarto's
    normal heading rule, so it needs no separator. Adding one anyway strands
    the rule in a slide of its own, which renders as a blank slide.
    """
    if cell.get("cell_type") != "markdown":
        return False
    source = cell.get("source", "")
    text = "".join(source) if isinstance(source, list) else source
    return bool(_OPENS_A_SLIDE.match(text.lstrip()))


def _markdown_cell(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": [text]}


def slide_type_of(cell: dict) -> str | None:
    """The cell's nbconvert slide type, if it carries one."""
    slideshow = cell.get("metadata", {}).get("slideshow")
    if not isinstance(slideshow, dict):
        return None
    value = slideshow.get("slide_type")
    return value if isinstance(value, str) else None


def apply_slide_types(cells: list[dict]) -> list[dict]:
    """Translate nbconvert slideshow metadata into Quarto markdown.

    Notebooks authored with JupyterLab's "Slide Type" control record where
    slides begin in cell metadata, and nbconvert's slides exporter reads it.
    Quarto's model is different: a slide begins at a heading or a horizontal
    rule, and its notebook renderer does not consult the metadata. A cell
    marked as a slide but titled with an H3 therefore does not begin one --
    it is absorbed into the preceding slide, silently and often heavily.

    This restores the intended structure using nbconvert's own mapping,
    expressed in the markdown Quarto documents:

        slide, subslide  ->  a horizontal rule before the cell
        fragment         ->  a pause before the cell
        notes            ->  the cell wrapped in a speaker-notes div
        skip             ->  the cell dropped
        "-", absent      ->  no change; the cell continues the current slide

    Separators are inserted as their own cells so the translation works for
    code cells as well as markdown. The slideshow metadata is left in place:
    it is the notebook's own record of intent, and this function is the only
    thing that reads it.

    Headings are deliberately untouched. Promoting an H3 to an H2 would also
    break the slide, but it would flatten the document's real structure, and
    that structure is what the PDF's outline and table of contents are built
    from.
    """
    out: list[dict] = []
    for cell in cells:
        slide_type = slide_type_of(cell)

        if slide_type == "skip":
            continue

        if slide_type in ("slide", "subslide"):
            # Skipped before the first cell (a leading rule opens on a blank
            # slide) and before a cell that already breaks on its own heading.
            if out and not opens_a_slide(cell):
                out.append(_markdown_cell(SLIDE_BREAK))
        elif slide_type == "fragment":
            out.append(_markdown_cell(FRAGMENT))
        elif slide_type == "notes":
            out.append(_markdown_cell(NOTES_OPEN))
            out.append(cell)
            out.append(_markdown_cell(NOTES_CLOSE))
            continue

        out.append(cell)
    return out


def _source_lines(text: str) -> list[str]:
    """nbformat stores cell source as a list of lines, each keeping its
    trailing newline except (optionally) the last."""
    return text.splitlines(keepends=True)


def prepare_notebook(notebook_path: Path, cfg: Config, dest_dir: Path) -> Path:
    """Write a render-ready copy of the notebook into dest_dir.

    The filename is preserved, because Quarto names its output from the input
    stem. dest_dir is caller-owned: the copy has to outlive every quarto call
    made against it, so this function does not manage its lifetime.
    """
    notebook = json.loads(notebook_path.read_text())
    cells = notebook.get("cells", [])

    if cfg.compat.slide_type:
        cells = apply_slide_types(cells)
    notebook["cells"] = cells

    for cell in cells:
        if cell.get("cell_type") != "markdown":
            continue
        source = cell.get("source", "")
        was_list = isinstance(source, list)
        original = "".join(source) if was_list else source

        updated = apply_url_rewrites(original, cfg.render.url_rewrites)
        updated = wrap_html_tables(updated)

        if updated != original:
            cell["source"] = _source_lines(updated) if was_list else updated

    dest_dir.mkdir(parents=True, exist_ok=True)
    staged = dest_dir / notebook_path.name
    staged.write_text(json.dumps(notebook, indent=1, ensure_ascii=False))

    for name, target in cfg.render.mounts.items():
        link = dest_dir / name
        if not link.exists():
            link.symlink_to(target)

    return staged
