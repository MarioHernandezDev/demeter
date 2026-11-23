"""Servidor local de la demo del gemelo digital.

Sirve los ficheros estáticos y hace de proxy hacia los servicios del IGN, porque a veces
responden sin la cabecera CORS y el navegador bloquea la ortofoto o el relieve.
Solo reenvía a los hosts de la lista blanca.

Uso:  python demo/gemelo/server.py   →  http://localhost:8765
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PORT = 8765
UPSTREAM = {
    "/proxy/pnoa-wms": "https://www.ign.es/wms-inspire/pnoa-ma",
    "/proxy/mdt-wcs": "https://servicios.idee.es/wcs-inspire/mdt",
}


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path, _, query = self.path.partition("?")
        base = UPSTREAM.get(path)
        if base is None:
            return super().do_GET()
        url = f"{base}?{query}"
        try:
            with urlopen(Request(url, headers={"User-Agent": "demeter-demo"}), timeout=60) as r:
                body = r.read()
                self.send_response(r.status)
                self.send_header("Content-Type", r.headers.get("Content-Type", "application/octet-stream"))
        except HTTPError as e:
            body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "text/plain"))
        except (URLError, TimeoutError) as e:
            body = f"Error contactando con el IGN: {e}".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    handler = partial(Handler, directory=str(Path(__file__).parent))
    print(f"Demo gemelo en http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()
