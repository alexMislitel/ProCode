"""
ProCode — защита целостности сборки.
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Манифест сборки: список файлов с их хешами плюс подпись.

Замысел такой. При сборке перечисляются все файлы, для каждого считается
SHA-256. Получается манифест. Манифест подписывается приватным ключом, и
подпись кладётся рядом. При запуске приложение проверяет подпись вшитым
публичным ключом, потом сверяет каждый файл с манифестом.

Что это даёт. Подделать файл нельзя — нельзя подделать хеш, а значит нельзя
подделать манифест, а значит нельзя подписать свой. Пересобрать с другим
содержимым и получить ту же подпись не получится. Ключи, которыми это
подписывается, живут на машине сборки и в поставку не попадают.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

# Хеш считается блоками, а не целиком: исполняемые файлы бывают большие,
# а Windows любит падать на чтении всего файла целиком.
CHUNK = 1024 * 1024

ALGORITHM = "ed25519"
MANIFEST_VERSION = 1


def canonical(payload: dict) -> bytes:
    """
    Байтовое представление, на котором считается подпись.

    Порядок ключей, отступы и экранирование обязаны быть фиксированными,
    иначе файл, не меняясь по смыслу, даст другой хеш и подпись не сойдётся.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(files: list[Path], root: Path, extra: dict | None = None) -> dict:
    """
    Собирает манифест по списку файлов.

    Пути в манифесте хранятся относительно корня через прямой слэш, чтобы
    список читался одинаково и на Windows, и на Linux.
    """
    entries: dict[str, str] = {}
    skipped: list[str] = []

    for path in sorted(files):
        if not path.is_file():
            skipped.append(str(path))
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            # Файл вне корня в манифест не попадает: иначе через него
            # можно было бы вытащить что угодно с диска.
            skipped.append(str(path))
            continue
        entries[relative.as_posix()] = hash_file(path)

    return {
        "version": MANIFEST_VERSION,
        "algorithm": ALGORITHM,
        "files": entries,
        **(extra or {}),
    }


@dataclass
class VerifyResult:
    ok: bool
    signature_ok: bool = False
    signature_error: str = ""
    tampered: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    checked: int = 0

    def reason(self) -> str:
        if self.ok:
            return "ok"
        if not self.signature_ok:
            return "signature"
        if self.tampered:
            return "tampered"
        return "missing"


def sign_manifest(manifest: dict, private_key) -> bytes:
    """Подписывает манифест приватным ключом Ed25519."""
    return private_key.sign(canonical(manifest))


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_signature(path: Path) -> bytes:
    return path.read_bytes()


def verify_manifest(manifest: dict, signature: bytes, public_key) -> VerifyResult:
    """
    Проверяет подпись манифеста.

    Именно здесь становится ясно, что подделать нельзя: подпись проверяется
    публичным ключом, а сам публичный ключ вшит в код. Подмена ключа ломает
    проверку подписи, а не даёт новую подпись.
    """
    from cryptography.exceptions import InvalidSignature

    try:
        public_key.verify(signature, canonical(manifest))
        return VerifyResult(ok=True, signature_ok=True)
    except InvalidSignature:
        return VerifyResult(
            ok=False, signature_ok=False, signature_error="подпись не сходится"
        )


def verify_files(manifest: dict, root: Path) -> VerifyResult:
    """
    Сверяет файлы на диске с манифестом.

    Путь из манифеста проверяется на выход за пределы корня: без этой
    проверки запись вида «../../Windows/System32/x.dll» заставила бы
    приложение читать что угодно с диска.
    """
    result = VerifyResult(ok=True, signature_ok=True)
    root_resolved = root.resolve()

    for relative, expected in manifest.get("files", {}).items():
        target = (root_resolved / relative).resolve()

        if not str(target).startswith(str(root_resolved)):
            result.ok = False
            result.tampered.append(relative)
            continue

        if not target.is_file():
            result.ok = False
            result.missing.append(relative)
            continue

        result.checked += 1
        if hash_file(target) != expected:
            result.ok = False
            result.tampered.append(relative)

    return result
