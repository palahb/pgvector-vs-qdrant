# Target journal check: Information Systems (Elsevier), 27 November 2026

The plan asks for the journal's scope, article type, length limit and the place of the AI declaration to be checked **from the source**, then the manuscript
converted to the Elsevier template. This note records what could be read and what could not.

## Read from the source

* **Generative-AI declaration** (Elsevier's policy page, "The use of generative AI and AI-assisted technologies in writing for Elsevier", reached through a web search
  on 27 November 2026): the statement goes at the end of the manuscript, immediately above the references, after acknowledgements and the funding and competing-interest
  statements; it is not in the abstract or the methods. Section title: "Declaration of generative AI and AI-assisted technologies in the writing process". Template wording:
  "During the preparation of this work the author(s) used [NAME TOOL / SERVICE] in order to [REASON]. After using this tool/service, the author(s) reviewed and edited the content
  as needed and take(s) full responsibility for the content of the publication." Basic checks of grammar, spelling and punctuation need no declaration. Use of AI as part of the research
  method (here: code written and tests run with AI tools) is described in the methods. The manuscript follows this (section "Declaration of generative AI...").
* **Template** (CTAN, `elsarticle` 3.5 of 2026-01-09, `elsarticle-template-num.tex`): `\documentclass[preprint,12pt]{elsarticle}`, add `review` for double spacing; `\begin{frontmatter}`
  with `\title`, `\author`, `\affiliation{organization=...,city=...,country=...}`, `abstract`, `highlights`, `keyword` (separated by `\sep`); numbered references with `elsarticle-num` or a
  `thebibliography` environment (the template uses the latter). The class loads `graphicx`. The template gives no place for CRediT, competing interests or data availability.

## Could not be read

The journal's own **Guide for Authors** (aims and scope, accepted article types, length limit, highlights and graphical-abstract requirements, data-availability policy, review model)
is behind ScienceDirect, which answered HTTP 403 for `sciencedirect.com/journal/information-systems/publish/guide-for-authors` and for the same page reached by redirect from
`elsevier.com`. A web search returned only the pointer to that page. Nothing about scope, article type or length was taken from memory.

**To do by the authors before submission (needs a browser):** open the Guide for Authors and confirm (1) that a benchmarking and measurement study of this kind is in scope and which article
type it should be submitted as; (2) whether there is a length limit; (3) whether highlights (included, five lines) and a graphical abstract (not included) are required; (4) the data and code
availability wording; (5) single or double anonymized review (if double, the author block and the repository link in the manuscript must be removed for the review copy).
The fallback journals named by the supervisor, in order, are the Journal of Systems and Software and PeerJ Computer Science; the ACM version of the manuscript is kept in `paper/alt/`.

## Consequence for the manuscript

The Elsevier version is `paper/main.tex`. It follows what was read; the statements about scope, type and length are left to the authors' check above, and the manuscript makes no claim about them.
