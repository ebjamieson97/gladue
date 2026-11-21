"""Evaluate every method on the two 3,200-decision samples, for two tasks, and save trained models.

Samples
  stratified : the stratum random sample (weighted, so figures estimate the whole collection)
  random     : the purely random sample (unweighted)
Tasks
  sentencing : is this a sentencing decision (label IMPOSES or REVIEWS)?  Scored over all criminal decisions.
  imposes    : among decisions selected by Rules v2.0, does the court impose the sentence (label IMPOSES)?

Fixed rules need no training, so they are scored on the whole sample.
Statistical models are scored by 5-fold cross-validation inside each sample.

Outputs
  data/labels/results_3200.csv   every figure in the tables
  models/                        models trained on all labelled decisions (see models/README.md)

    .venv\\Scripts\\python.exe -X utf8 scripts\\evaluation\\evaluate_3200.py
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
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_methods as cm  # noqa: E402  (fixed rule definitions)
from model_features import FEATURE_NAMES, model_matrix  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data" / "labels"
MODELS = ROOT / "models"
FEATURES = (ROOT / "data" / "processed" / "eval_features.parquet").as_posix()
SIGNALS = (ROOT / "data" / "processed" / "criminal_decisions_signals.parquet").as_posix()
K = 5
SEED = 0

# ------------------------------------------------------------------ fixed rules
SENTENCING_RULES = {
    "Starting idea: cites s. 718, or 10+ mentions": cm.FIXED["Original idea: cites s.718 or 10+ mentions"],
    "Count only: 3+ mentions": cm.FIXED["Count only: 3+ mentions"],
    "Count only: 5+ mentions": cm.FIXED["Count only: 5+ mentions"],
    "Count only: 10+ mentions": cm.FIXED["Count only: 10+ mentions"],
    "Simple: density 8+, or 16+ mentions": cm.FIXED["Simple: density 8+ or 16+ mentions"],
    "Rules v1.0, core": cm.FIXED["Rules v1.0, core only"],
    "Rules v1.0, core + brief": cm.FIXED["Rules v1.0, core + brief"],
    "Rules v2.0, core": cm.FIXED["v2f: v2c with refined exclusions"],
    "Rules v2.0, core + brief": cm.FIXED["v2g: v2f + brief rule"],
}


def v2_selected(d):
    return SENTENCING_RULES["Rules v2.0, core + brief"](d)


# IMPOSES rules. Each is applied to decisions already selected by Rules v2.0.
# They were chosen using only the first 1,000 labelled decisions.
def _trial_no_appeal(d):
    return (d.trial_court == 1) & (d.head_appeal == 0)


IMPOSES_RULES = {
    "Trial court": lambda d: d.trial_court == 1,
    "Trial court, heading shows no appeal": _trial_no_appeal,
    "IMPOSES rules v1.0: also needs a sentencing heading or 10+ mentions":
        lambda d: _trial_no_appeal(d) & ((d.title_trial == 1) | (d.n_sentenc >= 10)),
    "Variant: v1.0, or 2+ sentence terms in the closing":
        lambda d: _trial_no_appeal(d) & ((d.title_trial == 1) | (d.n_sentenc >= 10) | (d.n_close_orders >= 2)),
}

# ------------------------------------------------------------------ statistical models
MODEL_MAKERS = {
    "decision_tree": ("Statistical: decision tree",
                      lambda: DecisionTreeClassifier(max_depth=4, min_weight_fraction_leaf=0.01, random_state=SEED)),
    "logistic_regression": ("Statistical: logistic regression",
                            lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=5000))),
    "gradient_boosting": ("Statistical: gradient boosting",
                          lambda: GradientBoostingClassifier(n_estimators=300, max_depth=3, learning_rate=0.05,
                                                             subsample=0.8, random_state=SEED)),
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
    return (tp / (tp + fp) if tp + fp else np.nan), (tp / (tp + fn) if tp + fn else np.nan)


def folds_for(strata, y, seed=SEED):
    """Assign each row to one of K folds, balanced within stratum and label."""
    rng = np.random.default_rng(seed)
    fold = np.empty(len(strata), int)
    key = pd.Series(strata).astype(str) + "|" + pd.Series(y).astype(str)
    for _, ix in key.groupby(key).groups.items():
        ix = np.asarray(ix)
        fold[rng.permutation(ix)] = np.arange(len(ix)) % K
    return fold


def cross_validated(make, X, y, w, strata, seed=SEED):
    """Out-of-fold predictions, plus (precision, recall) on each held-out fold."""
    fold = folds_for(strata, y, seed)
    oof = np.zeros(len(y), bool)
    per_fold = []
    for k in range(K):
        tr, te = fold != k, fold == k
        oof[te] = fit(make, X[tr], y[tr], w[tr]).predict(X[te]).astype(bool)
        per_fold.append(prf(y[te], oof[te], w[te]))
    return oof, per_fold


FOLD_ROWS = []      # per-fold scores, written to data/labels/results_3200_folds.csv


def report_folds(sample, task, label, per_fold):
    ps, rs = [p for p, _ in per_fold], [r for _, r in per_fold]
    for k, (p, r) in enumerate(per_fold, 1):
        FOLD_ROWS.append([sample, task, label, k, round(p, 4), round(r, 4)])
    print(f"{'':6s}per fold  precision " + " ".join(f"{p:6.1%}" for p in ps) +
          f"   mean {np.mean(ps):6.1%}  range {min(ps):5.1%}-{max(ps):5.1%}")
    print(f"{'':6s}          recall    " + " ".join(f"{r:6.1%}" for r in rs) +
          f"   mean {np.mean(rs):6.1%}  range {min(rs):5.1%}-{max(rs):5.1%}")


HEAD_ROWS = []      # repeated cross-validation, logistic regression against gradient boosting


def head_to_head(sample, X, y, w, strata, repeats=10):
    """Repeat 5-fold cross-validation with different splits; compare the two best models fold by fold."""
    lr_make, gb_make = MODEL_MAKERS["logistic_regression"][1], MODEL_MAKERS["gradient_boosting"][1]
    lr_p, lr_r, gb_p, gb_r = [], [], [], []
    for seed in range(repeats):
        _, a = cross_validated(lr_make, X, y, w, strata, seed)
        _, b = cross_validated(gb_make, X, y, w, strata, seed)
        lr_p += [p for p, _ in a]; lr_r += [r for _, r in a]
        gb_p += [p for p, _ in b]; gb_r += [r for _, r in b]
    lr_p, lr_r, gb_p, gb_r = map(np.array, (lr_p, lr_r, gb_p, gb_r))
    lr_f = 2 * lr_p * lr_r / (lr_p + lr_r)
    gb_f = 2 * gb_p * gb_r / (gb_p + gb_r)
    n = len(lr_p)
    print(f"\n  Logistic regression vs gradient boosting, sentencing task: {repeats} x 5-fold = {n} held-out folds")
    for name, a, b in (("precision", lr_p, gb_p), ("recall", lr_r, gb_r), ("F1", lr_f, gb_f)):
        print(f"    {name:10s} logistic mean {a.mean():6.1%}   boosting mean {b.mean():6.1%}   "
              f"logistic better {(a > b).sum()}/{n}, boosting better {(b > a).sum()}/{n}")
        HEAD_ROWS.append([sample, name, repeats, n, round(a.mean(), 4), round(b.mean(), 4), int((a > b).sum()), int((b > a).sum())])


def load():
    con = duckdb.connect()
    pop = con.sql(f"SELECT f.*, s.rules_v2_tier AS production_tier FROM '{FEATURES}' f JOIN '{SIGNALS}' s USING (court, citation)").df()
    pop["density"] = pop["n_sentenc"] * 10000.0 / pop["n_chars"]
    lab = pd.read_csv(LAB / "labels.csv", dtype={"stratum": str})
    df = lab.drop(columns=["n_sentenc", "n_chars"]).merge(pop, on=["court", "citation"], how="left")
    assert df["n_sentenc"].notna().all(), "labelled decisions missing from the feature table"
    return pop, df


def evaluate_sample(name, df, weights, results):
    """Print both tables for one sample and append rows to results."""
    w = np.asarray(weights, float)
    strata = df.stratum.values
    X = model_matrix(df).values
    sent = df.label.isin(["IMPOSES", "REVIEWS"]).values
    imp = (df.label == "IMPOSES").values
    print(f"\n{'=' * 100}\n{name}: {len(df):,} decisions; labels "
          f"{dict(df.label.value_counts())}\n{'=' * 100}")

    # ---- task 1: sentencing decision or not
    print(f"\nTask 1. Sentencing decision (IMPOSES or REVIEWS) among all criminal decisions")
    print(f"{'method':70s}{'precision':>10s}{'recall':>9s}   how scored")
    for label, fn in SENTENCING_RULES.items():
        p, r = prf(sent, fn(df).values, w)
        print(f"{label:70s}{p:10.1%}{r:9.1%}   whole sample")
        results.append([name, "sentencing", label, "whole sample", len(df), round(p, 4), round(r, 4), ""])
    oof_sentencing = {}
    for key, (label, make) in MODEL_MAKERS.items():
        oof, per_fold = cross_validated(make, X, sent, w, strata)
        oof_sentencing[key] = oof
        p, r = prf(sent, oof, w)
        print(f"{label:70s}{p:10.1%}{r:9.1%}   {K}-fold cross-validation (pooled)")
        report_folds(name, "sentencing", label, per_fold)
        results.append([name, "sentencing", label, f"{K}-fold cross-validation", len(df), round(p, 4), round(r, 4), ""])
    head_to_head(name, X, sent, w, strata)

    # ---- task 2: IMPOSES among decisions selected by the sentencing logistic regression.
    # The subset uses out-of-fold predictions, so no decision is selected by a model trained on it.
    sel = oof_sentencing["logistic_regression"]
    kept = (w * (imp & sel)).sum() / (w * imp).sum()
    d2, w2, X2, imp2, strata2 = df[sel], w[sel], X[sel], imp[sel], strata[sel]
    print(f"\nTask 2. IMPOSES among the {int(sel.sum()):,} decisions selected by the sentencing logistic regression "
          f"({int(imp2.sum()):,} are IMPOSES).  That selection keeps {kept:.1%} of all IMPOSES decisions.")
    print(f"{'method':70s}{'precision':>10s}{'recall':>9s}{'recall, all':>13s}   how scored")
    for label, fn in IMPOSES_RULES.items():
        p, r = prf(imp2, fn(d2).values, w2)
        print(f"{label:70s}{p:10.1%}{r:9.1%}{r * kept:13.1%}   whole sample")
        results.append([name, "imposes", label, "whole sample", int(sel.sum()), round(p, 4), round(r, 4), round(r * kept, 4)])
    for key, (label, make) in MODEL_MAKERS.items():
        oof, per_fold = cross_validated(make, X2, imp2, w2, strata2)
        p, r = prf(imp2, oof, w2)
        print(f"{label:70s}{p:10.1%}{r:9.1%}{r * kept:13.1%}   {K}-fold cross-validation (pooled)")
        report_folds(name, "imposes", label, per_fold)
        results.append([name, "imposes", label, f"{K}-fold cross-validation", int(sel.sum()), round(p, 4), round(r, 4), round(r * kept, 4)])


def unseen_check(df):
    """Fixed rules on decisions that played no part in designing them (everything after the first 1,000).

    For the IMPOSES rules, the decisions are first selected by a sentencing logistic regression trained
    on the first 1,000 labels only, so neither step has seen the decisions being scored."""
    first = df[df.id.str.lstrip("D").astype(int) <= 1000]
    new = df[df.id.str.lstrip("D").astype(int) > 1000]
    lr = fit(MODEL_MAKERS["logistic_regression"][1], model_matrix(first).values,
             first.label.isin(["IMPOSES", "REVIEWS"]).values, first.weight.values)
    imp_rule = IMPOSES_RULES["IMPOSES rules v1.0: also needs a sentencing heading or 10+ mentions"]
    print(f"\n{'=' * 100}\nCheck: fixed rules on decisions never used to design them\n{'=' * 100}")
    for name in ("Stratum random sample, new decisions only", "Random sample, new decisions only"):
        sub = new[new.in_stratified == 1] if "Stratum" in name else new[new.in_random == 1]
        w = sub.weight.values if "Stratum" in name else np.ones(len(sub))
        sent = sub.label.isin(["IMPOSES", "REVIEWS"]).values
        imp = (sub.label == "IMPOSES").values
        p, r = prf(sent, v2_selected(sub).values, w)
        sel = lr.predict(model_matrix(sub).values).astype(bool)
        ip, ir = prf(imp[sel], imp_rule(sub[sel]).values, w[sel])
        print(f"{name} ({len(sub):,}):  Rules v2.0 core + brief  precision {p:.1%} recall {r:.1%}   |   "
              f"IMPOSES rules v1.0 (on logistic-selected)  precision {ip:.1%} recall {ir:.1%}")


def audit(df):
    """Compare the main labels with a second model's labels on the audit subset."""
    rows = []
    for path in sorted((LAB / "raw_audit").glob("labels_audit_*.csv")):
        rows += list(csv.DictReader(path.open(encoding="utf-8-sig")))
    if not rows:
        return
    a = pd.DataFrame(rows)[["id", "label"]].rename(columns={"label": "audit_label"})
    a["audit_label"] = a.audit_label.str.strip().str.upper()
    m = df.merge(a, on="id")
    s1, s2 = m.label.isin(["IMPOSES", "REVIEWS"]), m.audit_label.isin(["IMPOSES", "REVIEWS"])
    print(f"\n{'=' * 100}\nLabel audit: {len(m)} decisions labelled again by a different model\n{'=' * 100}")
    print(f"same of the 4 labels:            {(m.label == m.audit_label).sum()} of {len(m)}")
    print(f"same sentencing / not decision:  {(s1 == s2).sum()} of {len(m)}")
    print(f"same IMPOSES / not decision:     {((m.label == 'IMPOSES') == (m.audit_label == 'IMPOSES')).sum()} of {len(m)}")
    print(pd.crosstab(m.label, m.audit_label).to_string())


def save_models(pop, df):
    """Train each model on every labelled decision and save it."""
    MODELS.mkdir(exist_ok=True)
    # Weight = 1 / chance of being in either sample (stratified draw or purely random draw).
    n_pop = len(pop)
    stratum_size = df.groupby("stratum").stratum_size.first() if "stratum_size" in df else None
    sizes = pop.assign(stratum=pd.cut(pop.n_sentenc, [-1, 0, 2, 9, 24, 10**9], labels=["0", "1-2", "3-9", "10-24", "25+"]).astype(str)).groupby("stratum").size()
    n_strat = df[df.in_stratified == 1].groupby("stratum").size()
    n_rand = int((df.in_random == 1).sum())
    p_incl = 1 - (1 - df.stratum.map(n_strat / sizes)) * (1 - n_rand / n_pop)
    w = (1 / p_incl).values
    X = model_matrix(df).values
    Xpop = model_matrix(pop).values
    sent = df.label.isin(["IMPOSES", "REVIEWS"]).values
    imp = (df.label == "IMPOSES").values
    # The IMPOSES models are trained on the decisions the adopted sentencing model selects.
    sentencing_lr = fit(MODEL_MAKERS["logistic_regression"][1], X, sent, w)
    sel = sentencing_lr.predict(X).astype(bool)
    sel_pop = sentencing_lr.predict(Xpop).astype(bool)
    card = {"trained_on": int(len(df)), "sklearn_version": sklearn.__version__, "feature_names": FEATURE_NAMES,
            "imposes_models_trained_on": "labelled decisions selected by sentencing_logistic_regression",
            "models": {}}
    for task, Xt, yt, wt, Xp in (("sentencing", X, sent, w, Xpop), ("imposes", X[sel], imp[sel], w[sel], Xpop[sel_pop])):
        for key, (label, make) in MODEL_MAKERS.items():
            model = fit(make, Xt, yt, wt)
            name = f"{task}_{key}"
            joblib.dump(model, MODELS / f"{name}.joblib")
            card["models"][name] = {"training_rows": int(len(yt)), "positives": int(yt.sum()),
                                    "selected_in_collection": int(model.predict(Xp).sum())}
            if key == "decision_tree":
                (MODELS / f"{name}.txt").write_text(export_text(model, feature_names=FEATURE_NAMES), encoding="utf-8")
            if key == "logistic_regression":
                sc, lr = model.named_steps["standardscaler"], model.named_steps["logisticregression"]
                (MODELS / f"{name}.json").write_text(json.dumps({
                    "how_to_score": "z = (x - mean) / scale for each input; score = intercept + sum(coef * z); "
                                    "probability = 1 / (1 + exp(-score)); select if probability >= 0.5",
                    "intercept": float(lr.intercept_[0]),
                    "inputs": [{"name": n, "mean": float(m), "scale": float(s), "coef": float(c)}
                               for n, m, s, c in zip(FEATURE_NAMES, sc.mean_, sc.scale_, lr.coef_[0])],
                }, indent=2), encoding="utf-8")
    (MODELS / "model_info.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    print(f"\nSaved {len(card['models'])} models to {MODELS}")
    for k, v in card["models"].items():
        print(f"   {k:32s} trained on {v['training_rows']:,} decisions; selects {v['selected_in_collection']:,} in the collection")


def main():
    pop, df = load()
    print(f"{len(df):,} labelled decisions in total")
    results = []
    strat = df[df.in_stratified == 1].reset_index(drop=True)
    rand = df[df.in_random == 1].reset_index(drop=True)
    evaluate_sample("STRATUM RANDOM SAMPLE (weighted)", strat, strat.weight.values, results)
    evaluate_sample("RANDOM SAMPLE (unweighted)", rand, np.ones(len(rand)), results)
    unseen_check(df)
    audit(df)
    with (LAB / "results_3200.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["sample", "task", "method", "how_scored", "decisions_scored", "precision", "recall", "recall_of_all_imposes"])
        wr.writerows(results)
    with (LAB / "results_3200_folds.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["sample", "task", "method", "fold", "precision", "recall"])
        wr.writerows(FOLD_ROWS)
    with (LAB / "results_3200_head_to_head.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["sample", "measure", "repeats", "folds", "logistic_mean", "boosting_mean",
                     "logistic_better_folds", "boosting_better_folds"])
        wr.writerows(HEAD_ROWS)
    save_models(pop, df)


if __name__ == "__main__":
    main()
