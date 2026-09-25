"""
ProCode — сборка и подпись манифеста.
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Запуск:
    python tools/build_manifest.py <папка-с-программой>

Делает три вещи:
    1. обходит папку и считает SHA-256 каждого файла
    2. собирает манифест
    3. подписывает его приватным ключом

Результат рядом с программой:
    procode.manifest.json   — что внутри
    procode.manifest.sig    — подпись

Приватный ключ читается из keys/signing_key_ed25519.bin. Сам файл
подписи и манифеста исключены из обхода, иначе они посчитали бы сами
себя и хеши не сходились бы при каждой пересборке.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from procode_guard.manifest import (  # noqa: E402
    MANIFEST_VERSION,
    build_manifest,
    canonical,
    sign_manifest,
)

PRIVATE_PATH = ROOT / "keys" / "signing_key_ed25519.bin"

# Папки, содержимое которых не имеет смысла проверять: кэш, логи,
# временные файлы, служебные каталоги.
SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    "logs", "tmp", "temp", "cache", ".pytest_cache", "keys",
}

# Расширения, которые не имеют смысла проверять.
SKIP_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".bak", ".old"}

# Служебные файлы самой защиты.
SKIP_NAMES = {"procode.manifest.json", "procode.manifest.sig"}


def collect(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in SKIP_NAMES:
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        found.append(path)
    return found


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    root = Path(argv[1]).resolve()
    if not root.is_dir():
        print(f"Нет такой папки: {root}")
        return 2

    if not PRIVATE_PATH.is_file():
        print("Нет приватного ключа. Сначала:")
        print("    python tools/init_keys.py")
        return 2

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    files = collect(root)
    if not files:
        print(f"В {root} не нашлось ни одного файла.")
        return 2

    manifest = build_manifest(files, root, extra={"build": MANIFEST_VERSION})

    private = Ed25519PrivateKey.from_private_bytes(PRIVATE_PATH.read_bytes())
    signature = sign_manifest(manifest, private)

    manifest_path = root / "procode.manifest.json"
    signature_path = root / "procode.manifest.sig"

    manifest_path.write_bytes(canonical(manifest))
    signature_path.write_bytes(signature)

    size = sum(path.stat().st_size for path in files)
    print(f"Файлов в манифесте: {len(manifest['files'])}")
    print(f"Общий размер:        {size / 1024 / 1024:.1f} МБ")
    print(f"Манифест:            {manifest_path.name} ({manifest_path.stat().st_size} байт)")
    print(f"Подпись:             {signature_path.name} ({len(signature)} байт)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
