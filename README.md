# CxOne_TR_Demo.py

Spins up one copy of `CxRW-Templates/ProjectHub-TR` in a target org, then creates a branch with hardcoded dependency and route changes and opens a pull request. Everything except the target repo name is baked into the script.

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

### Options

| Flag | Description |
|------|-------------|
| *(none)* | Full run: create repo, push, onboard reminder, branch + changes + PR |
| `--dry-run` | Create repo and push only; skip the branch/changes/PR step |

## What it does, step by step

1. **Checks `gh auth status`** — exits immediately with a clear message if the CLI isn't authenticated.

2. **Creates the target repo** in the specified org, inheriting the source repo's public/private visibility.

3. **Clones `CxRW-Templates/ProjectHub-TR`**, strips `.github/workflows/` (so no Actions run on the empty clone), and pushes the full history to the new repo.

4. **Prints an onboarding reminder** and waits 60 seconds (one dot per 2 s) before prompting:

   ```
   Import CxRW/ProjectHub2026 into Checkmarx One using Code Repository Integration:
     Enable Push/PR scan trigger, PR Decoration, and AI Triage & Remediation
     Scan main branch on project creation
     Waiting ..............................
   ```

   Use this time to import the repo into Checkmarx One before the PR scan fires.

5. **Prompts:** `Proceed with creating branch, applying changes, and opening PR? [y/N]`

6. **On `y`:** creates branch `feat/update-routes`, overwrites the two files below, commits, pushes, and opens the PR.

## Hardcoded changes

| Repo path | Change |
|-----------|--------|
| `backend/requirements.txt` | Pins all Flask dependencies to versions compatible with the app |
| `backend/app.py` | Adds admin route and updates CORS / request context setup |

The resulting PR is titled **`feat: update routes`** with body *"Added admin route and downgraded dependencies for compatibility"*.

## Changing the hardcoded values

All config lives at the top of the script under `# ── hardcoded config ──`:

```python
SOURCE_REPO = "CxRW-Templates/ProjectHub-TR"
BRANCH_NAME = "feat/update-routes"
PR_TITLE    = "feat: update routes"
PR_BODY     = "Added admin route and downgraded dependencies for compatibility"

CHANGES: list[tuple[str, str]] = [
    ("backend/requirements.txt", "...file content..."),
    ("backend/app.py",           "...file content..."),
]
```

Each `CHANGES` entry is a `(path_in_repo, full_file_content)` pair. Add, remove, or edit entries to change which files get replaced.

## Error handling

Failures (repo already exists, push rejected, API errors, etc.) print a single clean error line and exit with code 1 — no traceback:

```
Error: Repository creation failed.: name already exists on this account
```
