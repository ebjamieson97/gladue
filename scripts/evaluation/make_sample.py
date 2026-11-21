"""Draw the labelling sample and write excerpt files for labellers.

The sample is a stratified random sample of criminal decisions, stratified by how
often "sentenc..." appears, because the hard cases are the ones with few mentions.
Each sampled decision gets a weight (decisions in its stratum / sampled from it),
so results can be scaled back up to the full collection.

Outputs (in data/labels/):
    sample.csv           one row per sampled decision: id, court, citation, stratum, weight, split
    batches/batch_NN.txt excerpts for labellers (heading, opening, mentions, closing)

Deterministic: the same SEED always gives the same sample.
Run build_sentencing_data.py first.
"""
import csv
import random
import re
import textwrap
from pathlib import Path

import duckdb

SEED = "eval-v1"
ALLOCATION = {"0": 15, "1-2": 75, "3-9": 160, "10-24": 130, "25+": 100}
N_DOUBLE = 40          # decisions labelled twice, to measure how consistent the labels are
BATCH_UNIQUE = 24      # unique decisions per batch file
TEST_SHARE = 0.4

ROOT = Path(__file__).resolve().parents[2]
SIGNALS = (ROOT / "data" / "processed" / "criminal_decisions_signals.parquet").as_posix()
RAW = (ROOT / "data" / "raw" / "a2aj").as_posix()
OUT = ROOT / "data" / "labels"
BATCHES = OUT / "batches"

COURT_NAMES = {
    "SCC": "Supreme Court of Canada (appeal court)",
    "ONCA": "Court of Appeal for Ontario (appeal court)",
    "BCCA": "Court of Appeal for British Columbia (appeal court)",
    "NSCA": "Nova Scotia Court of Appeal (appeal court)",
    "NLCA": "Court of Appeal of Newfoundland and Labrador (appeal court)",
    "BCSC": "Supreme Court of British Columbia (trial court; also hears summary conviction appeals)",
    "NSSC": "Supreme Court of Nova Scotia (trial court; also hears summary conviction appeals)",
    "NSPC": "Provincial Court of Nova Scotia (trial court)",
}


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def excerpt(text: str) -> str:
    idx = text.find("[1]")
    bs = idx if 0 <= idx < 8000 else min(2999, len(text))
    if len(text) <= 3600:
        return "FULL TEXT: " + clean(text)
    heading = clean(text[:bs])[-700:]
    opening = clean(text[bs:bs + 1000])
    closing = clean(text[-900:])
    middle = text[bs + 1000:len(text) - 900]
    hits = [m.start() for m in re.finditer("sentenc", middle, flags=re.I)]
    parts = [f"HEADING (end of the header block): {heading}", f"OPENING: {opening}"]
    if hits:
        k = min(4, len(hits))
        picks = [hits[round(i * (len(hits) - 1) / max(k - 1, 1))] for i in range(k)]
        picks = sorted(set(picks))
        parts.append(f"MENTIONS OF SENTENCE IN THE MIDDLE ({len(picks)} shown of {len(hits)}):")
        for p in picks:
            parts.append("  - ..." + clean(middle[max(p - 100, 0):p + 110]) + "...")
    else:
        parts.append("MENTIONS OF SENTENCE IN THE MIDDLE: none")
    parts.append(f"CLOSING: {closing}")
    return "\n".join(parts)


def main() -> None:
    BATCHES.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    alloc_sql = " ".join(f"WHEN '{k}' THEN {v}" for k, v in ALLOCATION.items())
    rows = con.sql(f"""
        WITH s AS (
            SELECT court, citation, name, n_sentenc, n_chars,
                   CASE WHEN n_sentenc = 0 THEN '0' WHEN n_sentenc <= 2 THEN '1-2'
                        WHEN n_sentenc <= 9 THEN '3-9' WHEN n_sentenc <= 24 THEN '10-24' ELSE '25+' END AS stratum
            FROM '{SIGNALS}'
        ), r AS (
            SELECT *, row_number() OVER (PARTITION BY stratum ORDER BY hash(court || '|' || citation || '{SEED}')) AS rn,
                   count(*) OVER (PARTITION BY stratum) AS stratum_size
            FROM s
        )
        SELECT court, citation, name, n_sentenc, n_chars, stratum, rn, stratum_size
        FROM r WHERE rn <= CASE stratum {alloc_sql} END
        ORDER BY stratum, rn
    """).fetchall()

    items = []
    for i, (court, cit, name, n_sent, n_chars, stratum, rn, size) in enumerate(rows, 1):
        n_h = ALLOCATION[stratum]
        # every 5th and 6th-of-10 style pattern -> 40% test, spread evenly through each stratum
        split = "test" if (rn % 5) in (0, 1) and TEST_SHARE == 0.4 else "dev"
        items.append({"id": f"D{i:03d}", "court": court, "citation": cit, "name": name,
                      "n_sentenc": n_sent, "n_chars": n_chars, "stratum": stratum,
                      "stratum_size": size, "weight": round(size / n_h, 3), "split": split})

    # texts
    con.sql("CREATE TEMP TABLE pick(id VARCHAR, court VARCHAR, citation VARCHAR)")
    con.executemany("INSERT INTO pick VALUES (?,?,?)", [(d["id"], d["court"], d["citation"]) for d in items])
    texts = dict(con.sql(f"""
        SELECT p.id, r.unofficial_text_en FROM pick p
        JOIN read_parquet('{RAW}/*/train.parquet') r ON r.dataset = p.court AND r.citation_en = p.citation
    """).fetchall())
    assert len(texts) == len(items), "some sampled decisions were not found in the raw files"

    rng = random.Random(SEED)
    order = items[:]
    rng.shuffle(order)
    batches = [order[i:i + BATCH_UNIQUE] for i in range(0, len(order), BATCH_UNIQUE)]
    doubles = [d for d in order if d["stratum"] != "0"][:N_DOUBLE]
    for j, d in enumerate(doubles):
        home = next(b for b, batch in enumerate(batches) if d in batch)
        target = (home + 1 + j % (len(batches) - 1)) % len(batches)
        batches[target].append(d)
        d["double_batch"] = target + 1

    for b, batch in enumerate(batches, 1):
        lines = []
        for d in batch:
            d.setdefault("batches", []).append(b)
            lines.append(f"===== ITEM {d['id']} =====")
            lines.append(f"Court: {COURT_NAMES[d['court']]} | Case: {d['name']} | Length: {d['n_chars']:,} characters")
            for para in excerpt(texts[d["id"]]).split("\n"):
                lines.extend(textwrap.wrap(para, width=170, subsequent_indent="    ") or [""])
            lines.append("")
        (BATCHES / f"batch_{b:02d}.txt").write_text("\n".join(lines), encoding="utf-8")

    with (OUT / "sample.csv").open("w", newline="", encoding="utf-8") as f:
        cols = ["id", "court", "citation", "name", "n_sentenc", "n_chars", "stratum", "stratum_size", "weight", "split", "batches"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for d in items:
            w.writerow({**d, "batches": " ".join(str(b) for b in d["batches"])})

    print(f"{len(items)} decisions sampled, {len(doubles)} of them labelled twice, {len(batches)} batch files")
    for s in ALLOCATION:
        sub = [d for d in items if d["stratum"] == s]
        print(f"  stratum {s:6s} sampled {len(sub):4d} of {sub[0]['stratum_size']:6,d}  "
              f"(dev {sum(d['split'] == 'dev' for d in sub)}, test {sum(d['split'] == 'test' for d in sub)})")
    sizes = [(p.name, p.stat().st_size) for p in sorted(BATCHES.glob('batch_*.txt'))]
    print("  batch file sizes (KB):", [round(s / 1024) for _, s in sizes])


if __name__ == "__main__":
    main()
