"""Merge the AI readers' answers from the full reading of every selected sentencing decision.

Input   data/labels/full_read_raw/read_*.jsonl          one JSON object per decision
        data/labels/full_read_audit_raw/audit_*.jsonl   the second model's answers on the audit subset
        data/labels/adjudication_raw/adjudicate_*.jsonl a third reading of the systemic factors, for decisions
                                                        where the full reading and the keyword review disagreed
                                                        (it replaces both; see make_adjudication_batches.py)
Output  data/labels/decision_labels.csv                 one row per decision, checked and tidied

Checks made here (all by script, no AI):
  * every decision has exactly one valid answer (missing or unreadable ones are listed)
  * every code is one of the allowed codes
  * every quoted passage really appears in the decision text (letters and digits compared);
    a quote that does not is dropped
Also prints agreement with the second model and with the two earlier labelling rounds.

    .venv\\Scripts\\python.exe -X utf8 scripts\\evaluation\\merge_full_read.py [--write-missing]
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from enrichment_patterns import MITIGATION_FACTORS, OFFENCE_CATEGORIES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data" / "labels"
DATA = (ROOT / "sentencing_data").as_posix()

OUTCOMES = ["imposed", "appeal_upheld", "appeal_reduced", "appeal_increased", "appeal_varied_other", "no_sentence", "unclear"]
PRISON_SPECIAL = ["life", "indeterminate", "none", "time_served", "unclear", "na"]
ORDERS = ["intermittent", "suspended_sentence", "discharge_absolute", "discharge_conditional", "victim_surcharge",
          "weapons_prohibition", "dna_order", "soira", "s161_order", "no_contact_order", "forfeiture", "delayed_parole",
          "dangerous_offender", "long_term_offender", "youth_sentence", "other"]
ALT_TYPES = ["healing_lodge", "residential_treatment", "psychiatric_facility", "other", "none"]
ALT_BASIS = ["ordered", "if_directed", "recommended", ""]
GENERAL_MITIGATING = ["guilty_plea", "remorse", "no_record", "youth", "age_or_health", "mental_health", "cognitive", "addiction",
                      "abuse_or_trauma", "good_character", "family", "rehabilitation", "cooperation", "lesser_role", "collateral",
                      "delay", "custody_conditions", "bail_conditions", "state_misconduct", "restitution_made", "other"]
KEYS = ["id", "offences", "offence_note", "outcome", "n_offenders", "co_offenders", "prison", "prison_after_credit", "credit",
        "parole_ineligibility_years", "conditional_sentence", "probation", "long_term_supervision", "driving_prohibition",
        "fine", "restitution", "community_service_hours", "orders", "alt_institution", "alt_basis", "alt_name", "alt_time",
        "sentence_quote", "indigenous", "systemic", "systemic_quote", "hate_motivated", "mitigating", "confidence", "note"]

DUR = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*y\s*(-?\d+(?:\.\d+)?)\s*m\s*(-?\d+(?:\.\d+)?)\s*d\s*$", re.I)


def duration(value):
    """'2y 0m -1d' -> (months as a number, readable text). (None, None) if not a duration."""
    m = DUR.match(str(value or ""))
    if not m:
        return None, None
    y, mo, d = (float(x) for x in m.groups())
    months = round(y * 12 + mo + d / 30.4375, 2)
    if months <= 0:
        return None, None

    def unit(n, word):
        n = int(n) if n == int(n) else n
        return f"{n} {word}{'' if n == 1 else 's'}"
    parts = [unit(y, "year")] if y else []
    parts += [unit(mo, "month")] if mo else []
    if d > 0:
        parts.append(unit(d, "day"))
    text = " ".join(parts)
    if d < 0:
        text += " less a day" if d == -1 else f" less {unit(-d, 'day')}"
    return months, text


def number(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except ValueError:
        return None


def codes(value, allowed):
    """Split a semicolon list. Returns (codes that are allowed, codes that are not)."""
    got = [c.strip().lower() for c in str(value or "").replace(",", ";").split(";") if c.strip()]
    return [c for c in got if c in allowed], [c for c in got if c not in allowed and c not in ("none", "not_shown")]


def squash(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def read_raw(folder, pattern):
    """Later files replace earlier ones (follow-up files are numbered from 9001)."""
    rows, bad = {}, []
    for path in sorted((LAB / folder).glob(pattern)):
        for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = line.strip().rstrip(",")
            if not line or line.startswith("```") or line in ("[", "]"):
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                bad.append(f"{path.name}:{n}")
                continue
            if isinstance(r, dict) and r.get("id"):
                rows[str(r["id"]).strip()] = r
    return rows, bad


def tidy(r, texts):
    """One reader answer -> one tidy row. Returns (row, list of problems)."""
    problems = []
    out = {}
    cats, odd = codes(r.get("offences"), OFFENCE_CATEGORIES)
    problems += [f"offence code {c}" for c in odd]
    for c in OFFENCE_CATEGORIES:
        out[f"offence_{c}"] = int(c in cats)
    out["offence_unclear"] = int(not cats)
    out["offence_description"] = str(r.get("offence_note") or "").strip()

    outcome = str(r.get("outcome") or "").strip().lower()
    if outcome not in OUTCOMES:
        problems.append(f"outcome {outcome}")
        outcome = "unclear"
    out["sentence_outcome"] = outcome
    n_off = number(r.get("n_offenders"))
    out["n_offenders"] = int(n_off) if n_off else 1
    out["co_offenders"] = str(r.get("co_offenders") or "").strip()

    prison = str(r.get("prison") or "").strip().lower()
    months, text = duration(prison)
    if months is None and prison not in PRISON_SPECIAL:
        problems.append(f"prison {prison}")
        prison = "unclear"
    out["prison_time"] = text if months is not None else {"time_served": "time served", "na": ""}.get(prison, prison)
    out["prison_months"] = months if months is not None else (0 if prison == "none" else "")
    out["prison_life"] = int(prison == "life")
    out["prison_indeterminate"] = int(prison == "indeterminate")
    out["prison_after_credit_months"] = duration(r.get("prison_after_credit"))[0] or ""
    out["presentence_credit_months"] = duration(r.get("credit"))[0] or ""
    pi = number(r.get("parole_ineligibility_years"))
    out["parole_ineligibility_years"] = pi if pi else ""
    ordered = {}      # ordered at all, even when the length is not shown
    for key, col in (("conditional_sentence", "conditional_sentence_months"), ("probation", "probation_months"),
                     ("long_term_supervision", "long_term_supervision_months")):
        out[col] = duration(r.get(key))[0] or ""
        ordered[key] = int(out[col] != "" or str(r.get(key) or "").strip().lower() in ("unstated", "unclear"))
    dp = str(r.get("driving_prohibition") or "none").strip().lower()
    dp_months = duration(dp)[0]
    out["driving_prohibition"] = duration(dp)[1] if dp_months else (dp if dp in ("life", "unstated") else "")
    out["fine_dollars"] = number(r.get("fine")) or 0
    out["restitution_dollars"] = number(r.get("restitution")) or 0
    out["community_service_hours"] = number(r.get("community_service_hours")) or 0

    orders, odd = codes(r.get("orders"), ORDERS)
    if odd:
        orders = sorted(set(orders) | {"other"})
    out["penalty_conditional_sentence"] = ordered["conditional_sentence"]
    out["penalty_probation"] = ordered["probation"]
    out["penalty_long_term_supervision"] = ordered["long_term_supervision"]
    out["penalty_driving_prohibition"] = int(out["driving_prohibition"] != "")
    out["penalty_fine"] = int(out["fine_dollars"] > 0)
    out["penalty_restitution"] = int(out["restitution_dollars"] > 0)
    out["penalty_community_service"] = int(out["community_service_hours"] > 0)
    for o in ORDERS:
        out[f"penalty_{o}"] = int(o in orders)

    alt = str(r.get("alt_institution") or "none").strip().lower()
    if alt not in ALT_TYPES:
        problems.append(f"alt_institution {alt}")
        alt = "other"
    basis = str(r.get("alt_basis") or "").strip().lower()
    out["alt_institution"] = "" if alt == "none" else alt
    out["alt_institution_basis"] = (basis if basis in ALT_BASIS else "") if alt != "none" else ""
    out["alt_institution_name"] = str(r.get("alt_name") or "").strip() if alt != "none" else ""
    alt_months, alt_text = duration(r.get("alt_time"))
    out["alt_institution_time"] = (alt_text if alt_months else "unspecified") if alt != "none" else ""
    out["alt_institution_months"] = (alt_months or "") if alt != "none" else ""

    text = texts.get(r["id"], "")
    for key, col in (("sentence_quote", "sentence_quote"), ("systemic_quote", "mitigating_quote")):
        q = str(r.get(key) or "").strip()
        found = bool(q) and len(squash(q)) >= 12 and squash(q) in text
        if q and not found:      # a quote joined with "..." counts if every piece is there
            pieces = [p for p in re.split(r"\.\.\.+|…|\[\.\.\.\]", q) if len(squash(p)) >= 12]
            found = len(pieces) > 1 and all(squash(p) in text for p in pieces)
        out[col] = q if found else ""
        out[f"{col}_given"] = int(bool(q))
        out[f"{col}_verified"] = int(found)

    out["offender_indigenous"] = int(str(r.get("indigenous") or "").strip().upper().startswith("Y"))
    sys_codes = {f: "X" for f in MITIGATION_FACTORS}
    for part in str(r.get("systemic") or "").replace(",", ";").split(";"):
        if "=" in part:
            f, code = (x.strip() for x in part.split("=", 1))
            if f.lower() in sys_codes and code.upper()[:1] in "MRN" and code:
                sys_codes[f.lower()] = code.upper()[:1]
            else:
                problems.append(f"systemic {part.strip()}")
    for f in MITIGATION_FACTORS:
        out[f"systemic_{f}"] = sys_codes[f]
    out["systemic_source"] = "full_reading"
    out["reading_systemic"] = ";".join(f"{f}={c}" for f, c in sys_codes.items() if c != "X")   # as first read
    out["hate_motivated"] = int(str(r.get("hate_motivated") or "").strip().upper().startswith("Y"))

    raw_mit = str(r.get("mitigating") or "").strip().lower()
    mit, odd = codes(raw_mit, GENERAL_MITIGATING)
    if odd:
        mit = sorted(set(mit) | {"other"})
    out["mitigating_shown"] = int(raw_mit != "not_shown" and raw_mit != "")
    for g in GENERAL_MITIGATING:
        out[f"general_{g}"] = int(g in mit)

    out["confidence"] = "LOW" if str(r.get("confidence") or "").strip().upper().startswith("L") else "HIGH"
    out["note"] = str(r.get("note") or "").strip()
    return out, problems


def apply_adjudication(rows, texts):
    """Replace the systemic-factor codes with the third reading where there is one."""
    adj, bad = read_raw("adjudication_raw", "adjudicate_*.jsonl")
    if not adj:
        return
    changed_any = 0
    for r in rows:
        a = adj.get(r["id"])
        if not a:
            continue
        before = any(r[f"systemic_{f}"] == "M" for f in MITIGATION_FACTORS)
        for f in MITIGATION_FACTORS:
            code = str(a.get(f) or "X").strip().upper()[:1]
            r[f"systemic_{f}"] = code if code in "MRN" and code else "X"
        r["systemic_source"] = "adjudicated"
        after = any(r[f"systemic_{f}"] == "M" for f in MITIGATION_FACTORS)
        changed_any += before != after
        q = str(a.get("quote") or "").strip()
        ok = after and len(squash(q)) >= 12 and squash(q) in texts.get(r["id"], "")
        if ok:
            r["mitigating_quote"], r["mitigating_quote_given"], r["mitigating_quote_verified"] = q, 1, 1
        elif not after:
            r["mitigating_quote"] = ""
    n = sum(r["systemic_source"] == "adjudicated" for r in rows)
    print(f"Third reading applied to {n} decisions ({len(bad)} unreadable lines); "
          f"'any systemic factor mitigating' changed from the full reading in {changed_any}")

    # Which earlier reading did the third reader side with?
    old = {(o["court"], o["citation"]): o for o in csv.DictReader((LAB / "mitigation_labels.csv").open(encoding="utf-8"))}
    tally = Counter()
    for r in rows:
        if r["systemic_source"] != "adjudicated":
            continue
        first = dict(x.split("=") for x in r["reading_systemic"].split(";") if "=" in x)
        o = old[(r["court"], r["citation"])]
        for f in MITIGATION_FACTORS:
            full_m, key_m, adj_m = first.get(f) == "M", o[f] == "M", r[f"systemic_{f}"] == "M"
            if full_m != key_m:
                tally["full reading" if adj_m == full_m else "keyword review"] += 1
        full_any = any(first.get(f) == "M" for f in MITIGATION_FACTORS)
        key_any = any(o[f] == "M" for f in MITIGATION_FACTORS)
        adj_any = any(r[f"systemic_{f}"] == "M" for f in MITIGATION_FACTORS)
        if full_any != key_any:
            tally["any: full reading" if adj_any == full_any else "any: keyword review"] += 1
    print(f"  factor-level disagreements settled: sided with the full reading {tally['full reading']}, "
          f"with the keyword review {tally['keyword review']}")
    print(f"  'any factor mitigating' disagreements settled: sided with the full reading {tally['any: full reading']}, "
          f"with the keyword review {tally['any: keyword review']}")


def load_texts(sample):
    con = duckdb.connect()
    rows = con.sql(f"SELECT court, citation, text FROM read_parquet('{DATA}/*/*/decisions.parquet')").fetchall()
    by_key = {(c, k): t for c, k, t in rows}
    return {s["id"]: squash(by_key.get((s["court"], s["citation"]), "")) for s in sample}


def pct(a, b):
    return f"{a:,}/{b:,} ({a / b:.1%})" if b else "0/0"


def agreement(name, pairs, fields):
    if not pairs:
        return
    print(f"\n{name}: {len(pairs):,} decisions read twice")
    for label, fn in fields:
        same = sum(fn(a) == fn(b) for a, b in pairs)
        print(f"   {label:46s} same answer in {pct(same, len(pairs))}")


def main():
    # The original reading plus any update rounds (full_read_sample_TAG.csv with answers in full_read_raw_TAG/).
    sample = []
    for path in [LAB / "full_read_sample.csv"] + sorted(LAB.glob("full_read_sample_*.csv")):
        sample += list(csv.DictReader(path.open(encoding="utf-8")))
    raw, bad = {}, []
    for folder in ["full_read_raw"] + sorted(p.name for p in LAB.glob("full_read_raw_*") if p.is_dir()):
        r, b_ = read_raw(folder, "read_*.jsonl")
        raw.update(r)
        bad += b_
    texts = load_texts(sample)

    rows, missing, problems = [], [], Counter()
    for s in sample:
        r = raw.get(s["id"])
        if not r:
            missing.append(s["id"])
            continue
        tidy_row, probs = tidy(r, texts)
        problems.update(p.split(" ")[0] for p in probs)
        rows.append({**{k: s[k] for k in ("id", "court", "citation", "name", "shown")}, **tidy_row})
    apply_adjudication(rows, texts)
    print(f"{len(sample):,} decisions; {len(rows):,} read; {len(missing)} missing; {len(bad)} unreadable lines "
          f"{bad[:8]}; answers for unknown ids: {len(set(raw) - {s['id'] for s in sample})}")
    print("  values outside the allowed codes (tidied):", dict(problems))
    if not rows:
        return missing

    with (LAB / "decision_labels.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    print("\nOFFENCES   ", {c: sum(r[f"offence_{c}"] for r in rows) for c in OFFENCE_CATEGORIES},
          " unclear:", sum(r["offence_unclear"] for r in rows))
    print("OUTCOME    ", dict(Counter(r["sentence_outcome"] for r in rows).most_common()))
    kinds = Counter("duration" if isinstance(r["prison_months"], float) else (r["prison_time"] or "na") for r in rows)
    print("PRISON     ", dict(kinds.most_common()))
    print("PENALTIES  ", {k[8:]: sum(r[k] for r in rows) for k in rows[0] if k.startswith("penalty_")})
    print("PLACEMENT  ", dict(Counter((r["alt_institution"], r["alt_institution_basis"]) for r in rows if r["alt_institution"]).most_common()))
    print("INDIGENOUS ", sum(r["offender_indigenous"] for r in rows))
    for fct in MITIGATION_FACTORS:
        c = Counter(r[f"systemic_{fct}"] for r in rows)
        print(f"  {fct:18s} mitigating {c['M']:5d}   rejected {c['R']:4d}   mentioned only {c['N']:5d}")
    print("  any systemic factor mitigating:", sum(any(r[f"systemic_{f}"] == "M" for f in MITIGATION_FACTORS) for r in rows),
          "  hate-motivated offence:", sum(r["hate_motivated"] for r in rows))
    print("GENERAL    ", {g: sum(r[f"general_{g}"] for r in rows) for g in GENERAL_MITIGATING},
          " mitigating factors dealt with in the text shown:", pct(sum(r["mitigating_shown"] for r in rows), n))
    print("CONFIDENCE ", dict(Counter(r["confidence"] for r in rows)), " shown:", dict(Counter(r["shown"] for r in rows)))
    for col in ("sentence_quote", "mitigating_quote"):
        given = sum(r[f"{col}_given"] for r in rows)
        print(f"QUOTES      {col}: given for {given:,}; found word for word in the decision: {pct(sum(r[f'{col}_verified'] for r in rows), given)}")

    # ---- agreement with the second model (audit subset)
    by_id = {r["id"]: r for r in rows}
    audit_raw, audit_bad = read_raw("full_read_audit_raw", "audit_*.jsonl")
    pairs = [(by_id[i], tidy(a, texts)[0]) for i, a in audit_raw.items() if i in by_id]
    any_sys = lambda r: any(r[f"systemic_{f}"] == "M" for f in MITIGATION_FACTORS)      # noqa: E731
    fields = [("every offence category", lambda r: tuple(r[f"offence_{c}"] for c in OFFENCE_CATEGORIES)),
              ("sentence outcome", lambda r: r["sentence_outcome"]),
              ("prison time", lambda r: (r["prison_time"], r["prison_months"])),
              ("probation length", lambda r: r["probation_months"]),
              ("conditional sentence length", lambda r: r["conditional_sentence_months"]),
              ("alternative institution (type)", lambda r: r["alt_institution"]),
              ("offender identified as Indigenous", lambda r: r["offender_indigenous"]),
              ("any systemic factor mitigating", any_sys),
              ("Gladue factors code (M/R/N/X)", lambda r: r["systemic_gladue_factors"]),
              ("guilty plea mitigating", lambda r: r["general_guilty_plea"]),
              ("every general mitigating factor", lambda r: tuple(r[f"general_{g}"] for g in GENERAL_MITIGATING))]
    agreement(f"SECOND MODEL (audit; {len(audit_bad)} unreadable lines)", pairs, fields)
    if pairs:
        cells = sum(a[f"offence_{c}"] == b[f"offence_{c}"] for a, b in pairs for c in OFFENCE_CATEGORIES)
        print(f"   offence category calls the same: {pct(cells, len(pairs) * len(OFFENCE_CATEGORIES))}")
        cells = sum(a[f"general_{g}"] == b[f"general_{g}"] for a, b in pairs for g in GENERAL_MITIGATING)
        print(f"   general mitigating calls the same: {pct(cells, len(pairs) * len(GENERAL_MITIGATING))}")
        for g in GENERAL_MITIGATING:
            a1 = sum(a[f"general_{g}"] for a, _ in pairs); b1 = sum(b[f"general_{g}"] for _, b in pairs)
            same = sum(a[f"general_{g}"] == b[f"general_{g}"] for a, b in pairs)
            print(f"      {g:20s} first reader yes {a1:3d}, second model yes {b1:3d}, same call {same}/{len(pairs)}")

    # ---- agreement with the earlier rounds (shorter excerpts, same first model)
    by_key = {(r["court"], r["citation"]): r for r in rows}
    old = [o for o in csv.DictReader((LAB / "offence_labels.csv").open(encoding="utf-8")) if o["unclear"] == "0"]
    pairs = [(by_key[(o["court"], o["citation"])], o) for o in old if (o["court"], o["citation"]) in by_key]
    pairs = [(a, o) for a, o in pairs if not a["offence_unclear"]]
    if pairs:
        same = sum(all(a[f"offence_{c}"] == int(o[c]) for c in OFFENCE_CATEGORIES) for a, o in pairs)
        cells = sum(a[f"offence_{c}"] == int(o[c]) for a, o in pairs for c in OFFENCE_CATEGORIES)
        print(f"\nEARLIER OFFENCE ROUND: {len(pairs):,} decisions in both; every category the same in {pct(same, len(pairs))}; "
              f"category calls the same {pct(cells, len(pairs) * len(OFFENCE_CATEGORIES))}")
        for c in OFFENCE_CATEGORIES:
            both = sum(a[f"offence_{c}"] and int(o[c]) for a, o in pairs)
            new_only = sum(a[f"offence_{c}"] and not int(o[c]) for a, o in pairs)
            old_only = sum(int(o[c]) and not a[f"offence_{c}"] for a, o in pairs)
            print(f"      {c:12s} both {both:5d}   new reading only {new_only:4d}   earlier round only {old_only:4d}")
    old = list(csv.DictReader((LAB / "mitigation_labels.csv").open(encoding="utf-8")))
    pairs = [(by_key[(o["court"], o["citation"])], o) for o in old if (o["court"], o["citation"]) in by_key]
    if pairs:
        old_any = lambda o: any(o[f] == "M" for f in MITIGATION_FACTORS)      # noqa: E731
        same = sum(any_sys(a) == old_any(o) for a, o in pairs)
        print(f"\nEARLIER MITIGATING ROUND: {len(pairs):,} decisions in both; same answer on 'any systemic factor mitigating' in {pct(same, len(pairs))}")
        print(f"      mitigating in both {sum(any_sys(a) and old_any(o) for a, o in pairs)}, new reading only "
              f"{sum(any_sys(a) and not old_any(o) for a, o in pairs)}, earlier round only {sum(old_any(o) and not any_sys(a) for a, o in pairs)}")
        for f in MITIGATION_FACTORS:
            same = sum((a[f"systemic_{f}"] == "M") == (o[f] == "M") for a, o in pairs)
            print(f"      {f:18s} new reading M {sum(a[f'systemic_{f}'] == 'M' for a, _ in pairs):4d}, earlier M "
                  f"{sum(o[f] == 'M' for _, o in pairs):4d}, same call {pct(same, len(pairs))}")
        keyed = {(o["court"], o["citation"]) for o in old}
        outside = [r for r in rows if (r["court"], r["citation"]) not in keyed and any_sys(r)]
        print(f"      decisions with NO keyword match where the new reading found a systemic factor mitigating: {len(outside)}")
    return missing


def write_missing(missing):
    """Follow-up files for decisions with no valid answer."""
    if not missing:
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import make_full_read_batches as mb
    sample = {}
    for path in [LAB / "full_read_sample.csv"] + sorted(LAB.glob("full_read_sample_*.csv")):
        sample.update({r["id"]: r for r in csv.DictReader(path.open(encoding="utf-8"))})
    con = duckdb.connect()
    con.sql("CREATE TEMP TABLE pick(id VARCHAR, court VARCHAR, citation VARCHAR)")
    con.executemany("INSERT INTO pick VALUES (?,?,?)", [(i, sample[i]["court"], sample[i]["citation"]) for i in missing])
    rows = con.sql(f"""SELECT p.id, d.court, d.citation, d.name, CAST(d.decision_date AS VARCHAR), d.n_chars, d.text FROM pick p
                       JOIN read_parquet('{DATA}/*/*/decisions.parquet') d USING (court, citation) ORDER BY p.id""").fetchall()
    items = [dict(zip(["id", "court", "citation", "name", "decision_date", "n_chars", "text"], r)) for r in rows]
    folder = LAB / "full_read_batches"
    start = 9001 + len(list(folder.glob("read_9*.txt")))
    buf, size, count, number, written = [], 0, 0, start, 0
    for i, d in enumerate(items):
        _, lines = mb.item_lines(d)
        buf += lines
        size += sum(len(x) + 1 for x in lines)
        count += 1
        if size >= mb.FILE_CHARS or count >= 10 or i == len(items) - 1:
            (folder / f"read_{number:04d}.txt").write_text("\n".join(buf), encoding="utf-8")
            buf, size, count, number, written = [], 0, 0, number + 1, written + 1
    print(f"\nwrote {written} follow-up file(s) for {len(items)} decisions: read_{start:04d}.txt to read_{number - 1:04d}.txt")


if __name__ == "__main__":
    m = main()
    if "--write-missing" in sys.argv:
        write_missing(m)
