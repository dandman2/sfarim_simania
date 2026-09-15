"""Download the original catalog cover and validate its image bytes."""

from calibre.utils.imghdr import identify
from .simania_client import read
from .simania_html import image_url


def download(browser, url, abort, timeout, log):
    """Return a valid public cover only while the Calibre operation is active."""
    if abort.is_set():
        return None
    if not image_url(url):
        raise ValueError('Invalid public cover URL.')
    data = read(browser, url, timeout)
    if abort.is_set():
        return None
    fmt, width, height = identify(data)
    if not fmt or not width or not height:
        raise ValueError('Simania returned no valid cover image.')
    log('Simania cover dimensions:', width, height)
    return data
