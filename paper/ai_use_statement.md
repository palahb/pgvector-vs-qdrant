# Generative-AI use statement (DRAFT for the authors)

This is a draft. The authors are the ones who attest to it, so every sentence in the
"Statement" section has to be true before it is used, and the journal's own wording and
placement rules (the target journal is not final) have to be checked against its current
author guidelines. Nothing here has been sent anywhere.

## Statement (English, for the manuscript)

> During the preparation of this work the authors used Claude (Anthropic; Claude Code and a
> chat interface) and GPT/Codex (OpenAI) in order to write and test benchmark and analysis
> code, to automate experiment submission and result validation on a Slurm cluster, to draft
> and edit parts of the manuscript text, and to organize the response to the review comments.
> The authors designed the study, chose the experiments and the claims, ran the experiments,
> and checked the results. After using these tools the authors reviewed and edited the content
> as needed and take full responsibility for the content of the publication.

The last two sentences are the authors' attestation, not something the tools can supply. See
the checklist below.

## What the tools did (facts from this repository's records)

| Tool | Period | Work |
|---|---|---|
| Claude (chat) | Sep-Oct 2026 | Review of the course-project scripts; the first version of the ARF harness (`bench/`), data preparation, summaries and figure scripts; drafts of the paper rewrite and of e-mails to the supervisor |
| GPT / Codex | Nov 2026 | Review of the project state against the review report; the working plan (`MAKALE_CALISMA_PLANI.md`); the provenance schema and validator, the Slurm orchestration layer, and the first E6/E7 code |
| Claude Code | Nov 2026 | Experiments E6-E10 and E17 (harness changes, tests, submission, analysis tools); rewrites of the Results, Confounders, Related Work and Abstract text; the referee-response draft; literature checks |

## What guards the content (also facts)

- Every number in the Results sections comes from a result set that passed the strict
  validator (`analysis/validate_results.py`) with zero errors and zero warnings, and each set
  has a manifest under `data-manifests/` with its commit, job IDs and file checksums.
- Experiments went through a smoke, pilot and full gate for the exact commit that ran.
- Literature details (authors, venue, pages) were checked against primary listings; where a
  page range could not be verified it was left out of the reference.
- Errors the process itself found are recorded in `docs/MONTH_PLAN.md` (for example the
  `hnsw.ef_search` range problem and the corrected description of Zhang et al.).

## What the authors must confirm before using the statement

1. That each author has actually read the manuscript text as it will be submitted. The text
   was written and revised by the tools; the records available for this draft show no full
   read-through of it by an author, so this has to be done and cannot be assumed.
2. That every claim and number in the final text was checked against the result files or the
   cited sources by a human, or that this will be done before submission.
3. Whether the review report and the planning documents that the supervisor produced with
   Claude and Gemini (mentioned in the e-mails of 12 Sep and 4 Nov 2026) should be named in
   the statement. They are not manuscript content, so this is the supervisor's decision.
4. The exact tool names and versions the journal wants, and whether it wants the statement
   in the manuscript, in a separate declaration section, or in the submission system.
5. That no confidential material, such as cluster credentials, was given to a tool. A scan of
   the 190 tracked files found no key files, private-key blocks or access tokens. The only
   password strings are the placeholder `password="password"` for a local Docker test
   database in the archived course scripts under `legacy/`. The scan does not cover what was
   typed into the tool conversations, which only the authors can confirm.

## Notes for the cover letter and for later

- Some publishers treat AI tools as not eligible for authorship and want the use described,
  not credited. The draft above follows that.
- The commit trailers in this repository name the model used for each commit; if a
  reviewer asks, `git log` shows which changes were tool-assisted.
