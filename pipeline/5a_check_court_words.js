export const meta = {
  name: 'check-rationale-source',
  description: 'Check that each rationale picture highlights the court\'s own reasoning, not counsel\'s or a report\'s words',
  phases: [{ title: 'Check', detail: 'one reader per file of 15 decisions', model: 'sonnet' }],
}
const W = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\case_extracts\\work'
const pad = n => String(n).padStart(2, '0')
const PROMPT = `You are checking extracts for a research website about Gladue and other systemic factors in Canadian sentencing. Read each case yourself; do not write code.

Each case starts with \`===== CASE Q001 =====\`, then the HIGHLIGHTED PHRASES, then the paragraphs of its "court's reasons on systemic factors" picture.

The picture is meant to show the COURT'S OWN reasoning about the systemic factors. Text that sets out what defence counsel, the Crown, a Gladue report, an IRCA, a pre-sentence report or a witness argued or said is acceptable ONLY if one of the paragraphs shown has the judge explicitly accepting, adopting or agreeing with it (for example "I accept that...", "I agree with counsel...", "I adopt the report's conclusions"). A judge merely summarising or describing a submission or report, without saying they accept it, does not count.

For each case answer:
- source_ok: Y if the highlighted phrases are the court's own reasoning, or submission/report text that the judge explicitly accepts in the paragraphs shown. N if ANY highlighted phrase (other than single named terms such as Gladue or colonialism) is the words of counsel, a report or another person that the judge does not explicitly accept in the paragraphs shown.
- reason: at most 20 words; for N, say whose words were highlighted.

OUTPUT: JSON Lines, one object per case, one line each:
{"id":"Q001","source_ok":"Y","reason":"..."}
Inside strings never use a double quotation mark and no line breaks.
RULES: Read the whole file (in parts with offset/limit). Every case gets exactly one line. Write the output file with the Write tool (overwrite). Reply with one short line.`
const tag = args.tag || 'source'
const files = Array.from({ length: args.to - args.from + 1 }, (_, i) => args.from + i)
const res = await parallel(files.map(b => () =>
  agent(`${PROMPT}\n\nINPUT: ${W}\\${tag}_batches\\${tag}_${pad(b)}.txt\nOUTPUT: ${W}\\${tag}_raw\\${tag}_${pad(b)}.jsonl`,
        { label: `check:${pad(b)}`, phase: 'Check', model: 'sonnet' })))
const failed = files.filter((b, i) => !res[i])
log(`${files.length - failed.length} of ${files.length} files done; failed: ${failed.join(', ') || 'none'}`)
return { failed }
