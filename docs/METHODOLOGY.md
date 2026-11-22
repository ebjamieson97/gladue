# Identifying sentencing decisions: methodology and evaluation

This project selects criminal **sentencing decisions** from published Canadian court decisions. This
document explains:

- the data used
- how decisions are selected: a logistic regression model, with published weights
- the written rules (Rules v2.0) that were used before, and are kept for comparison
- how the decisions where a court **imposes** a sentence are picked out
- how each decision's **offence categories** are identified
- how **Gladue references** and **mitigating factors** tied to prejudice are identified
- how every decision was **read by AI readers** to record its offences, its sentence (prison time,
  other penalties, any placement in a healing lodge or treatment facility) and its mitigating factors
- how accuracy was measured, on two samples of 3,200 labelled decisions, and how every method compares

**To update the data and website with new decisions, follow [PIPELINE.md](PIPELINE.md).**

Selection is done by [scripts/build_sentencing_data.py](../scripts/build_sentencing_data.py). It runs
without any AI, so anyone with the same script, model file and data gets the same result. The columns
that come from the AI reading (section 10) cannot be reproduced by a script; they are saved in a file
that the build script reads.

## Summary

| Task | Method | Precision | Recall |
|---|---|---|---|
| Find sentencing decisions | Starting idea: cites s. 718, or 10+ mentions of "sentence" | 86.5% | 78.7% |
| Find sentencing decisions | Rules v2.0 (written rules) | 90.8% | 92.6% |
| Find sentencing decisions | **Logistic regression (adopted)** | **95.5%** | **94.7%** |
| Find IMPOSES among them | **Rule: trial court, and the heading shows no appeal (adopted)** | **98.2%** | **100.0%** |
| Find IMPOSES among them | Logistic regression | 99.1% | 99.7% |
| Offence categories | Logistic regression, one per category (now a fallback only) | 89.1% | 80.9% |

The sentencing and IMPOSES figures are from the purely random sample of 3,200 decisions. The stratum
random sample gives nearly the same figures (section 7). The offence figure is over all 11 categories,
from 5,000 labelled sentencing decisions (section 8).

**Offences, the sentence and mitigating factors now come from an AI reading of every one of the 10,096
selected decisions** (section 10). There is no separate answer key to score that reading against, so
it is checked in other ways instead:

| Check | Result |
|---|---|
| A second model (Claude Opus 5.5) re-read 150 decisions: every offence category the same | 145/150 |
| The same: sentence outcome (imposed, upheld, reduced, increased) the same | 146/150 |
| The same: prison time the same | 140/150 |
| The same: "any systemic factor mitigating" the same | 147/150 |
| Quotations of the sentence found word for word in the decision, by script | 9,792/9,813 (99.8%) |
| Offence categories the same as the earlier, separate labelling of 4,709 of the same decisions | 4,476/4,709 (95.1%) |

- **Precision** is the share of selected decisions that really are what the method says they are.
- **Recall** is the share of all such decisions that the method found.

## 1. Data

| Item | Detail |
|---|---|
| Source | A2AJ Canadian case law dataset (`a2aj/canadian-case-law` on Hugging Face), from the Access to Algorithmic Justice project at York University |
| Version used | Revision `4e85f2882e506177ee08e1286292a52af3b0fe6b`, updated 15 November 2026 |
| Courts | Supreme Court of Canada; Courts of Appeal of Ontario, British Columbia, Nova Scotia, and Newfoundland and Labrador; Supreme Courts of British Columbia and Nova Scotia; Provincial Court of Nova Scotia |
| Criminal decisions | 32,187 (the case name is the Crown against a person, and there is English text of 200+ characters) |
| Sentencing decisions selected | 10,096 by logistic regression. For comparison, Rules v2.0 would select 10,503; 9,655 are selected by both |
| Of those, IMPOSES | 3,576 |
| Of those, referencing Gladue | 1,486 |
| Of those, with a prejudice-related mitigating factor | 579 |

## 2. What counts as a sentencing decision

A decision is a sentencing decision if a court **imposes a sentence or reviews one on the merits**. Each
labelled decision received one of four labels:

| Label | Meaning | Counted as sentencing? |
|---|---|---|
| IMPOSES | A court imposes a sentence and gives reasons. Includes youth sentences and dangerous offender decisions | Yes |
| REVIEWS | An appeal court rules on a challenge to a sentence, even briefly | Yes |
| RELATED | About sentencing but not setting or reviewing a sentence. Examples: a ruling on evidence at a sentencing hearing, a sex offender registry order alone, an extension of time to appeal a sentence | No |
| NOT | Everything else, including verdicts, conviction-only appeals, bail, and sentence appeals that were abandoned or not reached | No |

## 3. How sentencing decisions are selected: logistic regression

### Step 1: is it a criminal case?

The case name must be the Crown against a person, in either order, for example `R. v. Smith`,
`Regina v. Smith` or `Smith v. The Queen`.

### Step 2: measure 41 text signals

The signals are listed in section 12. They include how often "sentenc..." appears (overall, and in the
heading, opening and closing), sentencing vocabulary, appeal wording, bail wording, and the court.

### Step 3: score

Each signal is standardized, multiplied by its weight, and added up. The total becomes a probability
between 0 and 1. **A decision is selected when its probability is 0.5 or more.** Every weight is
published in [models/sentencing_logistic_regression.json](../models/sentencing_logistic_regression.json),
so any decision's score can be checked by hand.

The strongest weights, on standardized signals:

| Signal | Weight | Effect |
|---|---|---|
| Mentions of "sentenc..." (log count) | +1.51 | Toward sentencing |
| Sentence terms in the closing, such as probation, DNA, months, years (log count) | +0.96 | Toward sentencing |
| Mentions of "appeal" (log count) | −0.82 | Away from sentencing |
| The heading says it is a sentencing decision | +0.80 | Toward sentencing |
| Length of the decision (log) | −0.75 | Away from sentencing |
| Sentencing vocabulary, such as denunciation, deterrence, parity (log count) | +0.69 | Toward sentencing |
| Cites s. 718 of the Criminal Code | +0.64 | Toward sentencing |
| Operative sentencing words in the closing, such as "I sentence you" (log count) | +0.62 | Toward sentencing |

The dataset records each decision's probability (`sentencing_probability`) and whether it was selected
(`is_sentencing`).

## 4. Rules v2.0: the written rules (kept for comparison)

Rules v2.0 were used to select decisions before the logistic regression was adopted. They are still
computed, and each decision's result is kept in the column `rules_v2_tier`.

### Signals

| Signal | Meaning |
|---|---|
| COUNT | Number of times "sentenc..." appears (sentence, sentenced, sentencing) |
| DENSITY | COUNT per 10,000 characters |
| TITLE | The heading says it is a sentencing decision, or an appeal "from ... the sentence imposed" |
| STATUTE | Cites ss. 718 to 718.3 of the Criminal Code, the sentencing principles |
| OPENING | "sentenc..." appears in the first 900 characters of the reasons |
| CLOSING | "sentenc..." appears in the last 2,000 characters |
| DISPOSITION | An explicit ruling such as "the sentence appeal is dismissed" or "the sentence is varied" |
| NOT DECIDED | Wording that a sentence appeal was abandoned, not pursued, or need not be addressed |
| NEW TRIAL | "new trial" appears in the last 1,500 characters |
| PROCEDURAL | The opening mentions appointing counsel, an extension of time, reopening, directions or case management |
| CHAMBERS | The heading says it was heard in chambers (one judge dealing with an application) |
| DANGEROUS | Number of mentions of "dangerous offender" or "long-term offender" |
| BAIL | The opening says it is a bail or release application, and the closing deals with release |

### Exclusions

| Exclusion | Condition |
|---|---|
| Bail | BAIL, and no DISPOSITION in the closing |
| Procedural | Appeal court, PROCEDURAL, and either CHAMBERS or no DISPOSITION |
| Not decided | NOT DECIDED (or NEW TRIAL with no DISPOSITION), no sentencing TITLE at trial level, and COUNT under 15 |

### Inclusion

| Rule | Condition | Tier |
|---|---|---|
| A | TITLE, and COUNT of 3 or more | core |
| B | COUNT of 10 or more, and CLOSING | core |
| C | COUNT of 10 or more, STATUTE, and DENSITY of 8 or more | core |
| D | COUNT of 25 or more, and DENSITY of 8 or more | core |
| F | DISPOSITION, and COUNT of 2 or more | core |
| G | Trial court, DANGEROUS of 5 or more, and COUNT of 10 or more | core |
| E | COUNT of 3 or more, OPENING and CLOSING, and no other rule matched | brief |

"Rules v2.0" in the results means core and brief together unless a row says otherwise.

## 5. Finding where a sentence is imposed (IMPOSES)

The IMPOSES methods apply to decisions **already selected by the logistic regression**. They decide
whether the court imposed the sentence itself, as opposed to reviewing one on appeal.

Three rule-based methods were tested, building on each other:

| Method | A decision is marked IMPOSES if |
|---|---|
| Trial court | It is from the Supreme Court of British Columbia, the Supreme Court of Nova Scotia or the Provincial Court of Nova Scotia |
| Trial court, heading shows no appeal | As above, and the heading does not contain "appellant", "respondent", "on appeal", "appeal from" or "summary conviction appeal". This removes sentence appeals heard by a trial court |
| IMPOSES rules v1.0 | As above, and also a sentencing heading (TITLE) or COUNT of 10 or more |

A logistic regression, a gradient boosting model and a decision tree were also trained for this task.

**The dataset uses "trial court, heading shows no appeal".** It scored within about 1 point of the
statistical models (section 7) and can be checked by hand. Each selected decision carries a column
`imposes`. On the current data, 3,576 of the 10,096 selected decisions are marked IMPOSES: 2,471 from
the Supreme Court of British Columbia, 643 from the Supreme Court of Nova Scotia and 462 from the
Provincial Court of Nova Scotia.

## 6. How accuracy was measured

### 6.1 Two samples of 3,200 decisions

| Sample | How it was drawn | Weighting |
|---|---|---|
| **Stratum random sample** | 3,200 decisions drawn at random within five groups (strata) defined by COUNT. The middle groups, where mistakes are most likely, are sampled more heavily | Each decision is weighted by the number of decisions in its stratum divided by the number sampled from it, so figures estimate the whole collection |
| **Random sample** | 3,200 decisions drawn purely at random from all 32,187 criminal decisions | None needed |

The two samples share 316 decisions, so 6,084 different decisions were labelled in all.

| Stratum (COUNT) | Decisions in collection | Stratum random sample | Random sample |
|---|---|---|---|
| 0 | 13,796 | 96 | 1,388 |
| 1 to 2 | 4,722 | 496 | 460 |
| 3 to 9 | 4,690 | 1,072 | 452 |
| 10 to 24 | 3,249 | 864 | 361 |
| 25 or more | 5,730 | 672 | 539 |
| **Total** | **32,187** | **3,200** | **3,200** |

| Label | Stratum random sample | Random sample |
|---|---|---|
| IMPOSES | 531 | 341 |
| REVIEWS | 1,251 | 655 |
| RELATED | 200 | 106 |
| NOT | 1,218 | 2,098 |

The stratum random sample includes the 1,000 decisions labelled in earlier rounds, extended in the same
proportions. Fixed seeds choose every draw (`eval-v1`, `eval-v2` and `eval-v3` for the stratum random
sample, `random-v1` for the random sample).

### 6.2 Labelling

- **Who labelled.** AI labellers (Claude Sonnet 5.5) each labelled about 52 decisions.
- **What they read.** An excerpt of every decision: the end of the heading, the first 1,000 characters
  of the reasons, up to four passages mentioning "sentence", and the last 900 characters. Decisions
  under 3,600 characters were given in full.
- **What they were told.** The definitions in section 2, and nothing about the rules or models.
- **Consistency.** 57 decisions were labelled independently by two labellers of the same model. All 57
  pairs agreed.
- **Cross-check with a different model.** 104 decisions were labelled again by Claude Opus 5.5. It
  agreed on 102. The two differences were between REVIEWS and RELATED. All 104 agreed on whether the
  decision was IMPOSES.

### 6.3 Scoring

| Kind of method | How it was scored |
|---|---|
| Fixed rules (count thresholds, Rules v1.0 and v2.0, IMPOSES rules) | Nothing is trained, so each rule set is applied to the whole sample and compared with the labels |
| Statistical models | **5-fold cross-validation** inside each sample, described below |

**5-fold cross-validation.**

1. The sample is split into five folds, balanced by stratum and by label (seed 0).
2. A model is trained on four folds and classifies the fifth.
3. This repeats five times, so every decision is classified once by a model that never saw it.
4. Those classifications are compared with the labels, pooled across all five folds. Section 7.4 also
   gives the score on each fold separately.

To choose between the two best models, the 5-fold cross-validation was also repeated 10 times with
different splits (section 7.5).

**The two tasks.**

- **Sentencing:** over all criminal decisions in the sample, find those labelled IMPOSES or REVIEWS.
- **IMPOSES:** over the decisions in the sample that the logistic regression selects, find those
  labelled IMPOSES. The selection uses the cross-validated predictions from the sentencing task, so no
  decision is selected by a model that was trained on it. The tables also give "recall of all IMPOSES",
  which also counts IMPOSES decisions that the logistic regression missed in the first place.

**Rules designed on part of the data.** Rules v2.0 was designed using the first 480 decisions of the
stratum random sample, and the IMPOSES rules using the first 1,000. Section 7.3 scores both on the
remaining decisions only.

## 7. Results

### 7.1 Stratum random sample (3,200 decisions, weighted)

**Task: find sentencing decisions**

| Method | Precision | Recall | Decisions selected in collection |
|---|---|---|---|
| Starting idea: cites s. 718, or 10+ mentions | 85.8% | 76.9% | 9,058 |
| Count only: 3+ mentions | 71.9% | 97.5% | 13,669 |
| Count only: 5+ mentions | 79.4% | 92.1% | 11,725 |
| Count only: 10+ mentions | 85.8% | 76.4% | 8,979 |
| Simple: density 8+, or 16+ mentions | 86.8% | 93.1% | 10,829 |
| Rules v1.0, core | 88.1% | 89.3% | 10,219 |
| Rules v1.0, core + brief | 85.8% | 94.2% | 11,021 |
| Rules v2.0, core | 91.8% | 91.2% | 10,053 |
| Rules v2.0, core + brief | 90.5% | 93.9% | 10,503 |
| Statistical: decision tree (5-fold) | 90.1% | 91.7% | 9,694 |
| **Statistical: logistic regression (5-fold, adopted)** | **95.4%** | **95.0%** | **10,096** |
| Statistical: gradient boosting (5-fold) | 95.1% | 95.8% | 10,133 |

**Task: find IMPOSES among the 1,770 sampled decisions selected by logistic regression** (516 are
IMPOSES; this selection keeps 97.7% of all IMPOSES decisions)

| Method | Precision | Recall | Recall of all IMPOSES |
|---|---|---|---|
| Trial court | 90.4% | 99.6% | 97.3% |
| **Trial court, heading shows no appeal (adopted)** | **97.6%** | **99.5%** | **97.2%** |
| IMPOSES rules v1.0 | 97.7% | 98.5% | 96.2% |
| Statistical: decision tree (5-fold) | 98.8% | 97.6% | 95.3% |
| Statistical: logistic regression (5-fold) | 98.2% | 99.1% | 96.7% |
| Statistical: gradient boosting (5-fold) | 98.3% | 99.1% | 96.7% |

### 7.2 Random sample (3,200 decisions, unweighted)

**Task: find sentencing decisions**

| Method | Precision | Recall |
|---|---|---|
| Starting idea: cites s. 718, or 10+ mentions | 86.5% | 78.7% |
| Count only: 3+ mentions | 71.5% | 97.1% |
| Count only: 5+ mentions | 78.9% | 92.5% |
| Count only: 10+ mentions | 86.7% | 78.3% |
| Simple: density 8+, or 16+ mentions | 86.4% | 92.5% |
| Rules v1.0, core | 88.5% | 90.2% |
| Rules v1.0, core + brief | 87.0% | 94.3% |
| Rules v2.0, core | 92.1% | 90.4% |
| Rules v2.0, core + brief | 90.8% | 92.6% |
| Statistical: decision tree (5-fold) | 89.7% | 92.4% |
| **Statistical: logistic regression (5-fold, adopted)** | **95.5%** | **94.7%** |
| Statistical: gradient boosting (5-fold) | 94.7% | 95.0% |

**Task: find IMPOSES among the 987 sampled decisions selected by logistic regression** (331 are
IMPOSES; this selection keeps 97.1% of all IMPOSES decisions)

| Method | Precision | Recall | Recall of all IMPOSES |
|---|---|---|---|
| Trial court | 91.2% | 100.0% | 97.1% |
| **Trial court, heading shows no appeal (adopted)** | **98.2%** | **100.0%** | **97.1%** |
| IMPOSES rules v1.0 | 98.2% | 98.8% | 95.9% |
| Statistical: decision tree (5-fold) | 98.2% | 99.1% | 96.2% |
| Statistical: logistic regression (5-fold) | 99.1% | 99.7% | 96.8% |
| Statistical: gradient boosting (5-fold) | 98.5% | 100.0% | 97.1% |

### 7.3 Fixed rules on decisions never used to design them

For the IMPOSES rules, the decisions were first selected by a sentencing logistic regression trained
on the first 1,000 labels only, so neither step had seen the decisions being scored.

| Decisions scored | Rules v2.0: precision | Rules v2.0: recall | IMPOSES rules v1.0: precision | IMPOSES rules v1.0: recall |
|---|---|---|---|---|
| Stratum random sample, excluding the first 1,000 (2,200) | 90.3% | 93.0% | 97.4% | 98.3% |
| Random sample, excluding the first 1,000 (3,094) | 90.5% | 92.2% | 97.2% | 98.7% |

These match the whole-sample figures closely, so designing the rules on part of the data did not
flatter them.

### 7.4 Per-fold scores for the statistical models

The tables above give **pooled** scores: every decision gets one prediction from the fold that held it
out, and precision and recall are calculated once over all 3,200 predictions. Below are the scores on
each of the five held-out folds, their mean, and their range.

**Stratum random sample: find sentencing decisions** (about 640 decisions per fold)

| Model | Measure | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Fold 5 | Mean | Range |
|---|---|---|---|---|---|---|---|---|
| Decision tree | Precision | 91.5% | 90.1% | 87.9% | 91.4% | 89.9% | 90.1% | 87.9–91.5% |
| Decision tree | Recall | 92.4% | 90.7% | 92.1% | 89.5% | 94.0% | 91.7% | 89.5–94.0% |
| Logistic regression | Precision | 94.8% | 95.4% | 96.4% | 95.4% | 95.0% | 95.4% | 94.8–96.4% |
| Logistic regression | Recall | 95.2% | 93.0% | 94.4% | 94.9% | 97.4% | 95.0% | 93.0–97.4% |
| Gradient boosting | Precision | 93.3% | 95.5% | 96.8% | 95.0% | 94.8% | 95.1% | 93.3–96.8% |
| Gradient boosting | Recall | 95.6% | 95.3% | 94.6% | 94.7% | 98.7% | 95.8% | 94.6–98.7% |

**Random sample: find sentencing decisions** (about 640 decisions per fold)

| Model | Measure | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Fold 5 | Mean | Range |
|---|---|---|---|---|---|---|---|---|
| Decision tree | Precision | 88.8% | 91.3% | 90.5% | 87.0% | 91.0% | 89.7% | 87.0–91.3% |
| Decision tree | Recall | 90.5% | 94.0% | 91.0% | 94.4% | 91.9% | 92.4% | 90.5–94.4% |
| Logistic regression | Precision | 95.5% | 96.4% | 95.5% | 93.5% | 96.9% | 95.6% | 93.5–96.9% |
| Logistic regression | Recall | 94.5% | 94.0% | 95.0% | 93.9% | 95.9% | 94.7% | 93.9–95.9% |
| Gradient boosting | Precision | 94.6% | 96.0% | 93.0% | 93.9% | 96.0% | 94.7% | 93.0–96.0% |
| Gradient boosting | Recall | 95.5% | 95.0% | 94.0% | 93.9% | 96.4% | 95.0% | 93.9–96.4% |

**Stratum random sample: find IMPOSES** (about 354 decisions per fold)

| Model | Measure | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Fold 5 | Mean | Range |
|---|---|---|---|---|---|---|---|---|
| Decision tree | Precision | 98.1% | 99.5% | 98.2% | 99.5% | 98.7% | 98.8% | 98.1–99.5% |
| Decision tree | Recall | 94.6% | 97.7% | 98.1% | 99.5% | 98.2% | 97.6% | 94.6–99.5% |
| Logistic regression | Precision | 97.6% | 100.0% | 96.5% | 98.2% | 98.8% | 98.2% | 96.5–100.0% |
| Logistic regression | Recall | 98.8% | 98.9% | 98.1% | 100.0% | 99.4% | 99.1% | 98.1–100.0% |
| Gradient boosting | Precision | 98.2% | 99.5% | 96.5% | 98.8% | 98.8% | 98.3% | 96.5–99.5% |
| Gradient boosting | Recall | 98.2% | 98.9% | 98.8% | 100.0% | 99.4% | 99.1% | 98.2–100.0% |

**Random sample: find IMPOSES** (about 197 decisions per fold)

| Model | Measure | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Fold 5 | Mean | Range |
|---|---|---|---|---|---|---|---|---|
| Decision tree | Precision | 98.6% | 94.3% | 100.0% | 100.0% | 98.4% | 98.3% | 94.3–100.0% |
| Decision tree | Recall | 100.0% | 100.0% | 100.0% | 100.0% | 95.4% | 99.1% | 95.4–100.0% |
| Logistic regression | Precision | 100.0% | 95.7% | 100.0% | 100.0% | 100.0% | 99.1% | 95.7–100.0% |
| Logistic regression | Recall | 100.0% | 100.0% | 98.5% | 100.0% | 100.0% | 99.7% | 98.5–100.0% |
| Gradient boosting | Precision | 98.6% | 94.3% | 100.0% | 100.0% | 100.0% | 98.6% | 94.3–100.0% |
| Gradient boosting | Recall | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0–100.0% |

Each random-sample IMPOSES fold holds only about 66 IMPOSES decisions, so one mistake moves a fold's
score by about 1.5 points.

### 7.5 Logistic regression against gradient boosting (sentencing task)

The two best models are close, so the 5-fold cross-validation was repeated **10 times with different
random splits** (seeds 0 to 9). That gives 50 held-out folds per sample. Both models were scored on the
same folds.

| Sample | Measure | Logistic regression (mean) | Gradient boosting (mean) | Logistic better | Boosting better |
|---|---|---|---|---|---|
| Stratum random | Precision | 95.4% | 95.1% | 34/50 | 16/50 |
| Stratum random | Recall | 94.9% | 95.5% | 12/50 | 38/50 |
| Stratum random | F1 | 95.2% | 95.3% | 21/50 | 29/50 |
| Random | Precision | 95.6% | 94.6% | 42/50 | 8/50 |
| Random | Recall | 94.6% | 94.9% | 18/50 | 28/50 |
| Random | F1 | 95.0% | 94.7% | 32/50 | 18/50 |

**How to read this table.** The mean columns give each model's average score over the 50 held-out
folds. The last two columns count, fold by fold, which model scored higher. For example, 34/50 means
logistic regression was more precise than gradient boosting on 34 of the 50 folds. F1 combines
precision and recall into one score (their harmonic mean).

- **Logistic regression is consistently a little more precise.** It wins on precision in 34/50 and
  42/50 folds.
- **Gradient boosting is consistently a little better at recall.** It wins on recall in 38/50 and
  28/50 folds.
- **Overall they are tied.** The F1 scores differ by 0.1 to 0.3 points, and the winner changes between
  samples.

**Logistic regression was adopted** for identifying sentencing decisions. It is just as accurate as
gradient boosting and far simpler: one weight per input, published in
`models/sentencing_logistic_regression.json`. Gradient boosting is 300 trees that cannot be read.

### 7.6 What the results show

- **The two samples agree.** Every method scores within about 2 points on the two samples.
- **Logistic regression finds sentencing decisions best.** It is about 95% precise and finds about 95%
  of sentencing decisions, against about 91% and 93% for Rules v2.0, and 86% and 78% for the starting
  idea.
- **IMPOSES is easy once sentencing decisions are well selected.** On the decisions chosen by logistic
  regression, the plain rule "trial court, and the heading shows no appeal" is 98% precise and finds
  99.5 to 100% of IMPOSES decisions. The statistical models are at most about 1 point better.
- **A better first step makes the IMPOSES rules look better.** On the decisions chosen by Rules v2.0,
  the same rule was only 93 to 95% precise, because Rules v2.0 let through more trial-court decisions
  that are not sentencing decisions.
- **A decision can impose a penalty without using the word "sentence".** Of 1,478 labelled decisions
  with a COUNT of zero, 5 were sentencing decisions, each a short decision imposing a fine. No method
  based on that word can find these.

## 8. Offence categories

Each selected decision gets one TRUE or FALSE column per offence category. A decision can be TRUE for
several categories, for example assault and kidnapping.

This section describes the logistic regression models that were built first. Because they missed about
1 real category in 5, **the dataset now takes offence categories from the AI reading of every decision
(section 10)**. The models are kept for decisions the reading could not settle, and for new decisions
after an update until they are read (section 8.6).

### 8.1 Categories

| Column | Offences covered |
|---|---|
| `offence_homicide` | Murder, attempted murder, manslaughter, infanticide, criminal negligence causing death (not driving offences causing death) |
| `offence_sexual` | Sexual assault, sexual interference, sexual exploitation, child pornography, luring, voyeurism, incest, historical offences such as rape or indecent assault |
| `offence_assault` | Non-sexual assault of any level, assaulting a peace officer, unlawfully causing bodily harm |
| `offence_robbery` | Robbery, armed robbery |
| `offence_kidnapping` | Kidnapping, forcible or unlawful confinement, abduction, hostage taking, human trafficking |
| `offence_break_enter` | Break and enter, home invasion, being unlawfully in a dwelling |
| `offence_theft_fraud` | Theft, fraud, possession of stolen property or proceeds of crime, forgery, identity theft, money laundering |
| `offence_drugs` | Trafficking, possession for the purpose of trafficking, production, importing or possession of drugs |
| `offence_weapons` | Firearms or weapons offences. "Assault with a weapon" counts as assault, not weapons |
| `offence_driving` | Impaired or over-80 driving, dangerous driving, driving while prohibited, failing to stop, including when they cause death or bodily harm |
| `offence_other` | Any other offence being sentenced: breaches of court orders, threats, harassment, mischief, arson, obstruction, regulatory offences, and so on |

A category applies only to offences **for which a sentence is imposed or reviewed** in the decision. It
does not apply to offences in the offender's record, in cases cited for comparison, or in charges that
were acquitted, stayed or withdrawn.

### 8.2 Labelled sample

- **Sample.** 5,000 decisions drawn purely at random from the 10,096 selected decisions (seed
  `offence-v1`).
- **Labelling.** AI labellers (Claude Sonnet 5.5) each read about 44 decisions and listed every category
  that applied. They read the end of the heading, the first 1,500 characters of the reasons, up to six
  passages about charges or convictions, and the last 1,000 characters. Decisions under 5,000 characters
  were given in full.
- **Unclear decisions.** For 258 decisions (5.2%), the excerpt did not show what the offences were.
  These are mostly short appeal rulings that never name the offence. They were set aside, leaving 4,742
  decisions.
- **Categories per decision.** Of the 4,742, 3,223 had one category, 1,019 had two, and 500 had three or
  more.
- **Cross-check with a different model.** 100 decisions were labelled again by Claude Opus 5.5. Every
  category matched in 97 of them, and 1,097 of the 1,100 individual category calls matched.

### 8.3 Models and scoring

One yes or no model was trained per category. All models share the same 59 inputs, built by
[scripts/enrichment_patterns.py](../scripts/enrichment_patterns.py):

- **44 keyword counts.** For each of the 11 categories, the log count of that category's keywords
  (offence names and Criminal Code section numbers) in four places: the whole decision, the charge
  wording, the opening, and the closing. "Charge wording" is the 250 characters after words such as
  "convicted", "guilty", "contrary to" and "charged with".
- **11 shares.** Each category's share of all keyword mentions in the charge wording.
- **4 others.** Mentions of weapons prohibition orders, mentions of driving prohibition orders, the log
  of the decision's length, and whether it is a trial court.

| Method | Settings | How scored |
|---|---|---|
| Rule: keyword anywhere | The category's keywords appear at least once in the decision | Whole sample |
| Rule: keyword in the charge wording | The category's keywords appear at least once in the charge wording | Whole sample |
| Logistic regression | Inputs standardized; L2 penalty with C = 1.0 | 5-fold cross-validation |
| Gradient boosting | 200 trees of depth 3; learning rate 0.05; each tree fitted on a random 80% | 5-fold cross-validation |

The 5 folds are a random split of the 4,742 decisions (seed 0), about 948 per fold. Every decision is
classified once, by models that never saw it.

### 8.4 Results

| Category | Labelled decisions | Keyword anywhere: precision | recall | Keyword in charge wording: precision | recall | Logistic regression: precision | recall | Gradient boosting: precision | recall |
|---|---|---|---|---|---|---|---|---|---|
| Homicide | 601 | 56.1% | 98.8% | 70.3% | 96.2% | 94.6% | 93.5% | 92.5% | 93.8% |
| Sexual | 1,016 | 72.0% | 97.1% | 85.1% | 89.1% | 96.3% | 93.0% | 95.1% | 94.8% |
| Assault | 853 | 37.6% | 96.5% | 51.4% | 88.0% | 87.4% | 79.7% | 86.2% | 81.9% |
| Robbery | 401 | 43.3% | 97.3% | 56.1% | 90.0% | 90.0% | 85.5% | 87.5% | 89.3% |
| Kidnapping | 245 | 48.9% | 95.5% | 62.8% | 89.0% | 85.0% | 80.8% | 82.1% | 87.8% |
| Break and enter | 327 | 41.2% | 96.3% | 52.9% | 86.9% | 85.5% | 79.5% | 85.7% | 82.6% |
| Theft and fraud | 593 | 41.5% | 93.6% | 52.1% | 83.8% | 87.1% | 76.4% | 86.2% | 78.2% |
| Drugs | 891 | 44.0% | 98.7% | 68.9% | 92.6% | 96.2% | 93.6% | 95.6% | 93.0% |
| Weapons | 612 | 24.2% | 99.0% | 40.9% | 91.5% | 84.1% | 71.7% | 80.5% | 74.7% |
| Driving | 350 | 27.5% | 95.7% | 48.2% | 88.6% | 89.8% | 82.6% | 86.3% | 86.6% |
| Other | 1,094 | 33.9% | 91.1% | 47.0% | 79.5% | 77.0% | 59.0% | 75.8% | 62.0% |

**All categories together.** Every decision-and-category pair is counted once.

| Method | Precision | Recall | Decisions with every category right |
|---|---|---|---|
| Rule: keyword anywhere | 40.1% | 96.2% | 20.1% |
| Rule: keyword in the charge wording | 56.6% | 88.2% | 39.4% |
| **Logistic regression (adopted)** | **89.1%** | **80.9%** | **68.2%** |
| Gradient boosting | 87.4% | 83.1% | 67.7% |

**Per-fold scores, logistic regression.**

| Category | Measure | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Fold 5 | Mean |
|---|---|---|---|---|---|---|---|
| Homicide | Precision | 97.4% | 96.5% | 91.1% | 93.4% | 95.0% | 94.7% |
| Homicide | Recall | 90.4% | 94.8% | 98.3% | 94.2% | 90.4% | 93.6% |
| Sexual | Precision | 95.9% | 95.9% | 98.4% | 94.0% | 97.5% | 96.4% |
| Sexual | Recall | 92.6% | 93.5% | 89.1% | 95.0% | 95.0% | 93.1% |
| Assault | Precision | 84.7% | 90.1% | 84.4% | 87.3% | 90.3% | 87.4% |
| Assault | Recall | 79.2% | 78.7% | 75.6% | 79.4% | 85.6% | 79.7% |
| Robbery | Precision | 91.0% | 96.1% | 88.5% | 85.3% | 88.8% | 89.9% |
| Robbery | Recall | 87.7% | 82.2% | 80.2% | 87.9% | 91.0% | 85.8% |
| Kidnapping | Precision | 90.9% | 80.7% | 79.2% | 88.6% | 87.8% | 85.4% |
| Kidnapping | Recall | 76.9% | 82.1% | 82.6% | 81.6% | 81.1% | 80.9% |
| Break and enter | Precision | 87.5% | 81.4% | 88.5% | 84.2% | 86.9% | 85.7% |
| Break and enter | Recall | 74.2% | 78.7% | 76.7% | 87.7% | 79.1% | 79.3% |
| Theft and fraud | Precision | 87.9% | 87.9% | 86.0% | 86.6% | 87.4% | 87.1% |
| Theft and fraud | Recall | 79.7% | 69.0% | 76.7% | 82.9% | 74.1% | 76.5% |
| Drugs | Precision | 98.2% | 96.4% | 97.8% | 92.8% | 95.8% | 96.2% |
| Drugs | Recall | 93.8% | 92.6% | 94.7% | 93.3% | 93.5% | 93.6% |
| Weapons | Precision | 85.6% | 82.7% | 80.6% | 84.3% | 87.3% | 84.1% |
| Weapons | Recall | 67.9% | 71.1% | 71.8% | 74.6% | 73.6% | 71.8% |
| Driving | Precision | 91.7% | 91.8% | 88.1% | 88.4% | 88.5% | 89.7% |
| Driving | Recall | 84.6% | 86.2% | 75.4% | 84.7% | 81.8% | 82.5% |
| Other | Precision | 73.3% | 78.3% | 80.2% | 78.3% | 74.2% | 76.9% |
| Other | Recall | 56.5% | 63.5% | 63.5% | 58.9% | 52.2% | 58.9% |

### 8.5 What the offence results show

- **Keywords alone are not enough.** A decision that mentions "robbery" is a robbery sentencing less
  than half the time, because decisions also name offences from the record and from comparison cases.
- **The models are strong for homicide, sexual offences and drugs**: about 95% precision and 93% recall.
- **They are moderate for assault, robbery, kidnapping, break and enter, theft and fraud, and driving**:
  85 to 90% precision and 76 to 86% recall.
- **They are weakest for weapons and "other".** Weapons words appear in most sentences through
  prohibition orders and "assault with a weapon". "Other" is a mixed group with no common wording.
- **Logistic regression and gradient boosting are again close.** Logistic regression is a little more
  precise, gradient boosting finds a little more.

**Other designs tried.** None was clearly better, so the simplest was kept.

| Design | Precision | Recall | Every category right |
|---|---|---|---|
| Logistic regression on keyword counts (adopted) | 89.1% | 80.9% | 68.2% |
| Logistic regression on the words and word pairs of the charge passages | 94.4% | 59.6% | 54.3% |
| Words and word pairs, plus keyword counts | 90.6% | 82.0% | 70.6% |
| Keyword counts, plus counts within the passages the labellers read | 87.8% | 82.1% | 67.6% |

### 8.6 What the dataset uses

The final models were trained on all 4,742 labelled decisions and are saved in
[models/offence_logistic_regression.json](../models/offence_logistic_regression.json). They are no longer
the main source of the offence columns:

- **9,509 decisions** take their offence categories from the AI reading (`offence_source` =
  `ai_reading`).
- **587 decisions** take them from the models (`offence_source` = `model`), because the reader could not
  tell from the text what the offences were. These are mostly short appeal rulings that never name the
  offence. The model answer for them is a best guess.
- **A decision added by a later download** also uses the models until it has been read.

| Column | Decisions marked TRUE (of 10,096) |
|---|---|
| `offence_homicide` | 1,260 |
| `offence_sexual` | 2,068 |
| `offence_assault` | 1,737 |
| `offence_robbery` | 816 |
| `offence_kidnapping` | 507 |
| `offence_break_enter` | 644 |
| `offence_theft_fraud` | 1,178 |
| `offence_drugs` | 1,777 |
| `offence_weapons` | 1,276 |
| `offence_driving` | 685 |
| `offence_other` | 2,332 |

`offence_description` gives the reader's description of the offences in a few words.

## 9. Gladue references and mitigating factors

### 9.1 Gladue reference

`references_gladue` is TRUE when the text contains "Gladue", "Ipeelee" or "718.2(e)". This is a plain
keyword rule, so it is exact. **1,486** of the 10,096 selected decisions are TRUE.

A reference is not the same as an application. Many decisions cite *Gladue* only for general sentencing
principles. Section 9.3 covers whether Gladue factors were given weight.

### 9.2 First round: decisions with a keyword

Whether a court gave a factor weight cannot be read from keywords, so AI readers reviewed the decisions.
The first round (sections 9.2 to 9.4) reviewed only decisions containing at least one of these
keywords. The full reading in section 10 later checked every decision, and the two were reconciled
(section 9.5).

- Gladue, Ipeelee, 718.2(e)
- colonial, coloniz, residential school, Sixties Scoop, intergenerational
- anti-Black, racism, racist, racial profiling, racial discrimination
- Impact of Race and Culture (IRCA), and the citations of *R. v. Morris* (2021 ONCA 680) and
  *R. v. Anderson* (2021 NSCA 62)
- Islamophob, anti-Muslim, white suprem, antisemit

**1,677** decisions matched (`mitigation_keyword`). The other 8,419 contain none of these words.

### 9.3 How the review was done

- **Who.** AI readers (Claude Sonnet 5.5) each reviewed about 30 decisions.
- **What they read.** The end of the heading, the first 900 characters of the reasons, the passages
  around every keyword (up to about 4,800 characters), passages about mitigating factors (up to about
  1,500 characters), and the last 1,200 characters. Decisions under 7,000 characters were given in full.
- **What they decided.** For each factor, one of four codes, as it relates to the offender being
  sentenced:

| Code | Meaning |
|---|---|
| Mitigating | The court treated it as mitigating: it reduced moral blameworthiness, was accepted as a mitigating factor, or was a reason for a lower or non-custodial sentence. On an appeal, the appeal court did this itself or accepted that the sentencing judge properly did |
| Rejected | The court considered it for this offender but gave it no effect |
| Mentioned only | It appears but was not weighed for this offender: a quotation, a general statement of law, a report description, or it concerns someone else |
| Not mentioned | It does not appear in the excerpt |

The readers were told to be strict: "mitigating" requires the excerpt to show the court giving the
factor weight for this offender.

### 9.4 Results of the first round

These are the first round's figures, on the 1,677 keyword decisions. The dataset's final figures are in
section 9.5.

| Factor | Mitigating | Rejected | Mentioned only | Not mentioned |
|---|---|---|---|---|
| Gladue factors: Indigenous background and systemic factors | 508 | 205 | 701 | 263 |
| Colonialism, named as such | 55 | 6 | 104 | 1,512 |
| Residential schools | 109 | 16 | 176 | 1,376 |
| Intergenerational trauma, named as such | 75 | 6 | 82 | 1,514 |
| Anti-Black racism | 69 | 25 | 59 | 1,524 |
| Other systemic or overt racism | 36 | 17 | 147 | 1,477 |
| Islamophobia | 1 | 1 | 5 | 1,670 |
| White supremacy, with the offender as its victim | 1 | 0 | 7 | 1,669 |
| Other prejudice, such as antisemitism or homophobia | 1 | 1 | 10 | 1,665 |

- **579 decisions** have at least one factor treated as mitigating.
- **12 decisions** involve an offence that was itself motivated by hatred of a group. This is the
  opposite situation, and makes a sentence heavier.
- **The readers marked 389 of the 1,677 reviews as low confidence**, meaning the excerpt did not clearly
  show how the court treated the factors.

**Cross-check with a different model.** 60 decisions were reviewed again by Claude Opus 5.5. The two
models gave the same answer on "any factor mitigating" in 59 of 60. For each single factor they agreed
on 59 or 60 of the 60.

### 9.5 Second round and reconciliation

The full reading of every decision (section 10) coded the same nine factors again, with the same four
codes, for all 10,096 decisions. The two rounds were built from different excerpts: the first around
the keywords, the second around the sentence and the mitigating factors.

- **Decisions with no keyword.** The full reading found a factor treated as mitigating in **27
  decisions** that contain none of the keywords. Most weigh the offender's "Aboriginal background" or
  "Indigenous status" without naming *Gladue* or s. 718.2(e). The first round could never have found
  these.
- **Disagreements.** On the 1,677 keyword decisions, the two rounds disagreed about at least one factor
  being mitigating in **250 decisions**, and about "any factor mitigating" in 125.
- **Third reading.** Claude Opus 5.5 re-read those 250 decisions from a longer text: the whole decision
  up to 40,000 characters, and otherwise the opening, the last 5,000 characters, and passages around
  every keyword, every mention of Indigenous background, racialization or discrimination, and every
  mention of mitigation. Its answer replaces both earlier rounds for those decisions (`systemic_source`
  = `adjudicated` in [data/labels/decision_labels.csv](../data/labels/decision_labels.csv)).
- **Who the third reader sided with.** On "any factor mitigating", it sided with the full reading in 63
  and the first round in 62 of the 125. On single factors, 161 and 167. Neither round was clearly better.
- **One wording change.** The third reader's instructions added one sentence: a court that says it
  "took into account" the offender's Indigenous background when choosing a lower sentence or range is
  giving it weight. This applies the existing definition, but it may make the third reading slightly
  more willing to code "mitigating". It affects only the 250 reconciled decisions.

**Final counts** (all 10,096 decisions):

| Factor (column) | Mitigating | Rejected | Mentioned only |
|---|---|---|---|
| Gladue factors (`mitigating_gladue_factors`) | 532 | 217 | 184 |
| Colonialism (`mitigating_colonialism`) | 86 | 5 | 94 |
| Residential schools (`mitigating_res_school`) | 136 | 17 | 147 |
| Intergenerational trauma (`mitigating_intergen_trauma`) | 85 | 11 | 60 |
| Anti-Black racism (`mitigating_anti_black_racism`) | 68 | 23 | 41 |
| Other systemic or overt racism (`mitigating_systemic_racism`) | 42 | 17 | 82 |
| Islamophobia (`mitigating_islamophobia`) | 2 | 1 | 0 |
| White supremacy (`mitigating_white_supremacy`) | 1 | 0 | 0 |
| Other prejudice (`mitigating_other_prejudice`) | 4 | 2 | 4 |

- **602 decisions** have at least one of these factors treated as mitigating
  (`mitigating_any_systemic`).
- **17 decisions** involve an offence that was itself motivated by hatred of a group
  (`hate_motivated_offence`).
- **941 decisions** identify an offender being sentenced as Indigenous (`offender_indigenous`).

### 9.6 Columns in the dataset

| Column | Meaning |
|---|---|
| `references_gladue` | The keyword rule in section 9.1 |
| `mitigation_keyword` | The decision contains a keyword from section 9.2 |
| `mitigating_<factor>` | TRUE if the factor was treated as mitigating for an offender in this decision |
| `mitigating_any_systemic` | TRUE if any of the nine factors is mitigating |
| `gladue_factors_treatment` | How Gladue factors were treated: mitigating, rejected, mentioned only, or blank if not mentioned |
| `mitigating_quote` | The passage showing the court giving a factor weight, copied exactly and checked against the text |
| `offender_indigenous` | The decision identifies an offender being sentenced as Indigenous |
| `hate_motivated_offence` | The offence was motivated by hatred of a group |

The four-way codes for every factor are in
[data/labels/decision_labels.csv](../data/labels/decision_labels.csv) (columns `systemic_<factor>`). The
first round's codes stay in [data/labels/mitigation_labels.csv](../data/labels/mitigation_labels.csv).

### 9.7 What these columns can and cannot show

- **They show that a court treated a factor as mitigating, not by how much.** Courts almost never state
  a number of months taken off for a factor.
- **They come from AI readers, not from a rule or model**, so a script cannot reproduce them. The saved
  file is the record.
- **Long decisions were read as excerpts.** A factor weighed in a passage the excerpt left out could be
  missed.
- **Islamophobia, white supremacy and other prejudice are each mitigating in four decisions or fewer.**
  That is too few to analyse.
- **The two readings disagreed on 15% of the keyword decisions (250/1,677)** before reconciliation.
  Judging whether a court "gave weight" to a factor is genuinely uncertain in many decisions.

## 10. Reading every decision: offences, sentence and mitigating factors

AI readers read every one of the 10,096 selected decisions and recorded what each one decided. This is
the source of the offence columns (section 8.6), the sentence and penalty columns, the
alternative-institution columns, and the mitigating-factor columns (section 9).

### 10.1 What the readers saw

Prepared by [scripts/evaluation/make_full_read_batches.py](../scripts/evaluation/make_full_read_batches.py)
(seed `full-read-v1`):

- **Decisions up to 18,000 characters were given in full.** That covers 5,618 decisions (56%).
- **Longer decisions** (4,478) were given as the end of the heading, the first 3,500 characters of the
  reasons, the last 6,000 characters, and passages from the middle around:
  - mentions of a healing lodge, treatment centre, residential program or psychiatric facility
  - statements of the sentence ("I sentence", "term of imprisonment", "credit for", "global sentence",
    "conditional sentence order" and similar)
  - mentions of mitigation
  - the systemic-factor keywords of section 9.2
  - the charges
- Decisions were packed about 10 to a file (958 files). Each file went to one reader (Claude Sonnet
  5.5). The full instructions are in the workflow script recorded with the labels.

### 10.2 What the readers recorded

For each decision, one line of structured answers:

| Item | Recorded as |
|---|---|
| Offences | The 11 categories of section 8.1, and a short description |
| Outcome | Imposed (first instance), appeal upheld, appeal reduced, appeal increased, appeal varied otherwise, no sentence fixed (for example a new trial ordered), or unclear |
| Prison | Total jail or penitentiary time before credit for pre-sentence custody, or life, indeterminate, none, time served, or unclear. Also the time left after credit, the credit itself, and parole ineligibility for life sentences |
| Other penalties | Lengths of a conditional sentence, probation, long-term supervision and driving prohibition; dollar amounts of fines and restitution; community service hours; and every ancillary order (weapons prohibition, DNA order, sex offender registration, s. 161 order, no-contact order, forfeiture, victim surcharge, discharge, suspended sentence, intermittent sentence, delayed parole, dangerous or long-term offender designation, youth sentence) |
| Alternative institution | A healing lodge, residential treatment centre, psychiatric facility, or other non-prison institution; whether it was **ordered**, required **if a supervisor directs**, or only **recommended** to corrections authorities; its name; and how long |
| Sentence quotation | The passage stating the sentence, copied exactly |
| Systemic factors | The nine factors of section 9, each coded mitigating, rejected or mentioned only |
| Ordinary mitigating factors | The ones the court accepted, from 21 codes (section 10.5) |
| Indigenous offender | Whether the decision identifies an offender being sentenced as Indigenous |
| Confidence | High or low, with a short note |

**Which sentence is recorded:**
- **The sentence that stands at the end of the decision.** On an appeal that fails, that is the
  sentence under appeal. On an appeal that succeeds, it is the new sentence.
- **The majority's reasons, not a dissent.**
- **The total for all counts in the decision** (the global sentence).
- **The first-named offender**, when several are sentenced together (475 decisions). The others are
  summarised in `co_offenders`. The systemic and ordinary mitigating factors count if they apply to any
  offender sentenced.

**Durations** were recorded as years, months and days exactly as the court stated them ("two years less
a day"). A script then converted each one to months (one day = 1/30.4375 of a month) and to readable
text.

### 10.3 Checks made by script

[scripts/evaluation/merge_full_read.py](../scripts/evaluation/merge_full_read.py) combines the answers
and checks them, with no AI:

- **Completeness.** Every decision must have exactly one valid answer. Readers skipped 20 decisions; a
  follow-up reader read those.
- **Allowed values.** Codes outside the allowed lists are tidied: unknown penalty codes become
  `other`, and an unreadable prison value becomes `unclear` (7 cases).
- **Quotations.** Each quotation is compared with the decision's text, ignoring spacing and
  punctuation. 9,792 of 9,813 sentence quotations (99.8%) and 598 of 599 mitigating quotations were
  found word for word. The 22 that were not found were dropped.

### 10.4 Agreement

**A second model.** Claude Opus 5.5 read 150 randomly chosen decisions from the same text.

| Item | Same answer |
|---|---|
| Every offence category | 145/150 |
| Single offence category calls | 1,642/1,650 |
| Sentence outcome | 146/150 |
| Prison time | 140/150 |
| Probation length | 148/150 |
| Conditional sentence length | 149/150 |
| Alternative institution (type) | 149/150 |
| Offender identified as Indigenous | 150/150 |
| Any systemic factor mitigating | 147/150 |
| Gladue factors code (mitigating, rejected, mentioned only, not mentioned) | 140/150 |
| Guilty plea accepted as mitigating | 140/150 |
| Every one of the 21 ordinary mitigating factors | 103/150 |
| Single ordinary mitigating factor calls | 3,088/3,150 |

The ordinary mitigating factors agree call by call (98%), but with 21 of them it is common for the two
readers to differ on at least one. Good character and rehabilitation were the most disputed; the
second model found slightly more of most factors.

**The earlier offence labelling.** 4,709 decisions were labelled for offences in both the earlier round
(section 8.2, from shorter excerpts) and this reading. Every category matched in 4,476 (95.1%), and
51,500 of 51,799 single category calls (99.4%). Most differences were in `other`.

### 10.5 Results

**Outcome.**

| Outcome (`sentence_outcome`) | Decisions |
|---|---|
| Imposed (first instance) | 3,515 |
| Appeal upheld | 3,797 |
| Appeal reduced | 1,644 |
| Appeal increased | 447 |
| Appeal varied otherwise | 411 |
| No sentence fixed | 259 |
| Unclear | 23 |

**Prison time** (`prison_time`, `prison_months`, `prison_life`, `prison_indeterminate`):

| Prison | Decisions |
|---|---|
| A stated length | 6,838 |
| Life | 504 |
| Indeterminate (dangerous offender) | 248 |
| Time served | 183 |
| None | 1,256 |
| Not stated in the text read | 808 |
| No sentence fixed | 259 |

The median stated length is 36 months. Most of the 808 "not stated" decisions are short appeal rulings
that say the appeal is dismissed without restating the sentence; only 59 are IMPOSES decisions.

**Other penalties** (decisions with each one):

| Penalty | Decisions | Penalty | Decisions |
|---|---|---|---|
| Probation | 2,595 | Weapons prohibition | 2,926 |
| Conditional sentence | 875 | DNA order | 2,799 |
| Long-term supervision | 141 | No-contact order | 1,044 |
| Driving prohibition | 497 | Forfeiture | 1,024 |
| Fine | 304 | Victim surcharge | 704 |
| Restitution | 290 | Sex offender registration | 672 |
| Community service | 398 | s. 161 order | 319 |
| Intermittent sentence | 132 | Dangerous offender | 276 |
| Suspended sentence | 213 | Long-term offender | 124 |
| Conditional discharge | 96 | Youth sentence | 229 |
| Absolute discharge | 17 | Delayed parole | 59 |

Ancillary orders such as the victim surcharge and DNA order are often not mentioned in appeal
decisions, so these counts are lower than the number actually ordered.

**Alternative institutions** (`alt_institution`, `alt_institution_basis`, `alt_institution_name`,
`alt_institution_time`, `alt_institution_months`):

| Type | Ordered | If a supervisor directs | Recommended | Total |
|---|---|---|---|---|
| Healing lodge | 2 | 0 | 10 | 12 |
| Residential treatment | 36 | 81 | 16 | 133 |
| Psychiatric facility | 3 | 1 | 21 | 25 |
| Other | 15 | 1 | 11 | 27 |

- **Courts rarely set a length.** Only 16 of the 197 give one. A healing lodge placement was ordered in
  only 2 decisions; in the other 10 the court recommended that the prison service place the offender in
  one. Courts cannot order a penitentiary placement.
- **Healing lodges are rare in published sentencing.** Section 81 healing lodge placements are decided
  by Correctional Service Canada after sentencing, so they seldom appear in the decision.

**Ordinary mitigating factors** (`mitigating_<code>`). 6,568 decisions deal with mitigating factors in
the text read (`mitigating_discussed`); 6,041 have at least one accepted (`mitigating_any_general`).

| Factor | Decisions | Factor | Decisions |
|---|---|---|---|
| Guilty plea | 2,729 | Collateral consequences | 459 |
| No or minor record | 2,555 | Addiction | 478 |
| Rehabilitation | 2,167 | Mental health | 418 |
| Remorse | 1,846 | Strict bail conditions | 369 |
| Good character | 1,480 | Age or health | 333 |
| Family support or dependants | 1,424 | Cooperation | 333 |
| Youth | 1,224 | Lesser role | 302 |
| Abuse or trauma in upbringing | 728 | Harsh pre-sentence custody | 220 |
| Delay | 186 | FASD, cognitive or brain injury | 141 |
| Restitution made | 63 | State misconduct | 27 |
| Other | 190 | | |

`mitigating_any` is TRUE when either a systemic or an ordinary factor was mitigating (6,081 decisions).

**Confidence.** Readers marked 1,560 decisions (15%) low confidence. 1,159 of these were given in full,
because short decisions, mostly brief appeal rulings, often do not restate the sentence.

### 10.6 Columns in the dataset

All of these come from [data/labels/decision_labels.csv](../data/labels/decision_labels.csv), joined by
court and citation. `ai_read` is TRUE for every current decision. **A decision added by a later
download has `ai_read` = FALSE and blank reading columns until it has been read.**

| Column | Meaning |
|---|---|
| `offence_source`, `offence_description` | Where the offence columns came from; the offences in words |
| `sentence_outcome`, `n_offenders`, `co_offenders` | Section 10.2 |
| `prison_time` | The prison sentence in words, as stated ("2 years less a day", "life", "time served", "none", "unclear") |
| `prison_months` | The same in months (0 for no prison; blank for life, indeterminate, unclear or no sentence) |
| `prison_life`, `prison_indeterminate` | Life or indeterminate sentence |
| `prison_after_credit_months`, `presentence_credit_months`, `parole_ineligibility_years` | When stated |
| `conditional_sentence_months`, `probation_months`, `long_term_supervision_months`, `driving_prohibition` | Lengths, when stated |
| `fine_dollars`, `restitution_dollars`, `community_service_hours` | Amounts (0 if none) |
| `penalty_<type>` | TRUE if that penalty or order is part of the sentence |
| `alt_institution`, `alt_institution_basis`, `alt_institution_name`, `alt_institution_time`, `alt_institution_months` | Section 10.5 |
| `sentence_quote` | The sentence as the court stated it, copied exactly and checked |
| `mitigating_<code>`, `mitigating_any_general`, `mitigating_discussed`, `mitigating_any` | Section 10.5 |
| `reading_shown`, `reading_confidence`, `reading_note` | Whether the reader saw the full text or excerpts, and how sure it was |

### 10.7 What this reading can and cannot show

- **It is an AI reading, not a lawyer's.** The checks above show it is consistent and its quotations
  are real. They do not show it is always right.
- **Long decisions were read as excerpts.** The sentence is nearly always in the closing or in a passage
  the excerpt picks out, but a factor discussed elsewhere can be missed.
- **Appeal decisions often do not restate the full sentence.** Prison time is unclear for 808
  decisions, almost all appeals. Ancillary orders are under-counted on appeals.
- **Several offenders.** The sentence columns describe only the first-named offender.
- **Prison months are before credit** for pre-sentence custody. Compare like with like.
- **New decisions need reading.** The build script does not call AI. After a data update, new decisions
  show `ai_read` = FALSE until the reading is run for them.

### 10.8 Extract pictures: the crime and the court's reasons

The 602 decisions with a systemic factor treated as mitigating each have two pictures, in
[case_extracts/](../case_extracts/)`<court>/<citation>_crime.png` and `_rationale.png`. Each picture shows
the court's own numbered paragraphs, with key phrases highlighted in yellow.

**How they were made.**
1. **Numbered paragraphs.** [scripts/extracts/make_extract_batches.py](../scripts/extracts/make_extract_batches.py)
   splits each decision into its numbered paragraphs. It keeps only paragraph markers that run in
   sequence, so citations such as "[2001] 1 S.C.R." are not mistaken for paragraphs.
2. **Picking passages.** An AI reader (Claude Sonnet 5.5) read each decision, 3 decisions per file, and
   picked two passages. Its instructions are in
   [pipeline/4_pick_extracts.js](../pipeline/4_pick_extracts.js).
   - **Crime:** one run of consecutive paragraphs (about 120–300 words) telling what the offender did.
   - **Rationale:** one or two runs of paragraphs (about 120–350 words) showing what systemic factor was
     weighed and the court's own conclusion about its effect.
3. **Choosing the highlights.** The reader chose phrases copied from the text.
   - **In the crime passage:** each phrase names who did what to whom ("he slashed her…"), covering the
     most serious acts and their effect on the victim. Graphic sexual details and anything identifying a
     victim are never highlighted.
   - **In the rationale:** whole clauses, namely the court's framing of the question, the link between
     the offender and the systemic factor, and the court's conclusion. Any statement that the sentence
     must not perpetuate structural inequities is highlighted in full.
     A phrase that argues against the factor (it is not mitigating, has little weight or no link to the
     offence) is never highlighted.
4. **Drawing.** [scripts/extracts/render_extracts.py](../scripts/extracts/render_extracts.py) draws the
   pictures without AI.
   - **Automatic highlights:** in the rationale it also highlights the named factors (Gladue,
     s. 718.2(e), colonialism, residential schools, intergenerational trauma, anti-Black racism, IRCA,
     *R. v. Anderson*, *R. v. Morris* and similar).
   - **Checking phrases:** it highlights a phrase only where it is found in the paragraph text.

**Direction check.** A final check ([pipeline/5d_check_direction.js](../pipeline/5d_check_direction.js),
applied by [scripts/extracts/apply_direction_check.py](../scripts/extracts/apply_direction_check.py)) reads every
reasons picture shown on the website. Sonnet 5.5 readers check each one, and Opus 5.5 re-reads every case they
flag. Highlights saying the factor is not mitigating are removed. Cases where the court did not treat the factor
as mitigating, or never stated its effect, are hidden from the website and no longer counted as mitigating in the
dataset.

**How the instructions were set.** Three pilot cases (*Taniskishayinew*, 2018 BCSC 296; *Arnet*, 2026
BCSC 2194; *Caldi*, 2025 NSSC 426) went through four rounds of review by the project author. The rules
above come from that review. Earlier rounds are kept in `case_extracts/v1/` and `v2/`.

**Results.**

| | Count |
|---|---|
| Decisions | 602 |
| Pictures drawn | 1,200 |
| Decisions where the court plainly states the factor's effect (`extract_conclusion_clear` = Y) | 469 |
| Decisions where it does not (N) | 133 |
| Decisions with no numbered paragraphs, so no pictures (2013 NSPC 99, 2015 NSPC 83) | 2 |
| Picked phrases not found in the text (skipped) | 21 |
| Decisions whose crime picture has no account of the offence (noted by the reader; mostly short appeal rulings) | about 20 |

**Columns:** `extract_crime_png`, `extract_rationale_png` and `extract_conclusion_clear`. The picks,
with the reader's notes, are in [case_extracts/extracts.csv](../case_extracts/extracts.csv). The readers'
raw answers are in `case_extracts/work/raw/`.

**Before publishing.**
- **Different runs pick slightly different phrases.** Every picture is a reasonable choice, not the
  only one.
- **Victims are named as the decision names them.**
- **Sexual offences:** about 124 of the decisions are sexual offences. Their crime passages contain the
  court's description even though the graphic phrases are not highlighted.
- **Cases marked N or noted as having no offence account** are the ones to review or leave out.

## 11. Limits

- **The labels came from AI models reading excerpts**, not from lawyers reading full decisions.
- **About 1 selected decision in 22 is not a sentencing decision.** Many of these are RELATED rulings,
  for example a ruling on evidence at a sentencing hearing.
- **About 5% of sentencing decisions are missed.** These are mostly very short appeal rulings, and
  decisions that impose a penalty without using the word "sentence".
- **A model's choice is harder to explain than a rule's.** The weights are published, but a decision is
  selected because of a combined score, not one condition.
- **The IMPOSES methods depend on knowing which courts are trial courts.** They would need extending
  for courts outside the eight used here.
- **The models have only seen these eight courts.** Accuracy on other courts is unknown.
- **Offences, the sentence and mitigating factors come from an AI reading** (sections 10.7 and 9.7).
  For the 587 decisions whose offences the reader could not tell, the offence models are used instead;
  they miss about 1 real category in 5 (section 8).
- **Regulatory prosecutions** (for example under the Fisheries Act) are included, because they are also
  named `R. v. ...`.
- **French-only decisions** (about 200) are skipped.
- **Only published decisions exist in the source.** Most sentences in Canada are never published.

## 12. The statistical models for sentencing and IMPOSES

All models use the same 41 inputs, built by
[scripts/evaluation/model_features.py](../scripts/evaluation/model_features.py) from signals defined in
[scripts/evaluation/build_features.py](../scripts/evaluation/build_features.py):

- the log count of 21 kinds of phrase, including "sentence" (overall, and separately in the heading,
  opening and closing), aggravating or mitigating, fitness of sentence, sentencing vocabulary,
  pre-sentence reports, operative sentencing words, sentence-appeal outcomes, appeal wording, voir
  dire, bail, guilty plea, dangerous offender, "appellant", "application", and sentence terms in the
  closing (such as probation, DNA, months, years)
- 17 yes or no signals, including trial court, sentencing heading, appeal heading, cites s. 718,
  abandoned, new trial, procedural opening, chambers, and Supreme Court of Canada
- the log of the decision's length, its density (capped at 100), and how far into the text "sentence"
  first appears

| Model | Settings |
|---|---|
| Decision tree | Depth 4; each leaf holds at least 1% of the weight |
| Logistic regression | Inputs standardized; L2 penalty with C = 1.0 |
| Gradient boosting | 300 trees of depth 3; learning rate 0.05; each tree fitted on a random 80% |

**Saved models.** After the evaluation, each model was retrained on all 6,084 labelled decisions and
saved in [models/](../models/). The IMPOSES models were retrained on the 2,579 labelled decisions that the
saved sentencing logistic regression selects. Each decision was weighted by one over its chance of
being sampled. [models/README.md](../models/README.md) explains the files and how to use them.

## 13. Software

| Package | Version | Used for |
|---|---|---|
| Python | 3.12.10 | Running everything |
| DuckDB | 2.0.0 | Reading the data and measuring the signals |
| PyArrow | 26.0.1 | Parquet file support |
| pandas | 3.1.1 | Evaluation tables |
| NumPy | 2.5.5 | Scoring with the published weights, and cross-validation folds |
| scikit-learn | 1.9.1 | Training the statistical models |
| joblib | bundled with scikit-learn | Saving the models |

## 14. Reproducing

From the project folder:

```
.venv\Scripts\python.exe scripts\build_sentencing_data.py                # download data, select sentencing decisions
.venv\Scripts\python.exe scripts\evaluation\build_features.py            # signals for every criminal decision
.venv\Scripts\python.exe scripts\evaluation\merge_labels.py              # combine the labellers' answers
.venv\Scripts\python.exe -X utf8 scripts\evaluation\evaluate_3200.py     # tables in section 7, and the saved models
.venv\Scripts\python.exe -X utf8 scripts\evaluation\merge_enrichment_labels.py   # combine offence and mitigating-factor answers
.venv\Scripts\python.exe -X utf8 scripts\evaluation\evaluate_offences.py  # tables in section 8, and the offence models
.venv\Scripts\python.exe -X utf8 scripts\evaluation\make_full_read_batches.py      # texts for the full reading (section 10)
.venv\Scripts\python.exe -X utf8 scripts\evaluation\merge_full_read.py             # check and combine the readers' answers
.venv\Scripts\python.exe -X utf8 scripts\evaluation\make_adjudication_batches.py   # texts for the third reading (section 9.5)
```

The readings themselves were done by AI readers between the script steps. Their raw answers are saved,
so `merge_full_read.py` rebuilds `decision_labels.csv` exactly without any AI.

Building the dataset only needs the published weights in
`models/sentencing_logistic_regression.json`, not scikit-learn.

| File | Contents |
|---|---|
| [data/labels/labels.csv](../data/labels/labels.csv) | The 6,084 labelled decisions. `in_stratified` and `in_random` mark which sample each belongs to |
| [data/labels/results_3200.csv](../data/labels/results_3200.csv) | Every pooled figure in section 7 |
| [data/labels/results_3200_folds.csv](../data/labels/results_3200_folds.csv) | The per-fold scores in section 7.4 |
| [data/labels/results_3200_head_to_head.csv](../data/labels/results_3200_head_to_head.csv) | The repeated comparison in section 7.5 |
| [data/labels/offence_labels.csv](../data/labels/offence_labels.csv) | The 5,000 decisions labelled with offence categories |
| [data/labels/results_offences.csv](../data/labels/results_offences.csv) and `results_offences_folds.csv` | Every figure in section 8.4 |
| [data/labels/mitigation_labels.csv](../data/labels/mitigation_labels.csv) | The 1,677 decisions reviewed in the first round, with a code for each factor |
| [data/labels/decision_labels.csv](../data/labels/decision_labels.csv) | The full reading of all 10,096 decisions, after checks and the third reading. The build script reads this file |
| `data/labels/full_read_batches/`, `full_read_raw/`, `full_read_audit_batches/`, `full_read_audit_raw/` | The texts read in section 10, the readers' raw answers, and the second model's |
| `data/labels/adjudication_batches/`, `adjudication_raw/` | The texts and answers of the third reading |
| [pipeline/](../pipeline/) | The exact instructions given to the AI readers (one-off and abandoned steps in `pipeline/archive/`) |
| [case_extracts/](../case_extracts/), `extracts.csv`, `work/` | The extract pictures (section 10.8), the list of picks, and the readers' raw answers |
| `data/labels/offence_batches/`, `mitigation_batches/` and the matching `_raw/` and `_audit` folders | The excerpts read for sections 8 and 9, and the raw answers |
| `data/labels/batches/` | The excerpts the labellers read |
| `data/labels/raw/` and `data/labels/raw_audit/` | The labellers' raw answers, and the second model's answers |

The build script downloads the newest version of the data, so a later run covers more decisions. The
version used for this document is recorded in `sentencing_data/build_info.json`.
