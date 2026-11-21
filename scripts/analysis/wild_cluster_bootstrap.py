"""Wild cluster restricted bootstrap (WCR) p-values for the three core length models, clustered by court.

Method (MacKinnon, Nielsen and Webb 2023): impose beta = 0, keep the restricted residuals, flip them by court with
Webb six-point weights, re-estimate, and compare the bootstrap t-statistics (CRV1 by court) with the actual one.
Uses the Frisch-Waugh-Lovell form, so each draw is cheap.

    .venv\\Scripts\\python.exe -X utf8 scripts\\analysis\\wild_cluster_bootstrap.py
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import statsmodels.formula.api as smf

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sentence_regression import CONTROLS, load  # noqa: E402

B = 99999
WEBB = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])


def wcr(d, treatment, seed=0):
    model = smf.ols(f"log_months ~ {treatment} + {CONTROLS}", data=d)
    names = model.exog_names
    j = names.index(treatment)
    X, y = model.exog, model.endog
    Z = np.delete(X, j, axis=1)
    Q, _ = np.linalg.qr(Z)
    mz = lambda v: v - Q @ (Q.T @ v)                       # residual-maker for the controls  # noqa: E731
    x = mz(X[:, j])
    u = mz(y)                                              # restricted residuals (beta = 0)
    n, k = X.shape
    groups = d["court"].astype("category").cat.codes.to_numpy()
    G = groups.max() + 1
    c = G / (G - 1) * (n - 1) / (n - k)
    xx = x @ x

    def t_stat(ytil):                                      # ytil: n x m (already residualized)
        b = (x @ ytil) / xx
        e = ytil - np.outer(x, b)
        s = np.zeros((G, ytil.shape[1]))
        np.add.at(s, groups, x[:, None] * e)
        return b / np.sqrt(c * (s ** 2).sum(axis=0) / xx ** 2), b

    t0, b0 = t_stat(mz(y)[:, None])
    rng = np.random.default_rng(seed)
    exceed, done = 0, 0
    while done < B:
        m = min(5000, B - done)
        w = rng.choice(WEBB, size=(G, m))[groups]          # one weight per court per draw
        tb, _ = t_stat(mz(u[:, None] * w))
        exceed += int((np.abs(tb) >= abs(t0[0])).sum())
        done += m
    return float(b0[0]), float(t0[0]), (exceed + 1) / (B + 1), int(G)


def main():
    df = load()
    L = df[df["log_months"].notna()]
    for label, d, t in [("All sentencing decisions", L, "mitigating_any_systemic"),
                        ("Among Indigenous offenders only", L[L.offender_indigenous == 1], "mitigating_any_systemic"),
                        ("Gladue factors specifically", L, "mitigating_gladue_factors")]:
        b, t0, p, G = wcr(d, t)
        print(f"{label:34s} beta={b:+.3f} ({(np.exp(b) - 1) * 100:+.1f}%)  t(CRV1)={t0:+.2f}  "
              f"wild cluster bootstrap p={p:.3f}  ({G} courts, {B:,} draws)")


if __name__ == "__main__":
    main()
