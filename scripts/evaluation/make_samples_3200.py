"""Draw the two 3,200-decision evaluation samples and write excerpt files for what still needs labels.

  Stratum random sample: 3,200 decisions, random within five strata by COUNT of "sentenc...".
                         Extends the 1,000 decisions already labelled (same strata, same proportions).
  Random sample:         3,200 decisions drawn purely at random from all criminal decisions.

A decision can be in both samples; it is labelled once.

Updates data/labels/sample.csv (adds columns in_stratified, in_random) and writes
data/labels/batches/batch_41.txt onward, plus data/labels/audit_batches/ (a subset to be
labelled a second time by a different model). Deterministic for the given seeds.
"""
import csv
import random
import textwrap
from pathlib import Path

import duckdb

from make_sample import COURT_NAMES, excerpt

SEED_STRATIFIED = "eval-v3"
SEED_RANDOM = "random-v1"
STRATIFIED_TARGET = {"0": 96, "1-2": 496, "3-9": 1072, "10-24": 864, "25+": 672}   # 3,200
RANDOM_N = 3200
BATCH_SIZE = 26
FIRST_BATCH = 41
N_AUDIT = 104

ROOT = Path(__file__).resolve().parents[2]
SIGNALS = (ROOT / "data" / "processed" / "criminal_decisions_signals.parquet").as_posix()
RAW = (ROOT / "data" / "raw" / "a2aj").as_posix()
LAB = ROOT / "data" / "labels"

STRATUM_SQL = """CASE WHEN n_sentenc = 0 THEN '0' WHEN n_sentenc <= 2 THEN '1-2'
                      WHEN n_sentenc <= 9 THEN '3-9' WHEN n_sentenc <= 24 THEN '10-24' ELSE '25+' END"""


def write_batches(folder: Path, prefix: str, first: int, batches, texts) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for b, batch in enumerate(batches, first):
        lines = []
        for d in batch:
            lines.append(f"===== ITEM {d['id']} =====")
            lines.append(f"Court: {COURT_NAMES[d['court']]} | Case: {d['name']} | Length: {int(d['n_chars']):,} characters")
            for para in excerpt(texts[d["id"]]).split("\n"):
                lines.extend(textwrap.wrap(para, width=170, subsequent_indent="    ") or [""])
            lines.append("")
        (folder / f"{prefix}_{b:02d}.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    old = list(csv.DictReader((LAB / "sample.csv").open(encoding="utf-8")))
    if "in_random" in old[0]:
        raise SystemExit("The 3,200 samples have already been drawn.")
    con = duckdb.connect()
    con.sql("CREATE TEMP TABLE old(court VARCHAR, citation VARCHAR)")
    con.executemany("INSERT INTO old VALUES (?,?)", [(r["court"], r["citation"]) for r in old])
    have = {}
    for r in old:
        have[r["stratum"]] = have.get(r["stratum"], 0) + 1
    need_sql = " ".join(f"WHEN '{k}' THEN {STRATIFIED_TARGET[k] - have[k]}" for k in STRATIFIED_TARGET)

    con.sql(f"""CREATE TEMP TABLE frame AS
        SELECT court, citation, name, n_sentenc, n_chars, {STRATUM_SQL} AS stratum,
               count(*) OVER (PARTITION BY {STRATUM_SQL}) AS stratum_size
        FROM '{SIGNALS}'""")
    strat_new = con.sql(f"""
        WITH r AS (
            SELECT *, row_number() OVER (PARTITION BY stratum ORDER BY hash(court || '|' || citation || '{SEED_STRATIFIED}')) AS rn
            FROM frame ANTI JOIN old USING (court, citation)
        )
        SELECT court, citation, name, n_sentenc, n_chars, stratum, stratum_size
        FROM r WHERE rn <= CASE stratum {need_sql} END ORDER BY stratum, rn
    """).fetchall()
    rand = con.sql(f"""
        SELECT court, citation, name, n_sentenc, n_chars, stratum, stratum_size
        FROM frame ORDER BY hash(court || '|' || citation || '{SEED_RANDOM}') LIMIT {RANDOM_N}
    """).fetchall()

    rows = {(r["court"], r["citation"]): {**r, "in_stratified": 1, "in_random": 0} for r in old}
    next_id = len(old) + 1
    new = []

    def add(rec, split, in_strat):
        nonlocal next_id
        c, cit, nm, n, ch, st, sz = rec
        d = {"id": f"D{next_id:04d}", "court": c, "citation": cit, "name": nm, "n_sentenc": n, "n_chars": ch,
             "stratum": st, "stratum_size": sz, "split": split, "in_stratified": in_strat, "in_random": 0,
             "batches": ""}
        next_id += 1
        rows[(c, cit)] = d
        new.append(d)

    for rec in strat_new:
        add(rec, "round3", 1)
    for rec in rand:
        key = (rec[0], rec[1])
        if key not in rows:
            add(rec, "random", 0)
        rows[key]["in_random"] = 1

    for d in rows.values():
        d["weight"] = round(int(d["stratum_size"]) / STRATIFIED_TARGET[d["stratum"]], 4) if int(d["in_stratified"]) else ""

    con.sql("CREATE TEMP TABLE pick(id VARCHAR, court VARCHAR, citation VARCHAR)")
    con.executemany("INSERT INTO pick VALUES (?,?,?)", [(d["id"], d["court"], d["citation"]) for d in new])
    texts = dict(con.sql(f"""
        SELECT p.id, r.unofficial_text_en FROM pick p
        JOIN read_parquet('{RAW}/*/train.parquet') r ON r.dataset = p.court AND r.citation_en = p.citation
    """).fetchall())
    assert len(texts) == len(new), "some sampled decisions were not found in the raw files"

    rng = random.Random(SEED_STRATIFIED)
    order = new[:]
    rng.shuffle(order)
    batches = [order[i:i + BATCH_SIZE] for i in range(0, len(order), BATCH_SIZE)]
    for b, batch in enumerate(batches, FIRST_BATCH):
        for d in batch:
            d["batches"] = str(b)
    write_batches(LAB / "batches", "batch", FIRST_BATCH, batches, texts)

    # Audit subset: new decisions that mention "sentence" at least once, to be labelled again by another model.
    audit = [d for d in order if int(d["n_sentenc"]) >= 1][:N_AUDIT]
    audit_batches = [audit[i:i + BATCH_SIZE] for i in range(0, len(audit), BATCH_SIZE)]
    write_batches(LAB / "audit_batches", "audit", 1, audit_batches, texts)

    cols = ["id", "court", "citation", "name", "n_sentenc", "n_chars", "stratum", "stratum_size", "weight",
            "split", "batches", "in_stratified", "in_random"]
    with (LAB / "sample.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda d: d["id"].lstrip("D").zfill(5)))

    allr = list(rows.values())
    print(f"Stratum random sample: {sum(int(d['in_stratified']) for d in allr):,}   "
          f"Random sample: {sum(int(d['in_random']) for d in allr):,}   "
          f"in both: {sum(int(d['in_stratified']) and int(d['in_random']) for d in allr):,}")
    print(f"Already labelled: {len(old):,}.  New decisions to label: {len(new):,} in batches "
          f"{FIRST_BATCH}-{FIRST_BATCH + len(batches) - 1}.  Audit subset: {len(audit)} in {len(audit_batches)} files.")
    for s in STRATIFIED_TARGET:
        print(f"  stratum {s:6s} stratified: {sum(d['stratum'] == s and int(d['in_stratified']) for d in allr):5d}"
              f"   random: {sum(d['stratum'] == s and int(d['in_random']) for d in allr):5d}")


if __name__ == "__main__":
    main()
