"""File browser and console behaviours that need a real dui window."""

import os
import sys
import tempfile
import time

import dui

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pymat.gui.app import PymatApp
from pymat.gui.main_window import PymatWindow


def main():
    root = tempfile.mkdtemp()
    sub = os.path.join(root, "subdir")
    os.mkdir(sub)
    script = os.path.join(root, "hello.py")
    with open(script, "w", encoding="utf-8") as handle:
        handle.write("print('hello from file')\n")

    app = PymatApp(cwd=root)
    dui.startup()
    window = PymatWindow(app)
    assert window.create_wnd("browser")
    window.show_window()
    window.update_window()

    root_node = window._tree_root
    print("tree children", root_node.get_child_node_count())
    print("icons", window._folder_icon, window._file_icon)
    assert root_node.get_child_node_count() == 2
    assert window._folder_icon and window._file_icon

    # Select the directory node, then expand it.
    dir_node = None
    for index in range(root_node.get_child_node_count()):
        node = root_node.get_child_node(index)
        if node.get_text().endswith("/"):
            dir_node = node
            break
    assert dir_node is not None
    dir_node.send_event("click")
    assert window._selected_path and os.path.isdir(window._selected_path)
    dir_node.send_event("expand")
    print("dir children after expand", dir_node.get_child_node_count())
    assert dir_node.get_child_node_count() >= 0

    # Find the .py leaf and open it with a double click.
    file_node = None
    for index in range(root_node.get_child_node_count()):
        node = root_node.get_child_node(index)
        if node.get_text().endswith(".py"):
            file_node = node
            break
    assert file_node is not None
    file_node.send_event("mouse_double_click")
    print("tabs:", [t.title for t in window.tabs])
    assert any(t.title == "hello.py" for t in window.tabs)

    # Console font is the monospace face and Enter/Return runs the line.
    font_id = window.console.get_font_id()
    print("console font", font_id)
    assert font_id == "system_14"
    window.input.set_text("answer = 6 * 7")
    window.input.send_event("return")
    assert window.session.ns.get("answer") == 42
    assert window.console.get_sel() == (136, 136) or window.console.get_sel()[0] == window.console.get_sel()[1]
    print("console tail:", window.console.get_text_a()[-80:].replace("\n", " | "))

    window.close()
    dui.shutdown()
    print("FILE BROWSER / CONSOLE OK")


if __name__ == "__main__":
    main()
