export const meta = {
  name: 'classify-appeals',
  description: 'Readers say what each appeal court did with the systemic factors, to pick which appeals belong on the site',
  phases: [{ title: 'Classify', detail: 'one reader per file of 5 appeal decisions', model: 'sonnet' }],
}
const W = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\scripts\\site\\work'
const pad = n => String(n).padStart(2, '0')
const PROMPT = `You are classifying Canadian criminal APPEAL decisions about sentence for a research website about Gladue and other systemic factors in sentencing (Indigenous background, residential schools, colonialism, intergenerational trauma, anti-Black racism, other racism). Read each decision yourself; do not write code.

The input file holds up to 5 decisions. Each starts with \`===== CASE A001 =====\`, a line of details, then the decision text (the whole text, or its opening, the closing and the paragraphs about systemic factors). Follow the majority; ignore any dissent.

For each decision decide:
- appellant: who appealed the sentence: "offender", "crown", "both", or "unclear".
- category, exactly one of:
  corrected - the appeal court found that the systemic factors were NOT properly considered, were given too little weight, or were misapplied by the sentencing judge (or the judge failed to get a Gladue report or IRCA, or wrongly held them irrelevant), and the appeal court itself gave them effect: it reduced the sentence, substituted a non-custodial or shorter sentence, or sent the case back for that reason.
  crown_appeal_dismissed - the Crown appealed a sentence in which the judge gave effect to systemic factors, and the appeal court dismissed the appeal or otherwise left that lighter sentence in place, approving the judge's treatment of the factors.
  upheld_considered - the offender appealed, and the appeal court dismissed the appeal (or changed only something unrelated) because the judge had properly considered the systemic factors, or because they did not justify a lower sentence.
  increased - the appeal court increased the sentence (usually on a Crown appeal), even if it mentions the systemic factors.
  reduced_other - the appeal court reduced or changed the sentence for reasons that are NOT about the systemic factors (for example a mistake in credit for pre-sentence custody, parity with a co-accused, a legal error unrelated to the factors), even if it mentions them.
  other - none of these fits.
- reason: at most 20 words saying what the appeal court did with the systemic factors.

OUTPUT: JSON Lines, one object per decision, one line each:
{"id":"A001","appellant":"offender","category":"corrected","reason":"..."}
Inside strings never use a double quotation mark and no line breaks.

RULES: Read the whole file (in parts with offset/limit). Every decision gets exactly one line. Write the output file with the Write tool (overwrite if it exists). Reply with one short line.`
const bdir = args.tag ? `batches_${args.tag}` : 'batches'
const rdir = args.tag ? `raw_${args.tag}` : 'raw'
const files = Array.from({ length: args.to - args.from + 1 }, (_, i) => args.from + i)
const res = await parallel(files.map(b => () =>
  agent(`${PROMPT}\n\nINPUT: ${W}\\${bdir}\\appeal_${pad(b)}.txt\nOUTPUT: ${W}\\${rdir}\\appeal_${pad(b)}.jsonl`,
        { label: `classify:${pad(b)}`, phase: 'Classify', model: 'sonnet' })))
const failed = files.filter((b, i) => !res[i])
log(`${files.length - failed.length} of ${files.length} files done; failed: ${failed.join(', ') || 'none'}`)
return { failed }
