import pytest

from quartocourse import config
from quartocourse.execute import (
    SHOW,
    SHOW_ON_CLICK,
    ExecutionError,
    check_forbidden,
    execute_notebook,
    for_format,
    is_blank,
)


def code(source, tags=(), outputs=None):
    return {
        "cell_type": "code",
        "execution_count": 1,
        "metadata": {"tags": list(tags)} if tags else {},
        "outputs": outputs if outputs is not None else [stream("out\n")],
        "source": source,
    }


def stream(text):
    return {"name": "stdout", "output_type": "stream", "text": text}


def notebook(*cells):
    return {
        "cells": list(cells),
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


class TestForFormat:
    def test_untagged_output_is_hidden_in_both(self):
        nb = notebook(code("x"))
        for slides in (True, False):
            cell = for_format(nb, slides)["cells"][0]
            assert cell["outputs"] == []
            assert cell["execution_count"] is None

    def test_show_is_published_in_both(self):
        nb = notebook(code("x", [SHOW]))
        for slides in (True, False):
            assert for_format(nb, slides)["cells"][0]["outputs"]

    def test_show_on_click_is_a_fragment_in_the_slides(self):
        cell = for_format(notebook(code("x", [SHOW_ON_CLICK])), True)["cells"][0]
        assert cell["outputs"]
        assert cell["source"].startswith("#| output-location: fragment\n")

    def test_show_on_click_is_hidden_in_the_notes(self):
        cell = for_format(notebook(code("x", [SHOW_ON_CLICK])), False)["cells"][0]
        assert cell["outputs"] == []
        assert "output-location" not in cell["source"]

    def test_markdown_is_untouched(self):
        md = {"cell_type": "markdown", "metadata": {}, "source": "# Hi"}
        assert for_format(notebook(md), True)["cells"][0] == md

    def test_does_not_modify_its_input(self):
        nb = notebook(code("x"))
        for_format(nb, True)
        assert nb["cells"][0]["outputs"]


class TestIsBlank:
    def test_code_cell_with_the_marker(self):
        assert is_blank(code("total = ____"), "____")

    def test_markdown_with_the_marker_is_not_a_blank(self):
        md = {"cell_type": "markdown", "source": "Blanks look like `____`"}
        assert not is_blank(md, "____")

    def test_empty_marker_disables_detection(self):
        assert not is_blank(code("total = ____"), "")


class TestCheckForbidden:
    def test_match_in_published_output_fails(self):
        nb = notebook(code("df", [SHOW], [stream("hadm_id  sodium\n")]))
        with pytest.raises(ExecutionError, match="hadm_id"):
            check_forbidden(nb, ("hadm_id",), "L3.ipynb")

    def test_reads_rich_and_error_outputs(self):
        html = {
            "output_type": "display_data",
            "data": {"text/html": ["<td>stay_id</td>"]},
        }
        error = {
            "output_type": "error",
            "ename": "KeyError",
            "evalue": "'subject_id'",
            "traceback": [],
        }
        for output in (html, error):
            with pytest.raises(ExecutionError):
                check_forbidden(
                    notebook(code("x", [SHOW], [output])),
                    ("stay_id", "subject_id"),
                    "L3.ipynb",
                )

    def test_hidden_output_is_not_published_so_passes(self):
        nb = for_format(notebook(code("df", outputs=[stream("hadm_id\n")])), True)
        check_forbidden(nb, ("hadm_id",), "L3.ipynb")

    def test_no_patterns_never_fails(self):
        check_forbidden(notebook(code("x", [SHOW])), (), "L3.ipynb")


class TestExecuteNotebook:
    """Runs a real kernel, using the interpreter running the tests."""

    def _cfg(self, tmp_path):
        (tmp_path / "notebooks").mkdir()
        path = tmp_path / "course.toml"
        path.write_text('[course]\ntitle = "T"\n\n[execute]\nenabled = true\n')
        return config.load(path)

    def _run(self, tmp_path, *cells):
        cfg = self._cfg(tmp_path)
        nb = notebook(*[code(src, tags, outputs=[]) for src, tags in cells])
        return execute_notebook(nb, cfg, tmp_path, tmp_path, "T.ipynb")

    def test_outputs_are_fresh(self, tmp_path):
        out = self._run(tmp_path, ("x = 2", ()), ("print(x * 21)", [SHOW]))
        assert out["cells"][1]["outputs"][0]["text"] == "42\n"

    def test_shown_and_blank_cells_may_error(self, tmp_path):
        out = self._run(
            tmp_path,
            ('print("37.5" + 1)', [SHOW]),
            ("____", ()),
            ("print('still running')", [SHOW]),
        )
        assert out["cells"][0]["outputs"][0]["ename"] == "TypeError"
        assert out["cells"][2]["outputs"][0]["text"] == "still running\n"

    def test_an_untagged_error_stops_the_render(self, tmp_path):
        with pytest.raises(ExecutionError, match="untagged cell"):
            self._run(tmp_path, ("1 / 0", ()))

    def test_runs_in_the_given_directory(self, tmp_path):
        (tmp_path / "data.txt").write_text("hello")
        out = self._run(tmp_path, ("print(open('data.txt').read())", [SHOW]))
        assert out["cells"][0]["outputs"][0]["text"] == "hello\n"
