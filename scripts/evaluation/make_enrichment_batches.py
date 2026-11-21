"""Draw the samples for the offence and mitigating-factor steps, and write excerpts for labellers.

Offences:    5,000 sentencing decisions drawn purely at random from the selected decisions.
Mitigating:  every selected decision that matches a mitigation keyword (the "candidates").

Outputs in data/labels/:
    offence_sample.csv, offence_batches/, offence_audit_batches/
    mitigation_sample.csv, mitigation_batches/, mitigation_audit_batches/
Deterministic for the given seeds. Run build_sentencing_data.py first.
"""
import csv
import random
import re
import sys
import textwrap
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from enrichment_patterns import MITIGATION_KEYWORDS, MITIGATION_KEYWORDS_CASE_SENSITIVE  # noqa: E402
from make_sample import COURT_NAMES, clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = (ROOT / "sentencing_data").as_posix()
LAB = ROOT / "data" / "labels"

OFFENCE_N = 5000
OFFENCE_SEED = "offence-v1"
OFFENCE_PER_FILE = 22
OFFENCE_AUDIT = 100
MITIGATION_SEED = "mitigation-v1"
MITIGATION_PER_FILE = 10
MITIGATION_AUDIT = 60

CHARGE_WORDS = re.compile(r"convict|guilty|contrary to|charged with|counts?\b|indictment", re.I)
MITIGATION_RE = re.compile(MITIGATION_KEYWORDS, re.I)
MITIGATION_CS_RE = re.compile(MITIGATION_KEYWORDS_CASE_SENSITIVE)
MITIGATING_WORD = re.compile(r"mitigat|moral (blameworthiness|culpability)", re.I)


def body_start(text: str) -> int:
    idx = text.find("[1]")
    return idx if 0 <= idx < 8000 else min(2999, len(text))


def windows(text, positions, before, after, limit_chars):
    """Merge windows around positions; if too long, keep an evenly spaced subset."""
    spans = []
    for p in sorted(positions):
        a, b = max(p - before, 0), min(p + after, len(text))
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    total = sum(b - a for a, b in spans)
    if total > limit_chars and len(spans) > 1:
        keep = max(1, int(len(spans) * limit_chars / total))
        idx = sorted({round(i * (len(spans) - 1) / max(keep - 1, 1)) for i in range(keep)})
        spans = [spans[i] for i in idx]
    return ["..." + clean(text[a:b]) + "..." for a, b in spans]


def offence_excerpt(text: str) -> str:
    bs = body_start(text)
    if len(text) <= 5000:
        return "FULL TEXT: " + clean(text)
    parts = [f"HEADING (end of the header block): {clean(text[:bs])[-500:]}",
             f"OPENING: {clean(text[bs:bs + 1500])}"]
    mid_a, mid_b = bs + 1500, len(text) - 1000
    middle = text[mid_a:mid_b]
    hits = [m.start() for m in CHARGE_WORDS.finditer(middle)]
    picks = []
    for h in hits:                      # first six non-overlapping charge passages
        if not picks or h > picks[-1] + 340:
            picks.append(h)
        if len(picks) == 6:
            break
    if picks:
        parts.append("PASSAGES ABOUT CHARGES OR CONVICTIONS (from the middle):")
        parts += ["  - ..." + clean(middle[max(p - 80, 0):p + 260]) + "..." for p in picks]
    parts.append(f"CLOSING: {clean(text[-1000:])}")
    return "\n".join(parts)


def mitigation_excerpt(text: str) -> str:
    bs = body_start(text)
    if len(text) <= 7000:
        return "FULL TEXT: " + clean(text)
    parts = [f"HEADING (end of the header block): {clean(text[:bs])[-400:]}",
             f"OPENING: {clean(text[bs:bs + 900])}"]
    mid_a, mid_b = bs + 900, len(text) - 1200
    middle = text[mid_a:mid_b]
    key = [m.start() for m in MITIGATION_RE.finditer(middle)] + [m.start() for m in MITIGATION_CS_RE.finditer(middle)]
    parts.append(f"PASSAGES MENTIONING THE KEYWORDS ({len(key)} mentions in the middle of the decision):")
    parts += ["  - " + w for w in windows(middle, key, 350, 450, 4800)]
    mit = [m.start() for m in MITIGATING_WORD.finditer(middle)]
    if mit:
        parts.append("PASSAGES ABOUT MITIGATING FACTORS:")
        parts += ["  - " + w for w in windows(middle, mit, 150, 350, 1500)]
    parts.append(f"CLOSING: {clean(text[-1200:])}")
    return "\n".join(parts)


def write_batches(folder, prefix, groups, make_excerpt):
    folder.mkdir(parents=True, exist_ok=True)
    for b, group in enumerate(groups, 1):
        lines = []
        for d in group:
            lines.append(f"===== ITEM {d['id']} =====")
            lines.append(f"Court: {COURT_NAMES[d['court']]} | Case: {d['name']} | Length: {d['n_chars']:,} characters")
            for para in make_excerpt(d["text"]).split("\n"):
                lines.extend(textwrap.wrap(para, width=170, subsequent_indent="    ") or [""])
            lines.append("")
        (folder / f"{prefix}_{b:03d}.txt").write_text("\n".join(lines), encoding="utf-8")


def chunks(items, n):
    return [items[i:i + n] for i in range(0, len(items), n)]


def save_sample(path, rows, batch_of):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "court", "citation", "name", "n_chars", "batch"])
        for d in rows:
            w.writerow([d["id"], d["court"], d["citation"], d["name"], d["n_chars"], batch_of[d["id"]]])


def main():
    con = duckdb.connect()
    con.sql(f"CREATE VIEW d AS SELECT court, citation, name, n_chars, text FROM read_parquet('{DATA}/*/*/decisions.parquet')")
    cols = ["court", "citation", "name", "n_chars", "text"]

    # ---- offences: 5,000 at random
    rows = con.sql(f"SELECT * FROM d ORDER BY hash(court || '|' || citation || '{OFFENCE_SEED}') LIMIT {OFFENCE_N}").fetchall()
    off = [dict(zip(cols, r), id=f"F{i:04d}") for i, r in enumerate(rows, 1)]
    groups = chunks(off, OFFENCE_PER_FILE)
    write_batches(LAB / "offence_batches", "offence", groups, offence_excerpt)
    save_sample(LAB / "offence_sample.csv", off, {d["id"]: b for b, g in enumerate(groups, 1) for d in g})
    rng = random.Random(OFFENCE_SEED)
    audit = rng.sample(off, OFFENCE_AUDIT)
    write_batches(LAB / "offence_audit_batches", "offence_audit", chunks(audit, 25), offence_excerpt)
    print(f"Offences: {len(off):,} decisions in {len(groups)} files; audit subset {len(audit)}")

    # ---- mitigating factors: every candidate
    kw = MITIGATION_KEYWORDS.replace("'", "''")
    kw_cs = MITIGATION_KEYWORDS_CASE_SENSITIVE.replace("'", "''")
    rows = con.sql(f"""
        SELECT * FROM d
        WHERE regexp_matches(text, '{kw}', 'i') OR regexp_matches(text, '{kw_cs}')
        ORDER BY hash(court || '|' || citation || '{MITIGATION_SEED}')
    """).fetchall()
    mit = [dict(zip(cols, r), id=f"M{i:04d}") for i, r in enumerate(rows, 1)]
    groups = chunks(mit, MITIGATION_PER_FILE)
    write_batches(LAB / "mitigation_batches", "mitigation", groups, mitigation_excerpt)
    save_sample(LAB / "mitigation_sample.csv", mit, {d["id"]: b for b, g in enumerate(groups, 1) for d in g})
    rng = random.Random(MITIGATION_SEED)
    audit = rng.sample(mit, MITIGATION_AUDIT)
    write_batches(LAB / "mitigation_audit_batches", "mitigation_audit", chunks(audit, 10), mitigation_excerpt)
    print(f"Mitigating factors: {len(mit):,} candidate decisions in {len(groups)} files; audit subset {len(audit)}")

    for name in ("offence_batches", "mitigation_batches"):
        sizes = [p.stat().st_size / 1024 for p in (LAB / name).glob("*.txt")]
        print(f"  {name}: mean file {sum(sizes) / len(sizes):.0f} KB, largest {max(sizes):.0f} KB")


if __name__ == "__main__":
    main()
