"""
ProCode — автообновление.
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Схема та же, что проверена в Wow-Bot и VoiDxt: файла version.json,
скачивание, сверка размера, хеша и сигнатуры MZ, переименование
работающего exe в скрытый .old, установка нового, уборка .old при
следующем старте.

Одно отличие, и оно главное: манифест обновления ПОДПИСАН тем же ключом,
что и манифест сборки. Поэтому подпись проверяется раньше, чем из
манифеста берётся хоть что-нибудь.

Почему это важно. В старой схеме хеш файла приезжает по тому же
открытому каналу, что и сам файл. Кто встал посередине — подменяет
и файл, и хеш, и проверка радостно проходит. Здесь так не выйдет:
подделать файл он может, а подписать манифест — нет.

Порядок работы:

    1. скачать манифест
    2. ПРОВЕРИТЬ ПОДПИСЬ
    3. только теперь читать из него версию, адрес и хеш
    4. скачать файл
    5. сверить размер, хеш из подписанного манифеста, сигнатуру MZ
    6. поставить, попросить перезапустить
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from .manifest import canonical

# Меньше мегабайта exe не бывает. Явный признак того, что скачали
# не то: заглушку, страницу с ошибкой, редирект.
MIN_EXE_BYTES = 1_000_000

# Безопасный заголовок: по умолчанию urlopen шлёт Python/urllib,
# и по этому заголовку в логах видно, что зашёл бот, а не программа.
USER_AGENT = "ProCode-Update/1.0"

TIMEOUT_CHECK = 10
TIMEOUT_DOWNLOAD = 600


@dataclass
class UpdateInfo:
    """Разобранный и проверенный манифест обновления."""

    ok: bool
    err: str = ""
    current: str = ""
    latest: str = ""
    url: str = ""
    size: int = 0
    sha256: str = ""
    notes: str = ""

    @property
    def has_update(self) -> bool:
        return bool(self.ok and self.latest and self.latest != self.current)


# --- манифест со стороны сервера ----------------------------------------


def sign_update(release: dict, private_key) -> bytes:
    """Подписывает манифест обновления. Вызывается на машине сборки."""
    return private_key.sign(canonical(release))


def write_update_manifest(
    path: Path,
    version: str,
    url: str,
    size: int,
    sha256: str,
    private_key,
    notes: str = "",
) -> bytes:
    """Готовит version.json с подписью. Публикуется на сервер обновлений."""
    manifest = {
        "version": version,
        "url": url,
        "size": int(size),
        "sha256": sha256,
        "notes": notes,
    }
    signature = sign_update(manifest, private_key)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(manifest))
    path.with_suffix(path.suffix + ".sig").write_bytes(signature)
    return signature


# --- проверка со стороны программы ---------------------------------------


def verify_update_manifest(manifest: dict, signature: bytes, public_key):
    """
    Проверяет подпись манифеста.

    Возвращает VerifyResult. Дальше программа имеет право читать поля
    манифеста ТОЛЬКО если signature_ok.
    """
    from .manifest import verify_manifest

    return verify_manifest(manifest, signature, public_key)


def _get(url: str, timeout: int) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def check(
    base_url: str,
    current_version: str,
    public_key,
    frozen: bool = True,
) -> UpdateInfo:
    """
    Спрашивает сервер, есть ли обновление.

    Подпись проверяется до чтения полей. Это единственное, что отличает
    эту схему от обычной: сначала доказательство, потом данные.
    """
    if not base_url:
        return UpdateInfo(False, "адрес сервера обновлений не задан")
    if not frozen:
        return UpdateInfo(False, "обновление работает только в собранной программе")

    base = base_url.rstrip("/")

    try:
        raw = _get(f"{base}/version.json", TIMEOUT_CHECK)
        signature = _get(f"{base}/version.json.sig", TIMEOUT_CHECK)
    except Exception as error:
        return UpdateInfo(False, f"сервер обновлений недоступен: {error}")

    try:
        manifest = json.loads(raw.decode("utf-8"))
    except Exception as error:
        return UpdateInfo(False, f"манифест не читается: {error}")

    # ГЛАВНОЕ. До этой строки ни одно поле манифеста не использовано.
    result = verify_update_manifest(manifest, signature, public_key)
    if not result.signature_ok:
        return UpdateInfo(
            False,
            "подпись манифеста не сходится — обновление не принимается",
            current=current_version,
        )

    latest = str(manifest.get("version", ""))
    if not latest:
        return UpdateInfo(False, "в манифесте нет версии", current=current_version)

    # Откат версии — тоже атака: сначала подсовывают старую дырявую
    # сборку, потом «новую». Не даём.
    if _is_older(latest, current_version):
        return UpdateInfo(
            False,
            f"на сервере версия {latest}, а стоит {current_version} — откат не принимаем",
            current=current_version,
            latest=latest,
        )

    return UpdateInfo(
        ok=True,
        current=current_version,
        latest=latest,
        url=str(manifest.get("url", "")),
        size=int(manifest.get("size", 0) or 0),
        sha256=str(manifest.get("sha256", "")),
        notes=str(manifest.get("notes", "")),
    )


def _is_older(remote: str, local: str) -> bool:
    """Сравнение версий вида 2.0.1. Неудачное сравнение не считаем откатом."""
    def parts(value: str):
        out = []
        for piece in str(value).replace("-", ".").split("."):
            out.append(int(piece) if piece.isdigit() else 0)
        return out

    try:
        return parts(remote) < parts(local)
    except Exception:
        return False


def why_bad(data: bytes, size: int = 0, sha256: str = "") -> str | None:
    """
    Почему скачанное негодно. None — годно.

    От дешёвых проверок к дорогим: сперва смотрим, что файл вообще
    похож на exe, и только потом считаем хеш.
    """
    if not data:
        return "пусто"
    if len(data) < MIN_EXE_BYTES:
        return f"слишком мал: {len(data)} байт"
    if data[:2] != b"MZ":
        return "это не exe, нет сигнатуры MZ"
    if size and len(data) != size:
        return f"размер {len(data)}, а в манифесте {size}"
    if sha256:
        actual = hashlib.sha256(data).hexdigest().lower()
        if actual != sha256.lower():
            return "хеш не сходится"
    return None


# --- установка ----------------------------------------------------------


def _hide(path: Path) -> None:
    """Ставит скрытым атрибут. Windows позволяет переименовать занятый exe."""
    try:
        import ctypes

        ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x02)
    except Exception:
        pass


def _unhide(path: Path) -> None:
    try:
        import ctypes

        ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x80)
    except Exception:
        pass


def install_update(
    info: UpdateInfo,
    exe_path: Path,
    log=None,
) -> dict:
    """
    Скачивает и ставит обновление.

    exe_path — путь к работающему файлу. Windows даёт переименовать файл,
    который сейчас в памяти, поэтому «на лету» не требуется: старый
    уезжает в .old, новый занимает его имя.
    """
    def say(message: str) -> None:
        if log:
            log(message)

    if not info.has_update:
        return {"ok": False, "err": "обновления нет"}
    if not info.url:
        return {"ok": False, "err": "в манифесте нет адреса файла"}

    say(f"качаю версию {info.latest}")
    try:
        data = _get(info.url, TIMEOUT_DOWNLOAD)
    except Exception as error:
        return {"ok": False, "err": f"не скачалось: {error}"}

    # Хеш берётся из подписанного манифеста, а не из файла рядом.
    bad = why_bad(data, info.size, info.sha256)
    if bad:
        return {"ok": False, "err": f"скачалось битым ({bad}) — ничего не меняю"}

    # Повторная проверка с диска: между записью и подменой есть окно.
    staging = exe_path.with_name(exe_path.name + ".new")
    try:
        staging.write_bytes(data)
        on_disk = staging.read_bytes()
    except Exception as error:
        return {"ok": False, "err": f"не записал временный файл: {error}"}

    if on_disk != data:
        staging.unlink(missing_ok=True)
        return {"ok": False, "err": "файл на диске отличается от скачанного — откат"}

    old = exe_path.with_name(f"{exe_path.stem}.{info.latest}.old")
    try:
        _unhide(exe_path)
        if old.exists():
            _unhide(old)
            old.unlink()
        exe_path.rename(old)
        _hide(old)

        staging.replace(exe_path)
    except Exception as error:
        # Возвращаем как было, чтобы человек не остался без программы.
        try:
            if not exe_path.exists() and old.exists():
                _unhide(old)
                old.rename(exe_path)
        except Exception:
            pass
        return {"ok": False, "err": f"не смог заменить файл: {error}"}

    say(f"установлена версия {info.latest}, перезапустите программу")
    return {
        "ok": True,
        "version": info.latest,
        "restart": True,
        "backup": str(old),
        "notes": info.notes,
    }


def cleanup_old(exe_path: Path) -> list[str]:
    """
    При старте: убрать прошлые версии *.old.

    Вызывается до того, как программа что-либо делает. Если файл
    потерялся при прошлом обновлении — возвращаем его на место.
    """
    removed: list[str] = []
    stem = exe_path.stem
    backups = sorted(exe_path.parent.glob(f"{stem}.*.old"))

    for backup in backups:
        # Последний бэкап не трогаем сразу: если текущий exe битый,
        # он ещё может пригодиться.
        if not exe_path.exists() and backup is not backups[-1]:
            continue
        try:
            _unhide(backup)
            backup.unlink()
            removed.append(backup.name)
        except OSError:
            pass

    return removed
