"""Write the filler highlights flagged by the check into case_extracts/overrides.json.

Hand-written entries are kept; entries from the check are marked "source": "filler check".
Never removes every highlight of a case.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "case_extracts" / "work"
OVR = ROOT / "case_extracts" / "overrides.json"


def main():
    import sys
    tag = (sys.argv[sys.argv.index("--tag") + 1] + "_filler") if "--tag" in sys.argv else "filler"
    sample = {r["id"]: r for r in csv.DictReader((WORK / f"{tag}_sample.csv").open(encoding="utf-8"))}
    answers = {}
    for p in sorted((WORK / f"{tag}_raw").glob(f"{tag}_*.jsonl")):
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("{"):
                a = json.loads(line)
                answers[a.get("id")] = a
    ovr = json.loads(OVR.read_text(encoding="utf-8")) if OVR.exists() else {}
    cases = phrases = 0
    for cid, s in sample.items():
        a = answers.get(cid)
        hl = json.loads(s["highlights_json"])
        drop = sorted({int(n) for n in (a or {}).get("drop", []) if str(n).isdigit() and 1 <= int(n) <= len(hl)})
        if not drop or len(drop) >= len(hl):
            continue
        entry = ovr.setdefault(s["citation"], {})
        existing = set(entry.get("remove_crime_highlights", []))
        new = [hl[n - 1] for n in drop if hl[n - 1] not in existing]
        if new:
            entry["remove_crime_highlights"] = sorted(existing | set(new))
            entry.setdefault("source", "filler check")
            entry.setdefault("why", a.get("reason", "") or "Filler highlight flagged by the check")
            cases += 1
            phrases += len(new)
    OVR.write_text(json.dumps(ovr, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(answers)} of {len(sample)} cases checked; {phrases} filler highlights removed in {cases} cases")


if __name__ == "__main__":
    main()
