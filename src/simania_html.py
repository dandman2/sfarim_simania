"""Parse Simania's public search JSON and structured Book metadata in HTML."""

import json
import math
import re
from html import unescape
from urllib.parse import parse_qs, urljoin, urlsplit
from lxml import html

BASE = 'https://simania.co.il'


def book_id(url):
    """Accept only a Simania book details URL and its numeric identifier."""
    parts = urlsplit(urljoin(BASE, url))
    if parts.scheme != 'https' or parts.netloc.lower() not in ('simania.co.il', 'www.simania.co.il'):
        return None
    if parts.path != '/bookdetails.php':
        return None
    values = parse_qs(parts.query).get('item_id', [])
    return values[0] if len(values) == 1 and re.fullmatch(r'[1-9][0-9]*', values[0]) else None


def image_url(value):
    """Use the original catalog image, never avatars or resized proxy images."""
    if not isinstance(value, str):
        return None
    url = urljoin('https://cdn.simania.co.il', value)
    parts = urlsplit(url)
    if (parts.scheme == 'https' and parts.netloc.lower() in ('simania.co.il', 'www.simania.co.il', 'cdn.simania.co.il')
            and re.fullmatch(r'/bookimages/covers[0-9]*/[0-9]+\.(?:jpg|jpeg|png|webp)', parts.path, re.I)):
        return url
    return None


def clean_text(value):
    """Normalize source text and legacy escaped line breaks, preserving Unicode."""
    if not isinstance(value, str):
        return ''
    value = unescape(value).replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\"', '"')
    return ' '.join(value.split())


def names(value):
    """Read single and structured author names without splitting Hebrew conjunctions."""
    if isinstance(value, list):
        return list(dict.fromkeys(name for item in value for name in names(item)))
    if isinstance(value, dict):
        return names(value.get('name', ''))
    result = clean_text(value)
    return [result] if result else []


def search_page(data):
    """Read only books from the public search response, ignoring entity suggestions."""
    payload = json.loads(data)
    if not isinstance(payload, dict) or payload.get('success') is not True:
        raise ValueError('Simania search did not return a successful response.')
    section = payload.get('data')
    if not isinstance(section, dict) or not isinstance(section.get('books'), list):
        raise ValueError('Simania search response format changed.')
    pagination = section.get('pagination')
    if not isinstance(pagination, dict) or not isinstance(pagination.get('hasNextPage'), bool):
        raise ValueError('Simania pagination information is missing.')
    result, seen = [], set()
    for entry in section['books']:
        if not isinstance(entry, dict):
            continue
        ident = str(entry.get('BOOK_ID') or entry.get('ID') or '')
        title = clean_text(entry.get('NAME'))
        if not re.fullmatch(r'[1-9][0-9]*', ident) or not title or ident in seen:
            continue
        seen.add(ident)
        result.append({'id': ident, 'title': title, 'authors': names(entry.get('AUTHOR'))})
    return result, pagination['hasNextPage']


def structured_books(root):
    """Read Book JSON-LD in a page, including graph containers."""
    def visit(value):
        if isinstance(value, list):
            for item in value:
                yield from visit(item)
        elif isinstance(value, dict):
            kinds = value.get('@type', [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if isinstance(kinds, list) and 'Book' in kinds:
                yield value
            yield from visit(value.get('@graph', []))
    for script in root.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            yield from visit(json.loads(script))
        except (ValueError, TypeError):
            continue


def details_page(data, expected_id):
    """Extract the requested edition, without inferring dates from reviews or prose."""
    root = html.fromstring(data, parser=html.HTMLParser(encoding='utf-8'))
    metadata = None
    for entry in structured_books(root):
        ident = book_id(entry.get('url') or entry.get('@id') or '')
        if ident == expected_id and str(entry.get('sku', expected_id)) == expected_id:
            metadata = entry
            break
    if metadata is None:
        raise ValueError('The page does not identify the requested Simania book.')
    title = clean_text(metadata.get('name'))
    if not title:
        raise ValueError('Simania book title is missing.')
    date = str(metadata.get('datePublished') or '').strip()
    match = re.fullmatch(r'([12][0-9]{3})(?:-\d{2}(?:-\d{2})?)?', date)
    genre = clean_text(metadata.get('genre'))
    series = metadata.get('isPartOf')
    series = series if isinstance(series, dict) and series.get('@type') == 'BookSeries' else {}
    try:
        number = float(series.get('position'))
        if not math.isfinite(number) or number < 0:
            number = None
    except (ValueError, TypeError):
        number = None
    return {'id': expected_id, 'title': title, 'authors': names(metadata.get('author')),
            'publisher': ', '.join(names(metadata.get('publisher'))),
            'year': int(match.group(1)) if match else None,
            'isbn': metadata.get('isbn') or '', 'language': clean_text(metadata.get('inLanguage')),
            'tags': list(dict.fromkeys(tag.strip() for tag in genre.split('»') if tag.strip())),
            'comments': clean_text(metadata.get('description')),
            'series': clean_text(series.get('name')), 'series_index': number,
            'cover': image_url(metadata.get('image'))}
