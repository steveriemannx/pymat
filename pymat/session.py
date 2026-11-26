"""The execution session: a plain Python namespace with the scientific stack.

Nothing here invents a new language or a MATLAB-style function catalogue.  A
line typed at the prompt is compiled and executed by CPython exactly as written,
with numpy, pandas, scipy and matplotlib already imported under their usual
aliases:

    np   numpy          pd   pandas        sp   scipy        plt  matplotlib.pyplot

The only REPL conveniences are ordinary CPython ones: an expression displays its
``repr`` and is stored in ``_``; an incomplete block (``for ...:``) is buffered
until it compiles.
"""

from __future__ import annotations

import ast
import codeop
import contextlib
import io
import math
import os
import random
import sys
import traceback
from dataclasses import dataclass
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy as sp
import scipy.integrate
import scipy.interpolate
import scipy.linalg
import scipy.optimize
import scipy.signal
import scipy.stats

from . import mpl

__all__ = ["Session", "install_namespace", "ExecResult", "VarInfo"]


def _library_namespace() -> dict[str, Any]:
    return {
        "np": np, "numpy": np,
        "pd": pd, "pandas": pd,
        "sp": sp, "scipy": sp,
        "plt": plt, "matplotlib": matplotlib,
        "linalg": scipy.linalg,
        "optimize": scipy.optimize,
        "stats": scipy.stats,
        "signal": scipy.signal,
        "interpolate": scipy.interpolate,
        "integrate": scipy.integrate,
        "math": math,
        "random": random,
    }


def install_namespace(ns: dict[str, Any]) -> dict[str, Any]:
    """Put the scientific stack into *ns* (a dict used as ``globals()``)."""
    ns.update(_library_namespace())
    ns["__builtins__"] = __builtins__
    return ns


@dataclass
class VarInfo:
    name: str
    size: str
    kind: str
    value: str


@dataclass
class ExecResult:
    output: str = ""
    error: str = ""
    value: Any = None
    executed: bool = True

    @property
    def ok(self) -> bool:
        return not self.error


class Session:
    """One interpreter namespace plus the console bookkeeping around it."""

    def __init__(self, cwd: str | None = None) -> None:
        self.ns: dict[str, Any] = {"__name__": "__main__", "__doc__": None}
        install_namespace(self.ns)
        self._reserved = set(self.ns) | {"__name__", "__doc__", "__builtins__"}
        self.history: list[str] = []
        self.cwd = cwd or os.getcwd()
        self._buffer = ""
        self.on_clear: Any = None

    # -- working directory ------------------------------------------------
    def chdir(self, path: str) -> str:
        target = os.path.abspath(os.path.expanduser(str(path)))
        if not os.path.isdir(target):
            raise NotADirectoryError(target)
        os.chdir(target)
        self.cwd = target
        return target

    def clear(self) -> None:
        for key in list(self.ns):
            if key in self._reserved:
                continue
            del self.ns[key]

    # -- workspace --------------------------------------------------------
    def workspace(self) -> list[VarInfo]:
        out: list[VarInfo] = []
        for name in sorted(self.ns):
            if name.startswith("_") or name in self._reserved:
                continue
            value = self.ns[name]
            if isinstance(value, type(os)) or isinstance(value, type(np)):
                continue
            out.append(VarInfo(name, _size_text(value), _kind_text(value),
                               _preview(value)))
        return out

    # -- execution --------------------------------------------------------
    def feed(self, line: str) -> tuple[bool, ExecResult]:
        """Console line in, complete-statement check out (for multi-line input)."""
        if line == "" and self._buffer:
            self._buffer = ""
            return True, ExecResult()
        self._buffer += ("\n" if self._buffer else "") + line
        code = self._buffer
        try:
            compiled = codeop.compile_command(code, "<pymat>", "exec")
        except (SyntaxError, OverflowError, ValueError):
            compiled = False
        if compiled is None:
            return False, ExecResult(executed=False)
        self._buffer = ""
        self.history.append(code)
        return True, self.execute(code, interactive=True)

    def execute(self, code: str, interactive: bool = False) -> ExecResult:
        """Run *code*.

        ``interactive=True`` gives REPL semantics: if the last statement is an
        expression, its repr is returned and saved in ``_``.  Scripts run with
        ``interactive=False``, so nothing is echoed unless the script prints it.
        """
        result = ExecResult()
        buffer = io.StringIO()
        try:
            tree = ast.parse(code, "<pymat>", "exec")
        except SyntaxError as error:
            result.error = _format_syntax_error(error)
            result.executed = False
            return result
        body = tree.body
        if not body:
            return result
        display_value: Any = None
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            try:
                if not interactive:
                    exec(compile(tree, "<pymat>", "exec"), self.ns)
                else:
                    if len(body) > 1:
                        module = ast.Module(body=body[:-1], type_ignores=[])
                        exec(compile(module, "<pymat>", "exec"), self.ns)
                    last = body[-1]
                    if isinstance(last, ast.Expr):
                        value = eval(compile(ast.Expression(last.value), "<pymat>",
                                             "eval"), self.ns)
                        if value is not None:
                            self.ns["_"] = value
                            display_value = value
                    else:
                        exec(compile(ast.Module(body=[last], type_ignores=[]),
                                     "<pymat>", "exec"), self.ns)
            except Exception:  # noqa: BLE001 - user code may raise anything
                result.error = _short_traceback()
        output = buffer.getvalue()
        if display_value is not None:
            output += _display(display_value) + "\n"
        result.output = output
        result.value = display_value
        return result

    def run_file(self, path: str) -> ExecResult:
        full = os.path.abspath(os.path.expanduser(str(path)))
        with open(full, "r", encoding="utf-8") as handle:
            code = handle.read()
        old_cwd = os.getcwd()
        old_file = self.ns.get("__file__")
        self.ns["__file__"] = full
        sys.path.insert(0, os.path.dirname(full) or ".")
        try:
            os.chdir(os.path.dirname(full) or old_cwd)
            self.cwd = os.getcwd()
            result = self.execute(code)
        finally:
            os.chdir(old_cwd)
            sys.path.pop(0)
            if old_file is None:
                self.ns.pop("__file__", None)
            else:
                self.ns["__file__"] = old_file
        return result

    def reset(self) -> None:
        mpl.close_all()
        self.ns.clear()
        self.ns.update({"__name__": "__main__", "__doc__": None})
        install_namespace(self.ns)


# ---------------------------------------------------------------------------
# Workspace formatting helpers
# ---------------------------------------------------------------------------

def _display(value: Any) -> str:
    """repr(), except graphics objects where the full repr is noise."""
    if isinstance(value, mpl.FigureClass):
        return f"<Figure {value.number}>"
    module = type(value).__module__ or ""
    if module.startswith("matplotlib"):
        return f"<{type(value).__name__}>"
    if isinstance(value, (list, tuple)) and value:
        names = {type(item).__name__ for item in value
                 if (type(item).__module__ or "").startswith("matplotlib")}
        if names and len(names) == 1:
            return f"<{names.pop()} list ({len(value)})>"
    return repr(value)


def _size_text(value: Any) -> str:
    try:
        import numpy as _np
        import pandas as _pd
    except ImportError:  # pragma: no cover - the stack is a hard dependency now
        _np = _pd = None
    if _np is not None and isinstance(value, _np.ndarray):
        if value.ndim == 0:
            return "scalar"
        return "x".join(str(v) for v in value.shape)
    if _pd is not None and isinstance(value, _pd.DataFrame):
        return f"{value.shape[0]}x{value.shape[1]}"
    if _pd is not None and isinstance(value, _pd.Series):
        return str(len(value))
    shape = getattr(value, "shape", None)
    if isinstance(shape, tuple) and shape:
        return "x".join(str(v) for v in shape)
    if isinstance(value, (list, tuple, set, dict)):
        return str(len(value))
    return "1"


def _kind_text(value: Any) -> str:
    try:
        import pandas as _pd
    except ImportError:  # pragma: no cover
        _pd = None
    if isinstance(value, mpl.FigureClass):
        return "Figure"
    if _pd is not None and isinstance(value, _pd.DataFrame):
        return "DataFrame"
    if _pd is not None and isinstance(value, _pd.Series):
        return "Series"
    if isinstance(value, np.ndarray):
        return "ndarray"
    if isinstance(value, (bool, np.bool_)):
        return "bool"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, (list, tuple)):
        return type(value).__name__
    if callable(value):
        return "function"
    return type(value).__name__


def _fmt_number(value: Any) -> str:
    if isinstance(value, (bool, np.bool_)):
        return "1" if value else "0"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number) and abs(number) < 1e9:
        return str(int(number))
    return f"{number:.4g}"


def _preview(value: Any) -> str:
    try:
        import pandas as _pd
    except ImportError:  # pragma: no cover
        _pd = None
    if isinstance(value, mpl.FigureClass):
        return f"Figure {value.number}"
    if _pd is not None and isinstance(value, _pd.DataFrame):
        return " ".join(str(c) for c in value.columns)
    if _pd is not None and isinstance(value, _pd.Series):
        head = ", ".join(_fmt_number(v) for v in value.head(4).tolist())
        return head or (value.name or str(value.dtype))
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return "[]"
        if value.ndim == 0:
            return _fmt_number(value.item())
        if value.ndim == 2:
            row = value[0][:3]
            body = ", ".join(_fmt_number(v) for v in row)
            return f"[{body}]"
        flat = value.ravel()[:3]
        return "[" + ", ".join(_fmt_number(v) for v in flat) + "]"
    if isinstance(value, dict):
        return ", ".join(str(k) for k in list(value)[:5])
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        return "[" + ", ".join(str(v) for v in value[:5]) + "]"
    return str(value)


def _format_syntax_error(exc: BaseException) -> str:
    if isinstance(exc, SyntaxError):
        line = f"  File \"<pymat>\", line {exc.lineno}\n    {exc.text.rstrip() if exc.text else ''}"
        return f"SyntaxError: {exc.msg}\n{line}\n"
    return f"{type(exc).__name__}: {exc}\n"


def _short_traceback() -> str:
    exc_type, exc_value, exc_tb = sys.exc_info()
    frames = traceback.extract_tb(exc_tb)
    lines = ["Traceback (most recent call last):"]
    for frame in frames:
        if frame.filename == "<pymat>":
            lines.append(f'  File "<console>", line {frame.lineno}, in {frame.name}')
            if frame.line:
                lines.append(f"    {frame.line}")
    lines.extend(traceback.format_exception_only(exc_type, exc_value))
    return "\n".join(lines)


HELP_TEXT = """pymat -- Python scientific desktop

Libraries already imported     np / numpy, pd / pandas, sp / scipy, plt / matplotlib
                               linalg, optimize, stats, signal, interpolate, integrate
Arrays                         np.array([[1, 2], [3, 4]])
Tables                         pd.DataFrame({"a": [1, 2], "b": [3, 4]})
Linear algebra                 sp.linalg.inv(A), sp.linalg.eig(A)
Optimisation / statistics      sp.optimize.minimize(...), sp.stats.norm.pdf(...)
Plots                          plt.plot(x, y); plt.title("..."); plt.show()
Scripts                        the editor's Run button, or run a .py file from the CLI
Workspace                      the Workspace tab in the left pane
Help                           help(np.linspace), dir(np), ...
Console                        Python REPL semantics; expressions print repr; `_` holds the last value

Any Python statement is allowed.  Assignments do not echo: type the name to see
the value.  matplotlib figures open as pymat windows when plt.show() is called.
"""
