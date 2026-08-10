# API core del MCP Memory Server.
# Por defecto instala solo el núcleo. Para incluir embeddings:
#   docker build --build-arg WITH_EMBEDDINGS=true -t memoria-mcp .
FROM python:3.12-slim

ARG WITH_EMBEDDINGS=false
WORKDIR /app

COPY requirements.txt requirements-embeddings.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$WITH_EMBEDDINGS" = "true" ]; then \
         pip install --no-cache-dir -r requirements-embeddings.txt ; \
       fi

COPY memory_server ./memory_server

# Usuario no-root + caché de modelos (para persistir por volumen si hay embeddings)
RUN useradd -m app && mkdir -p /home/app/.cache && chown -R app /home/app /app
USER app
ENV HF_HOME=/home/app/.cache

EXPOSE 8000
CMD ["python", "-m", "memory_server.server"]
