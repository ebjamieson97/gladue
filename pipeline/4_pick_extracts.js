export const meta = {
  name: 'pick-extract-passages',
  description: 'Readers pick the crime and rationale passages, and the phrases to highlight, for systemic-mitigation decisions',
  phases: [{ title: 'Pick', detail: 'one reader per file of 3 decisions', model: 'sonnet' }],
}
// Run with args {"from": 1, "to": N, "out": "raw"} ; files are case_extracts/work/batches/extract_NNN.txt
const W = 'C:\\Users\\Eric Bruce Jamieson\\Documents\\Conditional Sentencing\\case_extracts\\work'
const pad = n => String(n).padStart(3, '0')
const PROMPT = `You are preparing short extracts from Canadian criminal sentencing decisions for a research website. Each extract becomes a picture of the court's own words with a few phrases highlighted in yellow. Read each decision yourself; do not write code.

The input file holds up to 3 decisions. Each starts with \`===== CASE X0001 =====\`, a line of details, the passage an earlier reader picked as showing the court giving weight to a systemic factor (Gladue factors, residential schools, colonialism, intergenerational trauma, anti-Black racism, other racism), and then the decision's numbered paragraphs [1], [2], ...

FOR EACH DECISION make two extracts.

1. CRIME
- Passage: one paragraph or a run of CONSECUTIVE paragraphs, about 120 to 300 words, that best tells what the offender actually did. Prefer the court's own narrative of the events over procedural history.
- Highlights: 1 to 6 phrases, and ONLY facts that are genuinely serious: violence, weapons, threats, danger to others, harm to victims. Fewer is better than filler: in a case with little violence (for example drugs, possession of a gun, flight from police) highlight only the one or two most serious acts, and never pad with incidental or investigative details (what police saw, how a search began, where the offender was standing). Each must read as a complete action: include the person doing it, so the reader can see who did what to whom (write "he stabbed her in the back", not "stabbed her in the back"; "Mr. X struck the victim with a bat", not "struck the victim"). Cover both the most serious acts (violence, weapons, threats) AND their effects on the victim (injuries, pain, fear, death), for example "she believed she was going to die" or "he died from his injuries". A phrase can be a whole sentence or two consecutive sentences when that is what conveys the harm. Do not highlight graphic sexual details or anything that identifies a victim.

2. RATIONALE
- Passage: the court's explanation of the systemic factor. Use one run of consecutive paragraphs, or two runs that are not next to each other (for example "24-25;31"), about 120 to 350 words in total. Taken together, the passage must make two things clear to someone who has not read the decision:
  (a) WHAT is being weighed: the systemic factor and the offender's history it rests on (for example what a Gladue report or an Impact of Race and Culture Assessment says about this offender);
  (b) the COURT'S OWN CONCLUSION that the factor reduces the offender's moral culpability or blameworthiness, or lowers or shapes the sentence.
  WHOSE WORDS: the passage must show the COURT'S OWN reasoning. A paragraph that sets out what defence counsel, the Crown, a Gladue report, an IRCA, a pre-sentence report or a witness argued or said (for example "His counsel has argued...", "Counsel submits...", "The author of the report states...") is NOT the court's reasoning, even when it is persuasive. You may include such a paragraph only if the passage ALSO includes the paragraph where the judge explicitly accepts, adopts or agrees with it ("I accept that...", "I agree with counsel that...", "I adopt the report's conclusion..."); otherwise leave it out and use the court's own paragraphs. Never highlight words that are only counsel's or a report's unless the judge explicitly adopts them in the passage.
  Prefer the court's own words. If the clearest description is the court summarising a report or counsel's submission, add the paragraph where the court itself accepts it and states its effect, even if that paragraph is further away. If the conclusion is not next to the systemic discussion, look through the WHOLE decision for the court's statement of effect, which may be brief and earlier or later (for example "it was very important to the outcome here", "I have taken these factors into account", "this reduces his moral blameworthiness", "this justifies a shorter sentence"), and use that paragraph as the second run.
- Highlights: 2 to 6 phrases, each a whole clause rather than a single word:
  - where the court frames the question about this offender, for example "I must determine Mr. Smith's moral culpability";
  - the link between this offender and the systemic factor, for example "particularly her Indigenous heritage, viewed in light of the systemic factors" or "the racism he experienced throughout his schooling";
  - the court's conclusion, for example "his moral culpability is significantly reduced" or "I would impose a lower sentence than I otherwise would";
  - the PRINCIPLE behind the decision: any statement of how the sentence should respond to systemic or structural inequality, such as a sentence that must not perpetuate or compound the structural inequities, systemic discrimination or disadvantage that shaped the offender. Highlight it IN FULL, even when it runs over two or three sentences, and whether the court says it itself or quotes it from a report or submission it relies on. Example of the kind of passage to highlight whole: "The court is therefore urged to craft a sentence that embodies Anderson's vision. One that recognizes the moral blameworthiness of the offence while refusing to perpetuate the structural inequities that produced it." If such a statement exists, make sure the passage includes its paragraph.
  Do NOT highlight isolated words, case citations or pinpoint references (for example "Ipeelee at para 73"), or words about someone other than the offender (for example the victim's background). Named factors such as colonialism, residential schools, intergenerational trauma, anti-Black racism, IRCA, Gladue and R. v. Anderson are highlighted automatically; do not list them on their own.

Copy every phrase EXACTLY from inside the chosen paragraphs (same spelling and punctuation).

OUTPUT: JSON Lines, one object per decision, one line each:
{"id":"X0001","crime_paras":"12-14","rationale_paras":"40-41;47","crime_highlights":["phrase one","phrase two"],"rationale_highlights":["phrase"],"conclusion_clear":"Y","note":"at most 15 words, or empty"}
Use "12" for a single paragraph. conclusion_clear is Y if the rationale passage contains the court's own statement that the factor reduced culpability or affected the sentence, N if the court never says so clearly anywhere in the decision. Inside strings never use a double quotation mark (use a single quote) and no line breaks.

RULES: Read the whole file (in parts with offset/limit). Every decision gets exactly one line. Write the output file with the Write tool (overwrite if it exists). Reply with one short line.`
const files = Array.from({ length: args.to - args.from + 1 }, (_, i) => args.from + i)
const out = args.out || 'raw'
const bdir = args.batches || 'batches'
const pfx = args.prefix || 'extract'
const res = await parallel(files.map(b => () =>
  agent(`${PROMPT}\n\nINPUT: ${W}\\${bdir}\\${pfx}_${pad(b)}.txt\nOUTPUT: ${W}\\${out}\\${pfx}_${pad(b)}.jsonl`,
        { label: `pick:${pad(b)}`, phase: 'Pick', model: 'sonnet' })))
const failed = files.filter((b, i) => !res[i])
log(`${files.length - failed.length} of ${files.length} files done; failed: ${failed.join(', ') || 'none'}`)
return { failed }
