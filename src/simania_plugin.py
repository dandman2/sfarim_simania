"""Calibre metadata-source adapter for Simania search, catalog metadata and covers."""

from datetime import datetime, timezone
from html import escape
from queue import Queue
import re

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata import check_isbn
from calibre.utils.localization import canonicalize_lang
from calibre.ebooks.metadata.sources.base import Source, Option
from .simania_cover import download as download_simania_cover
from . import simania_client
from .book_matching import rank_books
from .simania_html import BASE, book_id
from .plugin_constants import PLUGIN_VER_MAJOR, PLUGIN_VER_MINOR, PLUGIN_VER_BUILD


class SfarimSimaniaPlugin(Source):
    """Offer user-selected metadata matches; never modify the library directly."""

    name = 'Sfarim Simania'
    description = 'Download book metadata and original cover images from Simania.'
    author = 'Dan D Man'
    version = (PLUGIN_VER_MAJOR, PLUGIN_VER_MINOR, PLUGIN_VER_BUILD)
    minimum_calibre_version = (6, 0, 0)
    supported_platforms = ['windows', 'osx', 'linux']
    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset(['title', 'authors', 'publisher', 'pubdate', 'comments', 'tags', 'languages', 'series', 'series_index', 'identifier:isbn', 'identifier:simania'])
    has_html_comments = True
    supports_gzip_transfer_encoding = True
    options = (
        Option('max_results', 'number', 5, 'Maximum metadata candidates', 'Fetch details for the best 1–20 matching books.'),
        Option('max_pages', 'number', 3, 'Maximum search pages', 'Read 1–5 public search result pages.'),
    )

    def get_book_url(self, identifiers):
        ident = str((identifiers or {}).get('simania', ''))
        if re.fullmatch(r'[1-9][0-9]*', ident):
            return ('simania', ident, BASE + '/bookdetails.php?item_id=' + ident)

    def id_from_url(self, url):
        ident = book_id(url)
        return ('simania', ident) if ident else None

    def get_cached_cover_url(self, identifiers):
        ident = (identifiers or {}).get('simania')
        return self.cached_identifier_to_cover_url(str(ident)) if ident else None

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers=None, timeout=30):
        """Search by title or exact Simania ID, rank by author, and publish complete candidates."""
        if abort.is_set():
            return
        identifiers = identifiers or {}
        exact = self.get_book_url(identifiers)
        browser = self.browser
        limit = max(1, min(20, int(self.prefs['max_results'])))
        pages = max(1, min(5, int(self.prefs['max_pages'])))
        try:
            direct = None
            if exact:
                try:
                    direct = simania_client.details(browser, exact[1], timeout)
                except Exception:
                    log.exception('Simania ID lookup failed; trying title search if supplied.')
            if direct:
                candidates = [direct]
            elif title and title.strip():
                candidates = rank_books(simania_client.search(browser, title.strip(), abort, timeout, pages, log), title, authors)[:limit]
            else:
                log('Provide a title or a Simania identifier. ISBN-only lookup is not supported by this catalog scraper.')
                return
            for index, candidate in enumerate(candidates):
                if abort.is_set() or (index and abort.wait(0.5)):
                    return
                try:
                    book = direct if direct else simania_client.details(browser, candidate['id'], timeout)
                    if abort.is_set():
                        return
                    mi = Metadata(book['title'], book['authors'] or ['Unknown'])
                    mi.set_identifier('simania', book['id'])
                    mi.publisher = book['publisher'] or None
                    mi.comments = '<p>' + escape(book['comments']) + '</p>' if book['comments'] else None
                    mi.tags = book['tags']
                    if book.get('series'):
                        mi.series = book['series']
                        if book.get('series_index') is not None:
                            mi.series_index = book['series_index']
                    isbn = check_isbn(str(book.get('isbn') or ''))
                    if isbn:
                        mi.set_identifier('isbn', isbn)
                    language = canonicalize_lang({'עברית': 'he', 'אנגלית': 'en', 'ערבית': 'ar', 'רוסית': 'ru'}.get(book.get('language'), book.get('language', '')))
                    if language:
                        mi.languages = [language]
                    if book['year']:
                        mi.pubdate = datetime(book['year'], 1, 1, tzinfo=timezone.utc)
                    mi.source_relevance = index
                    if book['cover']:
                        self.cache_identifier_to_cover_url(book['id'], book['cover'])
                        mi.has_cover = True
                    self.clean_downloaded_metadata(mi)
                    result_queue.put(mi)
                except Exception:
                    log.exception('Could not parse Simania candidate', candidate['id'])
        except Exception as exc:
            log.exception('Simania metadata lookup failed')
            return str(exc)

    def download_cover(self, log, result_queue, abort, title=None, authors=None,
                       identifiers=None, timeout=30, get_best_cover=False):
        """Retrieve one matching public cover, with image validation before delivery."""
        if abort.is_set():
            return
        url = self.get_cached_cover_url(identifiers)
        if not url:
            results = Queue()
            error = self.identify(log, results, abort, title, authors, identifiers, timeout)
            if error:
                return error
            while not results.empty() and not url:
                url = self.get_cached_cover_url(results.get().identifiers)
        if not url or abort.is_set():
            return
        try:
            data = download_simania_cover(self.browser, url, abort, timeout, log)
            if data is not None:
                result_queue.put((self, data))
        except Exception as exc:
            log.exception('Simania cover download failed')
            return str(exc)
