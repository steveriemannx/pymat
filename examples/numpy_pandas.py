"""numpy / pandas / scipy examples -- run with: python examples/numpy_pandas.py"""

import numpy as np
import pandas as pd
import scipy.linalg as la
import scipy.stats as stats

A = np.array([[4.0, -2.0], [1.0, 1.0]])
b = np.array([6.0, 3.0])

print("A =\n", A)
print("solve(A, b) =", la.solve(A, b))
print("inv(A) =\n", la.inv(A))
print("eigvals(A) =", la.eigvals(A))

df = pd.DataFrame({
    "x": np.arange(1, 6),
    "square": np.arange(1, 6) ** 2,
    "normal_pdf": stats.norm.pdf(np.arange(1, 6), 3, 1),
})
print(df)
print(df.describe())

print("mean:", df["square"].mean(), "corr:", df["x"].corr(df["square"]))
