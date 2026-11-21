"""Train and test the offence-category models on the 5,000 labelled sentencing decisions.

One yes/no model per category (a decision can be in several categories).
Scored by 5-fold cross-validation: every decision is classified by a model that never saw it.
Two plain keyword rules are scored on the whole sample for comparison.

Outputs
    data/processed/offence_features.parquet   keyword counts for every selected decision
    data/labels/results_offences.csv          precision and recall per category and method (pooled)
    data/labels/results_offences_folds.csv    the same on each held-out fold
    models/offence_logistic_regression.json   every weight, used by the build script
    models/offence_*.joblib                   the trained models

    .venv\\Scripts\\python.exe -X utf8 scripts\\evaluation\\evaluate_offences.py
"""
import csv
import json
import sys
import warnings
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from enrichment_patterns import (OFFENCE_CATEGORIES, OFFENCE_FEATURE_NAMES, offence_feature_sql,  # noqa: E402
                                 offence_matrix)

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data" / "labels"
MODELS = ROOT / "models"
DATA = (ROOT / "sentencing_data").as_posix()
FEATURES = ROOT / "data" / "processed" / "offence_features.parquet"
K, SEED = 5, 0


def prf(y, pred):
    y, pred = np.asarray(y, bool), np.asarray(pred, bool)
    tp, fp, fn = (y & pred).sum(), (~y & pred).sum(), (y & ~pred).sum()
    return (tp / (tp + fp) if tp + fp else np.nan), (tp / (tp + fn) if tp + fn else np.nan)


def build_features():
    con = duckdb.connect()
    con.sql("SET memory_limit = '3GB'")
    con.sql("SET threads = 4")
    src = f"read_parquet('{DATA}/*/*/decisions.parquet')"
    con.sql(f"COPY ({offence_feature_sql(src)}) TO '{FEATURES.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    return pd.read_parquet(FEATURES)


def make_logistic():
    return LogisticRegression(C=1.0, max_iter=5000)


def make_boosting():
    return GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=SEED)


def main():
    feats = build_features()
    lab = pd.read_csv(LAB / "offence_labels.csv")
    df = lab.merge(feats, on=["court", "citation"], how="left")
    assert df["n_chars"].notna().all()
    unclear = int(df.unclear.sum())
    df = df[df.unclear == 0].reset_index(drop=True)
    print(f"{len(lab):,} labelled decisions; {unclear} set aside because the excerpt did not show the offences; "
          f"{len(df):,} used.  {len(feats):,} selected decisions in the collection.\n")

    Xraw = offence_matrix(df).values
    rng = np.random.default_rng(SEED)
    fold = rng.permutation(len(df)) % K

    results, fold_rows = [], []
    oof = {"logistic": np.zeros((len(df), len(OFFENCE_CATEGORIES)), bool),
           "boosting": np.zeros((len(df), len(OFFENCE_CATEGORIES)), bool)}
    per_fold = {m: {c: [] for c in OFFENCE_CATEGORIES} for m in oof}
    for k in range(K):
        tr, te = fold != k, fold == k
        scaler = StandardScaler().fit(Xraw[tr])
        Xtr, Xte = scaler.transform(Xraw[tr]), scaler.transform(Xraw[te])
        for j, c in enumerate(OFFENCE_CATEGORIES):
            y = df[c].values.astype(bool)
            for name, make, A, B in (("logistic", make_logistic, Xtr, Xte), ("boosting", make_boosting, Xraw[tr], Xraw[te])):
                pred = make().fit(A, y[tr]).predict(B).astype(bool)
                oof[name][te, j] = pred
                per_fold[name][c].append(prf(y[te], pred))

    rules = {"Rule: keyword anywhere in the decision": lambda c: df[f"n_{c}_all"] >= 1,
             "Rule: keyword in the charge wording": lambda c: df[f"n_{c}_charge"] >= 1}
    labels = {"logistic": "Logistic regression (5-fold)", "boosting": "Gradient boosting (5-fold)"}

    print(f"{'category':13s}{'decisions':>10s}   " + "".join(f"{m:>26s}" for m in ["keyword anywhere", "keyword in charge wording",
                                                                                 "logistic regression", "gradient boosting"]))
    print(f"{'':26s}" + "   precision    recall   " * 4)
    truth = df[OFFENCE_CATEGORIES].values.astype(bool)
    for j, c in enumerate(OFFENCE_CATEGORIES):
        y = truth[:, j]
        line = f"{c:13s}{int(y.sum()):>10,d}   "
        for name, fn in rules.items():
            p, r = prf(y, fn(c).values)
            results.append([c, int(y.sum()), name, "whole sample", round(p, 4), round(r, 4)])
            line += f"{p:12.1%}{r:10.1%}    "
        for m in ("logistic", "boosting"):
            p, r = prf(y, oof[m][:, j])
            results.append([c, int(y.sum()), labels[m], "5-fold cross-validation", round(p, 4), round(r, 4)])
            line += f"{p:12.1%}{r:10.1%}    "
            for k, (fp_, fr_) in enumerate(per_fold[m][c], 1):
                fold_rows.append([c, labels[m], k, round(fp_, 4), round(fr_, 4)])
        print(line)

    print("\nAll categories together (every decision-category pair counted once)")
    for m in ("logistic", "boosting"):
        p, r = prf(truth.ravel(), oof[m].ravel())
        exact = (oof[m] == truth).all(axis=1).mean()
        results.append(["ALL", int(truth.sum()), labels[m], "5-fold cross-validation", round(p, 4), round(r, 4)])
        print(f"  {labels[m]:30s} precision {p:6.1%}  recall {r:6.1%}   decisions with every category right: {exact:6.1%}")
        results.append(["EXACT MATCH", len(df), labels[m], "5-fold cross-validation", round(exact, 4), ""])
    for name, fn in rules.items():
        pred = np.column_stack([fn(c).values for c in OFFENCE_CATEGORIES])
        p, r = prf(truth.ravel(), pred.ravel())
        exact = (pred == truth).all(axis=1).mean()
        results.append(["ALL", int(truth.sum()), name, "whole sample", round(p, 4), round(r, 4)])
        results.append(["EXACT MATCH", len(df), name, "whole sample", round(exact, 4), ""])
        print(f"  {name:30s} precision {p:6.1%}  recall {r:6.1%}   decisions with every category right: {exact:6.1%}")

    print("\nPer-fold scores, logistic regression (precision / recall on each held-out fold)")
    for c in OFFENCE_CATEGORIES:
        ps = [p for p, _ in per_fold["logistic"][c]]; rs = [r for _, r in per_fold["logistic"][c]]
        print(f"  {c:13s} precision " + " ".join(f"{p:6.1%}" for p in ps) + f"  mean {np.mean(ps):6.1%} | recall " +
              " ".join(f"{r:6.1%}" for r in rs) + f"  mean {np.mean(rs):6.1%}")

    with (LAB / "results_offences.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "labelled_decisions_in_category", "method", "how_scored", "precision", "recall"])
        w.writerows(results)
    with (LAB / "results_offences_folds.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "method", "fold", "precision", "recall"])
        w.writerows(fold_rows)

    # ---- final models on every labelled decision
    MODELS.mkdir(exist_ok=True)
    scaler = StandardScaler().fit(Xraw)
    Xs = scaler.transform(Xraw)
    Xall = offence_matrix(feats).values
    Xall_s = scaler.transform(Xall)
    spec = {"how_to_score": "z = (x - mean) / scale for each input; for each category, score = intercept + sum(coef * z); "
                            "probability = 1 / (1 + exp(-score)); the category applies if probability >= 0.5",
            "trained_on": int(len(df)), "sklearn_version": sklearn.__version__,
            "inputs": [{"name": n, "mean": float(m), "scale": float(s)} for n, m, s in zip(OFFENCE_FEATURE_NAMES, scaler.mean_, scaler.scale_)],
            "categories": {}}
    lr_models, gb_models = {}, {}
    print(f"\nFinal models trained on all {len(df):,} labelled decisions. Decisions per category in the collection:")
    for c in OFFENCE_CATEGORIES:
        y = df[c].values.astype(bool)
        lr_models[c] = make_logistic().fit(Xs, y)
        gb_models[c] = make_boosting().fit(Xraw, y)
        spec["categories"][c] = {"intercept": float(lr_models[c].intercept_[0]),
                                 "coef": [float(v) for v in lr_models[c].coef_[0]]}
        print(f"   {c:13s} logistic {int(lr_models[c].predict(Xall_s).sum()):6,d}   boosting {int(gb_models[c].predict(Xall).sum()):6,d}")
    (MODELS / "offence_logistic_regression.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    joblib.dump({"scaler": scaler, "models": lr_models, "feature_names": OFFENCE_FEATURE_NAMES}, MODELS / "offence_logistic_regression.joblib")
    joblib.dump({"models": gb_models, "feature_names": OFFENCE_FEATURE_NAMES}, MODELS / "offence_gradient_boosting.joblib")
    print(f"Saved offence models to {MODELS}")


if __name__ == "__main__":
    main()
