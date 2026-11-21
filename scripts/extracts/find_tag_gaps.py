"""Find factor tags that a reasons picture does not show (rule: every tag shown must be visible in the picture).

Writes case_extracts/work/tag_gaps.json (or TAG_gaps.json with --new --tag TAG), the input of make_tag_gap_batches.py.
--new checks only decisions whose pick came from an update round and that have no tag-rule entry in overrides.json.
"""
import json
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "case_extracts" / "work"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_extract_batches import paragraphs  # noqa: E402
from make_tag_gap_batches import TAG_RE  # noqa: E402
from render_extracts import load_picks  # noqa: E402

FACTOR_COLS = {"mitigating_gladue_factors": "Gladue factors", "mitigating_res_school": "Residential schools",
               "mitigating_colonialism": "Colonialism", "mitigating_intergen_trauma": "Intergenerational trauma",
               "mitigating_anti_black_racism": "Anti-Black racism", "mitigating_systemic_racism": "Systemic racism",
               "mitigating_islamophobia": "Islamophobia", "mitigating_white_supremacy": "White supremacy",
               "mitigating_other_prejudice": "Other prejudice"}


def main():
    new = "--new" in sys.argv
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else None
    picks = load_picks()
    ovr = json.loads((ROOT / "case_extracts" / "overrides.json").read_text(encoding="utf-8"))
    rows = duckdb.sql(f"""SELECT court, citation, {", ".join(FACTOR_COLS)}
        FROM read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}') WHERE mitigating_any_systemic""").fetchall()
    texts = {(c, k): t for c, k, t in duckdb.sql(f"SELECT court, citation, text FROM read_parquet('{(ROOT / 'sentencing_data').as_posix()}/*/*/decisions.parquet')").fetchall()}
    gaps = []
    for court, cit, *flags in rows:
        pk = picks.get((court, cit))
        if not pk:
            continue
        if new and (pk.get("round") in ("raw", "raw_redo") or "tag_rule" in (ovr.get(cit) or {})):
            continue
        paras = paragraphs(texts[(court, cit)])
        spec = str(pk.get("rationale_paras") or "") + ";" + ";".join(str(n) for n in (ovr.get(cit) or {}).get("add_rationale_paras", []))
        shown = " ".join(paras.get(int(n), "") for n in re.findall(r"\d+", spec))
        labels = [lab for lab, on in zip(FACTOR_COLS.values(), flags) if on is True]
        missing = [lab for lab in labels if lab not in (ovr.get(cit) or {}).get("drop_tags", [])
                   and not re.search(TAG_RE[lab], shown, re.I)]
        if missing:
            gaps.append([court, cit, missing])
    if new and not gaps:
        print("Nothing new to do.")
        return
    out = WORK / (f"{tag}_gaps.json" if new else "tag_gaps.json")
    out.write_text(json.dumps(gaps), encoding="utf-8")
    print(f"{len(gaps)} decisions with a tag not visible in the reasons picture -> {out.name}")


if __name__ == "__main__":
    main()
