"""Apply the direction check (pipeline/5d_check_direction.js) to the reasons pictures.

Reads every round (direction, TAG_direction, ...). For each case the Opus verifier's answer (<tag>_verify/<id>.json)
replaces the Sonnet reader's (<tag>_raw/*.jsonl); a later round replaces an earlier one.

Writes
  case_extracts/overrides.json        highlights that argue against the factor -> remove_rationale_highlights;
                                      trims (a highlight cut before a caveat) and missing statements of principle
                                      -> add_rationale_highlights
                                      (marked "direction_source": "direction check"); never every highlight of a case
  case_extracts/work/direction_verdicts.json   {citation: {"overall": ..., "reason": ...}}; build_site.py hides
                                      cases whose overall is "not_mitigating"
Then re-run render_extracts.py and build_site.py.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "case_extracts" / "work"
OVR = ROOT / "case_extracts" / "overrides.json"


def read_answers(tag):
    out = {}
    for p in sorted((WORK / f"{tag}_raw").glob(f"{tag}_*.jsonl")):
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("{"):
                a = json.loads(line)
                out[a.get("id")] = a | {"by": "reader"}
    for p in sorted((WORK / f"{tag}_verify").glob("*.json")):
        txt = p.read_text(encoding="utf-8-sig").strip()
        if txt.startswith("{"):
            a = json.loads(txt.splitlines()[0])
            out[a.get("id") or p.stem] = a | {"by": "verifier"}
    return out


def main():
    # Rounds in the order they were made (a later round replaces an earlier one's verdict)
    tags = [p.name[:-len("_sample.csv")] for p in sorted(WORK.glob("*direction_sample.csv"), key=lambda p: p.stat().st_mtime)]
    ovr = json.loads(OVR.read_text(encoding="utf-8"))
    verdicts, missing, dropped, cases, trimmed, added = {}, [], 0, 0, 0, 0
    for tag in tags:
        sample = {r["id"]: r for r in csv.DictReader((WORK / f"{tag}_sample.csv").open(encoding="utf-8"))}
        answers = read_answers(tag)
        for cid, s in sample.items():
            a = answers.get(cid)
            if not a:
                missing.append(f"{tag}:{cid}")
                continue
            overall = a.get("overall", "unclear")
            verdicts[s["citation"]] = {"overall": overall, "reason": a.get("reason", ""), "by": a["by"]}
            hl = json.loads(s["highlights_json"])
            entry = ovr.setdefault(s["citation"], {})
            keep = set(entry.get("keep_rationale_highlights", []))      # protected by hand
            adds = entry.setdefault("add_rationale_highlights", [])
            # Trims: replace a highlight by its start, cut before a caveat that argues against the factor
            for t in a.get("trim", []) or []:
                n, short = t.get("n"), (t.get("text") or "").strip()
                if not (str(n).isdigit() and 1 <= int(n) <= len(hl)) or not short:
                    continue
                orig = hl[int(n) - 1]
                if orig in keep or short not in orig or short == orig or short in adds:
                    continue
                if orig in adds:
                    adds.remove(orig)
                else:
                    entry["remove_rationale_highlights"] = sorted(set(entry.get("remove_rationale_highlights", [])) | {orig})
                adds.append(short)
                entry["direction_source"] = "direction check"
                trimmed += 1
            # Additions: statements of principle not yet highlighted
            for phrase in a.get("add", []) or []:
                phrase = (phrase or "").strip()
                if phrase and phrase not in adds and phrase not in hl:
                    adds.append(phrase)
                    entry["direction_source"] = "direction check"
                    added += 1
            if not adds:
                del entry["add_rationale_highlights"]
            if not entry:
                del ovr[s["citation"]]
            drop = sorted({int(n) for n in a.get("drop", []) if str(n).isdigit() and 1 <= int(n) <= len(hl)})
            if not drop or len(drop) >= len(hl):
                continue
            entry = ovr.setdefault(s["citation"], {})
            existing = set(entry.get("remove_rationale_highlights", []))
            new = [hl[n - 1] for n in drop if hl[n - 1] not in existing and hl[n - 1] not in keep]
            if new:
                entry["remove_rationale_highlights"] = sorted(existing | set(new))
                entry["direction_source"] = "direction check"
                entry["direction_why"] = a.get("reason", "") or "Highlight argues against the systemic factor"
                cases += 1
                dropped += len(new)
    OVR.write_text(json.dumps(ovr, indent=2, ensure_ascii=False), encoding="utf-8")
    (WORK / "direction_verdicts.json").write_text(json.dumps(verdicts, indent=1, ensure_ascii=False), encoding="utf-8")
    from collections import Counter
    print(f"{len(verdicts)} cases checked ({', '.join(tags)}); missing: {', '.join(missing) or 'none'}")
    print("overall:", dict(Counter(v["overall"] for v in verdicts.values())))
    print(f"{dropped} misleading highlights removed in {cases} cases; {trimmed} trimmed; {added} principle highlights added")
    for cit, v in sorted(verdicts.items()):
        if v["overall"] != "mitigating":
            print(f"  {v['overall']:15} {cit:18} ({v['by']}) {v['reason']}")


if __name__ == "__main__":
    main()
