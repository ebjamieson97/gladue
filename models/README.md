# Saved statistical models

Six models trained on 6,084 hand-labelled Canadian criminal court decisions. See
[METHODOLOGY.md](../docs/METHODOLOGY.md) for how they were evaluated.

**`sentencing_logistic_regression` is the model the dataset uses** to select sentencing decisions.
The build script scores decisions with the weights in `sentencing_logistic_regression.json`. The other
five models are kept for comparison and possible later use.

## What each model does

| Task | Question it answers | Apply it to |
|---|---|---|
| `sentencing_*` | Is this a sentencing decision (a court imposes a sentence or reviews one)? | Any criminal decision |
| `imposes_*` | Does the court impose the sentence itself, as opposed to reviewing it on appeal? | Decisions already selected by `sentencing_logistic_regression` |

Each task has three models:

| Model | Files | Notes |
|---|---|---|
| Logistic regression | `.joblib`, and `.json` with every weight | Most accurate with gradient boosting. The JSON file is enough to score a decision without scikit-learn |
| Gradient boosting | `.joblib` | 300 small decision trees. Cannot be read by eye |
| Decision tree | `.joblib`, and `.txt` with the tree written out | Readable, but less accurate |

## Accuracy

Measured by 5-fold cross-validation inside each 3,200-decision sample. The saved models were then
retrained on all labelled decisions.

| Model | Stratum random sample: precision | recall | Random sample: precision | recall |
|---|---|---|---|---|
| `sentencing_logistic_regression` | 95% | 95% | 96% | 95% |
| `sentencing_gradient_boosting` | 95% | 96% | 95% | 95% |
| `sentencing_decision_tree` | 90% | 92% | 90% | 92% |
| `imposes_logistic_regression` | 98% | 99% | 99% | 100% |
| `imposes_gradient_boosting` | 98% | 99% | 99% | 100% |
| `imposes_decision_tree` | 99% | 98% | 98% | 99% |

For comparison, Rules v2.0 scores 91% precision and 93 to 94% recall on the sentencing task. On the
IMPOSES task, the plain rule "trial court, and the heading shows no appeal" scores 98% precision and
99.5 to 100% recall.

## Inputs

All six models take the same 41 inputs, listed in order in `model_info.json` and built by
[scripts/evaluation/model_features.py](../scripts/evaluation/model_features.py):

- 21 phrase counts, each as log(1 + count), such as how often "sentenc..." appears
- 17 yes or no signals, such as whether the decision is from a trial court
- the log of the text length, the density of "sentenc..." per 10,000 characters (capped at 100), and
  how far into the text "sentenc..." first appears

The underlying counts and signals come from
[scripts/evaluation/build_features.py](../scripts/evaluation/build_features.py), which holds every text
pattern.

## Using a model

```python
import sys
import duckdb
import joblib

sys.path.insert(0, "scripts/evaluation")
from model_features import model_matrix

# 1. Signals for every criminal decision (made by scripts/evaluation/build_features.py)
df = duckdb.sql("""
    SELECT f.*
    FROM 'data/processed/eval_features.parquet' f
    JOIN 'data/processed/criminal_decisions_signals.parquet' s USING (court, citation)
""").df()

# 2. Sentencing decision or not, for every criminal decision
model = joblib.load("models/sentencing_logistic_regression.joblib")
df["is_sentencing"] = model.predict(model_matrix(df).values)

# 3. IMPOSES or not, for decisions selected by the sentencing model
selected = df[df.is_sentencing == 1].copy()
model = joblib.load("models/imposes_logistic_regression.joblib")
selected["imposes"] = model.predict(model_matrix(selected).values)
```

On the data version of 15 November 2026, `sentencing_logistic_regression` selects 10,096 of 32,187
criminal decisions, and `imposes_logistic_regression` selects 3,522 of those 10,096.

## Training

- **Data:** 6,084 labelled decisions (the two 3,200-decision samples, which share 316 decisions). The
  IMPOSES models were trained on the 2,579 of those that `sentencing_logistic_regression` selects.
- **Weights:** each decision is weighted by one over its chance of being sampled, so the models reflect
  the whole collection.
- **Settings:** logistic regression with standardized inputs and C = 1.0; gradient boosting with 300
  trees of depth 3, learning rate 0.05, each tree on a random 80%; decision tree of depth 4, each leaf
  holding at least 1% of the weight.
- **Software:** Python 3.12.10, scikit-learn 1.9.1, NumPy 2.5.5, pandas 3.1.1.
- **To retrain:** `.venv\Scripts\python.exe -X utf8 scripts\evaluation\evaluate_3200.py`

## Limits

- **The labels came from an AI model reading excerpts**, not from lawyers reading full decisions. A
  second, different AI model agreed on 102 of 104 re-labelled decisions.
- **The models have only seen eight courts**: the Supreme Court of Canada, four provincial Courts of
  Appeal, and three trial courts in British Columbia and Nova Scotia. Decisions from other courts are
  laid out differently, and accuracy there is unknown.
- **The `.joblib` files need the same scikit-learn version** (1.9.1) to load reliably. The `.json` and
  `.txt` files do not.
- **A model's answer cannot be explained by pointing to a rule.**

## Offence category models

Added after the models above. See section 8 of [METHODOLOGY.md](../docs/METHODOLOGY.md).

| File | Contents |
|---|---|
| `offence_logistic_regression.json` | **Used by the dataset as a fallback**: for decisions whose offences the AI reading could not tell (587), and for new decisions until they are read. One logistic regression per offence category (11 in all), with every weight. All share the same 59 inputs |
| `offence_logistic_regression.joblib` | The same models as scikit-learn objects, with their scaler |
| `offence_gradient_boosting.joblib` | A gradient boosting model per category, kept for comparison |

- **Apply to:** decisions already selected as sentencing decisions.
- **Inputs:** built by `offence_matrix()` in [scripts/enrichment_patterns.py](../scripts/enrichment_patterns.py), from keyword counts made by `offence_feature_sql()` in the same file.
- **Training data:** 4,742 labelled sentencing decisions (5,000 sampled, less 258 whose excerpt did not show the offences).
- **Accuracy (5-fold cross-validation, all categories together):** logistic regression 89.1% precision and 80.9% recall; gradient boosting 87.4% and 83.1%. Homicide, sexual offences and drugs score about 95% and 93%. Weapons and "other" are the weakest.
- **To retrain:** `.venv\Scripts\python.exe -X utf8 scripts\evaluation\evaluate_offences.py`

The dataset's main offence columns, and its sentence, penalty and mitigating-factor columns, do not come from a model. They come from an AI reading of every decision, saved in `data/labels/decision_labels.csv` (sections 9 and 10 of METHODOLOGY.md).
