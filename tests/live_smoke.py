"""Live verification of the installable ZIP, with no library or installation changes."""

from pathlib import Path
from queue import Queue
from threading import Event
from calibre.customize.zipplugin import loader
from calibre.utils.logging import default_log
from calibre.utils.imghdr import identify


def main():
    root = Path(__file__).resolve().parents[1]
    version = (root / 'version.txt').read_text().strip()
    plugin = loader.load(str(root / ('sfarim_simania_v' + version + '.zip')))(None)
    results = Queue()
    error = plugin.identify(default_log, results, Event(), title='העונה החמישית', authors=['נ.ק. ג׳מיסין'])
    assert not error, error
    matches = []
    while not results.empty():
        matches.append(results.get())
    mi = next(m for m in matches if m.identifiers.get('simania') == '1006659')
    assert mi.pubdate.year == 2022
    assert mi.publisher == 'אופוס'
    assert mi.title == 'העונה החמישית'
    assert mi.authors and mi.comments and mi.series == 'העולם השבור'
    assert not mi.isbn, 'The source placeholder ISBN must not be exported'
    covers = Queue()
    fresh_plugin = type(plugin)(None)
    error = fresh_plugin.download_cover(default_log, covers, Event(), identifiers=mi.identifiers)
    assert not error, error
    assert not covers.empty(), 'No cover returned'
    fmt, width, height = identify(covers.get()[1])
    assert width >= 1000 and height >= 1500, 'Expected the original cover, not a resized thumbnail'
    print('LIVE PASS:', plugin.name, plugin.version, 'year:', mi.pubdate.year, 'cover:', fmt, width, height)


if __name__ == '__main__':
    main()
