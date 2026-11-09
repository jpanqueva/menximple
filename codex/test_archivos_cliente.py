"""Subida real HTTP a un servidor local, sin publicar datos ni usar producción."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from fastmcp.exceptions import ToolError
from memory_tui.mcp_local import _subir


class Archivos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pedidos = []
        cls.status = 201
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                cls.pedidos.append((self.path, dict(self.headers), body))
                respuesta = json.dumps({'sha256': hashlib.sha256(body).hexdigest()}).encode()
                self.send_response(cls.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(respuesta)))
                self.end_headers()
                self.wfile.write(respuesta)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.hilo = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.hilo.join()

    def setUp(self):
        self.__class__.status = 201
        self.pedidos.clear()
        self.env = patch.dict(os.environ, {'MEMORY_BASE_URL':
            f'http://127.0.0.1:{self.server.server_port}/api', 'MEMORY_APIKEY': 'test-only'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_bytes_crudos_autenticacion_nombre_y_expiracion(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'origen.bin'
            contenido = b'\x00\xffMENX-Codex\r\n'
            p.write_bytes(contenido)
            for _ in range(8):
                r = _subir(str(p), 'reporte.pdf', 1, 'prueba local')
                self.assertEqual(r['sha256'], hashlib.sha256(contenido).hexdigest())
            ruta, headers, recibido = self.pedidos[-1]
            self.assertEqual(len(self.pedidos), 8)
            self.assertEqual(recibido, contenido)
            self.assertEqual(headers['X-API-Key'], 'test-only')
            self.assertEqual(headers['Content-Type'], 'application/pdf')
            self.assertIn('nombre=reporte.pdf', ruta)
            self.assertIn('expira_dias=1', ruta)
            # Windows no permite esto con el descriptor de subida abierto.
            p.unlink()

    def test_error_http_no_queda_como_publicacion_exitosa(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'prueba.txt'
            p.write_text('prueba')
            for status in (404, 413, 415, 503):
                self.__class__.status = status
                with self.assertRaises(ToolError):
                    _subir(str(p), None, None, None)
            p.unlink()

    def test_archivo_inexistente_no_hace_peticion(self):
        with self.assertRaisesRegex(ToolError, 'no existe'):
            _subir('archivo-inexistente-menx', None, None, None)
        self.assertEqual(self.pedidos, [])


if __name__ == '__main__':
    unittest.main()
