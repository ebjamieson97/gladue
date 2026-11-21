"""The appeal decisions on the site, prepared for a reader who says what the appeal court did with the systemic factors.

Output  scripts/site/work/appeal_sample.csv and scripts/site/work/batches/appeal_NN.txt
"""
import csv
import re
import sys
import textwrap
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent / "work"
sys.path.insert(0, str(ROOT / "scripts" / "extracts"))
from make_extract_batches import paragraphs  # noqa: E402

FULL_LIMIT = 25000
PER_FILE = 5


def main():
    rows = duckdb.sql(f"""
        SELECT i.court, i.citation, i.name, i.sentence_outcome, i.prison_time, e.rationale_paragraphs, d.text
        FROM read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}') i
        JOIN read_csv_auto('{(ROOT / "case_extracts" / "extracts.csv").as_posix()}', all_varchar=true) e USING (court, citation)
        JOIN read_parquet('{(ROOT / "sentencing_data").as_posix()}/*/*/decisions.parquet') d USING (court, citation)
        WHERE i.extract_conclusion_clear = 'Y' AND i.extract_crime_png IS NOT NULL AND i.sentence_outcome <> 'imposed'
        ORDER BY i.court, i.citation
    """).fetchall()
    # --new --tag TAG (updates): only appeals not yet classified -> appeal_sample_TAG.csv, batches_TAG/ (answers: raw_TAG/)
    sample_name, bdir, idp = "appeal_sample.csv", "batches", "A"
    if "--new" in sys.argv:
        tag = sys.argv[sys.argv.index("--tag") + 1]
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from build_site import appeal_categories
        done = set(appeal_categories())
        rows = [r for r in rows if (r[0], r[1]) not in done]
        sample_name, bdir, idp = f"appeal_sample_{tag}.csv", f"batches_{tag}", f"{tag}_A"
    elif "--all" not in sys.argv:
        sys.exit("Use --new --tag TAG for an update, or --all to rebuild the original classification set.")
    if not rows:
        print("Nothing new to do.")
        return
    (WORK / bdir).mkdir(parents=True, exist_ok=True)
    with (WORK / sample_name).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "court", "citation", "name", "batch"])
        for b in range(0, len(rows), PER_FILE):
            lines = []
            for k, (court, cit, name, outcome, prison, rparas, text) in enumerate(rows[b:b + PER_FILE], b + 1):
                cid = f"{idp}{k:03d}"
                w.writerow([cid, court, cit, name, b // PER_FILE + 1])
                paras = paragraphs(text)
                lines += [f"===== CASE {cid} =====", f"Citation: {cit} | Case: {name} | Sentence after this decision: {prison}"]
                if len(text) <= FULL_LIMIT or not paras:
                    body = [re.sub(r"\s+", " ", text).strip()]
                else:
                    keep = sorted(set(list(paras)[:6] + list(paras)[-6:] +
                                      [int(n) for n in re.findall(r"\d+", rparas or "")]))
                    body, prev = [], None
                    for n in keep:
                        if n in paras:
                            if prev is not None and n != prev + 1:
                                body.append("[...]")
                            body.append(f"[{n}] {paras[n]}")
                            prev = n
                for para in body:
                    lines.extend(textwrap.wrap(para, width=170, subsequent_indent="    ") or [""])
                lines.append("")
            (WORK / bdir / f"appeal_{b // PER_FILE + 1:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} appeal decisions in {(len(rows) + PER_FILE - 1) // PER_FILE} files")


if __name__ == "__main__":
    main()
