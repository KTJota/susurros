"""The translation table is complete and consistent, and numbers and dates follow the language."""
import ast
import string
from datetime import date
from pathlib import Path

import pytest

from susurros import config, hotkey, i18n, sounds

SRC = Path(i18n.__file__).parent
# Source strings that read the same in Spanish and need no entry.
SAME_IN_BOTH: set[str] = set()


def tr_literals() -> dict[str, str]:
    """Every string literal passed as first argument to `tr(...)` in the package -> where it is."""
    found: dict[str, str] = {}
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            first = node.args[0]
            if name == "tr" and isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.setdefault(first.value, f"{path.name}:{node.lineno}")
    return found


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


@pytest.fixture(autouse=True)
def english_afterwards():
    yield
    i18n.set_language("en")


def test_every_translated_literal_has_a_spanish_entry():
    literals = tr_literals()
    assert len(literals) > 80                      # the scan really finds the interface
    missing = {text: where for text, where in literals.items()
               if text not in i18n.ES and text not in SAME_IN_BOTH}
    assert not missing


def test_strings_from_other_modules_have_a_spanish_entry():
    """Option lists and key names are English source strings translated when displayed."""
    names = [name for _, name in config.LANGUAGES + config.HUD_POSITIONS + sounds.SETS]
    names.append(dict(config.UI_LANGUAGES)[""])
    names += [name for name in hotkey._KEY_NAMES.values() if name not in ("Ctrl", "Alt", "Insert", "Tab")]
    assert [name for name in names if name not in i18n.ES] == []


def test_spanish_keeps_the_placeholders_of_the_source():
    wrong = {key: value for key, value in i18n.ES.items() if placeholders(key) != placeholders(value)}
    assert not wrong


def test_tr_translates_and_fills_placeholders():
    assert i18n.tr("Hold {key} to dictate. Press it twice in a row to dictate hands-free.", key="F8") \
        .startswith("Hold F8 to dictate.")
    i18n.set_language("es")
    assert i18n.language() == "es"
    assert i18n.tr("History") == "Historial"
    assert i18n.tr("Ready to dictate · {device}", device="GPU") == "Listo para dictar · GPU"
    assert i18n.tr("Not in the table") == "Not in the table"


def test_numbers_follow_the_interface_language():
    assert (i18n.fmt_int(12345), i18n.fmt_decimal(3.25), i18n.fmt_int(999)) == ("12,345", "3.2", "999")
    i18n.set_language("es")
    assert (i18n.fmt_int(12345), i18n.fmt_decimal(3.25), i18n.fmt_int(999)) == ("12.345", "3,2", "999")


def test_day_labels_in_both_languages():
    today = date(2026, 3, 10)
    days = (today, date(2026, 3, 9), date(2026, 1, 5), date(2025, 12, 31))
    assert [i18n.day_label(day, today) for day in days] == \
        ["TODAY", "YESTERDAY", "JANUARY 5", "DECEMBER 31, 2025"]
    i18n.set_language("es")
    assert [i18n.day_label(day, today) for day in days] == \
        ["HOY", "AYER", "5 DE ENERO", "31 DE DICIEMBRE DE 2025"]


def test_resolve_keeps_an_explicit_choice():
    assert i18n.resolve("es") == "es" and i18n.resolve("en") == "en"
    assert i18n.resolve("") in ("es", "en")
