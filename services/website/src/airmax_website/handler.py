import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from airmax_website.app.main import route
from airmax_website.config import Settings


def _reader():
    settings = Settings()
    if settings.store == "local":
        from .adapters.local_reader import LocalReader

        return LocalReader(settings.local_root)
    from .adapters.s3_reader import S3Reader

    return S3Reader(settings.results_bucket)


def lambda_handler(event, _context=None, reader=None):
    status, content_type, body = route(event.get("rawPath", "/"), reader or _reader())
    try:
        response_body = body.decode("utf-8")
        encoded = False
    except UnicodeDecodeError:
        response_body = base64.b64encode(body).decode()
        encoded = True
    return {
        "statusCode": status,
        "headers": {"content-type": content_type, "cache-control": "no-cache"},
        "isBase64Encoded": encoded,
        "body": response_body,
    }


class _LocalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, content_type, body = route(self.path, _reader())
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print("AirMax map: http://localhost:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), _LocalHandler).serve_forever()
