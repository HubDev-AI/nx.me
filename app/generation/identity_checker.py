"""Identity preservation checker — ArcFace embedding comparison.

ADR-1: Embeddings are ephemeral. Computed, compared, discarded.
Never stored in any database or log.

Uses insightface buffalo_l model, CPU execution.
Pre-loaded at worker startup via preload_arcface().
"""

from __future__ import annotations

import io
import logging
import threading

import numpy as np
import PIL.Image

from app.config import settings
from app.generation.models import IdentityCheckResult

logger = logging.getLogger(__name__)

_arcface_app = None
_arcface_lock = threading.Lock()  # insightface is not thread-safe


def preload_arcface() -> None:
    """Pre-load ArcFace model at worker startup. Blocks until ready.

    Raises:
        RuntimeError: If the model fails to load.
    """
    global _arcface_app
    try:
        from insightface.app import FaceAnalysis

        _arcface_app = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
        )
        _arcface_app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("ArcFace buffalo_l model pre-loaded")
    except Exception as exc:
        _arcface_app = None
        raise RuntimeError(f"Failed to preload ArcFace model: {exc}") from exc


def check_identity(
    source_image_bytes: bytes,
    generated_image_bytes: bytes,
    threshold: float | None = None,
) -> IdentityCheckResult:
    """Compare source and generated face embeddings.

    Args:
        source_image_bytes: Original selfie bytes.
        generated_image_bytes: Generated glow-up bytes.
        threshold: Similarity threshold (default from config, per-tier override).

    Returns:
        IdentityCheckResult with score, pass/fail, face detection status.
        Embeddings are discarded after comparison (ADR-1).
    """
    if _arcface_app is None:
        raise RuntimeError("ArcFace not pre-loaded. Call preload_arcface() at startup.")

    if threshold is None:
        threshold = settings.IDENTITY_SIMILARITY_THRESHOLD

    # Load images as numpy arrays (context managers prevent resource leaks)
    with PIL.Image.open(io.BytesIO(source_image_bytes)) as _src_pil:
        source_img = np.array(_src_pil.convert("RGB"))
    with PIL.Image.open(io.BytesIO(generated_image_bytes)) as _gen_pil:
        gen_img = np.array(_gen_pil.convert("RGB"))

    # Detect faces and extract embeddings (lock for thread safety)
    with _arcface_lock:
        source_faces = _arcface_app.get(source_img)
    if not source_faces:
        logger.warning("No face detected in source image")
        return IdentityCheckResult(
            similarity_score=0.0,
            identity_preserved=False,
            face_detected_in_output=True,  # Source issue, not output
        )

    with _arcface_lock:
        gen_faces = _arcface_app.get(gen_img)
    if not gen_faces:
        logger.warning("No face detected in generated image")
        return IdentityCheckResult(
            similarity_score=0.0,
            identity_preserved=False,
            face_detected_in_output=False,
        )

    # Compare embeddings (cosine similarity)
    source_emb = source_faces[0].embedding
    gen_emb = gen_faces[0].embedding

    similarity = float(
        np.dot(source_emb, gen_emb)
        / (np.linalg.norm(source_emb) * np.linalg.norm(gen_emb) + 1e-8)
    )

    # Embeddings discarded here — ADR-1 compliance
    # source_emb, gen_emb are local variables, garbage collected

    identity_preserved = similarity >= threshold

    logger.info(
        "Identity check: similarity=%.3f, threshold=%.2f, preserved=%s",
        similarity,
        threshold,
        identity_preserved,
    )

    return IdentityCheckResult(
        similarity_score=round(similarity, 4),
        identity_preserved=identity_preserved,
        face_detected_in_output=True,
    )
