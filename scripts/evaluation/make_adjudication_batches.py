"""Decisions where the two readings of the systemic factors disagree, prepared for a third reading.

The keyword review (data/labels/mitigation_labels.csv, excerpts built around the keywords) and the
full reading (data/labels/decision_labels.csv, excerpts built around the sentence) were done from
different excerpts. Where they disagree on whether any systemic factor was mitigating, a third
reader (a different model) sees a longer text and decides.

Output  data/labels/adjudication_sample.csv and data/labels/adjudication_batches/adjudicate_NN.txt
"""
import csv
import re
import sys
import textwrap
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrichment_patterns import MITIGATION_FACTORS, MITIGATION_KEYWORDS, MITIGATION_KEYWORDS_CASE_SENSITIVE  # noqa: E402
from make_full_read_batches import body_start, merge, pick  # noqa: E402
from make_sample import COURT_NAMES, clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data" / "labels"
DATA = (ROOT / "sentencing_data").as_posix()
FULL_LIMIT = 40000
PER_FILE = 8

PASSAGES = [
    (re.compile(MITIGATION_KEYWORDS, re.I), 500, 700, 9000, "spread"),
    (re.compile(MITIGATION_KEYWORDS_CASE_SENSITIVE), 500, 700, 1500, "spread"),
    (re.compile(r"aboriginal|indigenous|first nation|m[ée]tis|inuit|racializ|systemic|discriminat", re.I), 300, 500, 3000, "spread"),
    (re.compile(r"mitigat", re.I), 250, 600, 3000, "spread"),
]


def excerpt(text):
    if len(text) <= FULL_LIMIT:
        return "FULL TEXT: " + clean(text)
    bs = body_start(text)
    parts = [f"HEADING: {clean(text[:bs])[-500:]}", f"OPENING: {clean(text[bs:bs + 3000])}"]
    middle = text[bs + 3000:len(text) - 5000]
    spans = merge([s for p in PASSAGES for s in pick(middle, *p)])
    parts.append("PASSAGES FROM THE MIDDLE (in order; text between them is left out):")
    parts += ["  - ..." + clean(middle[a:b]) + "..." for a, b in spans]
    parts.append(f"CLOSING: {clean(text[-5000:])}")
    return "\n".join(parts)


def main():
    old = {(r["court"], r["citation"]): r for r in csv.DictReader((LAB / "mitigation_labels.csv").open(encoding="utf-8"))}
    new = list(csv.DictReader((LAB / "decision_labels.csv").open(encoding="utf-8")))
    pick_rows = []
    for r in new:
        o = old.get((r["court"], r["citation"]))
        first = dict(x.split("=") for x in r["reading_systemic"].split(";") if "=" in x)   # codes as first read
        new_m = {f for f in MITIGATION_FACTORS if first.get(f) == "M"}
        old_m = {f for f in MITIGATION_FACTORS if o and o[f] == "M"}
        if o and new_m != old_m:
            pick_rows.append((r, "readings disagree"))
    con = duckdb.connect()
    con.sql("CREATE TEMP TABLE p(id VARCHAR, court VARCHAR, citation VARCHAR, why VARCHAR)")
    con.executemany("INSERT INTO p VALUES (?,?,?,?)", [(r["id"], r["court"], r["citation"], w) for r, w in pick_rows])
    rows = con.sql(f"""SELECT p.id, d.court, d.citation, d.name, d.n_chars, d.text, p.why FROM p
                       JOIN read_parquet('{DATA}/*/*/decisions.parquet') d USING (court, citation) ORDER BY p.id""").fetchall()
    folder = LAB / "adjudication_batches"
    folder.mkdir(exist_ok=True)
    for f in folder.glob("*.txt"):
        f.unlink()
    with (LAB / "adjudication_sample.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "court", "citation", "name", "why", "batch"])
        for b in range(0, len(rows), PER_FILE):
            lines = []
            for i, court, cit, name, n, text, why in rows[b:b + PER_FILE]:
                w.writerow([i, court, cit, name, why, b // PER_FILE + 1])
                lines += [f"===== ITEM {i} =====",
                          f"Court: {COURT_NAMES[court]} | Case: {name} | Length: {n:,} characters"]
                for para in excerpt(text).split("\n"):
                    lines.extend(textwrap.wrap(para, width=170, subsequent_indent="    ") or [""])
                lines.append("")
            (folder / f"adjudicate_{b // PER_FILE + 1:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} decisions in {(len(rows) + PER_FILE - 1) // PER_FILE} files")


if __name__ == "__main__":
    main()
