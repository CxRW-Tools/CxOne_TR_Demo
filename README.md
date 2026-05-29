# CxOne_TR_Demo.py

A setup script for Triage & Remediation Assist demos in Checkmarx One. It creates one or more copies of the demo repo in target GitHub orgs, gives you a window to import them into Checkmarx One with the right scan settings, then opens a PR with intentional code changes to trigger scanning and demonstrate AI-assisted triage and remediation.

## Prerequisites

- **Python 3.9+** and **git** on your PATH
- **[GitHub CLI](https://cli.github.com/)** installed and authenticated:

  ```powershell
  gh auth login
  ```

No `pip install` required — the script uses only the Python standard library.

## Usage

```powershell
python CxOne_TR_Demo.py <owner>/<repo>[,<owner>/<repo>,...]
python CxOne_TR_Demo.py --delete <owner>/<repo>[,<owner>/<repo>,...]
```

Targets are provided as a comma-separated list of `<owner>/<repo>` pairs. The owner can be a GitHub org or a personal account.

**Examples:**

```powershell
# Single target
python CxOne_TR_Demo.py MyOrg/ProjectHub

# Multiple targets
python CxOne_TR_Demo.py MyOrg/ProjectHub,OtherOrg/ProjectHub

# Tear down after the demo
python CxOne_TR_Demo.py --delete MyOrg/ProjectHub,OtherOrg/ProjectHub
```

## What to expect

### Setup flow

1. The script runs preflight checks — verifying GitHub auth, confirming each target repo doesn't already exist, and validating org access — before touching anything.

2. It creates each target repo and pushes the demo codebase.

3. It prints a reminder to import all repos into Checkmarx One before the PR scan fires:

   ```
   Import the following repos into Checkmarx One using Code Repository Integration:
     MyOrg/ProjectHub  (default branch: main)

   For each repo:
     - Enable Push/PR scan trigger, PR Decoration, and AI Triage & Remediation
     - Scan the default branch on project creation
   ```

   The script waits for you to confirm before proceeding.

4. It creates branch `feat/update-routes` with dependency downgrades and a new admin route, then opens a PR for each repo. This triggers the PR scan that demonstrates Triage & Remediation Assist.

### Teardown (`--delete`)

The `--delete` flag permanently deletes the specified repos. The flow:

1. Checks that each repo exists.
2. Verifies the repo was created by this tool by matching its description. Repos that don't match are flagged and require a separate confirmation before deletion.
3. Prompts for explicit confirmation before any deletion occurs.

Ctrl-C is safe at any point — no repos will be deleted without confirmation.

## Customizing the script

All configurable values — source repo, branch name, PR title, and file changes — live at the top of the script under `# ── hardcoded config ──`. Edit that block to adapt the demo for a different scenario.
