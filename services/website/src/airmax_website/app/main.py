import json
from pathlib import Path

from airmax_website.app.presenter import dashboard_view
from airmax_website.config import Settings

STATIC = Path(__file__).parent / "static"
STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/vendor/maplibre-gl.js": (
        "vendor/maplibre-gl.js",
        "application/javascript; charset=utf-8",
    ),
    "/vendor/maplibre-gl.css": ("vendor/maplibre-gl.css", "text/css; charset=utf-8"),
}


def route(path: str, reader) -> tuple[int, str, bytes]:
    if path in STATIC_ROUTES:
        filename, content_type = STATIC_ROUTES[path]
        return 200, content_type, (STATIC / filename).read_bytes()
    if path == "/api/current":
        result = json.loads(reader.result())
        body = json.dumps(
            dashboard_view(result, Settings().stale_hours),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return 200, "application/json; charset=utf-8", body.encode()
    if path == "/data.json":
        return 200, "application/json", reader.result()
    if path in ("/assets/municipalities.min.geojson", "/municipalities.json"):
        return 200, "application/geo+json", reader.municipalities()
    return 404, "text/plain; charset=utf-8", b"Not found"
