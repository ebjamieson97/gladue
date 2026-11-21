"""Compare ways of identifying sentencing decisions against the labelled sample.

    python scripts/evaluation/compare_methods.py dev      # development set only (for designing rules)
    python scripts/evaluation/compare_methods.py test     # held-out test set + repeated random splits
    python scripts/evaluation/compare_methods.py errors   # list dev-set mistakes of one method (--method NAME)

"Sentencing decision" (the target) = labelled IMPOSES or REVIEWS.
All figures are weighted, so they estimate results over every criminal decision in
the eight courts, not just the sample.
"""
import argparse
import sys
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_v2  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "data" / "labels" / "labels.csv"
FEATURES = (ROOT / "data" / "processed" / "eval_features.parquet").as_posix()
SIGNALS = (ROOT / "data" / "processed" / "criminal_decisions_signals.parquet").as_posix()

COUNTS = ["n_sentenc", "n_head", "n_open", "n_close", "n_close500", "n_aggmit", "n_vocab", "n_fit",
          "n_reports", "n_operative", "n_dispo", "n_appeal_phrase", "n_conv_appeal", "n_voirdire",
          "n_bail", "n_guilty_plea", "n_do"]
FLAGS = ["trial_court", "title_trial", "title_appeal", "statute718", "dispo_close", "abandoned",
         "bail_open", "bail_close", "newtrial_close", "not_decided", "proc_open", "chambers", "scc"]


def load_population() -> pd.DataFrame:
    con = duckdb.connect()
    df = con.sql(f"""
        SELECT f.*, s.rules_v2_tier AS production_tier
        FROM '{FEATURES}' f JOIN '{SIGNALS}' s USING (court, citation)
    """).df()
    df["density"] = df["n_sentenc"] * 10000.0 / df["n_chars"]
    return df


def rules_v1(d, brief: bool):
    """Rules version 1.0, kept here so the comparison does not depend on the production output."""
    bail = (d.bail_open == 1) & (d.bail_close == 1)
    core = (((d.title_trial == 1) | (d.title_appeal == 1)) & (d.n_sentenc >= 3)
            | (d.n_sentenc >= 10) & (d.n_close >= 1)
            | (d.n_sentenc >= 10) & (d.statute718 == 1) & (d.density >= 8)
            | (d.n_sentenc >= 25) & (d.density >= 8))
    sel = core | ((d.n_sentenc >= 3) & (d.n_open >= 1) & (d.n_close >= 1)) if brief else core
    return sel & ~bail


def model_matrix(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame({f"log_{c}": np.log1p(df[c]) for c in COUNTS})
    for c in FLAGS:
        X[c] = df[c]
    X["log_chars"] = np.log(df["n_chars"])
    X["density"] = np.minimum(df["density"], 100)
    X["first_pos"] = df["first_pos"]
    return X


# ---------------------------------------------------------------- fixed methods
FIXED = {
    "Original idea: cites s.718 or 10+ mentions": lambda d: (d.statute718 == 1) | (d.n_sentenc >= 10),
    "Count only: 3+ mentions": lambda d: d.n_sentenc >= 3,
    "Count only: 5+ mentions": lambda d: d.n_sentenc >= 5,
    "Count only: 10+ mentions": lambda d: d.n_sentenc >= 10,
    "Rules v1.0, core only": lambda d: rules_v1(d, brief=False),
    "Rules v1.0, core + brief": lambda d: rules_v1(d, brief=True),
}
FIXED.update(rules_v2.METHODS)
# What scripts/build_sentencing_data.py currently produces (should match v2f / v2g).
FIXED["Production pipeline, core only"] = lambda d: d.production_tier == "core"
FIXED["Production pipeline, core + brief"] = lambda d: d.production_tier.isin(["core", "brief"])

# ---------------------------------------------------------------- fitted methods
FITTED = {
    "Fitted: decision tree (depth 3)": lambda: DecisionTreeClassifier(max_depth=3, min_weight_fraction_leaf=0.02, random_state=0),
    "Fitted: decision tree (depth 4)": lambda: DecisionTreeClassifier(max_depth=4, min_weight_fraction_leaf=0.02, random_state=0),
    "Fitted: logistic regression": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=5000)),
    "Fitted: gradient boosting": lambda: GradientBoostingClassifier(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0),
}


def fit(make, X, y, w):
    model = make()
    if hasattr(model, "steps"):
        model.fit(X, y, logisticregression__sample_weight=w)
    else:
        model.fit(X, y, sample_weight=w)
    return model


def prf(y, pred, w):
    y, pred, w = np.asarray(y, bool), np.asarray(pred, bool), np.asarray(w, float)
    tp, fp, fn = (w * (y & pred)).sum(), (w * (~y & pred)).sum(), (w * (y & ~pred)).sum()
    p = tp / (tp + fp) if tp + fp else np.nan
    r = tp / (tp + fn) if tp + fn else np.nan
    f = 2 * p * r / (p + r) if p + r else np.nan
    return p, r, f


def bootstrap(y, pred, w, strata, reps=2000, seed=0):
    rng = np.random.default_rng(seed)
    idx_by = [np.flatnonzero(strata == s) for s in np.unique(strata)]
    out = []
    for _ in range(reps):
        idx = np.concatenate([rng.choice(ix, len(ix)) for ix in idx_by])
        out.append(prf(y[idx], pred[idx], w[idx]))
    return np.nanpercentile(np.array(out), [2.5, 97.5], axis=0)


def final_evaluation(df, X, y, w, strata, pop, target, folds=5, seed=0):
    """Fixed rules: scored on the round-2 decisions they were never tuned on, and on all labels.
    Fitted models: 5-fold cross-validation over all labelled decisions (folds stratified)."""
    new = (df.split == "new").values
    print(f"Target: {target}.  {len(df)} labelled decisions ({int(y.sum())} sentencing); "
          f"{new.sum()} of them are new (round 2) and were never used to design rules.\n")

    rng = np.random.default_rng(seed)
    fold = np.empty(len(df), int)
    for s in np.unique(strata):
        ix = np.flatnonzero(strata == s)
        fold[rng.permutation(ix)] = np.arange(len(ix)) % folds
    Xpop = model_matrix(pop)

    print(f"{'method':46s} {'new decisions only':>22s} {'all labelled':>22s} {'selected':>10s}")
    print(f"{'':46s} {'precision':>11s}{'recall':>11s} {'precision':>11s}{'recall':>11s}")
    for name, fn in FIXED.items():
        pred = fn(df).values
        p1, r1, _ = prf(y[new], pred[new], w[new])
        p2, r2, _ = prf(y, pred, w)
        print(f"{name:46s} {p1:11.1%}{r1:11.1%} {p2:11.1%}{r2:11.1%} {int(fn(pop).sum()):10,d}")

    print(f"\nFitted models, {folds}-fold cross-validation on all {len(df)} labelled decisions:")
    for name, make in FITTED.items():
        oof = np.zeros(len(df), bool)
        for k in range(folds):
            tr, te = fold != k, fold == k
            oof[te] = fit(make, X[tr], y[tr], w[tr]).predict(X[te]).astype(bool)
        p1, r1, _ = prf(y[new], oof[new], w[new])
        p2, r2, _ = prf(y, oof, w)
        n_sel = int(fit(make, X, y, w).predict(Xpop).sum())
        print(f"{name:46s} {p1:11.1%}{r1:11.1%} {p2:11.1%}{r2:11.1%} {n_sel:10,d}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["dev", "test", "errors", "final"])
    ap.add_argument("--method", default="Rules v1.0, core only")
    ap.add_argument("--target", choices=["main", "full", "broad"], default="main",
                    help="main = IMPOSES/REVIEWS; full = those with a full discussion; broad = also RELATED")
    ap.add_argument("--repeats", type=int, default=200)
    ap.add_argument("--split", choices=["dev", "test"], default="dev", help="which half to list mistakes from")
    args = ap.parse_args()

    pop = load_population()
    lab = pd.read_csv(LABELS, dtype={"stratum": str})
    df = lab.merge(pop, on=["court", "citation"], how="left", suffixes=("", "_f"))
    assert df["n_sentenc_f"].notna().all()
    df["n_sentenc"] = df["n_sentenc_f"]
    df["n_chars"] = df["n_chars_f"]
    sent = df.label.isin(["IMPOSES", "REVIEWS"])
    df["y"] = {"main": sent, "full": sent & (df.depth == "FULL"),
               "broad": sent | (df.label == "RELATED")}[args.target]
    X = model_matrix(df)
    dev, test = (df.split == "dev").values, (df.split == "test").values
    y, w, strata = df.y.values, df.weight.values, df.stratum.values

    if args.stage == "final":
        final_evaluation(df, X, y, w, strata, pop, args.target)
        return

    if args.stage == "errors":
        pred = FIXED[args.method](df).values
        half = dev if args.split == "dev" else test
        for kind, mask in (("MISSED (labelled sentencing, not selected)", half & y & ~pred),
                           ("WRONGLY SELECTED (selected, not labelled sentencing)", half & ~y & pred)):
            sub = df[mask].sort_values("n_sentenc")
            print(f"\n=== {kind}: {len(sub)} dev items, weighted {sub.weight.sum():,.0f}")
            cols = ["id", "citation", "label", "depth", "n_sentenc", "n_chars", "n_open", "n_close", "title_trial",
                    "title_appeal", "statute718", "dispo_close", "n_dispo", "abandoned", "n_aggmit", "n_fit",
                    "n_operative", "bail_open", "newtrial_close", "n_conv_appeal", "note"]
            with pd.option_context("display.width", 320, "display.max_columns", 40, "display.max_rows", 200,
                                   "display.max_colwidth", 60):
                print(sub[cols].to_string(index=False))
        return

    part = dev if args.stage == "dev" else test
    print(f"Target: {args.target}.  {args.stage} set: {part.sum()} labelled decisions "
          f"({int(y[part].sum())} sentencing).  Fitted methods are trained on the dev set only.\n")
    preds = {name: fn(df).values for name, fn in FIXED.items()}
    models = {}
    for name, make in FITTED.items():
        models[name] = fit(make, X[dev], y[dev], w[dev])
        preds[name] = models[name].predict(X).astype(bool)

    Xpop = model_matrix(pop)
    print(f"{'method':46s} {'precision':>18s} {'recall':>18s} {'F1':>7s} {'selected':>9s}")
    for name, pred in preds.items():
        p, r, f = prf(y[part], pred[part], w[part])
        lo, hi = bootstrap(y[part], pred[part], w[part], strata[part])
        n_sel = int(FIXED[name](pop).sum()) if name in FIXED else int(models[name].predict(Xpop).sum())
        print(f"{name:46s} {p:6.1%} ({lo[0]:4.0%}-{hi[0]:4.0%}) {r:6.1%} ({lo[1]:4.0%}-{hi[1]:4.0%}) {f:7.1%} {n_sel:9,d}")
    if args.stage == "dev":
        print("\nNote: fitted methods were trained on these same decisions, so their dev scores flatter them.")
        print("Fairer dev scores for fitted methods (cross-validation inside the dev set, 5 folds x 20 repeats):")
        dev_idx = np.flatnonzero(dev)
        rng = np.random.default_rng(2)
        for name, make in FITTED.items():
            runs = []
            for _ in range(20):
                fold = np.empty(len(dev_idx), int)
                for s in np.unique(strata[dev_idx]):
                    ix = np.flatnonzero(strata[dev_idx] == s)
                    fold[rng.permutation(ix)] = np.arange(len(ix)) % 5
                oof = np.zeros(len(dev_idx), bool)
                for k in range(5):
                    tr, te = dev_idx[fold != k], dev_idx[fold == k]
                    oof[fold == k] = fit(make, X.iloc[tr], y[tr], w[tr]).predict(X.iloc[te]).astype(bool)
                runs.append(prf(y[dev_idx], oof, w[dev_idx]))
            m = np.mean(runs, 0)
            print(f"   {name:43s} precision {m[0]:6.1%}  recall {m[1]:6.1%}  F1 {m[2]:6.1%}")
        tree = models["Fitted: decision tree (depth 3)"]
        print("\nDecision tree (depth 3) learned from the dev set:\n" + export_text(tree, feature_names=list(X.columns)))
        lr = models["Fitted: logistic regression"].named_steps["logisticregression"]
        coefs = sorted(zip(X.columns, lr.coef_[0]), key=lambda t: -abs(t[1]))[:12]
        print("Logistic regression, strongest signals:", ", ".join(f"{c} {v:+.2f}" for c, v in coefs))
        return

    # Repeated random splits: refit the fitted methods each time, score everything on the held-out part.
    print(f"\nRepeated random splits ({args.repeats} x: 60% to fit, 40% to score). Mean, with the middle 95% of runs.")
    rng = np.random.default_rng(1)
    res = {name: [] for name in list(FIXED) + list(FITTED)}
    idx_by = [np.flatnonzero(strata == s) for s in np.unique(strata)]
    for _ in range(args.repeats):
        te = np.zeros(len(df), bool)
        for ix in idx_by:
            te[rng.choice(ix, int(round(0.4 * len(ix))), replace=False)] = True
        tr = ~te
        for name, fn in FIXED.items():
            res[name].append(prf(y[te], preds[name][te], w[te]))
        for name, make in FITTED.items():
            m = fit(make, X[tr], y[tr], w[tr])
            res[name].append(prf(y[te], m.predict(X[te]).astype(bool), w[te]))
    print(f"{'method':46s} {'precision':>18s} {'recall':>18s} {'F1':>18s}")
    for name, vals in res.items():
        a = np.array(vals)
        m, lo, hi = np.nanmean(a, 0), np.nanpercentile(a, 2.5, 0), np.nanpercentile(a, 97.5, 0)
        print(f"{name:46s} " + " ".join(f"{m[i]:6.1%} ({lo[i]:4.0%}-{hi[i]:4.0%})" for i in range(3)))


if __name__ == "__main__":
    main()
