"""
ProCode — проверка обновления.
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Запуск:
    python tools/test_update.py

Гоняет схему обновления без сети: поднимает локальный сервер на
localhost, кладёт туда подписанный манифест, потом ломает его четырьмя
разными способами и смотрит, что клиент во всех случаях отказывается.

Смысл: убедиться, что подпись действительно защищает. Если бы манифест
читался до проверки подписи, половина сценариев прошла бы, а в релизе
это была бы дыра.
"""

from __future__ import annotations

import base64
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from procode_guard.guard import public_key_from_bytes  # noqa: E402
from procode_guard.keys import PUBLIC_KEY_B64  # noqa: E402
from procode_guard.manifest import canonical  # noqa: E402
from procode_guard.update import check, install_update, verify_update_manifest  # noqa: E402

RESULTS: list[tuple[bool, str, str]] = []


def record(ok: bool, name: str, note: str = "") -> None:
    RESULTS.append((ok, name, note))
    print(f"  [{'ПРОШЁЛ' if ok else 'НЕ ПРОШЁЛ':^9}] {name}")
    if note:
        print(f"               {note}")


def serve(directory: Path):
    """Поднимает файловый сервер на свободном порту."""

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):  # молчание в тесте
            pass

    httpd = socketserver.TCPServer(("127.0.0.1", 0), lambda *a, **kw: Quiet(*a, directory=str(directory), **kw))
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{port}"


def main() -> int:
    import tempfile
    import shutil

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from procode_guard.update import write_update_manifest

    # Настоящая пара ключей, а не свежесгенерированная. Иначе тест
    # проверял бы не работу, а собственную ошибку: подпишем одним
    # ключом, проверим другим, и всегда получим «не сходится».
    # Так заодно видно, что выданные ключи реально работают вместе.
    key_path = ROOT / "keys" / "signing_key_ed25519.bin"
    if not key_path.is_file():
        print("Нет приватного ключа. Сначала: python tools/init_keys.py")
        return 2
    private = Ed25519PrivateKey.from_private_bytes(key_path.read_bytes())
    public = public_key_from_bytes(base64.b64decode(PUBLIC_KEY_B64))
    attacker = Ed25519PrivateKey.generate()

    work = Path(tempfile.mkdtemp(prefix="procode-update-"))
    httpd = None

    try:
        # Готовим «сервер обновлений» с настоящим релизом.
        payload = b"MZ\x90\x00" + bytes(1_200_000)
        (work / "ProCode.exe").write_bytes(payload)

        import hashlib

        write_update_manifest(
            work / "version.json",
            version="9.9.9",
            url="PLACEHOLDER",
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            private_key=private,
            notes="тест",
        )
        # Адрес внутри манифеста переписываем: подпись не сойдётся.
        # Поэтому подписываем заново, уже с настоящим адресом.

        httpd, base = serve(work)

        write_update_manifest(
            work / "version.json",
            version="9.9.9",
            url=f"{base}/ProCode.exe",
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            private_key=private,
            notes="тест",
        )

        print("\n1. Настоящее обновление")
        info = check(base, "9.8.0", public)
        record(
            info.ok and info.has_update and info.latest == "9.9.9",
            "подписанное обновление принимается",
            f"текущая {info.current} → последняя {info.latest}"
            + (f" | ОШИБКА: {info.err}" if not info.ok else ""),
        )

        print("\n2. Уже актуальная версия")
        info = check(base, "9.9.9", public)
        record(not info.has_update, "совпадающие версии обновления не предлагают")

        print("\n3. Откат версии")
        write_update_manifest(
            work / "version.json", "1.0.0", f"{base}/ProCode.exe",
            len(payload), hashlib.sha256(payload).hexdigest(), private,
        )
        info = check(base, "9.9.9", public)
        record(not info.ok, "откат на старую версию отклонён", info.err)

        print("\n4. Манифест под чужим ключом")
        write_update_manifest(
            work / "version.json", "10.0.0", f"{base}/ProCode.exe",
            len(payload), hashlib.sha256(payload).hexdigest(), attacker,
        )
        info = check(base, "9.9.9", public)
        record(not info.ok, "чужая подпись отклонена", info.err)

        print("\n5. Подмена поля в подписанном манифесте")
        good = json.loads((work / "version.json").read_text(encoding="utf-8"))
        good["version"] = "11.0.0"
        (work / "version.json").write_bytes(canonical(good))
        info = check(base, "9.9.9", public)
        record(not info.ok, "правка подписанного поля ломает проверку", info.err)

        print("\n6. Подпись удалена")
        good = json.loads((work / "version.json").read_text(encoding="utf-8"))
        (work / "version.json").write_bytes(canonical(good))
        (work / "version.json.sig").unlink()
        info = check(base, "9.9.9", public)
        record(not info.ok, "отсутствие подписи отклонено", info.err)

        print("\n7. Файл не совпадает с подписанным хешем")
        write_update_manifest(
            work / "version.json", "9.9.9", f"{base}/ProCode.exe",
            len(payload), hashlib.sha256(payload).hexdigest(), private,
        )
        (work / "ProCode.exe").write_bytes(
            b"MZ\x90\x00" + bytes(1_200_000) + "вредонос".encode("utf-8")
        )
        info = check(base, "9.8.0", public)
        if info.has_update:
            target = work / "target.exe"
            target.write_bytes(b"MZ" + b"\x00" * 1_100_000)
            result = install_update(info, target)
            record(not result["ok"], "испорченный файл не устанавливается", result.get("err", ""))
        else:
            record(False, "испорченный файл не устанавливается", "обновление не предложено")

        print("\n8. Установка годного файла")
        write_update_manifest(
            work / "version.json", "9.9.9", f"{base}/ProCode.exe",
            len(payload), hashlib.sha256(payload).hexdigest(), private,
        )
        (work / "ProCode.exe").write_bytes(payload)
        info = check(base, "9.8.0", public)
        target = work / "app" / "ProCode.exe"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"MZ" + b"\x00" * 1_100_000)
        result = install_update(info, target)
        record(
            result["ok"] and target.read_bytes() == payload,
            "годный файл встаёт на место",
            f"остался бэкап: {Path(result.get('backup','')).name}",
        )

    finally:
        if httpd:
            httpd.shutdown()
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for ok, _, _ in RESULTS if ok)
    total = len(RESULTS)

    print("\n" + "=" * 58)
    print(f"  Пройдено: {passed} из {total}")
    print("=" * 58)

    if passed != total:
        print("\n  Есть провалы. Обновление в релиз не выпускать.")
        return 1

    print("\n  Канал обновлений защищён: без нашей подписи клиент не примет")
    print("  ни подменённый манифест, ни подменённый файл, ни откат версии.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
