export const meta = {
  name: 'check-direction',
  description: 'Check that each reasons picture shows a systemic factor treated as MITIGATING, and flag highlights that say the opposite',
  phases: [
    { title: 'Check', detail: 'one Sonnet reader per file of 15 decisions', model: 'sonnet' },
    { title: 'Verify', detail: 'Opus re-reads every flagged decision', model: 'opus' },
  ],
}
const W = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\case_extracts\\work'
const pad = n => String(n).padStart(2, '0')
const TASK = `This website shows Canadian sentencing decisions in which the court treated a SYSTEMIC FACTOR (Gladue factors, the offender's Indigenous background, residential schools, colonialism, intergenerational trauma, anti-Black racism, systemic racism and similar) as MITIGATING: it reduced the offender's moral culpability, or lowered or shaped the sentence. Each case has a picture of the court's reasons with some phrases highlighted in yellow.

Each case starts with \`===== CASE D001 =====\`, lists its numbered HIGHLIGHTs, then the PARAGRAPHS in the picture.

For each case decide two things.

1. "overall": what the court concludes in these paragraphs about the systemic factor:
   - "mitigating": the court treats it as reducing culpability or the sentence, even partly or modestly (for example "his Aboriginal background, with his other circumstances, warrants a sentence at the low end of the range", or it chooses a conditional sentence or healing lodge because of it). This holds even if the court ALSO says the factor's weight is limited.
   - "not_mitigating": the court says plainly that the factor does NOT mitigate here: little or no link to the offence and no reduction, no weight given, it does not reduce moral culpability, or it is outweighed so that it changes nothing. Also use this when the passage only shows the court rejecting or disregarding the factor.
   - "unclear": the paragraphs never say what effect the factor had.
2. "drop": the numbers of the highlights that say the OPPOSITE of mitigation: that the factor is not mitigating, carries little or no weight, has little evidence or no link to the offence, does not reduce culpability, or is outweighed. A highlight that only states the law or a principle is NOT dropped. Never drop a highlight because it is merely weak; drop it only if it argues against the factor.`

const READ = `You are checking pictures for that website. Read each case yourself; do not write code.

${TASK}

OUTPUT: JSON Lines, one object per case, one line each:
{"id":"D001","overall":"mitigating","drop":[2],"reason":"at most 20 words"}
Use "drop":[] when nothing should be removed. Inside strings never use a double quotation mark and no line breaks.
RULES: Read the whole file (in parts with offset/limit). Every case gets exactly one line. You MUST write the output file with the Write tool (overwrite). Then return the ids of every case where overall is not "mitigating" or drop is not empty.`

const VERIFY = `You are the second, final reader for that website, checking one case that the first reader flagged. Read it yourself; do not write code. Be careful: removing a case wrongly hides a genuine example, and keeping one wrongly misleads the public.

${TASK}

OUTPUT: write a single JSON object on one line (overwrite):
{"id":"D001","overall":"mitigating","drop":[2],"reason":"at most 25 words"}
Inside strings never use a double quotation mark. You MUST write the output file with the Write tool. Reply with one short line.`

const FLAGGED = { type: 'object', properties: { flagged: { type: 'array', items: { type: 'string' } } }, required: ['flagged'] }
// args: {"to": N} for the original round, or {"tag": "TAG", "to": N} for an update (files TAG_direction_NN)
const pre = args.tag ? `${args.tag}_direction` : 'direction'
const files = Array.from({ length: args.to }, (_, i) => i + 1)
const res = await pipeline(files,
  b => agent(`${READ}\n\nINPUT: ${W}\\${pre}_batches\\${pre}_${pad(b)}.txt\nOUTPUT: ${W}\\${pre}_raw\\${pre}_${pad(b)}.jsonl`,
             { label: `check:${pad(b)}`, phase: 'Check', model: 'sonnet', schema: FLAGGED }),
  (r, b) => parallel((r.flagged || []).map(id => () =>
    agent(`${VERIFY}\n\nCASE: ${id} in the file ${W}\\${pre}_batches\\${pre}_${pad(b)}.txt (find the line \`===== CASE ${id} =====\` and read to the next case)\nOUTPUT: ${W}\\${pre}_verify\\${id}.json`,
          { label: `verify:${id}`, phase: 'Verify', model: 'opus' }).then(() => id))))
const failed = files.filter((b, i) => !res[i])
const flagged = res.filter(Boolean).flat().filter(Boolean)
log(`${files.length - failed.length} of ${files.length} files done; ${flagged.length} cases verified; failed files: ${failed.join(', ') || 'none'}`)
return { failed, flagged }
