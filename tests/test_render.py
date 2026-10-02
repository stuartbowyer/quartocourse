from pathlib import Path

from quartocourse import config
from quartocourse.render import typst_header


def _cfg(tmp_path):
    (tmp_path / "notebooks").mkdir()
    path = tmp_path / "course.toml"
    path.write_text('[course]\ntitle = "T"\nauthor = "A. Lecturer"\n')
    return config.load(path)


class TestTypstHeader:
    def test_version_is_on_the_first_page_footer_only(self, tmp_path):
        header = typst_header(_cfg(tmp_path), Path("L1.ipynb"), "v.2026-10-02_abc1234")
        assert 'counter(page).get().first() == 1 [ · #"v.2026-10-02_abc1234"]' in header

    def test_no_version_leaves_the_footer_unchanged(self, tmp_path):
        header = typst_header(_cfg(tmp_path), Path("L1.ipynb"))
        assert "[A. Lecturer]," in header
        assert "get().first()" not in header
