"""How do sentences differ when a systemic factor was treated as mitigating, holding other things equal?

Two kinds of model, each with the same controls:
  1. Length: ordinary least squares on log(prison months), for decisions with a fixed jail term.
  2. Jail or not: logistic regression on whether the sentence includes jail at all, for IMPOSES cases only
     (a trial court sentencing the offender itself), where that choice is cleanest.
Add --by-era to also print how the length effect differs by legal era.

Controls: the 11 offence categories (a decision can have several), whether there is more than one, court,
legal era of the decision (see ERAS), first offence (no or minor record accepted as mitigating), guilty plea,
youthful offender, and the stage of the case (trial sentencing, or the appeal outcome). Robust (HC1) standard errors.
Youth sentences (much lower maximums) and decisions that do not fix a sentence are left out of both.

    .venv\\Scripts\\python.exe -X utf8 scripts\\analysis\\sentence_regression.py
"""
import sys
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
CATS = ["homicide", "sexual", "assault", "robbery", "kidnapping", "break_enter", "theft_fraud", "drugs", "weapons",
        "driving", "other"]
# Legal eras, from the timeline on the "What are Gladue factors?" page (start date of each era).
ERAS = [("1_before_718.2e", "1800-01-01"), ("2_718.2e_to_Gladue", "1996-09-03"), ("3_Gladue_to_Ipeelee", "1999-04-23"),
        ("4_Ipeelee_to_C-5", "2012-03-23"), ("5_after_C-5", "2022-11-17")]
FLAGS = ["mitigating_any_systemic", "mitigating_gladue_factors", "mitigating_anti_black_racism", "mitigating_no_record",
         "mitigating_guilty_plea", "mitigating_youth", "offender_indigenous", "imposes"]


def load():
    """Every sentencing decision that fixes an adult sentence, with the jail outcome and (where stated) its length."""
    df = duckdb.sql(f"""
        SELECT court, CAST(decision_date AS DATE) AS date, prison_months, prison_life, prison_indeterminate, prison_time,
               sentence_outcome, {", ".join(FLAGS)}, {", ".join(f"offence_{c}" for c in CATS)}
        FROM read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}')
        WHERE sentence_outcome NOT IN ('no_sentence', 'unclear') AND NOT coalesce(penalty_youth_sentence, false)
    """).df()
    for c in FLAGS + [f"offence_{c}" for c in CATS] + ["prison_life", "prison_indeterminate"]:
        df[c] = df[c].fillna(False).astype(int)
    df["multiple_offences"] = (df[[f"offence_{c}" for c in CATS]].sum(axis=1) > 1).astype(int)
    starts = pd.to_datetime([s for _, s in ERAS])
    df["era"] = [ERAS[np.searchsorted(starts, pd.Timestamp(d), side="right") - 1][0] for d in df["date"]]
    df["stage"] = df["sentence_outcome"]
    # Jail: a stated term, life, indeterminate, or jail of unstated length. No jail: none ordered.
    # "Time served" is left out of the jail model: the offender was jailed before sentence but given no further term.
    df["jail"] = np.where((df["prison_months"] > 0) | (df["prison_life"] == 1) | (df["prison_indeterminate"] == 1)
                          | (df["prison_time"] == "unclear"), 1, np.where(df["prison_months"] == 0, 0, np.nan))
    df["log_months"] = np.log(df["prison_months"].where(df["prison_months"] > 0))
    return df


CONTROLS = (" + ".join(f"offence_{c}" for c in CATS) +
            " + multiple_offences + C(court) + C(era) + mitigating_no_record + mitigating_guilty_plea"
            " + mitigating_youth + C(stage)")


def pct(x):
    return (np.exp(x) - 1) * 100


def length_model(df, label, treatment="mitigating_any_systemic", controls=CONTROLS):
    d = df[df["log_months"].notna()]
    m = smf.ols(f"log_months ~ {treatment} + {controls}", data=d).fit(cov_type="HC1")
    lo, hi = m.conf_int().loc[treatment]
    print(f"  {label:40s} n={int(m.nobs):5d} (mitigated {int(d[treatment].sum()):4d})  {pct(m.params[treatment]):+6.1f}% "
          f"[{pct(lo):+.0f}% to {pct(hi):+.0f}%]  p={m.pvalues[treatment]:.3f}  adj R2={m.rsquared_adj:.3f}")
    return m


def jail_model(df, label, treatment="mitigating_any_systemic", controls=CONTROLS):
    d = df[df["jail"].notna()].copy()
    d["jail"] = d["jail"].astype(int)
    m = smf.logit(f"jail ~ {treatment} + {controls}", data=d).fit(disp=0, cov_type="HC1", maxiter=200)
    ame = m.get_margeff(at="overall").summary_frame().loc[treatment]
    odds = np.exp(m.params[treatment])
    auc = roc_auc_score(d["jail"], m.predict(d))
    t = d[treatment] == 1
    print(f"  {label:40s} n={int(m.nobs):5d} (mitigated {int(t.sum()):4d})  jail rate {d.loc[t, 'jail'].mean():.0%} vs "
          f"{d.loc[~t, 'jail'].mean():.0%}  odds ratio {odds:.2f}  effect {ame['dy/dx'] * 100:+.1f} points "
          f"[{ame['Conf. Int. Low'] * 100:+.1f} to {ame['Cont. Int. Hi.'] * 100:+.1f}]  p={m.pvalues[treatment]:.3f}  "
          f"pseudo R2={m.prsquared:.3f}  AUC={auc:.3f}")
    return m


def crv3(d, treatment, controls=CONTROLS):
    """Leave-one-court-out jackknife standard error (CRV3), and the number of courts G."""
    f = f"log_months ~ {treatment} + {controls}"
    courts = sorted(d["court"].unique())
    G = len(courts)
    bs = np.array([smf.ols(f, data=d[d["court"] != g]).fit().params[treatment] for g in courts])
    return float(np.sqrt((G - 1) / G * np.sum((bs - bs.mean()) ** 2))), G


def summarize_length(m, d, treatment, label, controls=CONTROLS):
    """Key numbers for the website. Standard errors: CRV3 by court; p and 95% range from t with G - 1 df."""
    from scipy import stats
    d = d[d["log_months"].notna()]
    b = float(m.params[treatment])
    se, G = crv3(d, treatment, controls)
    q = stats.t.ppf(0.975, G - 1)
    return {"label": label, "n": int(m.nobs), "treated": int(d[treatment].sum()), "courts": G,
            "beta": round(b, 4), "se": round(se, 4), "p": round(float(2 * stats.t.sf(abs(b / se), G - 1)), 4),
            "pct": round(float(pct(b)), 1), "pct_lo": round(float(pct(b - q * se)), 1), "pct_hi": round(float(pct(b + q * se)), 1),
            "r2": round(float(m.rsquared), 3), "adj_r2": round(float(m.rsquared_adj), 3)}


def summarize_jail(m, d, treatment, label):
    d = d[d["jail"].notna()]
    ame = m.get_margeff(at="overall").summary_frame().loc[treatment]
    t = d[treatment] == 1
    return {"label": label, "n": int(m.nobs), "treated": int(t.sum()),
            "beta": round(float(m.params[treatment]), 4), "se": round(float(m.bse[treatment]), 4),
            "p": round(float(m.pvalues[treatment]), 4), "odds_ratio": round(float(np.exp(m.params[treatment])), 2),
            "ame_pts": round(float(ame["dy/dx"]) * 100, 1), "ame_lo": round(float(ame["Conf. Int. Low"]) * 100, 1),
            "ame_hi": round(float(ame["Cont. Int. Hi."]) * 100, 1),
            "jail_rate_treated": round(float(d.loc[t, "jail"].mean()) * 100, 1),
            "jail_rate_other": round(float(d.loc[~t, "jail"].mean()) * 100, 1),
            "pseudo_r2": round(float(m.prsquared), 3), "auc": round(float(roc_auc_score(d["jail"].astype(int), m.predict(d))), 3)}


def results():
    """The core models' key numbers, for the website's Statistics page."""
    df = load()
    ind = df[df.offender_indigenous == 1]
    imp = df[df.imposes == 1]
    no_stage = CONTROLS.replace(" + C(stage)", "")
    out = {"length": [], "eras": [e for e, _ in ERAS]}
    for label, d, t in [("All sentencing decisions", df, "mitigating_any_systemic"),
                        ("Among Indigenous offenders only", ind, "mitigating_any_systemic"),
                        ("Gladue factors specifically", df, "mitigating_gladue_factors")]:
        out["length"].append(summarize_length(length_model(d, label, t), d, t, label))
    return out


def main():
    df = load()
    print("Decisions by legal era:", df["era"].value_counts().sort_index().to_dict(), "\n")
    ind = df[df.offender_indigenous == 1]

    print("1. PRISON LENGTH (decisions with a fixed jail term): % difference when the factor is mitigating")
    length_model(df, "All decisions")
    length_model(ind, "Indigenous offenders only")
    length_model(df, "Gladue factors specifically", treatment="mitigating_gladue_factors")

    print("\n2. JAIL OR NOT, IMPOSES cases only (a trial court sentencing the offender itself; time served left out)")
    imp = df[df.imposes == 1]
    no_stage = CONTROLS.replace(" + C(stage)", "")          # every IMPOSES case is a trial sentencing
    jail_model(imp, "All IMPOSES decisions", controls=no_stage)
    jail_model(imp[imp.offender_indigenous == 1], "Indigenous offenders only", controls=no_stage)
    jail_model(imp, "Gladue factors specifically", treatment="mitigating_gladue_factors", controls=no_stage)

    if "--by-era" not in sys.argv:          # the era-by-era breakdown is optional
        return

    print("\n3. DID THE EFFECT ON LENGTH CHANGE BY ERA? (one model with era x factor terms)")
    d = df[df["log_months"].notna()]
    m = smf.ols(f"log_months ~ C(era):mitigating_any_systemic + {CONTROLS}", data=d).fit(cov_type="HC1")
    for k, v in m.params.items():
        if k.startswith("C(era)") and ":mitigating" in k:
            era = k.split("T.")[-1].split("]")[0] if "T." in k else k.split("[")[1].split("]")[0]
            n = int(((d["era"] == era) & (d["mitigating_any_systemic"] == 1)).sum())
            if n < 10:                       # too few mitigated cases in this era to estimate anything
                print(f"  {era:22s} mitigated cases {n:4d}   (too few to estimate)")
                continue
            print(f"  {era:22s} mitigated cases {n:4d}   {pct(v):+6.1f}%  p={m.pvalues[k]:.3f}")


if __name__ == "__main__":
    main()
