"""App settings stored in the Setting table, with defaults and option lists."""
from flask import current_app, g

THEMES = {
    "green": {"label": "Light black & light green (default)", "ink": "#2b2e30", "ink-2": "#363a3d", "ink-3": "#4a4f53",
              "green": "#9be3ae", "green-2": "#c8f2d3", "green-3": "#e9f9ee", "green-dark": "#2f7d4a", "bg": "#f3f7f4"},
    "blue": {"label": "Navy & sky blue", "ink": "#1f2a3c", "ink-2": "#28354a", "ink-3": "#3a4a63",
             "green": "#9cc9f5", "green-2": "#cfe4fa", "green-3": "#ecf4fd", "green-dark": "#245d96", "bg": "#f2f6fa"},
    "teal": {"label": "Charcoal & teal", "ink": "#263236", "ink-2": "#2f3d42", "ink-3": "#435459",
             "green": "#8fdcd3", "green-2": "#c7eeea", "green-3": "#e8f8f6", "green-dark": "#1f7a70", "bg": "#f1f7f6"},
    "purple": {"label": "Slate & lavender", "ink": "#2c2a36", "ink-2": "#363342", "ink-3": "#4a4659",
               "green": "#c6b5f2", "green-2": "#e1d8f8", "green-3": "#f3effc", "green-dark": "#5b3fa8", "bg": "#f6f4fa"},
    "rose": {"label": "Graphite & rose", "ink": "#33292c", "ink-2": "#3e3135", "ink-3": "#544348",
             "green": "#f2b5c4", "green-2": "#f8d8e0", "green-3": "#fcf0f3", "green-dark": "#a83f5b", "bg": "#faf5f6"},
}

PAPER_SIZES = {
    "A4": ("A4 (210 × 297 mm)", "A4"),
    "A5": ("A5 (148 × 210 mm)", "A5"),
    "letter": ("US Letter", "letter"),
    "80mm": ("Thermal receipt 80 mm", "80mm auto"),
    "58mm": ("Thermal receipt 58 mm", "58mm auto"),
}
# Thermal rolls are only valid for receipts - reports/cards must stay on sheet paper.
REPORT_PAPER_SIZES = {k: v for k, v in PAPER_SIZES.items() if "auto" not in v[1]}
ORIENTATIONS = {"portrait": "Portrait", "landscape": "Landscape"}

DATE_FORMATS = {
    "%d %b %Y": "11 Oct 2026",
    "%d/%m/%Y": "11/10/2026",
    "%m/%d/%Y": "10/11/2026",
    "%Y-%m-%d": "2026-10-11",
    "%A, %d %B %Y": "Sunday, 11 October 2026",
}
TIME_FORMATS = {"%H:%M": "24-hour (14:30)", "%I:%M %p": "12-hour (02:30 PM)"}
CURRENCY_POSITIONS = {"before": "Before amount (₦1,000.00)", "after": "After amount (1,000.00 ₦)"}
DECIMALS = {"2": "2 decimal places", "0": "No decimals"}

VOICE_LANGUAGES = {
    "en-NG": "English (Nigeria)",
    "en-GB": "English (UK)",
    "en-US": "English (US)",
    "en-GH": "English (Ghana)",
    "en-KE": "English (Kenya)",
    "en-ZA": "English (South Africa)",
    "fr-FR": "French",
    "yo-NG": "Yoruba",
    "ha-NG": "Hausa",
    "ig-NG": "Igbo",
}

# Documents that get their own number prefix: key -> (label, default prefix)
DOCUMENT_TYPES = {
    "receipt": ("Payment receipt", "RCT-"),
    "lab": ("Laboratory result", "LAB-"),
    "rx": ("Prescription", "RX-"),
}


def defaults():
    cfg = current_app.config
    d = {
        "hospital_name": cfg.get("HOSPITAL_NAME", "NIA HOSPITAL"),
        "hospital_tagline": "Quality care, every visit",
        "hospital_address": "",
        "hospital_phone": "",
        "hospital_email": "",
        "patient_id_prefix": cfg.get("PATIENT_ID_PREFIX", "NIA"),
        "patient_id_format": "month_year",
        "theme": "green",
        "currency_symbol": cfg.get("CURRENCY", "₦"),
        "currency_code": "NGN",
        "currency_position": "before",
        "currency_decimals": "2",
        "date_format": "%d %b %Y",
        "time_format": "%H:%M",
        "report_paper": "A4",
        "report_orientation": "portrait",
        "receipt_paper": "A4",
        "print_margin_mm": "12",
        "auto_print_receipt": "0",
        "print_show_address": "1",
        "receipt_show_wallet": "1",
        "document_footer": "Thank you for choosing us. Get well soon.",
        "doc_number_digits": "6",
        "voice_enabled": "1",
        "voice_language": "en-NG",
        "voice_punctuation": "1",
    }
    for key, (_label, prefix) in DOCUMENT_TYPES.items():
        d[f"doc_prefix_{key}"] = prefix
    return d


def get_settings():
    """All settings (defaults overridden by saved values), cached per request."""
    if "app_settings" not in g:
        from .models import Setting

        values = defaults()
        for row in Setting.query.filter(Setting.key.in_(list(values))).all():
            if row.value is not None:
                values[row.key] = row.value
        g.app_settings = values
    return g.app_settings


def clear_cache():
    g.pop("app_settings", None)


def setting(key):
    return get_settings().get(key)


def theme_vars():
    return THEMES.get(setting("theme"), THEMES["green"])


def page_css(paper_key=None, orientation=None):
    s = get_settings()
    size = PAPER_SIZES.get(paper_key or s["report_paper"], PAPER_SIZES["A4"])[1]
    if paper_key is None and "auto" in size:
        size = PAPER_SIZES["A4"][1]  # a thermal size saved for reports would shrink every document
    orient = orientation or s["report_orientation"]
    if "auto" not in size and orient == "landscape":
        size += " landscape"
    try:
        margin = max(0, min(40, int(s["print_margin_mm"])))
    except (TypeError, ValueError):
        margin = 12
    if "auto" in size:
        margin = min(margin, 4)
    return f"@page {{ size: {size}; margin: {margin}mm; }}"


def format_money(value):
    s = get_settings()
    decimals = 0 if s["currency_decimals"] == "0" else 2
    amount = f"{float(value or 0):,.{decimals}f}"
    sym = s["currency_symbol"]
    return f"{amount} {sym}" if s["currency_position"] == "after" else f"{sym}{amount}"


def doc_number(kind, number):
    s = get_settings()
    try:
        digits = max(1, min(10, int(s["doc_number_digits"])))
    except (TypeError, ValueError):
        digits = 6
    return f"{s.get(f'doc_prefix_{kind}', '')}{int(number):0{digits}d}"
