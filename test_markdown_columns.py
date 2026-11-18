import unittest

from markdown_columns import parse_article


class ParseArticleTests(unittest.TestCase):
    def test_plain_export_header_and_cleanup(self):
        article = parse_article("Title Here by A Writer\nA Writer · Jan 1, 2026 · site.test\n\n1.\n\nBody.\n\nObsidian Reader · footer")
        self.assertEqual(article.title, "Title Here")
        self.assertEqual(article.author, "A Writer")
        self.assertEqual(article.date, "Jan 1, 2026")
        self.assertEqual(article.blocks, [("section", "1."), ("body", "Body.")])

    def test_removes_eflux_branding(self):
        article = parse_article("# Title\n\ne-flux Journal\n\nKeep me")
        self.assertEqual(article.blocks, [("body", "Keep me")])

    def test_markdown_image(self):
        article = parse_article("# Title\n\n![A figure](figures/art.jpg)\n\nCaption text")
        self.assertEqual(article.blocks[0], ("image", "figures/art.jpg"))


class RenderArticleTests(unittest.TestCase):
    def render(self, source, **settings):
        import tempfile
        from pathlib import Path
        from pypdf import PdfReader
        from markdown_columns import render_article, RenderOptions
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'test.pdf'
            render_article(parse_article(source), output, options=RenderOptions(**settings))
            return PdfReader(output)

    def test_first_page_has_title_and_body_in_separate_columns(self):
        reader = self.render('# Test title\n\nBody begins here.', duplex=False)
        self.assertEqual(len(reader.pages), 1)
        positions = {}
        def visitor(text, cm, tm, font, size):
            for marker in ['Test title', 'Body begins here.']:
                if marker in text: positions[marker] = cm[4] + tm[4]
        reader.pages[0].extract_text(visitor_text=visitor)
        self.assertLess(positions['Test title'], 100)
        self.assertGreater(positions['Body begins here.'], 300)

    def test_paper_size_odd_page_count_and_embedded_font_variants(self):
        reader = self.render('# Title\n\nNormal **Bold** *Italic*.', page_size='half-letter')
        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(tuple(reader.pages[0].mediabox)[2:], (396, 612))
        fonts = reader.pages[0]['/Resources']['/Font'].get_object().values()
        embedded = [font.get_object() for font in fonts if '/FontDescriptor' in font.get_object()]
        self.assertEqual(len(embedded), 3)
        self.assertTrue(all('/FontFile2' in font['/FontDescriptor'] for font in embedded))

    def test_markdown_notes_tables_and_last_paragraph_survive(self):
        source = '# Test\n\nText[^1].\n\n| A | B |\n|---|---|\n| one | two |\n\n' + ('A long paragraph with complete text. '*60+'\n\n')*6 + 'LAST SENTENCE.\n\n[^1]: A real note.'
        reader = self.render(source, duplex=False)
        text = '\n'.join(page.extract_text() for page in reader.pages)
        for expected in ['one', 'two', 'LAST SENTENCE.', 'A real note.']:
            self.assertIn(expected, text)
        self.assertGreater(len(reader.pages), 1)

    def test_figure_caption_and_linked_duplicate(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from pypdf import PdfReader
        from markdown_columns import render_article, RenderOptions
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB', (200, 100), 'red').save(root / 'figure.png')
            source = '# Figures\n\n![figure](figure.png)\n\n**Figure 1.** A caption.\n\n[![figure](figure.png)](https://example.com)\n\nFollowing text.'
            output = root / 'figure.pdf'
            render_article(parse_article(source), output, options=RenderOptions(base_dir=root, duplex=False))
            reader = PdfReader(output)
            text = reader.pages[0].extract_text()
            self.assertEqual(text.count('Figure 1.'), 1)
            self.assertIn('Following text.', text)
            operations = reader.pages[0].get_contents().operations
            self.assertEqual(sum(op == b'Do' for args, op in operations), 1)

    def test_long_caption_splits_without_losing_text_or_repeating_image(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from pypdf import PdfReader
        from markdown_columns import render_article, RenderOptions
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB', (300, 180), 'red').save(root / 'figure.png')
            caption = '**Figure 1.** ' + ' '.join(f'Captionword{n}' for n in range(500))
            source = '# Figures\n\n' + ('Introductory text. ' * 50) + '\n\n![figure](figure.png)\n\n' + caption + '\n\nFollowing text.'
            output = root / 'figure.pdf'
            render_article(parse_article(source), output, options=RenderOptions(base_dir=root, duplex=False))
            reader = PdfReader(output)
            text = '\n'.join(page.extract_text() for page in reader.pages)
            normalized = text.replace('-\n', '').replace('\n', ' ')
            for number in range(500):
                self.assertIn(f'Captionword{number}', normalized)
            self.assertIn('Following text.', text)
            image_pages = [page for page in reader.pages if page.images]
            self.assertEqual(len(image_pages), 1)
            self.assertIn('Figure 1.', image_pages[0].extract_text())
            self.assertGreater(len(reader.pages), 1)
            self.assertEqual(sum(op == b'Do' for page in reader.pages for args, op in page.get_contents().operations), 1)

    def test_image_alt_fallback_and_explicit_figcaption(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from pypdf import PdfReader
        from markdown_columns import render_article, RenderOptions
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB', (200, 100), 'red').save(root / 'fallback.png')
            Image.new('RGB', (200, 100), 'blue').save(root / 'explicit.png')
            source = (
                '# Figures\n\n'
                '![Fallback alt caption](fallback.png)\n\n'
                '![Alt text that should be replaced](explicit.png)\n\n'
                '<figcaption>Explicit figure caption</figcaption>'
            )
            output = root / 'figure.pdf'
            render_article(parse_article(source), output, options=RenderOptions(base_dir=root, duplex=False))
            text = '\n'.join(page.extract_text() for page in PdfReader(output).pages)
            self.assertIn('Fallback alt caption', text)
            self.assertIn('Explicit figure caption', text)
            self.assertNotIn('Alt text that should be replaced', text)

    def test_web_cannot_read_local_figures_or_private_hosts(self):
        from markdown_columns import remote_image
        with self.assertRaisesRegex(ValueError, 'local files'):
            self.render('# Test\n\n![secret](/etc/passwd)', allow_local_images=False)
        with self.assertRaisesRegex(ValueError, 'Private network'):
            remote_image('http://127.0.0.1/secret')

    def test_hyphenated_split_fragment_keeps_its_measured_line_count(self):
        import random
        from reportlab.lib.styles import ParagraphStyle
        from markdown_columns import BASELINE, Paragraph, register_fonts
        regular, _, _ = register_fonts('sans')
        style = ParagraphStyle(
            'split-regression', fontName=regular, fontSize=10, leading=BASELINE,
            spaceAfter=BASELINE, allowWidows=0, allowOrphans=0,
            hyphenationLang='en_US', embeddedHyphenation=1,
        )
        vocabulary = (
            'memory enumeration language extraordinary representation communication consideration '
            'imagination administration observation development particular individual circumstances '
            'experience recognizable unintelligible magnificent impossible frequently everything '
            'something different without between recorded practiced faithfully repeating happened '
            'perception attention afternoon consciousness intolerable blue-gray old-fashioned well-known'
        ).split()
        generator = random.Random(2)
        words = [generator.choice(vocabulary) for _ in range(generator.randint(90, 180))]
        words[5] = f'<i>{words[5]}</i>'
        text = ' '.join(words) + '.'
        paragraph = Paragraph(text, style)
        paragraph.wrap(261, 10_000)
        first, _ = paragraph.split(261, 138)
        self.assertLessEqual(first.wrap(261, 138)[1], 138)

    def test_heading_keeps_only_opening_lines_of_long_paragraph(self):
        source = (
            '# Test\n\n'
            + ('Prelude material fills the first column at a predictable pace. ' * 50)
            + '\n\n## Opening Digital Black Boxes\n\n'
            + ('Following paragraph is deliberately long so it must split across frames. ' * 45)
        )
        reader = self.render(source, start_on_right=False, duplex=False)
        positions = []

        def visitor(text, cm, tm, font, size):
            if 'Opening Digital Black Boxes' in text:
                positions.append(cm[4] + tm[4])

        reader.pages[0].extract_text(visitor_text=visitor)
        self.assertEqual(len(positions), 1)
        self.assertLess(positions[0], 300, 'the heading should use the remaining room in the left column')

    def test_footnote_marker_uses_a_compact_superscript(self):
        from reportlab.lib.styles import ParagraphStyle
        from markdown_columns import Paragraph, inline, register_fonts
        regular, _, _ = register_fonts('sans')
        marker = inline([{'type': 'footnote_ref', 'attrs': {'index': 12}}])
        paragraph = Paragraph('Anchor' + marker + ' text', ParagraphStyle('note-marker', fontName=regular, fontSize=10))
        footnote_frag = next(fragment for fragment in paragraph.frags if fragment.text == '12')
        self.assertEqual(footnote_frag.fontSize, 7.5)
        self.assertEqual(footnote_frag.rise, 3)

    def test_prose_quotes_are_typographic_but_code_quotes_are_literal(self):
        source = '# Test\n\nHe said, "hello" to the species\' keeper\'s friend.\n\n`print("literal")`'
        text = '\n'.join(page.extract_text() for page in self.render(source, duplex=False).pages)
        self.assertIn('“hello”', text)
        self.assertIn('species’ keeper’s', text)
        self.assertIn('print("literal")', text)

    def test_display_math_uses_monospace_style(self):
        source = '# Test\n\n$$ D_{KL}(P_{post} || P_{prior}) = \\ln\n\\frac{a}{b} $$'
        reader = self.render(source, duplex=False)
        math_fonts = []

        def visitor(text, cm, tm, font, size):
            if 'D_' in text or '\\frac' in text:
                math_fonts.append((font.get('/BaseFont'), size))

        reader.pages[0].extract_text(visitor_text=visitor)
        self.assertTrue(math_fonts)
        self.assertTrue(all('Courier' in str(font) and size == 8 for font, size in math_fonts))

    def test_lowercase_mid_sentence_paragraph_fragment_is_rejoined(self):
        reader = self.render('# Test\n\nWe used tools to suggest\n\nwording ideas for the final draft.', duplex=False)
        text = reader.pages[0].extract_text()
        self.assertIn('We used tools to suggest wording ideas for the final draft.', text.replace('\n', ' '))

    def test_moved_figure_keeps_its_caption_on_the_image_page(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from pypdf import PdfReader
        from markdown_columns import render_article, RenderOptions
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB', (500, 350), 'red').save(root / 'figure.png')
            source = (
                '# Figures\n\n' + ('Filler text occupies the earlier columns. ' * 320)
                + '\n\n![figure](figure.png)\n\nFigure 7. Caption travels with the moved figure.'
            )
            output = root / 'figure.pdf'
            render_article(parse_article(source), output, options=RenderOptions(base_dir=root, start_on_right=False, duplex=False))
            reader = PdfReader(output)
            image_pages = [index for index, page in enumerate(reader.pages) if page.images]
            caption_pages = [index for index, page in enumerate(reader.pages) if 'Caption travels with' in page.extract_text()]
            self.assertEqual(len(image_pages), 1)
            self.assertEqual(caption_pages, image_pages)
            self.assertGreater(image_pages[0], 0)

    def test_notes_use_compact_style_and_heading_stays_with_first_note(self):
        source = (
            '# Test\n\n'
            + ('Body material fills columns predictably. ' * 155)
            + '\n\nText[^1].\n\n[^1]: FIRSTNOTE '
            + ('Long note text continues. ' * 60)
        )
        reader = self.render(source, start_on_right=False, duplex=False)
        positions = {}

        for page_number, page in enumerate(reader.pages):
            def visitor(text, cm, tm, font, size):
                for marker in ('Notes', 'FIRSTNOTE'):
                    if marker in text:
                        positions[marker] = (page_number, cm[5] + tm[5], size)
                if text.strip() == '1.':
                    positions['note-number'] = (page_number, cm[5] + tm[5], size)

            page.extract_text(visitor_text=visitor)

        self.assertEqual(positions['Notes'][0], positions['FIRSTNOTE'][0])
        self.assertLess(positions['Notes'][1] - positions['FIRSTNOTE'][1], 30)
        self.assertEqual(positions['FIRSTNOTE'][2], 8)
        self.assertEqual(positions['note-number'][2], 8)


if __name__ == "__main__":
    unittest.main()
