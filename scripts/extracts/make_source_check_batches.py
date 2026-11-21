"""Check whose words each rationale picture shows: the court's own reasoning, or a submission or report.

For every decision with pictures: the rationale paragraphs and the phrases highlighted in them.
Output  case_extracts/work/source_sample.csv and case_extracts/work/source_batches/source_NN.txt
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
    rows = duckdb.sql(f"""
        SELECT e.court, e.citation, e.rationale_paragraphs, d.text
        FROM read_csv_auto('{(ROOT / "case_extracts" / "extracts.csv").as_posix()}', all_varchar=true) e
        JOIN read_parquet('{(ROOT / "sentencing_data").as_posix()}/*/*/decisions.parquet') d USING (court, citation)
        WHERE e.rationale_png IS NOT NULL AND e.rationale_png <> ''
        ORDER BY e.court, e.citation
    """).fetchall()
    # --only FILE: just the decisions listed ("court|citation" per line), written as a separate set (recheck_*)
    tag = "source"
    if "--new" in sys.argv:          # updates: pictures not yet checked, written as TAG_source_*
        tag = sys.argv[sys.argv.index("--tag") + 1] + "_source"
        done = set()
        for p in WORK.glob("*_sample.csv"):
            if p.name.startswith(("source_", "recheck_")) or p.name.endswith("_source_sample.csv"):
                done |= {(r["court"], r["citation"]) for r in csv.DictReader(p.open(encoding="utf-8"))}
        rows = [r for r in rows if (r[0], r[1]) not in done]
    elif "--only" in sys.argv:
        keys = {tuple(l.strip().split("|")) for l in Path(sys.argv[sys.argv.index("--only") + 1]).read_text(encoding="utf-8").splitlines() if l.strip()}
        rows = [r for r in rows if (r[0], r[1]) in keys]
        tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "recheck"
    if not rows:
        print("Nothing new to do.")
        return
    (WORK / f"{tag}_batches").mkdir(parents=True, exist_ok=True)
    with (WORK / f"{tag}_sample.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "court", "citation", "batch"])
        for b in range(0, len(rows), PER_FILE):
            lines = []
            for k, (court, cit, spec, text) in enumerate(rows[b:b + PER_FILE], b + 1):
                cid = f"Q{k:03d}"
                w.writerow([cid, court, cit, b // PER_FILE + 1])
                paras = paragraphs(text)
                hl = (picks.get((court, cit)) or {}).get("rationale_highlights") or []
                lines.append(f"===== CASE {cid} ===== {cit}")
                lines.append("HIGHLIGHTED PHRASES: " + json.dumps(hl, ensure_ascii=False))
                for n in [int(x) for x in re.findall(r"\d+", spec or "")]:
                    if n in paras:
                        lines.extend(textwrap.wrap(f"[{n}] {paras[n]}", width=170, subsequent_indent="    "))
                lines.append("")
            (WORK / f"{tag}_batches" / f"{tag}_{b // PER_FILE + 1:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} decisions in {(len(rows) + PER_FILE - 1) // PER_FILE} files")


if __name__ == "__main__":
    main()
