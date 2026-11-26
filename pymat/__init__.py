"""pymat -- a Python scientific desktop built on dui.

The desk is Python: the namespace already contains numpy, pandas, scipy and
matplotlib under their usual aliases (``np``, ``pd``, ``sp``, ``plt``), and every
line typed at the prompt is ordinary CPython.

    >>> np.linalg.inv(np.array([[4, -2], [1, 1]]))
    >>> pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    >>> plt.plot([1, 2, 3], [3, 1, 2]); plt.show()
"""

from .session import ExecResult, Session, VarInfo, install_namespace

__version__ = "0.2.0"

__all__ = ["Session", "ExecResult", "VarInfo", "install_namespace", "__version__"]
