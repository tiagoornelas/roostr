import dataclasses

from roostr.i18n.catalog import SUPPORTED_LOCALES, get_messages
from roostr.i18n.schema import Messages


def test_i18n_all_locales_supported():
    fields = dataclasses.fields(Messages)
    for loc in SUPPORTED_LOCALES:
        msgs = get_messages(loc)
        assert isinstance(msgs, Messages)
        assert msgs.app_title == "roostr"
        for field in fields:
            val = getattr(msgs, field.name)
            assert val is not None, f"Field '{field.name}' is None in locale '{loc}'"
            if isinstance(val, str):
                assert len(val.strip()) > 0, f"Field '{field.name}' is empty in locale '{loc}'"
            elif isinstance(val, tuple):
                assert len(val) > 0, f"Tuple field '{field.name}' is empty in locale '{loc}'"


def test_i18n_fallback():
    # Unsupported locale falls back to 'en'
    msgs = get_messages("fr")
    assert msgs.locale == "en"
