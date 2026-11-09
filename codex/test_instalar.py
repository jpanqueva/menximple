"""Protecciones del instalador: nunca sobrescribir configuración ajena."""
import importlib.util
from pathlib import Path
import tomllib
import unittest

spec = importlib.util.spec_from_file_location('instalar', Path(__file__).with_name('instalar.py'))
instalar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(instalar)


class Configuracion(unittest.TestCase):
    def test_preserva_configuracion_y_reinstala_sin_duplicar(self):
        original = 'model = "modelo-local"\n[mcp_servers.otro]\ncommand = "otro"\n'
        bloque = instalar.bloque('https://example.test/mcp', 'clave-"\\\n', solo_memorias=True)
        primera = instalar.preparar(original, bloque)
        self.assertEqual(primera, instalar.preparar(primera, bloque))
        datos = tomllib.loads(primera)
        self.assertEqual(datos['model'], 'modelo-local')
        self.assertEqual(datos['mcp_servers']['otro']['command'], 'otro')
        self.assertEqual(datos['mcp_servers']['menximple']['http_headers']['X-API-Key'], 'clave-"\\\n')
        self.assertNotIn('menx-canal', datos['mcp_servers'])

    def test_no_reemplaza_mcp_existente_no_administrado(self):
        with self.assertRaisesRegex(ValueError, 'ya existen MCP'):
            instalar.preparar('[mcp_servers.menximple]\nurl="https://example.test"', '')

    def test_bloque_incompleto_no_se_repara_adivinando(self):
        with self.assertRaisesRegex(ValueError, 'incompleto'):
            instalar.preparar(instalar.INICIO, '')


if __name__ == '__main__':
    unittest.main()
