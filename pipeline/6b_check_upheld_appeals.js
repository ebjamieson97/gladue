export const meta = {
  name: 'check-upheld-appeals',
  description: 'Check that each upheld appeal on the site describes the crime and at least one specific systemic factor',
  phases: [{ title: 'Check', detail: 'one reader per file of 12 decisions', model: 'sonnet' }],
}
const W = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\scripts\\site\\work'
const PROMPT = `You are checking extracts for a research website about Gladue and other systemic factors in Canadian sentencing. Read each case yourself; do not write code.

Each case starts with \`===== CASE C001 =====\` and shows the paragraphs in its two pictures: CRIME PICTURE and SYSTEMIC FACTORS PICTURE.

For each case answer:
- crime_described: Y if the CRIME PICTURE paragraphs describe what the offender actually did (the acts of the offence, even briefly, e.g. "he stabbed the victim twice in the chest"). N if they only name the offence, discuss the sentencing range, the criminal record, risk, or procedure.
- factor_detail: Y if the SYSTEMIC FACTORS PICTURE paragraphs give at least one SPECIFIC detail of a systemic factor in THIS offender's life (for example a parent or grandparent attended residential school, raised in foster care after the Sixties Scoop, grew up on a reserve with violence and addiction, experienced anti-Black racism at school, the contents of a Gladue report or IRCA about the offender). N if they only cite Gladue or s. 718.2(e), say the offender is Indigenous, or say the factors were considered, without any specific detail about the offender's background.
- reason: at most 15 words.

OUTPUT: JSON Lines, one object per case, one line each:
{"id":"C001","crime_described":"Y","factor_detail":"N","reason":"..."}
Inside strings never use a double quotation mark and no line breaks.
RULES: Read the whole file. Every case gets exactly one line. Write the output file with the Write tool (overwrite). Reply with one short line.`
// args: {"to": N} for the original round, or {"tag": "TAG", "to": N} for an update
const bdir = args.tag ? `check_batches_${args.tag}` : 'check_batches'
const rdir = args.tag ? `check_raw_${args.tag}` : 'check_raw'
const pad = n => String(n).padStart(2, '0')
const files = Array.from({ length: args.to }, (_, i) => i + 1)
const res = await parallel(files.map(b => () =>
  agent(`${PROMPT}\n\nINPUT: ${W}\\${bdir}\\check_${pad(b)}.txt\nOUTPUT: ${W}\\${rdir}\\check_${pad(b)}.jsonl`,
        { label: `check:${pad(b)}`, phase: 'Check', model: 'sonnet' })))
return { failed: files.filter((b, i) => !res[i]) }
