"""Merge the labellers' answers for the offence and mitigating-factor steps.

Outputs in data/labels/:
    offence_labels.csv      one row per sampled decision, one TRUE/FALSE column per offence category
    mitigation_labels.csv   one row per candidate decision, one code per factor (M, R, N or X)
Also prints agreement with the second model on the audit subsets, and writes a batch file of any
decisions the labellers skipped (offence_batches/offence_9NN.txt, mitigation_batches/mitigation_9NN.txt).
"""
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from enrichment_patterns import MITIGATION_FACTORS, OFFENCE_CATEGORIES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data" / "labels"


def read_raw(folder, pattern):
    rows = {}
    for path in sorted((LAB / folder).glob(pattern)):
        for r in csv.DictReader(path.open(encoding="utf-8-sig")):
            if r.get("id"):
                rows[r["id"].strip()] = {k: (v or "").strip() for k, v in r.items() if k}
    return rows


def parse_categories(text):
    cats = {c.strip().lower() for c in text.replace(",", ";").split(";") if c.strip()}
    return cats & set(OFFENCE_CATEGORIES), bool(cats - set(OFFENCE_CATEGORIES) - {"none"})


def offences():
    sample = list(csv.DictReader((LAB / "offence_sample.csv").open(encoding="utf-8")))
    raw = read_raw("offence_raw", "labels_offence_*.csv")
    out, missing, odd = [], [], 0
    for s in sample:
        r = raw.get(s["id"])
        if not r:
            missing.append(s["id"])
            continue
        cats, bad = parse_categories(r.get("categories", ""))
        odd += bad
        out.append({**{k: s[k] for k in ("id", "court", "citation", "name")},
                    **{c: int(c in cats) for c in OFFENCE_CATEGORIES},
                    "unclear": int(not cats), "confidence": r.get("confidence", "").upper(), "note": r.get("note", "")})
    with (LAB / "offence_labels.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"OFFENCES: {len(sample):,} sampled, {len(out):,} labelled, {len(missing)} missing, {odd} rows with an unknown code")
    print("  decisions per category:", {c: sum(r[c] for r in out) for c in OFFENCE_CATEGORIES})
    print("  unclear (no category):", sum(r["unclear"] for r in out), "  confidence:", dict(Counter(r["confidence"] for r in out)))
    print("  categories per decision:", dict(sorted(Counter(sum(r[c] for c in OFFENCE_CATEGORIES) for r in out).items())))

    audit = read_raw("offence_audit_raw", "labels_offence_audit_*.csv")
    main = {r["id"]: r for r in out}
    both = [(main[i], parse_categories(a.get("categories", ""))[0]) for i, a in audit.items() if i in main]
    if both:
        same_all = sum(all(m[c] == int(c in cats) for c in OFFENCE_CATEGORIES) for m, cats in both)
        cells = sum(m[c] == int(c in cats) for m, cats in both for c in OFFENCE_CATEGORIES)
        print(f"  audit by a second model: {len(both)} decisions; every category the same in {same_all}; "
              f"{cells} of {len(both) * len(OFFENCE_CATEGORIES)} category calls the same")
        for c in OFFENCE_CATEGORIES:
            a = sum(m[c] for m, _ in both); b = sum(c in cats for _, cats in both)
            agree = sum(m[c] == int(c in cats) for m, cats in both)
            print(f"     {c:12s} first model yes {a:3d}, second model yes {b:3d}, same call {agree}/{len(both)}")
    return missing


def mitigation():
    sample = list(csv.DictReader((LAB / "mitigation_sample.csv").open(encoding="utf-8")))
    raw = read_raw("mitigation_raw", "labels_mitigation_*.csv")
    out, missing = [], []
    for s in sample:
        r = raw.get(s["id"])
        if not r:
            missing.append(s["id"])
            continue
        codes = {f: (r.get(f, "X").upper()[:1] or "X") for f in MITIGATION_FACTORS}
        codes = {f: (v if v in "MRNX" else "X") for f, v in codes.items()}
        out.append({**{k: s[k] for k in ("id", "court", "citation", "name")}, **codes,
                    "hate_motivated": int(r.get("hate_motivated", "N").upper().startswith("Y")),
                    "confidence": r.get("confidence", "").upper(), "note": r.get("note", "")})
    with (LAB / "mitigation_labels.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"\nMITIGATING FACTORS: {len(sample):,} candidates, {len(out):,} labelled, {len(missing)} missing")
    for fct in MITIGATION_FACTORS:
        c = Counter(r[fct] for r in out)
        print(f"  {fct:18s} mitigating {c['M']:5d}   rejected {c['R']:4d}   mentioned only {c['N']:5d}   not mentioned {c['X']:5d}")
    any_m = sum(any(r[f] == "M" for f in MITIGATION_FACTORS) for r in out)
    print(f"  any factor mitigating: {any_m:,}   hate-motivated offence: {sum(r['hate_motivated'] for r in out)}   "
          f"confidence: {dict(Counter(r['confidence'] for r in out))}")

    audit = read_raw("mitigation_audit_raw", "labels_mitigation_audit_*.csv")
    main = {r["id"]: r for r in out}
    both = [(main[i], a) for i, a in audit.items() if i in main]
    if both:
        def is_m(row, f):
            return row.get(f, "X").upper().startswith("M")
        any_same = sum(any(is_m(m, f) for f in MITIGATION_FACTORS) == any(is_m(a, f) for f in MITIGATION_FACTORS) for m, a in both)
        print(f"  audit by a second model: {len(both)} decisions; same answer on 'any factor mitigating' in {any_same}")
        for f in MITIGATION_FACTORS:
            a1 = sum(is_m(m, f) for m, _ in both); a2 = sum(is_m(a, f) for _, a in both)
            agree = sum(is_m(m, f) == is_m(a, f) for m, a in both)
            print(f"     {f:18s} first model mitigating {a1:3d}, second model {a2:3d}, same call {agree}/{len(both)}")
    return missing


def write_missing(kind, missing):
    """Excerpts for skipped decisions, for a follow-up labelling pass."""
    if not missing:
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import duckdb
    import make_enrichment_batches as mb
    sample = {r["id"]: r for r in csv.DictReader((LAB / f"{kind}_sample.csv").open(encoding="utf-8"))}
    con = duckdb.connect()
    con.sql("CREATE TEMP TABLE pick(id VARCHAR, court VARCHAR, citation VARCHAR)")
    con.executemany("INSERT INTO pick VALUES (?,?,?)", [(i, sample[i]["court"], sample[i]["citation"]) for i in missing])
    rows = con.sql(f"""SELECT p.id, d.court, d.citation, d.name, d.n_chars, d.text FROM pick p
                       JOIN read_parquet('{mb.DATA}/*/*/decisions.parquet') d USING (court, citation) ORDER BY p.id""").fetchall()
    items = [dict(zip(["id", "court", "citation", "name", "n_chars", "text"], r)) for r in rows]
    per = mb.OFFENCE_PER_FILE if kind == "offence" else mb.MITIGATION_PER_FILE
    groups = mb.chunks(items, per)
    excerpt = mb.offence_excerpt if kind == "offence" else mb.mitigation_excerpt
    folder = LAB / f"{kind}_batches"
    for b, group in enumerate(groups, 901):
        lines = []
        for d in group:
            lines.append(f"===== ITEM {d['id']} =====")
            lines.append(f"Court: {mb.COURT_NAMES[d['court']]} | Case: {d['name']} | Length: {d['n_chars']:,} characters")
            for para in excerpt(d["text"]).split("\n"):
                lines.extend(mb.textwrap.wrap(para, width=170, subsequent_indent="    ") or [""])
            lines.append("")
        (folder / f"{kind}_{b:03d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"  wrote {len(groups)} follow-up file(s) for {len(items)} skipped {kind} decisions: {kind}_901.txt onward")


if __name__ == "__main__":
    m1 = offences()
    m2 = mitigation()
    if "--write-missing" in sys.argv:
        write_missing("offence", m1)
        write_missing("mitigation", m2)
