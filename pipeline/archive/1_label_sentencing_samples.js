export const meta = {
  name: 'label-3200-samples',
  description: 'Label 5,084 new court decisions (batches 41-236) plus a 104-decision cross-model audit',
  phases: [{ title: 'Label', detail: '98 labellers, two batch files each' }, { title: 'Audit', detail: 'second model re-labels 104 decisions', model: 'opus' }],
}
const ROOT = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\data\\labels'
const INSTR = `You are labelling excerpts of Canadian criminal court decisions for a research dataset. Careful, consistent labels matter more than speed.

Each input file holds about 26 items. An item starts with a line like \`===== ITEM D1234 =====\`, then the court, case name and length, then excerpts: the end of the HEADING, the OPENING of the reasons, a few MENTIONS OF SENTENCE from the middle (with a count of how many there are in total), and the CLOSING. Short decisions are given as FULL TEXT. Read each file completely; if a file is too large for one read, read it in parts with offset/limit.

TASK: give every item one label.

IMPOSES - In this decision a court imposes a sentence on an offender and gives its reasons ("reasons for sentence"). Includes youth sentences, dangerous offender / long-term offender decisions at first instance, decisions setting parole ineligibility after a murder conviction, and reasons that give both the verdict and the sentence.
REVIEWS - A court hearing an appeal rules, on the merits, on a challenge to a sentence or to part of the sentence proper (length, type, probation, fine, parole ineligibility, credit for pre-sentence custody, dangerous offender designation). Includes sentence appeals, Crown sentence appeals, appeals from both conviction and sentence where the sentence part is actually ruled on, applications for leave to appeal sentence that are decided by assessing the merits, and summary conviction sentence appeals heard by a superior court. It counts even if the reasoning about the sentence is one line (for example "the sentence was fit; the sentence appeal is dismissed").
RELATED - The decision is about sentencing law or the sentencing process but does not itself impose a sentence or review one on the merits. Examples: a constitutional challenge to a mandatory minimum decided separately from the sentence; a ruling on evidence or procedure within a sentencing hearing; a fact-finding hearing held before sentence; a decision only about ancillary orders (sex offender registry, DNA, forfeiture, restitution, driving or weapons prohibition); breach of a conditional sentence order; parole eligibility review (s. 745.6); disputes about how a sentence is calculated or administered; an extension of time or other procedural ruling in a sentence appeal that does not assess the sentence.
NOT - Everything else: verdicts, conviction-only appeals, bail and release pending appeal, rulings on evidence at trial, stays, Charter rulings not about sentence, withdrawal of guilty pleas, extradition, and so on. Also NOT when a sentence appeal is only mentioned but not decided on the merits (abandoned, dismissed as abandoned, not reached because a new trial was ordered or the conviction was quashed, adjourned), and NOT when the sentence is mentioned only as background.

For each item also give:
- depth: for IMPOSES and REVIEWS only. FULL = the discussion of the sentence is at least roughly a paragraph (facts about the offence or offender, aggravating/mitigating factors, ranges, or reasoning about fitness). MINIMAL = only a sentence or two about the sentence. For RELATED and NOT write NA.
- confidence: HIGH or LOW. Use LOW when the excerpt does not let you tell with reasonable certainty.
- note: at most 12 words saying what the decision is. Do not use commas or quotation marks in the note.

RULES
- Judge only from the excerpt. Do not look anything up, do not open any other files, and do not search the web.
- Label what the decision actually does, not how often the word "sentence" appears.
- Every item in a file must get a label.

OUTPUT: for each input file write one CSV with the Write tool. First line exactly: id,label,depth,confidence,note
Then one row per item in the order they appear, for example: D1234,REVIEWS,FULL,HIGH,Sentence appeal for robbery dismissed

When done, reply with one short line per file giving the number of rows. Nothing else.`

const pad = n => String(n).padStart(2, '0')
const jobs = []
for (let b = 41; b <= 236; b += 2) {
  jobs.push({ phase: 'Label', model: 'sonnet', label: `label:${b}-${b + 1}`,
    io: [b, b + 1].map(n => `INPUT: ${ROOT}\\batches\\batch_${pad(n)}.txt  ->  OUTPUT: ${ROOT}\\raw\\labels_batch_${pad(n)}.csv`).join('\n') })
}
for (let a = 1; a <= 4; a += 2) {
  jobs.push({ phase: 'Audit', model: 'opus', label: `audit:${a}-${a + 1}`,
    io: [a, a + 1].map(n => `INPUT: ${ROOT}\\audit_batches\\audit_${pad(n)}.txt  ->  OUTPUT: ${ROOT}\\raw_audit\\labels_audit_${pad(n)}.csv`).join('\n') })
}
const results = await parallel(jobs.map(j => () =>
  agent(`${INSTR}\n\nFILES:\n${j.io}`, { label: j.label, phase: j.phase, model: j.model })
    .then(r => ({ job: j.label, result: r }))))
const failed = jobs.filter((j, i) => !results[i]).map(j => j.label)
log(`${results.filter(Boolean).length} of ${jobs.length} labellers finished; failed: ${failed.join(', ') || 'none'}`)
return { done: results.filter(Boolean).length, failed }
