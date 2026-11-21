# Systemic Factors Casebook

A searchable collection of Canadian criminal sentencing decisions in which a court treated a systemic factor as
mitigating. These factors include Gladue factors, residential schools, colonialism, intergenerational trauma,
anti-Black racism and systemic racism.

**Website:** https://ebjamieson97.github.io/gladue/

For each case, the site shows two passages from the decision:

- the court's description of the crime, and
- the court's reasons on the systemic factor.

Key phrases are highlighted. The site also has a catalogue of every case, a short history of Gladue sentencing, and
statistics.

## What is in this repository

| Folder | Contents |
|---|---|
| `sentencing_data/` | 10,096 sentencing decisions selected from 32,187 criminal decisions in eight courts (SCC, ONCA, BCCA, BCSC, NSCA, NSSC, NSPC, NLCA), with offences, sentences and mitigating factors. `index.csv` lists them all. |
| `data/labels/` | The AI readers' answers and the merged labels (`decision_labels.csv`) |
| `case_extracts/` | The chosen passages and highlights (`extracts.csv`) and the hand corrections (`overrides.json`) |
| `models/` | The saved logistic regressions used to select sentencing decisions |
| `scripts/` | Python scripts: data building, evaluation, extract pictures, analysis and the website |
| `pipeline/` | The Claude Code workflow files used for the AI reading steps |
| `docs/` | [METHODOLOGY.md](docs/METHODOLOGY.md) explains how the data was built and how accurate it is. [PIPELINE.md](docs/PIPELINE.md) explains how to update the data and the website. |

The website itself is on the `gh-pages` branch.

## Running it

You need Python 3.12.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r scripts\requirements.txt
.venv\Scripts\python.exe -X utf8 scripts\build_sentencing_data.py            # downloads the A2AJ files (about 2 GB)
.venv\Scripts\python.exe -X utf8 scripts\extracts\render_extracts.py         # draws the extract pictures
.venv\Scripts\python.exe -X utf8 scripts\site\build_site.py                  # builds the website into site/
.venv\Scripts\python.exe -m http.server 8000 --directory site                # open http://localhost:8000
```

To add newly published decisions, follow [docs/PIPELINE.md](docs/PIPELINE.md).

## Data source and terms of use

The court decisions come from the [A2AJ Canadian Case Law dataset](https://huggingface.co/datasets/a2aj/canadian-case-law),
published by Access to Algorithmic Justice (A2AJ).

The MIT licence in [LICENSE](LICENSE) covers only the code and the original work in this repository. It does not cover
the text of court decisions. Each decision keeps the terms set by the court that issued it; the `upstream_license`
column records these terms.

- **Courts' own terms.** Courts generally allow non-commercial reproduction of their published decisions, provided the
  source is named and the copy is not presented as official. Some courts, for example in British Columbia, require
  permission for commercial use. Check the issuing court's terms before reusing decision text for anything else.
- **Unofficial reproduction.** The passages here are unofficial reproductions and may contain errors. This project
  is not affiliated with or endorsed by any court or by A2AJ. For the official text, consult the court's own
  publication.
- **AI-generated labels.** Offences, sentences, mitigating factors and highlights were produced by AI models and then
  checked. They contain errors. Do not rely on them as legal advice or as a substitute for reading the decision.
- **Publication bans.** Decisions are reproduced as published by the courts, which anonymize them where the law
  requires. If you believe a passage should not appear here, please open an issue.

## Licence

Code: [MIT](LICENSE). Court decisions: the terms of the issuing court (see above).
