"""A syntax-highlighted code editor built from dui controls.

dui's RichEdit draws one text colour for the whole control, so the colours and
the editable text are separated into two perfectly aligned layers:

* a read-only ``RichText`` behind the input carries the coloured Python source;
* a ``RichEdit`` on top has transparent text and a visible caret/selection, and
  owns all editing, undo, mouse positioning and scrolling.

Both layers use the same font, padding and row spacing, so their scroll ranges
and line heights match exactly; the test suite checks that they do.  The gutter
is a third RichText showing line numbers, scrolled in step with the editor.
"""

from __future__ import annotations

import builtins
import io
import keyword
import re
import tokenize
from typing import Any, Callable

import dui

from . import theme

_BUILTINS = set(dir(builtins))
_LIBRARY_NAMES = {
    "np", "numpy", "pd", "pandas", "sp", "scipy", "plt", "matplotlib",
    "linalg", "optimize", "stats", "signal", "interpolate", "integrate",
    "math", "random",
}
_KEYWORDS = set(keyword.kwlist)

_STRING_TYPES = {tokenize.STRING}
for _name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
    _value = getattr(tokenize, _name, None)
    if _value is not None:
        _STRING_TYPES.add(_value)

_FALLBACK = re.compile(
    r"(?P<comment>#[^\n]*)"
    r"|(?P<string>'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\""
    r"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")"
    r"|(?P<number>\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)"
    r"|(?P<name>\b[A-Za-z_]\w*\b)",
    re.M,
)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _token_color(tok_type: int, text: str, prev: str | None,
                 prev_prev: str | None) -> str:
    if tok_type == tokenize.COMMENT:
        return theme.SYNTAX["comment"]
    if tok_type in _STRING_TYPES:
        return theme.SYNTAX["string"]
    if tok_type == tokenize.NUMBER:
        return theme.SYNTAX["number"]
    if tok_type == tokenize.NAME:
        if text in _KEYWORDS:
            return theme.SYNTAX["keyword"]
        if text == "self":
            return theme.SYNTAX["self"]
        if prev in ("def", "class"):
            return theme.SYNTAX["definition"]
        if prev == ".":
            return theme.SYNTAX["default"]
        if text in _BUILTINS or text in _LIBRARY_NAMES:
            return theme.SYNTAX["builtin"]
        return theme.SYNTAX["default"]
    if tok_type == tokenize.OP:
        # Punctuation keeps the default colour: every extra <font> slice costs a
        # fraction of a pixel in the coloured layer, so only meaningful tokens
        # are split out.
        return theme.SYNTAX["default"]
    if tok_type == tokenize.ERRORTOKEN:
        return theme.SYNTAX["error"]
    return theme.SYNTAX["default"]


def _spans_from_tokens(text: str) -> list[tuple[int, int, str]]:
    line_starts = [0]
    for line in text.splitlines(True):
        line_starts.append(line_starts[-1] + len(line))

    def offset(position: tuple[int, int]) -> int:
        row, col = position
        if row - 1 >= len(line_starts):
            return len(text)
        return min(len(text), line_starts[row - 1] + col)

    spans: list[tuple[int, int, str]] = []
    prev = prev_prev = None
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        tok_type, tok_text, start, end, _ = token
        color = _token_color(tok_type, tok_text, prev, prev_prev)
        begin, stop = offset(start), offset(end)
        if stop > begin and color != theme.SYNTAX["default"]:
            spans.append((begin, stop, color))
        if tok_type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                            tokenize.DEDENT, tokenize.ENCODING):
            prev_prev, prev = prev, tok_text
    return spans


def _spans_from_regex(text: str) -> list[tuple[int, int, str]]:
    spans = []
    for match in _FALLBACK.finditer(text):
        group = match.lastgroup
        if group == "comment":
            color = theme.SYNTAX["comment"]
        elif group == "string":
            color = theme.SYNTAX["string"]
        elif group == "number":
            color = theme.SYNTAX["number"]
        elif match.group(group) in _KEYWORDS:
            color = theme.SYNTAX["keyword"]
        elif match.group(group) in _BUILTINS or match.group(group) in _LIBRARY_NAMES:
            color = theme.SYNTAX["builtin"]
        else:
            continue
        spans.append((match.start(), match.end(), color))
    return spans


def highlight_markup(text: str) -> str:
    """Return RichText markup for *text* (colours only, exact whitespace)."""
    text = text.expandtabs(4)
    try:
        spans = _spans_from_tokens(text)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        spans = _spans_from_regex(text)

    colors = [theme.SYNTAX["default"]] * len(text)
    for begin, stop, color in spans:
        colors[begin:stop] = [color] * (stop - begin)

    lines = text.split("\n")
    rendered: list[str] = []
    offset = 0
    for line in lines:
        if not line:
            rendered.append("")
            offset += 1
            continue
        end = offset + len(line)

        # Group by colour first.
        raw: list[list[Any]] = []
        run_start = offset
        run_color = colors[offset]
        for index in range(offset + 1, end + 1):
            color = colors[index] if index < end else None
            if color != run_color:
                raw.append([line[run_start - offset:index - offset], run_color])
                run_start = index
                run_color = color

        # pugixml (used by RichText) drops text nodes that contain only
        # whitespace, even with trim_policy="none".  Glue whitespace-only runs
        # to an adjacent non-empty run so indentation and the spaces between
        # tokens survive.
        runs: list[list[Any]] = []
        pending = ""
        for chunk, color in raw:
            if chunk.strip() == "":
                if runs:
                    runs[-1][0] += chunk
                else:
                    pending += chunk
            else:
                runs.append([pending + chunk, color])
                pending = ""
        if pending:
            if runs:
                runs[-1][0] += pending
            else:
                runs.append([pending.replace(" ", "\u00a0"), theme.SYNTAX["default"]])

        pieces: list[str] = []
        for chunk, color in runs:
            escaped = _escape(chunk)
            if color == theme.SYNTAX["default"]:
                pieces.append(escaped)
            else:
                pieces.append(f"<font color='{color}'>{escaped}</font>")
        rendered.append("".join(pieces))
        offset = end + 1
    return "<br/>".join(rendered)


def line_number_markup(count: int) -> str:
    return "<br/>".join(f"{number:>4}" for number in range(1, max(1, count) + 1))


class CodeEditor:
    """A dui editor with syntax colours, line numbers and scroll sync."""

    def __init__(self, parent: Any,
                 on_change: Callable[[], None] | None = None,
                 on_cursor: Callable[[int, int], None] | None = None) -> None:
        self.on_change = on_change
        self.on_cursor = on_cursor
        self._highlight_timer = 0
        self._suppress = False

        self.container = dui.HBox(parent, width="stretch", height="stretch",
                                  bkcolor=theme.EDITOR_BG)

        # Line-number gutter.
        self.gutter_scroll = dui.ScrollBox(
            self.container, width="58", height="stretch", bkcolor=theme.GUTTER_BG,
            vscrollbar="true", hscrollbar="false", mouse_enabled="false")
        self.gutter = dui.RichText(
            self.gutter_scroll, width="stretch", height="auto", font="system_14",
            text_color=theme.GUTTER_TEXT, text_padding="6,10,6,10",
            text_align="right,top", trim_policy="none", mouse_enabled="false")
        self.gutter_scroll.add_item(self.gutter)
        self.container.add_item(self.gutter_scroll)

        # Code body: coloured RichText under a transparent RichEdit.
        self.code_box = dui.Box(self.container, width="stretch", height="stretch",
                                bkcolor=theme.EDITOR_BG)
        self.code_scroll = dui.ScrollBox(
            self.code_box, width="stretch", height="stretch", float="true",
            bkcolor=theme.EDITOR_BG, vscrollbar="true", hscrollbar="true",
            mouse_enabled="false")
        self.rich = dui.RichText(
            self.code_scroll, width="auto", height="auto", font="system_14",
            text_color=theme.SYNTAX["default"], text_padding="10,10,10,10",
            text_align="left,top", trim_policy="none", word_wrap="false",
            mouse_enabled="false")
        self.code_scroll.add_item(self.rich)
        self.code_box.add_item(self.code_scroll)

        self.edit = dui.RichEdit(
            self.code_box, width="stretch", height="stretch", float="true",
            multiline="true", word_wrap="false", font="system_14",
            bkcolor="#00000000", normal_text_color="#00FFFFFF",
            selection_bkcolor="#552D7FF9", inactive_selection_bkcolor="#332D7FF9",
            selection_text_color="#FF1A1A1A", caret_color="#FF1A1A1A",
            text_padding="10,10,10,10", want_tab="true", want_return="true",
            hide_selection="false", default_context_menu="true",
            auto_vscroll="true", focus_bottom_border_size="0",
            vscrollbar="true", hscrollbar="true")
        self.edit.set_text_color("#00FFFFFF")
        self.code_box.add_item(self.edit)
        self.container.add_item(self.code_box)

        self.edit.attach_text_changed(self._on_text_changed)
        self.edit.attach_scroll_pos_changed(self._sync_scroll)
        self.edit.attach_sel_changed(self._on_sel_changed)
        # Scrollbars only exist after the first layout; fade the decorative
        # ones behind the RichEdit so only the real editor scrollbars show.
        dui.set_timer(self._hide_decorative_scrollbars, 80, 1, owner=self.edit)
        self._render_markup("")

    # -- content ----------------------------------------------------------
    def set_text(self, text: str) -> None:
        self._suppress = True
        try:
            self.edit.set_text(text)
        finally:
            self._suppress = False
        self._render_markup(text)
        self.edit.set_scroll_pos_x(0)
        self.edit.set_scroll_pos_y(0)
        self._sync_scroll()

    def get_text(self) -> str:
        return self.edit.get_text_a()

    def set_focus(self) -> None:
        self.edit.set_focus()

    def is_dirty(self) -> bool:
        return False

    # -- highlighting -----------------------------------------------------
    def _on_text_changed(self, args: Any = None) -> bool:
        if self._suppress:
            return True
        if self.on_change is not None:
            self.on_change()
        if self._highlight_timer == 0:
            self._highlight_timer = dui.set_timer(
                self._apply_highlight, 70, 1, owner=self.edit)
        return True

    def _apply_highlight(self) -> bool:
        self._highlight_timer = 0
        text = self.get_text()
        self._render_markup(text)
        self._sync_scroll()
        return False

    def _render_markup(self, text: str) -> None:
        expanded = text.expandtabs(4)
        self.rich.set_text(highlight_markup(expanded))
        lines = expanded.count("\n") + 1
        self.gutter.set_text(line_number_markup(lines))

    # -- scrolling / cursor ----------------------------------------------
    def _sync_scroll(self, args: Any = None) -> bool:
        try:
            pos = self.edit.get_scroll_pos()
            self.code_scroll.set_scroll_pos(dui.UiSize64(pos.cx, pos.cy))
            self.gutter_scroll.set_scroll_pos_y(pos.cy)
        except Exception:  # noqa: BLE001 - layout may not be ready yet
            pass
        return True

    def _on_sel_changed(self, args: Any = None) -> bool:
        if self.on_cursor is None:
            return True
        try:
            selection = self.edit.get_sel()
            start = int(selection[0]) if selection else 0
            text = self.get_text()
            line = text.count("\n", 0, start) + 1
            last_nl = text.rfind("\n", 0, start)
            column = start - (last_nl + 1) + 1
            self.on_cursor(line, column)
        except Exception:  # noqa: BLE001
            pass
        return True

    def _hide_decorative_scrollbars(self) -> bool:
        for scroll in (self.code_scroll, self.gutter_scroll):
            for getter in ("get_v_scroll_bar", "get_h_scroll_bar"):
                try:
                    bar = getattr(scroll, getter)()
                    if bar is not None:
                        bar.set_attribute("alpha", "0")
                except Exception:  # noqa: BLE001
                    pass
        return False
