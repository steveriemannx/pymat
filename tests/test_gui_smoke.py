"""Drive the real window without a human: build it, run the demo, inspect the output."""

import os
import sys

import dui

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymat.gui.app import PymatApp
from pymat.gui.main_window import PymatWindow
from pymat import mpl


def main():
    app = PymatApp(cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dui.startup()
    window = PymatWindow(app)
    assert window.create_wnd("pymat test"), "create_wnd failed"
    window.show_window()
    window.update_window()
    print("window built, tabs:", [t.title for t in window.tabs])
    assert window._tree_root.get_child_node_count() > 0, "file tree is empty"
    assert window._folder_icon and window._file_icon, "file icons missing"

    window.on_run()
    text = window.console.get_text_a()
    print("--- console after Run ---")
    print(text[-1200:])
    assert "solution x" in text, "demo output missing"
    assert mpl.manager().windows, "demo did not open a figure window"
    win = mpl.manager().windows[1]
    print("figure 1 window:", win, "axes:", len(win.figure.axes))
    win.refresh()
    assert "file=" in win._view.get_bk_image()

    # Console path: numpy + matplotlib, exactly as a Python user would write it.
    window.input.set_text("A = np.array([[1, 2, 3], [4, 5, 6]])")
    window.input.send_event("return")
    assert ">>> A = np.array" in window.console.get_text_a()
    print("--- after console assignment ---")
    print(window.console.get_text_a()[-300:])
    window.input.set_text("plt.plot([1, 2, 3], [3, 1, 2], 'ro-'); plt.show()")
    window.input.send_event("return")
    print("--- workspace rows ---")
    for var in window.session.workspace():
        print(var)
    window.refresh_workspace()
    print("workspace count:", window.workspace_row_count())
    assert window.workspace_row_count() >= 5

    window.close()
    dui.shutdown()
    print("GUI SMOKE OK")


if __name__ == "__main__":
    main()
