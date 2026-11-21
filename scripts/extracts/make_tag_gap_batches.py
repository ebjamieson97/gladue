"""Tags (systemic factors) shown on the site that the reasons picture does not show.

For each gap: the paragraphs of the decision that mention the factor, so a reader can pick one brief
paragraph (in the court's own words) to add to the picture, or say there is none (the tag is then dropped).
Input   case_extracts/work/tag_gaps.json   [court, citation, [factor labels]]
Output  case_extracts/work/gap_sample.csv, case_extracts/work/gap_batches/gap_NN.txt
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

TAG_RE = {"Gladue factors": r"Gladue|718\.2|Indigenous|Aboriginal|First Nations?|M[ée]tis|Inuit|Cree|Mi.kmaq|reserve",
          "Residential schools": r"residential school", "Colonialism": r"coloni[sz]",
          "Intergenerational trauma": r"intergenerational|inter-generational",
          "Anti-Black racism": r"\bBlack\b|African|anti-Black|IRCA|Impact of Race", "Systemic racism": r"racis|racial|discriminat",
          "Islamophobia": r"Islam|Muslim", "White supremacy": r"supremac", "Other prejudice": r"prejudic|homophob|antisemit|persecut"}
PER_FILE = 8


def main():
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else None     # update round: TAG_gaps.json -> TAG_gap_*
    gaps = json.loads((WORK / (f"{tag}_gaps.json" if tag else "tag_gaps.json")).read_text(encoding="utf-8"))
    pre = f"{tag}_gap" if tag else "gap"
    texts = {k: t for k, t in duckdb.sql(f"SELECT citation, text FROM read_parquet('{(ROOT / 'sentencing_data').as_posix()}/*/*/decisions.parquet')").fetchall()}
    shown = {r[0]: r[1] for r in duckdb.sql(f"SELECT citation, rationale_paragraphs FROM read_csv_auto('{(ROOT / 'case_extracts' / 'extracts.csv').as_posix()}', all_varchar=true)").fetchall()}
    (WORK / f"{pre}_batches").mkdir(parents=True, exist_ok=True)
    with (WORK / f"{pre}_sample.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "court", "citation", "factors", "batch"])
        for b in range(0, len(gaps), PER_FILE):
            lines = []
            for k, (court, cit, factors) in enumerate(gaps[b:b + PER_FILE], b + 1):
                cid = f"G{k:03d}"
                w.writerow([cid, court, cit, ";".join(factors), b // PER_FILE + 1])
                paras = paragraphs(texts[cit])
                lines.append(f"===== CASE {cid} ===== {cit}")
                lines.append(f"PARAGRAPHS ALREADY IN THE PICTURE: {shown.get(cit, '')}")
                for f in factors:
                    lines.append(f"--- FACTOR: {f} --- paragraphs that mention it:")
                    hits = [n for n, t in paras.items() if re.search(TAG_RE[f], t, re.I)]
                    for n in hits[:12]:
                        lines.extend(textwrap.wrap(f"[{n}] {paras[n]}", width=170, subsequent_indent="    "))
                    if not hits:
                        lines.append("(no paragraph mentions it)")
                lines.append("")
            (WORK / f"{pre}_batches" / f"{pre}_{b // PER_FILE + 1:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(gaps)} decisions in {(len(gaps) + PER_FILE - 1) // PER_FILE} files")


if __name__ == "__main__":
    main()
