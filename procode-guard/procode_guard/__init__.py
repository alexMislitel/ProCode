"""
ProCode — защита целостности сборки.
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Публичный интерфейс модуля.
"""

from .guard import GuardReport, check, enforce, public_key_from_bytes
from .keys import PUBLIC_KEY_B64
from .manifest import build_manifest, hash_file, sign_manifest, verify_manifest

__all__ = [
    "GuardReport",
    "check",
    "enforce",
    "public_key_from_bytes",
    "PUBLIC_KEY_B64",
    "build_manifest",
    "hash_file",
    "sign_manifest",
    "verify_manifest",
]
