# Pipeline: updating the sentencing data and the website

This file tells you how to update everything when new court decisions are published:

- the sentencing dataset (`sentencing_data/`)
- the extract pictures (`case_extracts/`)
- the website (`site/`)

It is written so that an AI agent, or a person, can follow it top to bottom. Part A is the update procedure. Part B
records how the project was first built, for reference only.

The detailed methods and accuracy figures are in [METHODOLOGY.md](METHODOLOGY.md).

---

## How to run things

- **Folder.** Run every command from the project folder.
- **Python.** Use `.venv\Scripts\python.exe -X utf8 <script>`.
- **AI steps** are Claude Code workflow files in [pipeline/](../pipeline/). Run one with the Workflow tool:
  `Workflow({scriptPath: "<project>/pipeline/<file>.js", args: {...}})`.
  - **Permission mode.** Use Claude Code's *manual approval* mode: auto mode has blocked these workflows before.
  - **Usage limits.** If a run stops because of a usage limit, nothing is lost. Every answer already written is
    kept, and re-running the same step on the same TAG prepares only what is still missing.
  - **What the readers see.** The instructions inside each `.js` file are the exact text the AI readers see. Do not
    change them casually; the website's quality rules live there.
- **TAG.** Every update gets a short name, its TAG: letters, digits and underscores only, for example `upd2027a`. Use
  the same TAG in every step. Each step writes its work under that TAG, so earlier work is never overwritten.
- **Read each step's printed counts before moving on.** If a step says "Nothing new to do", skip its AI part.

---

## Part A: updating with new data (run in order)

### Step 0: download the new data and select sentencing decisions (no AI)

```
.venv\Scripts\python.exe -X utf8 scripts\build_sentencing_data.py
```

What it does:

1. **Download.** Fetches the newest A2AJ file for each court from Hugging Face (`a2aj/canadian-case-law`). Courts
   whose file has not changed are skipped.
2. **Select sentencing decisions.** Scores every criminal decision with the saved logistic regression,
   [models/sentencing_logistic_regression.json](../models/sentencing_logistic_regression.json). A decision with
   probability 0.5 or more is a sentencing decision. **This is how new decisions are found without AI reading them.**
3. **Mark IMPOSES decisions.** A sentencing decision from a trial court whose heading shows no appeal is marked
   `imposes`.
4. **Fill in offence categories for unread decisions.** Uses the saved offence models,
   [models/offence_logistic_regression.json](../models/offence_logistic_regression.json), as a stand-in until the
   decision has been read.
5. **Add everything already known.** Joins the AI readings (`data/labels/decision_labels.csv`), the extract
   pictures (`case_extracts/extracts.csv`) and the hand corrections.

New decisions come out with `ai_read = false` and blank reading columns. The script prints how many decisions were
selected per court. `sentencing_data/build_info.json` records the A2AJ revision that was used.

**Do not retrain the models during an update.** They were trained on 6,084 labelled decisions (sentencing) and 4,742
(offences); see METHODOLOGY.md sections 3–8.

### Step 1: prepare the new decisions for reading (no AI)

```
.venv\Scripts\python.exe -X utf8 scripts\evaluation\make_full_read_batches.py --new --tag TAG
```

This writes only the sentencing decisions that have no reading yet to `data/labels/full_read_batches_TAG/`
(`read_0001.txt` …), about 10 decisions per file. It prints the number of files, N. If it prints "No unread
decisions", skip to Step 3.

### Step 2: AI reading of the new decisions

```
Workflow pipeline/2_full_read.js   args: {"tag": "TAG", "from": 1, "to": N}
```

Each reader records, for each decision:

- offences
- outcome
- prison time and other penalties
- any healing lodge or treatment placement
- an exact sentence quote
- the systemic factors (Gladue and so on), and the ordinary mitigating factors

Answers go to `data/labels/full_read_raw_TAG/`. Then merge and check:

```
.venv\Scripts\python.exe -X utf8 scripts\evaluation\merge_full_read.py --write-missing
```

- **Read the report.** Expect 0 missing, and sentence quotes found word for word in about 99% of decisions.
- **Skipped decisions.** If it says it wrote follow-up files (`read_9001.txt` …), run
  `Workflow pipeline/2_full_read.js args: {"ranges": [[9001, LAST]]}` with no tag, then run the merge again.
- **Rebuild the dataset** so the new readings appear:

```
.venv\Scripts\python.exe -X utf8 scripts\build_sentencing_data.py --skip-download
```

### Step 3: extract pictures for new systemic-factor cases

These are cases where a systemic factor (Gladue factors, residential schools, anti-Black racism and so on) was
treated as mitigating. Prepare them, run the readers, then draw the pictures:

```
.venv\Scripts\python.exe -X utf8 scripts\extracts\make_extract_batches.py --new --tag TAG
Workflow pipeline/4_pick_extracts.js   args: {"from": 1, "to": N, "batches": "batches_TAG", "prefix": "TAG", "out": "raw_TAG"}
.venv\Scripts\python.exe -X utf8 scripts\extracts\render_extracts.py
```

- **Picking.** The readers pick the crime passage, the court's reasons on the systemic factors, and the phrases to
  highlight.
- **Drawing.** `render_extracts.py` draws a wide and a phone-width PNG of each passage into
  `case_extracts/<court>/`, and lists them in `case_extracts/extracts.csv`.
- **Skipped decisions.** If `render_extracts.py` lists decisions "not picked yet", re-run the workflow for those file
  numbers only.

### Step 4: quality checks on the new pictures

Run all four checks, in order. Each one prepares only pictures that have not been checked before.

**4a. Court's own words.** The reasons picture must show the judge's own reasoning. Counsel's or a report's words
count only when the judge explicitly accepts them in the picture.

```
.venv\Scripts\python.exe -X utf8 scripts\extracts\make_source_check_batches.py --new --tag TAG
Workflow pipeline/5a_check_court_words.js   args: {"tag": "TAG_source", "from": 1, "to": N}
```

Cases that fail are hidden from the website automatically. To try to fix them instead, list the failing citations
and re-pick them as a new round named `TAG_fix` (it sorts after TAG, so it replaces the earlier picks). Then check
that round as well:

```
.venv\Scripts\python.exe -X utf8 scripts\extracts\make_extract_batches.py --tag TAG_fix --citations "2027 BCSC 1" "2027 NSSC 2"
Workflow pipeline/4_pick_extracts.js   args: {"from": 1, "to": N, "batches": "batches_TAG_fix", "prefix": "TAG_fix", "out": "raw_TAG_fix"}
.venv\Scripts\python.exe -X utf8 scripts\extracts\make_source_check_batches.py --new --tag TAG_fix
Workflow pipeline/5a_check_court_words.js   args: {"tag": "TAG_fix_source", "from": 1, "to": N}
```

**4b. No filler highlights.** Crime highlights must be serious acts or harm, not incidental or investigative details.

```
.venv\Scripts\python.exe -X utf8 scripts\extracts\make_filler_check_batches.py --new --tag TAG
Workflow pipeline/5b_check_filler_highlights.js   args: {"tag": "TAG", "to": N}
.venv\Scripts\python.exe -X utf8 scripts\extracts\apply_filler_check.py --tag TAG
```

**4c. Every tag visible.** Each factor tag shown on the website, such as "Anti-Black racism", must be visible in the
reasons picture. The readers add a short paragraph showing it, or the tag is dropped.

```
.venv\Scripts\python.exe -X utf8 scripts\extracts\find_tag_gaps.py --new --tag TAG
.venv\Scripts\python.exe -X utf8 scripts\extracts\make_tag_gap_batches.py --tag TAG
Workflow pipeline/5c_fill_tag_gaps.js   args: {"tag": "TAG", "to": N}
.venv\Scripts\python.exe -X utf8 scripts\extracts\apply_tag_gaps.py --tag TAG
```

**4d. Mitigating, not the opposite.** Run this last, after 4c has added its highlights. Every reasons picture must show
the court treating the systemic factor as mitigating, and no highlight may say the opposite (for example "there is
little evidence that his Aboriginal background lessens his culpability"). The highlights must give the view of the
court deciding the case: on an appeal, a trial judge's words are highlighted only when the appeal court agrees with
them and they treat the factor as mitigating. Sonnet readers check each picture; Opus
re-reads every case they flag, and its answer is final.

```
.venv\Scripts\python.exe -X utf8 scripts\extracts\make_direction_check_batches.py --new --tag TAG
Workflow pipeline/5d_check_direction.js   args: {"tag": "TAG", "to": N}
.venv\Scripts\python.exe -X utf8 scripts\extracts\apply_direction_check.py
```

- **Highlights that argue against the factor, or give someone else's view** are removed (written to `overrides.json`).
- **Highlights that run on into a caveat** ("…as an infant, although that is not conclusive…") are trimmed before
  it, and **statements of principle** about not perpetuating structural inequities that were missed are added. Phrases
  listed under `keep_rationale_highlights` in `overrides.json` are never removed.
- **After changing these rules,** re-check every picture on the site as a new round, which replaces the earlier
  answers: `make_direction_check_batches.py --recheck --tag NAME`, then the workflow with `{"tag": "NAME", "to": N}`.
- **Cases where the court did not treat the factor as mitigating, or never states its effect ("unclear")** are
  listed by the script and handled automatically through `case_extracts/work/direction_verdicts.json`:
  - they are hidden from the website (`build_site.py`), and
  - they stop counting as "systemic factor treated as mitigating" in the dataset (`build_sentencing_data.py` turns
    their M codes into R or N), so the Statistics page and the models follow.

Checks 4b, 4c and 4d write their results to [case_extracts/overrides.json](../case_extracts/overrides.json), the file of
hand and automatic corrections. Then redraw the pictures and rebuild the dataset:

```
.venv\Scripts\python.exe -X utf8 scripts\extracts\render_extracts.py
.venv\Scripts\python.exe -X utf8 scripts\build_sentencing_data.py --skip-download
```

### Step 5: decide which new appeal decisions belong on the website

**5a. Classify new appeals.** For each new appeal, the reader records what the appeal court did with the systemic
factors.

```
.venv\Scripts\python.exe -X utf8 scripts\site\make_appeal_batches.py --new --tag TAG
Workflow pipeline/6a_classify_appeals.js   args: {"tag": "TAG", "from": 1, "to": N}
```

**5b. Check the upheld ones.** For appeals that upheld the sentence, a reader checks that the pictures describe the
crime and at least one specific systemic factor.

```
.venv\Scripts\python.exe -X utf8 scripts\site\make_check_batches.py --new --tag TAG
Workflow pipeline/6b_check_upheld_appeals.js   args: {"tag": "TAG", "to": N}
```

### Step 6: rebuild and view the website (no AI)

```
.venv\Scripts\python.exe -X utf8 scripts\site\build_site.py
.venv\Scripts\python.exe -m http.server 8000 --directory site      # then open http://localhost:8000
```

`build_site.py` prints how many decisions it considered, and why each one was or was not included. A case is on the
website when all of these hold:

- **Conclusion.** The court plainly states the systemic factor's effect (`extract_conclusion_clear = Y`).
- **Pictures.** Both pictures exist.
- **Court's own words.** The reasons picture passed the court's-own-words check.
- **Mitigating.** The direction check (4d) found the court treated the factor as mitigating.
- **Trial or appeal.** It is either:
  - a trial-court sentencing, or
  - an appeal where the systemic factors were corrected, or
  - an upheld appeal whose pictures describe the crime and a specific factor.

The rules are at the top of [scripts/site/build_site.py](../scripts/site/build_site.py).

**Publish the website.** The live site is the `gh-pages` branch of https://github.com/ebjamieson97/gladue, which
holds the contents of `site/` and nothing else. After checking the site locally, commit the data changes on `main`,
then publish `site/`:

```
git add -A
git commit -m "Update TAG"
git push origin main
.venv\Scripts\python.exe -X utf8 scripts\site\publish_site.py      # copies site/ to the gh-pages branch and pushes it
```

### Optional (not yet run): count the offences sentenced

The sentence-length models control for offence categories but not for the number of counts sentenced, because that is not
recorded. A reading step to add it is ready but has not been run on the full set:

```
.venv\Scripts\python.exe -X utf8 scripts\analysis\make_count_batches.py            # first time: all decisions in the length models
Workflow pipeline/7_count_offences.js   args: {"from": 1, "to": N}
```

- **What it records.** For each decision in the length models (adult sentences with a fixed jail term, about 6,700),
  the reader gives the number of counts sentenced. Concurrent counts are included; stayed, dismissed, acquitted and
  withdrawn counts are not. Answers go to `data/labels/count_raw/`.
- **Status.** A pilot on the first 3 files (60 decisions) is already in `count_raw/` and looked accurate.
- **Updates.** Later updates use `--tag TAG` on the script and `{"tag": "TAG", ...}` on the workflow, which reads only
  decisions without a count.
- **Still to write.** A merge script (`count_raw` → `data/labels/offence_counts.csv`), and a version of the regression in
  `scripts/analysis/sentence_regression.py` that uses the count in place of the more-than-one-offence indicator.

### Step 7: record the update

Add a row to the update log below. If the numbers changed noticeably, update the counts quoted in METHODOLOGY.md
sections 10 and 10.8.

| Date | TAG | A2AJ revision | New sentencing decisions | New systemic-factor cases | Cases on website |
|---|---|---|---|---|---|
| 2026-11-21 | (original build) | 4e85f2882e506177ee08e1286292a52af3b0fe6b | 10,096 total | 586 total (602 before the direction check, 4d) | 386 |

---

## What the saved models and rules do

| Item | Used for | File |
|---|---|---|
| Sentencing logistic regression | Deciding which criminal decisions are sentencing decisions (probability ≥ 0.5) | `models/sentencing_logistic_regression.json` |
| IMPOSES rule | Trial court, and the heading shows no appeal | in `scripts/build_sentencing_data.py` |
| Offence logistic regressions | Offence categories only for decisions not yet read, or whose offences the reader could not tell | `models/offence_logistic_regression.json` |
| Gladue reference rule | `references_gladue`: the text mentions Gladue, Ipeelee or 718.2(e) | `scripts/enrichment_patterns.py` |
| Rules v2.0 | Kept for comparison only (`rules_v2_tier`); not used to select | `scripts/build_sentencing_data.py` |

Everything else (offences, sentences, mitigating factors, pictures, website checks) comes from the AI steps above.

## Where things are

| Folder or file | Contents |
|---|---|
| [pipeline/](../pipeline/) | The AI instruction files used in updates (steps 2, 4, 5a–d, 6a–b; 7 is the optional offence count) |
| [pipeline/archive/](../pipeline/archive/) | AI instructions used once in the original build (Part B) |
| `scripts/` | All Python scripts |
| `data/labels/` | AI answers and merged label files (`decision_labels.csv` is the main one) |
| `case_extracts/` | Extract pictures, `extracts.csv`, `overrides.json`, and the readers' work in `work/` |
| `sentencing_data/` | The dataset: decisions by province and court, and `index.csv` |
| `site/` | The website, built by `scripts/site/build_site.py` from the page files in `scripts/site/` |
| `models/` | The saved statistical models |

**Not in git** (see `.gitignore`): `data/raw/` (the A2AJ downloads), the `*batches*` folders (decision text prepared
for the readers), the extract PNGs and `site/`. All of them are re-made by the scripts. On a fresh copy of the
repository, run `scripts\build_sentencing_data.py` (download), then `scripts\extracts\render_extracts.py` (pictures),
before Step 0. The readers' answers (`*_raw` folders) are kept in git, so nothing has to be read again.

---

## Part B: how the project was first built (reference only; do not re-run)

1. **Data.** Downloaded A2AJ for 8 courts: 32,187 criminal decisions (METHODOLOGY.md section 1).
2. **Labelled samples.** Drew two samples of 3,200 decisions, one stratified and one random (6,084 different
   decisions). AI readers labelled each as imposes a sentence, reviews one, related, or not sentencing.
   - Instructions: `pipeline/archive/1_label_sentencing_samples*.js`.
3. **Choosing the selection method.** Compared written rules and statistical models with 5-fold cross-validation.
   The logistic regression was adopted and saved (`scripts/evaluation/evaluate_3200.py`; METHODOLOGY.md sections
   3–7). It selected 10,096 sentencing decisions.
4. **Offence models (now only a fallback).** Trained on 5,000 AI-labelled decisions
   (`scripts/evaluation/evaluate_offences.py`; section 8). A first, keyword-only review of systemic factors read
   1,677 decisions.
   - Instructions: `pipeline/archive/superseded_label_offences_and_mitigation.js`.
5. **Full reading of all 10,096 decisions** (`pipeline/2_full_read.js`; section 10). A second model re-read 150 of
   them. Claude Opus settled 250 disagreements with the keyword-only review.
   - Instructions: `pipeline/archive/2b_adjudicate_systemic_factors.js`.
6. **Extract pictures** for the 602 systemic-factor cases (section 10.8). The instructions were refined over several
   pilot rounds of review by the project author, then checked for the court's own words, filler highlights and tag
   visibility, with hand fixes in `overrides.json`.
7. **Website.** Appeals classified and checked; site rules as in Step 6.
