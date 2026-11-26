# pymat

**A scientific-computing desktop written in Python, built on the sibling
[pydui](../pydui) checkout (the Python bindings for dui).**

This is a Python workbench, not a MATLAB clone: there is no M language, no M
syntax translation, and no MATLAB-style function names. You write ordinary
Python in the desktop, with the usual aliases already injected into the
namespace:

```python
np   numpy        pd  pandas        sp  scipy        plt  matplotlib.pyplot
```

```python
A = np.array([[4.0, -2.0], [1.0, 1.0]])
b = np.array([6.0, 3.0])
x = np.linalg.solve(A, b)

df = pd.DataFrame({"x": [1, 2, 3], "y": [3, 1, 2]})
print(df.describe())

plt.plot(df["x"], df["y"], "o-")
plt.title("a normal matplotlib plot")
plt.show()
```

## Environment

A conda environment named `pymat` (Python 3.14) with numpy / pandas / scipy /
matplotlib is already set up. To recreate it:

```sh
./setup_env.sh
# or manually:
conda create -n pymat python=3.14 -y
conda activate pymat
pip install numpy pandas scipy matplotlib
pip install -e .
# Make pydui importable (setup_env.sh also writes this file):
echo "$PWD/../pydui/python" > "$(python -c 'import site;print(site.getsitepackages()[0])')/pydui-local.pth"
```

`pydui` uses the prebuilt `_native` extension in `../pydui`; it is not published
on PyPI, so it is added through a local path. `run.sh` also sets `PYTHONPATH`.

## Running

```sh
./run.sh                       # open the desktop
./run.sh --cli                 # terminal REPL
./run.sh -e 'print(np.arange(5) ** 2)'
./run.sh examples/numpy_pandas.py
./run.sh examples/plot_demo.py

python -m pymat                # equivalent entry point (with the env active)
pymat                          # installed command after pip install -e .
```

## Desktop layout

A classic scientific IDE arrangement: files and variables on the left, the
editor in the upper right, and the console below the editor.

```
┌──────────────────────────────────────────────┐
│ pymat toolbar: New / Open / Save / Run ...    │
├──────────────┬───────────────────────────────┤
│ FILES        │  welcome.py                   │
│  current dir │  gutter │ highlighted code   │
│  file tree   │         │                     │
│              │         │                     │
│ WORKSPACE    │─────────┴─────────────────────│
│  variables   │ CONSOLE                       │
│              │ >>> np.arange(5)              │
│              │ array([0, 1, 2, 3, 4])        │
│              │ >>>                           │
├──────────────┴───────────────────────────────┤
│ status bar                                    │
└──────────────────────────────────────────────┘
```

- **FILES** (top left): a tree view. Click a folder to expand/collapse it and a
  file to open it in the editor. Folder/file icons, selection highlight, and
  Up/refresh buttons are included.
- **WORKSPACE** (bottom left): variable name, shape, type, and a preview. numpy,
  pandas, and matplotlib Figure values are supported.
- Both the FILES/WORKSPACE boundary and the editor/console boundary are
  **draggable splitters**.
- **Editor** (top right): multiple tabs, `*` for unsaved files, Run / Save /
  close-tab actions, Python syntax highlighting, a line-number gutter,
  `Ln, Col`, and scroll synchronization with the highlight layer.
- **Console** (under the editor): a Python REPL with `↑`/`↓` history.
  Assignments do not print; expressions print `repr` and are stored in `_`.
  Multi-line blocks continue automatically and `Esc` cancels them. The
  editor/console boundary is vertically draggable.
- **Figure**: `plt.show()` does not open a Tk/Qt window; matplotlib figures are
  shown in a pymat window instead.

## Using the standard libraries directly

The console has no custom numerical-function layer; use the libraries normally:

```python
np.linspace(0, 2*np.pi, 200)
np.linalg.solve(A, b)
np.fft.fft(signal)
pd.read_csv("data.csv")
df.groupby("key").mean()
sp.optimize.minimize(f, x0)
sp.stats.norm.pdf(x, mu, sigma)
sp.signal.butter(4, 0.2)
plt.plot(x, y); plt.xlabel("x"); plt.show()
```

The namespace also contains `linalg`, `optimize`, `stats`, `signal`,
`interpolate`, `integrate`, `math`, and `random`, so repeated imports are
optional.

## pysimu: block-diagram simulation

The **pysimu** button in the toolbar opens a Simulink-style block-diagram
window (inspired by simupy's `DynamicalSystem` + `BlockDiagram` design, but
maintained inside pymat):

- The Block Library on the left is grouped Simulink-style and scrolls
  vertically. It contains 27 blocks:
  - Sources: Step / Sine / Constant / Ramp / Clock / Pulse
  - Sinks: Scope / Terminator
  - Continuous: Integrator / Derivative / Transfer Fcn / State Space / PID
  - Math: Gain / Sum / Product / Divide / Abs / Math Function / MinMax /
    Sign / Saturation
  - Signal: Bias / Dead Zone
  - Logic: Compare / Switch / Logical Op

  Every block has its own small icon. Derivative uses a filtered derivative
  with time constant `tau`, which avoids the algebraic-loop problems of a pure
  derivative.
- Add a block by clicking its icon or dragging the icon onto the canvas. While
  dragging, a full block preview (frame, icon, title, and parameters) follows
  the pointer. Every block on the canvas also shows its icon.
- A draggable splitter between the Block Library and the canvas lets you resize
  the two areas left/right.
- The canvas is a white dot grid. Blocks can be dragged and are compact.
- A single click selects a block, fills the `params` field, and selects the
  current parameters; edit them and press `Apply` or Enter. A double click has
  the same effect.
- The block face shows a compact parameter summary (for example `order 2` or
  `Kp=1 Ki=0`). Long summaries end in `…`; the full parameters are available
  in the hover tooltip and in the `params` field.
- Manual wiring: drag from the green output dot on the right of a block to the
  target block or a blue input dot on its left. Multi-input blocks such as Sum
  choose the port from the drop position. Alternatively, press `Connect` and
  click the source block, then the target block, to use the first free input
  port.
- Wires avoid intervening blocks automatically; feedback wires route below the
  blocks instead of crossing them.
- A wire can be dragged with the mouse: horizontal segments move up/down and
  vertical segments move left/right.
- Selected blocks get a blue border and light-blue fill; selected wires turn
  blue. Right-click a wire for its delete menu, or press `Delete` to remove the
  selected wire.
- Block context menu: Edit parameters / Duplicate block / Disconnect wires /
  Delete block.
- The `params` field edits the selected block, for example `gain=2` or
  `num=[1]; den=[1,2,1]`; press Apply to commit.
- `Run` simulates with `scipy.integrate.solve_ivp`; Scope signals are shown in
  pymat figure windows through matplotlib.
- `Save` / `Load` store the diagram as JSON (default
  `pysimu/pysimu_diagram.json`).
- A new window starts with an empty canvas. If a `pysimu_diagram.json` exists
  in the current directory, it is loaded automatically.

The engine lives in `pymat/sim/`:

| File | Contents |
|---|---|
| `blocks.py` | Block types, initial state, output/derivative |
| `diagram.py` | Links, topological ordering, algebraic-loop detection, `solve_ivp` simulation, JSON |
| `gui.py` | dui block-diagram window, block dragging, wire drawing, run/save/load |

Signals are currently scalar and continuous-time. An algebraic loop must be
broken by an Integrator or a transfer function with `D=0`; otherwise the engine
reports a clear error.

## Syntax-highlighting implementation

dui's `RichEdit` has no "editable rich text" interface, so the editor uses two
strictly aligned layers:

- A read-only `RichText` underneath: displays colored Python code (colors only,
  no bold/italic, so glyph widths do not change).
- A transparent-text `RichEdit` on top: handles input, caret, selection, undo,
  mouse positioning, and scrolling.
- A separate line-number `RichText`: scrolls vertically in sync with the editor.

Both layers use the same font, padding, and line height; the tests verify:

```text
colored scroll range == edit scroll range
gutter scroll range  == edit scroll range
scroll x/y synchronized
```

Highlighting is done with Python's standard `tokenize` module. If the code is
temporarily invalid while being typed, it falls back to regex highlighting so
editing never stops. The pugixml layer under `RichText` drops whitespace-only
text nodes (which would remove indentation and spaces between words), so the
generated markup merges whitespace runs into adjacent non-empty runs, preserving
both indentation and spaces.

## Code structure

```
pymat/
  session.py        Python namespace, REPL, workspace
  mpl.py            matplotlib <-> dui figure bridge (plt.show/close)
  cli.py            GUI/REPL/script entry point
  gui/
    main_window.py   two-column main window: Console/Workspace/Files left, editor right
    code_editor.py   syntax highlighting + line numbers + scroll sync
    figure_window.py matplotlib figure window (PNG background + redraw on resize)
    app.py           Session + main window + figure wiring
    theme.py         colors, syntax palette, small widgets
tests/
  test_core.py         namespace / numpy / pandas / scipy / matplotlib
  test_code_editor.py  highlight markup, line height, scroll sync
  test_gui_smoke.py    real dui window: run example, open figure, workspace
  test_layout.py       two-column layout and control geometry
  test_live_editor.py  highlight refresh after input in the message loop
  test_live_plot.py    plt.show() in the message loop
  test_sim.py          pysimu engine / block-diagram window / save-load
examples/
  numpy_pandas.py      numpy / pandas / scipy
  plot_demo.py         matplotlib
```

## Tests

```sh
conda activate pymat
python tests/test_core.py          # no GUI
python tests/test_code_editor.py   # needs a desktop session
python tests/test_gui_smoke.py
python tests/test_layout.py
python tests/test_live_editor.py
python tests/test_live_plot.py
```

## License

MIT. See the pydui / dui repositories for their respective licenses.
