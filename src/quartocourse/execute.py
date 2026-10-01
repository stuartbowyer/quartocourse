"""Render-time execution, and which outputs each format publishes.

When `[execute] enabled` is set, each notebook is run once on a temporary copy
and every saved output in the source is ignored. Publishing is then opt-in, cell
by cell, through tags in the cell metadata (invisible to students in Colab):

    show            output published in the slides and the notes
    show-on-click   output revealed on a click in the slides; hidden in the notes
    (no tag)        output hidden in both

A cell may raise an error only if it is tagged (the error is then what is shown)
or is a blank exercise -- a code cell containing the configured `blank` marker.
Any other error stops the render, so a real bug cannot pass unnoticed.

Hiding by default means a forgotten tag costs a missing output on a slide,
never a published one. That is the point for notebooks over sensitive data.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from quartocourse.config import Config

SHOW = "show"
SHOW_ON_CLICK = "show-on-click"

# nbclient's own tag: the cell may raise without stopping the run.
_RAISES = "raises-exception"
# Quarto's option for revealing a cell's output as the next fragment. It needs
# the cell's code echoed, which metadata.py sets for every render.
_FRAGMENT_OPTION = "#| output-location: fragment\n"
_KERNEL_NAME = "quartocourse"


class ExecutionError(Exception):
    """A notebook failed to execute, or would publish a forbidden output."""


def tags_of(cell: dict) -> list[str]:
    tags = cell.get("metadata", {}).get("tags", [])
    return tags if isinstance(tags, list) else []


def _source(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else source


def _as_lines(text: str) -> list[str]:
    """Source in the list-of-lines form saved notebooks use.

    Quarto loses the line breaks of a single-string markdown source in some
    notebooks (seen with Colab metadata), so nothing leaves this module as one.
    """
    return text.splitlines(keepends=True)


def is_blank(cell: dict, blank: str) -> bool:
    return bool(blank) and cell.get("cell_type") == "code" and blank in _source(cell)


def _write_kernelspec(python: Path, kernels_dir: Path) -> None:
    """A kernelspec for exactly this interpreter.

    Naming the interpreter directly avoids depending on which kernels happen to
    be installed on the machine, or on the notebook's own kernelspec name.
    """
    spec_dir = kernels_dir / _KERNEL_NAME
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "argv": [str(python), "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": _KERNEL_NAME,
        "language": "python",
    }
    (spec_dir / "kernel.json").write_text(json.dumps(spec))


def execute_notebook(
    notebook: dict, cfg: Config, cwd: Path, work: Path, name: str
) -> dict:
    """Run a copy of the notebook in `cwd`, returning it with fresh outputs.

    `work` holds the temporary kernelspec and is caller-owned, as `cwd` is:
    both must outlive the run.
    """
    # Imported here so courses that never execute do not pay for the import.
    import nbformat
    from jupyter_client.kernelspec import KernelSpecManager
    from jupyter_client.manager import KernelManager
    from nbclient import NotebookClient
    from nbclient.exceptions import CellExecutionError, CellTimeoutError
    from nbclient.exceptions import DeadKernelError

    nb = copy.deepcopy(notebook)
    for index, cell in enumerate(nb.get("cells", [])):
        # Saved notebooks store source as a list of lines; nbclient wants one
        # string. Older notebooks also lack the cell ids nbformat now expects.
        cell["source"] = _source(cell)
        cell.setdefault("id", f"quartocourse-{index}")
    nb = nbformat.from_dict(nb)
    allowed = []
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        tags = tags_of(cell)
        if SHOW in tags or SHOW_ON_CLICK in tags or is_blank(cell, cfg.execute.blank):
            if _RAISES not in tags:
                cell.metadata["tags"] = [*tags, _RAISES]
                allowed.append(cell)

    kernels_dir = work / "kernels"
    _write_kernelspec(cfg.execute.python, kernels_dir)
    km = KernelManager(
        kernel_name=_KERNEL_NAME,
        kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernels_dir)]),
    )
    client = NotebookClient(
        nb,
        km=km,
        timeout=cfg.execute.timeout,
        allow_errors=False,
        record_timing=False,
        resources={"metadata": {"path": str(cwd)}},
    )
    try:
        client.execute()
    except CellExecutionError as exc:
        raise ExecutionError(
            f"{name}: an untagged cell raised an error. Fix it, or tag it "
            f"'{SHOW}' or '{SHOW_ON_CLICK}' if the error is meant to be shown.\n"
            f"{exc}"
        ) from exc
    except (CellTimeoutError, DeadKernelError) as exc:
        raise ExecutionError(f"{name}: {exc}") from exc
    finally:
        # Only ever needed for the run, so not left to reach the output.
        for cell in allowed:
            cell.metadata["tags"].remove(_RAISES)
    out = nbformat.from_dict(nb)
    for cell in out.cells:
        cell.source = _as_lines(cell.source)
    return out


def for_format(notebook: dict, slides: bool) -> dict:
    """The executed notebook as one format publishes it.

    Untagged code cells lose their outputs. `show-on-click` keeps its output in
    the slides, revealed as a fragment, and loses it in the notes.
    """
    out = copy.deepcopy(notebook)
    for cell in out.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        tags = tags_of(cell)
        shown = SHOW in tags or (SHOW_ON_CLICK in tags and slides)
        if not shown:
            cell["outputs"] = []
            cell["execution_count"] = None
        elif SHOW_ON_CLICK in tags:
            cell["source"] = _as_lines(_FRAGMENT_OPTION + _source(cell))
    return out


def _published_text(cell: dict) -> str:
    parts: list[str] = []
    for output in cell.get("outputs", []):
        text = output.get("text", "")
        parts.append("".join(text) if isinstance(text, list) else text)
        for value in output.get("data", {}).values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.append("".join(v for v in value if isinstance(v, str)))
        parts += [output.get("ename", ""), output.get("evalue", "")]
        parts += output.get("traceback", [])
    return "\n".join(parts)


def check_forbidden(notebook: dict, patterns: tuple[str, ...], name: str) -> None:
    """Fail if any output about to be published matches a forbidden pattern.

    A backstop, not the control: it sees text, so it cannot catch values in an
    image or rows that carry no identifying column.
    """
    if not patterns:
        return
    compiled = [re.compile(p) for p in patterns]
    for index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        text = _published_text(cell)
        for pattern in compiled:
            if pattern.search(text):
                first_line = _source(cell).strip().splitlines()[:1]
                raise ExecutionError(
                    f"{name}: output of cell {index} matches forbidden pattern "
                    f"{pattern.pattern!r}: {first_line[0] if first_line else ''}"
                )
