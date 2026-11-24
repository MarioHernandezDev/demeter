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

import bancales_cv  # detección automática de muros (mismo directorio)
import dataset_io   # guardado de ejemplos etiquetados (Fase 1 del plan de mejora)

PORT = 8765
UPSTREAM = {
    "/proxy/pnoa-wms": "https://www.ign.es/wms-inspire/pnoa-ma",
    "/proxy/mdt-wcs": "https://servicios.idee.es/wcs-inspire/mdt",
}


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/api/ortho":
            return self._ortho(query)
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

    def _ortho(self, query):
        """GET /api/ortho?bbox=x0,y0,x1,y1&w=&h= → JPEG de la ortofoto (WMS o, si falla, teselas WMTS)."""
        from urllib.parse import parse_qs
        import numpy as np
        from PIL import Image
        import io
        try:
            q = parse_qs(query)
            x0, y0, x1, y1 = map(float, q["bbox"][0].split(","))
            w, h = int(q["w"][0]), int(q["h"][0])
            img = bancales_cv.ortho(x0, y0, x1, y1, px=(x1 - x0) / w)
            buf = io.BytesIO(); Image.fromarray((img * 255).astype(np.uint8)).save(buf, "JPEG", quality=88)
            body, code, ctype = buf.getvalue(), 200, "image/jpeg"
        except Exception as e:  # noqa: BLE001
            body, code, ctype = f"Error ortofoto: {e}".encode(), 502, "text/plain; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        """POST /api/detectar  {bbox: [x0, y0, x1, y1], poly: [[x, y], ...]} (EPSG:25830)
        → {muros: [{pts: [[x, y], ...], conf}], segundos}"""
        if self.path not in ("/api/detectar", "/api/ejemplo"):
            self.send_error(404); return
        import json
        import time
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            x0, y0, x1, y1 = map(float, req["bbox"])
            if x1 - x0 > 450 or y1 - y0 > 450:
                raise ValueError("Zona demasiado grande (máx. ~450 m de lado). Dibuja un terreno más pequeño.")
            if self.path == "/api/ejemplo":
                # POST /api/ejemplo {bbox, poly, muros, muros_auto, meta} → guarda un ejemplo etiquetado en dataset/
                body, code = json.dumps(dataset_io.guardar_ejemplo(req)).encode(), 200
            else:
                t = time.time()
                muros = bancales_cv.detectar(x0, y0, x1, y1, poly=req.get("poly"))
                body, code = json.dumps({"muros": muros, "segundos": round(time.time() - t, 1)}).encode(), 200
        except Exception as e:  # noqa: BLE001 — demo: devolver el error legible al navegador
            body, code = json.dumps({"error": str(e)}).encode(), 500
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    handler = partial(Handler, directory=str(Path(__file__).parent))
    print(f"Demo gemelo en http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()
