"""Checks for pysimu: engine, persistence and the dui block-diagram window."""

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymat.sim.diagram import AlgebraicLoopError, Diagram, demo_diagram


def test_engine():
    diagram = demo_diagram()
    print("order", diagram.order())
    result = diagram.simulate(10, 400)
    scope_id, scope = result.scope_data()[0]
    print("scope final", scope[-1])
    assert abs(scope[-1] - 0.5) < 0.02

    # Step -> integrator integrates to 2 at t=3.
    diagram = Diagram()
    step = diagram.add_block("Step", {"time": 1.0, "after": 1.0})
    integrator = diagram.add_block("Integrator")
    scope = diagram.add_block("Scope")
    diagram.connect(step, integrator)
    diagram.connect(integrator, scope)
    result = diagram.simulate(3, 200)
    print("integrator final", result.signals[integrator][-1])
    assert abs(result.signals[integrator][-1] - 2.0) < 0.05

    # A direct-feedthrough cycle must be rejected.
    loop = Diagram()
    first = loop.add_block("Gain", {"gain": 1.0})
    second = loop.add_block("Gain", {"gain": 1.0})
    loop.connect(first, second)
    loop.connect(second, first)
    try:
        loop.order()
    except AlgebraicLoopError:
        print("algebraic loop detected")
    else:
        raise AssertionError("algebraic loop was not detected")

    # Persistence keeps kinds, parameters and links.
    data = diagram.to_dict({step: (10, 20), integrator: (100, 20)})
    restored = Diagram.from_dict(data)
    assert len(restored.blocks) == 3
    assert len(restored.links) == 2
    assert restored.blocks[integrator].kind == "Integrator"
    print("SIM ENGINE OK")


def test_gui():
    import dui
    from pymat.gui.app import PymatApp
    from pymat.sim.gui import PysimuWindow

    app = PymatApp(cwd=tempfile.mkdtemp())
    dui.startup()
    main = __import__("pymat.gui.main_window", fromlist=["PymatWindow"]).PymatWindow(app)
    assert main.create_wnd("pymat")
    main.show_window()
    main.update_window()
    main.on_open_pysimu()
    window = app.pysimu_window
    assert window is not None
    window.show_window()
    window.update_window()
    print("sim blocks", len(window.blocks), "links", len(window.diagram.links))
    # A new window starts empty instead of loading a demo diagram.
    assert len(window.blocks) == 0
    assert len(window.diagram.links) == 0

    # Add a block, select it, apply parameters, then connect it.
    bid = window.add_block("Gain", {"gain": 2.5})
    assert bid > 0
    window._click_block(bid)
    assert window.selected == bid
    window._param_edit.set_text("gain=3.5")
    window.on_apply_params()
    assert window.diagram.blocks[bid].gain == 3.5

    window.on_run()
    import matplotlib.pyplot as plt
    print("figure numbers", plt.get_fignums())
    assert plt.get_fignums()

    data = window.diagram.to_dict(window.positions)
    window._load_data(data)
    assert len(window.blocks) == 1

    window.close()
    main.close()
    dui.shutdown()
    print("PYSIMU GUI OK")


if __name__ == "__main__":
    test_engine()
    test_gui()
    print("SIM OK")
