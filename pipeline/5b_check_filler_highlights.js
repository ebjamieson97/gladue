export const meta = {
  name: 'check-filler-highlights',
  description: 'Flag filler highlights in the crime pictures on the site',
  phases: [{ title: 'Check', detail: 'one reader per file of 15 decisions', model: 'sonnet' }],
}
const W = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\case_extracts\\work'
const pad = n => String(n).padStart(2, '0')
const PROMPT = `You are checking highlights in extracts for a website about Canadian sentencing decisions. Read each case yourself; do not write code.

Each case starts with \`===== CASE F001 =====\`, lists its numbered HIGHLIGHTs, then the PARAGRAPHS of its crime picture. The highlights should mark only the genuinely serious facts of the offence: violent acts, weapons, threats, danger to others, and harm to victims (injuries, fear, death). They should NOT mark filler: incidental or investigative details, such as what police observed, how a stop or search began, where someone was standing or sitting, background before the offence, or procedural facts.

For each case list the numbers of the highlights that are FILLER and should be removed. Be conservative: drop a highlight only if it is clearly not a serious act or harm. Weapons found, drugs trafficked in a drug case, and the offender's key acts in the offence are NOT filler. Never drop every highlight in a case; if all look weak, keep the most serious one.

OUTPUT: JSON Lines, one object per case, one line each:
{"id":"F001","drop":[2],"reason":"at most 15 words, or empty"}
Use "drop":[] when nothing should be removed. Inside strings never use a double quotation mark and no line breaks.
RULES: Read the whole file (in parts with offset/limit). Every case gets exactly one line. You MUST write the output file with the Write tool (overwrite). Reply with one short line.`
// args: {"to": N} for the original round, or {"tag": "TAG", "to": N} for an update (files TAG_filler_NN)
const pre = args.tag ? `${args.tag}_filler` : 'filler'
const files = Array.from({ length: args.to }, (_, i) => i + 1)
const res = await parallel(files.map(b => () =>
  agent(`${PROMPT}\n\nINPUT: ${W}\\${pre}_batches\\${pre}_${pad(b)}.txt\nOUTPUT: ${W}\\${pre}_raw\\${pre}_${pad(b)}.jsonl`,
        { label: `check:${pad(b)}`, phase: 'Check', model: 'sonnet' })))
const failed = files.filter((b, i) => !res[i])
log(`${files.length - failed.length} of ${files.length} files done; failed: ${failed.join(', ') || 'none'}`)
return { failed }
