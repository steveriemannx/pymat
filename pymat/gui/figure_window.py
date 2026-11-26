"""A window showing one matplotlib figure.

matplotlib draws to a PNG with the Agg backend, and the window paints that PNG as
a background image.  Re-rendering on resize keeps the plot sharp: the image is
rendered at the control's device-pixel size and drawn 1:1.
"""

from __future__ import annotations

import os
from typing import Any

import dui

from .. import mpl
from . import theme


class FigureWindow(dui.WindowImplBase):
    def __init__(self, figure: mpl.FigureClass) -> None:
        super().__init__()
        self.figure = figure
        self.number = int(figure.number)
        self._ready = False
        self._closing = False
        self._resize_timer = 0

    def on_init_window(self) -> None:
        self.set_native_fullscreen(True)
        self.set_window_size(920, 660)
        self.center_window()
        label = self.figure.get_label() or f"Figure {self.number}"
        name = label if not label.startswith("_") else f"Figure {self.number}"

        root = dui.VBox(self, bkcolor=theme.WINDOW_BG)
        caption = dui.HBox(self, name="window_caption_bar", height="34",
                           bkcolor=theme.CAPTION_BG)
        caption.add_item(dui.Label(self, text="Figure", font="system_bold_12",
                                   normal_text_color=theme.ACCENT, valign="center",
                                   margin="10,0,8,0"))
        caption.add_item(dui.Label(self, name="window_caption_title", text=name,
                                   valign="center", normal_text_color=theme.TEXT))
        caption.add_item(dui.Control(self, width="stretch", mouse_enabled="false"))
        caption.add_item(dui.Button(self, name="minbtn", class_="btn_wnd_min_11",
                                    width="40", height="30", margin="0,2,0,2"))
        caption.add_item(dui.Button(self, name="maxbtn", class_="btn_wnd_max_11",
                                    width="40", height="30", margin="0,2,0,2"))
        caption.add_item(dui.Button(self, name="closebtn", class_="btn_wnd_close_11",
                                    width="40", height="30", margin="0,2,8,2"))
        root.add_item(caption)

        tools = dui.HBox(self, height="36", bkcolor=theme.TOOLBAR_BG,
                         padding="8,3,8,3")
        save = dui.Button(self, class_="btn_global_color_gray", text="Save PNG...",
                          width="100", height="28", border_round="5,5")
        save.attach_click(self.on_save)
        tools.add_item(save)
        refresh = dui.Button(self, class_="btn_global_color_gray", text="Redraw",
                             width="76", height="28", border_round="5,5",
                             margin="6,0,0,0")
        refresh.attach_click(lambda args: (self.refresh(), True)[1])
        tools.add_item(refresh)
        tools.add_item(dui.Control(self, width="stretch"))
        self._hint = dui.Label(self, text=f"Figure {self.number}",
                               normal_text_color=theme.MUTED, valign="center",
                               margin="0,0,8,0")
        tools.add_item(self._hint)
        root.add_item(tools)

        self._view = dui.Control(self, name="figure_canvas", bkcolor="white",
                                 width="stretch", height="stretch",
                                 margin="8,0,8,8")
        root.add_item(self._view)
        self.attach_box(root)

        self._ready = True
        mpl.manager().register(self.number, self)
        self.attach_window_size_msg(self.on_size)
        self.attach_window_close_msg(self.on_window_close)
        dui.set_timer(self._initial_render, 30, 1, owner=self)

    def fit_to_work_area(self) -> None:
        work = dui.UiRect()
        if not self.get_monitor_work_rect(work):
            return
        window = dui.UiRect()
        self.get_window_rect(window)
        width, height = window.right - window.left, window.bottom - window.top
        work_w, work_h = work.right - work.left, work.bottom - work.top
        margin = 18
        width = min(width, max(480, work_w - 2 * margin))
        height = min(height, max(360, work_h - 2 * margin))
        x = work.left + max(0, (work_w - width) // 2)
        y = work.top + max(0, (work_h - height) // 2)
        self.move_window(int(x), int(y), int(width), int(height), True)

    # -- painting ---------------------------------------------------------
    def _client_size(self) -> tuple[int, int]:
        pos = self._view.get_pos() if self._ready else (0, 0, 0, 0)
        width, height = pos[2] - pos[0], pos[3] - pos[1]
        if width <= 20 or height <= 20:
            rc = dui.UiRect()
            try:
                self.get_client_rect(rc)
                width, height = rc.right - rc.left - 16, rc.bottom - rc.top - 84
            except Exception:  # noqa: BLE001
                width = height = 0
        return max(240, width), max(180, height)

    def refresh(self) -> None:
        if not self._ready or self._closing:
            return
        width, height = self._client_size()
        try:
            path = mpl.render_png(self.figure, width, height)
        except Exception as error:  # noqa: BLE001 - matplotlib can reject odd data
            self._hint.set_text(f"render failed: {error}")
            return
        dest = (f"file='{path}' dest='0,0,{width},{height}' dest_scale='false'")
        self._view.set_attribute("bkimage", dest)
        self._view.invalidate()
        self._hint.set_text(f"Figure {self.number}  {width}x{height}")

    def _initial_render(self) -> bool:
        self.refresh()
        return False

    def on_size(self, args: Any = None) -> bool:
        if self._resize_timer == 0:
            self._resize_timer = dui.set_timer(self._do_resize, 90, 1, owner=self)
        return True

    def _do_resize(self) -> bool:
        self._resize_timer = 0
        self.refresh()
        return False

    # -- actions ----------------------------------------------------------
    def on_save(self, args: Any = None) -> bool:
        path = dui.save_file(
            self, [("PNG image", "*.png")], "png",
            os.path.join(os.getcwd(), f"figure_{self.number}.png"))
        if path:
            self.figure.savefig(path, dpi=200)
            self._hint.set_text(f"saved {os.path.basename(path)}")
        return True

    def on_window_close(self, args: Any = None) -> bool:
        self._closing = True
        mpl.manager().forget(self.number)
        mpl.close_figure_silently(self.number)
        return True

    def raise_and_focus(self) -> None:
        self.show_window()
        self.set_window_focus()
