"""Compute a wide table of text signals for every criminal decision.

Used only for comparing methods (compare_methods.py). The production rules live in
scripts/build_sentencing_data.py.

Output: data/processed/eval_features.parquet  (one row per criminal decision, no text)
"""
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_sentencing_data as prod  # noqa: E402  (reuse the production patterns)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed" / "eval_features.parquet"

q = prod.q


def count(expr: str, pattern: str) -> str:
    return f"len(regexp_extract_all({expr}, {q(pattern)}, 0, 'i'))"


def has(expr: str, pattern: str) -> str:
    return f"regexp_matches({expr}, {q(pattern)}, 'i')"


# Extra patterns tried in the comparison
VOCAB = (r"denunciat|deterrence|rehabilitat|proportionalit|\bparity\b|\btotality\b|joint submission"
         r"|range of sentence|sentencing range|conditional sentence|probation|surcharge|time served"
         r"|credit for|moral blameworthiness|moral culpability")
AGGMIT = r"aggravating|mitigating"
FIT = r"unfit|fit sentence|fitness of (the )?sentence|fit and (proper|appropriate)|appropriate sentence"
REPORTS = r"pre-?sentence report|presentence report|victim impact statement|gladue report"
OPERATIVE = (r"I sentence|sentence you|I impose|you are sentenced|is sentenced to|will be sentenced to"
             r"|the sentence (I|will|shall)|sentence of (this|the) court|please stand|stand up")
DISPOSITION = (
    r"sentence appeal (is |be |should be |will be )?(dismissed|allowed|granted)"
    r"|appeal (from|against|as to|of) (the |his |her |their )?sentences? (is |be |should be |will be )?(dismissed|allowed)"
    r"|leave to appeal (the |his |her |their |against |from )?(the )?sentences? (is |be |should be )?(granted|refused|denied|dismissed)"
    r"|sentences? (is|are|be|was|were) (varied|reduced|set aside|increased|upheld|affirmed|substituted)"
    r"|(vary|reduce|increase|uphold|affirm|substitute) the sentence"
)
ABANDONED = (r"sentence appeal[^.]{0,80}abandon|abandon[^.]{0,80}sentence appeal"
             r"|appeal (from|against) (the |his |her )?sentence[^.]{0,60}abandon")
# Broader: abandoned, not pursued, or not reached (added for rules v2)
NOT_DECIDED = (
    r"sentence appeal[^.]{0,100}(abandon|not pursu|not proceed|not press)"
    r"|(abandon|not pursu|not proceed)[^.]{0,100}sentence appeal"
    r"|appeal (from|against|as to|of) (the |his |her |their )?sentence[^.]{0,80}(abandon|not pursu|not proceed)"
    r"|abandon(ed|s|ing)? (his|her|the|their) (appeal|application for leave to appeal) (from |against |as to )?(the |his |her )?sentence"
    r"|(unnecessary|not necessary|no need|need not|do not need|not required) to (address|consider|deal with|decide|determine|rule on)[^.]{0,80}sentence"
)
PROCEDURAL = (
    r"appoint(ment|ing)? of counsel|appointed counsel|appoint counsel|(s\.|section) ?684"
    r"|extension of time|exten(d|ding|sion of) the time|extend time"
    r"|to re-?open|application for directions|case management"
)
APPEAL_PHRASE = (r"sentence appeal|appeals? (from|against) (the |his |her |their |that |a |this )?"
                 r"(convictions? and )?sentence|leave to appeal (the |his |her |their |from )?(the )?sentence"
                 r"|appeals? (the |his |her |their )(convictions? and )?sentence")
CONV_APPEAL = r"conviction appeal|appeals? (from|against) (the |his |her |their )?convictions?"
VOIRDIRE = r"voir dire|admissib"
BAIL_ANY = r"bail pending|release pending|judicial interim release|interim release"
GUILTY_PLEA = r"guilty plea|pleaded guilty|pled guilty|plead guilty|plea of guilty"
DO = r"dangerous offender|long[- ]term offender"
# Signals for the IMPOSES task
APPELLANT = r"appellant"
HEAD_APPEAL = r"appellant|respondent|on appeal|appeal from|summary conviction appeal"
OPEN_APPLICATION = r"application|applies|applicant|ruling|voir dire"
OPEN_GUILTY = r"guilty|convicted"
APPLICATION = r"application|applicant"
CLOSE_ORDERS = r"DNA|surcharge|probation|prohibition|(s\.|section) ?109|concurrent|consecutive|months|years"
# The production script is the single source for the patterns it uses.
DISPOSITION, NOT_DECIDED, PROCEDURAL, DO = prod.DISPOSITION, prod.NOT_DECIDED, prod.PROCEDURAL, prod.DANGEROUS_OFFENDER


def feature_sql(path: Path) -> str:
    src = path.as_posix()
    head = "substr(text, 1, body_start - 1)"
    body_open = f"substr(text, body_start, {prod.OPENING_CHARS})"
    close = f"substr(text, greatest(n_chars - {prod.CLOSING_CHARS} + 1, 1))"
    close500 = "substr(text, greatest(n_chars - 499, 1))"
    close5000 = "substr(text, greatest(n_chars - 4999, 1))"
    return f"""
    WITH src AS (
        SELECT dataset AS court, citation_en AS citation, unofficial_text_en AS text,
               length(unofficial_text_en) AS n_chars,
               CASE WHEN instr(unofficial_text_en, '[1]') BETWEEN 1 AND {prod.HEADING_SEARCH_MAX}
                    THEN instr(unofficial_text_en, '[1]') ELSE {prod.HEADING_DEFAULT} END AS body_start
        FROM read_parquet('{src}')
        WHERE unofficial_text_en IS NOT NULL AND length(unofficial_text_en) >= {prod.MIN_TEXT_CHARS}
          AND regexp_matches(coalesce(name_en, ''), {q(prod.CRIMINAL_NAME)}, 'i')
    )
    SELECT court, citation, n_chars,
        CAST(court IN ('BCSC', 'NSSC', 'NSPC') AS INTEGER)            AS trial_court,
        {count('text', 'sentenc')}                                    AS n_sentenc,
        {count(head, 'sentenc')}                                      AS n_head,
        {count(body_open, 'sentenc')}                                 AS n_open,
        {count(close, 'sentenc')}                                     AS n_close,
        {count(close500, 'sentenc')}                                  AS n_close500,
        CAST({has(head, prod.TITLE_TRIAL)} AS INTEGER)                AS title_trial,
        CAST({has(head, prod.TITLE_APPEAL)} AS INTEGER)               AS title_appeal,
        CAST({has('text', prod.STATUTE)} AS INTEGER)                  AS statute718,
        {count('text', AGGMIT)}                                       AS n_aggmit,
        {count('text', VOCAB)}                                        AS n_vocab,
        {count('text', FIT)}                                          AS n_fit,
        {count('text', REPORTS)}                                      AS n_reports,
        {count(close5000, OPERATIVE)}                                 AS n_operative,
        CAST({has(close, DISPOSITION)} AS INTEGER)                    AS dispo_close,
        {count('text', DISPOSITION)}                                  AS n_dispo,
        CAST({has('text', ABANDONED)} AS INTEGER)                     AS abandoned,
        CAST({has('text', NOT_DECIDED)} AS INTEGER)                   AS not_decided,
        CAST({has("substr(text, body_start, 1500)", PROCEDURAL)} AS INTEGER) AS proc_open,
        CAST({has(head, "chambers")} AS INTEGER)                      AS chambers,
        CAST(court = 'SCC' AS INTEGER)                                AS scc,
        {count('text', APPEAL_PHRASE)}                                AS n_appeal_phrase,
        {count('text', CONV_APPEAL)}                                  AS n_conv_appeal,
        {count('text', VOIRDIRE)}                                     AS n_voirdire,
        {count('text', BAIL_ANY)}                                     AS n_bail,
        CAST({has(f"substr(text, body_start, {prod.BAIL_OPENING_CHARS})", prod.BAIL_OPENING)} AS INTEGER) AS bail_open,
        CAST({has(close, prod.BAIL_CLOSING)} AS INTEGER)              AS bail_close,
        CAST({has("substr(text, greatest(n_chars - 1499, 1))", "new trial")} AS INTEGER) AS newtrial_close,
        {count('text', GUILTY_PLEA)}                                  AS n_guilty_plea,
        {count('text', DO)}                                           AS n_do,
        -- signals for telling "imposes a sentence" from "reviews a sentence"
        {count('text', APPELLANT)}                                    AS n_appellant,
        CAST({has(head, HEAD_APPEAL)} AS INTEGER)                     AS head_appeal,
        CAST({has(body_open, 'appeal')} AS INTEGER)                   AS open_appeal,
        CAST({has(body_open, OPEN_APPLICATION)} AS INTEGER)           AS open_application,
        CAST({has(body_open, OPEN_GUILTY)} AS INTEGER)                AS open_guilty,
        {count('text', 'appeal')}                                     AS n_appeal,
        {count('text', APPLICATION)}                                  AS n_application,
        {count(close, CLOSE_ORDERS)}                                  AS n_close_orders,
        CASE WHEN regexp_matches(substr(text, body_start), 'sentenc', 'i')
             THEN (body_start + length(regexp_extract(substr(text, body_start), '^(.*?)sentenc', 1, 'is'))) * 1.0 / n_chars
             ELSE 1.0 END                                             AS first_pos
    FROM src
    """


def main() -> None:
    con = duckdb.connect()
    con.sql("SET memory_limit = '3GB'")
    con.sql("SET threads = 4")
    parts = []
    tmp = ROOT / "data" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for court in prod.COURTS:
        print(f"  {court} ...", flush=True)
        part = tmp / f"evalfeat_{court}.parquet"
        con.sql(f"COPY ({feature_sql(prod.RAW / court / 'train.parquet')}) TO '{part.as_posix()}' (FORMAT parquet)")
        parts.append(part)
    files = "[" + ", ".join(f"'{p.as_posix()}'" for p in parts) + "]"
    con.sql(f"COPY (SELECT * FROM read_parquet({files}) ORDER BY court, citation) TO '{OUT.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    n = con.sql(f"SELECT count(*) FROM '{OUT.as_posix()}'").fetchall()[0][0]
    for p in parts:
        p.unlink()
    print(f"{n:,} criminal decisions -> {OUT}")


if __name__ == "__main__":
    main()
