# CxOne_TR_Demo.py

A setup script for Triage & Remediation Assist demos in Checkmarx One. It creates a copy of the demo repo in a target GitHub org, gives you a window to import it into Checkmarx One with the right scan settings, then opens a PR with intentional code changes to trigger scanning and demonstrate AI-assisted triage and remediation.

## Prerequisites

- **Python 3.9+** and **git** on your PATH
- **[GitHub CLI](https://cli.github.com/)** installed and authenticated:

  ```powershell
  gh auth login
  ```

No `pip install` required — the script uses only the Python standard library.

## Usage

```powershell
python CxOne_TR_Demo.py <org>/<repo>
```

**Example:**

```powershell
python CxOne_TR_Demo.py CxRW/ProjectHub2026
```

| Flag | Description |
|------|-------------|
| *(none)* | Full run: create repo, onboard reminder, then branch + PR |
| `--dry-run` | Create and push the repo only — skip the branch and PR step |

## What to expect

1. The script creates the target repo in the specified GitHub org and pushes the demo codebase.

2. It prints a reminder to import the repo into Checkmarx One before the PR scan fires:

   ```
   Import CxRW/ProjectHub2026 into Checkmarx One using Code Repository Integration:
     Enable Push/PR scan trigger, PR Decoration, and AI Triage & Remediation
     Scan main branch on project creation
   ```

   The script waits for you to confirm before proceeding.

3. It creates branch `feat/update-routes` with dependency downgrades and a new admin route, then opens a PR. This triggers the PR scan that demonstrates Triage & Remediation Assist.

## Customizing the script

All configurable values — source repo, branch name, PR title, and file changes — live at the top of the script under `# ── hardcoded config ──`. Edit that block to adapt the demo for a different scenario.
