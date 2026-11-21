"""Prepare the decisions in the sentence-length models for a reading that counts the offences (counts) sentenced.

Only decisions in the length models (adult sentencing decisions with a fixed jail term). Each is shown as its opening,
its closing and the passages that mention counts or convictions; short decisions in full.

Output  data/labels/count_sample.csv and data/labels/count_batches/count_NNN.txt
    .venv\\Scripts\\python.exe -X utf8 scripts\\analysis\\make_count_batches.py [--new --tag TAG]
"""
import csv
import re
import sys
import textwrap
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data" / "labels"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))
from make_full_read_batches import body_start, merge  # noqa: E402
from make_sample import clean  # noqa: E402

FULL_LIMIT = 7000
OPENING, CLOSING = 2500, 3500
PER_FILE = 20
COUNT_WORDS = re.compile(r"\bcounts?\b|\bcharges?\b|convicted of|found guilty|pleaded guilty|pled guilty|guilty plea|"
                         r"concurrent|consecutive|stay(ed)? of proceedings|Kienapple", re.I)


def excerpt(text):
    if len(text) <= FULL_LIMIT:
        return "FULL TEXT: " + clean(text)
    bs = body_start(text)
    mid = text[bs + OPENING:len(text) - CLOSING]
    spans = merge([max(m.start() - 120, 0), min(m.start() + 300, len(mid))] for m in COUNT_WORDS.finditer(mid))
    picked, total = [], 0
    for a, b in spans:                        # the first passages, up to about 2,500 characters
        if total > 2500:
            break
        picked.append((a, b))
        total += b - a
    parts = [f"OPENING: {clean(text[bs:bs + OPENING])}"]
    if picked:
        parts.append("PASSAGES ABOUT COUNTS OR CONVICTIONS:")
        parts += ["  - ..." + clean(mid[a:b]) + "..." for a, b in picked]
    parts.append(f"CLOSING: {clean(text[-CLOSING:])}")
    return "\n".join(parts)


def main():
    sample_keys = set(map(tuple, load_keys()))
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else None
    sample_name, bdir, idp = (f"count_sample_{tag}.csv", f"count_batches_{tag}", f"{tag}_") if tag else \
                             ("count_sample.csv", "count_batches", "C")
    if tag:                                   # updates: only decisions without a count yet
        done = set()
        for p in LAB.glob("count_sample*.csv"):
            done |= {(r["court"], r["citation"]) for r in csv.DictReader(p.open(encoding="utf-8"))}
        sample_keys -= done
    rows = duckdb.sql(f"""SELECT d.court, d.citation, d.name, i.prison_time, i.sentence_outcome, d.text
                          FROM read_parquet('{(ROOT / "sentencing_data").as_posix()}/*/*/decisions.parquet') d
                          JOIN read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}') i USING (court, citation)
                          ORDER BY d.court, d.citation""").fetchall()
    rows = [r for r in rows if (r[0], r[1]) in sample_keys]
    (LAB / bdir).mkdir(parents=True, exist_ok=True)
    with (LAB / sample_name).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "court", "citation", "batch"])
        for b in range(0, len(rows), PER_FILE):
            lines = []
            for k, (court, cit, name, prison, outcome, text) in enumerate(rows[b:b + PER_FILE], b + 1):
                cid = f"{idp}{k:05d}"
                w.writerow([cid, court, cit, b // PER_FILE + 1])
                lines += [f"===== CASE {cid} =====", f"Citation: {cit} | Case: {name} | Outcome: {outcome} | Prison recorded: {prison}"]
                for para in excerpt(text).split("\n"):
                    lines.extend(textwrap.wrap(para, width=170, subsequent_indent="    ") or [""])
                lines.append("")
            (LAB / bdir / f"count_{b // PER_FILE + 1:03d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} decisions in {(len(rows) + PER_FILE - 1) // PER_FILE} files")


def load_keys():
    """(court, citation) of every decision in the length models."""
    d = duckdb.sql(f"""SELECT court, citation FROM read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}')
        WHERE prison_months > 0 AND sentence_outcome NOT IN ('no_sentence', 'unclear')
          AND NOT coalesce(penalty_youth_sentence, false)""").fetchall()
    return d


if __name__ == "__main__":
    main()
