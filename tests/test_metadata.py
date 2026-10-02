from pathlib import Path

from quartocourse import config
from quartocourse.metadata import notes_metadata


def _cfg(tmp_path):
    (tmp_path / "notebooks").mkdir()
    path = tmp_path / "course.toml"
    path.write_text('[course]\ntitle = "T"\nauthor = "A. Lecturer"\n')
    return config.load(path)


STAGED = {"typst_filter": Path("filter.lua")}


class TestNotesMetadata:
    def test_version_sits_under_the_author_on_the_title_page(self, tmp_path):
        meta = notes_metadata(_cfg(tmp_path), STAGED, Path("L1.ipynb"), "", "v.1_abc")
        assert meta["author"] == [
            {"name": "A. Lecturer", "affiliations": [{"name": "v.1_abc"}]}
        ]

    def test_no_version_keeps_the_plain_author(self, tmp_path):
        meta = notes_metadata(_cfg(tmp_path), STAGED, Path("L1.ipynb"), "")
        assert meta["author"] == "A. Lecturer"
