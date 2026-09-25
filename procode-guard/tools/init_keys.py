"""
ProCode — создание ключей подписи.
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Запуск:
    python tools/init_keys.py

Создаёт пару Ed25519:
    приватный ключ — сюда, в keys/ (в поставку не идёт)
    публичный ключ  — печатает, его надо вписать в procode_guard/keys.py

Приватный ключ — это и есть подпись сборки. Потеряем его — придётся
выпускать новую версию с новым ключом. Утечка — значит кто угодно сможет
подписать свою сборку под нашим именем. Поэтому он лежит в каталоге,
который точно не попадает в релиз, и в репозиторий не коммитится.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS_DIR = ROOT / "keys"
PRIVATE_PATH = KEYS_DIR / "signing_key_ed25519.bin"
PUBLIC_PATH = KEYS_DIR / "signing_key_ed25519.pub"


def main() -> int:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if PRIVATE_PATH.exists():
        print(f"Приватный ключ уже есть: {PRIVATE_PATH}")
        print("Новый ключ означает: старые сборки перестают проходить проверку.")
        answer = input("Создать новый поверх? (yes/N) ").strip().lower()
        if answer != "yes":
            print("Оставляем как есть.")
            return show_public()

    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    private = Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes_raw()
    public_bytes = private.public_key().public_bytes_raw()

    PRIVATE_PATH.write_bytes(private_bytes)
    PUBLIC_PATH.write_bytes(public_bytes)

    print(f"Приватный ключ: {PRIVATE_PATH}")
    print("  Этот файл НИКОГДА не попадает в сборку и в репозиторий.")
    print()
    return show_public()


def show_public() -> int:
    public_bytes = PUBLIC_PATH.read_bytes()
    encoded = base64.b64encode(public_bytes).decode("ascii")

    print("Публичный ключ впиши в procode_guard/keys.py:")
    print()
    print(f'PUBLIC_KEY_B64 = "{encoded}"')
    print()
    print("Этот ключ можно публиковать. Он и так есть в коде.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
