import shutil
import subprocess

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

    @pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
    def test_notebooks_in_a_repo_subdirectory(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        cfg = self._cfg(tmp_path, "https://github.com/u/r")
        assert cfg.github_url("L1.ipynb") == (
            "https://github.com/u/r/blob/main/notebooks/L1.ipynb"
        )

class TestExecute:
    def test_off_by_default(self, tmp_path):
        cfg = config.load(_write(tmp_path, MINIMAL))
        assert cfg.execute.enabled is False
        assert cfg.render.forbid == ()

    def test_missing_interpreter_is_an_error_when_enabled(self, tmp_path):
        body = MINIMAL + '\n[execute]\nenabled = true\npython = "nope/bin/python"\n'
        with pytest.raises(config.ConfigError, match="python interpreter"):
            config.load(_write(tmp_path, body))

    def test_interpreter_path_keeps_its_symlink(self, tmp_path):
        real = tmp_path / "real-python"
        real.write_text("")
        (tmp_path / "venv").mkdir()
        (tmp_path / "venv" / "python").symlink_to(real)
        body = MINIMAL + '\n[execute]\nenabled = true\npython = "venv/python"\n'
        cfg = config.load(_write(tmp_path, body))
        assert cfg.execute.python == tmp_path / "venv" / "python"

    def test_reveal_outputs_must_be_immediate_or_click(self, tmp_path):
        body = MINIMAL + '\n[execute]\nreveal_outputs = "sometimes"\n'
        with pytest.raises(config.ConfigError, match="reveal_outputs"):
            config.load(_write(tmp_path, body))

    def test_invalid_forbid_pattern_is_an_error(self, tmp_path):
        body = MINIMAL + '\n[render]\nforbid = ["("]\n'
        with pytest.raises(config.ConfigError, match="forbid"):
            config.load(_write(tmp_path, body))
