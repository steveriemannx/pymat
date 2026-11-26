"""Type into the real editor inside the dui loop and check highlight refresh."""

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
    assert window.create_wnd("editor live")
    window.post_quit_msg_when_closed(True)
    window.show_window()
    window.invalidate_all()
    window.update_window()
    editor = window.tabs[0].editor
    state = {"step": 0}

    def tick():
        state["step"] += 1
        if state["step"] == 1:
            # Not set_text(): this is the RichEdit path a keystroke would take.
            editor.edit.set_text("def add(a, b):\n    return a + b  # comment\n")
            assert window.tabs[0].dirty, "dirty flag should be set"
        elif state["step"] == 3:
            markup = editor.rich.text
            print("markup has keyword:", "#FFAF00DB" in markup)
            print("markup has comment:", "#FF6A737D" in markup)
            print("gutter numbers:", editor.gutter.text.count("<br />") + 1)
            assert "#FFAF00DB" in markup, markup[:300]
            assert "#FF6A737D" in markup, markup[-300:]
            assert " *" in window.tabs[0].item.get_title()
            window.close()
            return False
        return True

    dui.set_timer(tick, 200, 8, owner=window)
    dui.run()
    dui.shutdown()
    print("LIVE EDITOR OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
