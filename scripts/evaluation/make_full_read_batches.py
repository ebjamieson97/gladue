"""Prepare every selected sentencing decision for the full AI reading.

The readers record, for each decision: the offence categories, the sentence (prison time, other
penalties, any placement in a healing lodge or treatment facility), and the mitigating factors.

Decisions up to FULL_TEXT_LIMIT characters are given in full. Longer ones are given as the opening,
the closing and the passages in between that mention the sentence, mitigating factors, the
systemic-factor keywords or the charges.

Outputs in data/labels/:
    full_read_sample.csv           id, court, citation and the file each decision is in
    full_read_batches/             read_0001.txt onward (about 110,000 characters each)
    full_read_audit_batches/       a random subset for a second model
Deterministic for the given seed. Run build_sentencing_data.py first.

    .venv\\Scripts\\python.exe -X utf8 scripts\\evaluation\\make_full_read_batches.py
"""
import csv
import random
import re
import sys
import textwrap
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from enrichment_patterns import MITIGATION_KEYWORDS, MITIGATION_KEYWORDS_CASE_SENSITIVE  # noqa: E402
from make_sample import COURT_NAMES, clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = (ROOT / "sentencing_data").as_posix()
LAB = ROOT / "data" / "labels"

SEED = "full-read-v1"
FULL_TEXT_LIMIT = 18000        # decisions up to this many characters are shown in full
OPENING, CLOSING = 3500, 6000
FILE_CHARS = 105000            # start a new file once it holds this many characters
FILE_MAX_ITEMS = 12
AUDIT_N = 150
AUDIT_PER_FILE = 10

FLAGS = re.I
# (name, pattern, characters before, characters after, cap in characters, how to thin if over the cap)
MIDDLE_PASSAGES = [
    ("placement", re.compile(r"healing (lodge|centre|center)|treatment (centre|center|facility)|residential (treatment|program)"
                             r"|recovery (centre|center|house|home)|(psychiatric|forensic) (hospital|facility)", FLAGS),
     250, 450, 1500, "first"),
    ("sentence", re.compile(r"\bI (hereby |therefore |now )?(sentence|impose)|sentenced? (him|her|you|them|mr\.|ms\.|the (accused|offender)) to"
                            r"|(sentence|term|period) of (imprisonment|incarceration)|parole (in)?eligib|credit(ed)? for"
                            r"|global sentence|total sentence|conditional sentence order|long-?term supervision", FLAGS),
     200, 450, 1500, "last"),
    ("mitigating", re.compile(r"mitigat", FLAGS), 200, 500, 2200, "spread"),
    ("systemic", re.compile(MITIGATION_KEYWORDS, FLAGS), 350, 450, 2500, "spread"),
    ("systemic_cs", re.compile(MITIGATION_KEYWORDS_CASE_SENSITIVE), 350, 450, 800, "spread"),
    ("charges", re.compile(r"convict|guilty|contrary to|charged with|counts?\b|indictment", FLAGS), 80, 260, 1000, "first"),
]


def body_start(text: str) -> int:
    idx = text.find("[1]")
    return idx if 0 <= idx < 8000 else min(2999, len(text))


def merge(spans):
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def pick(text, pattern, before, after, cap, how):
    """Spans around each match, thinned to about `cap` characters."""
    spans = merge([max(m.start() - before, 0), min(m.start() + after, len(text))] for m in pattern.finditer(text))
    total = sum(b - a for a, b in spans)
    if total <= cap or len(spans) <= 1:
        return spans
    keep = max(1, int(len(spans) * cap / total))
    if how == "first":
        return spans[:keep]
    if how == "last":
        return spans[-keep:]
    idx = sorted({round(i * (len(spans) - 1) / max(keep - 1, 1)) for i in range(keep)})
    return [spans[i] for i in idx]


def read_excerpt(text: str):
    """Returns (how the decision is shown, the text given to the reader)."""
    if len(text) <= FULL_TEXT_LIMIT:
        return "full", "FULL TEXT: " + clean(text)
    bs = body_start(text)
    parts = [f"HEADING (end of the header block): {clean(text[:bs])[-500:]}",
             f"OPENING: {clean(text[bs:bs + OPENING])}"]
    mid_a, mid_b = bs + OPENING, len(text) - CLOSING
    middle = text[mid_a:mid_b] if mid_b > mid_a else ""
    spans = []
    for _name, pattern, before, after, cap, how in MIDDLE_PASSAGES:
        spans += pick(middle, pattern, before, after, cap, how)
    spans = merge(spans)
    if spans:
        parts.append("PASSAGES FROM THE MIDDLE OF THE DECISION (in order; text between them is left out):")
        parts += ["  - ..." + clean(middle[a:b]) + "..." for a, b in spans]
    parts.append(f"CLOSING: {clean(text[-CLOSING:])}")
    return "excerpts", "\n".join(parts)


def item_lines(d):
    kind, body = read_excerpt(d["text"])
    shown = "the full text" if kind == "full" else "excerpts only"
    lines = [f"===== ITEM {d['id']} =====",
             f"Court: {COURT_NAMES[d['court']]} | Case: {d['name']} | Date: {d['decision_date']} | "
             f"Length: {d['n_chars']:,} characters | Shown: {shown}"]
    for para in body.split("\n"):
        lines.extend(textwrap.wrap(para, width=170, subsequent_indent="    ") or [""])
    lines.append("")
    return kind, lines


def write_files(folder, prefix, items, digits, per_file=None):
    """Pack items into files. Returns {id: (file number, how shown)}."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{prefix}_*.txt"):
        old.unlink()
    where, buf, size, count, number = {}, [], 0, 0, 1

    def flush():
        nonlocal buf, size, count, number
        if buf:
            (folder / f"{prefix}_{number:0{digits}d}.txt").write_text("\n".join(buf), encoding="utf-8")
            number += 1
        buf, size, count = [], 0, 0

    for d in items:
        kind, lines = item_lines(d)
        where[d["id"]] = (number, kind)
        buf += lines
        size += sum(len(x) + 1 for x in lines)
        count += 1
        if (per_file and count >= per_file) or (not per_file and (size >= FILE_CHARS or count >= FILE_MAX_ITEMS)):
            flush()
    flush()
    return where, number - 1


def main():
    con = duckdb.connect()
    cols = ["court", "citation", "name", "decision_date", "n_chars", "text"]
    rows = con.sql(f"""
        SELECT court, citation, name, CAST(decision_date AS VARCHAR), n_chars, text
        FROM read_parquet('{DATA}/*/*/decisions.parquet')
        ORDER BY hash(court || '|' || citation || '{SEED}')
    """).fetchall()
    # Updates: --new --tag TAG prepares only decisions that have no reading yet (not in decision_labels.csv),
    # written separately (full_read_sample_TAG.csv, full_read_batches_TAG/, answers go to full_read_raw_TAG/).
    # Without --new it rebuilds the original full set, which would renumber everything: use --all to confirm.
    new = "--new" in sys.argv
    if not new and "--all" not in sys.argv:
        sys.exit("Use --new --tag TAG for an update (only unread decisions), or --all to rebuild the original set.")
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else None
    if new:
        if not tag:
            sys.exit("--new needs --tag TAG (for example --tag upd2027a)")
        done = set()
        path = LAB / "decision_labels.csv"
        if path.exists():
            done = {(r["court"], r["citation"]) for r in csv.DictReader(path.open(encoding="utf-8"))}
        rows = [r for r in rows if (r[0], r[1]) not in done]
        items = [dict(zip(cols, r), id=f"{tag}_{i:05d}") for i, r in enumerate(rows, 1)]
        if not items:
            print("No unread decisions: nothing to do.")
            return
        sample_name, batch_dir = f"full_read_sample_{tag}.csv", LAB / f"full_read_batches_{tag}"
    else:
        items = [dict(zip(cols, r), id=f"S{i:05d}") for i, r in enumerate(rows, 1)]
        sample_name, batch_dir = "full_read_sample.csv", LAB / "full_read_batches"

    where, n_files = write_files(batch_dir, "read", items, 4)
    with (LAB / sample_name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "court", "citation", "name", "n_chars", "batch", "shown"])
        for d in items:
            w.writerow([d["id"], d["court"], d["citation"], d["name"], d["n_chars"], *where[d["id"]]])
    full = sum(1 for v in where.values() if v[1] == "full")
    sizes = [p.stat().st_size / 1024 for p in batch_dir.glob("read_*.txt")]
    print(f"{len(items):,} decisions in {n_files} files; {full:,} shown in full, {len(items) - full:,} as excerpts")
    print(f"  mean file {sum(sizes) / len(sizes):.0f} KB, largest {max(sizes):.0f} KB, total {sum(sizes) / 1024:.0f} MB")

    if new:
        print(f"  files: {batch_dir.name}/read_0001.txt to read_{n_files:04d}.txt")
        return
    audit = random.Random(SEED).sample(items, AUDIT_N)
    _, n_audit = write_files(LAB / "full_read_audit_batches", "audit", audit, 2, per_file=AUDIT_PER_FILE)
    print(f"  audit subset: {len(audit)} decisions in {n_audit} files")


if __name__ == "__main__":
    main()
