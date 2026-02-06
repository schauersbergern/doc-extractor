"""Extraktion strukturierter Rechnungs-Properties aus OCR-Text."""

from __future__ import annotations

import re

PROPERTY_KEYS = [
    "Belegnummer",
    "Belegdatum",
    "Lieferant",
    "Lieferdatum",
    "Verknüpfung",
    "Fälligkeit",
    "Kostenstelle",
    "Tags",
    "Kategorie",
    "Betrag (Brutto)",
    "Währung",
    "Umsatzsteuer",
    "Beschreibung",
    "Positionen",
    "Gesamt Netto",
    "Gesamt Umsatzsteuer",
    "Gesamt Betrag",
]

_DATE = r"(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})"
_MONEY = r"([0-9]{1,3}(?:[.\s][0-9]{3})*(?:,[0-9]{2})|[0-9]+(?:[.,][0-9]{2}))"


def _search(pattern: str, text: str) -> str:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_invoice_properties(ocr_text: str) -> dict:
    """Heuristische Property-Extraktion für Rechnungsdaten."""
    text = ocr_text or ""
    lines = [_norm(x) for x in text.splitlines() if _norm(x)]

    props = {k: "" for k in PROPERTY_KEYS}

    props["Belegnummer"] = _search(
        r"(?:Beleg(?:nummer)?|Rechnungs(?:nummer|nr\.?)|Invoice\s*(?:No|#))\s*[:\-]?\s*([A-Z0-9\-\/_.]+)",
        text,
    )
    props["Belegdatum"] = _search(
        rf"(?:Belegdatum|Rechnungsdatum|Datum)\s*[:\-]?\s*{_DATE}",
        text,
    )
    props["Lieferdatum"] = _search(
        rf"(?:Lieferdatum|Leistungsdatum)\s*[:\-]?\s*{_DATE}",
        text,
    )
    props["Fälligkeit"] = _search(
        rf"(?:Fälligkeit|fällig(?:\s+am)?)\s*[:\-]?\s*{_DATE}",
        text,
    )
    props["Kostenstelle"] = _search(
        r"(?:Kostenstelle|Cost\s*Center)\s*[:\-]?\s*([A-Z0-9\-\/_. ]+)",
        text,
    )
    props["Kategorie"] = _search(r"(?:Kategorie|Category)\s*[:\-]?\s*([^\n]+)", text)
    props["Verknüpfung"] = _search(
        r"(?:Verknüpfung|Referenz|Reference)\s*[:\-]?\s*([A-Z0-9\-\/_. ]+)",
        text,
    )

    gross = _search(rf"(?:Brutto|Gesamtbetrag|Total)\s*[:\-]?\s*{_MONEY}", text)
    net = _search(rf"(?:Netto|Zwischensumme)\s*[:\-]?\s*{_MONEY}", text)
    vat_amount = _search(
        rf"(?:USt|MwSt|VAT|Umsatzsteuer)\s*[:\-]?\s*{_MONEY}",
        text,
    )
    vat_rate = _search(r"(?:USt|MwSt|VAT)[^%\n]{0,20}([0-9]{1,2}[.,]?[0-9]{0,2}\s*%)", text)

    props["Betrag (Brutto)"] = gross
    props["Gesamt Betrag"] = gross
    props["Gesamt Netto"] = net
    props["Gesamt Umsatzsteuer"] = vat_amount
    props["Umsatzsteuer"] = vat_rate or vat_amount

    currency = _search(r"(EUR|€|USD|CHF|GBP)", text)
    props["Währung"] = "EUR" if currency == "€" else currency

    # Lieferant: erster sinnvoller Header-Block
    if lines:
        props["Lieferant"] = lines[0][:160]

    # Beschreibung: erste Zeilen ohne Summenbereich
    desc_lines = []
    for line in lines[:15]:
        if re.search(r"(Brutto|Netto|MwSt|USt|VAT|Gesamt)", line, re.IGNORECASE):
            continue
        desc_lines.append(line)
    props["Beschreibung"] = " | ".join(desc_lines[:4])

    # Positionen: Zeilen mit Preis-/Mengenmuster
    pos = []
    pos_pattern = re.compile(
        rf"(?:\b[0-9]+(?:[.,][0-9]+)?\b.*{_MONEY}|{_MONEY}.*\b[0-9]+(?:[.,][0-9]+)?\b)",
        re.IGNORECASE,
    )
    for line in lines:
        if pos_pattern.search(line):
            pos.append(line)
        if len(pos) >= 10:
            break
    props["Positionen"] = pos

    return props


def normalize_value(value) -> str:
    if isinstance(value, list):
        return " | ".join(_norm(str(v)) for v in value if _norm(str(v)))
    return _norm("" if value is None else str(value))
