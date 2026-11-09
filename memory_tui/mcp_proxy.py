"""MCP del hub por stdio para Codex, reutilizando una sesión HTTP sin GET SSE."""
import asyncio
import os

from fastmcp import Client
from fastmcp.server import create_proxy

from .client import _transport


async def _run() -> None:
    key = os.environ.get('MEMORY_APIKEY')
    if not key:
        raise RuntimeError('falta MEMORY_APIKEY')
    # Entrar ANTES de create_proxy es importante: un Client desconectado haría
    # que FastMCP abriera una sesión remota nueva por cada petición.
    async with Client(_transport(key, None)) as backend:
        proxy = create_proxy(backend, name='menximple',
                             instructions=backend.initialize_result.instructions)
        await proxy.run_async(transport='stdio', show_banner=False)


def main() -> None:
    asyncio.run(_run())


if __name__ == '__main__':
    main()
