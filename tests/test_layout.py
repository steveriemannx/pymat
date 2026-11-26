import os
import sys

import dui

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pymat.gui.app import PymatApp
from pymat.gui.main_window import PymatWindow


def main():
    app = PymatApp(cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dui.startup()
    w = PymatWindow(app)
    assert w.create_wnd("layout")
    w.show_window()
    w.invalidate_all()
    w.update_window()
    for name, control in [
            ("file_tree", w.file_tree), ("workspace_table", w.workspace_table),
            ("console", w.console), ("input", w.input),
            ("editor", w.tabs[0].editor.edit),
            ("gutter", w.tabs[0].editor.gutter),
            ("status", w._status), ("path", w._path_label)]:
        print(f"{name:15} {control.get_pos()}")
    print("tab_ctrl", w.tab_ctrl.get_pos(), "tab_box", w.tab_box.get_pos())

    # Run a matplotlib plot and inspect the embedded figure window geometry.
    w.session.execute('plt.figure(1); plt.plot([1, 2, 3], [3, 1, 2]); '
                      'plt.title("test"); plt.show()')
    from pymat import mpl
    win = mpl.manager().windows[1]
    win.show_window()
    win.invalidate_all()
    win.update_window()
    print("figure canvas", win._view.get_pos(), "bkimage", win._view.get_bk_image()[:90])
    print("figure hint", win._hint.get_text_a() if hasattr(win._hint, "get_text_a") else win._hint.get_text())
    win.close()
    w.close()
    dui.shutdown()
    print("LAYOUT OK")


if __name__ == "__main__":
    main()
