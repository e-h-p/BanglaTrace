import re
import unicodedata
from .schemas import Sentence

SEGMENTER_VERSION = "nfc-offset-v1"
ABBREVIATIONS = {
    "ড",
    "ডা",
    "মো",
    "মোঃ",
    "প্রফ",
    "মি",
    "মিসেস",
    "জনাব",
    "dr",
    "mr",
    "mrs",
    "ms",
    "prof",
    "e.g",
    "i.e",
    "etc",
    "vs",
}


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def words(text: str) -> list[str]:
    """Whitespace tokens containing at least one Unicode letter/number; punctuation is not a word."""
    return [w for w in text.split() if any(unicodedata.category(c)[0] in "LN" for c in w)]


def lexical_tokens(text: str) -> list[str]:
    # Keep combining marks with Bangla letters; retain digits and negation words.
    return [
        "".join(c for c in token.casefold() if unicodedata.category(c)[0] in "LNM")
        for token in words(normalize(text))
    ]


def sentence_spans(text: str):
    start, i = 0, 0
    while i < len(text):
        c = text[i]
        end = None
        if c in "।!?":
            end = i + 1
        elif c == ".":
            before = text[i - 1] if i else ""
            after = text[i + 1] if i + 1 < len(text) else ""
            token = re.search(r"([^\s]+)$", text[start:i])
            token = token.group(1).strip('“”"()').casefold() if token else ""
            decimal = before.isdigit() and after.isdigit()
            initial = len(token) == 1 and token.isalpha() and bool(after)
            internal = bool(after) and after.isalnum() and before.isalnum()
            if not (decimal or initial or internal or token in ABBREVIATIONS):
                end = i + 1
        elif c == "\n" and re.match(r"\n[ \t]*\n", text[i:]):
            end = i
        if end is not None:
            if c in "।.!?":
                while end < len(text) and text[end] in "।.!?\"'”’»)]}":
                    end += 1
            a, b = start, end
            while a < b and text[a].isspace():
                a += 1
            while b > a and text[b - 1].isspace():
                b -= 1
            if b > a and words(text[a:b]):
                yield a, b
            start = end
            i = max(i + 1, end)
        else:
            i += 1
    a, b = start, len(text)
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    if b > a and words(text[a:b]):
        yield a, b


def segment(
    text: str, document_id: str, filename: str, locations=None, pdf=False
) -> list[Sentence]:
    """locations: (start, end, page, physical/extracted line) in the exact extraction text."""
    if locations is None:
        locations, offset = [], 0
        for line, value in enumerate(text.splitlines(keepends=True), 1):
            locations.append((offset, offset + len(value), None, line))
            offset += len(value)
    result = []
    for n, (a, b) in enumerate(sentence_spans(text), 1):
        locs = [loc for loc in locations if loc[0] < b and loc[1] > a]
        first, last = (locs[0], locs[-1]) if locs else (None, None)
        value = text[a:b]
        result.append(
            Sentence(
                document_id=document_id,
                filename=filename,
                sentence_id=f"{document_id}_S{n}",
                sentence_number=n,
                original_text=value,
                normalized_text=normalize(value),
                char_start=a,
                char_end=b,
                word_count=len(words(value)),
                page_number=first[2] if first else None,
                page_end=last[2] if last else None,
                line_start=first[3] if first else None,
                line_end=last[3] if last else None,
                location_type="extracted" if pdf else "physical",
            )
        )
    return result
