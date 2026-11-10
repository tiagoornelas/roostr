from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from roostr.i18n.catalog import get_messages
from roostr.i18n.schema import Messages


class NewFolderModal(ModalScreen[str | None]):
    DEFAULT_CSS = """
    NewFolderModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #folder-container {
        width: 60;
        background: $background;
        border: solid $primary;
        padding: 1 2;
        color: $foreground;
    }

    .modal-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        text-align: center;
    }

    .field-label {
        color: $secondary;
        margin-top: 1;
    }

    #error-label {
        color: $error;
        text-style: bold;
        margin-top: 1;
        height: 1;
    }

    .button-row {
        margin-top: 1;
        align: right middle;
        height: auto;
    }

    Button {
        background: $panel;
        color: $foreground;
        border: none !important;
        height: 1;
        min-width: 12;
        margin-left: 2;
        padding: 0 1;
    }

    Button:hover {
        background: $panel;
    }

    Button.-primary, Button.-style-default.-primary {
        background: $primary;
        color: $background !important;
        text-style: bold;
        border: none !important;
        height: 1;
    }

    Button#btn-cancel, Button.-style-default#btn-cancel {
        background: $panel;
        color: $foreground !important;
        border: none !important;
        height: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, messages: Messages | None = None, prefill: str = ""):
        super().__init__()
        self.msg = messages or get_messages("en")
        self.prefill = prefill

    def compose(self) -> ComposeResult:
        with Vertical(id="folder-container"):
            yield Label(self.msg.modal_title_new_folder, classes="modal-title")
            yield Label(self.msg.lbl_folder_name_rules, classes="field-label")
            yield Input(placeholder=self.msg.placeholder_folder_name, id="inp-folder-name", value=self.prefill)
            yield Label("", id="error-label")

            with Horizontal(classes="button-row"):
                yield Button(self.msg.btn_cancel, variant="default", id="btn-cancel")
                yield Button(self.msg.btn_save, variant="primary", id="btn-create")

    def on_mount(self) -> None:
        inp = self.query_one("#inp-folder-name", Input)
        inp.focus()
        if self.prefill:
            inp.cursor_position = len(self.prefill)

    @on(Input.Submitted, "#inp-folder-name")
    def on_input_submitted(self) -> None:
        self._submit()

    @on(Button.Pressed, "#btn-create")
    def on_btn_create(self) -> None:
        self._submit()

    def _submit(self) -> None:
        val = self.query_one("#inp-folder-name", Input).value.strip()
        cleaned = "/".join([p.strip() for p in val.strip("/").split("/") if p.strip()])
        if not cleaned:
            self.query_one("#error-label", Label).update(self.msg.err_folder_empty)
            return

        parts = cleaned.split("/")
        if len(parts) > 2:
            self.query_one("#error-label", Label).update(self.msg.err_folder_hierarchy)
            return

        self.dismiss(cleaned)

    @on(Button.Pressed, "#btn-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)
