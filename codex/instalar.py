"""Instala los tres MCP en la configuración PERSONAL de Codex, sin tocar Claude.

Python 3.11+; ejecutar desde cualquier carpeta. No imprime credenciales.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone

INICIO = '# BEGIN MENX CODEX (managed by codex/instalar.py)'
FIN = '# END MENX CODEX'
NOMBRES = ('menximple', 'menximple-selector', 'menx-canal')
REPO = Path(__file__).resolve().parent.parent


def cadena(value):
    return json.dumps(str(value), ensure_ascii=False)


def encontrar_cli():
    shim = shutil.which('codex.cmd') or shutil.which('codex')
    if not shim:
        raise ValueError('instala Codex CLI y agrega codex al PATH')
    ruta = Path(shim).resolve()
    js = ruta.parent / 'node_modules/@openai/codex/bin/codex.js'
    if js.is_file():
        # En Windows matar el shim Node puede dejar vivo su hijo codex.exe.
        # Lanzar directamente el binario permite cancelar una entrega colgada.
        if os.name == 'nt':
            binarios = list((js.parent.parent / 'node_modules/@openai').glob('codex-win32-*/vendor/*/bin/codex.exe'))
            if len(binarios) == 1:
                return binarios[0]
        return js
    if ruta.suffix.lower() in ('.cmd', '.bat', '.ps1'):
        raise ValueError('no se encontró el ejecutable de Codex; usa --codex-cli <ruta a codex.js o ejecutable>')
    return ruta


def bloque(url, key, node=None, cli=None, solo_memorias=False):
    env = {'MEMORY_BASE_URL': url, 'MEMORY_APIKEY': key}
    lineas = [INICIO, '[mcp_servers.menximple]', f'url = {cadena(url)}',
              'startup_timeout_sec = 45', 'tool_timeout_sec = 120',
              '[mcp_servers.menximple.http_headers]', f'X-API-Key = {cadena(key)}', '']
    locales = [
        ('menximple-selector', sys.executable, ['-m', 'memory_tui.mcp_local'], {}),
    ]
    if not solo_memorias:
        locales.append(('menx-canal', node, [str(REPO / 'codex/menx-canal.mjs')], {'MENX_CODEX_CLI': str(cli)}))
    for nombre, comando, args, extra in locales:
        lineas += [f'[mcp_servers.{nombre}]', f'command = {cadena(comando)}',
                   f'args = {json.dumps(args, ensure_ascii=False)}',
                   'startup_timeout_sec = 45', 'tool_timeout_sec = 120']
        if nombre == 'menx-canal':
            lineas += ['env_vars = ["CODEX_THREAD_ID", "CODEX_SESSION_ID"]']
        lineas += [f'[mcp_servers.{nombre}.env]']
        lineas += [f'{k} = {cadena(v)}' for k, v in {**env, **extra}.items()]
        lineas += ['']
    return '\n'.join(lineas + [FIN, ''])


def preparar(original, nuevo):
    if original.count(INICIO) != original.count(FIN) or original.count(INICIO) > 1:
        raise ValueError('bloque MENX incompleto o duplicado en config.toml')
    if INICIO in original:
        antes, resto = original.split(INICIO)
        _, despues = resto.split(FIN)
        original = antes + despues.lstrip('\r\n')
    datos = tomllib.loads(original)
    conflictos = set(NOMBRES) & datos.get('mcp_servers', {}).keys()
    if conflictos:
        raise ValueError('ya existen MCP fuera del bloque administrado: ' + ', '.join(sorted(conflictos)))
    resultado = original.rstrip() + '\n\n' + nuevo
    tomllib.loads(resultado)  # validar antes de escribir
    return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-claude', action='store_true', help='copiar URL y apikey del hub en ~/.claude.json')
    parser.add_argument('--solo-memorias', action='store_true', help='instalar hub y selector/archivos; canales después')
    parser.add_argument('--url', default=os.environ.get('MEMORY_BASE_URL'))
    parser.add_argument('--codex-cli', type=Path, help='ruta a codex.js o al ejecutable nativo')
    opts = parser.parse_args()
    url, key = opts.url, os.environ.get('MEMORY_APIKEY')
    if opts.from_claude:
        cfg = json.loads((Path.home() / '.claude.json').read_text(encoding='utf-8-sig'))
        hub = cfg['mcpServers']['menximple']
        url = url or hub['url']
        key = key or hub['headers']['X-API-Key']
    url = url or input('URL del hub: ').strip()
    key = key or getpass.getpass('API key de MENX (oculta): ').strip()
    if not url.startswith(('https://', 'http://')) or not key:
        raise ValueError('URL HTTP(S) y apikey son obligatorias')
    import importlib.util
    if not importlib.util.find_spec('fastmcp') or not importlib.util.find_spec('memory_tui'):
        raise ValueError('instala primero el cliente: python -m pip install -e .')
    node, cli = None, None
    if not opts.solo_memorias:
        node = shutil.which('node')
        cli = opts.codex_cli or encontrar_cli()
        if not node or not cli.is_file():
            raise ValueError('se requieren Node y una ruta válida a Codex CLI')
        comando = [node, str(cli)] if cli.suffix.lower() in ('.js', '.mjs', '.cjs') else [str(cli)]
        # No admite shims de shell: el texto recibido nunca pasa por cmd o bash.
        if cli.suffix.lower() in ('.cmd', '.bat', '.ps1'):
            raise ValueError('usa codex.js o el ejecutable nativo, no un shim de shell')
        comprobacion = subprocess.run([*comando, 'queue', '--help'], capture_output=True, text=True)
        if comprobacion.returncode or '--thread' not in comprobacion.stdout or '--resume' not in comprobacion.stdout:
            raise ValueError('esta versión de Codex no ofrece queue --thread --message --resume; actualízala')
        if not (REPO / 'canal/node_modules/@modelcontextprotocol/sdk').is_dir():
            raise ValueError('instala primero el puente: npm --prefix canal ci')
    destino = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'config.toml'
    original = destino.read_text(encoding='utf-8-sig') if destino.exists() else ''
    resultado = preparar(original, bloque(url, key, node, cli, opts.solo_memorias))
    if resultado == original:
        print('MENX ya está configurado; no hay cambios.')
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        sello = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        shutil.copy2(destino, destino.with_name(f'config.toml.menx-{sello}.bak'))
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destino.parent,
                                     prefix='.menx-', delete=False) as f:
        temporal = Path(f.name)
        os.chmod(temporal, 0o600)
        f.write(resultado)
    os.replace(temporal, destino)
    nombres = NOMBRES[:2] if opts.solo_memorias else NOMBRES
    print(f'Configurados {", ".join(nombres)} en {destino}. Credenciales omitidas.')
    print('Reabre o reanuda Codex para cargar los MCP. Identifícate por conversación, nunca globalmente.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(f'No se instaló: {exc}') from None
