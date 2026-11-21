"""Draw a second labelling sample (round 2) that excludes every decision already sampled.

Round 2 uses the same strata as round 1. Together the two rounds are a stratified random
sample, so weights are recomputed over the combined sample:
weight = decisions in the stratum / decisions sampled from it (both rounds).

Updates data/labels/sample.csv (round 2 rows get split = "new") and writes
data/labels/batches/batch_21.txt onward. Deterministic for a given SEED.
"""
import csv
import random
import textwrap
from pathlib import Path

import duckdb

from make_sample import COURT_NAMES, excerpt

SEED = "eval-v2"
ALLOCATION = {"0": 15, "1-2": 80, "3-9": 175, "10-24": 140, "25+": 110}   # 520 decisions
N_DOUBLE = 20
BATCH_UNIQUE = 26
FIRST_BATCH = 21

ROOT = Path(__file__).resolve().parents[2]
SIGNALS = (ROOT / "data" / "processed" / "criminal_decisions_signals.parquet").as_posix()
RAW = (ROOT / "data" / "raw" / "a2aj").as_posix()
LAB = ROOT / "data" / "labels"


def main() -> None:
    old = list(csv.DictReader((LAB / "sample.csv").open(encoding="utf-8")))
    if any(r["split"] == "new" for r in old):
        raise SystemExit("Round 2 has already been drawn.")
    con = duckdb.connect()
    con.sql("CREATE TEMP TABLE old(court VARCHAR, citation VARCHAR)")
    con.executemany("INSERT INTO old VALUES (?,?)", [(r["court"], r["citation"]) for r in old])
    alloc_sql = " ".join(f"WHEN '{k}' THEN {v}" for k, v in ALLOCATION.items())
    rows = con.sql(f"""
        WITH s AS (
            SELECT court, citation, name, n_sentenc, n_chars,
                   CASE WHEN n_sentenc = 0 THEN '0' WHEN n_sentenc <= 2 THEN '1-2'
                        WHEN n_sentenc <= 9 THEN '3-9' WHEN n_sentenc <= 24 THEN '10-24' ELSE '25+' END AS stratum
            FROM '{SIGNALS}'
        ), sized AS (
            SELECT *, count(*) OVER (PARTITION BY stratum) AS stratum_size FROM s
        ), r AS (
            SELECT *, row_number() OVER (PARTITION BY stratum ORDER BY hash(court || '|' || citation || '{SEED}')) AS rn
            FROM sized ANTI JOIN old USING (court, citation)
        )
        SELECT court, citation, name, n_sentenc, n_chars, stratum, stratum_size
        FROM r WHERE rn <= CASE stratum {alloc_sql} END ORDER BY stratum, rn
    """).fetchall()

    start = len(old) + 1
    new = [{"id": f"D{start + i:04d}", "court": c, "citation": cit, "name": nm, "n_sentenc": n, "n_chars": ch,
            "stratum": st, "stratum_size": sz, "split": "new"}
           for i, (c, cit, nm, n, ch, st, sz) in enumerate(rows)]

    con.sql("CREATE TEMP TABLE pick(id VARCHAR, court VARCHAR, citation VARCHAR)")
    con.executemany("INSERT INTO pick VALUES (?,?,?)", [(d["id"], d["court"], d["citation"]) for d in new])
    texts = dict(con.sql(f"""
        SELECT p.id, r.unofficial_text_en FROM pick p
        JOIN read_parquet('{RAW}/*/train.parquet') r ON r.dataset = p.court AND r.citation_en = p.citation
    """).fetchall())
    assert len(texts) == len(new)

    rng = random.Random(SEED)
    order = new[:]
    rng.shuffle(order)
    batches = [order[i:i + BATCH_UNIQUE] for i in range(0, len(order), BATCH_UNIQUE)]
    doubles = [d for d in order if d["stratum"] != "0"][:N_DOUBLE]
    for j, d in enumerate(doubles):
        home = next(b for b, batch in enumerate(batches) if d in batch)
        # send to a batch handled by a different labeller (labellers take batch pairs)
        target = (home + 2 + 2 * (j % (len(batches) // 2 - 1))) % len(batches)
        batches[target].append(d)

    for b, batch in enumerate(batches, FIRST_BATCH):
        lines = []
        for d in batch:
            d.setdefault("batches", []).append(b)
            lines.append(f"===== ITEM {d['id']} =====")
            lines.append(f"Court: {COURT_NAMES[d['court']]} | Case: {d['name']} | Length: {d['n_chars']:,} characters")
            for para in excerpt(texts[d["id"]]).split("\n"):
                lines.extend(textwrap.wrap(para, width=170, subsequent_indent="    ") or [""])
            lines.append("")
        (LAB / "batches" / f"batch_{b:02d}.txt").write_text("\n".join(lines), encoding="utf-8")

    combined = old + [{**d, "batches": " ".join(map(str, d["batches"]))} for d in new]
    per_stratum = {}
    for r in combined:
        per_stratum[r["stratum"]] = per_stratum.get(r["stratum"], 0) + 1
    for r in combined:
        r["weight"] = round(int(r["stratum_size"]) / per_stratum[r["stratum"]], 3)
    cols = ["id", "court", "citation", "name", "n_sentenc", "n_chars", "stratum", "stratum_size", "weight", "split", "batches"]
    with (LAB / "sample.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(combined)

    print(f"Round 2: {len(new)} decisions, {len(doubles)} labelled twice, batches {FIRST_BATCH}-{FIRST_BATCH + len(batches) - 1}")
    for s in ALLOCATION:
        print(f"  stratum {s:6s} round 2: {sum(d['stratum'] == s for d in new):4d}   combined: {per_stratum[s]:4d}")


if __name__ == "__main__":
    main()
