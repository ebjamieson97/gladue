"""For appeals that upheld a sentence (upheld_considered, crown_appeal_dismissed): the paragraphs shown in their
two pictures, so a reader can check that the crime is described and at least one specific systemic factor is.

Output  scripts/site/work/check_sample.csv and scripts/site/work/check_batches/check_NN.txt
"""
import csv
import json
import re
import sys
import textwrap
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent / "work"
sys.path.insert(0, str(ROOT / "scripts" / "extracts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_site import appeal_categories  # noqa: E402
from make_extract_batches import paragraphs  # noqa: E402

CATEGORIES = {"upheld_considered", "crown_appeal_dismissed"}
PER_FILE = 12


def main():
    cats = appeal_categories()
    keys = [k for k, a in cats.items() if a.get("category") in CATEGORIES]
    # --new --tag TAG (updates): only those not yet checked -> check_sample_TAG.csv, check_batches_TAG/ (answers: check_raw_TAG/)
    sample_name, bdir, idp = "check_sample.csv", "check_batches", "C"
    if "--new" in sys.argv:
        tag = sys.argv[sys.argv.index("--tag") + 1]
        from build_site import content_checks
        done = set(content_checks())
        keys = [k for k in keys if k not in done]
        sample_name, bdir, idp = f"check_sample_{tag}.csv", f"check_batches_{tag}", f"{tag}_C"
    if not keys:
        print("Nothing new to do.")
        return
    con = duckdb.connect()
    con.sql("CREATE TEMP TABLE k(court VARCHAR, citation VARCHAR)")
    con.executemany("INSERT INTO k VALUES (?,?)", keys)
    rows = con.sql(f"""
        SELECT e.court, e.citation, i.name, e.crime_paragraphs, e.rationale_paragraphs, d.text
        FROM read_csv_auto('{(ROOT / "case_extracts" / "extracts.csv").as_posix()}', all_varchar=true) e
        JOIN k USING (court, citation)
        JOIN read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}') i USING (court, citation)
        JOIN read_parquet('{(ROOT / "sentencing_data").as_posix()}/*/*/decisions.parquet') d USING (court, citation)
        ORDER BY e.court, e.citation
    """).fetchall()
    (WORK / bdir).mkdir(parents=True, exist_ok=True)
    with (WORK / sample_name).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "court", "citation", "name", "category", "batch"])
        for b in range(0, len(rows), PER_FILE):
            lines = []
            for k, (court, cit, name, crime, rat, text) in enumerate(rows[b:b + PER_FILE], b + 1):
                cid = f"{idp}{k:03d}"
                w.writerow([cid, court, cit, name, cats[(court, cit)]["category"], b // PER_FILE + 1])
                paras = paragraphs(text)
                lines.append(f"===== CASE {cid} ===== {cit} | {name}")
                for label, spec in (("CRIME PICTURE", crime), ("SYSTEMIC FACTORS PICTURE", rat)):
                    lines.append(f"--- {label} ---")
                    for n in [int(x) for x in re.findall(r"\d+", spec or "")]:
                        if n in paras:
                            lines.extend(textwrap.wrap(f"[{n}] {paras[n]}", width=170, subsequent_indent="    "))
                lines.append("")
            (WORK / bdir / f"check_{b // PER_FILE + 1:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} decisions in {(len(rows) + PER_FILE - 1) // PER_FILE} files")


if __name__ == "__main__":
    main()
