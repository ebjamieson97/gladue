"""Build the case browser: a static website of the extract pictures, ready for localhost or GitHub Pages.

Includes the decisions whose court plainly states the effect of the systemic factor
(extract_conclusion_clear = Y) and that have both pictures.

Output  site/index.html (copied from scripts/site/index.html), site/cases.js (and cases.json), site/img/<court>/<citation>_*.png

    .venv\\Scripts\\python.exe -X utf8 scripts\\site\\build_site.py
    .venv\\Scripts\\python.exe -m http.server 8000 --directory site      # then open http://localhost:8000
"""
import csv
import json
import shutil
from collections import Counter
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
COURTS = {
    "SCC": "Supreme Court of Canada", "ONCA": "Court of Appeal for Ontario", "BCCA": "BC Court of Appeal",
    "BCSC": "Supreme Court of British Columbia", "NSCA": "Nova Scotia Court of Appeal",
    "NSSC": "Supreme Court of Nova Scotia", "NSPC": "Provincial Court of Nova Scotia",
    "NLCA": "Court of Appeal of Newfoundland and Labrador",
}
FACTORS = {
    "mitigating_gladue_factors": "Gladue factors", "mitigating_res_school": "Residential schools",
    "mitigating_colonialism": "Colonialism", "mitigating_intergen_trauma": "Intergenerational trauma",
    "mitigating_anti_black_racism": "Anti-Black racism", "mitigating_systemic_racism": "Systemic racism",
    "mitigating_islamophobia": "Islamophobia", "mitigating_white_supremacy": "White supremacy",
    "mitigating_other_prejudice": "Other prejudice",
}
PROVINCES = {"BCSC": "British Columbia", "BCCA": "British Columbia", "NSSC": "Nova Scotia", "NSPC": "Nova Scotia",
             "NSCA": "Nova Scotia", "ONCA": "Ontario", "NLCA": "Newfoundland and Labrador", "SCC": "Canada (Supreme Court)"}
OUTCOMES = {"imposed": "Sentence imposed", "appeal_upheld": "Appeal: sentence upheld",
            "appeal_reduced": "Appeal: sentence reduced", "appeal_increased": "Appeal: sentence increased",
            "appeal_varied_other": "Appeal: sentence varied"}


# Which appeal decisions go on the site (from pipeline/6a_classify_appeals.js; answers in scripts/site/work/raw/).
# Trial-court sentencings are always included. Of the appeals, only these categories are:
APPEAL_CATEGORIES_SHOWN = {"corrected"}
# Every other appeal (upheld, Crown appeal dismissed, reduced or increased for other reasons, ...) is shown only when its
# two pictures describe the crime AND at least one specific systemic factor in the offender's life (checked by a reader;
# answers in scripts/site/work/check_raw*/, made by make_check_batches.py). The direction check (below) separately
# requires the APPEAL court's own view that the factor mitigates.
APPEAL_CATEGORIES_IF_DESCRIBED = "all other categories"
APPEAL_WORK = Path(__file__).resolve().parent / "work"

# Rationale pictures must show the court's own reasoning (or text the judge explicitly adopts). Cases whose latest
# picture failed that check (case_extracts/work/source_raw, recheck_raw) are hidden, except those listed here.
HIDE_IF_NOT_COURTS_OWN_WORDS = True
KEEP_ANYWAY = {"2025 NSSC 426"}    # Caldi: the IRCA passage the project author asked for; the judge called the IRCA "very important to the outcome"
EXTRACT_WORK = ROOT / "case_extracts" / "work"

# Cases whose reasons picture shows the court NOT treating the systemic factor as mitigating, or never stating its
# effect ("unclear"), are hidden
# (direction check: pipeline/5d_check_direction.js, applied by scripts/extracts/apply_direction_check.py).
DIRECTION_VERDICTS = EXTRACT_WORK / "direction_verdicts.json"


def source_checks():
    """{(court, citation): True if the rationale picture is the court's own reasoning}; later checks win."""
    out = {}
    tags = ["source", "recheck"] + sorted(p.name[:-len("_sample.csv")] for p in EXTRACT_WORK.glob("*_source_sample.csv"))
    for tag in tags:
        path = EXTRACT_WORK / f"{tag}_sample.csv"
        if not path.exists():
            continue
        sample = {r["id"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}
        for p in sorted((EXTRACT_WORK / f"{tag}_raw").glob(f"{tag}_*.jsonl")):
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                if line.strip().startswith("{"):
                    a = json.loads(line)
                    s = sample.get(a.get("id"))
                    if s:
                        out[(s["court"], s["citation"])] = a.get("source_ok") == "Y"
    return out


def content_checks():
    """{(court, citation): (crime_described, factor_detail)} for the checked upheld appeals (all rounds)."""
    out = {}
    for sample_path, raw_dir in _rounds("check_sample.csv", "check_raw", "check_sample_*.csv"):
        if sample_path.exists():
            for k, a in _answers(sample_path, raw_dir, "check_*.jsonl").items():
                out[k] = (a.get("crime_described") == "Y", a.get("factor_detail") == "Y")
    return out


def _rounds(first_sample, first_raw, pattern):
    """(sample file, answers folder) for the original round and every update round (TAG suffix)."""
    out = [(APPEAL_WORK / first_sample, APPEAL_WORK / first_raw)]
    for p in sorted(APPEAL_WORK.glob(pattern)):
        tag = p.stem.split("_sample_", 1)[1]
        out.append((p, APPEAL_WORK / f"{first_raw}_{tag}"))
    return out


def appeal_categories():
    """{(court, citation): category} for the classified appeal decisions (all rounds)."""
    out = {}
    for sample_path, raw_dir in _rounds("appeal_sample.csv", "raw", "appeal_sample_*.csv"):
        if sample_path.exists():
            out.update(_answers(sample_path, raw_dir, "appeal_*.jsonl"))
    return out


def _answers(sample_path, raw_dir, pattern):
    sample = {r["id"]: r for r in csv.DictReader(sample_path.open(encoding="utf-8"))}
    out = {}
    for p in sorted(raw_dir.glob(pattern)):
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("{"):
                a = json.loads(line)
                s = sample.get(a.get("id"))
                if s:
                    out[(s["court"], s["citation"])] = a
    return out


def offence_groups(r):
    """Broad offence groups for the site's buttons. A case can be in several; 'other' means none of the first three."""
    groups = [g for g, col in (("murder", "offence_homicide"), ("assault", "offence_assault"),
                               ("sexual", "offence_sexual")) if r[col] is True]
    return groups or ["other"]


def sentence_details(r):
    """The parts of the sentence shown in the sentence card (empty values left out)."""
    def num(k):
        v = r[k]
        return None if v is None or v != v else round(float(v), 1)      # v != v catches NaN
    out = {
        "months": num("prison_months"), "life": r["prison_life"] is True, "indeterminate": r["prison_indeterminate"] is True,
        "parole_years": num("parole_ineligibility_years"), "credit_months": num("presentence_credit_months"),
        "after_credit_months": num("prison_after_credit_months"), "cso_months": num("conditional_sentence_months"),
        "probation_months": num("probation_months"), "lts_months": num("long_term_supervision_months"),
        "youth": r["penalty_youth_sentence"] is True, "dangerous_offender": r["penalty_dangerous_offender"] is True,
        "alt": r["alt_institution"] or "", "alt_basis": r["alt_institution_basis"] or "", "alt_name": r["alt_institution_name"] or "",
        "note": r["reading_note"] or "",
    }
    return {k: v for k, v in out.items() if v is not None and v is not False and v != ""}   # keeps 0 months


def write_stats(shown):
    """site/stats.js: counts for the Statistics page, from the full set of criminal decisions and the sentencing index.

    "Mitigating" counts only the decisions shown on the site (`shown`, a list of citations): those where the court's
    reasons CLEARLY treat a systemic factor as mitigating and pass every check. So the Statistics page always matches
    the casebook.
    """
    import pandas as pd
    casebook = pd.DataFrame({"citation": sorted(set(shown))})            # noqa: F841 (used by name in SQL)
    names = {"british_columbia": "British Columbia", "ontario": "Ontario", "nova_scotia": "Nova Scotia",
             "newfoundland_and_labrador": "Newfoundland and Labrador", "canada": "Canada (Supreme Court)"}
    crim = duckdb.sql(f"""SELECT province, court, count(*) AS criminal, count(*) FILTER (is_sentencing) AS sentencing,
                                 count(*) FILTER (imposes) AS imposes
                          FROM read_parquet('{(ROOT / "data" / "processed" / "criminal_decisions_signals.parquet").as_posix()}')
                          GROUP BY ALL""").fetchall()
    # Systemic factors (Gladue factors, residential schools, colonialism, intergenerational trauma, anti-Black and other
    # racism or prejudice). Mentioned: a systemic-factor keyword in the text, or the AI reading found the court dealing
    # with any of them (accepted, rejected or only mentioned). Mitigating: shown on the site (see the docstring).
    glad = {r[0]: r[1:] for r in duckdb.sql(f"""
        SELECT i.court,
               count(*) FILTER (i.mitigation_keyword OR coalesce(l.any_mentioned, false)),
               count(*) FILTER (i.citation IN (SELECT citation FROM casebook))
        FROM read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}') i
        LEFT JOIN (SELECT court, citation,
                          list_has_any([systemic_gladue_factors, systemic_colonialism, systemic_res_school, systemic_intergen_trauma,
                                        systemic_anti_black_racism, systemic_systemic_racism, systemic_islamophobia,
                                        systemic_white_supremacy, systemic_other_prejudice], ['M', 'R', 'N']) AS any_mentioned
                   FROM read_csv_auto('{(ROOT / "data" / "labels" / "decision_labels.csv").as_posix()}', all_varchar=true)) l
               USING (court, citation)
        GROUP BY i.court""").fetchall()}
    provinces = {}
    for prov, court, n_crim, n_sent, n_imp in crim:
        p = provinces.setdefault(prov, {"name": names.get(prov, prov), "criminal": 0, "sentencing": 0, "courts": []})
        ref, mit = glad.get(court, (0, 0))
        p["courts"].append({"code": court, "name": COURTS.get(court, court), "criminal": n_crim, "sentencing": n_sent,
                            "imposes": n_imp, "systemic_mentioned": ref, "systemic_mitigating": mit})
        p["criminal"] += n_crim
        p["sentencing"] += n_sent
    info_path = ROOT / "sentencing_data" / "build_info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    stats = {"provinces": list(provinces.values()),
             "criminal": sum(p["criminal"] for p in provinces.values()),
             "sentencing": sum(p["sentencing"] for p in provinces.values()),
             "systemic_mentioned": sum(v[0] for v in glad.values()), "systemic_mitigating": sum(v[1] for v in glad.values()),
             "built": (info.get("built_at_utc") or "")[:10]}
    imp = duckdb.sql(f"""SELECT count(*) FILTER (imposes), count(*) FILTER (imposes AND citation IN (SELECT citation FROM casebook))
                         FROM read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}')""").fetchall()[0]
    stats["imposes"], stats["imposes_mitigating"] = imp           # trial courts sentencing the offender themselves
    # By year, from 1993 (earlier years have only a handful of decisions in the dataset)
    stats["by_year"] = [{"year": int(y), "sentencing": int(n), "mitigating": int(m)} for y, n, m in duckdb.sql(f"""
        SELECT year, count(*), count(*) FILTER (citation IN (SELECT citation FROM casebook))
        FROM read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}') WHERE year >= 1993
        GROUP BY year ORDER BY year""").fetchall()]
    (SITE / "stats.js").write_text("window.STATS = " + json.dumps(stats, ensure_ascii=False) + ";\n", encoding="utf-8")
    return stats


def main():
    rows = duckdb.sql(f"""
        SELECT court, citation, name, year, CAST(decision_date AS VARCHAR) AS decision_date, url, offence_description, prison_time, sentence_outcome,
               extract_crime_png, extract_rationale_png, {", ".join(FACTORS)},
               offence_homicide, offence_assault, offence_sexual,
               prison_months, prison_life, prison_indeterminate, parole_ineligibility_years,
               presentence_credit_months, prison_after_credit_months, conditional_sentence_months,
               probation_months, long_term_supervision_months, penalty_youth_sentence, penalty_dangerous_offender,
               alt_institution, alt_institution_basis, alt_institution_name, reading_note
        FROM read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}')
        WHERE extract_conclusion_clear = 'Y' AND extract_crime_png IS NOT NULL AND extract_rationale_png IS NOT NULL
        ORDER BY year, court, citation
    """).df()

    img = SITE / "img"
    if img.exists():
        shutil.rmtree(img)
    ov_path = ROOT / "case_extracts" / "overrides.json"
    overrides = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    cats = appeal_categories()
    checks = content_checks()
    sources = source_checks()
    direction = json.loads(DIRECTION_VERDICTS.read_text(encoding="utf-8")) if DIRECTION_VERDICTS.exists() else {}
    tally = Counter()
    cases = []
    for r in rows.itertuples(index=False):
        r = r._asdict()
        if HIDE_IF_NOT_COURTS_OWN_WORDS and sources.get((r["court"], r["citation"])) is False \
                and r["citation"] not in KEEP_ANYWAY:
            tally["hidden: rationale not the court's own words"] += 1
            continue
        # Shown only with a "mitigating" answer from the direction check: the deciding court's own view (on an appeal, the
        # appeal court's, even when it increased the sentence) is that the systemic factor mitigates. Unchecked cases wait.
        if direction.get(r["citation"], {}).get("overall") != "mitigating" and r["citation"] not in KEEP_ANYWAY:
            tally["hidden: direction check not passed (not mitigating, no effect stated, or not yet checked)"] += 1
            continue
        if r["sentence_outcome"] != "imposed":                 # an appeal: keep only the categories shown
            key = (r["court"], r["citation"])
            cat = cats.get(key, {}).get("category", "not classified")
            if cat in APPEAL_CATEGORIES_SHOWN:
                tally[cat] += 1
            else:
                ok = checks.get(key) == (True, True)
                tally[f"{cat} ({'shown: crime and factor described' if ok else 'left out: not described or not checked'})"] += 1
                if not ok:
                    continue
        else:
            tally["trial sentencing"] += 1
        pics = {}
        for kind in ("crime", "rationale"):
            src = ROOT / r[f"extract_{kind}_png"]
            dest = img / r["court"] / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            pics[kind] = dest.relative_to(SITE).as_posix()
            phone = src.with_name(src.stem + "_m.png")            # narrow version for phones
            if phone.exists():
                shutil.copy2(phone, dest.with_name(phone.name))
                pics[kind + "_m"] = dest.with_name(phone.name).relative_to(SITE).as_posix()
        cases.append({
            "id": r["citation"].replace(" ", "-"),
            "citation": r["citation"], "name": r["name"], "year": int(r["year"]),
            "court": COURTS.get(r["court"], r["court"]), "court_code": r["court"],
            "province": PROVINCES.get(r["court"], ""), "date": r["decision_date"] or "", "url": r["url"],
            "offence": r["offence_description"] or "", "prison": r["prison_time"] or "",
            "outcome": OUTCOMES.get(r["sentence_outcome"], ""),
            # every tag must be visible in the reasons picture; tags with no supporting paragraph are dropped
            "factors": [label for col, label in FACTORS.items() if r[col] is True
                        and label not in (overrides.get(r["citation"]) or {}).get("drop_tags", [])],
            "groups": offence_groups(r),
            "sentence": sentence_details(r),
            "crime": pics["crime"], "rationale": pics["rationale"],
            "crime_m": pics.get("crime_m", pics["crime"]), "rationale_m": pics.get("rationale_m", pics["rationale"]),
        })
    print("Decisions considered:", dict(tally.most_common()), "| appeal categories shown:", sorted(APPEAL_CATEGORIES_SHOWN))
    for g in ("murder", "assault", "sexual", "other"):
        print(f"   {g:8s}{sum(g in c['groups'] for c in cases):5d}")
    SITE.mkdir(exist_ok=True)
    data = json.dumps(cases, ensure_ascii=False, separators=(",", ":"))
    (SITE / "cases.json").write_text(data, encoding="utf-8")                 # for other tools
    # The page loads the list as a script, so it works in any browser and even when opened as a file.
    (SITE / "cases.js").write_text("window.CASES = " + data + ";\n", encoding="utf-8")
    shutil.copy2(Path(__file__).with_name("index.html"), SITE / "index.html")
    shutil.copy2(Path(__file__).with_name("catalogue.html"), SITE / "catalogue.html")
    for page in ("gladue.html", "stats.html", "methodology.html"):
        shutil.copy2(Path(__file__).with_name(page), SITE / page)
    shutil.copy2(Path(__file__).with_name("README.md"), SITE / "README.md")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")       # GitHub Pages: serve files as they are
    write_stats([c["citation"] for c in cases])                                                # data for the Statistics page
    import sys as _sys                                           # model results for the Statistics page
    _sys.path.insert(0, str(ROOT / "scripts" / "analysis"))
    from sentence_regression import results
    (SITE / "models.js").write_text("window.MODELS = " + json.dumps(results()) + ";\n", encoding="utf-8")
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1e6
    print(f"{len(cases)} cases, {2 * len(cases)} pictures, {size:.0f} MB in {SITE}")


if __name__ == "__main__":
    main()
