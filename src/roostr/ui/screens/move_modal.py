from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView

from roostr.domain.models import Job
from roostr.i18n.catalog import get_messages
from roostr.i18n.schema import Messages


class DestinationItem(ListItem):
    def __init__(self, label: str, target_folder: str | None, is_new_action: bool = False):
        super().__init__()
        self.label_text = label
        self.target_folder = target_folder
        self.is_new_action = is_new_action

    def compose(self) -> ComposeResult:
        yield Label(self.label_text)


class MoveJobModal(ModalScreen[str | None]):
    DEFAULT_CSS = """
    MoveJobModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #move-container {
        width: 64;
        max-height: 80%;
        background: $background;
        border: solid $primary;
        padding: 1 2;
        color: $foreground;
    }

    .move-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        text-align: center;
    }

    .field-label {
        color: $secondary;
        margin-top: 1;
    }

    #dest-list {
        height: auto;
        max-height: 12;
        background: $panel;
        border: solid $panel;
        margin-top: 1;
        margin-bottom: 1;
    }

    #dest-list > DestinationItem {
        padding: 0 1;
        height: 1;
        background: transparent;
        color: $foreground;
    }

    #dest-list > DestinationItem:hover {
        background: $panel;
    }

    #dest-list > DestinationItem.-highlight,
    #dest-list > DestinationItem.-selected,
    #dest-list:focus > DestinationItem.-highlight {
        background: $primary;
        color: $background;
        text-style: bold;
    }

    #new-folder-box {
        margin-top: 1;
        height: auto;
    }

    #move-error {
        color: $error;
        text-style: bold;
        margin-top: 1;
        height: 1;
    }

    .button-row {
        margin-top: 1;
        align: right middle;
        height: 3;
    }

    Button {
        background: $panel;
        color: $foreground;
        border: none;
        min-width: 12;
        margin-left: 2;
    }

    Button.-primary {
        background: $primary;
        color: $background;
        text-style: bold;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, job: Job, folders: list[str], messages: Messages | None = None):
        super().__init__()
        self.job = job
        self.folders = sorted(list(set(folders)))
        self.msg = messages or get_messages("en")
        self.is_creating_new = False

    def compose(self) -> ComposeResult:
        with Vertical(id="move-container"):
            title = f"{self.msg.modal_title_move}: {self.job.name}"
            yield Label(title, classes="move-title")

            yield Label("Select target folder:", classes="field-label")

            with ListView(id="dest-list"):
                # Option 0: Root (No Folder)
                yield DestinationItem(self.msg.lbl_no_folder_root, target_folder=None)

                # Options 1..N: Existing Folders
                for f in self.folders:
                    yield DestinationItem(f"● {f}", target_folder=f)

                # Option N+1: Create New Folder
                yield DestinationItem(self.msg.lbl_create_new_folder_option, target_folder=None, is_new_action=True)

            with Vertical(id="new-folder-box"):
                yield Label("New folder name (max 2 levels, e.g. Work or Work/Reports):", classes="field-label")
                yield Input(placeholder="e.g. Work or Work/Reports", id="inp-new-folder")

            yield Label("", id="move-error")

            with Horizontal(classes="button-row"):
                yield Button(self.msg.btn_cancel, variant="default", id="btn-cancel")
                yield Button(self.msg.btn_save, variant="primary", id="btn-move")

    def on_mount(self) -> None:
        self.query_one("#new-folder-box").display = False
        dest_list = self.query_one("#dest-list", ListView)
        dest_list.focus()

        # Pre-highlight current folder if any
        if self.job.folder and self.job.folder in self.folders:
            dest_list.index = 1 + self.folders.index(self.job.folder)
        else:
            dest_list.index = 0

    @on(ListView.Selected, "#dest-list")
    def on_dest_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, DestinationItem):
            if event.item.is_new_action:
                self._show_new_folder_input()
            else:
                self.dismiss(event.item.target_folder or "")

    def _show_new_folder_input(self) -> None:
        self.is_creating_new = True
        self.query_one("#dest-list").display = False
        box = self.query_one("#new-folder-box")
        box.display = True
        inp = self.query_one("#inp-new-folder", Input)
        inp.focus()

    @on(Input.Submitted, "#inp-new-folder")
    def on_input_submitted(self) -> None:
        self._submit_new_folder()

    @on(Button.Pressed, "#btn-move")
    def on_btn_move(self) -> None:
        if self.is_creating_new:
            self._submit_new_folder()
        else:
            dest_list = self.query_one("#dest-list", ListView)
            idx = dest_list.index
            if idx is not None and 0 <= idx < len(dest_list.children):
                item = dest_list.children[idx]
                if isinstance(item, DestinationItem):
                    if item.is_new_action:
                        self._show_new_folder_input()
                    else:
                        self.dismiss(item.target_folder or "")

    def _submit_new_folder(self) -> None:
        val = self.query_one("#inp-new-folder", Input).value.strip()
        cleaned = "/".join([p.strip() for p in val.strip("/").split("/") if p.strip()])
        if not cleaned:
            self.query_one("#move-error", Label).update("Folder name cannot be empty.")
            return

        parts = cleaned.split("/")
        if len(parts) > 2:
            self.query_one("#move-error", Label).update(
                "Hierarchy cannot exceed 2 levels (Folder or Folder/Subfolder)."
            )
            return

        self.dismiss(cleaned)

    @on(Button.Pressed, "#btn-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)
