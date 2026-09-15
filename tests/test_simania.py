"""Offline parser, pagination and Calibre integration checks."""

import io
import json
from pathlib import Path
from queue import Queue
import sys
from threading import Event
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.simania_html import BASE, book_id, image_url, search_page, details_page
from src.simania_client import search
from src.simania_cover import download
from src.simania_plugin import SfarimSimaniaPlugin
from src.book_matching import normalize, rank_books

COVER = 'https://cdn.simania.co.il/bookimages/covers100/1006659.jpg'


def search_data(ids=(123,), more=False):
    return json.dumps({'success': True, 'data': {
        'books': [{'BOOK_ID': i, 'NAME': 'שפה : מבוא', 'AUTHOR': 'יובל אילון'} for i in ids],
        'pagination': {'hasNextPage': more}, 'entities': [{'type': 'author', 'id': 999}]}}).encode()


def product(**overrides):
    entry = {'@type': 'Book', 'sku': '123', 'url': BASE + '/bookdetails.php?item_id=123',
             'name': 'שפה : מבוא', 'author': [{'name': 'יובל אילון'}, {'name': 'מחבר שני'}],
             'publisher': {'name': 'הוצאה לדוגמה'}, 'datePublished': '2021', 'inLanguage': 'he',
             'isbn': '9780306406157', 'image': COVER, 'genre': 'ספרות » עיון',
             'description': 'סיפור בשנת 1990\\r\\nטקסט &lt;b&gt;נוסף&lt;/b&gt;',
             'isPartOf': {'@type': 'BookSeries', 'name': 'סדרה', 'position': '2.5'}}
    entry.update(overrides)
    return ('<html><script type="application/ld+json">' + json.dumps(entry) + '</script>'
            '<p>Review from 2026</p><img src="https://cdn.simania.co.il/images/user.jpg"></html>').encode()


class ParserTests(unittest.TestCase):
    def test_hebrew_search_and_deduplication(self):
        books, more = search_page(search_data((123, 123, 124), True))
        self.assertEqual([b['id'] for b in books], ['123', '124'])
        self.assertEqual(books[0]['authors'], ['יובל אילון'])
        self.assertTrue(more)

    def test_empty_results(self):
        self.assertEqual(search_page(search_data(())), ([], False))

    def test_failed_or_changed_api_is_not_empty_success(self):
        for payload in ({'success': False}, {'success': True, 'data': {}},
                        {'success': True, 'data': {'books': [], 'pagination': {}}}):
            with self.assertRaises(ValueError):
                search_page(json.dumps(payload))

    def test_metadata_and_original_cover(self):
        book = details_page(product(), '123')
        self.assertEqual(book['title'], 'שפה : מבוא')
        self.assertEqual(book['authors'], ['יובל אילון', 'מחבר שני'])
        self.assertEqual(book['publisher'], 'הוצאה לדוגמה')
        self.assertEqual(book['year'], 2021)
        self.assertEqual(book['cover'], COVER)
        self.assertEqual(book['series_index'], 2.5)
        self.assertEqual(book['tags'], ['ספרות', 'עיון'])
        self.assertNotIn('\\r', book['comments'])

    def test_missing_and_ambiguous_dates_stay_unknown(self):
        for date in ('', '2011 / 2021', 'תשפ״א', 0):
            self.assertIsNone(details_page(product(datePublished=date), '123')['year'])
        self.assertEqual(details_page(product(datePublished='2022-03-01'), '123')['year'], 2022)

    def test_wrong_book_identity_and_nonbook_rejected(self):
        with self.assertRaises(ValueError):
            details_page(product(), '999')
        with self.assertRaises(ValueError):
            details_page(product(**{'@type': 'Product'}), '123')

    def test_invalid_series_position(self):
        for value in ('unknown', 'NaN', 'Infinity', '-1'):
            self.assertIsNone(details_page(product(isPartOf={'@type': 'BookSeries', 'name': 'סדרה', 'position': value}), '123')['series_index'])

    def test_known_image_hosts_and_no_avatar_or_placeholder(self):
        self.assertEqual(image_url('/bookimages/covers100/1006659.jpg'), COVER)
        for value in ('https://example.com/cover.jpg', '/images/noPicYetM.jpg',
                      'https://simania.co.il.evil.test/bookimages/covers100/1006659.jpg'):
            self.assertIsNone(image_url(value))

    def test_book_links(self):
        self.assertEqual(book_id('/bookdetails.php?item_id=123'), '123')
        for value in ('/author.php?item_id=123', '/bookdetails.php?item_id=0',
                      '/bookdetails.php?item_id=123&item_id=456',
                      'https://example.com/bookdetails.php?item_id=123'):
            self.assertIsNone(book_id(value))

    def test_normalization_and_author_ranking(self):
        self.assertEqual(normalize('שָׂפָה'), normalize('שפה'))
        books = [{'id': '1', 'title': 'שפה', 'authors': ['אחר']},
                 {'id': '2', 'title': 'שפה', 'authors': ['יובל אילון']}]
        self.assertEqual(rank_books(books, 'שפה', ['יובל אילון'])[0]['id'], '2')


class ClientTests(unittest.TestCase):
    def test_native_response_closed_without_context_manager(self):
        response = Mock(spec=['read', 'close'])
        response.read.return_value = search_data()
        browser = Mock()
        browser.open.return_value = response
        self.assertEqual(len(search(browser, 'שפה', Event(), 30, 1, Mock())), 1)
        response.close.assert_called_once()

    def test_pagination_and_repeated_page(self):
        browser = Mock()
        browser.open.side_effect = [io.BytesIO(search_data(ids, True)) for ids in ((123,), (123, 124), (123, 124))]
        books = search(browser, 'שפה', Event(), 30, 5, Mock())
        self.assertEqual([b['id'] for b in books], ['123', '124'])
        self.assertEqual(browser.open.call_count, 3)
        self.assertIn('page=2', browser.open.call_args_list[1].args[0])

    def test_network_failure_preserves_earlier_candidates(self):
        browser = Mock()
        browser.open.side_effect = [io.BytesIO(search_data(more=True)), OSError('offline')]
        self.assertEqual(len(search(browser, 'שפה', Event(), 30, 3, Mock())), 1)

    def test_cancelled_search(self):
        abort = Event()
        abort.set()
        browser = Mock()
        self.assertEqual(search(browser, 'שפה', abort, 30, 3, Mock()), [])
        browser.open.assert_not_called()


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.plugin = SfarimSimaniaPlugin(None)
        self.book = details_page(product(), '123')
        self.log, self.abort = Mock(), Event()

    def test_metadata_maps_and_caches_cover(self):
        queue = Queue()
        with patch('src.simania_client.details', return_value=self.book):
            self.plugin.identify(self.log, queue, self.abort, identifiers={'simania': '123'})
        mi = queue.get_nowait()
        self.assertEqual(mi.pubdate.year, 2021)
        self.assertEqual(mi.isbn, '9780306406157')
        self.assertEqual(mi.languages, ['heb'])
        self.assertEqual(mi.series, 'סדרה')
        self.assertEqual(mi.series_index, 2.5)
        self.assertEqual(self.plugin.get_cached_cover_url(mi.identifiers), COVER)
        self.assertIn('&lt;b&gt;', mi.comments)

    def test_invalid_isbn_not_exported(self):
        self.book['isbn'] = '0'
        queue = Queue()
        with patch('src.simania_client.details', return_value=self.book):
            self.plugin.identify(self.log, queue, self.abort, identifiers={'simania': '123'})
        self.assertFalse(queue.get_nowait().isbn)

    def test_failed_identifier_falls_back_to_title(self):
        queue = Queue()
        with patch('src.simania_client.details', side_effect=[ValueError(), self.book]), patch('src.simania_client.search', return_value=[self.book]):
            self.plugin.identify(self.log, queue, self.abort, title='שפה', identifiers={'simania': '999'})
        self.assertEqual(queue.qsize(), 1)

    def test_cover_only_resolves_book_first(self):
        queue = Queue()
        with patch('src.simania_client.details', return_value=self.book), patch('src.simania_plugin.download_simania_cover', return_value=b'image') as fetch:
            self.plugin.download_cover(self.log, queue, self.abort, identifiers={'simania': '123'})
        self.assertEqual(queue.get_nowait()[1], b'image')
        self.assertEqual(fetch.call_args.args[1], COVER)

    def test_cancelled_identify(self):
        self.abort.set()
        with patch('src.simania_client.details') as fetch:
            self.plugin.identify(self.log, Queue(), self.abort, identifiers={'simania': '123'})
            fetch.assert_not_called()

    def test_cover_image_validation(self):
        browser = Mock()
        browser.open.return_value = io.BytesIO(b'<html>error</html>')
        with self.assertRaises(ValueError):
            download(browser, COVER, self.abort, 30, self.log)


if __name__ == '__main__':
    suite = unittest.TestSuite()
    for case in (ParserTests, ClientTests, PluginTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if outcome.wasSuccessful() else 1)
