export const meta = {
  name: 'adjudicate-systemic-factors',
  description: 'A third reader settles decisions where the two readings of systemic mitigating factors disagree',
  phases: [{ title: 'Adjudicate', detail: 'Claude Opus reads longer text for 250 disputed decisions', model: 'opus' }],
}
const ROOT = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\data\\labels'
const pad = n => String(n).padStart(2, '0')
const PROMPT = `You are reading Canadian criminal sentencing decisions for a research dataset. Careful, consistent answers matter more than speed. Read each item yourself and judge it; do not write code or scripts to do the work.

The input file holds about 8 items. An item starts with a line like \`===== ITEM S01234 =====\`, then the court, case name and length, then either the FULL TEXT or long excerpts (HEADING, OPENING, PASSAGES FROM THE MIDDLE, CLOSING).

TASK: decide how the court dealt with each factor below AS IT RELATES TO AN OFFENDER BEING SENTENCED in this decision. These are about prejudice or historical wrongs that the offender (or the offender's family or community) experienced. Follow the majority; ignore dissenting reasons.

Factors:
gladue_factors - the offender's Indigenous background and systemic factors (the Gladue / Ipeelee / s. 718.2(e) analysis)
colonialism - colonialism or colonization and its effects, named as such (displacement, loss of culture, language or land, the Sixties Scoop)
res_school - residential schools: the offender or family members attended, or their effects on the offender
intergen_trauma - intergenerational trauma, named as such
anti_black_racism - anti-Black racism affecting the offender (including Impact of Race and Culture Assessments, R. v. Morris, R. v. Anderson)
systemic_racism - systemic or overt racism or discrimination affecting the offender, other than specifically anti-Black racism
islamophobia - Islamophobia or anti-Muslim prejudice affecting the offender
white_supremacy - white supremacy as something the offender was a victim of
other_prejudice - any other prejudice the offender experienced (antisemitism, homophobia, transphobia, anti-Asian racism, religious persecution, and so on)

Codes:
M - the court treated it as MITIGATING for this offender: it reduced moral blameworthiness, was listed or accepted as a mitigating factor, or was a reason for a lower or non-custodial sentence. For an appeal, M if the appeal court does this itself, or accepts that the sentencing judge properly did.
R - the court considered it for this offender but REJECTED it or gave it no effect (no connection shown, or the seriousness of the offence outweighed it entirely).
N - MENTIONED but not weighed for this offender: quoted from other cases, a general statement of law, a description from a report with no sign the court gave it weight, or it concerns someone else.
X - not mentioned.
Be strict about M: the text must show the court giving the factor mitigating weight for this offender, not merely reciting it. But a court that says it "took into account" or "considered" the offender's Indigenous background when choosing a lower sentence or range IS giving it weight (M).

OUTPUT: JSON Lines, one object per item, one line each, keys in this order:
{"id":"S01234","gladue_factors":"M","colonialism":"X","res_school":"M","intergen_trauma":"N","anti_black_racism":"X","systemic_racism":"X","islamophobia":"X","white_supremacy":"X","other_prejudice":"X","quote":"passage copied exactly from the text that best shows the court giving weight (at most about 50 words), or empty","reason":"at most 20 words"}
Inside string values never use a double quotation mark (use a single quote instead) and no line breaks.

RULES
- Judge only from the text shown. Do not look anything up, do not open any other files, and do not search the web.
- Every item must get exactly one line. Count the "===== ITEM" lines and check your output has the same number.
- The file is large: read it in parts with offset/limit until the end.
- Write the output file with the Write tool (overwrite if it exists). Reply with one short line giving the number of lines written.`
const jobs = []
for (let b = 1; b <= 32; b++) jobs.push({ label: `adjudicate:${pad(b)}`,
  io: `INPUT: ${ROOT}\\adjudication_batches\\adjudicate_${pad(b)}.txt\nOUTPUT: ${ROOT}\\adjudication_raw\\adjudicate_${pad(b)}.jsonl` })
const res = await parallel(jobs.map(j => () => agent(`${PROMPT}\n\nFILES\n${j.io}`, { label: j.label, phase: 'Adjudicate', model: 'opus' }).then(r => r ? 1 : 0)))
const failed = jobs.filter((j, i) => !res[i]).map(j => j.label)
return { done: res.filter(Boolean).length, total: jobs.length, failed }
