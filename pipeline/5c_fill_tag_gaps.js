export const meta = {
  name: 'fill-tag-gaps',
  description: 'For each factor tag not shown in a reasons picture, pick one brief paragraph that shows it, or drop the tag',
  phases: [{ title: 'Pick', detail: 'one reader per file of 8 decisions', model: 'sonnet' }],
}
const W = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\case_extracts\\work'
const pad = n => String(n).padStart(2, '0')
const PROMPT = `You are improving extracts for a website about Gladue and other systemic factors in Canadian sentencing. Read each case yourself; do not write code.

Each decision is tagged with systemic factors (for example "Anti-Black racism", "Colonialism"), but its "court's reasons" picture does not yet show one or more of them. Each case starts with \`===== CASE G001 =====\`, lists the paragraphs already in the picture, then for each missing FACTOR the paragraphs of the decision that mention it.

For each missing factor, choose ONE paragraph to add to the picture that shows this factor in THIS offender's life or in the court's reasoning about this offender, for example "his mother was Black and raised him in a Black community in Toronto" or "the effects of colonialism on his community shaped his upbringing". Rules:
- It must be the court's own words, or a report or submission that the court explicitly accepts in that same paragraph. Not a quotation from another case, and not a general statement of law.
- Prefer the shortest paragraph that clearly shows the factor for this offender.
- Give one phrase to highlight in it, copied EXACTLY (3 to 30 words), that shows the factor.
- If no paragraph meets these rules, give paragraph null: the tag will be removed from this case.

OUTPUT: JSON Lines, one object per case, one line each, with one entry per missing factor:
{"id":"G001","add":[{"factor":"Anti-Black racism","paragraph":22,"highlight":"exact phrase"},{"factor":"Colonialism","paragraph":null,"highlight":""}]}
Inside strings never use a double quotation mark and no line breaks.
RULES: Read the whole file. Every case gets exactly one line. You MUST write the output file with the Write tool (overwrite). Reply with one short line.`
// args: {"to": N} for the original round, or {"tag": "TAG", "to": N} for an update (files TAG_gap_NN)
const pre = args.tag ? `${args.tag}_gap` : 'gap'
const files = Array.from({ length: args.to }, (_, i) => i + 1)
const res = await parallel(files.map(b => () =>
  agent(`${PROMPT}\n\nINPUT: ${W}\\${pre}_batches\\${pre}_${pad(b)}.txt\nOUTPUT: ${W}\\${pre}_raw\\${pre}_${pad(b)}.jsonl`,
        { label: `gap:${pad(b)}`, phase: 'Pick', model: 'sonnet' })))
return { failed: files.filter((b, i) => !res[i]) }
