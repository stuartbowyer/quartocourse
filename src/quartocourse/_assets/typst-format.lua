-- Typst post-processing for notebook-derived documents. Runs only when
-- Quarto writes the typst format. Six concerns, all from quirks of the
-- Pandoc/Quarto/Typst pipeline:
--
-- 1. Restore HTML tables. Notebooks often embed `<table>` HTML for
--    multi-column layouts. The preprocessor wraps those in a Pandoc
--    raw-HTML fence; pandoc's ipynb reader doesn't enable `raw_attribute`
--    so the fence arrives as an inline `Code` element, not a RawBlock.
--    We catch that shape (a Para containing one Code starting with
--    `<table`), re-parse the HTML, and replace with proper Table AST so
--    the Typst writer renders a real table.
-- 2. Shrink CC license icons. The icons inside table attribution text were
--    sized via inline `style="height: 1em"` in the HTML source. Pandoc's
--    HTML reader drops inline styles, so without intervention they render
--    at their SVG-intrinsic dimensions (huge). The Image filter forces
--    them to 12pt.
-- 3. Drop horizontal rules. A rule is how a slide break is written in
--    markdown, so in the paginated document it carries no meaning and
--    would appear as a stray line between sections.
-- 4. Drop speaker notes. `::: {.notes}` becomes presenter-only content in
--    reveal.js, but the typst writer has no notion of a presenter view, so
--    the notes would otherwise be printed as body text in the reader's
--    document -- which is precisely who they are not written for.
-- 5. Skip image formats Typst can't decode. webp/avif/heic appear in
--    notebooks but Typst's image reader only handles PNG/JPEG/SVG/GIF.
--    Replace them with bracketed alt-text placeholders so the PDF build
--    doesn't fail. (Slides keep the originals — HTML <img> handles them.)
-- 6. Drop the redundant title cell + paginate sections. The Quarto cover
--    already shows title/subtitle/author from YAML, so strip everything
--    before the first H2. Then inject a #pagebreak() at the start of the
--    body (after TOC) and before each remaining H1.

if FORMAT ~= "typst" then return {} end


local function reparse_html_table(html)
  local ok, parsed = pcall(pandoc.read, html, "html")
  if not ok or #parsed.blocks == 0 then return nil end
  return parsed.blocks
end


function Para(el)
  if #el.content == 1 and el.content[1].t == "Code" then
    local code = el.content[1]
    if code.text:match("^%s*<table") then
      local blocks = reparse_html_table(code.text)
      if blocks then return blocks end
    end
  end
end


function RawBlock(el)
  if el.format == "html" and el.text:match("^%s*<table") then
    local blocks = reparse_html_table(el.text)
    if blocks then return blocks end
  end
end


-- A slide separator has no meaning in a paginated document.
function HorizontalRule(el)
  return {}
end


-- Speaker notes are for the presenter, not the reader.
function Div(el)
  if el.classes:includes("notes") then
    return {}
  end
end


local _TYPST_UNSUPPORTED_EXTS = { webp = true, avif = true, heic = true, heif = true }

local function _typst_unsupported_image(src)
  if not src then return false end
  -- Pandoc rewrites src to a local mediabag path. Notebook source bugs
  -- (e.g. trailing spaces in src="") can mangle filenames to things like
  -- "foo.webp-". Just check whether any unsupported extension appears in
  -- the path string anywhere.
  local lower = src:lower()
  for ext in pairs(_TYPST_UNSUPPORTED_EXTS) do
    if lower:find("%." .. ext) then return true end
  end
  return false
end


function Image(el)
  if _typst_unsupported_image(el.src) then
    local alt = pandoc.utils.stringify(el.caption or {})
    if alt == "" then
      alt = el.src:match("([^/]+)$") or "image"
    end
    return pandoc.Str("[" .. alt .. "]")
  end
  if el.src and el.src:match("creativecommons") then
    el.attr.attributes.height = "12pt"
    el.attr.attributes.width = nil
    return el
  end
end


function Pandoc(doc)
  local blocks = doc.blocks

  -- Find the first H2. Everything before it is the redundant title cell.
  local first_h2_idx
  for i, b in ipairs(blocks) do
    if b.t == "Header" and b.level == 2 then
      first_h2_idx = i
      break
    end
  end
  if not first_h2_idx then return doc end

  -- Start the body on a new page so the TOC ends cleanly on its own page(s).
  local new_blocks = {pandoc.RawBlock("typst", "#pagebreak()")}
  for i = first_h2_idx, #blocks do
    local b = blocks[i]
    if b.t == "Header" and b.level == 1 then
      table.insert(new_blocks, pandoc.RawBlock("typst", "#pagebreak()"))
    end
    table.insert(new_blocks, b)
  end

  doc.blocks = new_blocks
  return doc
end
