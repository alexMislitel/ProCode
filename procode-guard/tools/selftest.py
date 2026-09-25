"""
ProCode — проверка, что защита работает.
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Запуск:
    python tools/selftest.py

Проверяет семь сценариев на временных файлах, ничего не трогает настоящую
сборку. Смысл один: убедиться, что подделку поймать можно, а честную
сборку не отклонить.

Что именно проверяется:
    1. честная сборка проходит
    2. изменённый файл ловится
    3. пропавший файл ловится
    4. подпись чужого ключа не принимается
    5. правка манифеста ломает подпись
    6. путь, ведущий наружу, отбрасывается
    7. проверка не даёт пройти подменой ключа
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from procode_guard import manifest as M  # noqa: E402
from procode_guard.guard import GuardReport, check  # noqa: E402

RESULTS: list[tuple[bool, str, str]] = []


def record(ok: bool, name: str, note: str = "") -> None:
    RESULTS.append((ok, name, note))
    mark = "ПРОШЁЛ" if ok else "НЕ ПРОШЁЛ"
    print(f"  [{mark:^9}] {name}")
    if note:
        print(f"               {note}")


def make_app(folder: Path) -> None:
    """Папка, похожая на собранную программу."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "app.exe").write_bytes(b"MZ\x90\x00" + b"\x00" * 500)
    (folder / "data").mkdir()
    (folder / "data" / "ru.editorial.json").write_text('{"слова":["ну","типа"]}', encoding="utf-8")
    (folder / "readme.txt").write_text("ProCode, 2026", encoding="utf-8")


def sign_into(root: Path, private) -> tuple[Path, Path]:
    files = [p for p in root.rglob("*") if p.is_file()]
    manifest = M.build_manifest(files, root)
    signature = M.sign_manifest(manifest, private)

    manifest_path = root / "procode.manifest.json"
    signature_path = root / "procode.manifest.sig"
    manifest_path.write_bytes(M.canonical(manifest))
    signature_path.write_bytes(signature)
    return manifest_path, signature_path


def main() -> int:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    attacker = Ed25519PrivateKey.generate()

    work = Path(tempfile.mkdtemp(prefix="procode-selftest-"))
    try:
        # 1. Честная сборка проходит.
        print("\n1. Честная сборка")
        good = work / "good"
        make_app(good)
        sign_into(good, private)
        report = check(good, public)
        record(
            report.ok and report.checked > 0,
            "подписанная сборка принимается",
            f"проверено файлов: {report.checked}, этап: {report.stage}",
        )

        # 2. Изменённый файл ловится.
        print("\n2. Изменённый файл")
        tampered = work / "tampered"
        shutil.copytree(good, tampered)
        target = tampered / "readme.txt"
        target.write_text("ProCode, 2026 — с вредоносной строкой", encoding="utf-8")
        report = check(tampered, public)
        record(
            not report.ok and bool(report.tampered),
            "изменённый файл отклонён",
            f"этап: {report.stage}, найдено: {report.tampered}",
        )

        # 3. Пропавший файл ловится.
        print("\n3. Пропавший файл")
        gone = work / "gone"
        shutil.copytree(good, gone)
        (gone / "readme.txt").unlink()
        report = check(gone, public)
        record(
            not report.ok and bool(report.missing),
            "отсутствующий файл отклонён",
            f"этап: {report.stage}, не хватает: {report.missing}",
        )

        # 4. Подпись чужого ключа.
        print("\n4. Чужая подпись")
        forged = work / "forged"
        shutil.copytree(good, forged)
        # Содержимое честное, но подписано чужим ключом.
        files = [p for p in forged.rglob("*") if p.is_file() and p.name not in M.__dict__.get("_skip", set()) and "manifest" not in p.name]
        manifest = M.build_manifest(files, forged)
        signature = M.sign_manifest(manifest, attacker)
        (forged / "procode.manifest.json").write_bytes(M.canonical(manifest))
        (forged / "procode.manifest.sig").write_bytes(signature)
        report = check(forged, public)
        record(
            not report.ok and report.stage == "подпись",
            "подпись чужого ключа не принята",
            f"этап: {report.stage}, {report.detail}",
        )

        # 5. Правка манифеста ломает подпись.
        print("\n5. Правка манифеста")
        edited = work / "edited"
        shutil.copytree(good, edited)
        data = json.loads((edited / "procode.manifest.json").read_text(encoding="utf-8"))
        data["files"]["readme.txt"] = "0" * 64  # подставили чужой хеш
        (edited / "procode.manifest.json").write_bytes(M.canonical(data))
        report = check(edited, public)
        record(
            not report.ok and report.stage == "подпись",
            "правка манифеста ломает подпись",
            f"этап: {report.stage}",
        )

        # 6. Путь наружу отбрасывается.
        print("\n6. Путь за пределы папки")
        escaped = work / "escaped"
        make_app(escaped)
        outside = work / "секрет.txt"
        outside.write_text("нельзя", encoding="utf-8")
        manifest = M.build_manifest([outside], escaped)  # файл вне корня
        record(
            len(manifest["files"]) == 0,
            "файл вне корня в манифест не попал",
            f"записей: {len(manifest['files'])}",
        )

        # 7. Проверка манифеста на подмену целиком.
        print("\n7. Подмена манифеста и подписи парой")
        swapped = work / "swapped"
        make_app(swapped)
        sign_into(swapped, attacker)
        report = check(swapped, public)
        record(
            not report.ok and report.stage == "подпись",
            "чужая пара манифест+подпись не принята",
            f"этап: {report.stage}",
        )

    finally:
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for ok, _, _ in RESULTS if ok)
    total = len(RESULTS)

    print("\n" + "=" * 58)
    print(f"  Пройдено: {passed} из {total}")
    print("=" * 58)

    if passed != total:
        print("\n  Есть провалы. Защиту в релиз не выпускать.")
        return 1

    print("\n  Защита работает: подделка ловится, честная сборка проходит.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
