"""Check the reasons (rationale) pictures for direction: does the court treat the systemic factor as MITIGATING?

Two things are checked for each picture:
  1. the court's overall conclusion in the passage: is the systemic factor treated as mitigating?
  2. each numbered highlight: does it state the opposite (the factor is not mitigating, has little weight, no link,
     is outweighed)? Such highlights are misleading and are dropped.

Usage
  make_direction_check_batches.py                  every picture on the site (original round, tag "direction")
  make_direction_check_batches.py --new --tag TAG  every picture not yet checked (updates; files TAG_direction_*)
  make_direction_check_batches.py --recheck --tag TAG  every picture on the site again (after the rules change)

Output  case_extracts/work/<tag>_sample.csv and case_extracts/work/<tag>_batches/<tag>_NN.txt
Answers are applied by apply_direction_check.py; build_site.py hides cases judged not mitigating.
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


def para_numbers(spec):
    """'40-41;47' or '40, 41, 47' -> [40, 41, 47]"""
    out = []
    for part in re.split(r"[;,]", spec or ""):
        nums = [int(x) for x in re.findall(r"\d+", part)]
        if len(nums) == 2 and "-" in part:
            out.extend(range(nums[0], nums[1] + 1))
        else:
            out.extend(nums)
    return sorted(set(out))


def current_highlights(pick, override):
    """The rationale highlights as drawn: the reader's picks, minus removals, plus additions (as render_extracts.py)."""
    drop = {x.strip().rstrip(".,;") for x in (override or {}).get("remove_rationale_highlights", [])}
    hl = [h for h in (pick or {}).get("rationale_highlights") or [] if h.strip().rstrip(".,;") not in drop]
    return hl + list((override or {}).get("add_rationale_highlights", []))


def main():
    picks = load_picks()
    overrides = json.loads((ROOT / "case_extracts" / "overrides.json").read_text(encoding="utf-8"))
    site = {c["citation"]: c for c in json.loads((ROOT / "site" / "cases.json").read_text(encoding="utf-8"))}
    rows = duckdb.sql(f"""
        SELECT e.court, e.citation, e.rationale_paragraphs, d.text
        FROM read_csv_auto('{(ROOT / "case_extracts" / "extracts.csv").as_posix()}', all_varchar=true) e
        JOIN read_parquet('{(ROOT / "sentencing_data").as_posix()}/*/*/decisions.parquet') d USING (court, citation)
        WHERE e.conclusion_clear = 'Y'
        ORDER BY e.court, e.citation
    """).fetchall()
    tag = "direction"
    if "--new" in sys.argv:
        tag = sys.argv[sys.argv.index("--tag") + 1] + "_direction"
        done = set()
        for p in WORK.glob("*direction_sample.csv"):
            done |= {(r["court"], r["citation"]) for r in csv.DictReader(p.open(encoding="utf-8"))}
        rows = [r for r in rows if (r[0], r[1]) not in done and (r[0], r[1]) in picks]
    elif "--recheck" in sys.argv:    # every picture on the site again, as a later round that replaces earlier answers
        tag = sys.argv[sys.argv.index("--tag") + 1] + "_direction"
        rows = [r for r in rows if r[1] in site]
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
                cid = f"D{k:03d}"
                o = overrides.get(cit)
                hl = current_highlights(picks.get((court, cit)), o)
                nums = para_numbers(spec) + [int(n) for n in (o or {}).get("add_rationale_paras", [])]
                w.writerow([cid, court, cit, json.dumps(hl, ensure_ascii=False), b // PER_FILE + 1])
                paras = paragraphs(text)
                factors = (site.get(cit) or {}).get("factors", "")
                lines.append(f"===== CASE {cid} ===== {cit}   factors tagged: {factors}")
                for i, h in enumerate(hl, 1):
                    lines.append(f"HIGHLIGHT {i}: {h}")
                lines.append("PARAGRAPHS:")
                for n in sorted(set(nums)):
                    if n in paras:
                        lines.extend(textwrap.wrap(f"[{n}] {paras[n]}", width=170, subsequent_indent="    "))
                lines.append("")
            (WORK / f"{tag}_batches" / f"{tag}_{b // PER_FILE + 1:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} decisions in {(len(rows) + PER_FILE - 1) // PER_FILE} files ({tag})")


if __name__ == "__main__":
    main()
