"""Write the tag-gap answers into case_extracts/overrides.json.

A factor with a paragraph: add_rationale_paras + add_rationale_highlights (the paragraph joins the reasons picture).
A factor without one: drop_tags (the site no longer shows that tag for the case).
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "case_extracts" / "work"
OVR = ROOT / "case_extracts" / "overrides.json"


def main():
    import sys
    pre = (sys.argv[sys.argv.index("--tag") + 1] + "_gap") if "--tag" in sys.argv else "gap"
    sample = {r["id"]: r for r in csv.DictReader((WORK / f"{pre}_sample.csv").open(encoding="utf-8"))}
    answers = {}
    for p in sorted((WORK / f"{pre}_raw").glob(f"{pre}_*.jsonl")):
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("{"):
                a = json.loads(line)
                answers[a.get("id")] = a
    ovr = json.loads(OVR.read_text(encoding="utf-8"))
    added = dropped = 0
    for cid, s in sample.items():
        wanted = set(s["factors"].split(";"))
        entry = ovr.setdefault(s["citation"], {})
        got = {x.get("factor"): x for x in (answers.get(cid) or {}).get("add", [])}
        for f in wanted:
            x = got.get(f)
            if x and isinstance(x.get("paragraph"), int):
                paras = entry.setdefault("add_rationale_paras", [])
                if x["paragraph"] not in paras:
                    paras.append(x["paragraph"])
                if x.get("highlight"):
                    hl = entry.setdefault("add_rationale_highlights", [])
                    if x["highlight"] not in hl:
                        hl.append(x["highlight"])
                added += 1
            else:
                tags = entry.setdefault("drop_tags", [])
                if f not in tags:
                    tags.append(f)
                dropped += 1
        entry.setdefault("tag_rule", "every factor tag shown must be visible in the reasons picture (2026-11-21)")
    OVR.write_text(json.dumps(ovr, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(answers)} of {len(sample)} cases answered; {added} tags now shown by an added paragraph; {dropped} tags dropped")


if __name__ == "__main__":
    main()
