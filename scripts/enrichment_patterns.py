"""Text patterns shared by the offence models, the Gladue column and the mitigating-factor step.

Used by scripts/build_sentencing_data.py (production) and the scripts in scripts/evaluation/.
All patterns are case-insensitive regular expressions unless noted.
"""
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Gladue reference (a plain rule)
# --------------------------------------------------------------------------
GLADUE = r"gladue|ipeelee|718\.2\s*\(e\)"

# --------------------------------------------------------------------------
# Mitigating factors: which decisions get read (a decision is a candidate if any pattern matches)
# --------------------------------------------------------------------------
MITIGATION_KEYWORDS = (
    GLADUE +
    r"|colonial|coloniz|residential school|sixties scoop|intergenerational"
    r"|anti-black|racism|racist|racial(ly)? (profil|discrim)"
    r"|impact of race and cultur|2021 ONCA 680|2021 NSCA 62"
    r"|islamophob|anti-muslim|white suprem|anti-?semit"
)
MITIGATION_KEYWORDS_CASE_SENSITIVE = r"\bIRCAs?\b"   # Impact of Race and Culture Assessment

MITIGATION_FACTORS = ["gladue_factors", "colonialism", "res_school", "intergen_trauma", "anti_black_racism",
                      "systemic_racism", "islamophobia", "white_supremacy", "other_prejudice"]

# --------------------------------------------------------------------------
# Offence categories
# --------------------------------------------------------------------------
SEC = r"\b(s\.|ss\.|section|sections) ?"
OFFENCE_PATTERNS = {
    "homicide": r"murder|manslaughter|infanticide|criminal negligence causing death|" + SEC + r"(220|229|231|235|236|239)\b",
    "sexual": (r"sexual assault|sexually assault|sexual interference|sexual exploitation|sexual touching"
               r"|child pornography|luring|voyeurism|incest|indecent assault|gross indecency|\brape\b|sexual intercourse|"
               + SEC + r"(151|152|153|155|162|163\.1|172\.1|271|272|273)\b"),
    "assault": r"assault|" + SEC + r"(266|267|268|269|270)\b",   # sexual assaults are subtracted, see below
    "robbery": r"robbery|robbed|" + SEC + r"(343|344)\b",
    "kidnapping": (r"kidnap|forcible confinement|unlawful(ly)? confine|abduct|hostage|human trafficking"
                   r"|trafficking in persons|" + SEC + r"(279|279\.01|279\.1|280|281|282|283)\b"),
    "break_enter": r"break(ing)? and enter|break,? enter|broke into|home invasion|unlawfully in a dwelling|" + SEC + r"(348|349)\b",
    "theft_fraud": (r"\btheft\b|\bfraud|stolen property|property obtained by crime|proceeds of crime|forgery|forged"
                    r"|identity (theft|fraud)|laundering|embezzl|" + SEC + r"(334|354|355|362|366|368|380|462\.31)\b"),
    "drugs": (r"traffick|controlled drugs and substances|\bCDSA\b|narcotic|cocaine|heroin|fentanyl|methamphetamine"
              r"|marij?uana|marihuana|cannabis|possession for the purpose|grow[- ]op|importing"),
    "weapons": (r"firearm|handgun|\bgun\b|\bweapon|ammunition|"
                + SEC + r"(85|86|87|88|90|91|92|94|95|96|99|100|117\.01|244|244\.2)\b"),
    "driving": (r"impaired|over 80|blood alcohol|dangerous driving|dangerous operation|driving while (prohibited|disqualified)"
                r"|fail(ing|ure)? to (stop|remain)|breathalyzer|breath sample|motor vehicle|"
                + SEC + r"(249|252|253|254|255|259|320\.1[3-8])\b"),
    "other": (r"breach|fail(ing|ure)? to comply|utter\w* (a )?threat|criminal harassment|mischief|arson|obstruct"
              r"|perjury|contempt|extortion|conspiracy|procur|prostitution|cruelty|fisheries|income tax|excise"
              r"|customs act|securities|" + SEC + r"(145|733\.1|264|264\.1|430|433|434|139|131|346)\b"),
}
OFFENCE_CATEGORIES = list(OFFENCE_PATTERNS)
SEXUAL_ASSAULT = r"sexual assault|sexually assault|indecent assault"
# Ancillary orders that mention weapons or driving in almost every sentence
WEAPON_ORDER = r"(weapons?|firearms?) prohibition|prohibit\w* from possessing|" + SEC + r"(109|110)\b"
DRIVING_ORDER = r"driving prohibition|prohibit\w* from (driving|operating)"

# Words that introduce the offences being sentenced; the text right after them is the "charge context".
CHARGE_CONTEXT = (r"(convict|guilty|contrary to|charged with|counts? [0-9]|count of|counts of|indictment"
                  r"|sentenc\w+ (for|on))[^\[]{0,250}")
OPENING_CHARS = 2500
CLOSING_CHARS = 2000


def _q(pattern: str) -> str:
    return "'" + pattern.replace("'", "''") + "'"


def offence_feature_sql(source: str) -> str:
    """SQL giving raw offence counts per decision. `source` must provide court, citation, text, n_chars."""
    def count(expr, pattern):
        return f"len(regexp_extract_all({expr}, {_q(pattern)}, 0, 'i'))"
    cols = []
    for cat, pat in OFFENCE_PATTERNS.items():
        for zone in ("text", "charge", "opening", "closing"):
            expr = count(zone, pat)
            if cat == "assault":
                expr = f"greatest({expr} - {count(zone, SEXUAL_ASSAULT)}, 0)"
            cols.append(f"{expr} AS n_{cat}_{'all' if zone == 'text' else zone}")
    cols.append(f"{count('text', WEAPON_ORDER)} AS n_weapon_order")
    cols.append(f"{count('text', DRIVING_ORDER)} AS n_driving_order")
    return f"""
    WITH z AS (
        SELECT court, citation, text, n_chars,
               array_to_string(regexp_extract_all(text, {_q(CHARGE_CONTEXT)}, 0, 'i'), ' | ') AS charge,
               substr(text, 1, CASE WHEN instr(text, '[1]') BETWEEN 1 AND 8000 THEN instr(text, '[1]') ELSE 3000 END + {OPENING_CHARS}) AS opening,
               substr(text, greatest(n_chars - {CLOSING_CHARS} + 1, 1)) AS closing
        FROM {source}
    )
    SELECT court, citation, n_chars, CAST(court IN ('BCSC', 'NSSC', 'NSPC') AS INTEGER) AS trial_court,
           {", ".join(cols)}
    FROM z
    """


OFFENCE_FEATURE_NAMES = ([f"log_n_{c}_{z}" for c in OFFENCE_CATEGORIES for z in ("all", "charge", "opening", "closing")]
                         + [f"share_{c}" for c in OFFENCE_CATEGORIES]
                         + ["log_n_weapon_order", "log_n_driving_order", "log_chars", "trial_court"])


def offence_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Model inputs from the raw counts, in OFFENCE_FEATURE_NAMES order."""
    X = pd.DataFrame(index=df.index)
    for c in OFFENCE_CATEGORIES:
        for z in ("all", "charge", "opening", "closing"):
            X[f"log_n_{c}_{z}"] = np.log1p(df[f"n_{c}_{z}"].astype(float))
    total = sum(df[f"n_{c}_charge"].astype(float) for c in OFFENCE_CATEGORIES) + 1.0
    for c in OFFENCE_CATEGORIES:
        X[f"share_{c}"] = df[f"n_{c}_charge"].astype(float) / total      # share of charge-context mentions
    X["log_n_weapon_order"] = np.log1p(df["n_weapon_order"].astype(float))
    X["log_n_driving_order"] = np.log1p(df["n_driving_order"].astype(float))
    X["log_chars"] = np.log(df["n_chars"].astype(float))
    X["trial_court"] = df["trial_court"].astype(float)
    return X[OFFENCE_FEATURE_NAMES]
