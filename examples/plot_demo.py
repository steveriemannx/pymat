"""matplotlib examples -- run with: python examples/plot_demo.py

In the pymat desktop the same code opens pymat figure windows when plt.show()
is called; from a plain terminal it renders pymat_demo.png instead.
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pymat.mpl  # installs the Agg backend and the pymat plt.show bridge
import numpy as np

plt.close("all")
fig, axes = plt.subplots(2, 2, figsize=(8, 5))

t = np.linspace(0, 2 * np.pi, 400)
axes[0, 0].plot(t, np.sin(t), label="sin")
axes[0, 0].plot(t, np.cos(t), label="cos")
axes[0, 0].set_title("sin / cos")
axes[0, 0].legend()
axes[0, 0].grid(True, alpha=0.3)

rng = np.random.default_rng(0)
axes[0, 1].hist(rng.normal(size=500), bins=24)
axes[0, 1].set_title("normal sample")

axes[1, 0].imshow(np.arange(144).reshape(12, 12), cmap="viridis")
axes[1, 0].set_title("imshow")

x, y = np.meshgrid(np.linspace(-2, 2, 60), np.linspace(-2, 2, 60))
axes[1, 1].contour(x, y, np.exp(-(x ** 2 + y ** 2)) * 3)
axes[1, 1].set_title("contour")

fig.tight_layout()
out = os.path.join(os.getcwd(), "pymat_demo.png")
fig.savefig(out)
print("saved", out)
plt.show()
