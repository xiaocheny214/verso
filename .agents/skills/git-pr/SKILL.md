---
name: git-pr
description: Draft concise Git PR titles and descriptions from a committed branch diff by reading the current repository's PR template, preserving required sections, and omitting empty Optional sections. Verify branch-triggered CI locally and submit with GitHub CLI only after approval. Use whenever the user asks to prepare, review, create, or update PR metadata.
---

# Git PR Writing

Draft PR metadata from committed branch diff. Do not invent context or verification.

## Required Workflow

1. Inspect context:
   - `git status --short`
   - `git branch --show-current`
   - `git log --oneline -20`
   - `git remote -v`
   - `git branch -vv`
2. Resolve base: user input > upstream PR > `origin/HEAD` > `main`/`master`; ask only if ambiguity changes diff.
3. Inspect branch diff:
   - `git diff --stat <base>...HEAD`
   - `git diff --name-status <base>...HEAD`
   - `git diff --find-renames --find-copies <base>...HEAD`
4. Resolve and read the active PR template from the current repository:
   - Prefer `.github/pull_request_template.md` when it exists.
   - Otherwise inspect `.github/PULL_REQUEST_TEMPLATE/` and select the template matching the PR context. If multiple templates are equally applicable and the choice would change the PR body, ask the user.
   - Read the selected template in full, along with `CONTRIBUTING.md` and repository-local instructions. The repository template is the source of truth; never use a template hardcoded in this skill when a repository template exists.
5. Read relevant commits/files until behavior, implementation, and verification are clear.
6. Identify PR-triggered CI and run local equivalents where available.
7. Resolve the fork push target:
   - Existing PR: inspect head owner/repository/ref, then match its repository to a local remote.
   - New PR: match remote URL owner to `gh api user --jq .login`; do not trust remote name.
   - Verify push URL. No matching remote -> ask before creating a fork or adding a remote.
8. Draft title/body against the repository rules.
9. Create/edit PR only after explicit approval.

## Hard Rules

- Branch diff is source of truth.
- Ignore unrelated unstaged/uncommitted work unless user asks for working-tree draft.
- Do not invent tests, screenshots, issue links, metrics, or outcomes.
- If verification was not run, write `Not run (reason).` in a required Testing section.
- Do not omit or rename a required repository-template section. Preserve its order and checklist items.
- Strip prompt annotations such as `(Required)` and `(Optional)` from section headings in the final PR body.
- Treat Optional sections as conditional output: keep an Optional section only when the diff or verified context provides concrete content for it; otherwise remove the entire section, including its heading, placeholder, comments, and blank body. Do not leave empty Optional headings or filler such as `Not included` or `None`.
- Apply the same rule to optional checklist items or optional subsections: omit them when they have no applicable content, while preserving required checklist items exactly.
- For a required related-issue field, use only a user-provided or evidence-backed `Closes #123`, `Part of #123`, or `None`.
- Mark checklist items `[x]` only when the diff or recorded verification supports them; otherwise leave them unchecked and explain why.
- Keep reviewer-focused. Skip implementation trivia.
- Treat `origin` as upstream. Push only to verified fork remote; never push the PR branch to `origin`.
- Do not create, edit, merge, close, or push PR without explicit approval.
- Use English headings by default unless user requests localization.

## Local CI Before PR

- Identify triggered CI from changed files, workflow filters, scripts, and local config.
- Run closest available equivalents. Record exact commands/results in `Testing`; otherwise `Not run (reason)`.

## Submit With GitHub CLI

After approval to create PR:

```bash
git push -u <fork-remote> HEAD:<branch>
gh pr create --repo <upstream-owner/repository> --base <base-branch> --head <fork-owner>:<branch> --title "<type>(<scope>): <subject>" --body-file <body-file>
```

Add `--draft`, `--reviewer <handle>`, or `--web` only when requested.

## Title

```text
<type>(<scope>): <subject>
```

- Use narrowest type/scope matching branch diff.
- Imperative subject: `add`, `fix`, `remove`, `optimize`.
- Keep about <= 72 chars.
- Avoid vague words: `update`, `improve`, `misc`, `various`, `stuff`.

Types: `feat`, `fix`, `refactor`, `perf`, `docs`, `style`, `test`, `build`, `ci`, `chore`, `revert`.

## Body Generation

Generate the PR body from the active template resolved in the current repository. Preserve required section order, required headings, required checklist items, and any repository-specific wording that remains applicable. Remove HTML comments and prompt annotations such as `(Required)` and `(Optional)` from the final body.

For each Optional section, decide whether there is concrete content supported by the branch diff, verification results, or user-provided context. If there is none, delete that section as a whole. Do not replace it with a placeholder, `Not included`, `None`, or an empty heading. This cleanup happens after drafting and before `gh pr create`.

If no repository template exists, use the generic fallback below.

## Generic Body Fallback

```markdown
## Feature Description

- ...

## Implementation Approach

- ...

## Testing

- ...
```

Description: 1-4 bullets: purpose, behavior, observable effect. Implementation: 1-3 bullets: approach, boundaries, reused libs. Testing: only checks run/result; otherwise `Not run (reason)`.

If user asks only title or only body, return only requested piece.
