# AGENTS.md

This repository is a small XeLaTeX resume template, not an application service.
Most changes affect LaTeX sources, class/package files, bundled fonts, or helper scripts.

## Scope
- Main resume source: `resume.tex`
- Alternate sample with photo: `resume_photo.tex`
- Core class definition: `resume.cls`
- Optional Chinese font packages: `zh_CN-Adobefonts_external.sty`, `zh_CN-Adobefonts_internal.sty`
- Generated/bundled Font Awesome support: `fontawesome.sty`, `fontawesomesymbols-*.tex`
- Helper generation scripts: `scripts/fs_sty.py`, `scripts/fs_sty.sh`
- Build config: `Makefile`, `latexmkrc`

## Agent Priorities
- Preserve the template's current structure and visual style unless the task explicitly asks for redesign.
- Prefer minimal, localized edits; this repo is mostly static template content.
- Do not remove bundled fonts or generated symbol files unless the task is specifically about asset regeneration.
- Treat `fontawesome.sty` as generated output unless the user explicitly wants direct edits there.
- Avoid touching personal/sample content in `resume.tex` unless the request is about resume content.

## Cursor And Copilot Rules
- No `.cursor/rules/` directory was found.
- No `.cursorrules` file was found.
- No `.github/copilot-instructions.md` file was found.
- There are no extra editor rule files to merge beyond conventions inferred from source.

## Build Commands
### Primary build commands
- `make` - runs `clean` and then builds all root-level `*.tex` files into PDFs.
- `make pdf` - same practical effect as `make`; rebuilds every root-level TeX target.
- `make en` - cleans and compiles `resume.tex` with `xelatex`.
- `xelatex resume.tex` - compile the main English resume directly.
- `xelatex resume_photo.tex` - compile the photo variant directly.
- `make clean` - removes generated LaTeX artifacts and PDFs.

### Latexmk workflow
- `latexmk -xelatex -gg -silent resume.tex` - good default full rebuild for the main resume.
- `latexmk -xelatex -gg -silent resume_photo.tex` - full rebuild for the photo variant.
- `latexmk -xelatex -gg -silent -pvc resume.tex` - watch mode noted in `latexmkrc`.
- `latexmk -c` - cleanup of intermediate files when using `latexmk`.

### Dependencies
- `xelatex` is the expected compiler; the README explicitly says the template is compiled with XeLaTeX.
- `latexmk` is optional but supported via `latexmkrc`.
- Python is needed only for `scripts/fs_sty.py`.
- Git and shell utilities are needed only for `scripts/fs_sty.sh` when regenerating Font Awesome assets.

### Current environment note
- In this CLI environment, `xelatex` is not installed.
- In this CLI environment, `latexmk` is not installed.
- Do not claim a build passed unless it was actually run in an environment with those tools.

## Lint And Test Commands
This repository does not include a dedicated lint suite or automated unit/integration tests.
Validation is build-oriented.

- `xelatex resume.tex` - closest thing to the primary test for the main template.
- `xelatex resume_photo.tex` - targeted validation for the alternate template.
- `latexmk -xelatex -gg -silent resume.tex` - stricter rebuild that catches missing references across passes.
- `python scripts/fs_sty.py <path-to-font-awesome.css>` - functional check for the Font Awesome generation script.

### Single-test guidance
When asked to run a "single test", interpret that as the narrowest affected build or script check.

- If editing `resume.tex`, run `xelatex resume.tex`.
- If editing `resume_photo.tex`, run `xelatex resume_photo.tex`.
- If editing `resume.cls` or shared `.sty` files, run both `xelatex resume.tex` and `xelatex resume_photo.tex`.
- If editing Chinese font support files, compile the TeX entrypoint that uses that package, if present in the branch.
- If editing `scripts/fs_sty.py`, run the script against a real Font Awesome CSS file if available.
- If editing `scripts/fs_sty.sh`, treat it as an integration script and verify each external dependency before running.

## Repository Structure Notes
- Root-level `*.tex` files are standalone compile targets by the `Makefile` pattern rule.
- `resume.cls` defines layout, macros, typography, and list spacing.
- `fontawesome.sty` and `fontawesomesymbols-*.tex` are vendor/generated support files and should not be reformatted casually.
- The `fonts/` directory is part of the template runtime and should remain stable.
- `.gitignore` excludes generated PDFs and common LaTeX temporary files.

## Style Guidelines
### General
- Match the existing style in the file you edit; this repo mixes LaTeX, Python, shell, and Markdown.
- Keep diffs small and intentional.
- Prefer readability over clever macro tricks.
- Preserve existing whitespace patterns unless you are cleaning a file consistently.
- Do not introduce new tooling, formatters, or dependencies unless the task requires them.

### LaTeX imports and package usage
- Keep package imports near the top of the file, before `\begin{document}`.
- In class/package files, prefer `\RequirePackage{...}` over `\usepackage{...}`.
- Group related package declarations together.
- Follow existing optional-argument formatting, with one key per line when the option block is long.
- Reuse existing macros like `\section`, `\datedsubsection`, `\datedline`, `\role`, and `\basicInfo` instead of inventing parallel APIs.

### LaTeX formatting
- Use plain ASCII unless the file already contains intentional Unicode content.
- Keep one logical block per paragraph.
- Preserve the existing indentation style: two spaces for list items and multiline option blocks.
- Leave a blank line between major sections or macro blocks.
- Keep section content compact; this template values density and clean spacing.
- Escape LaTeX-special characters correctly, for example `%` as `\%`.

### LaTeX naming conventions
- Use descriptive macro names in lower camel style already present in the repo, such as `\basicInfo` and `\datedsubsection`.
- Keep package/class filenames stable and descriptive.
- For new helper macros, prefer names that read clearly at call sites.
- Do not rename public macros lightly; TeX entrypoints depend on them directly.

### Python style
- Follow the existing lightweight standard-library-only approach in `scripts/fs_sty.py`.
- Keep imports at the top of the file.
- Prefer simple functions over classes for small transformation scripts.
- Use snake_case for functions and local variables.
- Keep behavior explicit; the script parses line-oriented CSS and writes deterministic output.
- Avoid adding third-party dependencies.

### Shell style
- Keep shell scripts POSIX-leaning, matching `#!/bin/sh` in `scripts/fs_sty.sh`.
- Use lowercase variable names as the current script does.
- Quote variable expansions when paths may contain spaces.
- Be careful with destructive commands like `rm -rf`; preserve behavior unless fixing it is part of the task.

### Markdown style
- Keep README-like prose concise and task-oriented.
- Use fenced code blocks for commands.
- Prefer short sections with explicit command examples.

## Types And Interfaces
- There is no typed application layer in this repository.
- For LaTeX, "interfaces" are macro signatures; preserve argument order and optional arguments.
- For Python helpers, keep function contracts simple and file-oriented.
- For shell helpers, assume external tools may fail and keep steps easy to audit.

## Error Handling Expectations
- For LaTeX changes, avoid silent fallbacks that hide compile failures.
- Prefer explicit required assets and package declarations over magical detection.
- In Python scripts, fail loudly rather than swallowing parse or file errors.
- In shell scripts, keep commands straightforward so failures are obvious from command output.
- If a command cannot be verified because `xelatex` or `latexmk` is missing, state that clearly.

## Change-Specific Advice
- If you modify `resume.cls`, review whether both sample TeX entrypoints still compile.
- If you modify font-related files, verify referenced font paths still match the repository layout.
- If you regenerate Font Awesome assets, mention the source version used; `scripts/fs_sty.sh` targets Font Awesome `v4.5.0`, while bundled `fontawesome.sty` reports `v4.6.3`.
- If you add new root-level `*.tex` files, note that `make pdf` will try to compile them automatically.
- Do not commit generated PDFs unless the user explicitly asks.

## Safe Defaults For Agents
- Default compile target: `resume.tex`.
- Default validation scope for shared layout changes: `resume.tex` and `resume_photo.tex`.
- Default cleanup command: `make clean`.
- Default assumption: no automated tests exist beyond compile checks.
- Default documentation stance: explain missing local tooling instead of pretending verification happened.
