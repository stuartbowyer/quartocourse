import pytest

from quartocourse import config


def _write(tmp_path, body, with_notebooks=True):
    if with_notebooks:
        (tmp_path / "notebooks").mkdir(exist_ok=True)
    path = tmp_path / "course.toml"
    path.write_text(body)
    return path


MINIMAL = '[course]\ntitle = "T"\n'


class TestLoad:
    def test_minimal_config_uses_defaults(self, tmp_path):
        cfg = config.load(_write(tmp_path, MINIMAL))
        assert cfg.course.title == "T"
        assert cfg.brand.accent == config.DEFAULT_ACCENT
        assert cfg.brand.pdf_font == ""
        assert cfg.output.slides == (tmp_path / "build/slides").resolve()

    def test_accepts_a_directory(self, tmp_path):
        _write(tmp_path, MINIMAL)
        assert config.load(tmp_path).course.title == "T"

    def test_missing_title_is_an_error(self, tmp_path):
        with pytest.raises(config.ConfigError, match="title"):
            config.load(_write(tmp_path, '[course]\ncode = "X"\n'))

    def test_missing_notebooks_dir_is_an_error(self, tmp_path):
        with pytest.raises(config.ConfigError, match="notebooks directory"):
            config.load(_write(tmp_path, MINIMAL, with_notebooks=False))

    def test_paths_resolve_against_the_config_file(self, tmp_path):
        (tmp_path / "nb").mkdir()
        cfg = config.load(
            _write(tmp_path, MINIMAL + '\n[source]\nnotebooks = "nb"\n')
        )
        assert cfg.source.notebooks == (tmp_path / "nb").resolve()


class TestUrls:
    def _cfg(self, tmp_path, repo, ref="main"):
        body = MINIMAL + f'\n[source]\nrepo = "{repo}"\nref = "{ref}"\n'
        return config.load(_write(tmp_path, body))

    def test_github_url_pins_the_ref(self, tmp_path):
        cfg = self._cfg(tmp_path, "https://github.com/u/r", ref="v1.0")
        assert cfg.github_url("L1.ipynb") == "https://github.com/u/r/blob/v1.0/L1.ipynb"

    def test_strips_git_suffix(self, tmp_path):
        cfg = self._cfg(tmp_path, "https://github.com/u/r.git")
        assert cfg.github_url("L1.ipynb").startswith(
            "https://github.com/u/r/blob/main/"
        )

    def test_colab_url(self, tmp_path):
        cfg = self._cfg(tmp_path, "https://github.com/u/r")
        assert cfg.colab_url("L1.ipynb") == (
            "https://colab.research.google.com/github/u/r/blob/main/L1.ipynb"
        )

    def test_no_repo_means_no_urls(self, tmp_path):
        cfg = config.load(_write(tmp_path, MINIMAL))
        assert cfg.github_url("L1.ipynb") == ""
        assert cfg.colab_url("L1.ipynb") == ""
