"""Check the crime pictures on the site for filler highlights (incidental or investigative details rather than serious acts).

Output  case_extracts/work/filler_sample.csv and case_extracts/work/filler_batches/filler_NN.txt
Each highlight is numbered so the reader can say which to drop; apply_filler_check.py writes the drops to overrides.json.
"""
import csv
import json
import re
import sys
import textwrap
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "case_extracts" / "work"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_extract_batches import paragraphs  # noqa: E402
from render_extracts import load_picks  # noqa: E402

PER_FILE = 15


def main():
    picks = load_picks()
    site = {c["citation"] for c in json.loads((ROOT / "site" / "cases.json").read_text(encoding="utf-8"))}
    rows = duckdb.sql(f"""
        SELECT e.court, e.citation, e.crime_paragraphs, d.text
        FROM read_csv_auto('{(ROOT / "case_extracts" / "extracts.csv").as_posix()}', all_varchar=true) e
        JOIN read_parquet('{(ROOT / "sentencing_data").as_posix()}/*/*/decisions.parquet') d USING (court, citation)
        ORDER BY e.court, e.citation
    """).fetchall()
    tag = "filler"
    if "--new" in sys.argv:          # updates: every picture not yet checked (site or not), written as TAG_filler_*
        tag = sys.argv[sys.argv.index("--tag") + 1] + "_filler"
        done = set()
        for p in WORK.glob("*filler_sample.csv"):
            done |= {(r["court"], r["citation"]) for r in csv.DictReader(p.open(encoding="utf-8"))}
        rows = [r for r in rows if (r[0], r[1]) not in done and (r[0], r[1]) in picks]
    else:
        rows = [r for r in rows if r[1] in site]
    if not rows:
        print("Nothing new to do.")
        return
    (WORK / f"{tag}_batches").mkdir(parents=True, exist_ok=True)
    with (WORK / f"{tag}_sample.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "court", "citation", "highlights_json", "batch"])
        for b in range(0, len(rows), PER_FILE):
            lines = []
            for k, (court, cit, spec, text) in enumerate(rows[b:b + PER_FILE], b + 1):
                cid = f"F{k:03d}"
                hl = (picks.get((court, cit)) or {}).get("crime_highlights") or []
                w.writerow([cid, court, cit, json.dumps(hl, ensure_ascii=False), b // PER_FILE + 1])
                paras = paragraphs(text)
                lines.append(f"===== CASE {cid} ===== {cit}")
                for i, h in enumerate(hl, 1):
                    lines.append(f"HIGHLIGHT {i}: {h}")
                lines.append("PARAGRAPHS:")
                for n in [int(x) for x in re.findall(r"\d+", spec or "")]:
                    if n in paras:
                        lines.extend(textwrap.wrap(f"[{n}] {paras[n]}", width=170, subsequent_indent="    "))
                lines.append("")
            (WORK / f"{tag}_batches" / f"{tag}_{b // PER_FILE + 1:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} site decisions in {(len(rows) + PER_FILE - 1) // PER_FILE} files")


if __name__ == "__main__":
    main()
