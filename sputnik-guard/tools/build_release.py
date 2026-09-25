"""
Спутник — сборка релиза.
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Запуск на машине сборки:

    python tools/build_release.py <папка-с-программой> [папка-выгрузки]

Делает по порядку:

    1. проверяет, что приватный ключ на месте
    2. считает SHA-256 всех файлов программы
    3. собирает манифест и подписывает его
    4. кладёт манифест и подпись рядом с программой
    5. копирует всё в папку выгрузки
    6. печатает чек-лист того, что человек должен сделать руками

Приватный ключ читается, копируется в выгрузку и в репозиторий никогда
не попадает. Если его нет — сборка обязана упасть, а не выпустить
неподписанный релиз: неподписанная сборка всё равно не запустится у
пользователя, но упадёт у него, а не у нас.

Что делается руками и почему не автоматом:

    • подпись .exe сертификатом Authenticode — нужен платный сертификат
      и инструмент от его центра. Подробности в README.
    • загрузка на сервер и обновление страницы загрузок.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sputnik_guard.manifest import (  # noqa: E402
    build_manifest,
    canonical,
    sign_manifest,
)

PRIVATE_PATH = ROOT / "keys" / "signing_key_ed25519.bin"

MANIFEST_NAME = "sputnik.manifest.json"
SIGNATURE_NAME = "sputnik.manifest.sig"

SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    "logs", "tmp", "temp", "cache", ".pytest_cache", "keys",
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".bak", ".old"}
SKIP_NAMES = {MANIFEST_NAME, SIGNATURE_NAME}


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


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    source = Path(argv[1]).resolve()
    if not source.is_dir():
        print(f"Нет такой папки: {source}")
        return 2

    out = Path(argv[2]).resolve() if len(argv) > 2 else Path.cwd() / "release" / stamp()

    # 1. Ключ.
    if not PRIVATE_PATH.is_file():
        print("Нет приватного ключа:", PRIVATE_PATH)
        print("Создать:  python tools/init_keys.py")
        return 2

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.from_private_bytes(PRIVATE_PATH.read_bytes())

    # 2–3. Манифест и подпись.
    files = collect(source)
    if not files:
        print(f"В {source} не нашлось ни одного файла.")
        return 2

    version = stamp()
    manifest = build_manifest(
        files,
        source,
        extra={
            "product": "Спутник",
            "name": source.name,
            "build": version,
            "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    signature = sign_manifest(manifest, private)

    # 4. Рядом с программой.
    (source / MANIFEST_NAME).write_bytes(canonical(manifest))
    (source / SIGNATURE_NAME).write_bytes(signature)

    # 5. В выгрузку.
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(source, out, dirs_exist_ok=True)

    total = sum(path.stat().st_size for path in files)

    print()
    print("  Релиз собран")
    print("  " + "-" * 52)
    print(f"  версия:        {version}")
    print(f"  файлов:        {len(manifest['files'])}")
    print(f"  размер:        {total / 1024 / 1024:.1f} МБ")
    print(f"  выгрузка:      {out}")
    print(f"  манифест:      {MANIFEST_NAME}")
    print(f"  подпись:       {SIGNATURE_NAME} ({len(signature)} байт)")
    print()

    # 6. Чек-лист.
    print("  Осталось руками")
    print("  " + "-" * 52)
    print("  [ ]  подписать .exe сертификатом Authenticode")
    print("       код в этом не участвует: подпись манифеста и подпись")
    print("       exe — разные вещи, они не мешают друг другу")
    print("  [ ]  выложить на сервер в папку загрузок")
    print("  [ ]  вписать версию и хеши на страницу загрузок")
    print("  [ ]  проверить: python tools/verify_release.py " + str(out))
    print()
    print("  Хеш манифеста SHA-256:")
    print("   ", hashlib.sha256(canonical(manifest)).hexdigest())
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
