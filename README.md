# quartocourse

[![CI](https://github.com/stuartbowyer/quartocourse/actions/workflows/ci.yml/badge.svg)](https://github.com/stuartbowyer/quartocourse/actions/workflows/ci.yml)

Render Jupyter notebooks into reveal.js slides and Typst PDF notes, using
Quarto. One notebook produces both: a deck to present from and a paginated
document to read.

## Install

```sh
# as a standalone tool
uv tool install "quartocourse[quarto] @ git+https://github.com/stuartbowyer/quartocourse"

# as a project dependency
uv add "quartocourse[quarto] @ git+https://github.com/stuartbowyer/quartocourse"
```

Not on PyPI, so the package and its extra are given as a single argument with
the git URL attached. `uv tool update-shell` puts the installed command on
PATH if it is not already.

The `quarto` extra pins the whole rendering toolchain — see [Toolchain](#toolchain).
Drop it if you already manage Quarto yourself.

## Use

```sh
quartocourse init ./my-course       # write a starter course.toml
quartocourse render ./my-course     # slides + notes for every notebook
quartocourse render ./my-course -n notebooks/01_Intro.ipynb --slides-only
quartocourse doctor                 # check the toolchain
```

Source notebooks are never modified. All preprocessing happens on a temporary
copy, so notebooks can live in a read-only checkout or a pinned submodule.

## Configuration

One `course.toml` per course. Every relative path in it resolves against the
file itself, so a course directory can be moved or copied freely. Only a
title and a notebooks directory are required.

| Block | Purpose |
| :-- | :-- |
| `[course]` | `title`, `code`, `author`, `institution` — used in footers and on the PDF cover |
| `[source]` | `notebooks` directory; optional `repo` + `ref` to enable GitHub and Colab links |
| `[output]` | `slides` and `notes` directories |
| `[brand]` | `font` (CSS stack), `pdf_font` (one Typst family), `accent`, `body_font_size`, extra `css` |
| `[compat]` | `slide_type` — see below |
| `[render]` | `user_agent`, a fixed `version` string, `url_rewrites`, `mounts` and `forbid` |
| `[execute]` | run notebooks at render time — see below |

Omit `[brand]` and you get a neutral default deck; nothing in the package is
branded. See [`examples/course.toml`](examples/course.toml) for every option.

`url_rewrites` and `mounts` work together for notebooks that reference assets
by their published URL. The rewrite turns a URL prefix into a
notebook-relative path, and the mount links the corresponding local directory
in beside the notebook at render time — so a build can use assets that exist
locally but are not deployed yet, and skips a network fetch for those that are.

## Executing notebooks

By default the saved outputs in each notebook are rendered as they are. With

```toml
[execute]
enabled = true
python = "../notebooks/.venv/bin/python"   # needs ipykernel; default: quartocourse's own
```

each notebook is run once at render time, its saved outputs are ignored, and
publishing becomes opt-in per cell through tags in the cell metadata:

| Tag | Slides | Notes (PDF) |
| :-- | :-- | :-- |
| `show` | shown | shown |
| `answer` | revealed on the next click | hidden |
| none | hidden | hidden |

A forgotten tag therefore hides an output rather than publishing it. A cell may
raise only if it is tagged — the error is then what is shown — or if it is a
blank exercise, a code cell containing `blank` (default `____`). Any other
error stops the render. The other options are `timeout` (seconds per cell,
default 600) and `reveal_outputs`: `"immediate"` (default) shows `show` outputs
with their slide, `"click"` reveals them on the next click, as answers always are.

`[render] forbid` takes regexes that must not appear in any published output,
executed or not, and fails the render on a match. It reads text only, so it
backs up the tags rather than replacing them.

## nbconvert compatibility

Notebooks written with JupyterLab's **Slide Type** control record where slides
begin in cell metadata (`slideshow.slide_type`). That is what nbconvert's
slides exporter reads.

Quarto's model is different: a slide begins at a heading or a horizontal rule,
and its notebook renderer does not consult that metadata. A cell marked as a
slide but titled with an `###` therefore does not begin one — it is folded
into the preceding slide, silently. A deck built this way renders with a
fraction of its slides, several of them carrying many sections' worth of
content stacked past the bottom edge.

`quartocourse` restores the intended structure, using nbconvert's mapping
expressed in the markdown Quarto documents:

| `slide_type` | becomes |
| :-- | :-- |
| `slide`, `subslide` | a horizontal rule before the cell |
| `fragment` | a pause (`. . .`) before the cell |
| `notes` | the cell wrapped in a speaker-notes div |
| `skip` | the cell dropped |
| `-`, absent | nothing; the cell continues the current slide |

Headings are left alone. Promoting an `###` to `##` would also break the
slide, but it would flatten the document's real structure — and that
structure is what the PDF's outline and contents are built from.

This is on by default and is a no-op for notebooks that carry no slideshow
metadata. Turn it off with:

```toml
[compat]
slide_type = false
```

## Toolchain

The only external dependency is Quarto. Its distribution bundles the exact
pandoc, typst, deno and dart-sass it requires, so pinning Quarto pins
everything; `quartocourse doctor` reports all of them.

Version drift is worth guarding against because the failures are opaque —
Quarto 1.9.x against pandoc < 3.8 raises `Aeson exception: Unknown option
syntax-highlighting`, and Quarto 1.8.x against pandoc 3.7.x fails with jog.lua
`Don't know how to traverse TableBody` on any document containing a table.
Neither message mentions a version. So the resolved Quarto is checked against
a supported range before rendering. `$QUARTOCOURSE_QUARTO` overrides which
binary is used.

Note that some distributions repackage Quarto *unbundled*, dropping
`bin/tools/` and expecting a system pandoc, which reintroduces exactly this
mismatch. The `quarto` extra fetches the upstream build, which does not.

## What it does not do

Publishing. `quartocourse` writes slides and PDFs to a directory; wiring them
into a website — index pages, front matter, redirects — belongs to whatever
project owns the site.

## Development

[uv](https://docs.astral.sh/uv/) is the only prerequisite.

```sh
uv sync --extra quarto
uv run pytest
uv run quartocourse doctor
```

## Licence

MIT.
