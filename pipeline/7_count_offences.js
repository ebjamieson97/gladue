export const meta = {
  name: 'count-offences',
  description: 'Readers record how many counts (offences) the offender is sentenced on in each decision',
  phases: [{ title: 'Count', detail: 'one reader per file of 20 decisions', model: 'sonnet' }],
}
// args: {"from": 1, "to": N} for the original round, or {"tag": "TAG", "from": 1, "to": N} for an update
const L = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\data\\labels'
const pad = n => String(n).padStart(3, '0')
const bdir = args.tag ? `count_batches_${args.tag}` : 'count_batches'
const rdir = args.tag ? `count_raw_${args.tag}` : 'count_raw'
const PROMPT = `You are reading Canadian criminal sentencing decisions for a research dataset. Careful, consistent answers matter more than speed. Read each case yourself; do not write code.

Each case starts with \`===== CASE C00001 =====\`, a line of details, then the decision (FULL TEXT, or its OPENING, PASSAGES ABOUT COUNTS OR CONVICTIONS, and CLOSING).

For each case record:
- counts: the NUMBER of separate counts (offences) for which the offender is sentenced in this decision, as an integer.
  - Count every count that receives a sentence, including counts with concurrent sentences, suspended sentences or sentences of time served.
  - Do NOT count charges that were stayed (including Kienapple stays), dismissed, acquitted, withdrawn, or only taken into account under s. 725.
  - For an appeal, count the counts covered by the sentence being reviewed.
  - If several offenders are sentenced, count only the first-named offender's counts.
  - If the text shows only that there was more than one count but not how many, give your best lower bound and confidence LOW.
  - If the text gives no basis at all, write null.
- confidence: HIGH or LOW.
- note: at most 12 words (for example "3 counts; 2 stayed", or empty).

OUTPUT: JSON Lines, one object per case, one line each:
{"id":"C00001","counts":3,"confidence":"HIGH","note":""}
Inside strings never use a double quotation mark and no line breaks.
RULES: Read the whole file (in parts with offset/limit). Every case gets exactly one line. You MUST write the output file with the Write tool (overwrite if it exists). Reply with one short line.`
const files = Array.from({ length: args.to - args.from + 1 }, (_, i) => args.from + i)
const res = await parallel(files.map(b => () =>
  agent(`${PROMPT}\n\nINPUT: ${L}\\${bdir}\\count_${pad(b)}.txt\nOUTPUT: ${L}\\${rdir}\\count_${pad(b)}.jsonl`,
        { label: `count:${pad(b)}`, phase: 'Count', model: 'sonnet' })))
const failed = files.filter((b, i) => !res[i])
log(`${files.length - failed.length} of ${files.length} files done; failed: ${failed.join(', ') || 'none'}`)
return { failed }
