"""Print a random sample of decisions from each tier so a person can check the rules.

For each sampled decision it shows the citation, the count of "sentenc..." words,
the length, the first lines of the body and the last lines of the text.

    .venv\\Scripts\\python.exe -X utf8 scripts\\sample_for_review.py --seed 1 --n 10

Run build_sentencing_data.py first. The same seed always gives the same sample.
"""
import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SIGNALS = (ROOT / "data" / "processed" / "criminal_decisions_signals.parquet").as_posix()
RAW = (ROOT / "data" / "raw" / "a2aj").as_posix()

GROUPS = {
    "selected (logistic regression)": "is_sentencing",
    "near miss (probability 0.3 to 0.5)": "sentencing_probability BETWEEN 0.3 AND 0.5",
    "not selected, 3+ mentions": "NOT is_sentencing AND n_sentenc >= 3",
}

ap = argparse.ArgumentParser()
ap.add_argument("--seed", default="1")
ap.add_argument("--n", type=int, default=10)
args = ap.parse_args()

con = duckdb.connect()
for label, cond in GROUPS.items():
    total = con.sql(f"SELECT count(*) FROM '{SIGNALS}' WHERE {cond}").fetchall()[0][0]
    print(f"\n=== {label}  ({total:,} decisions)")
    rows = con.sql(f"""
        WITH pick AS (
            SELECT court, citation, n_sentenc, n_chars, matched_rules, sentencing_probability
            FROM '{SIGNALS}' WHERE {cond}
            ORDER BY hash(citation || '{args.seed}') LIMIT {args.n}
        )
        SELECT p.citation, p.sentencing_probability, p.n_sentenc, p.n_chars,
               regexp_replace(substr(r.unofficial_text_en,
                   CASE WHEN instr(r.unofficial_text_en, '[1]') BETWEEN 1 AND 8000
                        THEN instr(r.unofficial_text_en, '[1]') ELSE 3000 END, 280), '\\s+', ' ', 'g'),
               regexp_replace(right(r.unofficial_text_en, 230), '\\s+', ' ', 'g')
        FROM pick p
        JOIN read_parquet('{RAW}/*/train.parquet') r
          ON r.dataset = p.court AND r.citation_en = p.citation
        ORDER BY p.citation
    """).fetchall()
    for cit, prob, n, chars, intro, outro in rows:
        print(f"* {cit} [probability {prob:.2f}; {n} mentions; {chars:,} chars]\n    START: {intro}\n    END:   {outro}")
