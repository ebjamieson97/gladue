"""Candidate refined rule sets, designed by studying mistakes on the development set only.

Each function takes the signal table (one row per decision) and returns True/False per row.
Signals are defined in build_features.py.
"""


def exclusions(d):
    # Bail or release pending appeal, unless the closing also rules on a sentence appeal.
    bail = (d.bail_open == 1) & (d.bail_close == 1) & (d.dispo_close == 0)
    # Procedural applications in an appeal (appointing counsel, extending time, directions).
    procedural = (d.proc_open == 1) & (d.trial_court == 0) & ((d.chambers == 1) | (d.n_dispo == 0)) & (d.density < 8)
    # Sentence appeal abandoned, not pursued or not reached, with no ruling on a sentence anywhere.
    not_decided = (((d.not_decided == 1) | (d.newtrial_close == 1)) & (d.n_dispo == 0)
                   & (d.title_trial == 0) & (d.density < 8))
    return bail | procedural | not_decided


def exclusions_refined(d):
    """Second pass, after reading the mistakes of v2c on the development set."""
    bail = (d.bail_open == 1) & (d.bail_close == 1) & (d.dispo_close == 0)
    # Procedural applications in an appeal court: no density condition (short rulings are dense).
    procedural = (d.proc_open == 1) & (d.trial_court == 0) & ((d.chambers == 1) | (d.n_dispo == 0))
    # Abandoned / not pursued / not reached, or a new trial ordered with no sentence ruling:
    # applies only where the sentence gets few mentions.
    not_decided = (((d.not_decided == 1) | (d.abandoned == 1) | ((d.newtrial_close == 1) & (d.n_dispo == 0)))
                   & (d.title_trial == 0) & (d.n_sentenc < 15))
    return bail | procedural | not_decided


def include(d, b_density=0.0, disposition=True, dangerous=True, brief=False):
    title = ((d.title_trial == 1) | (d.title_appeal == 1)) & (d.n_sentenc >= 3)
    closing = (d.n_sentenc >= 10) & (d.n_close >= 1) & (d.density >= b_density)
    statute = (d.n_sentenc >= 10) & (d.statute718 == 1) & (d.density >= 8)
    heavy = (d.n_sentenc >= 25) & (d.density >= 8)
    sel = title | closing | statute | heavy
    if disposition:   # an explicit ruling on a sentence appeal ("the sentence appeal is dismissed")
        sel = sel | ((d.n_dispo >= 1) & (d.n_sentenc >= 2))
    if dangerous:     # dangerous / long-term offender hearings at trial level
        sel = sel | ((d.trial_court == 1) & (d.n_do >= 5) & (d.n_sentenc >= 10))
    if brief:
        sel = sel | ((d.n_sentenc >= 3) & (d.n_open >= 1) & (d.n_close >= 1))
    return sel


METHODS = {
    "Simple: density 8+ or 16+ mentions": lambda d: (d.density >= 8) | (d.n_sentenc >= 16),
    "v2a: v1 core + new exclusions": lambda d: include(d, disposition=False, dangerous=False) & ~exclusions(d),
    "v2b: v2a + disposition rule": lambda d: include(d, dangerous=False) & ~exclusions(d),
    "v2c: v2b + dangerous offender rule": lambda d: include(d) & ~exclusions(d),
    "v2d: v2c, closing rule needs density 2+": lambda d: include(d, b_density=2.0) & ~exclusions(d),
    "v2e: v2d + brief rule": lambda d: include(d, b_density=2.0, brief=True) & ~exclusions(d),
    "v2f: v2c with refined exclusions": lambda d: include(d) & ~exclusions_refined(d),
    "v2g: v2f + brief rule": lambda d: include(d, brief=True) & ~exclusions_refined(d),
}
