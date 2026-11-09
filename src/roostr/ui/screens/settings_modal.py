from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, RadioButton, RadioSet

from roostr.i18n.catalog import SUPPORTED_LOCALES, get_messages
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

    Button {
        background: $panel;
        color: $foreground;
        border: none;
        min-width: 14;
        margin-left: 1;
    }

    Button:hover {
        background: $panel;
    }

    Button.-primary {
        background: $primary;
        color: $background;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, current_theme: str, current_locale: str, messages: Messages):
        super().__init__()
        self.initial_theme = current_theme
        self.initial_locale = current_locale
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
                    yield Label(
                        f"🎨 {self.msg.settings_theme}", id="settings-theme-title", classes="settings-section-title"
                    )
                    with RadioSet(id="theme-radios"):
                        for name in THEME_NAMES:
                            yield RadioButton(
                                name,
                                value=(name == self.current_theme),
                                id=f"theme-{name}",
                            )

                with Vertical(classes="settings-col"):
                    yield Label(
                        f"🌐 {self.msg.settings_language}", id="settings-lang-title", classes="settings-section-title"
                    )
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

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id == "theme-radios":
            if event.pressed and event.pressed.id:
                theme_name = event.pressed.id.replace("theme-", "")
                self.current_theme = theme_name
                self.app.theme = theme_name
                if hasattr(self.app, "dashboard_screen"):
                    self.app.dashboard_screen.update_theme(theme_name)
        elif event.radio_set.id == "lang-radios":
            if event.pressed and event.pressed.id:
                locale = event.pressed.id.replace("lang-", "")
                self.current_locale = locale
                self.app.locale = locale
                self.msg = get_messages(locale)
                self.app.msg = self.msg
                if hasattr(self.app, "dashboard_screen"):
                    self.app.dashboard_screen.update_messages(self.msg)
                try:
                    self.query_one("#settings-title", Label).update(f"⚙️  {self.msg.settings_title}")
                    self.query_one("#settings-theme-title", Label).update(f"🎨 {self.msg.settings_theme}")
                    self.query_one("#settings-lang-title", Label).update(f"🌐 {self.msg.settings_language}")
                    self.query_one("#btn-save", Button).label = self.msg.btn_save
                    self.query_one("#btn-cancel", Button).label = self.msg.btn_close
                except Exception:
                    pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self.action_save()
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        # Revert theme if changed during preview
        if self.app.theme != self.initial_theme:
            self.app.theme = self.initial_theme
            if hasattr(self.app, "dashboard_screen"):
                self.app.dashboard_screen.update_theme(self.initial_theme)

        # Revert locale if changed during preview
        if self.app.locale != self.initial_locale:
            self.app.locale = self.initial_locale
            self.app.msg = get_messages(self.initial_locale)
            if hasattr(self.app, "dashboard_screen"):
                self.app.dashboard_screen.update_messages(self.app.msg)

        self.dismiss(None)

    def action_save(self) -> None:
        self.dismiss({"theme": self.current_theme, "locale": self.current_locale})
