"""
Спутник — проверка целостности при запуске.
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Порядок работы при старте программы:

    1. прочитать манифест
    2. проверить его подпись вшитым публичным ключом
    3. посчитать хеши всех файлов и сверить с манифестом
    4. если хоть один пункт не сошёлся — окно и выход

Проверка идёт до главного окна, до сети и до распаковки тяжёлых ресурсов.
Пока идёт проверка, программа ничего не делает: только читает файлы.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from . import dialog
from .manifest import (
    VerifyResult,
    load_manifest,
    read_signature,
    verify_files,
    verify_manifest,
)

MANIFEST_NAME = "sputnik.manifest.json"
SIGNATURE_NAME = "sputnik.manifest.sig"

# Заглушка. Меняется на боевой домен одной строкой перед выпуском.
# Домен .test не разрешается в интернете по RFC 6761 и не зарезолвится
# случайно: если такое значение уедет в продакшен, это сразу видно.
INFO_URL = "info.test"


@dataclass
class GuardReport:
    ok: bool
    stage: str
    detail: str = ""
    checked: int = 0
    tampered: list[str] | None = None
    missing: list[str] | None = None

    def as_lines(self, limit: int = 8) -> str:
        parts = [f"этап проверки: {self.stage}"]
        if self.detail:
            parts.append(f"причина: {self.detail}")
        if self.tampered:
            parts.append("изменены файлы:")
            parts.extend(f"  {name}" for name in self.tampered[:limit])
            if len(self.tampered) > limit:
                parts.append(f"  …и ещё {len(self.tampered) - limit}")
        if self.missing:
            parts.append("отсутствуют файлы:")
            parts.extend(f"  {name}" for name in self.missing[:limit])
            if len(self.missing) > limit:
                parts.append(f"  …и ещё {len(self.missing) - limit}")
        return "\n".join(parts)


def check(
    root: Path,
    public_key,
    manifest_name: str = MANIFEST_NAME,
    signature_name: str = SIGNATURE_NAME,
) -> GuardReport:
    """Прогоняет проверку целостности. Ничего не показывает и не завершает."""
    root = Path(root)
    manifest_path = root / manifest_name
    signature_path = root / signature_name

    # 1. Манифест и подпись лежат рядом с программой. Нет их — проверять нечего.
    if not manifest_path.is_file():
        return GuardReport(False, "манифест", "файл манифеста не найден")

    if not signature_path.is_file():
        return GuardReport(False, "подпись", "файл подписи не найден")

    # 2. Подпись. Пока она не сошлась, смотреть файлы смысла нет.
    try:
        manifest = load_manifest(manifest_path)
        signature = read_signature(signature_path)
    except Exception as error:
        return GuardReport(False, "чтение", f"манифест не читается: {error}")

    signed: VerifyResult = verify_manifest(manifest, signature, public_key)
    if not signed.signature_ok:
        return GuardReport(False, "подпись", signed.signature_error or "подпись не сходится")

    # 3. Файлы.
    files: VerifyResult = verify_files(manifest, root)
    if not files.ok:
        return GuardReport(
            False,
            "файлы",
            "содержимое не совпадает с манифестом",
            checked=files.checked,
            tampered=files.tampered,
            missing=files.missing,
        )

    return GuardReport(True, "ok", checked=files.checked)


def enforce(root: Path, public_key, info_url: str = INFO_URL) -> None:
    """
    Проверяет и, если что-то не так, показывает окно и завершает программу.

    Возвращается только когда всё в порядке. Ни одного исключения наружу:
    вызывающий код не должен знать, что проверка вообще существует.
    """
    report = check(Path(root), public_key)

    if report.ok:
        return

    # Причину показываем мелким шрифтом и только в окне с деталями.
    # Обычному человеку достаточно трёх причин из окна.
    detail = dialog.DETAIL if report.stage != "файлы" else (
        "Файлы не совпадают с манифестом сборки. Переустановите программу "
        "поверх старой версии или скачайте заново."
    )

    dialog.show(
        info_url=info_url,
        reason=report.as_lines(),
        detail=detail,
        show_details=True,
    )

    # Страховка: если окно почему-то закрылось само, выходим всё равно.
    sys.exit(2)


def public_key_from_bytes(raw: bytes):
    """
    Поднимает публичный ключ из сырых байтов.

    Ключ вшивается в код, а не кладётся файлом рядом: если бы он лежал
    на диске, его можно было бы подменить вместе с манифестом.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    return Ed25519PublicKey.from_public_bytes(raw)
