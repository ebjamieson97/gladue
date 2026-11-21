# Systemic Factors Casebook

A static website for browsing sentencing decisions where the court weighed a systemic factor, such as
Gladue factors, residential schools or anti-Black racism. The "Random case" button shows the offence on
the left and the court's reasons on the right.

## Build

From the project folder:

```
.venv\Scripts\python.exe -X utf8 scripts\site\build_site.py
```

This copies the extract pictures and writes `site/cases.js`. It includes only the decisions where the
court plainly states the factor's effect (`extract_conclusion_clear` = Y in `sentencing_data/index.csv`),
and of those:

- **Every trial-court sentencing.**
- **Only the appeals where the appeal court found the systemic factors were not properly considered and
  corrected the sentence** ("corrected").

- **Two kinds of appeal that upheld the sentence**, but only when the two pictures describe the crime
  **and** at least one specific systemic factor in the offender's life:
  - the offender's appeal was dismissed because the factors had already been considered
    ("upheld_considered");
  - the Crown's appeal against a lenient systemic-factor sentence was dismissed
    ("crown_appeal_dismissed").

Appeals that increased the sentence or changed it for unrelated reasons are left out. AI readers
classified each appeal and checked the pictures' content:

- **Classifications:** `scripts/site/work/raw/`, made by `make_appeal_batches.py` and `pipeline/6a_classify_appeals.js`.
- **Content checks:** `scripts/site/work/check_raw/`, made by `make_check_batches.py`.

The rules are at the top of `build_site.py`.

## View locally

```
.venv\Scripts\python.exe -m http.server 8000 --directory site
```

Then open http://localhost:8000. The page must be served this way: opening `index.html` directly as a
file cannot load `cases.json`.

- **Keys:** R or Space shows a random case; ← goes back.
- **Links to one case:** each case has its own link, for example `http://localhost:8000/#2025-NSSC-426`.

## Publish on GitHub Pages (later)

The `site/` folder is self-contained, about 65 MB.

1. Put the project in a GitHub repository.
2. Publish `site/` with a Pages workflow, or copy its contents to a `gh-pages` branch.
3. In the repository settings, turn on Pages for that branch.

**Before publishing,** check:
- **Victims' names:** the crime pictures use them as the decisions do.
- **Sexual offences:** about 124 of the cases are sexual offences, and their crime pictures contain the
  court's description.
- **Quality:** the pictures were chosen by AI readers, so spot-check them.
