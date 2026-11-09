from roostr.i18n.locales.en import EN_MESSAGES
from roostr.i18n.locales.es import ES_MESSAGES
from roostr.i18n.locales.pt_br import PT_BR_MESSAGES
from roostr.i18n.schema import Messages

SUPPORTED_LOCALES = ("en", "pt_br", "es")

_CATALOG = {
    "en": EN_MESSAGES,
    "pt_br": PT_BR_MESSAGES,
    "es": ES_MESSAGES,
}


def get_messages(locale: str = "en") -> Messages:
    normalized = locale.lower().replace("-", "_")
    return _CATALOG.get(normalized, EN_MESSAGES)
