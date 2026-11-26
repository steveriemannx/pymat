"""pysimu: a Simulink-style block-diagram window for pymat.

The user adds blocks by clicking or dragging an icon from the left palette,
moves them on the white grid, and wires them by dragging from a green output dot
to a block or a blue input dot (the Connect button keeps the older
click-source-then-target flow).  Blocks and wires have right-click menus, and a
double-click on a block focuses its parameter field.  The diagram is then run
with the simulation engine in ``pymat.sim``.  Results are plotted through
matplotlib, so they appear in pymat's regular figure windows.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from typing import Any

import dui

import numpy as np

from .. import mpl
from .blocks import BLOCK_TYPES
from .diagram import AlgebraicLoopError, Diagram

PALETTE_GROUPS = [
    ("SOURCES", [
        ("Step", "Step"),
        ("Sine", "Sine"),
        ("Constant", "Constant"),
        ("Ramp", "Ramp"),
        ("Clock", "Clock"),
        ("Pulse", "Pulse"),
    ]),
    ("SINKS", [
        ("Scope", "Scope"),
        ("Terminator", "Terminator"),
    ]),
    ("CONTINUOUS", [
        ("Integrator", "Integrator"),
        ("Derivative", "Derivative"),
        ("Transfer Fcn", "TransferFunction"),
        ("State Space", "StateSpace"),
        ("PID", "PID"),
    ]),
    ("MATH", [
        ("Gain", "Gain"),
        ("Sum", "Sum"),
        ("Product", "Product"),
        ("Divide", "Divide"),
        ("Abs", "Abs"),
        ("Math Function", "MathFunction"),
        ("MinMax", "MinMax"),
        ("Sign", "Sign"),
        ("Saturation", "Saturation"),
    ]),
    ("SIGNAL", [
        ("Bias", "Bias"),
        ("Dead Zone", "DeadZone"),
    ]),
    ("LOGIC", [
        ("Compare", "Compare"),
        ("Switch", "Switch"),
        ("Logical Op", "LogicalOperator"),
    ]),
]

PALETTE = [entry for _group, entries in PALETTE_GROUPS for entry in entries]

# Palette blocks that need parameters to be constructible get a sane default.
BLOCK_DEFAULTS = {
    "StateSpace": {
        "A": [[-1.0]], "B": [[1.0]], "C": [[1.0]], "D": [[0.0]],
    },
}

DISPLAY_TITLES = {kind: title for title, kind in PALETTE}
BLOCK_W, BLOCK_H = 108, 62
BLOCK_ICON = 14
PORT_SIZE = 12
LINE_WIDTH = 2

WINDOW_BG = "#FFFFFFFF"
CANVAS_BG = "#FFFFFFFF"
GRID_DOT = "#FFD9DEE6"
# SVG colours are CSS #RRGGBB, not dui's #AARRGGBB: an 8-digit fill is
# decoded as black by the image decoder.
GRID_DOT_SVG = "#d9dee6"
LINK_COLOR = "#FF5B6673"
LINK_SELECTED = "#FF2D7FF9"
LINK_PREVIEW = "#FF9AA7B8"
PORT_IN = "#FF0072BD"
PORT_OUT = "#FF2E7D32"
BLOCK_BORDER = "#FFB7C1CF"
BLOCK_SELECTED_BORDER = "#FF2D7FF9"
BLOCK_SELECTED_BG = "#FFF0F6FF"

# Small 20x20 line-art icons, one per palette entry.  Kept as SVG so they
# scale with the display and stay crisp in the palette and the drag ghost.
ICON_SVG = {
    "Integrator":
        '<path d="M9 3 C15 5 5 15 11 17" fill="none" stroke="#0072bd" '
        'stroke-width="2" stroke-linecap="round"/>',
    "Derivative":
        '<path d="M3 17 H17 M3 17 V3" fill="none" stroke="#0072bd" '
        'stroke-width="1.5"/>'
        '<path d="M4 14 C8 14 10 8 16 6" fill="none" stroke="#2e7d32" '
        'stroke-width="1.6"/>'
        '<path d="M7 16 L14 4" stroke="#0072bd" stroke-width="1.6"/>',
    "Gain":
        '<path d="M4 4 L17 10 L4 16 Z" fill="none" stroke="#0072bd" '
        'stroke-width="2" stroke-linejoin="round"/>',
    "Sum":
        '<circle cx="10" cy="10" r="6" fill="none" stroke="#0072bd" '
        'stroke-width="2"/>'
        '<path d="M7 10 H13 M10 7 V13" stroke="#2e7d32" stroke-width="1.6"/>',
    "Step":
        '<path d="M3 15 H9 V5 H17" fill="none" stroke="#0072bd" '
        'stroke-width="2" stroke-linejoin="round"/>',
    "Sine":
        '<path d="M3 10 C5 3 7 3 10 10 C13 17 15 17 17 10" fill="none" '
        'stroke="#0072bd" stroke-width="2"/>',
    "Constant":
        '<path d="M4 10 H16" stroke="#0072bd" stroke-width="2"/>'
        '<path d="M8 6 V14 M12 8 V12" stroke="#2e7d32" stroke-width="2"/>',
    "Ramp":
        '<path d="M3 16 H17 M3 16 V3" fill="none" stroke="#0072bd" '
        'stroke-width="1.5"/>'
        '<path d="M4 14 H8 L16 5" fill="none" stroke="#2e7d32" '
        'stroke-width="1.8"/>',
    "Clock":
        '<circle cx="10" cy="10" r="6" fill="none" stroke="#0072bd" '
        'stroke-width="2"/>'
        '<path d="M10 6 V10 L13 12" fill="none" stroke="#2e7d32" '
        'stroke-width="1.6"/>',
    "Pulse":
        '<path d="M3 14 H6 V6 H10 V14 H14 V6 H17" fill="none" '
        'stroke="#0072bd" stroke-width="1.8"/>',
    "Product":
        '<path d="M5 5 L15 15 M15 5 L5 15" stroke="#0072bd" '
        'stroke-width="2"/>',
    "Divide":
        '<path d="M6 5 L14 15" stroke="#0072bd" stroke-width="2"/>'
        '<circle cx="7" cy="5" r="1.4" fill="#2e7d32"/>'
        '<circle cx="13" cy="15" r="1.4" fill="#2e7d32"/>',
    "Abs":
        '<path d="M6 4 V16 M14 4 V16" stroke="#0072bd" stroke-width="2"/>'
        '<path d="M8 10 H12" stroke="#2e7d32" stroke-width="1.6"/>',
    "MathFunction":
        '<path d="M3 10 C5 3 7 3 10 10 C13 17 15 17 17 10" fill="none" '
        'stroke="#0072bd" stroke-width="2"/>',
    "MinMax":
        '<path d="M3 14 H7 L10 6 L13 14 H17" fill="none" stroke="#0072bd" '
        'stroke-width="1.8" stroke-linejoin="round"/>'
        '<path d="M4 6 L4 3 M2.5 4.5 L4 3 L5.5 4.5" fill="none" '
        'stroke="#2e7d32" stroke-width="1.2"/>',
    "Sign":
        '<path d="M4 8 H10 M7 5 V11" stroke="#0072bd" stroke-width="1.8"/>'
        '<path d="M12 13 H18" stroke="#2e7d32" stroke-width="1.8"/>',
    "Bias":
        '<path d="M3 13 H17" stroke="#0072bd" stroke-width="2"/>'
        '<path d="M10 10 V3 M8.5 4.5 L10 3 L11.5 4.5" fill="none" '
        'stroke="#2e7d32" stroke-width="1.5"/>',
    "DeadZone":
        '<path d="M3 15 H7 L9 8 H11 L13 15 H17" fill="none" '
        'stroke="#0072bd" stroke-width="1.8" stroke-linejoin="round"/>',
    "Compare":
        '<path d="M5 5 L15 10 L5 15" fill="none" stroke="#0072bd" '
        'stroke-width="2" stroke-linejoin="round"/>'
        '<path d="M5 17 H15" stroke="#2e7d32" stroke-width="1.4"/>',
    "Switch":
        '<path d="M3 7 H9 L14 13 H17 M3 13 H9" fill="none" '
        'stroke="#0072bd" stroke-width="1.8"/>'
        '<circle cx="11" cy="10" r="1.6" fill="#2e7d32"/>',
    "LogicalOperator":
        '<path d="M4 5 V15 H10 C15 15 16 12 16 10 C16 8 15 5 10 5 Z" '
        'fill="none" stroke="#0072bd" stroke-width="1.8"/>'
        '<path d="M1 7 H4 M1 13 H4 M16 10 H19" stroke="#2e7d32" '
        'stroke-width="1.5"/>',
    "StateSpace":
        '<rect x="3" y="5" width="14" height="10" rx="1" fill="none" '
        'stroke="#0072bd" stroke-width="2"/>'
        '<path d="M7 8 H13 M7 11 H13 M7 14 H11" stroke="#2e7d32" '
        'stroke-width="1.4"/>',
    "Terminator":
        '<path d="M10 4 V13 M5 13 H15 M7 16 H13" fill="none" '
        'stroke="#0072bd" stroke-width="1.8"/>',
    "TransferFunction":
        '<rect x="3" y="5" width="14" height="10" rx="1" fill="none" '
        'stroke="#0072bd" stroke-width="2"/>'
        '<path d="M6 12 C8 8 10 8 12 11" fill="none" stroke="#2e7d32" '
        'stroke-width="1.6"/>',
    "PID":
        '<rect x="3" y="5" width="14" height="10" rx="1" fill="none" '
        'stroke="#0072bd" stroke-width="2"/>'
        '<path d="M7 13 V8 M10 13 V6 M13 13 V10" stroke="#2e7d32" '
        'stroke-width="1.6"/>',
    "Saturation":
        '<path d="M3 14 H6 L8 6 H12 L14 14 H17" fill="none" stroke="#0072bd" '
        'stroke-width="2" stroke-linejoin="round"/>',
    "Scope":
        '<rect x="3" y="5" width="14" height="11" rx="1" fill="none" '
        'stroke="#0072bd" stroke-width="2"/>'
        '<path d="M5 11 C7 6 9 14 11 10 C12.5 7.5 13.5 9 15 8" fill="none" '
        'stroke="#2e7d32" stroke-width="1.4"/>',
}

_ICON_PATHS: dict[str, str] = {}


def _icon_path(kind: str) -> str:
    if kind in _ICON_PATHS:
        return _ICON_PATHS[kind]
    shape = ICON_SVG.get(kind)
    if not shape:
        return ""
    safe = "".join(ch if ch.isalnum() else "_" for ch in kind)
    path = os.path.join(tempfile.gettempdir(), f"pymat-sim-icon-{safe}.svg")
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
           f'{shape}</svg>')
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(svg)
        _ICON_PATHS[kind] = path
        return path
    except OSError:
        return ""


def _grid_svg() -> str:
    path = os.path.join(tempfile.gettempdir(), "pymat-sim-grid-white.svg")
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">'
           '<rect width="24" height="24" fill="#ffffff"/>'
           f'<circle cx="2" cy="2" r="1" fill="{GRID_DOT_SVG}"/></svg>')
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(svg)
        return path
    except OSError:
        return ""


@dataclass
class GuiBlock:
    bid: int
    kind: str
    block: Any
    control: Any
    title: Any
    detail: Any


class PysimuWindow(dui.WindowImplBase):
    def __init__(self, app: Any, project_path: str | None = None) -> None:
        super().__init__()
        self.app = app
        self.project_path = project_path or self._default_project_path()
        self.diagram = Diagram()
        self.blocks: dict[int, GuiBlock] = {}
        self.positions: dict[int, tuple[int, int]] = {}
        # (block id, "in" | "out", port index) -> port dot control
        self.ports: dict[tuple[int, str, int], Any] = {}
        self.selected: int | None = None
        self.selected_link: tuple[int, int, int] | None = None
        self.connect_mode = False
        self.connect_source: int | None = None
        self._link_drag: dict[str, Any] | None = None
        self._palette_drag: dict[str, Any] | None = None
        self._wire_drag: dict[str, Any] | None = None
        self._connect_handled = False
        self.link_lanes: dict[tuple[int, int, int], int] = {}
        self.link_columns: dict[tuple[int, int, int], tuple[int, int]] = {}
        self._ghost: Any = None
        self.root: Any = None
        self._menu: Any = None
        self._scale_cache: float | None = None
        # (left, top, right, bottom, key, "h"|"v") for wire hit tests
        self._segment_hits: list[tuple[int, int, int, int,
                                        tuple[int, int, int], str]] = []
        # (segment control, key) for in-place selection colour updates
        self._line_items: list[tuple[Any, tuple[int, int, int]]] = []
        self._ready = False

    def _default_project_path(self) -> str:
        here = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        pysimu = os.path.join(os.path.dirname(here), "pysimu")
        return pysimu if os.path.isdir(pysimu) else os.getcwd()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def on_init_window(self) -> None:
        self.set_native_fullscreen(True)
        self.set_window_size(1120, 700)
        self.center_window()

        root = dui.VBox(self, bkcolor=WINDOW_BG)
        self.root = root
        root.add_item(self._caption())
        root.add_item(dui.Control(self, height="1", bkcolor="#FFE6E8EC",
                                  mouse_enabled="false"))
        root.add_item(self._toolbar())
        body = dui.HBox(self, width="stretch", height="stretch",
                        padding="8,0,8,8")
        body.add_item(self._palette())
        body.add_item(dui.Split(self, width="7", height="stretch",
                                bkcolor="#FFE6E8EC"))
        body.add_item(self._canvas())
        root.add_item(body)
        root.add_item(dui.Control(self, height="1", bkcolor="#FFE6E8EC",
                                  mouse_enabled="false"))
        root.add_item(self._status_bar())
        self.attach_box(root)
        self.attach_window_close_msg(self._on_window_close)
        self.attach_window_mouse_move_msg(self._on_window_mouse_move)
        self.attach_window_l_button_up_msg(self._on_window_mouse_up)
        self.attach_window_first_shown(self._on_first_shown)
        self._ready = True
        self._load_or_demo()
        self.fit_to_work_area()

    def _on_first_shown(self, args: Any = None) -> bool:
        # Timers scheduled from OnInitWindow run before the message loop and
        # never fire, so finish the layout and wire redraw here.
        if not self._ready:
            return False
        self._apply_positions()
        self._schedule_links()
        return False

    def _caption(self):
        bar = dui.HBox(self, name="window_caption_bar", height="34",
                       bkcolor=WINDOW_BG)
        bar.add_item(dui.Label(self, text="pysimu", font="system_bold_14",
                               normal_text_color="#FF0072BD", valign="center",
                               margin="12,0,8,0"))
        bar.add_item(dui.Label(self, text="block diagram · Simulink-style",
                               normal_text_color="#FF6B7076", valign="center"))
        bar.add_item(dui.Control(self, width="stretch"))
        bar.add_item(dui.Button(self, name="minbtn", class_="btn_wnd_min_11",
                                width="40", height="28", margin="0,2,0,2"))
        bar.add_item(dui.Button(self, name="maxbtn", class_="btn_wnd_max_11",
                                width="40", height="28", margin="0,2,0,2"))
        bar.add_item(dui.Button(self, name="closebtn", class_="btn_wnd_close_11",
                                width="40", height="28", margin="0,2,8,2"))
        return bar

    def _toolbar(self):
        bar = dui.HBox(self, height="42", bkcolor=WINDOW_BG,
                       padding="10,6,10,6")
        for text, handler, width, blue in (
                ("Run", self.on_run, 66, True),
                ("Connect", self.on_toggle_connect, 78, False),
                ("Delete", self.on_delete, 66, False),
                ("Clear", self.on_clear, 58, False),
                ("Save", self.on_save, 58, False),
                ("Load", self.on_load, 58, False)):
            cls = "btn_global_color_blue" if blue else "btn_global_color_gray"
            button = dui.Button(self, class_=cls, text=text, width=str(width),
                                height="28", border_round="5,5",
                                margin="0,0,5,0")
            button.attach_click(handler)
            bar.add_item(button)
        bar.add_item(dui.Label(self, text="t =", height="26",
                               font="system_13", normal_text_color="#FF6B7076",
                               text_align="left,vcenter",
                               margin="8,0,4,0"))
        self._time_edit = dui.RichEdit(self, width="54", height="26",
                                       multiline="false", text="10",
                                       text_align="hcenter,vcenter",
                                       font="system_13",
                                       text_padding="4,4,4,4")
        bar.add_item(self._time_edit)
        bar.add_item(dui.Label(self, text="params", height="26",
                               font="system_13", normal_text_color="#FF6B7076",
                               text_align="left,vcenter",
                               margin="10,0,4,0"))
        self._param_edit = dui.RichEdit(
            self, width="230", height="26", multiline="false",
            prompt_mode="true",
            prompt_text="e.g. gain=2  |  num=[1]; den=[1,2,1]",
            font="system_13", text_padding="6,4,6,4",
            text_align="left,vcenter")
        bar.add_item(self._param_edit)
        self._param_edit.attach_return(
            lambda args: self.on_apply_params())
        apply = dui.Button(self, class_="btn_global_color_gray", text="Apply",
                           width="52", height="26", border_round="4,4",
                           margin="5,0,0,0")
        apply.attach_click(self.on_apply_params)
        bar.add_item(apply)
        bar.add_item(dui.Control(self, width="stretch"))
        self._mode = dui.Label(self, text="select", normal_text_color="#FF6B7076",
                               valign="center")
        bar.add_item(self._mode)
        return bar

    def _palette(self):
        panel = dui.VBox(self, width="176", height="stretch",
                         bkcolor=WINDOW_BG, border_size="1",
                         border_color="#FFD9DBDE", border_round="6,6",
                         padding="6,6,6,6")
        panel.add_item(dui.Label(self, text="BLOCK LIBRARY",
                                 font="system_bold_12",
                                 normal_text_color="#FF6B7076", height="20",
                                 margin="2,0,0,0"))
        scroll = dui.ScrollBox(
            panel, width="stretch", height="stretch",
            vscrollbar="true", hscrollbar="false", bkcolor="#00FFFFFF")
        panel.add_item(scroll)
        content = dui.VBox(scroll, width="stretch", height="auto",
                           bkcolor="#00FFFFFF")
        scroll.add_item(content)
        for group, entries in PALETTE_GROUPS:
            content.add_item(dui.Label(
                content, text=group, font="system_bold_11",
                normal_text_color="#FF8A97A8", height="18",
                margin="4,8,0,2", mouse_enabled="false"))
            for title, kind in entries:
                button = dui.ButtonHBox(
                    content, name=f"palette_{kind}",
                    class_="btn_global_color_gray", text="",
                    width="stretch", height="28", border_round="4,4",
                    margin="0,1,0,1")
                icon = _icon_path(kind)
                if icon:
                    button.add_item(dui.Control(
                        button, width="20", height="20",
                        bkimage=f"file='{icon}'", margin="6,0,0,0",
                        valign="center", mouse_enabled="false"))
                button.add_item(dui.Label(
                    button, text=title, width="stretch", height="20",
                    valign="center", margin="6,0,4,0",
                    mouse_enabled="false"))
                button.attach_click(
                    lambda args, k=kind: (self.add_block(k), True)[1])
                button.attach_button_down(
                    lambda args, k=kind: self._begin_palette_drag(k))
                content.add_item(button)
        hint = dui.Label(
            panel, name="palette_hint",
            text="click or drag an icon\nonto the canvas\n"
                 "right-click = menu",
            width="stretch", height="48", font="system_11",
            normal_text_color="#FF9AA0A6", single_line="false",
            mouse_enabled="false")
        panel.add_item(hint)
        return panel

    def _canvas(self):
        self.canvas_view = dui.Box(
            self, width="stretch", height="stretch", bkcolor=CANVAS_BG,
            border_size="1", border_color="#FFD9DBDE", border_round="6,6",
            clip="true")
        self.canvas = dui.Box(self.canvas_view, width="stretch",
                              height="stretch", bkcolor=CANVAS_BG)
        self.canvas_view.add_item(self.canvas)
        grid = _grid_svg()
        if grid:
            self.canvas.set_attribute(
                "bkimage", f"file='{grid}' xtiled='true' ytiled='true'")
        self.link_layer = dui.Box(self.canvas, width="stretch", height="stretch",
                                  float="true", bkcolor="#00000000",
                                  mouse_enabled="false")
        self.canvas.add_item(self.link_layer)
        # Paint wires above blocks so a hand-routed or crossing wire never
        # disappears behind a block face.
        self.link_layer.set_paint_order(255)
        self.canvas.attach_click(self._on_canvas_click)
        self.canvas.attach_context_menu(self._on_canvas_context_menu)
        self.canvas.attach_button_down(self._on_canvas_button_down)
        return self.canvas_view

    def _status_bar(self):
        bar = dui.HBox(self, height="24", bkcolor=WINDOW_BG,
                       padding="10,0,10,0")
        self._status = dui.Label(self, text=f"project: {self.project_path}",
                                 valign="center", normal_text_color="#FF6B7076")
        bar.add_item(self._status)
        bar.add_item(dui.Control(self, width="stretch"))
        bar.add_item(dui.Label(self, text="pysimu", normal_text_color="#FF6B7076",
                               valign="center"))
        return bar

    # ------------------------------------------------------------------
    # Blocks
    # ------------------------------------------------------------------
    def _dpi_scale(self) -> float:
        """Client pixels per logical point (2 on a Retina display)."""
        if self._scale_cache is not None:
            return self._scale_cache
        try:
            client = dui.UiRect()
            window = dui.UiRect()
            self.get_client_rect(client)
            self.get_window_rect(window)
            logical = window.right - window.left
            physical = client.right - client.left
            if logical > 0 and physical > 0:
                self._scale_cache = max(1.0, physical / logical)
                return self._scale_cache
        except Exception:  # noqa: BLE001
            pass
        return 1.0

    def _block_size(self) -> tuple[int, int]:
        scale = self._dpi_scale()
        return (max(1, round(BLOCK_W * scale)),
                max(1, round(BLOCK_H * scale)))

    def _next_position(self) -> tuple[int, int]:
        # Positions are in client pixels, so scale the spacing as well or new
        # blocks overlap on Retina screens.
        scale = self._dpi_scale()
        width, height = self._block_size()
        count = len(self.positions)
        return (round(28 * scale) + (count % 4) * (width + round(36 * scale)),
                round(28 * scale) + (count // 4) * (height + round(44 * scale)))

    def add_block(self, kind: str, params: dict | None = None,
                  position: tuple[int, int] | None = None,
                  block_id: int | None = None) -> int:
        if params is None:
            params = dict(BLOCK_DEFAULTS.get(kind, {}))
        try:
            block = self.diagram.add_block(kind, params, block_id)
        except Exception as error:  # noqa: BLE001
            self.set_status(f"cannot add {kind}: {error}")
            return -1
        position = position or self._next_position()
        self.positions[block] = (int(position[0]), int(position[1]))
        self._make_block_control(block, kind)
        self._place_block(block)
        self._rebuild_links()
        self._schedule_links()
        self.set_status(f"added {kind}")
        return block

    def _make_block_control(self, bid: int, kind: str) -> None:
        block = self.diagram.blocks[bid]
        control = dui.BoxMovable(
            self.canvas, width=str(BLOCK_W), height=str(BLOCK_H),
            bkcolor="#FFFFFFFF", border_round="7,7", border_size="1",
            border_color=BLOCK_BORDER, move_pos_keep_within_parent="true",
            move_pos_reserve_width="20", move_pos_reserve_height="20")
        self.canvas.add_item(control)
        # The default Box layout puts every non-floating child at the top
        # left, which made the title and the parameter line overlap.
        old_layout = control.reset_layout(dui.VLayout())
        if old_layout is not None:
            control.free_layout(old_layout)
        title_row = dui.HBox(control, width="stretch", height="20",
                             bkcolor="#00000000", mouse_enabled="false")
        control.add_item(title_row)
        icon = _icon_path(kind)
        if icon:
            title_row.add_item(dui.Control(
                title_row, width=str(BLOCK_ICON), height=str(BLOCK_ICON),
                bkimage=f"file='{icon}'", margin="5,0,3,0",
                valign="center", mouse_enabled="false"))
        title = dui.Label(
            title_row, text=DISPLAY_TITLES.get(
                kind, getattr(block, "title", kind)),
            width="stretch", height="20", valign="center",
            text_align="hleft,vcenter", font="system_bold_12",
            single_line="true", normal_text_color="#FF1F2328",
            mouse_enabled="false")
        title_row.add_item(title)
        detail = dui.Label(control, text=self._summary_text(block),
                           width="stretch", height="26", font="system_11",
                           normal_text_color="#FF6B7076", single_line="false",
                           text_align="hcenter,top", mouse_enabled="false")
        control.add_item(detail)
        tooltip = self._tooltip_text(block)
        control.set_tooltip_text(tooltip)
        detail.set_tooltip_text(tooltip)
        self._add_ports(control, bid, block)
        control.attach_button_down(
            lambda args, b=bid: (self._press_block(b), True)[1])
        control.attach_click(lambda args, b=bid: (self._click_block(b), True)[1])
        control.attach_double_click(
            lambda args, b=bid: (self._focus_block(b), True)[1])
        control.attach_context_menu(
            lambda args, b=bid: (self._show_block_menu(b), True)[1])
        control.attach_pos_changed(
            lambda args, b=bid: (self._block_moved(b), True)[1])
        self.blocks[bid] = GuiBlock(bid, kind, block, control, title, detail)

    def _add_ports(self, control: Any, bid: int, block: Any) -> None:
        """Draw one dot per port and make them draggable/clickable."""
        for side, count in (("in", block.n_inputs), ("out", block.n_outputs)):
            for index in range(count):
                if count == 1:
                    valign, margin = "center", "0,0,0,0"
                else:
                    # Symmetric vertical spread inside the block.
                    offset = round((BLOCK_H - PORT_SIZE) * (index + 1)
                                   / (count + 1))
                    valign, margin = "top", f"0,{offset},0,0"
                dot = dui.Control(
                    control, name=f"port_{side}_{bid}_{index}",
                    width=str(PORT_SIZE), height=str(PORT_SIZE),
                    border_round=f"{PORT_SIZE // 2},{PORT_SIZE // 2}",
                    bkcolor=PORT_IN if side == "in" else PORT_OUT,
                    float="true", halign="left" if side == "in" else "right",
                    valign=valign, margin=margin)
                control.add_item(dot)
                self.ports[(bid, side, index)] = dot
                dot.attach_context_menu(
                    lambda args, b=bid: (self._show_block_menu(b), True)[1])
                if side == "out":
                    dot.set_tooltip_text(
                        "Drag to a block or to a blue input dot to connect")
                    dot.attach_button_down(
                        lambda args, b=bid: self._begin_link_drag(b))
                    # Swallow the click so it does not bubble to the block and
                    # cancel the click-to-connect state armed on mouse-up.
                    dot.attach_click(lambda args: True)
                else:
                    dot.set_tooltip_text(f"input port {index + 1}")
                    dot.attach_click(
                        lambda args, b=bid, i=index:
                        self._click_input_port(b, i))

    def _port_geometry(self, bid: int, side: str, index: int
                       ) -> tuple[int, int, int] | None:
        """Port centre and size from the block rect, not a stale dot layout.

        During a block drag the child port dots are laid out slightly later
        than the block itself.  Deriving the port position from the block rect
        keeps wires attached and lets them shorten immediately.
        """
        block = self.diagram.blocks.get(bid)
        if block is None:
            return None
        count = block.n_inputs if side == "in" else block.n_outputs
        if count <= 0 or not 0 <= index < count:
            return None
        left, top, right, bottom = self._block_rect(bid)
        size = max(1, round(PORT_SIZE * self._dpi_scale()))
        half = size // 2
        if count <= 1:
            cy = (top + bottom) // 2
        else:
            offset = round((BLOCK_H - PORT_SIZE) * (index + 1)
                           / (count + 1))
            cy = top + round(offset * self._dpi_scale()) + half
        cx = right - half if side == "out" else left + half
        return cx, cy, size

    def _port_rect(self, bid: int, side: str, index: int
                   ) -> tuple[int, int, int, int] | None:
        geometry = self._port_geometry(bid, side, index)
        if geometry is None:
            return None
        cx, cy, size = geometry
        half = size // 2
        return cx - half, cy - half, cx + half, cy + half

    def _port_center(self, bid: int, side: str, index: int
                     ) -> tuple[int, int]:
        geometry = self._port_geometry(bid, side, index)
        if geometry is not None:
            return geometry[0], geometry[1]
        left, top, right, bottom = self._block_rect(bid)
        if side == "out":
            return right, (top + bottom) // 2
        return left, (top + bottom) // 2

    def _output_point(self, bid: int) -> tuple[int, int]:
        return self._port_center(bid, "out", 0)

    def _input_point(self, bid: int, port: int) -> tuple[int, int]:
        return self._port_center(bid, "in", port)

    def _place_block(self, bid: int) -> None:
        if bid not in self.blocks:
            return
        x, y = self.positions.get(bid, (40, 40))
        try:
            cx, cy = self.canvas.get_pos()[0], self.canvas.get_pos()[1]
        except Exception:  # noqa: BLE001
            cx = cy = 0
        if self.canvas.get_pos()[2] - self.canvas.get_pos()[0] <= 0:
            cx = cy = 0
        width, height = self._block_size()
        self.blocks[bid].control.set_pos(
            dui.UiRect(cx + int(x), cy + int(y),
                       cx + int(x) + width, cy + int(y) + height))

    def _apply_positions(self) -> bool:
        if not self._ready:
            return False
        for bid in self.blocks:
            self._place_block(bid)
        self._rebuild_links()
        self._schedule_links()
        return False

    def _schedule_links(self) -> None:
        """Redraw after dui has laid the port dots out for the new position."""
        try:
            dui.set_timer(self._deferred_rebuild_links, 30, 1, owner=self)
        except Exception:  # noqa: BLE001
            pass

    def _deferred_rebuild_links(self) -> bool:
        if self._ready:
            self._rebuild_links()
        return False

    def _press_block(self, bid: int) -> bool:
        """Highlight on mouse-down so a single click is always visible.

        Connect mode is handled here too: relying on the click event made a
        single click feel dead on some machines, so the source/target choice
        happens as soon as the block is pressed.
        """
        self._connect_handled = False
        if bid not in self.blocks:
            return False
        if self.connect_mode or self.connect_source is not None:
            self._connect_handled = True
            self._connect_press(bid)
            return True
        self.selected_link = None
        self.selected = bid
        self._highlight(bid)
        self._param_edit.set_text(
            self._params_text(self.diagram.blocks[bid]))
        return True

    def _connect_press(self, bid: int) -> None:
        if self.connect_source is None:
            self.connect_source = bid
            self.selected_link = None
            self._highlight(bid)
            self._set_mode("connect")
            self.set_status("connect: click a target block or input dot")
        elif self.connect_source == bid:
            self.connect_source = None
            self._highlight(None)
            self._set_mode("connect" if self.connect_mode else "select")
            self.set_status("connect cancelled")
        else:
            self._make_link(self.connect_source, bid, self._free_port(bid))

    def _click_block(self, bid: int) -> bool:
        if self._connect_handled:
            # The mouse-down already handled this click in Connect mode.
            self._connect_handled = False
            return True
        if self.selected_link is not None:
            self.selected_link = None
            self._apply_link_colors()
        if self.connect_mode or self.connect_source is not None:
            if self.connect_source is None:
                self.connect_source = bid
                self._highlight(bid)
                self._set_mode("connect")
                self.set_status("connect: click a target block or input dot")
            elif self.connect_source == bid:
                self.connect_source = None
                self._highlight(None)
                self._set_mode("select")
                self.set_status("connect cancelled")
            else:
                self._make_link(self.connect_source, bid, self._free_port(bid))
            return True
        # A single click selects the block and puts its parameters straight
        # into the edit box; double-click still does the same thing.
        return self._focus_block(bid)

    def _make_link(self, source: int, target: int, port: int) -> None:
        try:
            self.diagram.connect(source, target, port)
            self.set_status(f"linked {source} → {target}.{port}")
        except Exception as error:  # noqa: BLE001
            self.set_status(f"cannot link: {error}")
        self.connect_source = None
        self._link_drag = None
        self.selected_link = None
        self._highlight(None)
        self._set_mode("connect" if self.connect_mode else "select")
        self._rebuild_links()

    def _free_port(self, target: int) -> int:
        block = self.diagram.blocks[target]
        used = {link.port for link in self.diagram.links if link.target == target}
        for port in range(block.n_inputs):
            if port not in used:
                return port
        return 0

    def _set_mode(self, text: str) -> None:
        try:
            self._mode.set_text(text)
        except Exception:  # noqa: BLE001
            pass

    # -- palette drag ------------------------------------------------------
    def _begin_palette_drag(self, kind: str) -> bool:
        if self._link_drag is not None:
            self._cancel_link_drag()
        point = self._mouse_point() or (0, 0)
        self._wire_drag = None
        self._palette_drag = {
            "kind": kind, "start": point, "x": point[0], "y": point[1],
            "active": True,
        }
        self._create_ghost(kind)
        self._move_ghost(point)
        self.set_status(f"drag {kind} onto the canvas")
        return True

    def _create_ghost(self, kind: str) -> None:
        self._remove_ghost()
        ghost = dui.Box(
            self.root, width=str(BLOCK_W), height=str(BLOCK_H),
            bkcolor="#E6F0F6FF", border_size="2",
            border_color=BLOCK_SELECTED_BORDER, border_round="7,7",
            float="true", halign="left", valign="top",
            margin="0,0,0,0", mouse_enabled="false")
        old_layout = ghost.reset_layout(dui.VLayout())
        if old_layout is not None:
            ghost.free_layout(old_layout)
        title_row = dui.HBox(ghost, width="stretch", height="20",
                             bkcolor="#00000000", mouse_enabled="false")
        ghost.add_item(title_row)
        icon = _icon_path(kind)
        if icon:
            title_row.add_item(dui.Control(
                title_row, width=str(BLOCK_ICON), height=str(BLOCK_ICON),
                bkimage=f"file='{icon}'", margin="5,0,3,0",
                valign="center", mouse_enabled="false"))
        title_row.add_item(dui.Label(
            title_row, text=DISPLAY_TITLES.get(kind, kind),
            width="stretch", height="20", valign="center",
            text_align="hleft,vcenter", font="system_bold_12",
            single_line="true", normal_text_color="#FF1F2328",
            mouse_enabled="false"))
        try:
            from .blocks import make_block
            detail_text = self._summary_text(
                make_block(kind, dict(BLOCK_DEFAULTS.get(kind, {}))))
        except Exception:  # noqa: BLE001
            detail_text = ""
        ghost.add_item(dui.Label(
            ghost, text=detail_text, width="stretch", height="26",
            font="system_11", normal_text_color="#FF6B7076",
            single_line="false", text_align="hcenter,top",
            mouse_enabled="false"))
        self.root.add_item(ghost)
        self._ghost = ghost

    def _move_ghost(self, point: tuple[int, int]) -> None:
        if self._ghost is None:
            return
        scale = self._dpi_scale()
        width, height = self._block_size()
        left = max(0, round((point[0] - width // 2) / scale))
        top = max(0, round((point[1] - height // 2) / scale))
        self._ghost.set_attribute("margin", f"{left},{top},0,0")

    def _remove_ghost(self) -> None:
        if self._ghost is None:
            return
        try:
            self.root.remove_item(self._ghost)
        except Exception:  # noqa: BLE001
            pass
        self._ghost = None

    def _point_in_canvas(self, point: tuple[int, int]) -> bool:
        try:
            left, top, right, bottom = self.canvas_view.get_pos()
        except Exception:  # noqa: BLE001
            return False
        return left <= point[0] <= right and top <= point[1] <= bottom

    def _drop_position(self, point: tuple[int, int]) -> tuple[int, int]:
        canvas_point = self._canvas_point(point) or point
        try:
            left, top = self.canvas.get_pos()[0], self.canvas.get_pos()[1]
        except Exception:  # noqa: BLE001
            left = top = 0
        width, height = self._block_size()
        return (max(4, int(canvas_point[0] - left - width // 2)),
                max(4, int(canvas_point[1] - top - height // 2)))

    def _finish_palette_drag(self) -> bool:
        drag = self._palette_drag
        self._palette_drag = None
        point = self._mouse_point()
        active = bool(drag and drag["active"])
        self._remove_ghost()
        if active and point is not None and self._point_in_canvas(point):
            self.add_block(drag["kind"], position=self._drop_position(point))
            self._set_mode("select")
        return True

    # -- context menus -----------------------------------------------------
    def _show_context_menu(self, items: list) -> None:
        if self._menu is not None:
            try:
                self._menu.close()
            except Exception:  # noqa: BLE001
                pass
            self._menu = None
        point = self._mouse_point() or (0, 0)
        screen = dui.UiPoint(point[0], point[1])
        self.client_to_screen(screen)
        menu = dui.Menu(self, self.canvas)
        self._menu = menu
        # Shown before adding items, so dui measures the menu after they exist.
        menu.show_menu("", screen.x, screen.y)
        for entry in items:
            if entry is None:
                separator = dui.Control(menu, class_="menu_split_line",
                                        width="160", height="1")
                menu.add_menu_control(separator)
                continue
            text, handler = entry
            item = dui.MenuItem(menu, class_="menu_element", text=text)
            item.set_fixed_width(dui.UiFixedInt(170), True, True)
            item.attach_click(lambda args, h=handler: (h(), True)[1])
            menu.add_menu_item(item)

    def _show_block_menu(self, bid: int) -> bool:
        if bid not in self.blocks:
            return True
        self.selected = bid
        self.selected_link = None
        self._highlight(bid)
        block = self.diagram.blocks[bid]
        self._param_edit.set_text(self._params_text(block))
        items = [
            ("Edit parameters", lambda: self._focus_block(bid)),
            ("Duplicate block", lambda: self._duplicate_block(bid)),
            ("Disconnect wires", lambda: self._disconnect_block(bid)),
            None,
            ("Delete block", lambda: self._delete_block(bid)),
        ]
        self._rebuild_links()
        self._show_context_menu(items)
        return True

    def _show_link_menu(self, key: tuple[int, int, int]) -> bool:
        self._select_link(key)
        self._show_context_menu([
            ("Delete connection", lambda: self._delete_link(key)),
        ])
        return True

    def _apply_link_colors(self) -> None:
        highlighted = set()
        if self.selected_link is not None:
            highlighted.add(self.selected_link)
        if self.selected is not None:
            for link in self.diagram.links:
                if (link.source == self.selected
                        or link.target == self.selected):
                    highlighted.add((link.source, link.target, link.port))
        for control, key in self._line_items:
            try:
                control.set_bk_color(
                    LINK_SELECTED if key in highlighted else LINK_COLOR)
            except Exception:  # noqa: BLE001
                pass

    def _select_link(self, key: tuple[int, int, int]) -> bool:
        if not any((link.source, link.target, link.port) == key
                   for link in self.diagram.links):
            return False
        self.selected = None
        self.selected_link = key
        self._highlight(None)
        self._apply_link_colors()
        self.set_status(
            f"connection {key[0]} → {key[1]}.{key[2]} selected "
            "(drag up/down, right-click to delete)")
        return True

    def _begin_wire_drag(self, key: tuple[int, int, int],
                         orientation: str = "h") -> bool:
        if not self._select_link(key):
            return False
        point = self._canvas_point(self._mouse_point()) or (0, 0)
        self._wire_drag = {
            "key": key, "start": point, "dragged": False,
            "orientation": orientation,
        }
        direction = "up/down" if orientation == "h" else "left/right"
        self.set_status(
            f"drag the wire {direction} to move connection "
            f"{key[0]} → {key[1]}.{key[2]}")
        return True

    def _delete_link(self, key: tuple[int, int, int]) -> bool:
        self.diagram.disconnect(*key)
        self.link_lanes.pop(key, None)
        self.link_columns.pop(key, None)
        if self.selected_link == key:
            self.selected_link = None
        self._highlight(None)
        self._rebuild_links()
        self.set_status(f"deleted connection {key[0]} → {key[1]}.{key[2]}")
        return True

    def _prune_link_lanes(self) -> None:
        valid = {(link.source, link.target, link.port)
                 for link in self.diagram.links}
        self.link_lanes = {key: lane for key, lane in self.link_lanes.items()
                           if key in valid}
        self.link_columns = {
            key: columns for key, columns in self.link_columns.items()
            if key in valid}

    def _duplicate_block(self, bid: int) -> bool:
        block = self.diagram.blocks.get(bid)
        if block is None:
            return True
        params = dict(block.params)
        offset = round(24 * self._dpi_scale())
        x, y = self.positions.get(bid, (28, 28))
        new_id = self.add_block(block.kind, params,
                                position=(x + offset, y + offset))
        if new_id > 0:
            self.selected = new_id
            self._highlight(new_id)
            self.set_status(f"duplicated {block.kind} as block {new_id}")
        return True

    def _disconnect_block(self, bid: int) -> bool:
        before = len(self.diagram.links)
        self.diagram.links = [link for link in self.diagram.links
                              if link.source != bid and link.target != bid]
        self._prune_link_lanes()
        self.selected_link = None
        self._highlight(None)
        self._rebuild_links()
        self.set_status(
            f"removed {before - len(self.diagram.links)} connection(s)")
        return True

    def _delete_block(self, bid: int) -> bool:
        gui = self.blocks.get(bid)
        if gui is None:
            return True
        self.blocks.pop(bid, None)
        try:
            self.canvas.remove_item(gui.control)
        except Exception:  # noqa: BLE001
            pass
        self._drop_ports(bid)
        self.diagram.remove_block(bid)
        self._prune_link_lanes()
        self.positions.pop(bid, None)
        if self.selected == bid:
            self.selected = None
        if self.connect_source == bid:
            self.connect_source = None
        if self._link_drag is not None and self._link_drag["source"] == bid:
            self._link_drag = None
        if self.selected_link is not None:
            self.selected_link = None
        self._highlight(None)
        self._rebuild_links()
        self.set_status(f"deleted block {bid}")
        return True

    def _summary_text(self, block: Any, limit: int = 22) -> str:
        """A short line for the block face; the tooltip keeps the full text."""
        kind = block.kind
        if kind == "TransferFunction":
            text = f"order {max(0, len(block.den) - 1)}"
        elif kind == "StateSpace":
            text = f"order {block.n_states}"
        elif kind == "PID":
            text = f"Kp={block.kp:g} Ki={block.ki:g} Kd={block.kd:g}"
        elif kind == "Step":
            text = f"t={block.time:g} {block.before:g}→{block.after:g}"
        elif kind == "Sine":
            text = f"{block.amplitude:g} sin {block.frequency:g}Hz"
        elif kind == "Ramp":
            text = f"m={block.slope:g}"
        elif kind == "Terminator":
            text = ""
        elif kind == "Saturation":
            text = f"[{block.lower:g}, {block.upper:g}]"
        elif kind == "Sum":
            text = block.signs
        elif kind == "Scope":
            text = ""
        else:
            text = block.display_params()
        text = " ".join(str(text).split())
        if len(text) > limit:
            text = text[:max(1, limit - 1)] + "…"
        return text

    def _tooltip_text(self, block: Any) -> str:
        lines = [block.kind]
        for key, value in block.params.items():
            if key == "name":
                continue
            text = str(value)
            if len(text) > 100:
                text = text[:99] + "…"
            lines.append(f"{key} = {text}")
        if len(lines) == 1:
            lines.extend(block.display_params().splitlines() or [""])
        return "\n".join(line for line in lines if line)

    def _params_text(self, block: Any) -> str:
        parts = []
        for key, value in block.params.items():
            if key == "name":
                continue
            parts.append(f"{key}={value!r}")
        return "; ".join(parts)

    def _parse_params(self, text: str) -> dict:
        params: dict[str, Any] = {}
        for piece in (text or "").split(";"):
            piece = piece.strip()
            if not piece or "=" not in piece:
                continue
            key, value = piece.split("=", 1)
            key = key.strip()
            value = value.strip()
            try:
                params[key] = eval(value, {"__builtins__": {}}, {"np": np})
            except Exception:  # noqa: BLE001
                params[key] = value
        return params

    def _focus_block(self, bid: int) -> bool:
        block = self.diagram.blocks[bid]
        self.selected = bid
        self._highlight(bid)
        self._param_edit.set_text(self._params_text(block))
        self._param_edit.set_focus()
        try:
            self._param_edit.set_sel_all()
        except Exception:  # noqa: BLE001
            pass
        self.set_status(f"editing {block.kind} parameters — press Apply")
        return True

    def on_apply_params(self, args: Any = None) -> bool:
        if self.selected is None:
            self.set_status("select a block first")
            return True
        bid = self.selected
        old = self.diagram.blocks.get(bid)
        if old is None:
            return True
        params = self._parse_params(self._param_edit.get_text_a())
        try:
            from .blocks import make_block
            replacement = make_block(old.kind, params)
        except Exception as error:  # noqa: BLE001
            self.set_status(f"bad parameters: {error}")
            return True
        self.diagram.blocks[bid] = replacement
        gui = self.blocks[bid]
        gui.block = replacement
        gui.detail.set_text(self._summary_text(replacement) or " ")
        tooltip = self._tooltip_text(replacement)
        gui.control.set_tooltip_text(tooltip)
        gui.detail.set_tooltip_text(tooltip)
        if (old.n_inputs, old.n_outputs) != (replacement.n_inputs,
                                             replacement.n_outputs):
            # Sum(signs=...) and StateSpace can change their port count.
            self._drop_ports(bid, remove=True)
            self._add_ports(gui.control, bid, replacement)
            self._schedule_links()
        self.set_status(f"{old.kind}: {replacement.display_params()}")
        return True

    def _highlight(self, bid: int | None) -> None:
        highlighted = set()
        if bid is not None:
            highlighted.add(bid)
        if self.selected_link is not None:
            highlighted.add(self.selected_link[0])
            highlighted.add(self.selected_link[1])
        for key, gui in self.blocks.items():
            selected = key in highlighted
            gui.control.set_attribute(
                "border_color",
                BLOCK_SELECTED_BORDER if selected else BLOCK_BORDER)
            gui.control.set_attribute("border_size", "2" if selected else "1")
            gui.control.set_attribute(
                "bkcolor", BLOCK_SELECTED_BG if selected else "#FFFFFFFF")
        self._apply_link_colors()

    def _block_moved(self, bid: int) -> bool:
        gui = self.blocks.get(bid)
        if gui is not None:
            try:
                c = self.canvas.get_pos()
                p = gui.control.get_pos()
                self.positions[bid] = (p[0] - c[0], p[1] - c[1])
            except Exception:  # noqa: BLE001
                pass
        # Manual bends are absolute coordinates.  Once an endpoint moves,
        # keeping them makes the wire loop around instead of shortening.
        for link in self.diagram.links:
            if link.source == bid or link.target == bid:
                key = (link.source, link.target, link.port)
                self.link_lanes.pop(key, None)
                self.link_columns.pop(key, None)
        self._rebuild_links()
        self._schedule_links()
        return True

    # ------------------------------------------------------------------
    # Links
    # ------------------------------------------------------------------
    def _block_rect(self, bid: int) -> tuple[int, int, int, int]:
        p = self.blocks[bid].control.get_pos()
        return p[0], p[1], p[2], p[3]

    def _block_at(self, x: int, y: int, exclude: int | None = None
                  ) -> int | None:
        """The topmost block containing a client point, if any."""
        for bid in reversed(list(self.blocks)):
            if bid == exclude:
                continue
            try:
                left, top, right, bottom = self._block_rect(bid)
            except Exception:  # noqa: BLE001
                continue
            if left <= x <= right and top <= y <= bottom:
                return bid
        return None

    def _hit_port(self, x: int, y: int, side: str | None = None,
                  exclude: int | None = None
                  ) -> tuple[int, str, int] | None:
        tolerance = 6
        for bid, port_side, index in self.ports:
            if side is not None and port_side != side:
                continue
            if exclude is not None and bid == exclude:
                continue
            rect = self._port_rect(bid, port_side, index)
            if rect is None:
                continue
            if (rect[0] - tolerance <= x <= rect[2] + tolerance
                    and rect[1] - tolerance <= y <= rect[3] + tolerance):
                return bid, port_side, index
        return None

    def _target_port(self, x: int, y: int, exclude: int | None = None
                     ) -> tuple[int | None, int | None]:
        """Resolve a drop point to (block id, input port index)."""
        hit = self._hit_port(x, y, "in", exclude)
        if hit is not None:
            return hit[0], hit[2]
        bid = self._block_at(x, y, exclude)
        if bid is None:
            return None, None
        block = self.diagram.blocks[bid]
        if block.n_inputs <= 0:
            return None, None
        used = {link.port for link in self.diagram.links
                if link.target == bid}
        free = [index for index in range(block.n_inputs) if index not in used]
        candidates = free or list(range(block.n_inputs))

        def distance(index: int) -> int:
            px, py = self._port_center(bid, "in", index)
            return abs(y - py) * 4 + abs(x - px)

        return bid, min(candidates, key=distance)

    def _path_clear(self, points: list[tuple[int, int]],
                    obstacles: list[tuple[int, int, int, int]],
                    pad: int = 8) -> bool:
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            if abs(x1 - x2) <= 1 and abs(y1 - y2) <= 1:
                continue
            horizontal = abs(x1 - x2) >= abs(y1 - y2)
            for left, top, right, bottom in obstacles:
                l, t = left - pad, top - pad
                r, b = right + pad, bottom + pad
                if horizontal:
                    if (min(y1, y2) < b and max(y1, y2) > t
                            and max(x1, x2) > l and min(x1, x2) < r):
                        return False
                else:
                    if (min(x1, x2) < r and max(x1, x2) > l
                            and max(y1, y2) > t and min(y1, y2) < b):
                        return False
        return True

    def _link_path(self, source: int, target: int, port: int
                   ) -> list[tuple[int, int]]:
        sx, sy = self._output_point(source)
        tx, ty = self._input_point(target, port)
        key = (source, target, port)
        stub = 20
        lane = self.link_lanes.get(key)
        columns = self.link_columns.get(key)
        if columns is not None:
            c1, c2 = columns
            if lane is None:
                # A single vertical channel is enough while only the
                # left/right position has been adjusted.
                return [(sx, sy), (c1, sy), (c1, ty), (tx, ty)]
            if c1 == c2:
                c2 = tx - stub
            return [(sx, sy), (c1, sy), (c1, lane),
                    (c2, lane), (c2, ty), (tx, ty)]
        if lane is not None:
            return [(sx, sy), (sx + stub, sy), (sx + stub, lane),
                    (tx - stub, lane), (tx - stub, ty), (tx, ty)]
        obstacles = [self._block_rect(bid) for bid in self.blocks
                     if bid not in (source, target)]
        if tx > sx:
            midx = (sx + tx) // 2
            direct = [(sx, sy), (midx, sy), (midx, ty), (tx, ty)]
            if self._path_clear(direct, obstacles):
                return direct
        span = [rect for rect in obstacles
                if rect[0] < max(sx, tx) and rect[2] > min(sx, tx)]
        base = span or obstacles
        ys = [sy, ty] + [rect[1] for rect in base] + \
             [rect[3] for rect in base]
        lanes = (min(ys) - stub, max(ys) + stub)

        def route(lane: int) -> list[tuple[int, int]]:
            return [(sx, sy), (sx + stub, sy), (sx + stub, lane),
                    (tx - stub, lane), (tx - stub, ty), (tx, ty)]

        def length(path: list[tuple[int, int]]) -> int:
            return sum(abs(x2 - x1) + abs(y2 - y1)
                       for (x1, y1), (x2, y2) in zip(path, path[1:]))

        paths = [(length(path), self._path_clear(path, obstacles), path)
                 for path in (route(lanes[0]), route(lanes[1]))]
        clear = [entry for entry in paths if entry[1]]
        chosen = min(clear or paths, key=lambda entry: entry[0])
        return chosen[2]

    def _segment(self, x1: int, y1: int, x2: int, y2: int,
                 color: str = LINK_COLOR, thickness: int = LINE_WIDTH,
                 link_key: tuple[int, int, int] | None = None) -> None:
        if abs(x1 - x2) <= 1 and abs(y1 - y2) <= 1:
            return
        pad = max(1, thickness // 2)
        if abs(x1 - x2) >= abs(y1 - y2):
            # Horizontal: give the control a real height. A zero-height
            # rectangle paints nothing, which used to make links invisible.
            left, top = min(x1, x2), min(y1, y2) - pad
            right, bottom = max(x1, x2) + 1, max(y1, y2) + pad + 1
        else:
            left, top = min(x1, x2) - pad, min(y1, y2)
            right, bottom = max(x1, x2) + pad + 1, max(y1, y2) + 1
        # set_pos on a freshly rebuilt linker layer is undone by the next
        # layout pass, so express the segment with layout attributes instead:
        # width/height and margin are all in logical points (DPI scaled).
        scale = self._dpi_scale()
        try:
            layer = self.link_layer.get_pos()
            origin_x, origin_y = layer[0], layer[1]
        except Exception:  # noqa: BLE001
            origin_x = origin_y = 0
        left_attr = max(0, round((left - origin_x) / scale))
        top_attr = max(0, round((top - origin_y) / scale))
        width_attr = max(1, round((right - left) / scale))
        height_attr = max(1, round((bottom - top) / scale))
        line = dui.Control(
            self.link_layer, name="link_segment", bkcolor=color,
            float="true",
            mouse_enabled="true" if link_key is not None else "false",
            width=str(width_attr), height=str(height_attr),
            halign="left", valign="top",
            margin=f"{left_attr},{top_attr},0,0")
        self.link_layer.add_item(line)
        if link_key is not None:
            orientation = "h" if abs(x1 - x2) >= abs(y1 - y2) else "v"
            line.set_tooltip_text(
                "click to select · drag up/down or left/right · right-click")
            line.attach_click(
                lambda args, k=link_key: (self._select_link(k), True)[1])
            line.attach_button_down(
                lambda args, k=link_key, o=orientation:
                self._begin_wire_drag(k, o))
            line.attach_context_menu(
                lambda args, k=link_key: (self._show_link_menu(k), True)[1])
            self._line_items.append((line, link_key))
            # The visible line is only one or two pixels thick, so clicks are
            # also resolved against these rects with a tolerance on the canvas.
            self._segment_hits.append(
                (left, top, right, bottom, link_key, orientation))

    def _orthogonal(self, sx: int, sy: int, tx: int, ty: int,
                    color: str = LINK_COLOR,
                    link_key: tuple[int, int, int] | None = None,
                    thickness: int = LINE_WIDTH) -> None:
        midx = (sx + tx) // 2
        if tx < sx:
            midx = max(sx, tx) + 24
        self._segment(sx, sy, midx, sy, color, thickness, link_key)
        self._segment(midx, sy, midx, ty, color, thickness, link_key)
        self._segment(midx, ty, tx, ty, color, thickness, link_key)

    def _rebuild_links(self) -> None:
        self._segment_hits = []
        self._line_items = []
        try:
            self.link_layer.remove_all_items()
        except Exception:  # noqa: BLE001
            return
        for link in self.diagram.links:
            if link.source not in self.blocks or link.target not in self.blocks:
                continue
            key = (link.source, link.target, link.port)
            selected = key == self.selected_link
            path = self._link_path(link.source, link.target, link.port)
            for (x1, y1), (x2, y2) in zip(path, path[1:]):
                self._segment(
                    x1, y1, x2, y2,
                    color=LINK_SELECTED if selected else LINK_COLOR,
                    thickness=LINE_WIDTH, link_key=key)
        if self._link_drag is not None:
            source = self._link_drag["source"]
            if source in self.blocks:
                sx, sy = self._output_point(source)
                self._orthogonal(sx, sy, self._link_drag["x"],
                                 self._link_drag["y"], LINK_PREVIEW)

    # -- manual connection -------------------------------------------------
    def _mouse_point(self) -> tuple[int, int] | None:
        try:
            point = self.get_last_mouse_pos()
            return int(point.x), int(point.y)
        except Exception:  # noqa: BLE001
            return None

    def _canvas_scroll(self) -> tuple[int, int]:
        try:
            pos = self.canvas_view.get_scroll_pos()
            return int(pos.cx), int(pos.cy)
        except Exception:  # noqa: BLE001
            return 0, 0

    def _canvas_point(self, point: tuple[int, int] | None
                      ) -> tuple[int, int] | None:
        if point is None:
            return None
        sx, sy = self._canvas_scroll()
        return point[0] + sx, point[1] + sy

    def _begin_link_drag(self, bid: int, args: Any = None) -> bool:
        """Start dragging a wire from a block's output dot."""
        if bid not in self.blocks:
            return False
        if self.diagram.blocks[bid].n_outputs == 0:
            self.set_status("this block has no output port")
            return True
        self.connect_source = None
        sx, sy = self._output_point(bid)
        self._link_drag = {"source": bid, "x": sx, "y": sy}
        self._highlight(bid)
        self._set_mode("connect")
        self.set_status("drag to a block or a blue input dot, then release")
        self._rebuild_links()
        return True

    def _on_window_mouse_move(self, args: Any = None) -> bool:
        if self._palette_drag is not None:
            point = self._mouse_point()
            if point is not None:
                self._palette_drag["x"], self._palette_drag["y"] = point
                self._move_ghost(point)
            return True
        if self._wire_drag is not None:
            point = self._canvas_point(self._mouse_point())
            if point is not None:
                drag = self._wire_drag
                orientation = drag.get("orientation", "h")
                key = drag["key"]
                if orientation == "h":
                    if abs(point[1] - drag["start"][1]) >= 2:
                        drag["dragged"] = True
                        self.link_lanes[key] = point[1]
                        self._rebuild_links()
                else:
                    if abs(point[0] - drag["start"][0]) >= 2:
                        drag["dragged"] = True
                        if key not in self.link_lanes:
                            self.link_columns[key] = (point[0], point[0])
                        else:
                            sx, _ = self._output_point(key[0])
                            tx, _ = self._input_point(key[1], key[2])
                            c1, c2 = self.link_columns.get(
                                key, (sx + 20, tx - 20))
                            if point[0] <= (c1 + c2) // 2:
                                c1 = point[0]
                            else:
                                c2 = point[0]
                            self.link_columns[key] = (c1, c2)
                        self._rebuild_links()
            return True
        if self._link_drag is None:
            return False
        point = self._canvas_point(self._mouse_point())
        if point is not None:
            self._link_drag["x"], self._link_drag["y"] = point
            self._rebuild_links()
        return True

    def _on_window_mouse_up(self, args: Any = None) -> bool:
        if self._palette_drag is not None:
            return self._finish_palette_drag()
        if self._wire_drag is not None:
            drag = self._wire_drag
            self._wire_drag = None
            if drag.get("dragged"):
                key = drag["key"]
                self.set_status(
                    f"moved connection {key[0]} → {key[1]}.{key[2]}")
            return True
        if self._link_drag is None:
            return False
        point = self._canvas_point(self._mouse_point())
        if point is None:
            self._cancel_link_drag()
            return True
        return self._finish_link_at(point[0], point[1])

    def _finish_link_at(self, x: int, y: int) -> bool:
        drag = self._link_drag
        self._link_drag = None
        if drag is None:
            return False
        source = drag["source"]
        target, port = self._target_port(x, y, exclude=source)
        if target is None:
            hit = self._hit_port(x, y, "out")
            if hit is not None and hit[0] == source:
                # A click (not a drag) on the output dot arms click-to-connect.
                self.connect_source = source
                self._highlight(source)
                self._set_mode("connect")
                self.set_status("connect: click a target block or input dot")
            else:
                self._cancel_link_drag()
            return True
        self._make_link(source, target, int(port))
        return True

    def _cancel_link_drag(self) -> None:
        self._link_drag = None
        self.connect_source = None
        self._highlight(None)
        self._set_mode("connect" if self.connect_mode else "select")
        self.set_status("connection cancelled")
        self._rebuild_links()

    def _hit_segment(self, point: tuple[int, int], tolerance: int = 7):
        x, y = point
        for entry in reversed(self._segment_hits):
            left, top, right, bottom = entry[:4]
            if (left - tolerance <= x <= right + tolerance
                    and top - tolerance <= y <= bottom + tolerance):
                return entry
        return None

    def _hit_link(self, point: tuple[int, int],
                  tolerance: int = 7) -> tuple[int, int, int] | None:
        entry = self._hit_segment(point, tolerance)
        return entry[4] if entry is not None else None

    def _on_canvas_button_down(self, args: Any = None) -> bool:
        if self._link_drag is not None or self.connect_source is not None:
            return False
        point = self._canvas_point(self._mouse_point())
        if point is None:
            return False
        entry = self._hit_segment(point)
        if entry is None:
            return False
        return self._begin_wire_drag(entry[4], entry[5])

    def _on_canvas_click(self, args: Any = None) -> bool:
        if self._link_drag is not None or self.connect_source is not None:
            self._cancel_link_drag()
            return True
        point = self._canvas_point(self._mouse_point())
        if point is not None:
            key = self._hit_link(point)
            if key is not None:
                return self._select_link(key)
        if self.selected_link is not None:
            self.selected_link = None
            self._highlight(None)
            self.set_status("connection deselected")
            return True
        return False

    def _on_canvas_context_menu(self, args: Any = None) -> bool:
        point = self._canvas_point(self._mouse_point())
        if point is None:
            return False
        key = self._hit_link(point)
        if key is None:
            return False
        return self._show_link_menu(key)

    def _click_input_port(self, bid: int, port: int) -> bool:
        if bid not in self.blocks:
            return True
        if self.connect_source is None:
            self.selected = bid
            self._highlight(bid)
            block = self.diagram.blocks[bid]
            self._param_edit.set_text(self._params_text(block))
            self.set_status("drag from a green output dot to this input port")
            return True
        if self.connect_source == bid:
            self.set_status("source and target are the same block")
            return True
        self._make_link(self.connect_source, bid, port)
        return True

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def on_toggle_connect(self, args: Any = None) -> bool:
        self.connect_mode = not self.connect_mode
        self.connect_source = None
        self._connect_handled = False
        self.selected_link = None
        self._link_drag = None
        self._set_mode("connect" if self.connect_mode else "select")
        self._highlight(None)
        self.set_status("Connect mode: click source, then target"
                        if self.connect_mode else "Select mode")
        self._rebuild_links()
        return True

    def on_delete(self, args: Any = None) -> bool:
        if self.selected is None:
            if self.selected_link is not None:
                return self._delete_link(self.selected_link)
            self.set_status("no block or connection selected")
            return True
        self.connect_source = None
        self._link_drag = None
        return self._delete_block(self.selected)

    def on_clear(self, args: Any = None) -> bool:
        for gui in list(self.blocks.values()):
            try:
                self.canvas.remove_item(gui.control)
            except Exception:  # noqa: BLE001
                pass
        self.blocks.clear()
        self.positions.clear()
        self.ports.clear()
        self.link_lanes.clear()
        self.link_columns.clear()
        self.diagram.clear()
        self.selected = None
        self.selected_link = None
        self.connect_source = None
        self._link_drag = None
        self._palette_drag = None
        self._remove_ghost()
        self._rebuild_links()
        self.set_status("diagram cleared")
        return True

    def _drop_ports(self, bid: int, remove: bool = False) -> None:
        gui = self.blocks.get(bid)
        for key in [key for key in self.ports if key[0] == bid]:
            dot = self.ports.pop(key, None)
            if remove and gui is not None and dot is not None:
                try:
                    gui.control.remove_item(dot)
                except Exception:  # noqa: BLE001
                    pass

    def on_run(self, args: Any = None) -> bool:
        if not self.diagram.blocks:
            self.set_status("add blocks first")
            return True
        try:
            t_final = float(self._time_edit.get_text_a() or "10")
        except ValueError:
            t_final = 10.0
        try:
            result = self.diagram.simulate(t_final=max(0.01, t_final), points=1200)
        except (AlgebraicLoopError, RuntimeError, ValueError) as error:
            self.set_status(f"simulation error: {error}")
            dui.show_message_box(str(error), "pysimu simulation error")
            return True
        import matplotlib.pyplot as plt

        plt.close("all")
        figure = plt.figure()
        axis = figure.add_subplot(111)
        plotted = False
        for bid, signal in result.scope_data():
            axis.plot(result.t, signal, label=f"Scope {bid}")
            plotted = True
        if not plotted:
            for bid, signal in result.signals.items():
                block = self.diagram.blocks[bid]
                if block.n_outputs:
                    axis.plot(result.t, signal, label=block.name)
                    plotted = True
        if not plotted:
            self.set_status("nothing to plot (add a Scope)")
            return True
        axis.set_xlabel("time (s)")
        axis.set_ylabel("value")
        axis.set_title("pysimu simulation")
        axis.grid(True, alpha=0.3)
        axis.legend()
        plt.show()
        self.set_status(f"simulated {t_final:g}s")
        return True

    def on_save(self, args: Any = None) -> bool:
        default = os.path.join(self.project_path, "pysimu_diagram.json")
        path = dui.save_file(self, [("pysimu diagram", "*.json")], "json",
                             file_name="pysimu_diagram.json",
                             start_dir=self.project_path)
        if not path:
            return True
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.diagram.to_dict(self.positions), handle,
                          indent=2)
            self.project_path = os.path.dirname(path) or self.project_path
            self.set_status(f"saved {path}")
        except OSError as error:
            self.set_status(f"save failed: {error}")
        return True

    def on_load(self, args: Any = None) -> bool:
        path = dui.open_file(self, [("pysimu diagram", "*.json")], "json",
                             start_dir=self.project_path)
        if not path:
            return True
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as error:
            self.set_status(f"load failed: {error}")
            return True
        self._load_data(data)
        self.set_status(f"loaded {path}")
        return True

    def _load_or_demo(self) -> None:
        path = os.path.join(self.project_path, "pysimu_diagram.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    self._load_data(json.load(handle))
                self.set_status(f"loaded {path}")
                return
            except (OSError, ValueError):
                pass
        # Start with an empty canvas.  Previously a demo diagram was inserted
        # here, which made newly added blocks look randomly wired to it.
        self.set_status("empty diagram — click or drag a block from the library")

    def _load_data(self, data: dict) -> None:
        diagram = Diagram.from_dict(data)
        positions = {}
        for entry in data.get("blocks", []):
            pos = entry.get("position")
            if pos and len(pos) == 2:
                positions[int(entry["id"])] = (int(pos[0]), int(pos[1]))
        self._load_diagram(diagram, positions)

    def _load_diagram(self, diagram: Diagram,
                      positions: dict[int, tuple[int, int]]) -> None:
        for gui in list(self.blocks.values()):
            try:
                self.canvas.remove_item(gui.control)
            except Exception:  # noqa: BLE001
                pass
        self.blocks.clear()
        self.positions.clear()
        self.ports.clear()
        self.link_lanes.clear()
        self.link_columns.clear()
        self.diagram = diagram
        self.selected_link = None
        self.connect_source = None
        self._link_drag = None
        self._palette_drag = None
        self._remove_ghost()
        for index, bid in enumerate(sorted(diagram.blocks)):
            self.positions[bid] = positions.get(bid, self._next_position())
            self._make_block_control(bid, diagram.blocks[bid].kind)
        self._apply_positions()
        self._rebuild_links()

    # ------------------------------------------------------------------
    def fit_to_work_area(self) -> None:
        work = dui.UiRect()
        if not self.get_monitor_work_rect(work):
            return
        window = dui.UiRect()
        self.get_window_rect(window)
        width, height = window.right - window.left, window.bottom - window.top
        work_w, work_h = work.right - work.left, work.bottom - work.top
        margin = 18
        width = min(width, max(800, work_w - 2 * margin))
        height = min(height, max(560, work_h - 2 * margin))
        x = work.left + max(0, (work_w - width) // 2)
        y = work.top + max(0, (work_h - height) // 2)
        self.move_window(int(x), int(y), int(width), int(height), True)

    def _on_window_close(self, args: Any = None) -> bool:
        self._ready = False
        if getattr(self.app, "pysimu_window", None) is self:
            self.app.pysimu_window = None
        return True

    def set_status(self, text: str) -> None:
        self._status.set_text(text)

    def raise_and_focus(self) -> None:
        self.show_window()
        self.set_window_focus()
