"""Wiring and simulation for the pysimu block types.

The graph is evaluated the way simupy's block diagram is: outputs are computed in
topological order, then every block's state derivative is computed from those
outputs.  Blocks that do not have direct feed-through (integrators, transfer
functions without a D term, sources) break algebraic loops; a loop made only of
direct blocks is rejected with a clear error instead of silently iterating.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .blocks import Block, Scope, make_block

__all__ = ["Diagram", "Link", "SimulationResult", "AlgebraicLoopError",
           "demo_diagram"]


class AlgebraicLoopError(RuntimeError):
    pass


@dataclass
class Link:
    source: int
    target: int
    port: int = 0

    def to_list(self) -> list[int]:
        return [self.source, self.target, self.port]


@dataclass
class SimulationResult:
    t: np.ndarray
    signals: dict[int, np.ndarray]
    diagram: "Diagram"

    def scope_ids(self) -> list[int]:
        return [bid for bid, block in self.diagram.blocks.items()
                if block.kind in ("Scope", "Terminator")]

    def scope_data(self) -> list[tuple[int, np.ndarray]]:
        return [(bid, self.signals[bid]) for bid in self.scope_ids()
                if bid in self.signals]


class Diagram:
    def __init__(self) -> None:
        self.blocks: dict[int, Block] = {}
        self.links: list[Link] = []
        self._next_id = 1

    # -- construction ------------------------------------------------------
    def add_block(self, kind: str, params: dict[str, Any] | None = None,
                  block_id: int | None = None) -> int:
        block = make_block(kind, params)
        bid = self._next_id if block_id is None else int(block_id)
        self.blocks[bid] = block
        self._next_id = max(self._next_id, bid + 1)
        return bid

    def remove_block(self, block_id: int) -> None:
        self.blocks.pop(block_id, None)
        self.links = [link for link in self.links
                      if link.source != block_id and link.target != block_id]

    def connect(self, source: int, target: int, port: int = 0) -> Link:
        if source not in self.blocks or target not in self.blocks:
            raise KeyError("link endpoints must exist")
        if self.blocks[source].n_outputs == 0:
            raise ValueError("source block has no output")
        if not (0 <= int(port) < self.blocks[target].n_inputs):
            raise ValueError(f"input port {port} is out of range")
        # one source per input port
        self.links = [link for link in self.links
                      if not (link.target == target and link.port == port)]
        link = Link(source, target, int(port))
        self.links.append(link)
        return link

    def disconnect(self, source: int, target: int, port: int = 0) -> None:
        self.links = [link for link in self.links
                      if not (link.source == source and link.target == target
                              and link.port == port)]

    def clear(self) -> None:
        self.blocks.clear()
        self.links.clear()
        self._next_id = 1

    # -- ordering ----------------------------------------------------------
    def order(self) -> list[int]:
        dependencies: dict[int, set[int]] = {bid: set() for bid in self.blocks}
        for link in self.links:
            target = self.blocks[link.target]
            # A non-direct block reads its state, not the current input, when it
            # produces its output, so it does not constrain output order.
            if target.direct:
                dependencies[link.target].add(link.source)
        ordered: list[int] = []
        ready = sorted(bid for bid, deps in dependencies.items() if not deps)
        while ready:
            bid = ready.pop(0)
            ordered.append(bid)
            for other, deps in dependencies.items():
                if bid in deps:
                    deps.remove(bid)
                    if not deps and other not in ordered and other not in ready:
                        ready.append(other)
            ready.sort()
        if len(ordered) != len(self.blocks):
            raise AlgebraicLoopError(
                "algebraic loop: add an Integrator or a transfer function "
                "without a feed-through term to break it")
        return ordered

    # -- evaluation --------------------------------------------------------
    def _state_layout(self) -> dict[int, tuple[int, int]]:
        layout = {}
        offset = 0
        for bid, block in self.blocks.items():
            layout[bid] = (offset, offset + block.n_states)
            offset += block.n_states
        return layout

    def _inputs(self, block_id: int, outputs: dict[int, float]) -> np.ndarray:
        block = self.blocks[block_id]
        values = np.zeros(block.n_inputs)
        for link in self.links:
            if link.target != block_id:
                continue
            if link.port >= len(values):
                continue
            values[link.port] = float(outputs.get(link.source, 0.0))
        return values

    def evaluate(self, t: float, state: np.ndarray,
                 layout: dict[int, tuple[int, int]] | None = None
                 ) -> tuple[dict[int, float], np.ndarray]:
        layout = layout or self._state_layout()
        order = self.order()
        outputs: dict[int, float] = {}
        for bid in order:
            block = self.blocks[bid]
            start, stop = layout[bid]
            u = self._inputs(bid, outputs)
            if block.n_outputs:
                outputs[bid] = block.output(t, state[start:stop], u)
            else:
                block.output(t, state[start:stop], u)
                outputs[bid] = 0.0
        derivatives = np.zeros(sum(b.n_states for b in self.blocks.values()))
        for bid, block in self.blocks.items():
            if block.n_states:
                start, stop = layout[bid]
                u = self._inputs(bid, outputs)
                derivatives[start:stop] = block.derivative(
                    t, state[start:stop], u)
        return outputs, derivatives

    # -- simulation --------------------------------------------------------
    def simulate(self, t_final: float = 10.0, points: int = 1000,
                 method: str = "RK45") -> SimulationResult:
        from scipy.integrate import solve_ivp

        t_final = float(t_final)
        times = np.linspace(0.0, t_final, max(2, int(points)))
        layout = self._state_layout()
        x0 = np.concatenate([b.state0() for b in self.blocks.values()]) \
            if self.blocks else np.zeros(0)
        n_states = x0.size
        if n_states:
            def rhs(t: float, state: np.ndarray) -> np.ndarray:
                _, deriv = self.evaluate(t, state, layout)
                return deriv

            sol = solve_ivp(rhs, (0.0, t_final), x0, t_eval=times,
                            method=method, rtol=1e-7, atol=1e-9,
                            max_step=max(t_final / 200.0, 1e-3))
            if not sol.success:
                raise RuntimeError(f"simulation failed: {sol.message}")
            states = sol.y.T
        else:
            states = np.zeros((len(times), 0))

        signals: dict[int, np.ndarray] = {
            bid: np.zeros(len(times)) for bid in self.blocks
        }
        for index, t in enumerate(times):
            outputs, _ = self.evaluate(t, states[index], layout)
            for bid, block in self.blocks.items():
                if block.n_outputs == 0:
                    signals[bid][index] = float(self._inputs(bid, outputs)[0])
                else:
                    signals[bid][index] = outputs.get(bid, 0.0)
        return SimulationResult(times, signals, self)

    # -- persistence -------------------------------------------------------
    def to_dict(self, positions: dict[int, tuple[int, int]] | None = None) -> dict:
        positions = positions or {}
        blocks = []
        for bid in sorted(self.blocks):
            block = self.blocks[bid]
            entry = block.to_dict()
            entry["id"] = bid
            entry["name"] = block.name
            if bid in positions:
                entry["position"] = list(positions[bid])
            blocks.append(entry)
        return {"version": 1, "blocks": blocks,
                "links": [link.to_list() for link in self.links]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Diagram":
        diagram = cls()
        for entry in data.get("blocks", []):
            params = dict(entry.get("params") or {})
            if entry.get("name"):
                params["name"] = entry["name"]
            diagram.add_block(entry["kind"], params, entry.get("id"))
        for source, target, port in data.get("links", []):
            try:
                diagram.connect(int(source), int(target), int(port))
            except (KeyError, ValueError):
                pass
        return diagram


def demo_diagram() -> Diagram:
    """A closed-loop step response: Step -> Sum -> 1/(s²+2s+1) -> Scope."""
    diagram = Diagram()
    step = diagram.add_block("Step", {"time": 1.0, "before": 0.0, "after": 1.0})
    total = diagram.add_block("Sum", {"signs": "+-"})
    plant = diagram.add_block("TransferFunction",
                              {"num": [1.0], "den": [1.0, 2.0, 1.0]})
    scope = diagram.add_block("Scope")
    diagram.connect(step, total, 0)
    diagram.connect(plant, total, 1)
    diagram.connect(total, plant, 0)
    diagram.connect(plant, scope, 0)
    return diagram
