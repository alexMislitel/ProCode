"""
ProCode — окно «это не оригинальный файл».
© 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode.

Окно показывается ДО главного окна приложения, до сети и до распаковки
тяжёлых ресурсов. Если проверка не пройдена — программа не стартует.

Важная деталь: причин три, а не одна. Самая частая жалоба на такие
программы — «антивирус ругается», и это ложное срабатывание. Человек лечит
файл, антивирус его перепаковывает, проверка падает. Если написать только
«файл изменён», человек решит, что его взломали. Поэтому причин три, и
это правда.
"""

from __future__ import annotations

import sys
import webbrowser

TITLE = "Это не оригинальный файл"

BODY = (
    "Проверка не пройдена — программа не запустится.\n\n"
    "Три возможные причины:\n\n"
    "  •  Файл изменён после сборки. Скачайте заново\n"
    "  •  Антивирус поправил файл при распаковке\n"
    "  •  Установка не завершилась"
)

DETAIL = (
    "Подпись сборки сходится — файл выпущен под этой подписью.\n"
    "Проверка не прошла по другой причине. Переустановите поверх старой\n"
    "версии или скачайте заново."
)


def show(info_url: str, reason: str = "", detail: str = "", show_details: bool = False):
    """
    Показывает окно. tkinter выбран потому, что входит в стандартную
    поставку Windows: сторонние библиотеки в момент проверки целостности
    недоступны, а тянуть графическую библиотеку нельзя.
    """
    try:
        import tkinter
        from tkinter import font
    except ImportError:
        print(TITLE, file=sys.stderr)
        print(BODY, file=sys.stderr)
        return _console_fallback(info_url, reason, detail, show_details)

    root = tkinter.Tk()
    root.title(TITLE)
    root.configure(bg="#1a1d23")
    root.resizable(False, False)

    wrap = tkinter.Frame(root, bg="#1a1d23", padx=30, pady=24)
    wrap.pack(fill="both", expand=True)

    tkinter.Label(
        wrap, text=TITLE, bg="#1a1d23", fg="#f87171",
        font=("Segoe UI", 17, "bold"),
    ).pack(anchor="w", pady=(0, 14))

    tkinter.Label(
        wrap, text=BODY, bg="#1a1d23", fg="#e8ecf1", justify="left",
        font=("Segoe UI", 10), wraplength=430, anchor="w",
    ).pack(anchor="w")

    tkinter.Frame(wrap, bg="#242a33", height=1).pack(fill="x", pady=16)

    url_row = tkinter.Frame(wrap, bg="#1a1d23")
    url_row.pack(anchor="w")
    tkinter.Label(
        url_row, text="Оригинал:  ", bg="#1a1d23", fg="#8b95a3",
        font=("Segoe UI", 10),
    ).pack(side="left")
    tkinter.Label(
        url_row, text=info_url, bg="#1a1d23", fg="#5eead4",
        font=("Consolas", 10, "bold"),
    ).pack(side="left")

    if show_details and detail:
        tkinter.Label(
            wrap, text=detail, bg="#1a1d23", fg="#8b95a3", justify="left",
            font=("Consolas", 8), wraplength=430, anchor="w",
        ).pack(anchor="w", pady=(16, 0))

    if reason:
        tkinter.Label(
            wrap, text=reason, bg="#1a1d23", fg="#5f6977", justify="left",
            font=("Consolas", 7), wraplength=430, anchor="w",
        ).pack(anchor="w", pady=(8, 0))

    buttons = tkinter.Frame(wrap, bg="#1a1d23")
    buttons.pack(anchor="e", pady=(24, 0))

    def quit_app() -> None:
        root.destroy()
        sys.exit(2)

    def open_site() -> None:
        # Адрес написан текстом рядом, а не только в кнопке: если открытие
        # не сработает, человек всё равно видит, куда идти.
        try:
            webbrowser.open(info_url)
        except Exception:
            pass
        quit_app()

    tkinter.Button(
        buttons, text="Закрыть", command=quit_app,
        bg="#242a33", fg="#e8ecf1", activebackground="#2f3641",
        activeforeground="#ffffff", relief="flat", bd=0,
        font=("Segoe UI", 9), padx=18, pady=7, cursor="hand2",
    ).pack(side="left", padx=(0, 8))

    tkinter.Button(
        buttons, text="Открыть сайт", command=open_site,
        bg="#5eead4", fg="#06231f", activebackground="#2dd4bf",
        activeforeground="#06231f", relief="flat", bd=0,
        font=("Segoe UI", 9, "bold"), padx=18, pady=7, cursor="hand2",
    ).pack(side="left")

    root.protocol("WM_DELETE_WINDOW", quit_app)
    root.attributes("-topmost", True)
    root.update_idletasks()
    root.deiconify()
    root.focus_force()

    # Держим окно поверх остальных, пока пользователь его не закроет.
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass

    sys.exit(2)


def _console_fallback(info_url: str, reason: str, detail: str, show_details: bool) -> None:
    """Запасной путь, если tkinter недоступен. Плохо, но лучше, чем молчание."""
    print("\n" + "=" * 58, file=sys.stderr)
    print(TITLE, file=sys.stderr)
    print("=" * 58, file=sys.stderr)
    print(BODY, file=sys.stderr)
    print("\nОригинал: " + info_url, file=sys.stderr)
    if show_details and detail:
        print("\n" + detail, file=sys.stderr)
    if reason:
        print("\n" + reason, file=sys.stderr)
    print("=" * 58, file=sys.stderr)
