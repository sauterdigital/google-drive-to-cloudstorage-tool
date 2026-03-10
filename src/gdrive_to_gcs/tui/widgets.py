from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, OptionList, ProgressBar, Static, Tree, Input
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from gdrive_to_gcs.drive import FOLDER_MIME, list_files
from gdrive_to_gcs.gcs import list_buckets
from gdrive_to_gcs.tui.screens import ErrorScreen


class DriveTreePanel(Vertical):
    """Panel showing Google Drive folder tree with file selection."""

    def __init__(self) -> None:
        super().__init__()
        self._loaded: set[str] = set()
        self._selected: dict[str, dict] = {}  # file_id -> file_meta

    def compose(self) -> ComposeResult:
        yield Label("Google Drive", classes="panel-title")
        tree: Tree[dict] = Tree("My Drive", id="drive-tree")
        tree.root.data = {"id": "root", "mimeType": FOLDER_MIME, "name": "My Drive"}
        tree.root.expand()
        yield tree

    def on_mount(self) -> None:
        self._load_root()

    @work(thread=True, group="drive")
    def _load_root(self) -> None:
        service = self.app.drive_service
        if not service:
            return
        try:
            files = list_files(service, folder_id="root")
        except Exception as exc:
            self.app.call_from_thread(self.app.push_screen, ErrorScreen(f"Failed to load Drive: {exc}"))
            return
        self.app.call_from_thread(self._populate_node, self.tree.root, files)

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        if node.data is None:
            return
        folder_id = node.data.get("id")
        if not folder_id or folder_id in self._loaded:
            return
        self._loaded.add(folder_id)
        self._load_children(node, folder_id)

    @work(thread=True, group="drive")
    def _load_children(self, node: TreeNode, folder_id: str) -> None:
        service = self.app.drive_service
        if not service:
            return
        try:
            files = list_files(service, folder_id=folder_id)
        except Exception as exc:
            self.app.call_from_thread(self.app.push_screen, ErrorScreen(f"Failed to load folder: {exc}"))
            return
        self.app.call_from_thread(self._populate_node, node, files)

    def _populate_node(self, parent: TreeNode, files: list[dict]) -> None:
        # Sort: folders first, then files
        folders = [f for f in files if f["mimeType"] == FOLDER_MIME]
        regular = [f for f in files if f["mimeType"] != FOLDER_MIME]

        for folder in sorted(folders, key=lambda f: f["name"]):
            child = parent.add(f"\U0001f4c1 {folder['name']}", data=folder, allow_expand=True)
            child.data = folder

        for file in sorted(regular, key=lambda f: f["name"]):
            label = f"  {file['name']}"
            if file["id"] in self._selected:
                label = f"\u2713 {file['name']}"
            child = parent.add_leaf(label, data=file)
            child.data = file

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        if node.data is None:
            return

        file_id = node.data["id"]
        is_folder = node.data.get("mimeType") == FOLDER_MIME

        if file_id in self._selected:
            del self._selected[file_id]
            icon = "\U0001f4c1 " if is_folder else "  "
            node.set_label(f"{icon}{node.data['name']}")
        else:
            self._selected[file_id] = node.data
            icon = "\u2713\U0001f4c1 " if is_folder else "\u2713 "
            node.set_label(f"{icon}{node.data['name']}")

    def get_selected_files(self) -> list[dict]:
        return list(self._selected.values())

    def select_all_visible(self) -> None:
        """Select all loaded leaf nodes."""
        self._walk_and_select(self.tree.root, select=True)

    def deselect_all(self) -> None:
        """Deselect all files."""
        self._selected.clear()
        self._walk_and_select(self.tree.root, select=False)

    def _walk_and_select(self, node: TreeNode, select: bool) -> None:
        if node.data and node.data.get("id"):
            is_folder = node.data.get("mimeType") == FOLDER_MIME
            file_id = node.data["id"]
            if select:
                self._selected[file_id] = node.data
                icon = "\u2713\U0001f4c1 " if is_folder else "\u2713 "
                node.set_label(f"{icon}{node.data['name']}")
            else:
                self._selected.pop(file_id, None)
                icon = "\U0001f4c1 " if is_folder else "  "
                node.set_label(f"{icon}{node.data['name']}")
        for child in node.children:
            self._walk_and_select(child, select)

    @work(thread=True, group="drive")
    def refresh_tree(self) -> None:
        """Reload the root folder."""
        self._loaded.clear()
        service = self.app.drive_service
        if not service:
            return
        files = list_files(service, folder_id="root")

        def _rebuild(files):
            self.tree.root.remove_children()
            self._populate_node(self.tree.root, files)

        self.app.call_from_thread(_rebuild, files)

    @property
    def tree(self) -> Tree:
        return self.query_one("#drive-tree", Tree)


class BucketListPanel(Vertical):
    """Panel showing GCS buckets with destination prefix input."""

    def __init__(self) -> None:
        super().__init__()
        self.selected_bucket: str | None = None

    def compose(self) -> ComposeResult:
        yield Label("GCS Buckets", classes="panel-title")
        yield OptionList(id="bucket-list")
        yield Input(placeholder="Destination prefix (optional)", id="prefix-input", classes="prefix-input")

    def on_mount(self) -> None:
        self._load_buckets()

    @work(thread=True, group="gcs")
    def _load_buckets(self) -> None:
        client = self.app.gcs_client
        if not client:
            return
        try:
            buckets = list_buckets(client)
        except Exception as exc:
            self.app.call_from_thread(
                self.app.push_screen,
                ErrorScreen(f"Failed to load buckets: {exc}\n\nTry: gdrive-to-gcs --project YOUR_PROJECT_ID"),
            )
            return
        self.app.call_from_thread(self._populate_buckets, buckets)

    def _populate_buckets(self, buckets: list[str]) -> None:
        option_list = self.query_one("#bucket-list", OptionList)
        option_list.clear_options()
        for name in sorted(buckets):
            option_list.add_option(Option(f"\U0001faa3 {name}", id=name))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option:
            self.selected_bucket = event.option.id

    def get_prefix(self) -> str:
        return self.query_one("#prefix-input", Input).value.strip()

    @work(thread=True, group="gcs")
    def refresh_buckets(self) -> None:
        client = self.app.gcs_client
        if not client:
            return
        try:
            buckets = list_buckets(client)
        except Exception as exc:
            self.app.call_from_thread(self.app.push_screen, ErrorScreen(f"Failed to refresh buckets: {exc}"))
            return
        self.app.call_from_thread(self._populate_buckets, buckets)


class TransferProgressPanel(Horizontal):
    """Panel showing transfer progress at the bottom of the screen."""

    def compose(self) -> ComposeResult:
        yield Label("Ready", id="transfer-status", classes="status-label")
        yield ProgressBar(id="transfer-bar", total=100, show_eta=True)
        yield Label("", id="transfer-bytes", classes="bytes-label")

    def show_progress(self, current: int, total: int, filename: str) -> None:
        self.add_class("active")
        self.query_one("#transfer-status", Label).update(
            f"Transferring {current}/{total}: {filename}"
        )
        bar = self.query_one("#transfer-bar", ProgressBar)
        bar.update(total=total, progress=current)

    def set_status(self, text: str) -> None:
        self.query_one("#transfer-status", Label).update(text)

    def hide(self) -> None:
        self.remove_class("active")
        self.query_one("#transfer-status", Label).update("Ready")
        self.query_one("#transfer-bar", ProgressBar).update(total=100, progress=0)
        self.query_one("#transfer-bytes", Label).update("")
