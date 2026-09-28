"""Build download metadata and save original responses beside their manifests."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def build_manifest(
    raw_bytes: bytes,
    *,
    source: str,
    endpoint: str,
    parameters: dict[str, str],
    retrieved_at: datetime,
    license_info: str | None = None,
) -> dict[str, object]:
    """Describe a download using its original retrieval time and response bytes."""
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("Retrieval time must include a UTC offset.")

    return {
        "source": source,
        "endpoint": endpoint,
        "parameters": parameters.copy(),
        "retrieved_at_utc": retrieved_at.astimezone(UTC).isoformat(),
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "license": license_info,
    }


def save_response(
    sample_path: Path,
    raw_bytes: bytes,
    manifest: dict[str, object],
) -> None:
    """Save a new response/manifest pair without replacing existing files.

    These are sequential writes, not an atomic pair. An interrupted save may
    leave an incomplete pair, which the caller should report rather than reuse.
    """
    manifest_path = sample_path.with_suffix(".manifest.json")
    if sample_path == manifest_path:
        raise ValueError("Response and manifest paths must be different.")
    if sample_path.exists() or manifest_path.exists():
        raise FileExistsError(
            "Response or manifest already exists; refusing to overwrite."
        )
    if manifest.get("raw_sha256") != hashlib.sha256(raw_bytes).hexdigest():
        raise ValueError("Manifest hash does not match the response bytes.")

    # Serialize before creating files, so invalid metadata does not leave a sample.
    manifest_text = json.dumps(manifest, indent=2, allow_nan=False)
    sample_path.parent.mkdir(parents=True, exist_ok=True)

    with sample_path.open("xb") as response_file:
        response_file.write(raw_bytes)
    with manifest_path.open("x", encoding="utf-8") as manifest_file:
        manifest_file.write(manifest_text)
