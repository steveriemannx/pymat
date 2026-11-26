"""Checks for the overlay code editor: alignment, scrolling, markup."""

import os
import sys

import dui

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pymat.gui.code_editor import CodeEditor, highlight_markup


class Form(dui.WindowImplBase):
    def on_init_window(self):
        self.set_window_size(800, 500)
        root = dui.VBox(self, bkcolor="white")
        self.editor = CodeEditor(self)
        root.add_item(self.editor.container)
        self.attach_box(root)


def main():
    markup = highlight_markup('x = 1  # hi\ns = "<b>&"\n')
    assert "&lt;b&gt;&amp;" in markup, markup
    assert "<font color=" in markup
    print("markup ok", len(markup))

    dui.startup()
    form = Form()
    assert form.create_wnd("editor"), "create_wnd"
    form.show_window()
    form.invalidate_all()
    form.update_window()
    editor = form.editor
    code = "\n".join(
        f"value_{i} = mat(\"[1 2 3]\")  # line {i} " + "x" * 80
        for i in range(60))
    editor.set_text(code)
    form.update_window()

    rich_range = editor.code_scroll.get_scroll_range()
    edit_range = editor.edit.get_scroll_range()
    gutter_range = editor.gutter_scroll.get_scroll_range()
    print("rich range", rich_range.cx, rich_range.cy)
    print("edit range", edit_range.cx, edit_range.cy)
    print("gutter range", gutter_range.cx, gutter_range.cy)
    assert rich_range.cy == edit_range.cy, (rich_range.cy, edit_range.cy)
    assert gutter_range.cy == edit_range.cy, (gutter_range.cy, edit_range.cy)

    editor.edit.set_scroll_pos_x(120)
    editor.edit.set_scroll_pos_y(500)
    form.update_window()
    code_pos = editor.code_scroll.get_scroll_pos()
    gutter_pos = editor.gutter_scroll.get_scroll_pos()
    print("synced", code_pos.cx, code_pos.cy, gutter_pos.cx, gutter_pos.cy)
    assert code_pos.cy == gutter_pos.cy
    assert code_pos.cx == editor.edit.get_scroll_pos().cx

    # Whitespace must survive the RichText layer: indentation before a coloured
    # keyword used to be a whitespace-only XML text node, which pugixml drops.
    editor.set_text("x = 1\n")
    form.update_window()
    plain_width = editor.rich.get_pos()[2] - editor.rich.get_pos()[0]
    editor.set_text("    x = 1\n")
    form.update_window()
    indented_width = editor.rich.get_pos()[2] - editor.rich.get_pos()[0]
    print("widths", plain_width, indented_width)
    assert indented_width > plain_width + 10

    editor.set_text("def f():\n")
    form.update_window()
    keyword_width = editor.rich.get_pos()[2] - editor.rich.get_pos()[0]
    editor.set_text("    def f():\n")
    form.update_window()
    indented_keyword_width = editor.rich.get_pos()[2] - editor.rich.get_pos()[0]
    print("keyword widths", keyword_width, indented_keyword_width)
    assert indented_keyword_width > keyword_width + 10

    # Incomplete code must still produce markup (regex fallback).
    editor.set_text("def broken(:\n    print('still colourful')\n")
    text = editor.rich.text
    assert "still colourful" in text
    print("gutter text tail", editor.gutter.text[-80:])

    form.close()
    dui.shutdown()
    print("CODE EDITOR OK")


if __name__ == "__main__":
    main()
