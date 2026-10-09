# Coding Agent Alignment Brief: GitHub-Side Crowdin Workflow for MaiBot

## Purpose

Use this document as the authoritative implementation and maintenance guide for the repository's GitHub-side Crowdin workflow.

Its purpose is to keep Coding Agent aligned with the agreed operating model and prevent drift from the intended localization strategy.

This document is normative for:
- GitHub Actions changes related to Crowdin sync and localization PR flow
- branch and PR behavior for localization updates
- repository-side validation behavior for localization assets
- boundaries between baseline workflow logic and repository-specific policy

This document is **not** a generic Crowdin tutorial.
It describes the expected behavior for this repository specifically.

---

## Core Operating Model

The repository uses a **PR-based localization return flow**.

### Source branches covered by localization sync
- `main`
- `r-dev`

### Localization return branches
- `l10n_main`
- `l10n_r-dev`

### Return path
- Crowdin translations must **not** be pushed directly into `main` or `r-dev`.
- Translations must return through `l10n_${branch}` branches.
- Localization changes must reach `main` or `r-dev` through pull requests.

### Source-language assets
The source language is `zh-CN`.
Only source-language assets should trigger source uploads to Crowdin.

Current source-language assets:
- `locales/zh-CN/*.json`
- `prompts/zh-CN/**/*.prompt`
- `dashboard/src/i18n/locales/zh.json`
- `crowdin.yml`

### Prompt template extension
The repository currently treats `.prompt` as the only i18n-relevant prompt template extension.
Do not broaden prompt-related workflow triggers unless repository reality changes.

---

## Mandatory Interpretation Rules

Coding Agent must follow these interpretation rules exactly.

### Rule 1: Do not reinterpret `l10n_` branches
`l10n_main` and `l10n_r-dev` are service/localization return branches.
They are not feature branches and they are not alternate long-lived development branches.

### Rule 2: Do not bypass the PR model
Do not change the workflow so that translated assets are committed directly to `main` or `r-dev`.
The agreed model is:
- source branch sync
- Crowdin-side translation availability
- localization return branch update
- PR into the matching base branch
- maintainer review and merge

### Rule 3: Do not claim approval in Crowdin means immediate GitHub update
A translation being reviewed or approved in Crowdin does **not** mean GitHub is updated instantly.
GitHub reflects Crowdin-side updates only when the sync workflow runs.

That can happen via:
- push-triggered sync
- scheduled sync
- manual dispatch

Any documentation, comments, or workflow descriptions produced by Coding Agent must preserve this distinction.

### Rule 4: Treat GitHub-side content policy as repository-specific, not as a universal Crowdin rule
If the repository enforces extra validation rules on committed target locale content, those rules must be described as **repository-specific policy**.
They must not be described as an inherent or standard requirement of Crowdin's branch model.

### Rule 5: Preserve source-upload loop prevention
Do not modify the workflow in a way that allows translated target files to trigger a new source upload cycle to Crowdin.
Only source-language assets should trigger source uploads.

---

## Required GitHub Workflow Behavior

### 1. `crowdin-sync.yml`

This workflow must remain responsible for:
- uploading source-language assets to Crowdin
- downloading available translations from Crowdin
- creating or updating localization return branches
- creating or updating localization PRs into the matching source branch

#### Required triggers
The workflow may be triggered by:
- manual dispatch
- schedule
- push to `main` or `r-dev` when source-language assets change

#### Required branch mapping
The workflow must preserve this mapping:
- `main -> l10n_main -> PR into main`
- `r-dev -> l10n_r-dev -> PR into r-dev`

#### Required boundary
The workflow must preserve the PR-based return flow.
It must not be converted into direct translation pushes into `main` or `r-dev`.

#### Required wording discipline
When describing this workflow, Coding Agent must say that it downloads **currently available** Crowdin translations when the workflow runs.
Coding Agent must not imply that source-language pushes and translation return are a single synchronous transaction.

---

### 2. `precheck.yml`

This workflow must:
- run on pull requests
- check merge/conflict state against the **real PR base branch**

#### Required base-branch logic
For every PR, conflict simulation must use the actual PR target branch.
Examples:
- feature branch into `main` -> compare against `main`
- feature branch into `r-dev` -> compare against `r-dev`
- `l10n_main` PR -> compare against `main`
- `l10n_r-dev` PR -> compare against `r-dev`

#### Forbidden behavior
Coding Agent must not reintroduce any logic that hardcodes `main` as the comparison base for all PRs.

#### Label behavior
If the repository already uses a conflict label, that behavior should remain intact unless there is a clearly documented reason to change it.

---

### 3. `ruff-pr.yml`

This workflow must remain focused on Python code quality.

#### Required path discipline
Translation-only localization PRs must not trigger Ruff by default.
Ruff should run only when files relevant to Python code quality or Ruff configuration are changed.

#### Practical intent
The goal is to reduce CI noise on localization PRs without weakening Python quality checks.

#### Forbidden behavior
Do not expand Ruff triggers so broadly that translation-only localization PRs start running Ruff again by default.

---

### 4. `i18n-validate.yml`

This workflow must remain the repository-side structural validation layer for localization changes.

#### Required validation role
It should validate localization assets and i18n-relevant code changes.
That includes both:
- backend locale JSON under `locales/`
- dashboard locale JSON under `dashboard/src/i18n/locales/`

#### Prompt trigger scope
It must cover the actual prompt template extension used in the repository.
At present, that means `.prompt`.
Do not broaden the watched prompt-file patterns unless repository reality changes.

#### Missing prompt behavior
If localized prompt files are intentionally allowed to fall back to `zh-CN` at runtime, workflow and documentation should represent that accurately.
Do not silently convert warning-only behavior into hard-failure behavior unless explicitly instructed.

---

## Repository-Specific Policy Layer

The repository may enforce extra policy rules on committed target locale files.
Examples may include:
- forbidding unchanged source-language carry-over in target locale files
- forbidding Chinese characters in `en-US` locale files
- placeholder consistency checks
- plural structure checks

These rules are allowed.
However, Coding Agent must always describe them as:
- repository-specific validation policy
- layered on top of the baseline Crowdin PR workflow

They must **not** be described as:
- a standard Crowdin requirement
- an inherent property of `l10n_` branches
- something every Crowdin GitHub integration does by default

---

## Documentation Guardrails for Coding Agent

Whenever Coding Agent writes or updates repository documentation about localization workflow, it must obey the following rules.

### Always state these facts clearly
- `zh-CN` is the source language
- `main` and `r-dev` are the source branches covered by Crowdin sync
- translations return via `l10n_${branch}` branches
- localization changes reach `main` or `r-dev` through PRs
- GitHub receives translation updates when the sync workflow runs, not necessarily immediately when approval happens in Crowdin

### Never blur these concepts
Do not conflate:
- Crowdin approval state
- GitHub sync timing
- PR creation/update timing
- PR merge timing

These are related but distinct steps.

### Always distinguish baseline workflow from extra repository policy
If describing validation rules beyond branch flow and sync behavior, explicitly mark them as repository-specific policy.

### Keep statements operational and repository-specific
Do not write generic platform marketing language.
Do not convert this repository's workflow report into a generic localization tutorial.

---

## Change Control Rules

Coding Agent may adjust workflows only within the following boundaries.

### Allowed changes
Coding Agent may:
- fix PR base-branch detection bugs
- reduce CI noise for translation-only PRs
- tighten path filters to better match repository reality
- improve workflow descriptions so they do not misrepresent sync timing
- improve documentation clarity around repository-specific validation policy

### Allowed changes with explicit justification
Coding Agent may change repository-side i18n validation rules only if:
- the change is clearly labeled as repository-specific policy
- the justification is documented
- the change does not misrepresent itself as standard Crowdin behavior

### Forbidden changes
Coding Agent must not:
- replace the `l10n_${branch}` PR model with direct pushes into source branches
- make translated target files trigger source uploads back to Crowdin
- hardcode `main` as the merge-check target for all PRs
- broaden prompt-file watchers without confirming actual repository usage
- present repository-specific locale policy as if it were part of Crowdin's default model
- imply that approved translations automatically and immediately appear in GitHub without a sync run

---

## Expected End-to-End Flow

### Flow A: Source-language update
1. A source-language asset change is pushed to `main` or `r-dev`.
2. The Crowdin sync workflow runs.
3. The workflow uploads source-language assets to Crowdin.
4. The workflow may also download any translations currently available in Crowdin.
5. The workflow creates or updates the matching localization return branch.
6. A PR is created or updated from `l10n_${branch}` into the matching base branch.

### Flow B: Localization PR validation
1. A PR from `l10n_${branch}` into its matching base branch exists.
2. `precheck.yml` validates merge/conflict state against the real PR base branch.
3. `i18n-validate.yml` validates localization structure and repository-specific i18n policy.
4. `ruff-pr.yml` does not run unless the PR touches Python/Ruff-relevant files.
5. Maintainers review and merge the PR.

### Flow C: Scheduled synchronization
1. The scheduled Crowdin sync workflow runs.
2. It processes the supported source branches.
3. If Crowdin currently has downloadable translation updates, GitHub updates or creates the corresponding `l10n_` branch PRs.

---

## Coding Agent Self-Check Before Making Any Workflow or Docs Change

Before changing localization-related workflows or documentation, Coding Agent must confirm all of the following:

1. Am I preserving the `l10n_${branch}` PR-based return model?
2. Am I avoiding any claim that Crowdin approval instantly updates GitHub?
3. Am I keeping source-upload triggers limited to source-language assets?
4. Am I using the real PR base branch for conflict checks?
5. Am I keeping Ruff out of translation-only PRs by default?
6. Am I limiting prompt-file trigger patterns to what the repository actually uses?
7. If I describe extra locale-content rules, did I label them as repository-specific policy rather than standard Crowdin behavior?

If any answer is no, the change is not aligned and must be revised.

---

## Bottom Line

The correct GitHub-side localization model for this repository is:
- `zh-CN` is the source language
- `main` and `r-dev` are the source branches
- Crowdin returns translations through `l10n_${branch}` branches
- localization changes reach source branches through PRs
- sync timing depends on GitHub-side workflow execution
- repository-specific locale validation policy may exist, but it must be described as extra policy, not as the default Crowdin model

Coding Agent must preserve this model and must not drift into a direct-push workflow, a misleading sync description, or an over-generalized explanation of repository-specific validation rules.
