"""Merge the labellers' files into one label per sampled decision.

Inputs:  data/labels/sample.csv, data/labels/raw/labels_batch_NN.csv,
         data/labels/adjudication.csv (optional; final say on disputed items)
Output:  data/labels/labels.csv

Each labeller handled two consecutive batch files (1-2, 3-4, ...). A decision that
was labelled in batches handled by two different labellers counts as an independent
double label, and is used to measure how consistent the labels are.
"""
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data" / "labels"
VALID = {"IMPOSES", "REVIEWS", "RELATED", "NOT"}


def is_sentencing(label: str) -> bool:
    return label in ("IMPOSES", "REVIEWS")


def main() -> None:
    sample = {r["id"]: r for r in csv.DictReader((LAB / "sample.csv").open(encoding="utf-8"))}
    got = defaultdict(list)
    for path in sorted((LAB / "raw").glob("labels_batch_*.csv")):
        batch = int(re.search(r"(\d+)", path.stem).group(1))
        for r in csv.DictReader(path.open(encoding="utf-8-sig")):
            rid, label = r["id"].strip(), r["label"].strip().upper()
            if rid not in sample or label not in VALID:
                print(f"  ignoring bad row in {path.name}: {r}")
                continue
            got[rid].append({"batch": batch, "labeller": (batch + 1) // 2, "label": label,
                             "depth": (r.get("depth") or "NA").strip().upper(),
                             "confidence": (r.get("confidence") or "").strip().upper(),
                             "note": (r.get("note") or "").strip()})

    adj_path = LAB / "adjudication.csv"
    adjudicated = {r["id"]: r for r in csv.DictReader(adj_path.open(encoding="utf-8"))} if adj_path.exists() else {}

    missing = [i for i in sample if i not in got]
    print(f"{len(sample)} sampled, {len(got)} labelled, {len(missing)} missing {missing[:10]}")

    pairs, out, disputes = [], [], []
    for rid, s in sample.items():
        labs = got.get(rid, [])
        if not labs:
            continue
        indep = {l["labeller"]: l for l in labs}          # one label per labeller
        labs_i = list(indep.values())
        if len(labs_i) >= 2:
            pairs.append((rid, labs_i[0], labs_i[1]))
        first = labs_i[0]
        agree4 = len({l["label"] for l in labs_i}) == 1
        agree2 = len({is_sentencing(l["label"]) for l in labs_i}) == 1
        final = dict(first)
        status = "single" if len(labs_i) == 1 else ("agreed" if agree4 else "disputed")
        if rid in adjudicated:
            a = adjudicated[rid]
            final.update(label=a["label"].strip().upper(), depth=a["depth"].strip().upper(), note=a["note"].strip())
            status = "adjudicated"
        elif status == "disputed":
            disputes.append((rid, labs_i))
        out.append({**{k: s[k] for k in ("id", "court", "citation", "name", "n_sentenc", "n_chars", "stratum", "stratum_size", "weight", "split", "in_stratified", "in_random")},
                    "label": final["label"], "depth": final["depth"], "confidence": final["confidence"],
                    "note": final["note"], "status": status, "batches": s["batches"]})

    with (LAB / "labels.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    print("\nLabels:", dict(Counter(r["label"] for r in out)))
    print("Depth (IMPOSES/REVIEWS):", dict(Counter(r["depth"] for r in out if is_sentencing(r["label"]))))
    print("Confidence:", dict(Counter(r["confidence"] for r in out)))
    print("By stratum (share labelled IMPOSES or REVIEWS):")
    for st in ("0", "1-2", "3-9", "10-24", "25+"):
        sub = [r for r in out if r["stratum"] == st]
        pos = sum(is_sentencing(r["label"]) for r in sub)
        print(f"   {st:6s} {pos:3d} of {len(sub):3d}")

    if pairs:
        a4 = sum(a["label"] == b["label"] for _, a, b in pairs)
        a2 = sum(is_sentencing(a["label"]) == is_sentencing(b["label"]) for _, a, b in pairs)
        print(f"\nIndependent double labels: {len(pairs)}")
        print(f"   same of the 4 labels:           {a4} of {len(pairs)}")
        print(f"   same sentencing / not decision: {a2} of {len(pairs)}")
    if disputes:
        print(f"\n{len(disputes)} disputed items not yet adjudicated:")
        for rid, labs in disputes:
            print(f"   {rid} [{sample[rid]['citation']}] batches {sample[rid]['batches']}: " +
                  " | ".join(f"{l['label']}/{l['depth']}/{l['confidence']} ({l['note']})" for l in labs))


if __name__ == "__main__":
    main()
