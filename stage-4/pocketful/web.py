"""The browser app: one HTML shell for every screen and the static files it loads.

Everything is read from `pocketful/web/` inside the image at start-up, so the screens
need nothing from the network at run time.
"""
from pathlib import Path

from .errors import not_found

WEB_ROOT = Path(__file__).resolve().parent / "web"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}


class Asset:
    def __init__(self, data: bytes, content_type: str):
        self.data = data
        self.content_type = content_type


def _load() -> dict[str, Asset]:
    files = {}
    for path in (WEB_ROOT / "assets").iterdir():
        if path.suffix in CONTENT_TYPES:
            files[path.name] = Asset(path.read_bytes(), CONTENT_TYPES[path.suffix])
    return files


_SHELL = Asset((WEB_ROOT / "index.html").read_bytes(), CONTENT_TYPES[".html"])
_ASSETS = _load()


def page() -> Asset:
    """The shell; the script renders the screen named by the URL path."""
    return _SHELL


def asset(name: str) -> Asset:
    found = _ASSETS.get(name)
    if found is None:
        raise not_found("no such asset")
    return found
