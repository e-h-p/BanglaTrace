import unicodedata
import fitz
import pytest
from app.document_parser import parse_document, DocumentError
from app.bangla_sentence_segmenter import segment, normalize, words


def test_bangla_segmentation_and_wrapped_lines():
    text = "ডা. করিম ৩.১৪ কেজি চাল কিনলেন।\nতিনি\nঢাকায় থাকেন! “তুমি যাবে?”\n\nনতুন অনুচ্ছেদ"
    sentences = segment(text, "D1", "source.txt")
    assert len(sentences) == 4
    assert sentences[0].original_text == "ডা. করিম ৩.১৪ কেজি চাল কিনলেন।"
    assert sentences[1].line_start == 2 and sentences[1].line_end == 3
    assert sentences[2].original_text.endswith("?”")
    assert sentences[-1].line_start == 5
    for s in sentences:
        assert text[s.char_start : s.char_end] == s.original_text


def test_abbreviation_english_and_decimal():
    assert len(segment("Dr. Ali scored 3.14. He left.", "D", "a.txt")) == 2
    assert len(segment("মো. করিম এলেন। এরপর গেলেন।", "D", "a.txt")) == 2


def test_nfc_and_safe_normalization():
    original = "  বাড়ি\tনয়  ২০২৬। "
    assert normalize(original) == unicodedata.normalize("NFC", "বাড়ি নয় ২০২৬।")
    assert normalize("নয়") in normalize(original)


def test_stable_ids_and_locations():
    value = "প্রথম বাক্য।\nদ্বিতীয় বাক্য।".encode()
    a, b = parse_document(value, "one.txt"), parse_document(value, "renamed.txt")
    assert [s.sentence_id for s in a.sentences] == [s.sentence_id for s in b.sentences]
    assert a.sentences[1].line_start == 2
    assert a.sentences[1].location_type == "physical"
    assert a.sentences[1].page_number is None


def test_encodings():
    assert parse_document("বাংলা লেখা।".encode("utf-8-sig"), "a.txt").text == "বাংলা লেখা।"
    assert parse_document("বাংলা লেখা।".encode("utf-16"), "a.txt").text == "বাংলা লেখা।"
    with pytest.raises(DocumentError, match="UTF-8"):
        parse_document(b"\xff\xfe\xff", "a.txt")


@pytest.mark.parametrize(
    "data,name",
    [(b"", "a.txt"), (b"   ", "a.txt"), (b"abc", "a.exe"), (b"abc", "a.pdf"), (b"a\x00b", "a.txt")],
)
def test_invalid_documents(data, name):
    with pytest.raises(DocumentError):
        parse_document(data, name)


def test_pdf_extraction_and_line_mapping():
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "A sentence spans\nmultiple visual lines. Next sentence.")
        page = pdf.new_page()
        page.insert_text((72, 72), "Third sentence.")
        data = pdf.tobytes()
    doc = parse_document(data, "../../reference.pdf")
    assert doc.filename == "reference.pdf"
    assert doc.page_count == 2 and len(doc.sentences) == 3
    assert doc.sentences[0].line_start == 1 and doc.sentences[0].line_end == 2
    assert doc.sentences[0].page_number == 1
    assert doc.sentences[-1].page_number == 2
    assert doc.sentences[0].location_type == "extracted"


def test_scanned_and_password_pdf():
    with fitz.open() as pdf:
        pdf.new_page()
        with pytest.raises(DocumentError, match="OCR"):
            parse_document(pdf.tobytes(), "scanned.pdf")
        data = pdf.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
        with pytest.raises(DocumentError, match="unlock"):
            parse_document(data, "locked.pdf")


def test_word_definition_and_empty_punctuation():
    assert len(words("বাংলা ভাষা ২০২৬। ! —")) == 3
    assert segment("। ! ... \n\n", "D", "a.txt") == []
