from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, RadioButton, RadioSet

from roostr.i18n.catalog import SUPPORTED_LOCALES
from roostr.i18n.schema import Messages
from roostr.ui.themes import THEME_NAMES


class SettingsModal(ModalScreen[dict | None]):
    DEFAULT_CSS = """
    SettingsModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.65);
    }

    #settings-dialog {
        width: 60;
        height: auto;
        max-height: 85%;
        background: $background;
        border: solid $panel;
        padding: 1 2;
    }

    #settings-title {
        text-style: bold;
        color: $foreground;
        padding-bottom: 1;
        border-bottom: solid $panel;
        margin-bottom: 1;
        width: 100%;
        text-align: center;
    }

    .settings-body {
        height: auto;
        margin-bottom: 1;
    }

    .settings-col {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }

    .settings-section-title {
        color: $secondary;
        text-style: bold;
        margin-bottom: 1;
    }

    RadioSet {
        background: transparent;
        border: none;
        padding: 0;
    }

    RadioButton {
        background: transparent;
        padding: 0;
        height: 1;
        margin-bottom: 0;
    }

    .settings-actions {
        height: 3;
        align: right middle;
        border-top: solid $panel;
        padding-top: 1;
    }

    .settings-actions Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, current_theme: str, current_locale: str, messages: Messages):
        super().__init__()
        self.current_theme = current_theme
        self.current_locale = current_locale
        self.msg = messages

    def compose(self) -> ComposeResult:
        locale_labels = {
            "en": "English",
            "pt_br": "Português",
            "es": "Español",
        }

        with Vertical(id="settings-dialog"):
            yield Label(f"⚙️  {self.msg.settings_title}", id="settings-title")

            with Horizontal(classes="settings-body"):
                with Vertical(classes="settings-col"):
                    yield Label(f"🎨 {self.msg.settings_theme}", classes="settings-section-title")
                    with RadioSet(id="theme-radios"):
                        for name in THEME_NAMES:
                            yield RadioButton(
                                name,
                                value=(name == self.current_theme),
                                id=f"theme-{name}",
                            )

                with Vertical(classes="settings-col"):
                    yield Label(f"🌐 {self.msg.settings_language}", classes="settings-section-title")
                    with RadioSet(id="lang-radios"):
                        for loc in SUPPORTED_LOCALES:
                            yield RadioButton(
                                locale_labels.get(loc, loc.upper()),
                                value=(loc == self.current_locale),
                                id=f"lang-{loc}",
                            )

            with Horizontal(classes="settings-actions"):
                yield Button(self.msg.btn_save, variant="primary", id="btn-save")
                yield Button(self.msg.btn_close, id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self.action_save()
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        # Determine selected theme
        theme_radios = self.query_one("#theme-radios", RadioSet)
        selected_theme = self.current_theme
        if theme_radios.pressed_button and theme_radios.pressed_button.id:
            selected_theme = theme_radios.pressed_button.id.replace("theme-", "")

        # Determine selected locale
        lang_radios = self.query_one("#lang-radios", RadioSet)
        selected_locale = self.current_locale
        if lang_radios.pressed_button and lang_radios.pressed_button.id:
            selected_locale = lang_radios.pressed_button.id.replace("lang-", "")

        self.dismiss({"theme": selected_theme, "locale": selected_locale})
