"""The pymat desktop: folder tree left, editor top, console bottom.

This is the familiar scientific-IDE arrangement: the current folder and the
workspace live in the left sidebar, the Python editor fills the upper right, and
the console/output pane spans the bottom of the editing area.  Syntax colours
come from ``pymat.gui.code_editor``; matplotlib figures get their own windows.
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass
from typing import Any

import dui

from ..session import Session
from . import theme
from .code_editor import CodeEditor

DEMO_SCRIPT = '''# pymat demo -- ordinary Python with the scientific stack
# Run with the green Run button.

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

A = np.array([[4.0, -2.0], [1.0, 1.0]])
b = np.array([6.0, 3.0])
x = np.linalg.solve(A, b)
print("solution x =", x)

t = np.linspace(0, 2 * np.pi, 300)
df = pd.DataFrame({"t": t, "sin": np.sin(t), "cos": np.cos(t)})
print(df.head())

plt.figure()
plt.plot(df["t"], df["sin"], label="sin")
plt.plot(df["t"], df["cos"], label="cos")
plt.title("sin(t) and cos(t)")
plt.xlabel("t"); plt.ylabel("amplitude")
plt.grid(True); plt.legend()
plt.show()
'''


@dataclass
class EditorTab:
    title: str
    path: str | None
    page: Any
    editor: CodeEditor
    item: Any
    dirty: bool = False


_WS_COLUMNS = (("Name", 90, False), ("Type", 78, False),
               ("Shape", 50, False), ("Value", 110, False))
_WS_SEP = 6


def _ws_line_svg(name: str, color: str) -> str:
    path = os.path.join(tempfile.gettempdir(), name)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="24">'
           f'<rect width="2" height="24" fill="{color}"/></svg>')
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(svg)
    except OSError:
        pass
    return path


_WS_LINE = _ws_line_svg("pymat-ws-line.svg", "#FFD9DBDE")
_WS_LINE_ACTIVE = _ws_line_svg("pymat-ws-line-active.svg", "#FF0072BD")


class PymatWindow(dui.WindowImplBase):
    def __init__(self, app: Any) -> None:
        super().__init__()
        self.app = app
        self.session: Session = app.session
        self.tabs: list[EditorTab] = []
        self._history_index = 0
        self._continuation = False
        self._last_double = 0.0
        self._workspace_refresh_timer = 0

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def on_init_window(self) -> None:
        self.set_native_fullscreen(True)
        self.set_window_size(1280, 860)
        self.center_window()
        self.set_window_minimum_size(dui.UiSize(980, 680), True)

        root = dui.VBox(self, bkcolor=theme.WINDOW_BG)
        root.add_item(self._caption())
        root.add_item(self._toolbar())
        root.add_item(self._body())
        root.add_item(self._status_bar())
        self.attach_box(root)
        # Drawn on the window root, after the body, so the vertical rules sit
        # above both the header and every row.
        for _ in range(len(_WS_COLUMNS)):
            line = dui.Control(self, width="1", height="1",
                               bkcolor=theme.BORDER, float="true",
                               mouse_enabled="false")
            line.set_paint_order(255)
            root.add_item(line)
            self._ws_lines.append(line)

        self.attach_window_key_down_msg(self._on_key_down)
        self.attach_window_l_button_up_msg(self._on_mouse_up)
        self.attach_window_first_shown(self._schedule_ws_lines)
        self.add_editor("welcome.py", DEMO_SCRIPT, path=None)
        self._install_console()
        self.refresh_files()
        self.refresh_workspace()
        dui.set_timer(self._init_workspace_scale, 60, 1, owner=self)
        self.set_status("Ready.  Type Python in the console, or press Run.")

    def fit_to_work_area(self) -> None:
        """Keep the window inside the monitor's work area (above the Dock)."""
        work = dui.UiRect()
        if not self.get_monitor_work_rect(work):
            return
        window = dui.UiRect()
        self.get_window_rect(window)
        width, height = window.right - window.left, window.bottom - window.top
        work_w, work_h = work.right - work.left, work.bottom - work.top
        margin = 18
        width = min(width, max(640, work_w - 2 * margin))
        height = min(height, max(480, work_h - 2 * margin))
        x = work.left + max(0, (work_w - width) // 2)
        y = work.top + max(0, (work_h - height) // 2)
        if y + height > work.bottom:
            y = work.bottom - height
        if x + width > work.right:
            x = work.right - width
        self.move_window(int(x), int(y), int(width), int(height), True)

    # -- chrome ---------------------------------------------------------
    def _caption(self):
        bar = dui.HBox(self, name="window_caption_bar", height="34",
                       bkcolor=theme.CAPTION_BG)
        bar.add_item(dui.Label(self, text="P", font="system_bold_16",
                               normal_text_color=theme.ACCENT, valign="center",
                               margin="12,0,7,0"))
        bar.add_item(dui.Label(self, name="window_caption_title", text="pymat",
                               font="system_bold_14", normal_text_color=theme.TEXT,
                               valign="center"))
        bar.add_item(dui.Label(self, text="Python · numpy · pandas · scipy · matplotlib",
                               normal_text_color=theme.MUTED, valign="center",
                               margin="10,0,0,0"))
        bar.add_item(dui.Control(self, width="stretch", mouse_enabled="false"))
        bar.add_item(dui.Button(self, name="minbtn", class_="btn_wnd_min_11",
                                width="40", height="28", margin="0,2,0,2"))
        bar.add_item(dui.Button(self, name="maxbtn", class_="btn_wnd_max_11",
                                width="40", height="28", margin="0,2,0,2"))
        bar.add_item(dui.Button(self, name="closebtn", class_="btn_wnd_close_11",
                                width="40", height="28", margin="0,2,8,2"))
        return bar

    def _toolbar(self):
        bar = dui.HBox(self, height="42", bkcolor=theme.TOOLBAR_BG,
                       padding="10,6,10,6")
        for text, handler, width in (
                ("New", self.on_new, 62),
                ("Open", self.on_open, 66),
                ("Save", self.on_save, 62),
                ("Run", self.on_run, 74)):
            button = theme.toolbar_button(self, text, width, accent=(text == "Run"))
            button.attach_click(handler)
            bar.add_item(button)
        pysimu = theme.toolbar_button(self, "pysimu", 74)
        pysimu.set_tooltip_text("Open pysimu: Simulink-style block diagram simulation")
        pysimu.attach_click(self.on_open_pysimu)
        bar.add_item(pysimu)
        bar.add_item(theme.divider(self, vertical=True))
        for text, handler, width in (
                ("Clear console", self.on_clear_console, 104),
                ("Clear workspace", self.on_clear_workspace, 114),
                ("Help", self.on_help, 58)):
            button = theme.toolbar_button(self, text, width)
            button.attach_click(handler)
            bar.add_item(button)
        bar.add_item(dui.Control(self, width="stretch"))
        bar.add_item(dui.Label(self, text="Python 3 · dui", normal_text_color=theme.MUTED,
                               valign="center", text_align="right"))
        return bar

    def _body(self):
        body = dui.HBox(self, width="stretch", height="stretch",
                        padding="8,0,8,8")
        body.add_item(self._sidebar())
        self._main_split = dui.Split(self, width="7", height="stretch",
                                     bkcolor=theme.BORDER)
        body.add_item(self._main_split)
        right = dui.VBox(self, width="stretch", height="stretch")
        right.add_item(self._editor_area())
        # Horizontal splitter inside the right column: drag up/down to resize
        # the editor and the console.  The console no longer spans the whole
        # window, so it stays under the editor as requested.
        right.add_item(dui.Split(self, width="stretch", height="7",
                                 bkcolor=theme.BORDER))
        right.add_item(self._console_area())
        body.add_item(right)
        return body

    # -- left sidebar ----------------------------------------------------
    def _sidebar(self):
        panel = dui.VBox(self, width="360", height="stretch",
                         bkcolor=theme.PANEL_BG, border_size="1",
                         border_color=theme.BORDER, border_round="6,6",
                         padding="0,0,0,4")

        header = dui.HBox(self, height="28", bkcolor=theme.CAPTION_BG,
                          padding="10,0,8,0")
        header.add_item(dui.Label(self, text="FILES", font="system_bold_12",
                                  normal_text_color=theme.MUTED, valign="center"))
        header.add_item(dui.Control(self, width="stretch"))
        opening = dui.Button(self, class_="btn_global_color_gray", text="Open",
                             width="42", height="20", border_round="4,4",
                             margin="0,0,4,0", tooltip_text="Open selected file/folder")
        opening.attach_click(self.on_open_selected)
        header.add_item(opening)
        up = dui.Button(self, class_="btn_global_color_gray", text="Up", width="30",
                        height="20", border_round="4,4", margin="0,0,4,0")
        up.attach_click(lambda args: (self.on_up(), True)[1])
        header.add_item(up)
        refresh = dui.Button(self, class_="btn_global_color_gray", text="↻",
                             width="28", height="20", border_round="4,4")
        refresh.attach_click(lambda args: (self.refresh_files(), True)[1])
        header.add_item(refresh)
        panel.add_item(header)

        row = dui.HBox(self, height="24", padding="10,1,10,3")
        self._path_label = dui.Label(self, text=self.session.cwd, height="24",
                                     width="stretch", valign="center",
                                     normal_text_color=theme.MUTED,
                                     font="system_12", end_ellipsis="true")
        row.add_item(self._path_label)
        panel.add_item(row)

        # The file browser is a real tree: folders expand in place, files are
        # leaves, rows are icons + left-aligned text, and selection uses the
        # theme's tree_node selected background.
        self.file_tree = dui.TreeView(self, name="file_tree",
                                      class_="tree_view", width="stretch",
                                      height="360")
        panel.add_item(self.file_tree)
        self.file_tree.attach_event("return", self.on_open_selected)
        self.file_tree.set_tooltip_text(
            "Click to select; double-click or use the arrow to expand a folder; "
            "double-click a file to open it")
        self._tree_root = self.file_tree.get_root_node()
        self._expanded_dirs: set[str] = set()
        self._selected_path: str | None = None
        self._file_paths: list[str] = []
        self._folder_icon = self._load_icon("public/filesystem/folder.svg")
        self._file_icon = self._load_icon("public/filesystem/file.svg")

        # Vertical splitter between the file tree and the workspace.
        self._side_split = dui.Split(self, width="stretch", height="7",
                                     bkcolor=theme.BORDER)
        panel.add_item(self._side_split)

        self.workspace_panel = dui.VBox(self, width="stretch", height="stretch")
        workspace_panel = self.workspace_panel
        divider = dui.HBox(self, height="24", bkcolor=theme.CAPTION_BG,
                           padding="10,0,8,0")
        divider.add_item(dui.Label(self, text="WORKSPACE", font="system_bold_12",
                                   normal_text_color=theme.MUTED, valign="center"))
        divider.add_item(dui.Control(self, width="stretch"))
        refresh = dui.Button(self, class_="btn_global_color_gray", text="Refresh",
                             width="60", height="20", border_round="4,4")
        refresh.attach_click(lambda args: (self.refresh_workspace(), True)[1])
        divider.add_item(refresh)
        workspace_panel.add_item(divider)

        self.workspace_table = dui.VBox(
            self, width="stretch", height="stretch", bkcolor="white",
            border_size="1", border_color=theme.BORDER)
        header = dui.HBox(self, width="stretch", height="24",
                          bkcolor=theme.CAPTION_BG)
        self._ws_headers: list[Any] = []
        self._ws_widths = [90, 78, 50, 110]
        self._ws_splits: list[Any] = []
        self._ws_dpi_scale = 2.0
        self._ws_sync_timer = 0
        self._ws_line_timer = 0
        self._ws_line_retry = 0
        self._ws_active_split: int | None = None
        for index, (title, _width, _stretch) in enumerate(_WS_COLUMNS):
            if index:
                split = dui.Split(self, width=str(_WS_SEP), height="stretch",
                                  bkcolor="#00000000")
                split_index = len(self._ws_splits)
                split.attach_event(
                    "split_draged",
                    lambda args, i=split_index:
                    self._on_ws_split_dragged(i, args))
                header.add_item(split)
                self._ws_splits.append(split)
            label = dui.Label(
                self, text=title, width=str(self._ws_widths[index]),
                height="24", font="system_bold_12", normal_text_color=theme.MUTED,
                text_align="hcenter,vcenter", text_padding="5,0,5,0",
                tooltip_text=f"Sort by {title}")
            label.attach_click(
                lambda args, i=index: (self._workspace_header_clicked(i), True)[1])
            header.add_item(label)
            self._ws_headers.append(label)
        last = dui.Split(self, width=str(_WS_SEP), height="stretch",
                         bkcolor="#00000000", enable_split_single="true")
        last_index = len(self._ws_splits)
        last.attach_event(
            "split_draged",
            lambda args, i=last_index: self._on_ws_split_dragged(i, args))
        header.add_item(last)
        self._ws_splits.append(last)
        self.workspace_table.add_item(header)
        self.workspace_table.add_item(dui.Control(
            self, width="stretch", height="1", bkcolor=theme.BORDER,
            mouse_enabled="false"))

        self._ws_scroll = dui.ScrollBox(
            self, width="stretch", height="stretch", bkcolor="white",
            vscrollbar="true", hscrollbar="false")
        self._ws_body = dui.VBox(self._ws_scroll, width="stretch",
                                 height="auto", bkcolor="white")
        self._ws_scroll.add_item(self._ws_body)
        self.workspace_table.add_item(self._ws_scroll)
        self._ws_lines: list[Any] = []
        self.workspace_table.attach_size_changed(self._schedule_ws_lines)
        self._ws_rows: list[Any] = []
        self._ws_cells: list[list[Any]] = []
        self._ws_row_seps: list[list[Any]] = []
        self._ws_selected_cell: Any = None
        self._ws_sort_column: int | None = None
        self._ws_sort_desc = False
        workspace_panel.add_item(self.workspace_table)
        panel.add_item(workspace_panel)
        return panel

    # -- editor ----------------------------------------------------------
    def _editor_area(self):
        area = dui.VBox(self, width="stretch", height="stretch",
                        bkcolor=theme.PANEL_BG, border_size="1",
                        border_color=theme.BORDER, border_round="6,6")
        strip = dui.HBox(self, height="34", bkcolor=theme.CAPTION_BG,
                         padding="6,0,6,0")
        self.tab_ctrl = dui.TabCtrl(self, name="editor_tab_ctrl",
                                    class_="tab_ctrl", width="stretch",
                                    height="32", selected_id="0",
                                    bkcolor=theme.CAPTION_BG)
        self.tab_ctrl.set_tab_box_name("editor_tab_box")
        strip.add_item(self.tab_ctrl)
        run = dui.Button(self, class_="btn_global_color_blue", text="Run",
                         width="56", height="24", border_round="4,4",
                         margin="6,4,0,4")
        run.attach_click(self.on_run)
        strip.add_item(run)
        save = dui.Button(self, class_="btn_global_color_gray", text="Save",
                          width="52", height="24", border_round="4,4",
                          margin="4,4,0,4")
        save.attach_click(self.on_save)
        strip.add_item(save)
        close_tab = dui.Button(self, class_="btn_global_color_gray", text="✕",
                               width="28", height="24", border_round="4,4",
                               margin="4,4,0,4", tooltip_text="Close tab")
        close_tab.attach_click(self.on_close_tab)
        strip.add_item(close_tab)
        area.add_item(strip)

        self.tab_box = dui.TabBox(self, name="editor_tab_box", width="stretch",
                                  height="stretch", bkcolor="white",
                                  fade_switch="false")
        area.add_item(self.tab_box)

        footer = dui.HBox(self, height="24", bkcolor=theme.CAPTION_BG,
                          padding="10,0,10,0")
        footer.add_item(dui.Label(self, text="Python", normal_text_color=theme.MUTED,
                                  valign="center"))
        footer.add_item(dui.Control(self, width="stretch"))
        self._cursor_label = dui.Label(self, text="Ln 1, Col 1",
                                       normal_text_color=theme.MUTED,
                                       valign="center")
        footer.add_item(self._cursor_label)
        area.add_item(footer)
        return area

    # -- bottom console --------------------------------------------------
    def _console_area(self):
        area = dui.VBox(self, width="stretch", height="238", margin="0,0,0,0",
                        bkcolor=theme.PANEL_BG, border_size="1",
                        border_color=theme.BORDER, border_round="6,6")
        header = dui.HBox(self, height="28", bkcolor=theme.CAPTION_BG,
                          padding="10,0,8,0")
        header.add_item(dui.Label(self, text="CONSOLE", font="system_bold_12",
                                  normal_text_color=theme.MUTED, valign="center"))
        header.add_item(dui.Control(self, width="stretch"))
        header.add_item(dui.Label(self, text="Python REPL",
                                  normal_text_color=theme.MUTED, valign="center",
                                  margin="0,0,8,0"))
        clear = dui.Button(self, class_="btn_global_color_gray", text="Clear",
                           width="54", height="20", border_round="4,4")
        clear.attach_click(self.on_clear_console)
        header.add_item(clear)
        area.add_item(header)

        self.console = dui.RichEdit(self, name="console_output", width="stretch",
                                    height="stretch", bkcolor=theme.CONSOLE_BG,
                                    normal_text_color=theme.TEXT, font="system_14",
                                    multiline="true", vscrollbar="true",
                                    hscrollbar="true", auto_vscroll="true",
                                    word_wrap="false", text_padding="10,6,10,6",
                                    rich="false", hide_selection="false",
                                    default_context_menu="true",
                                    current_row_bkcolor="",
                                    inactive_current_row_bkcolor="",
                                    focus_bottom_border_size="0")
        self.console.set_read_only(True)
        area.add_item(self.console)

        input_row = dui.HBox(self, height="40", bkcolor=theme.CONSOLE_BG,
                             padding="10,3,8,4")
        # Bottom text padding lifts the label's centred text by one logical
        # pixel; the arrow glyph reads slightly high next to the input text.
        self._prompt = dui.Label(
            self, name="console_prompt", text=">>>",
            font="system_bold_14", normal_text_color=theme.ACCENT,
            width="34", height="32", valign="center",
            text_padding="0,0,0,2", text_align="hcenter,vcenter")
        input_row.add_item(self._prompt)
        self.input = dui.RichEdit(self, name="console_input", width="stretch",
                                  height="32", bkcolor="white",
                                  normal_text_color=theme.TEXT,
                                  font="system_14", multiline="false",
                                  prompt_mode="true",
                                  prompt_text="Type Python code and press Enter",
                                  prompt_color=theme.MUTED,
                                  text_align="left,vcenter",
                                  text_padding="6,0,6,0",
                                  focus_bottom_border_size="0",
                                  hide_selection="false",
                                  default_context_menu="true")
        self.input.attach_return(self.on_command_return)
        input_row.add_item(self.input)
        area.add_item(input_row)
        return area

    def _status_bar(self):
        bar = dui.HBox(self, height="24", bkcolor=theme.CAPTION_BG,
                       padding="10,0,10,0")
        self._status = dui.Label(self, text="Ready", height="24", valign="center",
                                 normal_text_color=theme.MUTED)
        bar.add_item(self._status)
        bar.add_item(dui.Control(self, width="stretch"))
        bar.add_item(dui.Label(self, text="pymat 0.2.0", height="24",
                               valign="center", normal_text_color=theme.MUTED))
        return bar

    # ------------------------------------------------------------------
    # Console
    # ------------------------------------------------------------------
    def _install_console(self) -> None:
        self._append_console(
            "pymat 0.2.0  ·  Python scientific desktop\n"
            "np / pd / sp / plt are ready.  Assignments do not echo; type a name "
            "to inspect it.\n\n")

    def _append_console(self, text: str) -> None:
        # A read-only RichEdit refuses AppendText, so the lock is lifted for the
        # programmatic write and put straight back.
        self.console.set_read_only(False)
        self.console.append_text(text, False, True)
        self.console.set_sel_none()
        self.console.set_read_only(True)
        # AppendText scrolls before the control has recalculated its range, so
        # the new rows can land below the viewport. Scroll explicitly once the
        # range is current; otherwise every command shows the old history.
        try:
            self.console.set_scroll_pos_y(
                int(self.console.get_scroll_range().cy))
        except Exception:  # noqa: BLE001
            pass

    def log(self, text: str) -> None:
        self._append_console(text if text.endswith("\n") else text + "\n")

    def on_command_return(self, args: Any = None) -> bool:
        line = self.input.get_text_a()
        self.input.set_text("")
        self.input.set_focus()
        if not line.strip() and not self._continuation:
            return True
        if not self._continuation:
            self.log(f">>> {line}")
        else:
            self.log(f"... {line}")
        try:
            done, result = self.session.feed(line)
        except Exception:  # noqa: BLE001 - a UI callback must keep the window alive
            import traceback
            self.log(traceback.format_exc())
            self._continuation = False
            self.set_status("Internal error.")
            return True
        self._history_index = len(self.session.history)
        if result.output:
            self.log(result.output.rstrip("\n"))
        if result.error:
            self.log(result.error.rstrip("\n"))
        if not done:
            self._continuation = True
            self.input.set_attribute("prompt_text", "  ...  ")
        else:
            self._continuation = False
            self.input.set_attribute("prompt_text", "Type Python code and press Enter")
            self.refresh_workspace()
            self.set_status("Ready." if result.ok else "Error.")
        return True

    def _on_key_down(self, args: Any = None) -> bool:
        try:
            focus = self.get_focus_control()
            if focus is None or getattr(focus, "name", "") != "console_input":
                return False
            key = int(getattr(args, "w_param", 0))
        except Exception:  # noqa: BLE001
            return False
        history = [line for line in self.session.history if line.strip()]
        if key in (38, 40) and history:  # Up / Down
            if key == 38:
                self._history_index = max(0, (self._history_index or len(history)) - 1)
            else:
                self._history_index = min(len(history), (self._history_index or 0) + 1)
            text = history[self._history_index] if self._history_index < len(history) else ""
            self.input.set_text(text)
            return True
        if key == 27:  # Esc cancels a continuation
            self._continuation = False
            self.session._buffer = ""
            self.input.set_attribute("prompt_text", "Type Python code and press Enter")
            return True
        return False

    # ------------------------------------------------------------------
    # Editor tabs
    # ------------------------------------------------------------------
    def add_editor(self, title: str, text: str, path: str | None = None) -> EditorTab:
        page = dui.VBox(self, width="stretch", height="stretch", bkcolor="white")
        editor = CodeEditor(
            page,
            on_cursor=lambda line, col: self._cursor_label.set_text(
                f"Ln {line}, Col {col}"))
        page.add_item(editor.container)
        index = len(self.tabs)
        item = dui.TabCtrlItem(self, class_="tab_ctrl_item", title=title,
                               tab_box_item_index=str(index), height="30",
                               width=str(max(96, min(260, 28 + len(title) * 8))))
        self.tab_ctrl.add_item(item)
        tab = EditorTab(title, path, page, editor, item)
        editor.on_change = lambda: self._on_editor_changed(tab)
        self.tab_box.add_item(page)
        self.tabs.append(tab)
        editor.set_text(text)
        self._select_editor_tab(index)
        self._set_editor_title(tab)
        editor.set_focus()
        return tab

    def _select_editor_tab(self, index: int) -> None:
        self.tab_box.select_item(index)
        try:
            self.tab_ctrl.set_attribute("selected_id", str(index))
        except Exception:  # noqa: BLE001
            pass

    def _set_editor_title(self, tab: EditorTab) -> None:
        tab.item.set_title(tab.title + (" *" if tab.dirty else ""))

    def _on_editor_changed(self, tab: EditorTab) -> None:
        if not tab.dirty:
            tab.dirty = True
            self._set_editor_title(tab)
        self.set_status(f"Editing {tab.title}")

    def current_tab(self) -> EditorTab | None:
        index = self.tab_box.get_cur_sel()
        if index is None:
            return None
        index = int(index)
        if 0 <= index < len(self.tabs):
            return self.tabs[index]
        return None

    def _current_index(self) -> int:
        index = self.tab_box.get_cur_sel()
        if index is None:
            return 0
        index = int(index)
        return index if 0 <= index < len(self.tabs) else 0

    def _replace_current_tab(self, title: str, text: str, path: str | None) -> EditorTab:
        tab = self.current_tab()
        if tab is None:
            return self.add_editor(title, text, path)
        tab.title = title
        tab.path = path
        tab.dirty = False
        tab.editor.set_text(text)
        self._set_editor_title(tab)
        return tab

    def on_new(self, args: Any = None) -> bool:
        self.add_editor("untitled.py", "# New pymat script\n", None)
        self.set_status("New script.")
        return True

    def on_open(self, args: Any = None) -> bool:
        path = dui.open_file(self, [("Python files", "*.py;*.pyw"),
                                    ("Text files", "*.txt"), ("All files", "*.*")],
                             "py", start_dir=self.session.cwd)
        if path:
            self.open_path(path)
        return True

    def open_path(self, path: str) -> None:
        full = os.path.abspath(path)
        for index, tab in enumerate(self.tabs):
            if tab.path and os.path.abspath(tab.path) == full:
                self._select_editor_tab(index)
                tab.editor.set_focus()
                self.set_status(f"Opened {path}")
                return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as error:
            self.log(f"cannot open {path}: {error}")
            return
        title = os.path.basename(path)
        # Reuse the untouched welcome tab instead of stacking a second one.
        tab = self.current_tab()
        if tab is not None and tab.path is None and tab.title == "welcome.py" and \
                tab.editor.get_text().strip() == DEMO_SCRIPT.strip():
            self._replace_current_tab(title, text, path)
        else:
            self.add_editor(title, text, path)
        self.set_status(f"Opened {path}")

    def on_save(self, args: Any = None) -> bool:
        tab = self.current_tab()
        if tab is None:
            return True
        path = tab.path
        if not path:
            path = dui.save_file(self, [("Python files", "*.py"),
                                        ("Text files", "*.txt")],
                                 "py", file_name=tab.title,
                                 start_dir=self.session.cwd)
            if not path:
                return True
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(tab.editor.get_text())
        except OSError as error:
            self.log(f"cannot save {path}: {error}")
            return True
        tab.path = path
        tab.title = os.path.basename(path)
        tab.dirty = False
        self._set_editor_title(tab)
        self.set_status(f"Saved {path}")
        return True

    def on_run(self, args: Any = None) -> bool:
        tab = self.current_tab()
        if tab is None:
            return True
        code = tab.editor.get_text()
        self.log(f"# run {tab.title}")
        old_file = self.session.ns.get("__file__")
        self.session.ns["__file__"] = tab.path or f"<{tab.title}>"
        try:
            result = self.session.execute(code)
        except Exception:  # noqa: BLE001
            import traceback
            self.log(traceback.format_exc())
            result = None
        if result is not None:
            if result.output:
                self.log(result.output.rstrip("\n"))
            if result.error:
                self.log(result.error.rstrip("\n"))
        if old_file is None:
            self.session.ns.pop("__file__", None)
        else:
            self.session.ns["__file__"] = old_file
        self.refresh_workspace()
        self.set_status("Run finished." if (result is not None and result.ok) else "Run failed.")
        tab.editor.set_focus()
        return True

    def on_close_tab(self, args: Any = None) -> bool:
        if len(self.tabs) <= 1:
            self.set_status("Cannot close the last tab.")
            return True
        index = self._current_index()
        tab = self.tabs[index]
        self.tab_box.remove_item(tab.page)
        self.tab_ctrl.remove_item(tab.item)
        self.tabs.pop(index)
        for k, remaining in enumerate(self.tabs):
            remaining.item.set_tab_box_item_index(k)
        self._select_editor_tab(max(0, index - 1))
        self.set_status("Tab closed.")
        return True

    # ------------------------------------------------------------------
    # Files and workspace
    # ------------------------------------------------------------------
    def _load_icon(self, image: str) -> int:
        try:
            return int(dui.add_icon(image))
        except Exception:  # noqa: BLE001 - icons are optional decoration
            return 0

    def _tree_node(self, parent_node: Any, name: str, path: str,
                   is_dir: bool) -> Any:
        node = dui.TreeNode(self, class_="tree_node", text=name, height="26")
        parent_node.add_child_node(node)
        icon = self._folder_icon if is_dir else self._file_icon
        if icon:
            try:
                node.set_bk_icon_id(icon, 16, True)
            except Exception:  # noqa: BLE001
                pass
        node.attach_click(
            lambda args, n=node, p=path, d=is_dir: self._tree_clicked(n, p, d))
        if is_dir:
            # A placeholder child makes the expand arrow appear; it is replaced
            # by the real children on the first expand.
            node.add_child_node(dui.TreeNode(self, text=" ", height="2"))
            node.attach_expand(
                lambda args, n=node, p=path: self._populate_directory(n, p))
            node.set_expand(False, False)
        else:
            node.attach_double_click(
                lambda args, p=path: (self.open_path(p), True)[1])
        return node

    def _tree_clicked(self, node: Any, path: str, is_dir: bool) -> bool:
        self._selected_path = path
        if is_dir:
            if node.is_expand():
                node.set_expand(False, False)
            else:
                self._populate_directory(node, path)
                node.set_expand(True, False)
            self.set_status(f"folder: {path}")
        else:
            self.open_path(path)
            self.set_status(f"file: {path}")
        return True

    def _populate_directory(self, node: Any, path: str) -> bool:
        if path in self._expanded_dirs:
            return True
        self._expanded_dirs.add(path)
        try:
            entries = sorted(os.scandir(path),
                             key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            entries = []
        node.remove_all_child_nodes()
        for entry in entries:
            try:
                is_dir = entry.is_dir()
            except OSError:
                is_dir = False
            self._tree_node(node, _display_name(entry), entry.path, is_dir)
        return True

    def _activate_path(self, path: str) -> None:
        if os.path.isdir(path):
            self.session.chdir(path)
            self.refresh_files()
            self.set_status(path)
        elif path.endswith((".py", ".pyw", ".txt")):
            self.open_path(path)
        else:
            self.set_status(f"Not a text file: {os.path.basename(path)}")

    def on_open_selected(self, args: Any = None) -> bool:
        if self._selected_path:
            self._activate_path(self._selected_path)
        return True

    def on_up(self) -> None:
        parent = os.path.dirname(self.session.cwd)
        if os.path.isdir(parent):
            self.session.chdir(parent)
            self.refresh_files()
            self.set_status(self.session.cwd)

    def refresh_files(self) -> None:
        path = self.session.cwd
        self._path_label.set_text(path)
        self._tree_root.remove_all_child_nodes()
        self._expanded_dirs.clear()
        self._expanded_dirs.add(path)
        self._selected_path = None
        self._file_paths = []
        try:
            entries = sorted(os.scandir(path),
                             key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            entries = []
        for entry in entries:
            try:
                is_dir = entry.is_dir()
            except OSError:
                is_dir = False
            self._tree_node(self._tree_root, _display_name(entry), entry.path,
                            is_dir)
            self._file_paths.append(entry.path)

    def refresh_workspace(self) -> None:
        variables = self.session.workspace()
        if self._ws_sort_column is not None:
            column = self._ws_sort_column
            variables = sorted(
                variables, key=lambda v: self._workspace_sort_key(v, column),
                reverse=self._ws_sort_desc)
        try:
            self._ws_body.remove_all_items()
        except Exception:  # noqa: BLE001
            pass
        self._ws_rows = []
        self._ws_cells = []
        self._ws_row_seps = []
        self._ws_selected_cell = None
        for row_index, var in enumerate(variables):
            values = (var.name, var.kind, var.size, var.value)
            row = dui.HBox(self._ws_body, width="stretch", height="23",
                           bkcolor="white")
            row_cells: list[Any] = []
            row_seps: list[Any] = []
            for index, (_, _width, _stretch) in enumerate(_WS_COLUMNS):
                if index:
                    sep = dui.Control(
                        self, width=str(_WS_SEP), height="stretch",
                        bkcolor="#00000000", mouse_enabled="false")
                    row.add_item(sep)
                    row_seps.append(sep)
                text = str(values[index])
                cell = dui.Label(
                    row, text=text,
                    width=str(self._ws_widths[index]),
                    height="23", font="system_12", normal_text_color=theme.TEXT,
                    text_align="hcenter,vcenter", text_padding="5,0,5,0",
                    tooltip_text=text, bkcolor="#00000000")
                cell.attach_click(
                    lambda args, ctrl=cell, i=row_index, c=index, t=text:
                    (self._workspace_cell_clicked(ctrl, i, c, t), True)[1])
                row.add_item(cell)
                row_cells.append(cell)
            right_sep = dui.Control(
                self, width=str(_WS_SEP), height="stretch",
                bkcolor="#00000000", mouse_enabled="false")
            row.add_item(right_sep)
            row_seps.append(right_sep)
            self._ws_body.add_item(row)
            self._ws_body.add_item(dui.Control(
                self, width="stretch", height="1", bkcolor=theme.BORDER,
                mouse_enabled="false"))
            self._ws_rows.append(row)
            self._ws_cells.append(row_cells)
            self._ws_row_seps.append(row_seps)
        try:
            self._ws_body.relayout_or_redraw()
            self.workspace_table.relayout_or_redraw()
        except Exception:  # noqa: BLE001
            pass
        self._update_ws_separators()
        self._layout_ws_lines()

    def _schedule_ws_lines(self, args: Any = None) -> bool:
        if self._ws_line_timer == 0:
            self._ws_line_timer = dui.set_timer(
                self._ws_lines_tick, 30, 1, owner=self)
        return True

    def _ws_lines_tick(self) -> bool:
        self._ws_line_timer = 0
        self._layout_ws_lines()
        return False

    def _layout_ws_lines(self, args: Any = None) -> bool:
        if not getattr(self, "_ws_lines", None):
            return True
        try:
            tp = self.workspace_table.get_pos()
            scale = max(1e-6, self._ws_dpi_scale)
            visible = bool(self._ws_rows)
            bottom = tp[3]
            if visible:
                try:
                    row_bottom = self._ws_rows[-1].get_pos()[3]
                    if row_bottom <= tp[1] + 4 and self._ws_line_retry < 12:
                        self._ws_line_retry += 1
                        self._schedule_ws_lines()
                    else:
                        self._ws_line_retry = 0
                    bottom = min(tp[3], row_bottom)
                except Exception:  # noqa: BLE001
                    bottom = tp[3]
            x = 0.0
            for index, width in enumerate(self._ws_widths):
                x += width
                center = x + _WS_SEP * index + _WS_SEP / 2.0
                px = tp[0] + int(round(center * scale))
                line = self._ws_lines[index]
                line.set_visible(visible)
                line.set_pos(
                    dui.UiRect(px, tp[1], px + max(1, int(round(scale))), bottom))
        except Exception:  # noqa: BLE001
            pass
        return True

    def _on_mouse_up(self, args: Any = None) -> bool:
        if getattr(self, "_ws_active_split", None) is not None:
            self._select_ws_split(None)
        return False

    def _init_workspace_scale(self) -> bool:
        try:
            p = self._ws_headers[0].get_pos()
            width = p[2] - p[0]
            if width > 0:
                self._ws_dpi_scale = width / max(1, self._ws_widths[0])
            self._schedule_ws_lines()
        except Exception:  # noqa: BLE001
            pass
        return False

    def _select_ws_split(self, index: Any) -> None:
        self._ws_active_split = index
        for idx, line in enumerate(self._ws_lines):
            try:
                line.set_attribute(
                    "bkcolor", "#FF0072BD" if idx == index else theme.BORDER)
            except Exception:  # noqa: BLE001
                pass
        self._update_ws_separators()
        self._layout_ws_lines()

    def _update_ws_separators(self) -> None:
        has_rows = bool(self._ws_rows)
        for line in getattr(self, "_ws_lines", ()):
            try:
                line.set_visible(has_rows)
            except Exception:  # noqa: BLE001
                pass

    def _on_ws_split_dragged(self, index: int = 0,
                             args: Any = None) -> bool:
        self._select_ws_split(index)
        if self._ws_sync_timer == 0:
            self._ws_sync_timer = dui.set_timer(
                self._sync_ws_widths, 25, 1, owner=self.workspace_table)
        return True

    def _sync_ws_widths(self) -> bool:
        self._ws_sync_timer = 0
        widths = []
        for index, label in enumerate(self._ws_headers):
            try:
                p = label.get_pos()
                px = p[2] - p[0]
                if self._ws_dpi_scale <= 0:
                    self._ws_dpi_scale = px / max(1, self._ws_widths[index])
                widths.append(max(32, int(round(px / self._ws_dpi_scale))))
            except Exception:  # noqa: BLE001
                widths.append(self._ws_widths[index])
        try:
            tp = self.workspace_table.get_pos()
            avail = int((tp[2] - tp[0]) / max(1e-6, self._ws_dpi_scale)) - 2
            used = sum(widths) + _WS_SEP * len(widths)
            for index in range(len(widths) - 1, -1, -1):
                if used <= avail:
                    break
                excess = used - avail
                reduce = min(excess, max(0, widths[index] - 32))
                widths[index] -= reduce
                used -= reduce
        except Exception:  # noqa: BLE001
            pass
        self._ws_widths = widths
        for row in self._ws_cells:
            for index, cell in enumerate(row):
                if index < len(widths):
                    try:
                        cell.set_attribute("width", str(widths[index]))
                    except Exception:  # noqa: BLE001
                        pass
        # Re-apply header widths only if clamping changed them.
        for index, label in enumerate(self._ws_headers):
            try:
                p = label.get_pos()
                current = int(round((p[2] - p[0]) / max(1e-6, self._ws_dpi_scale)))
                if current != widths[index]:
                    label.set_attribute("width", str(widths[index]))
            except Exception:  # noqa: BLE001
                pass
        try:
            self._ws_body.relayout_or_redraw()
        except Exception:  # noqa: BLE001
            pass
        self._layout_ws_lines()
        return False

    @staticmethod
    def _workspace_sort_key(var: Any, column: int) -> Any:
        values = (var.name, var.kind, var.size, var.value)
        text = str(values[column])
        if column == 2:
            parts = text.lower().split("x")
            numbers = []
            for part in parts:
                try:
                    numbers.append(int(part))
                except ValueError:
                    numbers.append(0)
            while len(numbers) < 2:
                numbers.append(1)
            product = 1
            for number in numbers:
                product *= number
            return (product, text)
        return text.lower()

    def _workspace_header_clicked(self, column: int) -> None:
        if self._ws_sort_column == column:
            self._ws_sort_desc = not self._ws_sort_desc
        else:
            self._ws_sort_column = column
            self._ws_sort_desc = False
        for index, (title, _, _) in enumerate(_WS_COLUMNS):
            suffix = ""
            if index == self._ws_sort_column:
                suffix = " ▼" if self._ws_sort_desc else " ▲"
            try:
                self._ws_headers[index].set_text(title + suffix)
            except Exception:  # noqa: BLE001
                pass
        self.refresh_workspace()

    def workspace_row_count(self) -> int:
        return len(self._ws_rows)

    def _workspace_cell_clicked(self, cell: Any, row_index: int,
                                column: int, text: str) -> None:
        if self._ws_selected_cell is not None:
            try:
                self._ws_selected_cell.set_attribute("bkcolor", "#00000000")
            except Exception:  # noqa: BLE001
                pass
        cell.set_attribute("bkcolor", "#FFDCEBFF")
        self._ws_selected_cell = cell
        title = _WS_COLUMNS[column][0]
        self.set_status(f"row {row_index + 1} · {title}: {text}")

    # ------------------------------------------------------------------
    # Toolbar commands
    # ------------------------------------------------------------------
    def _sibling_project(self, name: str) -> str | None:
        # main_window.py -> gui -> pymat package -> pymat repo -> projects-main
        projects = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(projects, name)
        return path if os.path.isdir(path) else None

    def on_open_pysimu(self, args: Any = None) -> bool:
        from ..sim.gui import PysimuWindow

        existing = getattr(self.app, "pysimu_window", None)
        if existing is not None:
            try:
                existing.show_window()
                existing.set_window_focus()
                return True
            except Exception:  # noqa: BLE001 - window was closed
                self.app.pysimu_window = None
        window = PysimuWindow(self.app)
        if not window.create_wnd("pysimu"):
            self.log("pysimu: could not create the block diagram window")
            return True
        window.fit_to_work_area()
        window.show_window()
        self.app.pysimu_window = window
        self.set_status("pysimu opened")
        return True

    def on_clear_console(self, args: Any = None) -> bool:
        self.console.set_read_only(False)
        self.console.set_text("")
        self.console.set_sel_none()
        self.console.set_read_only(True)
        self._install_console()
        self.set_status("Console cleared.")
        return True

    def on_clear_workspace(self, args: Any = None) -> bool:
        self.session.clear()
        self.refresh_workspace()
        self.set_status("Workspace cleared.")
        return True

    def on_help(self, args: Any = None) -> bool:
        from ..session import HELP_TEXT
        self.log(HELP_TEXT)
        return True

    def set_status(self, text: str) -> None:
        self._status.set_text(text)


def _display_name(entry: os.DirEntry) -> str:
    try:
        return entry.name + ("/" if entry.is_dir() else "")
    except OSError:
        return entry.name


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
