"""
ProCode — публикация обновления.
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Одна команда публикует релиз и обновляет всех клиентов сразу.

Запуск на машине сборки:

    python tools/publish_update.py <папка-релиза> [версия] [заметки]

Что делает, по порядку:

    1. проверяет, что релиз собран и подписан (иначе не выпускаем)
    2. считает хеш файла
    3. собирает version.json и подписывает его тем же ключом
    4. заливает на сервер
    5. проверяет, что сервер отдаёт то, что положили
    6. печатает, что готово

Клиенты узнают о новой версии при следующем запуске. Ничего вручную
делать не нужно: подняли version.json — все обновились сами.

Чего не делает и почему: не подписывает .exe сертификатом Authenticode.
Это отдельный платный шаг, см. README. Подпись манифеста и подпись exe —
разные вещи, они не мешают друг другу.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from procode_guard.keys import PUBLIC_KEY_B64  # noqa: E402
from procode_guard.guard import public_key_from_bytes  # noqa: E402
from procode_guard.guard import check as verify_release  # noqa: E402
from procode_guard.update import write_update_manifest  # noqa: E402

import base64  # noqa: E402

PRIVATE_PATH = ROOT / "keys" / "signing_key_ed25519.bin"

# Куда складываем на сервере. Ведь /var/www/wowbot-license — это
# корень существующих проектов; ProCode кладём рядом, своей папкой.
REMOTE_DIR = "/var/www/wowbot-license/procode"
REMOTE_UPDATE_URL = "http://185.43.4.62/updates/procode"

# Доступ к серверу берётся из переменных окружения, ключ в код не вшит.
SSH_KEY_ENV = "PROCODE_SSH_KEY"
SSH_USER_ENV = "PROCODE_SSH_USER"


def ssh_command(*args: str) -> list[str]:
    import os

    key = os.environ.get(SSH_KEY_ENV)
    user = os.environ.get(SSH_USER_ENV, "root")
    if not key:
        raise SystemExit(
            f"Не задана переменная {SSH_KEY_ENV} — путь к ключу ssh.\n"
            f"Пример: set {SSH_KEY_ENV}=C:\\Users\\alexk\\.ssh\\procode_deploy"
        )
    return ["ssh", "-i", key, "-o", "BatchMode=yes", f"{user}@185.43.4.62", *args]


def scp_command(local: Path, remote: str) -> list[str]:
    import os

    key = os.environ.get(SSH_KEY_ENV)
    user = os.environ.get(SSH_USER_ENV, "root")
    if not key:
        raise SystemExit(f"Не задана переменная {SSH_KEY_ENV}")
    return ["scp", "-i", key, "-o", "BatchMode=yes", str(local), f"{user}@185.43.4.62:{remote}"]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    release = Path(argv[1]).resolve()
    version = argv[2] if len(argv) > 2 else ""
    notes = argv[3] if len(argv) > 3 else ""

    if not release.is_dir():
        print(f"Нет такой папки: {release}")
        return 2

    if not PRIVATE_PATH.is_file():
        print("Нет приватного ключа:", PRIVATE_PATH)
        return 2

    # 1. Релиз должен быть подписан. Неподписанный выпускать нельзя:
    #    клиент всё равно его не примет, а сломается уже у него.
    public_key = public_key_from_bytes(base64.b64decode(PUBLIC_KEY_B64))
    report = verify_release(release, public_key)
    if not report.ok:
        print(f"Релиз не проходит проверку: этап {report.stage}, {report.detail}")
        for name in (report.tampered or [])[:5]:
            print("   изменён:", name)
        for name in (report.missing or [])[:5]:
            print("   отсутствует:", name)
        return 1

    print(f"  релиз подписан, файлов проверено: {report.checked}")

    if not version:
        meta = json.loads((release / "procode.manifest.json").read_text(encoding="utf-8"))
        version = str(meta.get("build", "")) or "0.0.0"

    # Ищем главный файл программы: самый большой .exe.
    executables = sorted(release.glob("*.exe"), key=lambda p: p.stat().st_size, reverse=True)
    if not executables:
        print("В релизе нет .exe — публиковать нечего.")
        return 1
    exe = executables[0]

    payload = exe.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()

    print(f"  версия:  {version}")
    print(f"  файл:    {exe.name}  {len(payload) / 1024 / 1024:.1f} МБ")
    print(f"  sha256:  {digest}")

    # 2. Готовим подписанный манифест обновления.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.from_private_bytes(PRIVATE_PATH.read_bytes())

    url = f"{REMOTE_UPDATE_URL}/{exe.name}"
    local_manifest = release / "version.json"
    write_update_manifest(local_manifest, version, url, len(payload), digest, private, notes)

    # 3. Заливаем. Сначала манифест и подпись, потом файл: если файл ещё
    #    не докачался, клиент увидит манифест позже, а не наоборот.
    print(f"  заливаю в {REMOTE_DIR}")
    try:
        subprocess.run(ssh_command(f"mkdir -p {REMOTE_DIR}"), check=True,
                       capture_output=True)
        for name in ("version.json", "version.json.sig", exe.name):
            result = subprocess.run(scp_command(release / name, f"{REMOTE_DIR}/{name}"),
                                    capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  не залил {name}: {result.stderr.strip()[:200]}")
                return 1
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode("utf-8", "replace")[:300]
        print("  ошибка доступа к серверу:", detail)
        return 1
    except SystemExit:
        raise

    # 4. Проверяем, что сервер отдаёт подписанное и это подпись сходится.
    print("  проверяю, что сервер отдаёт то же самое")
    try:
        from urllib.request import urlopen

        served = urlopen(f"{REMOTE_UPDATE_URL}/version.json", timeout=15).read()
        served_sig = urlopen(f"{REMOTE_UPDATE_URL}/version.json.sig", timeout=15).read()
        from procode_guard.manifest import verify_manifest

        result = verify_manifest(json.loads(served.decode("utf-8")), served_sig, public_key)
        if not result.signature_ok:
            print("  сервер отдаёт неподписанный манифест — публикация не удалась")
            return 1
    except Exception as error:
        print(f"  не смог проверить сервер: {error}")
        print("  файл залит, но проверку пройти не удалось — разбирайся руками")
        return 1

    print()
    print("  Опубликовано")
    print("  " + "-" * 52)
    print(f"  версия:  {version}")
    print(f"  адрес:   {url}")
    print(f"  манифест подписан, сервер отдаёт верный")
    print()
    print("  Клиенты получат обновление при следующем запуске.")
    print("  Страницу загрузок обновить не забудь — версия на ней должна")
    print("  совпадать с той, что здесь.")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
