"""Configuración por entorno. Todo lo desplegable es configurable (base_url incluida).

Almacenamiento: únicamente Qdrant (documentos en payload + vectores del resumen)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Servidor MCP (el path público /Yu4/api lo mapea nginx -> /mcp)
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000
    memory_base_url: str = "http://localhost:8000/mcp"

    # Qdrant (único almacén)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""  # apikey del propio Qdrant, si el despliegue la exige

    # Embeddings del resumen (opcional). Los vectores viven en Qdrant.
    embeddings_enabled: bool = False
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_dims: int = 384  # debe coincidir con el modelo (e5-small = 384)

    # Autenticación
    admin_token: str = ""   # protege crear/listar cuentas; vacío = abierto (solo dev)
    dev_apikey: str = ""    # apikey por defecto para pruebas/stdio sin headers HTTP


settings = Settings()
