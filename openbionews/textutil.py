"""Small text helpers used across the pipeline. Standard library only."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

# A compact English stop-word list. Kept small on purpose: it only needs to be
# good enough to make title similarity meaningful, not linguistically complete.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "he", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "to", "was", "were", "will", "with", "this", "these", "those", "they",
    "their", "his", "her", "you", "your", "we", "our", "but", "not", "how",
    "what", "why", "who", "when", "where", "which", "into", "over", "after",
    "new", "study", "says", "report", "reports", "amid", "could", "may",
    "would", "can", "than", "then", "up", "out", "off", "about",
}


class _Stripper(HTMLParser):
    """Collect text nodes, dropping tags, scripts and styles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def strip_html(raw: str | None) -> str:
    """Return plain text from an HTML fragment, with whitespace collapsed."""
    if not raw:
        return ""
    parser = _Stripper()
    try:
        parser.feed(raw)
        parser.close()
        text = parser.text()
    except Exception:
        # Never let a malformed fragment crash the pipeline; fall back to a
        # crude tag strip.
        text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


# Split on sentence-ending punctuation followed by a space + capital/quote/digit.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def split_sentences(text: str) -> list[str]:
    """Split text into sentences. Conservative: standard-library heuristics only,
    tuned for the short, well-formed descriptions primary sources return."""
    text = (text or "").strip()
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def first_sentences(text: str, count: int = 2, max_chars: int = 320) -> str:
    """Return roughly the first ``count`` sentences, bounded by ``max_chars``."""
    pieces = split_sentences(text)
    if not pieces:
        return ""
    out = " ".join(pieces[:count]).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return out


_WORD_RE = re.compile(r"[a-z0-9]+")


def tokens(text: str, drop_stopwords: bool = True) -> list[str]:
    """Lowercase word tokens, optionally without stop words and 1-char noise."""
    words = _WORD_RE.findall(text.lower())
    if drop_stopwords:
        words = [w for w in words if w not in STOPWORDS and len(w) > 1]
    return words


def token_set(text: str) -> frozenset[str]:
    return frozenset(tokens(text))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity of two token sets (0.0 .. 1.0)."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "item"
