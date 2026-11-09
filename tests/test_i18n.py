from roostr.i18n.catalog import SUPPORTED_LOCALES, get_messages
from roostr.i18n.schema import Messages


def test_i18n_all_locales_supported():
    for loc in SUPPORTED_LOCALES:
        msgs = get_messages(loc)
        assert isinstance(msgs, Messages)
        assert msgs.app_title == "roostr"
        assert len(msgs.btn_save) > 0
        assert len(msgs.btn_cancel) > 0
        assert len(msgs.status_running_today) > 0
        assert len(msgs.status_waiting) > 0
        assert len(msgs.status_paused) > 0


def test_i18n_fallback():
    # Unsupported locale falls back to 'en'
    msgs = get_messages("fr")
    assert msgs.locale == "en"
