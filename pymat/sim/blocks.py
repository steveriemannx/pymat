"""Block types for pymat's Simulink-style simulation engine.

The design follows the same idea as simupy -- a block exposes outputs and state
derivatives in terms of time, state and inputs, and a diagram wires the blocks
together -- but the implementation here is deliberately small and maintained as
part of pymat.

Signals are scalar floats.  A block with ``direct = False`` (an integrator, for
example) breaks algebraic loops because its output is a state, not a function of
the current input.
"""

from __future__ import annotations

from typing import Any

import numpy as np

__all__ = [
    "Block", "Integrator", "Derivative", "Gain", "Sum", "Product", "Divide",
    "Abs", "MathFunction", "MinMax", "Sign", "Bias", "DeadZone", "Compare",
    "Switch", "LogicalOperator", "Constant", "Step", "Sine", "Ramp", "Clock",
    "Pulse", "TransferFunction", "StateSpace", "PID", "Saturation", "Scope",
    "Terminator", "BLOCK_TYPES", "make_block",
]


class Block:
    kind = "Block"
    n_inputs = 1
    n_outputs = 1
    n_states = 0
    direct = True
    title = "Block"

    def __init__(self, **params: Any) -> None:
        self.params = dict(params)
        self.name = params.pop("name", None) or self.kind

    # -- state / evaluation ------------------------------------------------
    def state0(self) -> np.ndarray:
        return np.zeros(self.n_states)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return 0.0

    def derivative(self, t: float, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        return np.zeros(self.n_states)

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "params": dict(self.params)}

    def display_params(self) -> str:
        return ""


class Integrator(Block):
    kind = "Integrator"
    title = "Integrator"
    n_states = 1
    direct = False

    def __init__(self, initial: float = 0.0, **kwargs: Any) -> None:
        super().__init__(initial=initial, **kwargs)
        self.initial = float(initial)

    def state0(self) -> np.ndarray:
        return np.array([self.initial], dtype=float)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return float(x[0])

    def derivative(self, t: float, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        return np.array([float(u[0]) if len(u) else 0.0])

    def display_params(self) -> str:
        return f"x0={self.initial:g}"


class Derivative(Block):
    """A filtered derivative, y ~= du/dt.

    A mathematically pure derivative has no causal state representation, so
    this block uses the usual practical approximation: a first-order filter
    whose output is the filter's own derivative.

        dx/dt = (u - x) / tau
        y     = (u - x) / tau

    With a small tau it tracks du/dt closely without introducing an
    algebraic loop.
    """

    kind = "Derivative"
    title = "Derivative"
    n_states = 1
    direct = True

    def __init__(self, tau: float = 0.01, **kwargs: Any) -> None:
        super().__init__(tau=tau, **kwargs)
        self.tau = max(1e-6, float(tau))

    def state0(self) -> np.ndarray:
        return np.zeros(1, dtype=float)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        error = float(u[0]) if len(u) else 0.0
        return (error - float(x[0])) / self.tau

    def derivative(self, t: float, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        error = float(u[0]) if len(u) else 0.0
        return np.array([(error - float(x[0])) / self.tau])

    def display_params(self) -> str:
        return f"τ={self.tau:g}"


class Gain(Block):
    kind = "Gain"
    title = "Gain"

    def __init__(self, gain: float = 1.0, **kwargs: Any) -> None:
        super().__init__(gain=gain, **kwargs)
        self.gain = float(gain)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return self.gain * (float(u[0]) if len(u) else 0.0)

    def display_params(self) -> str:
        return f"K={self.gain:g}"


class Sum(Block):
    kind = "Sum"
    title = "Sum"

    def __init__(self, signs: str = "++", **kwargs: Any) -> None:
        signs = str(signs) or "++"
        super().__init__(signs=signs, **kwargs)
        self.signs = signs
        self.n_inputs = len(signs)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        total = 0.0
        for index, sign in enumerate(self.signs):
            value = float(u[index]) if index < len(u) else 0.0
            total += value if sign != "-" else -value
        return total

    def display_params(self) -> str:
        return self.signs


def _input(values: np.ndarray, index: int) -> float:
    return float(values[index]) if index < len(values) else 0.0


class Product(Block):
    kind = "Product"
    title = "Product"
    n_inputs = 2

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return _input(u, 0) * _input(u, 1)

    def display_params(self) -> str:
        return "*"


class Divide(Block):
    kind = "Divide"
    title = "Divide"
    n_inputs = 2

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        denominator = _input(u, 1)
        if abs(denominator) < 1e-12:
            return 0.0
        return _input(u, 0) / denominator

    def display_params(self) -> str:
        return "/"


class Abs(Block):
    kind = "Abs"
    title = "Abs"

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return abs(_input(u, 0))

    def display_params(self) -> str:
        return "|u|"


class MathFunction(Block):
    kind = "MathFunction"
    title = "Math Function"

    def __init__(self, op: str = "sin", **kwargs: Any) -> None:
        op = str(op or "sin")
        super().__init__(op=op, **kwargs)
        self.op = op

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        value = _input(u, 0)
        op = self.op
        if op == "cos":
            result = np.cos(value)
        elif op == "tan":
            result = np.tan(value)
        elif op == "tanh":
            result = np.tanh(value)
        elif op == "exp":
            result = np.exp(np.clip(value, -700.0, 700.0))
        elif op == "log":
            result = np.log(max(value, 1e-12))
        elif op == "sqrt":
            result = np.sqrt(max(value, 0.0))
        elif op == "square":
            result = value * value
        elif op == "abs":
            result = abs(value)
        else:
            result = np.sin(value)
        return float(result)

    def display_params(self) -> str:
        return self.op


class MinMax(Block):
    kind = "MinMax"
    title = "MinMax"
    n_inputs = 2

    def __init__(self, mode: str = "max", **kwargs: Any) -> None:
        mode = "min" if str(mode).lower() == "min" else "max"
        super().__init__(mode=mode, **kwargs)
        self.mode = mode

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        a, b = _input(u, 0), _input(u, 1)
        return min(a, b) if self.mode == "min" else max(a, b)

    def display_params(self) -> str:
        return self.mode


class Sign(Block):
    kind = "Sign"
    title = "Sign"

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return float(np.sign(_input(u, 0)))

    def display_params(self) -> str:
        return "sgn"


class Bias(Block):
    kind = "Bias"
    title = "Bias"

    def __init__(self, bias: float = 0.0, **kwargs: Any) -> None:
        super().__init__(bias=bias, **kwargs)
        self.bias = float(bias)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return _input(u, 0) + self.bias

    def display_params(self) -> str:
        return f"b={self.bias:g}"


class DeadZone(Block):
    kind = "DeadZone"
    title = "Dead Zone"

    def __init__(self, lower: float = -0.5, upper: float = 0.5,
                 **kwargs: Any) -> None:
        super().__init__(lower=lower, upper=upper, **kwargs)
        self.lower = float(lower)
        self.upper = float(upper)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        value = _input(u, 0)
        if value > self.upper:
            return value - self.upper
        if value < self.lower:
            return value - self.lower
        return 0.0

    def display_params(self) -> str:
        return f"[{self.lower:g}, {self.upper:g}]"


class Compare(Block):
    kind = "Compare"
    title = "Compare"
    n_inputs = 2

    def __init__(self, op: str = ">", **kwargs: Any) -> None:
        op = str(op or ">")
        super().__init__(op=op, **kwargs)
        self.op = op

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        a, b = _input(u, 0), _input(u, 1)
        result = {
            ">": a > b,
            ">=": a >= b,
            "<": a < b,
            "<=": a <= b,
            "==": a == b,
            "!=": a != b,
        }.get(self.op, a > b)
        return 1.0 if result else 0.0

    def display_params(self) -> str:
        return self.op


class Switch(Block):
    kind = "Switch"
    title = "Switch"
    n_inputs = 3

    def __init__(self, threshold: float = 0.0, **kwargs: Any) -> None:
        super().__init__(threshold=threshold, **kwargs)
        self.threshold = float(threshold)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        if _input(u, 0) >= self.threshold:
            return _input(u, 1)
        return _input(u, 2)

    def display_params(self) -> str:
        return f"≥{self.threshold:g}"


class LogicalOperator(Block):
    kind = "LogicalOperator"
    title = "Logical Op"
    n_inputs = 2

    def __init__(self, op: str = "and", **kwargs: Any) -> None:
        op = str(op or "and").lower()
        super().__init__(op=op, **kwargs)
        self.op = op

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        a, b = _input(u, 0) != 0.0, _input(u, 1) != 0.0
        if self.op == "or":
            result = a or b
        elif self.op == "xor":
            result = a != b
        else:
            result = a and b
        return 1.0 if result else 0.0

    def display_params(self) -> str:
        return self.op.upper()


class Constant(Block):
    kind = "Constant"
    title = "Constant"
    n_inputs = 0
    direct = False

    def __init__(self, value: float = 1.0, **kwargs: Any) -> None:
        super().__init__(value=value, **kwargs)
        self.value = float(value)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return self.value

    def display_params(self) -> str:
        return f"{self.value:g}"


class Step(Block):
    kind = "Step"
    title = "Step"
    n_inputs = 0
    direct = False

    def __init__(self, time: float = 1.0, before: float = 0.0,
                 after: float = 1.0, **kwargs: Any) -> None:
        super().__init__(time=time, before=before, after=after, **kwargs)
        self.time = float(time)
        self.before = float(before)
        self.after = float(after)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return self.before if t < self.time else self.after

    def display_params(self) -> str:
        return f"{self.time:g}: {self.before:g}->{self.after:g}"


class Sine(Block):
    kind = "Sine"
    title = "Sine"
    n_inputs = 0
    direct = False

    def __init__(self, amplitude: float = 1.0, frequency: float = 1.0,
                 phase: float = 0.0, bias: float = 0.0, **kwargs: Any) -> None:
        super().__init__(amplitude=amplitude, frequency=frequency, phase=phase,
                         bias=bias, **kwargs)
        self.amplitude = float(amplitude)
        self.frequency = float(frequency)
        self.phase = float(phase)
        self.bias = float(bias)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return self.bias + self.amplitude * np.sin(
            2.0 * np.pi * self.frequency * t + self.phase)

    def display_params(self) -> str:
        return f"{self.amplitude:g} sin(2π·{self.frequency:g}t)"


class Ramp(Block):
    kind = "Ramp"
    title = "Ramp"
    n_inputs = 0
    direct = False

    def __init__(self, slope: float = 1.0, start: float = 0.0, **kwargs: Any) -> None:
        super().__init__(slope=slope, start=start, **kwargs)
        self.slope = float(slope)
        self.start = float(start)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return max(0.0, t - self.start) * self.slope

    def display_params(self) -> str:
        return f"{self.slope:g}·(t-{self.start:g})+"


class Clock(Block):
    kind = "Clock"
    title = "Clock"
    n_inputs = 0
    direct = False

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return float(t)

    def display_params(self) -> str:
        return "t"


class Pulse(Block):
    kind = "Pulse"
    title = "Pulse"
    n_inputs = 0
    direct = False

    def __init__(self, amplitude: float = 1.0, period: float = 1.0,
                 duty: float = 0.5, phase: float = 0.0,
                 **kwargs: Any) -> None:
        super().__init__(amplitude=amplitude, period=period, duty=duty,
                         phase=phase, **kwargs)
        self.amplitude = float(amplitude)
        self.period = max(1e-9, float(period))
        self.duty = min(1.0, max(0.0, float(duty)))
        self.phase = float(phase)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        fraction = ((t / self.period) + self.phase) % 1.0
        return self.amplitude if fraction < self.duty else 0.0

    def display_params(self) -> str:
        return f"{self.amplitude:g} {self.period:g}s {self.duty * 100:g}%"


class StateSpace(Block):
    kind = "StateSpace"
    title = "State Space"

    def __init__(self, A: Any, B: Any, C: Any, D: Any,
                 x0: Any = None, **kwargs: Any) -> None:
        A = np.atleast_2d(np.asarray(A, dtype=float))
        B = np.atleast_2d(np.asarray(B, dtype=float))
        C = np.atleast_2d(np.asarray(C, dtype=float))
        D = np.atleast_2d(np.asarray(D, dtype=float))
        super().__init__(A=A.tolist(), B=B.tolist(), C=C.tolist(),
                         D=D.tolist(), x0=None if x0 is None else np.asarray(x0).tolist(),
                         **kwargs)
        self.A, self.B, self.C, self.D = A, B, C, D
        self.x0 = np.zeros(A.shape[0]) if x0 is None else np.asarray(x0, dtype=float)
        self.n_states = A.shape[0]
        self.n_inputs = B.shape[1]
        self.n_outputs = C.shape[0]
        self.direct = bool(np.any(D != 0))

    def state0(self) -> np.ndarray:
        return self.x0.copy()

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> Any:
        y = self.C @ x[:self.n_states] + self.D @ u[:self.n_inputs]
        return float(y[0]) if self.n_outputs == 1 else y

    def derivative(self, t: float, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        return self.A @ x[:self.n_states] + self.B @ u[:self.n_inputs]

    def display_params(self) -> str:
        return f"order {self.n_states}"


class TransferFunction(StateSpace):
    kind = "TransferFunction"
    title = "Transfer Fcn"

    def __init__(self, num: Any = (1.0,), den: Any = (1.0, 1.0),
                 **kwargs: Any) -> None:
        from scipy import signal

        num_list = [float(v) for v in np.atleast_1d(num)]
        den_list = [float(v) for v in np.atleast_1d(den)]
        if not den_list or den_list[0] == 0:
            den_list = [1.0]
        A, B, C, D = signal.tf2ss(num_list, den_list)
        prev = kwargs.pop("name", None)
        super().__init__(A, B, C, D, **kwargs)
        self.num = num_list
        self.den = den_list
        if prev:
            self.name = prev
        self.params = {"num": num_list, "den": den_list}
        if prev:
            self.params["name"] = prev

    def display_params(self) -> str:
        return f"num={self.num} den={self.den}"


class PID(Block):
    kind = "PID"
    title = "PID"
    n_states = 2
    direct = True

    def __init__(self, kp: float = 1.0, ki: float = 0.0, kd: float = 0.0,
                 tau: float = 0.02, **kwargs: Any) -> None:
        super().__init__(kp=kp, ki=ki, kd=kd, tau=tau, **kwargs)
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.tau = max(1e-6, float(tau))

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        error = float(u[0]) if len(u) else 0.0
        integral, derivative_state = x[0], x[1]
        d_term = (error - derivative_state) / self.tau
        return self.kp * error + self.ki * integral + self.kd * d_term

    def derivative(self, t: float, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        error = float(u[0]) if len(u) else 0.0
        return np.array([error, (error - x[1]) / self.tau])

    def display_params(self) -> str:
        return f"Kp={self.kp:g} Ki={self.ki:g} Kd={self.kd:g}"


class Saturation(Block):
    kind = "Saturation"
    title = "Saturation"

    def __init__(self, lower: float = -1.0, upper: float = 1.0,
                 **kwargs: Any) -> None:
        super().__init__(lower=lower, upper=upper, **kwargs)
        self.lower = float(lower)
        self.upper = float(upper)

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return float(np.clip(float(u[0]) if len(u) else 0.0,
                             self.lower, self.upper))

    def display_params(self) -> str:
        return f"[{self.lower:g}, {self.upper:g}]"


class Scope(Block):
    kind = "Scope"
    title = "Scope"
    n_outputs = 0
    direct = True

    def output(self, t: float, x: np.ndarray, u: np.ndarray) -> float:
        return 0.0


class Terminator(Scope):
    kind = "Terminator"
    title = "Terminator"


BLOCK_TYPES: dict[str, type[Block]] = {
    "Integrator": Integrator,
    "Derivative": Derivative,
    "Gain": Gain,
    "Sum": Sum,
    "Product": Product,
    "Divide": Divide,
    "Abs": Abs,
    "MathFunction": MathFunction,
    "MinMax": MinMax,
    "Sign": Sign,
    "Bias": Bias,
    "DeadZone": DeadZone,
    "Compare": Compare,
    "Switch": Switch,
    "LogicalOperator": LogicalOperator,
    "Constant": Constant,
    "Step": Step,
    "Sine": Sine,
    "Ramp": Ramp,
    "Clock": Clock,
    "Pulse": Pulse,
    "TransferFunction": TransferFunction,
    "StateSpace": StateSpace,
    "PID": PID,
    "Saturation": Saturation,
    "Scope": Scope,
    "Terminator": Terminator,
}


def make_block(kind: str, params: dict[str, Any] | None = None) -> Block:
    cls = BLOCK_TYPES.get(kind)
    if cls is None:
        raise KeyError(f"unknown block type: {kind!r}")
    return cls(**(params or {}))
