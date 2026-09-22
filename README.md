# PDF Zine Maker

Turns a PDF in normal reading order into a two-up booklet PDF. Print it double-sided, fold each sheet in half hamburger-style, nest the sheets, and staple through the fold.

## Journal Print web app

The web app and CLI use the same ReportLab renderer. The server generates a PDF with embedded fonts, fixed columns, and fixed page breaks. PDF.js displays those pages in the browser; Download PDF saves the same bytes. Safari and Chrome do not typeset or paginate the article.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
npm run dev
```

Paste Markdown or import a public article URL, choose settings, and click **Generate PDF**. After editing content or settings, generate again to update the preview. Use **Download PDF** to save the generated file and open it in your PDF viewer. Print at actual size with matching paper. For double-sided articles, flip on the long edge.

Supported controls: Letter, A4, and Half Letter; Areal sans and Alegreya serif; opening text in the right column; double-sided printing guidance; grayscale figures and brightness. Figures are loaded from public HTTP(S) URLs into memory, never saved into the codebase. Broken or unsupported figures produce an error instead of silently disappearing. The web renderer rejects local/private image URLs. The CLI also supports local images relative to the Markdown file.

The server needs a Node environment with Python installed (not an Edge runtime or static hosting). It uses `.venv/bin/python` by default; set `JOURNAL_PYTHON` to select another interpreter. Include `markdown_columns.py`, `assets/fonts/`, `public/fonts/`, and `vendor/pyphen/` in deployments, and install the Python requirements. `npm install` copies the matching PDF.js worker into `public/pdfjs/`.

Markdown support includes headings, emphasis, nested lists, quotes, code, tables, figures with captions, and endnotes. Raw HTML blocks are rejected. Long captions can continue across columns or pages while the image stays with at least the first two caption lines; wide tables may need a larger paper size. Alegreya italic is an embedded oblique generated from the bundled upright font. Complex-script shaping and mathematical typesetting are not implemented.

## Use in this chat

Attach a PDF and ask: `Make this into a booklet.` The resulting file will be imposed using the same layout as this tool.

## Use locally

```sh
python3 -m pip install -r requirements.txt
python3 booklet.py input.pdf
```

The default output is `input-booklet.pdf`. You can choose a destination with:

```sh
python3 booklet.py input.pdf output.pdf
```

## Print settings

- Print double-sided.
- Flip on the **short edge**.
- Use **actual size / 100%** when the printer paper matches the output sheet size.
- Do not enable the print dialog's own booklet or two-pages-per-sheet mode; this PDF is already imposed.
- Fold every sheet in half across the middle (hamburger fold), nest them in printed order, then staple along the fold.

If the source page count is not divisible by four, blank pages are added automatically. Mixed-size source pages are scaled proportionally and centered into slots matching the first source page.

## Portrait two-column articles (CLI)

```sh
.venv/bin/python markdown_columns.py article.md article.pdf \
  --title "Article title" --author "Author" \
  --page-size letter --typeface sans
```

Options:

- `--page-size letter|a4|half-letter`
- `--typeface sans|serif`
- `--no-start-on-right` to begin below the title in the left column
- `--no-grayscale` to preserve color
- `--midpoint 1.08` to adjust grayscale brightness (0.85–1.35)
- `--figure-map figures.json` for legacy caption-to-local-image mappings

Metadata can come from a leading `# Title`, a plain `Title by Author` line, or simple YAML front matter containing `title`, `author`, and `date`. Explicit CLI title/author options override extracted metadata. The command prints JSON containing the output path and page count. Without an output argument, PDFs go into `output/pdf/`.

```sh
.venv/bin/python -m unittest test_booklet test_markdown_columns
npm run lint
npm run build
```
