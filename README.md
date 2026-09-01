# CxOne_TR_Demo.py

A setup script for Triage & Remediation Assist demos in Checkmarx One. It creates one or more copies of a template repo in target GitHub orgs, gives you a window to import them into Checkmarx One with the right scan settings, then opens a PR with intentional code changes to trigger scanning and demonstrate AI-assisted triage and remediation.

## Source repos

Choose which template to clone with `--source`:

| `--source` value | Template repo | Demo change |
| --- | --- | --- |
| `projecthub` | [CxRW-Templates/ProjectHub-TR](https://github.com/CxRW-Templates/ProjectHub-TR) | Downgrades backend dependencies and adds an admin route |
| `totallysecure` | [CxRW-Templates/TotallySecure-TR](https://github.com/CxRW-Templates/TotallySecure-TR) | Adds a "JSON string validator" endpoint (framed as a legitimate feature; the implementation is exploitable via script injection) |

If `--source` is omitted, the script prompts you to choose interactively.

## Prerequisites

- **Python 3.9+** and **git** on your PATH
- **[GitHub CLI](https://cli.github.com/)** installed and authenticated:

  ```powershell
  gh auth login
  ```

No `pip install` required — the script uses only the Python standard library.

## Usage

```powershell
python CxOne_TR_Demo.py [--source projecthub|totallysecure] <owner>/<repo>[,<owner>/<repo>,...]
python CxOne_TR_Demo.py --delete <owner>/<repo>[,<owner>/<repo>,...]
```

Targets are provided as a comma-separated list of `<owner>/<repo>` pairs. The owner can be a GitHub org or a personal account. `--source` is ignored with `--delete` (deletion doesn't need to know which template a repo came from).

**Examples:**

```powershell
# Single target, prompted for which source to use
python CxOne_TR_Demo.py MyOrg/ProjectHub

# Single target, source given explicitly
python CxOne_TR_Demo.py --source totallysecure MyOrg/TotallySecure

# Multiple targets
python CxOne_TR_Demo.py --source projecthub MyOrg/ProjectHub,OtherOrg/ProjectHub

# Tear down after the demo
python CxOne_TR_Demo.py --delete MyOrg/ProjectHub,OtherOrg/ProjectHub
```

## What to expect

### Setup flow

1. The script verifies GitHub auth, then — if `--source` wasn't given — prompts you to pick a template repo.

2. It runs preflight checks — confirming each target repo doesn't already exist and validating org access — before touching anything.

3. It creates each target repo and pushes the demo codebase.

4. It prints a reminder to import all repos into Checkmarx One before the PR scan fires:

   ```
   Import the following repos into Checkmarx One using Code Repository Integration:
     MyOrg/ProjectHub  (default branch: main)

   For each repo:
     - Enable Push/PR scan trigger, PR Decoration, and AI Triage & Remediation
     - Scan the default branch on project creation
   ```

   The script waits for you to confirm before proceeding.

5. It creates a branch with the chosen source's demo change (see the [Source repos](#source-repos) table above), then opens a PR for each repo. This triggers the PR scan that demonstrates Triage & Remediation Assist.

### Teardown (`--delete`)

The `--delete` flag permanently deletes the specified repos. The flow:

1. Checks that each repo exists.
2. Verifies the repo was created by this tool by matching its description against any known source repo. Repos that don't match are flagged and require a separate confirmation before deletion.
3. Prompts for explicit confirmation before any deletion occurs.

Ctrl-C is safe at any point — no repos will be deleted without confirmation.

## Customizing the script

All configurable values live at the top of the script under `# ── hardcoded config ──`, in the `SOURCE_PROFILES` dict. Each entry is a `SourceProfile` with the source repo, branch name, PR title/body, and file changes for that scenario. Add a new entry (and it becomes selectable via `--source`) or edit an existing one to adapt the demo.
