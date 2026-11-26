"""Command line entry point: GUI by default, a REPL with --cli."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence

from .session import Session


def _repl(session: Session) -> int:
    print("pymat 0.2.0 -- Python scientific desktop (numpy/pandas/scipy/matplotlib)")
    try:
        import readline  # noqa: F401 - enables line editing in input()
    except ImportError:
        pass
    while True:
        try:
            line = input(">> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt")
            session._buffer = ""
            continue
        if line.strip() in {"exit", "quit"}:
            return 0
        done, result = session.feed(line)
        if result.output:
            print(result.output, end="")
        if result.error:
            print(result.error, end="")
        if not done:
            # Keep reading continuation lines into the same statement.
            while not done:
                try:
                    more = input("... ")
                except (EOFError, KeyboardInterrupt):
                    session._buffer = ""
                    print()
                    break
                done, result = session.feed(more)
                if result.output:
                    print(result.output, end="")
                if result.error:
                    print(result.error, end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pymat",
        description="Python scientific desktop (numpy, pandas, scipy, matplotlib) "
                    "built with dui. Runs the desktop by default; use --cli for a "
                    "terminal session.")
    parser.add_argument("script", nargs="?", help="Python script to run")
    parser.add_argument("-e", "--eval", help="execute a line and exit")
    parser.add_argument("--cli", action="store_true", help="terminal session, no GUI")
    parser.add_argument("--gui", action="store_true", help="force the desktop UI")
    parser.add_argument("--cwd", default=None, help="working directory")
    args = parser.parse_args(argv)

    cwd = os.path.abspath(args.cwd) if args.cwd else os.getcwd()
    os.chdir(cwd)

    if args.eval:
        session = Session(cwd)
        result = session.execute(args.eval)
        if result.output:
            print(result.output, end="")
        if result.error:
            print(result.error, end="")
        return 0 if result.ok else 1

    if args.script:
        session = Session(cwd)
        result = session.run_file(args.script)
        if result.output:
            print(result.output, end="")
        if result.error:
            print(result.error, end="")
        return 0 if result.ok else 1

    if args.cli:
        return _repl(Session(cwd))

    from .gui import run_gui
    run_gui(cwd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
