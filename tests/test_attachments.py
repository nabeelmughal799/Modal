import io
import unittest

from docx import Document
from fpdf import FPDF
from PIL import Image

from attachments import (
    MAX_ATTACHMENTS,
    MAX_FILE_BYTES,
    prepare_attachment,
    validate_attachments,
)


class AttachmentTests(unittest.TestCase):
    def test_reads_utf8_text_and_docx(self):
        text = prepare_attachment("note.txt", "hello".encode("utf-8"))
        self.assertEqual(text.extracted_text, "hello")

        document = Document()
        document.add_paragraph("DOCX contents")
        stream = io.BytesIO()
        document.save(stream)
        docx = prepare_attachment("note.docx", stream.getvalue())
        self.assertIn("DOCX contents", docx.extracted_text)

    def test_reads_pdf_and_rejects_scanned_pdf(self):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", size=12)
        pdf.cell(text="Readable PDF")
        data = bytes(pdf.output())
        self.assertIn("Readable PDF", prepare_attachment("note.pdf", data).extracted_text)

        blank = FPDF()
        blank.add_page()
        with self.assertRaisesRegex(ValueError, "scanned PDF"):
            prepare_attachment("scan.pdf", bytes(blank.output()))

    def test_validates_real_image_bytes(self):
        stream = io.BytesIO()
        Image.new("RGB", (4, 4), "white").save(stream, format="PNG")
        image = prepare_attachment("photo.png", stream.getvalue())
        self.assertEqual(image.mime_type, "image/png")
        self.assertEqual(image.data, stream.getvalue())

    def test_enforces_attachment_count_size_and_format(self):
        files = [(f"{index}.txt", b"words") for index in range(MAX_ATTACHMENTS + 1)]
        with self.assertRaisesRegex(ValueError, "no more than"):
            validate_attachments(files)
        with self.assertRaisesRegex(ValueError, "10 MB"):
            prepare_attachment("large.txt", b"x" * (MAX_FILE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "Supported file types"):
            prepare_attachment("script.exe", b"not allowed")


if __name__ == "__main__":
    unittest.main()
