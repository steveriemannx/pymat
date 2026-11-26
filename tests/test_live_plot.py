"""Exercise plotting from inside the real dui message loop, then quit."""

import os
import sys

import dui

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pymat.gui.app import PymatApp
from pymat.gui.main_window import PymatWindow


def main():
    app = PymatApp(cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dui.startup()
    window = PymatWindow(app)
    if not window.create_wnd("pymat live"):
        return 1
    window.post_quit_msg_when_closed(True)
    window.show_window()
    window.invalidate_all()
    window.update_window()

    state = {"step": 0}

    def tick():
        state["step"] += 1
        if state["step"] == 1:
            window.input.set_text("plt.figure(3); plt.plot([1, 2, 3], [2, 1, 4], 'go-'); "
                                  "plt.title('live'); plt.show()")
            window.on_command_return()
        elif state["step"] == 2:
            from pymat import mpl
            win = mpl.manager().windows.get(3)
            print("live figure window:", win)
            assert win is not None
            win.refresh()
            print("hint:", win._hint.get_text_a() if hasattr(win._hint, "get_text_a")
                  else win._hint.get_text())
        elif state["step"] >= 3:
            print("console tail:", window.console.get_text_a()[-160:].replace("\n", " | "))
            window.close()
            return False
        return True

    dui.set_timer(tick, 250, 6, owner=window)
    dui.run()
    dui.shutdown()
    print("LIVE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
