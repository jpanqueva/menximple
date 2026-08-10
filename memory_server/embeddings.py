"""Embeddings del `resumen`. Import perezoso: solo se carga el modelo si se usa.

El modelo es ligero (default multilingual-e5-small, 384d, CPU, buen español).
No es fijo que se use siempre — se controla por settings.embeddings_enabled."""
from .config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # import perezoso
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed(text: str, kind: str = "passage") -> list[float]:
    # Los modelos e5 esperan prefijo "query:"/"passage:".
    prefix = "query: " if kind == "query" else "passage: "
    vec = _get_model().encode(prefix + text, normalize_embeddings=True)
    return vec.tolist()


def dims() -> int:
    return int(_get_model().get_sentence_embedding_dimension())
