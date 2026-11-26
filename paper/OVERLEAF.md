# Compiling the manuscript (to be done by the authors, in Overleaf)

The manuscript was **not compiled** in this repository: there is no TeX installation on the machine it was written on. Its structure was checked by script
(`make verify-paper`: balanced environments, defined references, no unused label, no open `\todo`, braces balanced, 21 bibliography items all cited), which does
not replace a compile.

1. Create a project and upload `paper/main.tex` and the folder `paper/figures/` (four PDFs and PNGs). Set the main document to `main.tex` and the compiler to pdfLaTeX.
2. The class is `elsarticle` (CTAN 3.5 of January 2026). Overleaf's TeX Live must have elsarticle 3.2 or later (the `\affiliation{organization=...}` form and the `highlights` environment need it).
   If it is older, replace the `\affiliation` line with `\address[hu]{Department of Computer Engineering, Hacettepe University, Ankara, Turkey}` and drop `highlights` into a separate file.
3. First things to look at after compiling: (a) wide tables (`tab:sources`, `tab:openloop`, `tab:causal`, `tab:expmap`) in the single-column layout; `table*` is treated as `table` there;
   (b) overfull boxes from long `\texttt{}` names (the class option `\sloppy` is set); (c) the highlights lines (at most 85 characters each); (d) the figures `fig:recall`, `fig:throughput`
   (`figure*` in one column).
4. For a double-spaced review copy, change the class options to `[preprint,review,12pt]`.
5. The ACM two-column version of the same text is `paper/alt/main_acmsigconf.tex` (class `acmart`, option `sigconf`); it is a fallback and is not kept in step with later edits.
6. Before submission see `docs/OPEN_ITEMS.md`: declarations and the journal's own guide for authors need the authors.
