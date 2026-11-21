export const meta = {
  name: 'label-offences-and-mitigation',
  description: 'Label offence categories for 5,000 sentencing decisions and mitigating factors for 1,677 candidates, plus cross-model audits',
  phases: [
    { title: 'Offences', detail: '114 labellers, two files each' },
    { title: 'Mitigating', detail: '56 labellers, three files each' },
    { title: 'Audit', detail: 'second model re-labels 100 + 60 decisions', model: 'opus' },
  ],
}
const ROOT = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\data\\labels'
const pad = n => String(n).padStart(3, '0')

const COMMON = `RULES
- Judge only from the excerpt. Do not look anything up, do not open any other files, and do not search the web.
- Every item in a file must get exactly one row. Before you finish, count the "===== ITEM" lines in each input file and check your CSV has the same number of rows.
- Read each file completely; if a file is too large for one read, read it in parts with offset/limit.
- Write each CSV with the Write tool. When done, reply with one short line per file giving the number of rows. Nothing else.`

const OFFENCE = `You are labelling excerpts of Canadian criminal sentencing decisions for a research dataset. Careful, consistent labels matter more than speed.

Each input file holds about 22 items. An item starts with a line like \`===== ITEM F1234 =====\`, then the court, case name and length, then excerpts: the end of the HEADING, the OPENING of the reasons, PASSAGES ABOUT CHARGES OR CONVICTIONS, and the CLOSING. Short decisions are given as FULL TEXT.

TASK: for each item, list every category of offence FOR WHICH A SENTENCE IS BEING IMPOSED OR REVIEWED in this decision. Include all counts and all offenders sentenced in the decision. Do NOT count offences that appear only in the offender's prior record, in other cases cited for comparison, or in charges that were clearly acquitted, stayed or withdrawn.

Categories (use these exact codes):
homicide - murder, attempted murder, manslaughter, infanticide, criminal negligence causing death (not driving offences causing death)
sexual - sexual assault, sexual interference, sexual exploitation, invitation to sexual touching, child pornography, luring, voyeurism, incest, historical offences such as rape or indecent assault
assault - non-sexual assault of any level (assault, with a weapon, causing bodily harm, aggravated), assaulting a peace officer, unlawfully causing bodily harm
robbery - robbery, armed robbery
kidnapping - kidnapping, forcible or unlawful confinement, abduction, hostage taking, human trafficking
break_enter - break and enter, home invasion, being unlawfully in a dwelling
theft_fraud - theft, fraud, possession of stolen property or proceeds of crime, forgery, identity theft, money laundering
drugs - trafficking, possession for the purpose of trafficking, production, importing or possession of drugs
weapons - firearms or weapons offences (possession, discharging, pointing, trafficking in weapons); not merely "assault with a weapon", which is assault
driving - impaired or over-80 driving, dangerous driving or operation, driving while prohibited, failing to stop or remain, refusing a breath sample, including when they cause death or bodily harm
other - any other offence being sentenced: breaches of court orders, threats, criminal harassment, mischief, arson, obstruction, perjury, contempt, extortion, regulatory offences, and so on

For each item give:
- categories: the codes that apply, separated by semicolons (for example sexual;assault). Write none if the excerpt does not show what the offences are.
- confidence: HIGH or LOW. Use LOW when the excerpt leaves the offences unclear or incomplete.
- note: the offences in at most 12 words. Do not use commas or quotation marks.

OUTPUT: for each input file write one CSV. First line exactly: id,categories,confidence,note
Then one row per item in order, for example: F1234,sexual;assault,HIGH,Sexual assault and assault causing bodily harm

${COMMON}`

const MITIGATION = `You are labelling excerpts of Canadian criminal sentencing decisions for a research dataset. Careful, consistent labels matter more than speed.

Each input file holds about 10 items. An item starts with a line like \`===== ITEM M1234 =====\`, then the court, case name and length, then excerpts: the end of the HEADING, the OPENING of the reasons, PASSAGES MENTIONING THE KEYWORDS, PASSAGES ABOUT MITIGATING FACTORS, and the CLOSING. Short decisions are given as FULL TEXT.

TASK: decide, for each factor below, how the court dealt with it AS IT RELATES TO THE OFFENDER BEING SENTENCED in this decision. The factors are about prejudice or historical wrongs that the offender (or the offender's family or community) experienced.

Factors:
gladue_factors - the offender's Indigenous background and systemic factors (the Gladue / Ipeelee / s. 718.2(e) analysis)
colonialism - colonialism or colonization and its effects, named as such (displacement, loss of culture, language or land, the Sixties Scoop)
res_school - residential schools: the offender or family members attended, or their effects on the offender
intergen_trauma - intergenerational trauma, named as such
anti_black_racism - anti-Black racism affecting the offender (including Impact of Race and Culture Assessments, R. v. Morris, R. v. Anderson)
systemic_racism - systemic or overt racism or discrimination affecting the offender, other than specifically anti-Black racism
islamophobia - Islamophobia or anti-Muslim prejudice affecting the offender
white_supremacy - white supremacy as something the offender was a victim of
other_prejudice - any other prejudice the offender experienced (antisemitism, homophobia, transphobia, anti-Asian racism, and so on)

Code for each factor:
M - the court treated it as MITIGATING for this offender: it reduced moral blameworthiness, was listed or accepted as a mitigating factor, or was a reason for a lower or non-custodial sentence. For an appeal, use M if the appeal court does this itself, or accepts that the sentencing judge properly did.
R - the court considered it for this offender but REJECTED it or gave it no effect (for example no connection shown, or the seriousness of the offence outweighed it entirely).
N - it is MENTIONED but not weighed for this offender: quoted from other cases, a general statement of law, a description from a report with no sign the court gave it weight, or it concerns someone else (a victim, a co-accused, another case).
X - not mentioned at all in the excerpt.

Also give:
- hate_motivated: Y if the offence being sentenced was itself motivated by hatred or prejudice against a group (which makes a sentence heavier), otherwise N.
- confidence: HIGH or LOW. Use LOW when the excerpt does not let you tell how the court treated the factors.
- note: at most 14 words on what the court did. Do not use commas or quotation marks.

Be strict about M: the excerpt must show the court giving the factor mitigating weight for this offender, not merely reciting it.

OUTPUT: for each input file write one CSV. First line exactly:
id,gladue_factors,colonialism,res_school,intergen_trauma,anti_black_racism,systemic_racism,islamophobia,white_supremacy,other_prejudice,hate_motivated,confidence,note
Then one row per item in order, for example: M1234,M,X,M,N,X,X,X,X,X,N,HIGH,Gladue factors and residential school history reduced moral blameworthiness

${COMMON}`

const jobs = []
for (let b = 1; b <= 228; b += 2) {
  jobs.push({ phase: 'Offences', model: 'sonnet', label: `offence:${b}-${b + 1}`, prompt: OFFENCE,
    io: [b, b + 1].map(n => `INPUT: ${ROOT}\\offence_batches\\offence_${pad(n)}.txt  ->  OUTPUT: ${ROOT}\\offence_raw\\labels_offence_${pad(n)}.csv`) })
}
for (let b = 1; b <= 168; b += 3) {
  jobs.push({ phase: 'Mitigating', model: 'sonnet', label: `mitigation:${b}-${b + 2}`, prompt: MITIGATION,
    io: [b, b + 1, b + 2].filter(n => n <= 168).map(n => `INPUT: ${ROOT}\\mitigation_batches\\mitigation_${pad(n)}.txt  ->  OUTPUT: ${ROOT}\\mitigation_raw\\labels_mitigation_${pad(n)}.csv`) })
}
for (let b = 1; b <= 4; b += 2) {
  jobs.push({ phase: 'Audit', model: 'opus', label: `offence-audit:${b}-${b + 1}`, prompt: OFFENCE,
    io: [b, b + 1].map(n => `INPUT: ${ROOT}\\offence_audit_batches\\offence_audit_${pad(n)}.txt  ->  OUTPUT: ${ROOT}\\offence_audit_raw\\labels_offence_audit_${pad(n)}.csv`) })
}
for (let b = 1; b <= 6; b += 3) {
  jobs.push({ phase: 'Audit', model: 'opus', label: `mitigation-audit:${b}-${b + 2}`, prompt: MITIGATION,
    io: [b, b + 1, b + 2].map(n => `INPUT: ${ROOT}\\mitigation_audit_batches\\mitigation_audit_${pad(n)}.txt  ->  OUTPUT: ${ROOT}\\mitigation_audit_raw\\labels_mitigation_audit_${pad(n)}.csv`) })
}
const results = await parallel(jobs.map(j => () =>
  agent(`${j.prompt}\n\nFILES:\n${j.io.join('\n')}`, { label: j.label, phase: j.phase, model: j.model }).then(r => r ? 1 : 0)))
const failed = jobs.filter((j, i) => !results[i]).map(j => j.label)
log(`${results.filter(Boolean).length} of ${jobs.length} labellers finished; failed: ${failed.join(', ') || 'none'}`)
return { done: results.filter(Boolean).length, total: jobs.length, failed }
