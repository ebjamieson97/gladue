"""Draw the extract pictures: for each decision, one PNG of the crime passage and one of the rationale.

Input   case_extracts/work/sample.csv, case_extracts/work/raw/extract_*.jsonl (the readers' choices)
Output  case_extracts/<court>/<citation>_crime.png and _rationale.png, and case_extracts/extracts.csv

Highlights (yellow):
  crime      the phrases the reader picked (the most serious facts)
  rationale  every match of RATIONALE_TERMS below, plus the phrases the reader picked
Every picked phrase is checked against the paragraph text; one that is not found is skipped and counted.

    .venv\\Scripts\\python.exe -X utf8 scripts\\extracts\\render_extracts.py
"""
import csv
import json
import re
import sys
from pathlib import Path

import duckdb
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_extract_batches import paragraphs  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "case_extracts"
WORK = OUT / "work"
FONTS = Path("C:/Windows/Fonts")

# Highlighted automatically in the rationale: only the named systemic factors and the Gladue / Anderson / Morris
# references. Everything else (the court's framing, the link to the offender, the conclusion) is highlighted as
# whole clauses chosen by the reader, so the picture shows phrases rather than scattered single words.
RATIONALE_TERMS = re.compile(
    r"(?<!\w)(?:Gladue(?:\s(?:factors|principles|report|analysis))?|(?:s\.\s?|section\s)?718\.2\s?\(e\)"
    r"|colonial\w*|coloniz\w*|colonis\w*|decoloni\w*|(?:Indian\s)?residential schools?|Sixties Scoop|60s Scoop"
    r"|intergenerational trauma|systemic racism|systemic discrimination"
    r"|anti-Black racism|racial trauma|racial discrimination|racial profiling"
    r"|Impact of Race and Culture Assessments?|IRCAs?|R\.?\s?v\.?\s?Morris|R\.?\s?v\.?\s?Anderson|2021 ONCA 680|2021 NSCA 62"
    r"|Islamophob\w*|anti-Muslim prejudice|white supremac\w*|anti-?semit\w*)(?!\w)", re.I)
HEADING_TAIL = re.compile(r"(?<=[.!?\"”’)])\s+((?:[A-Z][\w’'-]*|of|the|and|on|to|for|in|a)(?:\s+(?:[A-Z][\w’'-]*|of|the|and|on|to|for|in|a)){0,7})\s*$")


def clean_para(t):
    """Drop a section heading that the source text runs onto the end of a paragraph ("... can. Impact on the Community")."""
    t = fix_chars(t)
    m = HEADING_TAIL.search(t)
    return t[:m.start()].rstrip() if m and m.group(1)[0].isupper() else t


# Characters the body font cannot draw would show as empty boxes. Known ones get a plain equivalent;
# any other missing character is decomposed (é -> e + accent) if that helps, otherwise dropped.
CHAR_FIXES = {
    "‑": "-", "‐": "-", "‒": "-", "−": "-",           # non-breaking hyphen, other hyphens, minus
    "⸺": "——", "⸻": "———",              # two- and three-em dashes
    "■": "•", "▪": "•", "●": "•",            # squares and circles used as bullets
    "\u0082": "‚", "\u0091": "‘", "\u0092": "’",            # Windows-1252 characters decoded wrongly
    "\u0093": "“", "\u0094": "”", "\u0096": "–", "\u0097": "—", "\u0085": "…",
    "​": "", "‌": "", "‍": "", "⁠": "", "﻿": "", "­": "",   # invisible marks
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",   # odd spaces
}
_GLYPHS = None


def fix_chars(s):
    global _GLYPHS
    if _GLYPHS is None:
        from fontTools.ttLib import TTFont
        _GLYPHS = set()
        for name in ("georgia.ttf", "georgiab.ttf"):
            _GLYPHS |= set(TTFont(str(FONTS / name)).getBestCmap())
    out = []
    for ch in s:
        ch = CHAR_FIXES.get(ch, ch)
        if all(ord(c) in _GLYPHS or c in " \n" for c in ch):
            out.append(ch)
            continue
        import unicodedata
        dec = "".join(c for c in unicodedata.normalize("NFKD", ch) if ord(c) in _GLYPHS)
        out.append(dec)
    return "".join(out)

W, MARGIN, GAP = 1400, 60, 10
W_PHONE = 720            # phone version: same text size, narrower, so it stays readable on a small screen
YELLOW = (255, 235, 59)
INK, MUTED, RULE = (30, 30, 30), (110, 110, 110), (210, 210, 210)


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


BODY, BODY_B = font("georgia.ttf", 26), font("georgiab.ttf", 26)
TITLE, SMALL, LABEL = font("georgiab.ttf", 34), font("arial.ttf", 21), font("arialbd.ttf", 22)


def spans_for(text, phrases, terms):
    """Character spans to highlight; returns (spans, number of picked phrases not found)."""
    spans, missing = [], 0
    norm = text.replace("’", "'").replace("“", '"').replace("”", '"')
    for ph in phrases:
        p = fix_chars(ph.strip()).replace("’", "'").replace("“", '"').replace("”", '"')
        i = norm.find(p) if p else -1
        if i < 0:
            m = re.search(re.escape(p).replace(r"\ ", r"\s+"), norm, re.I) if p else None
            i, p = (m.start(), m.group(0)) if m else (-1, p)
        if i < 0:
            missing += 1
            continue
        spans.append((i, i + len(p)))
    if terms is not None:
        spans += [(m.start(), m.end()) for m in terms.finditer(text)]
    return spans, missing


def layout(text, spans, max_w, draw):
    """Word-wrap; each word carries whether it is highlighted. Returns lines of (word, highlighted)."""
    flags = bytearray(len(text))
    for a, b in spans:
        flags[a:b] = b"\x01" * (b - a)
    words = [(m.group(0), any(flags[m.start():m.end()])) for m in re.finditer(r"\S+", text)]
    lines, line, width = [], [], 0
    space = draw.textlength(" ", font=BODY)
    for w, hl in words:
        wl = draw.textlength(w, font=BODY)
        if line and width + space + wl > max_w:
            lines.append(line)
            line, width = [], 0
        line.append((w, hl, wl))
        width += (space if len(line) > 1 else 0) + wl
    if line:
        lines.append(line)
    return lines


def render(path, header, label, para_range, blocks, W=W):
    """blocks: list of (paragraph number, text, spans)."""
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    max_w = W - 2 * MARGIN
    laid = [(n, layout(f"[{n}] {t}", [(a + len(f'[{n}] '), b + len(f'[{n}] ')) for a, b in s], max_w, probe))
            for n, t, s in blocks]
    line_h = 40
    gaps = sum(1 for (a, _), (b, _) in zip(laid, laid[1:]) if b != a + 1)

    def wrap(text, font):        # header and footer lines wrap on narrow (phone) pictures
        words, out, cur = text.split(" "), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if cur and probe.textlength(t, font=font) > max_w:
                out.append(cur)
                cur = w
            else:
                cur = t
        return out + ([cur] if cur else [])
    title, sub = wrap(header[0], TITLE), wrap(header[1], SMALL)
    label_lines = wrap(f"{label.upper()}  ·  {para_label([n for n, _ in laid])}", LABEL)
    source = wrap("Source: published reasons for sentence (A2AJ Canadian case law dataset). "
                  "Highlights added for this project.", SMALL)
    h = (MARGIN + 46 * len(title) + 30 * len(sub) + 22 + 40 * len(label_lines)
         + sum(len(lines) * line_h + 18 for _, lines in laid) + gaps * line_h + 30 * len(source) + 20 + MARGIN)
    img = Image.new("RGB", (W, h), "white")
    d = ImageDraw.Draw(img)
    y = MARGIN
    for t in title:
        d.text((MARGIN, y), t, font=TITLE, fill=INK)
        y += 46
    for t in sub:
        d.text((MARGIN, y), t, font=SMALL, fill=MUTED)
        y += 30
    d.line((MARGIN, y + 8, W - MARGIN, y + 8), fill=RULE, width=2)
    y += 22
    for t in label_lines:
        d.text((MARGIN, y), t, font=LABEL, fill=MUTED)
        y += 40
    space = probe.textlength(" ", font=BODY)
    prev = None
    for n, lines in laid:
        if prev is not None and n != prev + 1:      # paragraphs left out in between
            d.text((MARGIN, y - 14), "[ … ]", font=BODY, fill=MUTED)
            y += line_h
        prev = n
        for line in lines:
            x = MARGIN
            for i, (w, hl, wl) in enumerate(line):
                nxt = line[i + 1][1] if i + 1 < len(line) else False
                if hl:   # extend the highlight across the space when the next word is highlighted too
                    d.rectangle((x - 2, y + 2, x + wl + (space if nxt else 0) + 2, y + line_h - 4), fill=YELLOW)
                d.text((x, y + 4), w, font=BODY, fill=INK)
                x += wl + space
            y += line_h
        y += 18
    y += 2
    for t in source:
        d.text((MARGIN, y), t, font=SMALL, fill=MUTED)
        y += 30
    # A 64-colour palette keeps text edges smooth and makes the file about a quarter of the size.
    img.quantize(colors=64, method=Image.Quantize.MEDIANCUT).save(path, optimize=True)


def para_list(spec, paras):
    """'24-25;31' -> [24, 25, 31]. Runs may be separated by ';' or ','."""
    out = []
    for part in re.split(r"[;,]", str(spec)):
        a, _, b = part.strip().partition("-")
        if a.strip():
            a, b = int(a), int(b or a)
            out += [n for n in range(a, b + 1) if n in paras and n not in out]
    return sorted(out)                 # in the decision's order, even when paragraphs were added later


def para_label(nums):
    """[24, 25, 31] -> 'paragraphs 24-25, 31'."""
    runs = []
    for n in nums:
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    text = ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs)
    return f"paragraph{'s' if len(nums) > 1 else ''} {text}"


# Rounds of picks, in order; a later round replaces an earlier one for the same decision.
#   (sample file, folder of answers, file prefix)
ROUNDS = [("sample.csv", "raw", "extract"),
          ("sample_redo.csv", "raw_redo", "redo")]      # re-picks under the court's-own-words rule


def rounds():
    """The fixed rounds, then any update rounds (sample_TAG.csv with answers in raw_TAG/, files TAG_NNN), by name."""
    extra = sorted(p.stem[len("sample_"):] for p in WORK.glob("sample_*.csv") if p.name != "sample_redo.csv")
    return ROUNDS + [(f"sample_{t}.csv", f"raw_{t}", t) for t in extra]


def load_picks():
    """{(court, citation): the reader's pick}, with later rounds replacing earlier ones."""
    out = {}
    for sample_name, folder, prefix in rounds():
        path = WORK / sample_name
        if not path.exists():
            continue
        sample = {r["id"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}
        for p in sorted((WORK / folder).glob(f"{prefix}_*.jsonl")):
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                if line.strip().startswith("{"):
                    r = json.loads(line)
                    s = sample.get(r.get("id"))
                    if s:
                        out[(s["court"], s["citation"])] = {**r, "round": folder}
    return out


def main():
    # every decision in any round (first appearance wins, so each decision is drawn once)
    sample, seen = {}, set()
    for sample_name, _, _ in rounds():
        path = WORK / sample_name
        if path.exists():
            for r in csv.DictReader(path.open(encoding="utf-8")):
                if (r["court"], r["citation"]) not in seen:
                    seen.add((r["court"], r["citation"]))
                    sample[r["id"]] = r
    by_key = load_picks()
    picks = {cid: by_key.get((s["court"], s["citation"])) for cid, s in sample.items()}
    picks = {k: v for k, v in picks.items() if v}
    # Hand corrections (case_extracts/overrides.json), matched on the phrase without its final punctuation.
    ov_path = OUT / "overrides.json"
    overrides = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    for cid, pk in picks.items():
        o = overrides.get(sample[cid]["citation"])
        for kind in ("crime", "rationale"):
            drop = {x.strip().rstrip(".,;") for x in (o or {}).get(f"remove_{kind}_highlights", [])}
            if drop:
                pk[f"{kind}_highlights"] = [h for h in pk.get(f"{kind}_highlights") or [] if h.strip().rstrip(".,;") not in drop]
        # Added paragraphs and highlights (e.g. so every factor tag is visible in the reasons picture).
        add_p = [str(n) for n in (o or {}).get("add_rationale_paras", [])]
        if add_p:
            pk["rationale_paras"] = ";".join([str(pk.get("rationale_paras") or "")] + add_p).strip(";")
        pk["rationale_highlights"] = (pk.get("rationale_highlights") or []) + list((o or {}).get("add_rationale_highlights", []))
    con = duckdb.connect()
    keys = [(s["court"], s["citation"]) for s in sample.values()]
    con.sql("CREATE TEMP TABLE k(court VARCHAR, citation VARCHAR)")
    con.executemany("INSERT INTO k VALUES (?,?)", keys)
    info = {(r[0], r[1]): r[2:] for r in con.sql(f"""
        SELECT i.court, i.citation, i.name, i.offence_description, i.prison_time, i.sentence_outcome, d.text
        FROM read_csv_auto('{(ROOT / "sentencing_data" / "index.csv").as_posix()}') i
        JOIN read_parquet('{(ROOT / "sentencing_data").as_posix()}/*/*/decisions.parquet') d USING (court, citation)
        JOIN k USING (court, citation)""").fetchall()}
    rows, missing_total, not_read, empty = [], 0, [], []
    for cid, s in sample.items():
        pk = picks.get(cid)
        if not pk:
            not_read.append(cid)
            continue
        name, desc, prison, outcome, text = info[(s["court"], s["citation"])]
        paras = paragraphs(text)
        folder = OUT / s["court"]
        folder.mkdir(parents=True, exist_ok=True)
        stem = s["citation"].replace(" ", "_")
        header = (fix_chars(f"{name}, {s['citation']}"), fix_chars(f"{desc}  ·  Prison: {prison or 'n/a'}"))
        out = {"court": s["court"], "citation": s["citation"],
               "conclusion_clear": str(pk.get("conclusion_clear", "")).upper()[:1], "note": pk.get("note", "")}
        for label, key, hl_key, terms in (("The offence", "crime_paras", "crime_highlights", None),
                                          ("Systemic factors: the court's reasons", "rationale_paras", "rationale_highlights", RATIONALE_TERMS)):
            kind = "crime" if key == "crime_paras" else "rationale"
            try:
                nums = para_list(pk.get(key, ""), paras)
            except ValueError:
                nums = []
            if not nums:                       # nothing usable picked (e.g. a decision without numbered paragraphs)
                empty.append(f"{s['citation']} ({kind})")
                out[f"{kind}_png"], out[f"{kind}_paragraphs"] = "", ""
                continue
            blocks, found = [], set()
            for n in nums:
                t = clean_para(paras[n])
                sp, _ = spans_for(t, pk.get(hl_key) or [], terms)
                blocks.append((n, t, sp))
                found |= {ph for ph in (pk.get(hl_key) or []) if spans_for(t, [ph], None)[1] == 0}
            missing_total += len(set(pk.get(hl_key) or []) - found)
            path = folder / f"{stem}_{kind}.png"
            render(path, header, label, pk[key], blocks)
            render(path.with_name(path.stem + "_m.png"), header, label, pk[key], blocks, W=W_PHONE)   # phone version
            out[f"{kind}_png"] = path.relative_to(ROOT).as_posix()
            out[f"{kind}_paragraphs"] = ", ".join(str(n) for n in nums)
        rows.append(out)
    with (OUT / "extracts.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["court", "citation", "crime_paragraphs", "crime_png",
                                           "rationale_paragraphs", "rationale_png", "conclusion_clear", "note"])
        w.writeheader()
        w.writerows(rows)
    pics = sum(bool(r["crime_png"]) + bool(r["rationale_png"]) for r in rows)
    print(f"{len(sample)} decisions; {len(rows)} picked; {pics} pictures drawn; "
          f"picked phrases not found in the text: {missing_total}")
    print(f"  conclusion_clear: Y {sum(r['conclusion_clear'] == 'Y' for r in rows)}, N {sum(r['conclusion_clear'] == 'N' for r in rows)}")
    if empty:
        print(f"  no usable paragraphs picked ({len(empty)}): {empty}")
    if not_read:
        batches = sorted({int(sample[c]['batch']) for c in not_read})
        print(f"  not picked yet ({len(not_read)} decisions, files {batches})")


if __name__ == "__main__":
    main()
