"""Build the sentencing dataset from the A2AJ Canadian case law collection.

What it does, in order:
  1. Download  - fetches the latest file for each court from Hugging Face
                 (skipped for any court whose file has not changed).
  2. Classify  - measures text signals in every criminal decision and scores it with the
                 sentencing logistic regression (models/sentencing_logistic_regression.json).
                 A decision is selected when its probability is 0.5 or more.
                 The older Rules v2.0 are still computed and kept as the column rules_v2_tier.
                 Selected decisions from a trial court whose heading shows no appeal are
                 marked imposes = true (the court imposed the sentence itself).
                 Each selected decision also gets:
                   references_gladue    a keyword rule
                   the AI reading       saved in data/labels/decision_labels.csv: offence categories,
                                        the sentence (prison time, other penalties, any placement in a
                                        healing lodge or treatment facility) and mitigating factors.
                                        ai_read = false marks a decision that has not been read yet
                                        (for example one added by a later download); its reading
                                        columns are blank and its offence categories come from the
                                        offence logistic regressions instead (offence_source = model).
  3. Export    - writes the selected sentencing decisions, with full text, to
                 sentencing_data/<province>/<court>/decisions.parquet (compressed).

Run it from the project folder:
    .venv\\Scripts\\python.exe scripts\\build_sentencing_data.py
Options:
    --skip-download     use the files already in data/raw/a2aj
    --courts BCSC ONCA  only process some courts

Both steps are deterministic: the same input text always gives the same result.
The methodology is explained in docs/METHODOLOGY.md. If you change a rule, a threshold or the
model, bump SELECTION_VERSION so outputs can be told apart.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np

RULES_VERSION = "2.0"          # the written rules (kept for reference, column rules_v2_tier)
SELECTION_VERSION = "3.3"      # 3.0 = selection by the sentencing logistic regression; 3.1 adds imposes;
#                                3.2 adds offence categories, the Gladue reference and mitigating factors;
#                                3.3 takes offences, the sentence and mitigating factors from the AI reading
OFFENCE_MODEL = Path(__file__).resolve().parent.parent / "models" / "offence_logistic_regression.json"
DECISION_LABELS = Path(__file__).resolve().parent.parent / "data" / "labels" / "decision_labels.csv"
EXTRACTS = Path(__file__).resolve().parent.parent / "case_extracts" / "extracts.csv"         # optional
SENTENCING_MODEL = Path(__file__).resolve().parent.parent / "models" / "sentencing_logistic_regression.json"
SELECTION_THRESHOLD = 0.5

# --------------------------------------------------------------------------
# Where things live
# --------------------------------------------------------------------------
HF_REPO = "a2aj/canadian-case-law"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "a2aj"
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "sentencing_data"

# court code -> (province folder, court folder, court name)
COURTS = {
    "SCC": ("canada", "supreme_court_of_canada_scc", "Supreme Court of Canada"),
    "ONCA": ("ontario", "court_of_appeal_onca", "Court of Appeal for Ontario"),
    "BCCA": ("british_columbia", "court_of_appeal_bcca", "Court of Appeal for British Columbia"),
    "BCSC": ("british_columbia", "supreme_court_bcsc", "Supreme Court of British Columbia"),
    "NSCA": ("nova_scotia", "court_of_appeal_nsca", "Nova Scotia Court of Appeal"),
    "NSSC": ("nova_scotia", "supreme_court_nssc", "Supreme Court of Nova Scotia"),
    "NSPC": ("nova_scotia", "provincial_court_nspc", "Provincial Court of Nova Scotia"),
    "NLCA": ("newfoundland_and_labrador", "court_of_appeal_nlca", "Court of Appeal of Newfoundland and Labrador"),
}

# --------------------------------------------------------------------------
# THE RULES  (see METHODOLOGY.md)
# All patterns are case-insensitive regular expressions.
# --------------------------------------------------------------------------

# Step 1 - criminal case: the case name is "Crown v. someone" or "someone v. Crown".
CROWN = r"(R\.?|Regina|Rex|HMTQ|HMK|HMQ|The Queen|The King|(His|Her) Majesty\b.*)"
CRIMINAL_NAME = rf"^{CROWN}\s+v\.?\s|\sv\.?\s+{CROWN}\s*$"

# Step 2 - signals measured in each decision.
SENTENCE_WORD = r"sentenc"  # sentence, sentences, sentenced, sentencing
# Heading says the document is a sentencing decision (trial level) ...
TITLE_TRIAL = (
    r"reasons for sentenc|reasons for judgment on sentenc|reasons on sentenc"
    r"|sentencing decision|sentence decision|decision on sentenc"
    r"|sentencing reasons|sentencing judgment|sentencing ruling"
    r"|ruling on sentenc|judgment on sentenc|sentenc(e|ing) hearing"
)
# ... or an appeal from a sentence (appeal level, e.g. "On appeal from the
# conviction entered on ... and the sentence imposed on ...").
TITLE_APPEAL = r"on appeal (from|against)[^\[]{0,400}?sentences? imposed"
# Cites the Criminal Code's sentencing principles, sections 718 to 718.3.
STATUTE = r"\b(s|ss|section|sections)\.?\s*718(\.[0-9]+)?\b"
# Bail / release-pending-appeal applications (excluded): the opening says it is
# one and the closing disposes of it.
BAIL_OPENING = (
    r"bail pending|release pending|judicial interim release|interim release"
    r"|appl(ies|ying|ication) for (bail|release)|bail review"
)
BAIL_CLOSING = r"bail|release|detention|detained|recognizance|suret"

# An explicit ruling on a sentence appeal ("the sentence appeal is dismissed").
DISPOSITION = (
    r"sentence appeal (is |be |should be |will be )?(dismissed|allowed|granted)"
    r"|appeal (from|against|as to|of) (the |his |her |their )?sentences? (is |be |should be |will be )?(dismissed|allowed)"
    r"|leave to appeal (the |his |her |their |against |from )?(the )?sentences? (is |be |should be )?(granted|refused|denied|dismissed)"
    r"|sentences? (is|are|be|was|were) (varied|reduced|set aside|increased|upheld|affirmed|substituted)"
    r"|(vary|reduce|increase|uphold|affirm|substitute) the sentence"
)
# A sentence appeal that was abandoned, not pursued, or not reached.
NOT_DECIDED = (
    r"sentence appeal[^.]{0,100}(abandon|not pursu|not proceed|not press)"
    r"|(abandon|not pursu|not proceed)[^.]{0,100}sentence appeal"
    r"|appeal (from|against|as to|of) (the |his |her |their )?sentence[^.]{0,80}(abandon|not pursu|not proceed)"
    r"|abandon(ed|s|ing)? (his|her|the|their) (appeal|application for leave to appeal) (from |against |as to )?(the |his |her )?sentence"
    r"|(unnecessary|not necessary|no need|need not|do not need|not required) to (address|consider|deal with|decide|determine|rule on)[^.]{0,80}sentence"
)
NEW_TRIAL = r"new trial"
# Procedural applications in an appeal (appointing counsel, extending time, directions).
PROCEDURAL = (
    r"appoint(ment|ing)? of counsel|appointed counsel|appoint counsel|(s\.|section) ?684"
    r"|extension of time|exten(d|ding|sion of) the time|extend time"
    r"|to re-?open|application for directions|case management"
)
CHAMBERS = r"chambers"
DANGEROUS_OFFENDER = r"dangerous offender|long[- ]term offender"
TRIAL_COURTS = ("BCSC", "NSSC", "NSPC")

MIN_TEXT_CHARS = 200      # ignore empty or stub documents
HEADING_SEARCH_MAX = 8000  # the heading is everything before paragraph "[1]", if found this early
HEADING_DEFAULT = 3000    # otherwise treat the first 3,000 characters as the heading
OPENING_CHARS = 900       # "opening" = first 900 characters of the body
CLOSING_CHARS = 2000      # "closing" = last 2,000 characters
BAIL_OPENING_CHARS = 1500
PROCEDURAL_OPENING_CHARS = 1500
NEW_TRIAL_CLOSING_CHARS = 1500

# Step 3 - exclusions, checked first. COUNT = number of times SENTENCE_WORD appears;
# DENSITY = COUNT per 10,000 characters of text.
#   Bail:        bail opening and bail closing, and the closing has no DISPOSITION.
#   Procedural:  appeal court, PROCEDURAL in the opening, and (heading says "chambers"
#                or no DISPOSITION anywhere).
#   Not decided: (NOT_DECIDED anywhere, or NEW_TRIAL in the closing with no DISPOSITION),
#                no trial sentencing heading, and COUNT < 15.
NOT_DECIDED_MAX_COUNT = 15

# Step 4 - inclusion rules.
MIN_COUNT_TITLE = 3    # Rule A: sentencing heading           and COUNT >= 3
MIN_COUNT = 10         # Rule B: COUNT >= 10                   and sentence mentioned in the closing
#                        Rule C: COUNT >= 10, cites s. 718     and DENSITY >= 8
HEAVY_COUNT = 25       # Rule D: COUNT >= 25                   and DENSITY >= 8
MIN_DENSITY = 8.0
MIN_COUNT_DISPOSITION = 2  # Rule F: a DISPOSITION phrase     and COUNT >= 2
MIN_DANGEROUS = 5      # Rule G: trial court, 5+ DANGEROUS_OFFENDER mentions and COUNT >= 10
MIN_COUNT_BRIEF = 3    # Rule E: COUNT >= 3, mentioned in both the opening and the closing
# tier = "core"  if any of A, B, C, D, F, G matches
# tier = "brief" if only E matches (mostly short appeal rulings)


def q(pattern: str) -> str:
    """Quote a regex as a SQL string literal."""
    return "'" + pattern.replace("'", "''") + "'"


def classify_sql(parquet_path: Path) -> str:
    src = parquet_path.as_posix().replace("'", "''")
    return f"""
    WITH src AS (
        SELECT
            dataset                              AS court,
            citation_en                          AS citation,
            citation2_en                         AS citation2,
            name_en                              AS name,
            CAST(document_date_en AS DATE)       AS decision_date,
            url_en                               AS url,
            unofficial_text_en                   AS text,
            cases_cited_en                       AS cases_cited,
            upstream_license,
            scraped_timestamp_en                 AS a2aj_scraped_at,
            length(unofficial_text_en)           AS n_chars,
            CASE WHEN instr(unofficial_text_en, '[1]') BETWEEN 1 AND {HEADING_SEARCH_MAX}
                 THEN instr(unofficial_text_en, '[1]') ELSE {HEADING_DEFAULT} END AS body_start
        FROM read_parquet('{src}')
        WHERE unofficial_text_en IS NOT NULL
          AND length(unofficial_text_en) >= {MIN_TEXT_CHARS}
          AND regexp_matches(coalesce(name_en, ''), {q(CRIMINAL_NAME)}, 'i')
    ),
    sig AS (
        SELECT *,
            CAST((n_chars - length(regexp_replace(text, {q(SENTENCE_WORD)}, '', 'gi'))) // {len(SENTENCE_WORD)} AS INTEGER) AS n_sentenc,
            regexp_matches(substr(text, 1, body_start - 1), {q(TITLE_TRIAL)}, 'i')   AS sig_title_trial,
            regexp_matches(substr(text, 1, body_start - 1), {q(TITLE_APPEAL)}, 'i')  AS sig_title_appeal,
            regexp_matches(text, {q(STATUTE)}, 'i')                                  AS sig_statute,
            regexp_matches(substr(text, body_start, {OPENING_CHARS}), {q(SENTENCE_WORD)}, 'i') AS sig_opening,
            regexp_matches(substr(text, greatest(n_chars - {CLOSING_CHARS} + 1, 1)), {q(SENTENCE_WORD)}, 'i') AS sig_closing,
            regexp_matches(substr(text, body_start, {BAIL_OPENING_CHARS}), {q(BAIL_OPENING)}, 'i')
              AND regexp_matches(substr(text, greatest(n_chars - {CLOSING_CHARS} + 1, 1)), {q(BAIL_CLOSING)}, 'i') AS sig_bail,
            len(regexp_extract_all(text, {q(DISPOSITION)}, 0, 'i'))                  AS n_disposition,
            regexp_matches(substr(text, greatest(n_chars - {CLOSING_CHARS} + 1, 1)), {q(DISPOSITION)}, 'i') AS sig_disposition_closing,
            regexp_matches(text, {q(NOT_DECIDED)}, 'i')                              AS sig_not_decided,
            regexp_matches(substr(text, greatest(n_chars - {NEW_TRIAL_CLOSING_CHARS} + 1, 1)), {q(NEW_TRIAL)}, 'i') AS sig_new_trial_closing,
            regexp_matches(substr(text, body_start, {PROCEDURAL_OPENING_CHARS}), {q(PROCEDURAL)}, 'i') AS sig_procedural_opening,
            regexp_matches(substr(text, 1, body_start - 1), {q(CHAMBERS)}, 'i')      AS sig_chambers,
            len(regexp_extract_all(text, {q(DANGEROUS_OFFENDER)}, 0, 'i'))           AS n_dangerous,
            court IN {TRIAL_COURTS}                                                  AS is_trial_court
        FROM src
    ),
    rules AS (
        SELECT *,
            round(n_sentenc * 10000.0 / n_chars, 1) AS density,
            sig_bail AND NOT sig_disposition_closing                                            AS excl_bail,
            sig_procedural_opening AND NOT is_trial_court AND (sig_chambers OR n_disposition = 0) AS excl_procedural,
            (sig_not_decided OR (sig_new_trial_closing AND n_disposition = 0))
              AND NOT sig_title_trial AND n_sentenc < {NOT_DECIDED_MAX_COUNT}                   AS excl_not_decided,
            (sig_title_trial OR sig_title_appeal) AND n_sentenc >= {MIN_COUNT_TITLE}            AS rule_a,
            n_sentenc >= {MIN_COUNT} AND sig_closing                                            AS rule_b,
            n_sentenc >= {MIN_COUNT} AND sig_statute AND n_sentenc * 10000.0 / n_chars >= {MIN_DENSITY} AS rule_c,
            n_sentenc >= {HEAVY_COUNT} AND n_sentenc * 10000.0 / n_chars >= {MIN_DENSITY}       AS rule_d,
            n_disposition >= 1 AND n_sentenc >= {MIN_COUNT_DISPOSITION}                         AS rule_f,
            is_trial_court AND n_dangerous >= {MIN_DANGEROUS} AND n_sentenc >= {MIN_COUNT}      AS rule_g,
            n_sentenc >= {MIN_COUNT_BRIEF} AND sig_opening AND sig_closing                      AS rule_e
        FROM sig
    )
    SELECT
        court, citation, citation2, name, decision_date, year(decision_date) AS year, url,
        CASE WHEN excl_bail THEN 'excluded_bail'
             WHEN excl_procedural THEN 'excluded_procedural'
             WHEN excl_not_decided THEN 'excluded_not_decided'
             WHEN rule_a OR rule_b OR rule_c OR rule_d OR rule_f OR rule_g THEN 'core'
             WHEN rule_e THEN 'brief'
             ELSE 'not_sentencing' END AS rules_v2_tier,
        concat_ws(',', CASE WHEN rule_a THEN 'A' END, CASE WHEN rule_b THEN 'B' END,
                       CASE WHEN rule_c THEN 'C' END, CASE WHEN rule_d THEN 'D' END,
                       CASE WHEN rule_f THEN 'F' END, CASE WHEN rule_g THEN 'G' END,
                       CASE WHEN rule_e THEN 'E' END) AS matched_rules,
        n_chars, n_sentenc, density,
        sig_title_trial, sig_title_appeal, sig_statute, sig_opening, sig_closing, sig_bail,
        n_disposition, sig_disposition_closing, sig_not_decided, sig_new_trial_closing,
        sig_procedural_opening, sig_chambers, n_dangerous, is_trial_court,
        '{RULES_VERSION}' AS rules_version,
        upstream_license, a2aj_scraped_at, cases_cited, text
    FROM rules
    """


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------
def http_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "sentencing-data-builder"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(courts: list[str]) -> dict:
    """Fetch any court file that differs from the copy on disk. Returns source info."""
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    info = http_json(f"https://huggingface.co/api/datasets/{HF_REPO}")
    revision = info["sha"]
    print(f"A2AJ dataset revision {revision[:10]} (last modified {info.get('lastModified')})")

    for court in courts:
        tree = http_json(f"https://huggingface.co/api/datasets/{HF_REPO}/tree/{revision}/{court}")
        entry = next(e for e in tree if e["path"] == f"{court}/train.parquet")
        remote_sha, size = entry["lfs"]["oid"], entry["lfs"]["size"]
        dest = RAW / court / "train.parquet"
        dest.parent.mkdir(parents=True, exist_ok=True)

        local_sha = manifest.get(court, {}).get("sha256")
        if dest.exists() and local_sha is None:
            local_sha = sha256_of(dest)  # file downloaded before the manifest existed
        if dest.exists() and local_sha == remote_sha:
            print(f"  {court:5s} up to date")
        else:
            print(f"  {court:5s} downloading {size / 1e6:,.0f} MB ...", flush=True)
            url = f"https://huggingface.co/datasets/{HF_REPO}/resolve/{revision}/{court}/train.parquet"
            part = dest.with_suffix(".part")
            h = hashlib.sha256()
            req = urllib.request.Request(url, headers={"User-Agent": "sentencing-data-builder"})
            with urllib.request.urlopen(req, timeout=120) as resp, part.open("wb") as f:
                for chunk in iter(lambda: resp.read(1 << 20), b""):
                    h.update(chunk)
                    f.write(chunk)
            if h.hexdigest() != remote_sha:
                part.unlink()
                raise RuntimeError(f"{court}: download did not match the expected checksum")
            part.replace(dest)
        manifest[court] = {"sha256": remote_sha, "bytes": size, "revision": revision}
        manifest_path.write_text(json.dumps(manifest, indent=2))

    return {"revision": revision, "last_modified": info.get("lastModified")}


# --------------------------------------------------------------------------
# Sentencing model
# --------------------------------------------------------------------------
def sentencing_probability(features) -> np.ndarray:
    """Score decisions with the published logistic regression weights (no scikit-learn needed).

    features: rows of signals made by scripts/evaluation/build_features.py.
    For each input: z = (x - mean) / scale; score = intercept + sum(coef * z);
    probability = 1 / (1 + exp(-score)).
    """
    from model_features import FEATURE_NAMES, model_matrix   # scripts/evaluation
    model = json.loads(SENTENCING_MODEL.read_text())
    names = [i["name"] for i in model["inputs"]]
    if names != FEATURE_NAMES:
        raise RuntimeError("The saved model's inputs do not match scripts/evaluation/model_features.py")
    mean = np.array([i["mean"] for i in model["inputs"]])
    scale = np.array([i["scale"] for i in model["inputs"]])
    coef = np.array([i["coef"] for i in model["inputs"]])
    z = (model_matrix(features).values - mean) / scale
    return 1.0 / (1.0 + np.exp(-(model["intercept"] + z @ coef)))


# --------------------------------------------------------------------------
# Offence categories, Gladue reference, mitigating factors (selected decisions only)
# --------------------------------------------------------------------------
def offence_flags(counts):
    """TRUE/FALSE per offence category, from the published logistic regression weights."""
    from enrichment_patterns import OFFENCE_CATEGORIES, OFFENCE_FEATURE_NAMES, offence_matrix
    model = json.loads(OFFENCE_MODEL.read_text())
    if [i["name"] for i in model["inputs"]] != OFFENCE_FEATURE_NAMES:
        raise RuntimeError("The saved offence model inputs do not match scripts/enrichment_patterns.py")
    mean = np.array([i["mean"] for i in model["inputs"]])
    scale = np.array([i["scale"] for i in model["inputs"]])
    z = (offence_matrix(counts).values - mean) / scale
    out = counts[["court", "citation"]].copy()
    for cat in OFFENCE_CATEGORIES:
        w = model["categories"][cat]
        out[f"offence_{cat}"] = (w["intercept"] + z @ np.array(w["coef"])) >= 0.0     # probability >= 0.5
    return out


def enrich(con):
    """Extra columns for the selected decisions in the temp table `classified`."""
    import pandas as pd
    from enrichment_patterns import (GLADUE, MITIGATION_FACTORS, MITIGATION_KEYWORDS,
                                     MITIGATION_KEYWORDS_CASE_SENSITIVE, OFFENCE_CATEGORIES, offence_feature_sql)
    if not DECISION_LABELS.exists():
        sys.exit(f"Missing {DECISION_LABELS} (the AI reading). It ships with the project.")
    key = ["court", "citation"]
    selected = "(SELECT court, citation, text, n_chars FROM classified WHERE is_sentencing)"
    out = offence_flags(con.sql(offence_feature_sql(selected)).df())          # model answer, used as a fallback
    flags = con.sql(f"""
        SELECT court, citation,
               regexp_matches(text, {q(GLADUE)}, 'i') AS references_gladue,
               regexp_matches(text, {q(MITIGATION_KEYWORDS)}, 'i')
                 OR regexp_matches(text, {q(MITIGATION_KEYWORDS_CASE_SENSITIVE)}) AS mitigation_keyword
        FROM {selected}
    """).df()
    out = out.merge(flags, on=key)

    lab = pd.read_csv(DECISION_LABELS, dtype=str, keep_default_na=False).drop_duplicates(key)
    out = out.merge(lab, on=key, how="left", suffixes=("", "_read"), indicator=True)
    read = (out["_merge"] == "both").values

    def flag(values):                       # TRUE / FALSE, blank when the decision has not been read
        col = pd.array(np.asarray(values, dtype=bool), dtype="boolean")
        col[~read] = pd.NA
        return col

    def yes(name):
        return (out[name] == "1").values

    def num(name):                          # a number, blank when not stated or not read
        return pd.to_numeric(out[name], errors="coerce")

    def text(name):
        return pd.array([v if isinstance(v, str) and v != "" else None for v in out[name]], dtype="string")

    res = out[key].copy()
    clear = read & (out["offence_unclear"] == "0").values       # the reader could tell what the offences were
    for c in OFFENCE_CATEGORIES:
        res[f"offence_{c}"] = np.where(clear, yes(f"offence_{c}_read"), out[f"offence_{c}"].values.astype(bool))
    res["offence_source"] = np.where(clear, "ai_reading", "model")
    res["offence_description"] = text("offence_description")
    res["references_gladue"] = out["references_gladue"].values
    res["mitigation_keyword"] = out["mitigation_keyword"].values
    res["ai_read"] = read

    res["sentence_outcome"] = text("sentence_outcome")
    res["n_offenders"] = num("n_offenders").astype("Int64")
    res["co_offenders"] = text("co_offenders")
    res["prison_time"] = text("prison_time")
    res["prison_months"] = num("prison_months")
    res["prison_life"] = flag(yes("prison_life"))
    res["prison_indeterminate"] = flag(yes("prison_indeterminate"))
    for name in ("prison_after_credit_months", "presentence_credit_months", "parole_ineligibility_years",
                 "conditional_sentence_months", "probation_months", "long_term_supervision_months"):
        res[name] = num(name)
    res["driving_prohibition"] = text("driving_prohibition")
    for name in ("fine_dollars", "restitution_dollars", "community_service_hours"):
        res[name] = num(name)
    for name in [c for c in lab.columns if c.startswith("penalty_")]:
        res[name] = flag(yes(name))
    for name in ("alt_institution", "alt_institution_basis", "alt_institution_name", "alt_institution_time"):
        res[name] = text(name)
    res["alt_institution_months"] = num("alt_institution_months")
    res["sentence_quote"] = text("sentence_quote")

    res["offender_indigenous"] = flag(yes("offender_indigenous"))
    words = {"M": "mitigating", "R": "rejected", "N": "mentioned only"}
    res["gladue_factors_treatment"] = pd.array([words.get(v) if isinstance(v, str) else None
                                                for v in out["systemic_gladue_factors"]], dtype="string")
    systemic = np.column_stack([(out[f"systemic_{f}"] == "M").values for f in MITIGATION_FACTORS])
    for i, f in enumerate(MITIGATION_FACTORS):
        res[f"mitigating_{f}"] = flag(systemic[:, i])
    res["mitigating_any_systemic"] = flag(systemic.any(axis=1))
    res["mitigating_quote"] = text("mitigating_quote")
    res["hate_motivated_offence"] = flag(yes("hate_motivated"))
    general_names = [c for c in lab.columns if c.startswith("general_")]
    general = np.column_stack([yes(c) for c in general_names])
    res["mitigating_discussed"] = flag(yes("mitigating_shown"))
    for i, c in enumerate(general_names):
        res["mitigating_" + c[len("general_"):]] = flag(general[:, i])
    res["mitigating_any_general"] = flag(general.any(axis=1))
    res["mitigating_any"] = flag(general.any(axis=1) | systemic.any(axis=1))
    res["reading_shown"] = text("shown")
    res["reading_confidence"] = text("confidence")
    res["reading_note"] = text("note")

    # Extract pictures (crime passage and the court's systemic-factor reasons), where drawn (optional file).
    extract_cols = {"crime_png": "extract_crime_png", "rationale_png": "extract_rationale_png",
                    "conclusion_clear": "extract_conclusion_clear"}
    if EXTRACTS.exists():
        ex = pd.read_csv(EXTRACTS, dtype=str, keep_default_na=False)[key + list(extract_cols)].drop_duplicates(key)
        res = res.merge(ex.rename(columns=extract_cols), on=key, how="left")
    for c in list(extract_cols.values()):
        res[c] = pd.array([v if isinstance(v, str) and v else None for v in res[c]], dtype="string") \
            if c in res else pd.array([None] * len(res), dtype="string")
    return res


# --------------------------------------------------------------------------
# Classify + export
# --------------------------------------------------------------------------
def build(courts: list[str], source: dict) -> None:
    sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))
    from build_features import feature_sql   # imported here to avoid a circular import
    PROCESSED.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / "data" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.sql("SET TimeZone = 'UTC'")
    con.sql("SET memory_limit = '3GB'")
    con.sql("SET threads = 4")
    con.sql(f"SET temp_directory = '{tmp.as_posix()}'")

    feature_files = []
    for court in courts:
        province, court_dir, _ = COURTS[court]
        src = RAW / court / "train.parquet"
        if not src.exists():
            sys.exit(f"Missing {src}. Run without --skip-download first.")
        print(f"  {court:5s} classifying ...", flush=True)
        con.sql(f"CREATE OR REPLACE TEMP TABLE rules AS {classify_sql(src)}")

        # Score every criminal decision with the sentencing model.
        model_inputs = con.sql(feature_sql(src)).df()
        prob = sentencing_probability(model_inputs)
        model_inputs["is_sentencing"] = prob >= SELECTION_THRESHOLD      # decided before rounding
        model_inputs["sentencing_probability"] = prob.round(4)
        # IMPOSES: a selected decision from a trial court whose heading shows no appeal
        # ("appellant", "respondent", "on appeal", "appeal from", "summary conviction appeal").
        model_inputs["sig_appeal_heading"] = model_inputs["head_appeal"] == 1
        model_inputs["imposes"] = (model_inputs["is_sentencing"] & (model_inputs["trial_court"] == 1)
                                   & ~model_inputs["sig_appeal_heading"])
        scores = model_inputs[["court", "citation", "sentencing_probability", "is_sentencing",
                               "sig_appeal_heading", "imposes"]]
        con.register("scores", scores)
        con.sql(f"""
            CREATE OR REPLACE TEMP TABLE classified AS
            SELECT r.*, s.sentencing_probability, s.is_sentencing, s.sig_appeal_heading, s.imposes,
                   '{SELECTION_VERSION}' AS selection_version
            FROM rules r JOIN scores s USING (court, citation)
        """)
        con.unregister("scores")
        con.sql("DROP TABLE rules")

        # Gladue reference and the AI reading (offences, sentence, mitigating factors) for the selected decisions.
        extra = enrich(con)
        con.register("extra", extra)
        con.sql("""
            CREATE OR REPLACE TEMP TABLE classified2 AS
            SELECT c.* EXCLUDE (cases_cited, text), e.* EXCLUDE (court, citation), c.cases_cited, c.text
            FROM classified c LEFT JOIN extra e USING (court, citation)
        """)
        con.unregister("extra")
        con.sql("DROP TABLE classified")
        con.sql("ALTER TABLE classified2 RENAME TO classified")

        out_dir = OUT / province / court_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "decisions.parquet"
        con.sql(f"""
            COPY (
                SELECT '{province}' AS province, * FROM classified
                WHERE is_sentencing
                ORDER BY decision_date, citation
            ) TO '{out_file.as_posix()}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9)
        """)

        # Every criminal decision with its signals (no text), for auditing the rules.
        feat = tmp / f"features_{court}.parquet"
        con.sql(f"""
            COPY (SELECT '{province}' AS province, * EXCLUDE (text, cases_cited) FROM classified
                  ORDER BY decision_date, citation)
            TO '{feat.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
        """)
        feature_files.append(feat)

    con.sql("DROP TABLE IF EXISTS classified")
    feats = "[" + ", ".join(f"'{f.as_posix()}'" for f in feature_files) + "]"
    all_features = PROCESSED / "criminal_decisions_signals.parquet"
    con.sql(f"""
        COPY (SELECT * FROM read_parquet({feats}) ORDER BY court, decision_date, citation)
        TO '{all_features.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)
    con.sql(f"CREATE VIEW allc AS SELECT * FROM read_parquet('{all_features.as_posix()}')")

    # A plain listing of the sentencing decisions (no text) that opens in Excel.
    con.sql(f"""
        COPY (SELECT * FROM allc WHERE is_sentencing ORDER BY province, court, decision_date, citation)
        TO '{(OUT / "index.csv").as_posix()}' (HEADER, DELIMITER ',')
    """)
    con.sql(f"""
        COPY (SELECT province, court, year, count(*) AS sentencing_decisions,
                     count(*) FILTER (imposes) AS imposes,
                     count(*) FILTER (ai_read) AS ai_read,
                     count(*) FILTER (prison_months > 0 OR prison_life OR prison_indeterminate) AS prison_sentence,
                     count(*) FILTER (references_gladue) AS references_gladue,
                     count(*) FILTER (offender_indigenous) AS offender_indigenous,
                     count(*) FILTER (mitigating_any_systemic) AS mitigating_any_systemic
              FROM allc WHERE is_sentencing
              GROUP BY ALL ORDER BY province, court, year)
        TO '{(OUT / "summary_by_court_year.csv").as_posix()}' (HEADER, DELIMITER ',')
    """)

    rows = con.sql("""
        SELECT court, count(*) AS criminal,
               count(*) FILTER (is_sentencing) AS selected,
               count(*) FILTER (imposes) AS imposes,
               count(*) FILTER (rules_v2_tier IN ('core', 'brief')) AS rules_v2,
               count(*) FILTER (is_sentencing AND rules_v2_tier IN ('core', 'brief')) AS both,
               CAST(min(decision_date) FILTER (is_sentencing) AS VARCHAR) AS first_date,
               CAST(max(decision_date) FILTER (is_sentencing) AS VARCHAR) AS last_date
        FROM allc GROUP BY court ORDER BY selected DESC
    """).fetchall()

    print(f"\n{'court':6s}{'criminal':>10s}{'selected':>10s}{'imposes':>9s}{'rules v2.0':>12s}{'both':>8s}   first .. last")
    counts = {}
    for court, crim, sel, imp, v2, both, first, last in rows:
        print(f"{court:6s}{crim:>10,d}{sel:>10,d}{imp:>9,d}{v2:>12,d}{both:>8,d}   {first} .. {last}")
        counts[court] = {"criminal": crim, "sentencing_decisions": sel, "imposes": imp, "rules_v2_would_select": v2,
                         "selected_by_both": both, "first_date": first, "last_date": last}
    total = sum(c["sentencing_decisions"] for c in counts.values())
    print(f"{'TOTAL':6s}{sum(c['criminal'] for c in counts.values()):>10,d}{total:>10,d}{sum(c['imposes'] for c in counts.values()):>9,d}"
          f"{sum(c['rules_v2_would_select'] for c in counts.values()):>12,d}"
          f"{sum(c['selected_by_both'] for c in counts.values()):>8,d}")

    described = con.sql("DESCRIBE allc").fetchall()
    extra_cols = [r[0] for r in described if r[1] == "BOOLEAN" and (
        r[0].startswith(("offence_", "mitigating_", "penalty_", "prison_"))
        or r[0] in ("references_gladue", "mitigation_keyword", "ai_read", "offender_indigenous", "hate_motivated_offence"))]
    totals = con.sql("SELECT " + ", ".join(f'count(*) FILTER ("{c}")' for c in extra_cols)
                     + " FROM allc WHERE is_sentencing").fetchall()[0]
    extra_totals = dict(zip(extra_cols, totals))
    print("Decisions with each column TRUE:")
    for k, v in extra_totals.items():
        print(f"   {k:32s}{v:>7,d}")

    (OUT / "build_info.json").write_text(json.dumps({
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selection_version": SELECTION_VERSION,
        "selection_method": f"sentencing logistic regression ({SENTENCING_MODEL.name}), probability >= {SELECTION_THRESHOLD}",
        "rules_version_for_reference": RULES_VERSION,
        "source": {"dataset": HF_REPO, **source},
        "courts": counts,
        "total_sentencing_decisions": total,
        "total_imposes": sum(c["imposes"] for c in counts.values()),
        "decisions_with_each_column_true": extra_totals,
        "imposes_method": "selected, from a trial court, and the heading shows no appeal",
    }, indent=2))

    con.close()
    shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-download", action="store_true", help="use files already in data/raw/a2aj")
    ap.add_argument("--courts", nargs="+", choices=list(COURTS), default=list(COURTS))
    args = ap.parse_args()

    if args.skip_download:
        manifest_path = RAW / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        revs = {v.get("revision") for v in manifest.values()}
        source = {"revision": revs.pop() if len(revs) == 1 else None, "last_modified": None}
    else:
        source = download(args.courts)
    build(args.courts, source)
    print(f"\nDone. Sentencing decisions are in {OUT}")


if __name__ == "__main__":
    main()
