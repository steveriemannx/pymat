"""Headless checks for the session, the scientific stack and matplotlib figures."""

import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymat import Session, mpl


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.session = Session()

    def run_line(self, line):
        done, result = self.session.feed(line)
        self.assertTrue(done, line)
        self.assertEqual(result.error, "", line)
        return result.output

    def test_scientific_stack_is_loaded(self):
        for alias in ("np", "pd", "sp", "plt"):
            self.assertIn(alias, self.session.ns)
        self.assertIs(self.session.ns["np"], np)
        self.assertIs(self.session.ns["pd"], pd)
        self.assertIs(self.session.ns["plt"], mpl.plt)

    def test_no_matlab_catalogue(self):
        import pymat
        for name in ("mat", "zeros", "ones", "mldivide", "colon", "disp"):
            self.assertFalse(hasattr(pymat, name), name)

    def test_assignment_does_not_echo(self):
        self.assertEqual(self.run_line("x = 3"), "")
        self.assertEqual(self.session.ns["x"], 3)

    def test_expression_prints_repr_and_stores_last_value(self):
        self.assertEqual(self.run_line("x = 3"), "")
        self.assertEqual(self.run_line("x * 2").strip(), "6")
        self.assertEqual(self.session.ns["_"], 6)

    def test_numpy(self):
        self.run_line("A = np.array([[4.0, -2.0], [1.0, 1.0]])")
        self.run_line("b = np.array([6.0, 3.0])")
        out = self.run_line("np.linalg.solve(A, b)")
        self.assertIn("2.", out)
        self.assertIn("1.", out)
        out = self.run_line("A.T @ A")
        self.assertIn("array(", out)

    def test_pandas(self):
        self.run_line('df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})')
        out = self.run_line("df")
        self.assertIn("a", out)
        self.assertIn("3", out)
        names = {v.name: v for v in self.session.workspace()}
        self.assertEqual(names["df"].kind, "DataFrame")
        self.assertEqual(names["df"].size, "2x2")

    def test_scipy(self):
        out = self.run_line(
            "sp.linalg.inv(np.array([[4.0, -2.0], [1.0, 1.0]]))")
        self.assertIn("0.1666", out)
        out = self.run_line("sp.stats.norm.pdf(0.0, 0.0, 1.0)")
        self.assertIn("0.3989", out)

    def test_pure_python_syntax_only(self):
        done, result = self.session.feed("x = 1:5")
        self.assertTrue(done)
        self.assertIn("SyntaxError", result.error)
        done, result = self.session.feed("A = [1 2 3]")
        self.assertTrue(done)
        self.assertIn("SyntaxError", result.error)
        self.run_line("A = [1, 2, 3]")
        self.assertEqual(self.session.ns["A"], [1, 2, 3])

    def test_error_is_reported_not_raised(self):
        done, result = self.session.feed("1/0")
        self.assertTrue(done)
        self.assertIn("ZeroDivisionError", result.error)

    def test_multiline_block(self):
        self.assertTrue(self.session.feed("for i in range(2):")[0] is False)
        done, result = self.session.feed("    print(i)")
        self.assertTrue(done)
        self.assertEqual(result.error, "")
        self.assertEqual(result.output.strip(), "0\n1")

    def test_workspace_numpy(self):
        self.run_line("A = np.zeros((2, 3))")
        names = {v.name: v for v in self.session.workspace()}
        self.assertEqual(names["A"].size, "2x3")
        self.assertIn("ndarray", names["A"].kind)

    def test_run_file(self):
        path = os.path.join(tempfile.mkdtemp(), "script.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("import numpy as np\nprint(np.arange(3).sum())\n")
        result = self.session.run_file(path)
        self.assertEqual(result.error, "")
        self.assertEqual(result.output.strip(), "3")


class MatplotlibTests(unittest.TestCase):
    def test_figures_are_python_figures(self):
        import matplotlib.pyplot as plt

        plt.close("all")
        figure = plt.figure()
        plt.plot([1, 2, 3], [3, 1, 2])
        self.assertEqual(plt.get_fignums(), [figure.number])
        path = os.path.join(tempfile.gettempdir(), "pymat-test-plot.png")
        figure.savefig(path)
        self.assertTrue(os.path.exists(path) and os.path.getsize(path) > 1000)
        os.unlink(path)
        # No desktop attached: show() must be a quiet no-op, not a Tk popup.
        plt.show()
        plt.close("all")

    def test_render_png(self):
        import matplotlib.pyplot as plt

        plt.close("all")
        figure = plt.figure()
        plt.plot([1, 2, 3], [3, 1, 2])
        path = mpl.render_png(figure, 400, 300)
        self.assertTrue(os.path.exists(path))
        plt.close("all")


if __name__ == "__main__":
    unittest.main(verbosity=2)
