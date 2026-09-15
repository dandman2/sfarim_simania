"""Rank public catalog candidates using normalized title and author evidence."""

import re
import unicodedata
from difflib import SequenceMatcher


def normalize(value):
    """Ignore Hebrew pointing, direction markers and punctuation for comparisons."""
    value = unicodedata.normalize('NFKD', value or '').casefold()
    value = ''.join(c for c in value if unicodedata.category(c) not in ('Mn', 'Cf'))
    return ' '.join(re.findall(r'\w+', value, re.UNICODE))


def rank_books(books, title, authors=None):
    """Return plausible candidates in relevance order, preserving edition alternatives."""
    query = normalize(title)
    if not query:
        return []
    wanted_authors = [normalize(a) for a in (authors or []) if normalize(a)]
    ranked = []
    for book in books:
        actual = normalize(book['title'])
        short = normalize(book['title'].split(':', 1)[0])
        similarity = max(SequenceMatcher(None, query, actual).ratio(),
                         SequenceMatcher(None, query, short).ratio())
        if query == actual or query == short:
            similarity = 1.0
        elif set(query.split()).issubset(set(actual.split())):
            similarity = max(similarity, 0.85)
        if similarity < 0.60:
            continue
        author_text = normalize(' '.join(book.get('authors', [])))
        author_score = max((SequenceMatcher(None, a, author_text).ratio()
                            for a in wanted_authors), default=0)
        if any(set(a.split()).issubset(set(author_text.split())) for a in wanted_authors):
            author_score = 1.0
        ranked.append((similarity + 0.35 * author_score, book))
    return [book for score, book in sorted(ranked, key=lambda pair: -pair[0])]
