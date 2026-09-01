from quartocourse.preprocess import (
    FRAGMENT,
    NOTES_CLOSE,
    NOTES_OPEN,
    SLIDE_BREAK,
    _source_lines,
    apply_slide_types,
    apply_url_rewrites,
    slide_type_of,
    wrap_html_tables,
)


def cell(text, slide_type=None, cell_type="markdown"):
    meta = {"slideshow": {"slide_type": slide_type}} if slide_type else {}
    return {"cell_type": cell_type, "metadata": meta, "source": [text]}


def texts(cells):
    return ["".join(c["source"]) for c in cells]


class TestSlideTypeOf:
    def test_reads_the_slide_type(self):
        assert slide_type_of(cell("x", "slide")) == "slide"

    def test_absent_metadata(self):
        assert slide_type_of(cell("x")) is None

    def test_tolerates_a_malformed_slideshow_value(self):
        assert slide_type_of({"metadata": {"slideshow": "nonsense"}}) is None


class TestApplySlideTypes:
    def test_slide_inserts_a_break(self):
        out = apply_slide_types([cell("## A"), cell("### B", "slide")])
        assert texts(out) == ["## A", SLIDE_BREAK, "### B"]

    def test_subslide_also_breaks(self):
        out = apply_slide_types([cell("## A"), cell("### B", "subslide")])
        assert texts(out) == ["## A", SLIDE_BREAK, "### B"]

    def test_no_leading_break_before_the_first_cell(self):
        out = apply_slide_types([cell("## A", "slide")])
        assert texts(out) == ["## A"]

    def test_skip_drops_the_cell(self):
        out = apply_slide_types([cell("## A"), cell("gone", "skip")])
        assert texts(out) == ["## A"]

    def test_fragment_inserts_a_pause(self):
        out = apply_slide_types([cell("## A"), cell("more", "fragment")])
        assert texts(out) == ["## A", FRAGMENT, "more"]

    def test_notes_are_wrapped(self):
        out = apply_slide_types([cell("## A"), cell("aside", "notes")])
        assert texts(out) == ["## A", NOTES_OPEN, "aside", NOTES_CLOSE]

    def test_dash_and_absent_continue_the_slide(self):
        out = apply_slide_types([cell("## A"), cell("b", "-"), cell("c")])
        assert texts(out) == ["## A", "b", "c"]

    def test_separator_precedes_a_code_cell(self):
        out = apply_slide_types([cell("## A"), cell("print(1)", "slide", "code")])
        assert texts(out) == ["## A", SLIDE_BREAK, "print(1)"]
        assert out[1]["cell_type"] == "markdown"

    def test_headings_are_never_rewritten(self):
        out = apply_slide_types([cell("## A"), cell("### B", "slide")])
        assert "### B" in texts(out)

    def test_notebook_without_metadata_is_unchanged(self):
        cells = [cell("## A"), cell("## B")]
        assert texts(apply_slide_types(cells)) == texts(cells)


class TestWrapHtmlTables:
    def test_wraps_in_raw_html_fence(self):
        out = wrap_html_tables("<table><tr><td>a</td></tr></table>")
        assert "```{=html}" in out and "<table>" in out

    def test_leaves_plain_markdown_alone(self):
        src = "| a | b |\n| - | - |\n"
        assert wrap_html_tables(src) == src

    def test_handles_attributes_and_multiline(self):
        src = '<table class="x">\n<tr><td>a</td></tr>\n</table>'
        assert wrap_html_tables(src).count("```{=html}") == 1


class TestApplyUrlRewrites:
    REWRITES = {"https://example.edu/courses/": "_local/"}

    def test_rewrites_a_markdown_image_target(self):
        out = apply_url_rewrites(
            "![x](https://example.edu/courses/img.png)", self.REWRITES
        )
        assert out == "![x](_local/img.png)"

    def test_rewrites_an_html_src_attribute(self):
        out = apply_url_rewrites(
            '<img src="https://example.edu/courses/img.png">', self.REWRITES
        )
        assert out == '<img src="_local/img.png">'

    def test_leaves_prose_alone(self):
        src = "assets live at https://example.edu/courses/ until deployed"
        assert apply_url_rewrites(src, self.REWRITES) == src

    def test_only_matches_at_the_start_of_a_target(self):
        src = "[x](https://cdn.example/https://example.edu/courses/i.png)"
        assert apply_url_rewrites(src, self.REWRITES) == src

    def test_no_rewrites_is_identity(self):
        assert apply_url_rewrites("text", {}) == "text"


class TestSourceLines:
    def test_round_trips_through_join(self):
        for text in ("a\nb\n", "a\nb", "", "one line"):
            assert "".join(_source_lines(text)) == text
