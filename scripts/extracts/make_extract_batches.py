"""Prepare the systemic-mitigation decisions for the extract pictures.

Each decision is split into its numbered paragraphs ([1], [2], ...) so a reader can point to the
paragraphs that describe the crime and the paragraphs where the court explains the systemic factor.

Output  case_extracts/work/sample.csv and case_extracts/work/batches/extract_NNN.txt
    .venv\\Scripts\\python.exe -X utf8 scripts\\extracts\\make_extract_batches.py [--citations "2018 BCSC 296" ...]
"""
import csv
import re
import sys
import textwrap
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "case_extracts" / "work"
PER_FILE = 3
PARA = re.compile(r"\[(\d{1,4})\]\s")


def paragraphs(text):
    """{number: text} for the numbered paragraphs, in order. Text before [1] is the heading."""
    marks = [m for m in PARA.finditer(text)]
    out, expected = {}, 1
    keep = []
    for m in marks:                      # keep markers that run in sequence, to skip "[2001] 1 S.C.R." etc.
        n = int(m.group(1))
        if n == expected:
            keep.append(m)
            expected += 1
    for i, m in enumerate(keep):
        end = keep[i + 1].start() if i + 1 < len(keep) else len(text)
        out[int(m.group(1))] = re.sub(r"\s+", " ", text[m.end():end]).strip()
    return out


def main():
    # --citations "2018 BCSC 296" ... (stops at the next --option): re-pick just these decisions; needs --tag TAG
    wanted = None
    if "--citations" in sys.argv:
        rest = sys.argv[sys.argv.index("--citations") + 1:]
        wanted = rest[:next((i for i, a in enumerate(rest) if a.startswith("--")), len(rest))]
    con = duckdb.connect()
    rows = con.sql(f"""
        SELECT i.court, i.citation, i.name, CAST(i.decision_date AS VARCHAR), i.offence_description, i.prison_time,
               i.mitigating_quote, d.text
        FROM read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}') i
        JOIN read_parquet('{(ROOT / "sentencing_data").as_posix()}/*/*/decisions.parquet') d USING (court, citation)
        WHERE i.mitigating_any_systemic ORDER BY i.court, i.citation
    """).fetchall()
    # --redo FILE: a second round for the decisions listed in FILE (one "court|citation" per line). It is
    # written separately (sample_redo.csv, batches_redo/redo_NNN.txt) so the first round stays intact.
    redo = sys.argv[sys.argv.index("--redo") + 1] if "--redo" in sys.argv else None
    sample_name, bdir, prefix, idp = ("sample_redo.csv", "batches_redo", "redo", "R") if redo else \
                                     ("sample.csv", "batches", "extract", "X")
    # --new --tag TAG (updates): only systemic-mitigation decisions that have no pick yet, written as round TAG
    # (sample_TAG.csv, batches_TAG/TAG_NNN.txt; the readers' answers go to raw_TAG/).
    if "--new" in sys.argv:
        tag = sys.argv[sys.argv.index("--tag") + 1]
        from render_extracts import load_picks
        have = set(load_picks())
        rows = [r for r in rows if (r[0], r[1]) not in have]
        sample_name, bdir, prefix, idp = f"sample_{tag}.csv", f"batches_{tag}", tag, f"{tag}_"
        if not rows:
            print("No new decisions need extracts.")
            return
    elif wanted:
        if "--tag" not in sys.argv:
            sys.exit("--citations needs --tag TAG (the re-picks are written as their own round, which replaces earlier picks)")
        tag = sys.argv[sys.argv.index("--tag") + 1]
        sample_name, bdir, prefix, idp = f"sample_{tag}.csv", f"batches_{tag}", tag, f"{tag}_"
    elif not redo and "--all" not in sys.argv:
        sys.exit("Use --new --tag TAG for an update, or --all to rebuild the original round (renumbers everything).")
    if redo:
        keys = {tuple(l.strip().split("|")) for l in Path(redo).read_text(encoding="utf-8").splitlines() if l.strip()}
        rows = [r for r in rows if (r[0], r[1]) in keys]
    if wanted:
        rows = [r for r in rows if r[1] in wanted]
    (WORK / bdir).mkdir(parents=True, exist_ok=True)
    for old in (WORK / bdir).glob(f"{prefix}_*.txt"):
        old.unlink()
    with (WORK / sample_name).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "court", "citation", "name", "batch", "n_paragraphs"])
        for b in range(0, len(rows), PER_FILE):
            lines = []
            for k, (court, cit, name, date, desc, prison, quote, text) in enumerate(rows[b:b + PER_FILE], b + 1):
                cid = f"{idp}{k:04d}"
                paras = paragraphs(text)
                w.writerow([cid, court, cit, name, b // PER_FILE + 1, len(paras)])
                lines += [f"===== CASE {cid} =====",
                          f"Citation: {cit} | Case: {name} | Date: {date} | Offences: {desc} | Prison: {prison}",
                          f"Passage the earlier reader gave for the systemic factor: {quote or '(none)'}", ""]
                for n, p in paras.items():
                    lines.extend(textwrap.wrap(f"[{n}] {p}", width=170, subsequent_indent="    "))
                lines.append("")
            (WORK / bdir / f"{prefix}_{b // PER_FILE + 1:03d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} decisions in {(len(rows) + PER_FILE - 1) // PER_FILE} files")


if __name__ == "__main__":
    main()
