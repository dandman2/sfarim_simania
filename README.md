# Sfarim Simania

Standalone Calibre metadata-source plugin for [Simania](https://simania.co.il).
Uses the public search endpoint used by the website and Book JSON-LD embedded in book HTML.
No login, API key, browser extension or another Sfarim plugin is required.

## Install and use

1. Open **Calibre → Preferences → Plugins → Load plugin from file**.
2. Select `sfarim_simania_v1.1.zip`, accept the plugin prompt, then restart Calibre.
3. Enable **Sfarim Simania** in **Preferences → Metadata download**.
4. Select a book with title and preferably author, then use **Edit metadata → Download metadata** or **Download cover**.

Importing a book alone does not invoke the plugin. To verify this source independently,
temporarily enable only Sfarim Simania when downloading metadata, then restore your source selection.
No automatic import handling is included. Installation does not modify your other plugins.

## Metadata and covers

- Search by title and rank by normalized Hebrew title and author. Alternate editions remain available for manual selection.
- Read title, authors, publisher, publication year, description, genre tags, language and series/index when supplied.
- Record the catalog ID as a `simania` identifier. Existing identifiers support direct lookup.
- Validate ISBN checksums before exporting. Simania often supplies `0`, which is ignored.
- Missing dates stay unset; years in reviews, descriptions or image filenames are not publication dates.
- Use the original image URL in the book's structured metadata, rather than the website's resized image proxy.
  The verified sample is 1594 × 2480 pixels; other books may have smaller originals. Images are never upscaled.
- A placeholder or missing cover produces no replacement cover.
- User reviews and user profiles are not included in book metadata.
- Author lists preserve source grouping; Hebrew names joined in one source string are not split by guessing.
- ISBN-only searching is not implemented; provide a title or Simania identifier.

The public search endpoint is not a guaranteed third-party API contract. Website changes may require
a plugin update. No login, rating, review, sale, analytics or account endpoints are called.

## Settings and diagnostics

**Preferences → Plugins → Metadata source → Sfarim Simania → Customize plugin**:

- Maximum metadata candidates: default 5, bounded to 1–20.
- Maximum search pages: default 3, bounded to 1–5.

Requests use Calibre's browser and timeout, with short delays between pages and book lookups.
Cancellation prevents further processing. Repeated result pages are deduplicated and stop pagination.
Successful earlier results survive a later-page failure. Errors appear in Calibre's metadata job log.

## Versioned builds

Run `build_plugin.cmd` from any directory with Python 3.9+ available on PATH.
It reads `version.txt`, increments the minor integer, updates Calibre's internal plugin version and
exports `sfarim_simania_v<major>.<minor>.zip`. The supplied release is 1.1; the next successful build is 1.2.
Version 1.10 follows 1.9. `version.txt` records the last successfully exported release.

Only `src/` is included. The builder prevents concurrent builds and overwriting existing ZIPs,
validates before publication, and rolls back version changes if committing fails.
Load each new ZIP into Calibre manually, then restart Calibre.

## Validation

Use Calibre's Python for plugin tests and isolate its test configuration:

```powershell
$env:CALIBRE_CONFIG_DIRECTORY = Join-Path $env:TEMP 'simania-plugin-validation'
& 'C:\Program Files\Calibre2\calibre-debug.exe' -e .\tests\test_simania.py
python .\tests\test_build_plugin.py
& 'C:\Program Files\Calibre2\calibre-debug.exe' -e .\tests\live_smoke.py
```

Parser/integration tests are offline; build tests use temporary copies. The opt-in live test loads
the current ZIP, searches a known title, verifies its edition and retrieves an original cover.
Tests do not install plugins or change any library books.
