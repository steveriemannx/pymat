"""Colours and small layout helpers shared by the pymat windows."""

from __future__ import annotations

# A light desktop.  dui's own theme is light too, so the standard
# button/list classes stay readable without restyling every control.
WINDOW_BG = "#FFF3F3F3"
PANEL_BG = "#FFFFFFFF"
CAPTION_BG = "#FFE9EAEC"
TOOLBAR_BG = "#FFF7F7F8"
BORDER = "#FFD9DBDE"
TEXT = "#FF1A1A1A"
MUTED = "#FF6B7076"
ACCENT = "#FF0072BD"
ACCENT_DARK = "#FF005A96"
SUCCESS = "#FF2E7D32"
ERROR = "#FFC62828"
EDITOR_BG = "#FFFFFFFF"
CONSOLE_BG = "#FFFFFFFF"
GUTTER_BG = "#FFF6F8FA"
GUTTER_TEXT = "#FF9AA0A6"
CURRENT_LINE = "#FFF2F7FF"

# Python syntax colours for the code editor's RichText layer.  Only colours are
# used (no bold/italic): changing glyph widths would desynchronise the invisible
# RichEdit that owns the caret and selection.
SYNTAX = {
    "default": "#FF24292F",
    "keyword": "#FFAF00DB",
    "builtin": "#FF0072BD",
    "definition": "#FF267F99",
    "string": "#FFA31515",
    "comment": "#FF6A737D",
    "number": "#FF098658",
    "operator": "#FF57606A",
    "error": "#FFC62828",
    "self": "#FF7E2F8E",
}


def section_label(parent, text: str):
    import dui

    return dui.Label(parent, text=text.upper(), height="20", font="system_bold_12",
                     normal_text_color=MUTED, text_align="left,vcenter",
                     margin="0,8,0,4")


def toolbar_button(parent, text: str, width: int = 86, accent: bool = False):
    import dui

    cls = "btn_global_color_blue" if accent else "btn_global_color_gray"
    return dui.Button(parent, class_=cls, text=text, width=str(width), height="30",
                      border_round="5,5", margin="0,0,6,0", font="system_12")


def divider(parent, vertical: bool = False):
    import dui

    if vertical:
        return dui.Control(parent, class_="splitline_ver_level1", width="1",
                           height="stretch", margin="6,2,6,2")
    return dui.Control(parent, class_="splitline_hor_level1", width="stretch",
                       height="1", margin="0,4,0,4")
