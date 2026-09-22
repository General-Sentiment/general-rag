import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from booklet import booklet_spreads, impose_booklet


class BookletTests(unittest.TestCase):
    def test_eight_page_order(self):
        self.assertEqual(booklet_spreads(8), [(7, 0), (1, 6), (5, 2), (3, 4)])

    def test_padding(self):
        self.assertEqual(booklet_spreads(5), [(None, 0), (1, None), (None, 2), (3, 4)])

    def test_pdf_is_two_up(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pdf"
            output = Path(directory) / "booklet.pdf"
            writer = PdfWriter()
            for _ in range(6):
                writer.add_blank_page(width=300, height=500)
            with source.open("wb") as stream:
                writer.write(stream)
            impose_booklet(source, output)
            result = PdfReader(str(output))
            self.assertEqual(len(result.pages), 4)
            self.assertEqual(float(result.pages[0].mediabox.width), 500)
            self.assertEqual(float(result.pages[0].mediabox.height), 300)


if __name__ == "__main__":
    unittest.main()
