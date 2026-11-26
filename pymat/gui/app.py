"""Application wiring: session + main window + matplotlib figure windows."""

from __future__ import annotations

import dui
from typing import Any

from .. import mpl
from ..session import Session
from .figure_window import FigureWindow
from .main_window import PymatWindow


class PymatApp:
    def __init__(self, cwd: str | None = None) -> None:
        self.session = Session(cwd=cwd)
        self.window: PymatWindow | None = None
        self.pysimu_window: Any = None
        mpl.set_show_handler(self.show_figure)

    # -- figure windows ---------------------------------------------------
    def show_figure(self, figure: mpl.FigureClass) -> None:
        window = FigureWindow(figure)
        if not window.create_wnd(f"Figure {figure.number}"):
            print(f"pymat: could not create the window for Figure {figure.number}")
            return
        window.fit_to_work_area()
        window.show_window()
        window.refresh()

    # -- main loop --------------------------------------------------------
    def run(self) -> None:
        dui.startup()
        self.window = PymatWindow(self)
        if not self.window.create_wnd("pymat"):
            raise RuntimeError("pymat: could not create the main window")
        self.window.fit_to_work_area()
        self.window.post_quit_msg_when_closed(True)
        self.window.show_window()
        self.window.invalidate_all()
        self.window.update_window()
        try:
            dui.run()
        finally:
            dui.shutdown()


def run_gui(cwd: str | None = None) -> None:
    PymatApp(cwd).run()
