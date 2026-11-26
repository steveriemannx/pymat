"""matplotlib <-> dui bridge.

matplotlib is configured with the Agg backend.  ``plt.show()`` is patched so the
figures open as pymat windows instead of spawning a Tk/Qt window; in a terminal
session with no desktop attached it falls back to matplotlib's own ``show``.

Closing a pymat figure window removes the matplotlib figure too, and
``plt.close(...)`` closes the pymat window, so both APIs stay in step.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

FigureClass = Figure

_TEMP_DIR = os.path.join(tempfile.gettempdir(), "pymat-figures")
os.makedirs(_TEMP_DIR, exist_ok=True)

_ORIGINAL_SHOW = plt.show
_ORIGINAL_CLOSE = plt.close


class Manager:
    def __init__(self) -> None:
        self.windows: dict[int, Any] = {}
        self.show_handler: Callable[[Figure], Any] | None = None

    def show_all(self) -> None:
        for number in plt.get_fignums():
            figure = plt.figure(number)
            window = self.windows.get(number)
            if window is not None:
                window.refresh()
            elif self.show_handler is not None:
                self.show_handler(figure)

    def register(self, number: int, window: Any) -> None:
        self.windows[int(number)] = window

    def forget(self, number: int) -> None:
        self.windows.pop(int(number), None)

    def close_window(self, number: int) -> None:
        window = self.windows.get(int(number))
        if window is not None:
            window.close()

    def close_all(self) -> None:
        for number in list(self.windows):
            self.close_window(number)


_MANAGER = Manager()


def manager() -> Manager:
    return _MANAGER


def set_show_handler(handler: Callable[[Figure], Any] | None) -> None:
    _MANAGER.show_handler = handler


def render_png(figure: Figure, width: int, height: int) -> str:
    width = max(240, int(width))
    height = max(180, int(height))
    figure.set_dpi(100)
    figure.set_size_inches(width / 100.0, height / 100.0)
    try:
        figure.tight_layout()
    except Exception:  # noqa: BLE001 - 3-D axes can reject tight_layout
        pass
    path = os.path.join(_TEMP_DIR, f"fig{figure.number}-{uuid.uuid4().hex[:10]}.png")
    figure.savefig(path, dpi=100, facecolor=figure.get_facecolor())
    return path


def close_figure_silently(number: int) -> None:
    """Close the matplotlib figure without re-entering the patched plt.close."""
    try:
        _ORIGINAL_CLOSE(int(number))
    except Exception:  # noqa: BLE001
        pass


def close_all() -> None:
    _MANAGER.close_all()
    try:
        _ORIGINAL_CLOSE("all")
    except Exception:  # noqa: BLE001
        pass


def _show(*args: Any, **kwargs: Any):
    if _MANAGER.show_handler is None:
        # Terminal session: Agg has no window to show, and calling matplotlib's
        # own show() would only print a "non-interactive backend" warning.
        return None
    _MANAGER.show_all()
    return None


def _close(*args: Any, **kwargs: Any):
    targets: list[int] = []
    if not args or args[0] is None:
        targets = list(_MANAGER.windows)
    elif args[0] == "all":
        targets = list(_MANAGER.windows)
    else:
        target = args[0]
        number = getattr(target, "number", target)
        try:
            number = int(number)
        except (TypeError, ValueError):
            number = -1
        targets = [number]
    for number in targets:
        _MANAGER.close_window(number)
    return _ORIGINAL_CLOSE(*args, **kwargs)


plt.show = _show
plt.close = _close
