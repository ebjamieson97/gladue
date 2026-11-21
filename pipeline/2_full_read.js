export const meta = {
  name: 'full-read-sentencing-decisions',
  description: 'AI readers record offences, the sentence and mitigating factors for every selected sentencing decision',
  phases: [
    { title: 'Read', detail: 'one reader per file of about 10 decisions', model: 'sonnet' },
    { title: 'Audit', detail: 'a second model re-reads 150 decisions', model: 'opus' },
  ],
}
const ROOT = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\data\\labels'
const pad = (n, w) => String(n).padStart(w, '0')

const PROMPT = `You are reading Canadian criminal sentencing decisions for a research dataset. Careful, consistent answers matter more than speed. Read each item yourself and judge it; do not write code or scripts to do the work.

The input file holds about 10 items. An item starts with a line like \`===== ITEM S01234 =====\`, then a line giving the court, case name, date, length and whether you are shown "the full text" or "excerpts only". Long decisions are shown as the end of the HEADING, the OPENING, PASSAGES FROM THE MIDDLE, and the CLOSING.

For each item write ONE JSON object on ONE line, with exactly the keys below, in this order.

=== WHICH SENTENCE TO RECORD ===
- Record the sentence that stands for the offender at the END of this decision. Trial court sentencing: the sentence the judge imposes. Appeal: if the sentence appeal fails, the sentence that was under appeal (as the decision describes it); if the appeal court changes the sentence, the new sentence.
- Follow the majority. Ignore dissenting reasons (a CLOSING may end with a dissent - check).
- If several offenders are sentenced, the sentence keys (from "prison" to "sentence_quote") describe the FIRST-NAMED offender who is sentenced; say how many offenders in n_offenders and summarise the others in co_offenders. The keys "indigenous", "systemic", "systemic_quote" and "mitigating" cover ANY offender sentenced in the decision.
- Give the total for all counts dealt with in this decision (the global sentence). Do not add sentences from earlier cases that the offender is already serving.

=== KEYS ===
"id": the item id.

"offences": every category of offence FOR WHICH A SENTENCE IS BEING IMPOSED OR REVIEWED in this decision, all counts and all offenders, as codes separated by semicolons (for example "sexual;assault"). Do NOT count offences that appear only in the offender's prior record, in other cases cited for comparison, or in charges that were acquitted, stayed or withdrawn. Write "none" if the text does not show what the offences are. Codes:
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
"offence_note": the offences in at most 12 words.

"outcome": one of
  imposed - this court is sentencing the offender itself (first instance)
  appeal_upheld - a sentence appeal (or leave to appeal sentence) fails; the sentence stands
  appeal_reduced - the appeal court makes the sentence lighter
  appeal_increased - the appeal court makes the sentence heavier
  appeal_varied_other - the appeal court changes the sentence in a way that is neither clearly lighter nor heavier (for example only an ancillary order)
  no_sentence - this decision does not leave a sentence fixed: a new trial or a new sentencing hearing is ordered, the conviction is quashed, or it is only a ruling on a step in the proceeding (for example admissibility, a dangerous offender assessment order, an adjournment)
  unclear - the text shown does not let you tell
"n_offenders": number of offenders whose sentence is imposed or reviewed in this decision (integer).
"co_offenders": if n_offenders is more than 1, the sentence of each OTHER offender in a few words (for example "Jones: 3 years; Lee: 18 months conditional sentence"); otherwise "".

DURATIONS use the fixed form "Ny Nm Nd" (years, months, days), copying the units the court used without converting: "six years" -> "6y 0m 0d"; "18 months" -> "0y 18m 0d"; "90 days" -> "0y 0m 90d"; "two years less a day" -> "2y 0m -1d"; "three and a half years" -> "3y 6m 0d".

"prison": the total jail or penitentiary sentence BEFORE any deduction of credit for time already spent in custody. A duration, or one of: "life"; "indeterminate" (dangerous offender); "none" (no jail: for example only a conditional sentence, probation, a fine or a discharge); "time_served" (the sentence is time served and no total length is given); "unclear" (a jail sentence exists but the text shown does not give its length); "na" (outcome is no_sentence). A conditional sentence served in the community is NOT prison. For a youth sentence give the total custody and supervision length.
"prison_after_credit": the jail time left to serve after credit for pre-sentence custody, if the decision states it (a duration); otherwise "".
"credit": the credit given for pre-sentence custody, as credited (a duration); "none" if there is none; "" if not stated.
"parole_ineligibility_years": for a life sentence, the years before parole eligibility (a number); otherwise null.
"conditional_sentence": length of a conditional sentence order (jail served in the community / house arrest), a duration, "unstated" (ordered but the length is not shown), or "none".
"probation": length of probation, a duration, "unstated", or "none".
"long_term_supervision": length of a long-term supervision order, a duration, "unstated", or "none".
"driving_prohibition": length of a driving prohibition, a duration, "life", "unstated" (ordered but length not shown), or "none".
"fine": total fines in dollars (a number; include a fine in lieu of forfeiture; exclude the victim surcharge); 0 if none.
"restitution": total restitution or compensation ordered in dollars (a number); 0 if none.
"community_service_hours": hours of community service ordered (a number); 0 if none.
"orders": every other part of the sentence that applies, as codes separated by semicolons, or "none":
  intermittent (jail served intermittently, e.g. weekends); suspended_sentence; discharge_absolute; discharge_conditional; victim_surcharge; weapons_prohibition (s. 109 / 110); dna_order; soira (sex offender registration); s161_order (prohibition on being around children); no_contact_order; forfeiture; delayed_parole (s. 743.6); dangerous_offender; long_term_offender; youth_sentence (sentenced under the youth justice legislation); other (say what in "note")

"alt_institution": fill this when the sentence sends the offender to, or the court recommends, a place OTHER than an ordinary jail or penitentiary:
  healing_lodge - an Indigenous healing lodge or healing centre
  residential_treatment - a live-in addiction or other treatment centre, recovery house or similar residential program
  psychiatric_facility - a forensic or psychiatric hospital, or a regional psychiatric / treatment centre of the prison service
  other - another kind of alternative institution (say what in "note")
  none - otherwise
  Do NOT count programs the offender attended before being sentenced, or non-residential counselling.
"alt_basis": "ordered" (the sentence requires the offender to live at or attend the place, for example as a condition of a conditional sentence or probation); "if_directed" (only if a supervisor or probation officer directs it); "recommended" (the court recommends that corrections authorities place the offender there); "" if alt_institution is none.
"alt_name": the name of the place if given, otherwise "".
"alt_time": how long the offender is to be there (a duration), "unspecified" if no length is given, "" if alt_institution is none.

"sentence_quote": the passage where the court states the sentence that stands, COPIED EXACTLY from the text shown (at most about 50 words; one continuous passage; do not paraphrase or join separate passages). "" if the text shown has no such passage.

"indigenous": "Y" if the decision identifies an offender being sentenced as Indigenous (Aboriginal, First Nations, Metis, Inuit, Mi'kmaq and so on); otherwise "N".

"systemic": how the court dealt with each of the factors below AS IT RELATES TO AN OFFENDER BEING SENTENCED in this decision. These are about prejudice or historical wrongs that the offender (or the offender's family or community) experienced. List only the factors that are mentioned, as factor=code separated by semicolons (for example "gladue_factors=M;res_school=M;colonialism=N"), or "none" if none is mentioned.
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
  Codes:
  M - the court treated it as MITIGATING for this offender: it reduced moral blameworthiness, was listed or accepted as a mitigating factor, or was a reason for a lower or non-custodial sentence. For an appeal, use M if the appeal court does this itself, or accepts that the sentencing judge properly did.
  R - the court considered it for this offender but REJECTED it or gave it no effect (for example no connection shown, or the seriousness of the offence outweighed it entirely).
  N - it is MENTIONED but not weighed for this offender: quoted from other cases, a general statement of law, a description from a report with no sign the court gave it weight, or it concerns someone else (a victim, a co-accused, another case).
  Be strict about M: the text must show the court giving the factor mitigating weight for this offender, not merely reciting it.
"systemic_quote": if any factor is coded M, the passage that best shows the court giving it weight, COPIED EXACTLY from the text shown (at most about 50 words); otherwise "".
"hate_motivated": "Y" if the offence being sentenced was itself motivated by hatred or prejudice against a group (which makes a sentence heavier), otherwise "N".

"mitigating": the ordinary mitigating factors that the court ACCEPTED for the offender (if several offenders are sentenced, for any of them), as codes separated by semicolons. For an appeal, include those the appeal court accepts or reports the sentencing judge as having accepted. Write "none" if the court found no mitigating factors, and "not_shown" if the text shown does not deal with mitigating factors at all. Do not include a factor the court mentioned only to reject it or to say it carries no weight. Codes:
  guilty_plea; remorse (remorse, apology, acceptance of responsibility); no_record (no or minor or dated criminal record); youth (young age of the offender); age_or_health (old age or poor physical health); mental_health (mental illness or disorder); cognitive (FASD, intellectual disability, brain injury); addiction (addiction or substance abuse treated as mitigating); abuse_or_trauma (childhood abuse, neglect, trauma, a disadvantaged upbringing); good_character (good character, work history, community contribution, support letters); family (family support or dependants who rely on the offender); rehabilitation (steps taken toward rehabilitation or good prospects of it, treatment, sobriety); cooperation (cooperated with police or prosecution, testified); lesser_role (minor role, pressure from others, duress, provocation); collateral (collateral consequences: immigration, loss of career, publicity, injuries suffered); delay (delay in the proceedings or time elapsed); custody_conditions (harsh pre-sentence custody: lockdowns, pandemic conditions); bail_conditions (strict bail or house arrest before sentence); state_misconduct (Charter breach or mistreatment by police or the state); restitution_made (repaid or compensated the victim); other (say what in "note")

"confidence": "HIGH" or "LOW". Use LOW when the text shown leaves the offences or the sentence unclear or incomplete.
"note": at most 20 words on anything unusual or unclear. "" if nothing.

=== OUTPUT FORMAT ===
- JSON Lines: one object per line, no blank lines, no surrounding list, no markdown, no comments.
- Use double quotes for keys and string values. INSIDE a string value never use a double quotation mark: replace any quotation mark in copied text with a single quote ('). No line breaks inside a value.
- Example line:
{"id":"S01234","offences":"sexual;assault","offence_note":"Sexual assault and assault causing bodily harm","outcome":"imposed","n_offenders":1,"co_offenders":"","prison":"4y 0m 0d","prison_after_credit":"2y 6m 0d","credit":"0y 18m 0d","parole_ineligibility_years":null,"conditional_sentence":"none","probation":"3y 0m 0d","long_term_supervision":"none","driving_prohibition":"none","fine":0,"restitution":0,"community_service_hours":0,"orders":"weapons_prohibition;dna_order;soira","alt_institution":"none","alt_basis":"","alt_name":"","alt_time":"","sentence_quote":"I sentence Mr. Smith to four years in prison, less credit of 18 months for time served","indigenous":"Y","systemic":"gladue_factors=M;res_school=M;colonialism=N","systemic_quote":"His moral blameworthiness is reduced by the Gladue factors I have described","hate_motivated":"N","mitigating":"guilty_plea;remorse;abuse_or_trauma","confidence":"HIGH","note":""}

RULES
- Judge only from the text shown. Do not look anything up, do not open any other files, and do not search the web.
- Every item in the file must get exactly one line. Before you finish, count the "===== ITEM" lines in the input file and check that your output has the same number of lines.
- Read the file completely; it is too large for one read, so read it in parts with offset/limit until you reach the end.
- Write the output file with the Write tool (overwrite it if it exists). When done, reply with one short line giving the number of lines written. Nothing else.`

// args.tag: an update round (reads full_read_batches_TAG, writes full_read_raw_TAG); omit it for the original round
const bdir = args.tag ? `full_read_batches_${args.tag}` : 'full_read_batches'
const rdir = args.tag ? `full_read_raw_${args.tag}` : 'full_read_raw'
const jobs = []
const todo = (args.ranges || [[args.from, args.to]]).flatMap(([a, z]) => Array.from({ length: z - a + 1 }, (_, i) => a + i))
for (const b of todo) {
  jobs.push({ phase: 'Read', model: 'sonnet', label: `read:${pad(b, 4)}`,
    io: `INPUT: ${ROOT}\\${bdir}\\read_${pad(b, 4)}.txt\nOUTPUT: ${ROOT}\\${rdir}\\read_${pad(b, 4)}.jsonl` })
}
for (let b = (args.auditFrom || 1); b <= (args.auditTo || 0); b++) {
  jobs.push({ phase: 'Audit', model: 'opus', label: `audit:${pad(b, 2)}`,
    io: `INPUT: ${ROOT}\\full_read_audit_batches\\audit_${pad(b, 2)}.txt\nOUTPUT: ${ROOT}\\full_read_audit_raw\\audit_${pad(b, 2)}.jsonl` })
}
const results = await parallel(jobs.map(j => () =>
  agent(`${PROMPT}\n\nFILES\n${j.io}`, { label: j.label, phase: j.phase, model: j.model }).then(r => r ? 1 : 0)))
const failed = jobs.filter((j, i) => !results[i]).map(j => j.label)
log(`${results.filter(Boolean).length} of ${jobs.length} readers finished; failed: ${failed.join(', ') || 'none'}`)
return { done: results.filter(Boolean).length, total: jobs.length, failed }
