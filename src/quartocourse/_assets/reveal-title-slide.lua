-- Each lecture's first cell is structured as:
--   <img logo>
--   # Lecture Title  (Setext H1)
--   ### Subtitle
--   ### Author
-- Pandoc's revealjs writer (as wrapped by Quarto) puts the first H1 into a
-- special `title-slide` section, but it CLOSES that section as soon as it
-- encounters any subsequent heading — including H3 — so the subtitle / author
-- H3 lines get ejected out of the title slide into the stack-wrapper.
--
-- This filter does two passes on the first H1:
--   1. Move blocks appearing BEFORE the first H1 (the bare image, etc.) to
--      immediately AFTER the H1 so they live inside the title-slide section.
--   2. Convert any H3+ headings between the first H1 and the next H1/H2 into
--      bold paragraphs. They lose their "heading-ness" so Pandoc keeps them
--      inside the title-slide, while their text content survives. CSS styles
--      them back to a subtitle look in slides.css.
--
-- Result: title slide carries logo + title + subtitle lines on one slide,
-- and subsequent H2 slides nest under the title H1 in reveal's outline.

if FORMAT ~= "revealjs" then return {} end

function Pandoc(doc)
  local blocks = doc.blocks
  local h1_idx
  for i = 1, #blocks do
    if blocks[i].t == "Header" and blocks[i].level == 1 then
      h1_idx = i
      break
    end
  end
  if not h1_idx then return doc end

  -- Pass 1: move preamble blocks to after the H1.
  local preamble = {}
  for i = 1, h1_idx - 1 do
    preamble[i] = blocks[i]
  end
  local new_blocks = {blocks[h1_idx]}
  for _, b in ipairs(preamble) do
    table.insert(new_blocks, b)
  end
  for i = h1_idx + 1, #blocks do
    table.insert(new_blocks, blocks[i])
  end
  blocks = new_blocks

  -- Pass 2: convert H3+ headings between the first H1 (index 1) and the
  -- next H1/H2 into bold paragraphs wrapped in a div.title-subtitle so CSS
  -- can target them.
  for i = 2, #blocks do
    local b = blocks[i]
    if b.t == "Header" then
      if b.level <= 2 then
        break  -- next slide-breaking heading, stop here
      end
      blocks[i] = pandoc.Div(
        {pandoc.Para({pandoc.Strong(b.content)})},
        pandoc.Attr("", {"title-subtitle"}, {})
      )
    end
  end

  doc.blocks = blocks
  return doc
end
