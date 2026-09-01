#!/usr/bin/env python3
"""
CxOne_TR_Demo: creates one or more copies of a template repo (see
SOURCE_PROFILES below) in target orgs/accounts under the given repo names,
pushes their contents, then branches, applies hardcoded changes, and opens a
pull request for each.

Usage:
  python CxOne_TR_Demo.py [--source <name>] <owner>/<repo>[,<owner>/<repo>,...]
  python CxOne_TR_Demo.py --delete <owner>/<repo>[,<owner>/<repo>,...]

Examples:
  python CxOne_TR_Demo.py CxRW/my-project
  python CxOne_TR_Demo.py --source totallysecure CxRW/my-project
  python CxOne_TR_Demo.py CxRW/repo1,CxRW/repo2,other-org/repo3
  python CxOne_TR_Demo.py --delete CxRW/my-project
  python CxOne_TR_Demo.py --delete CxRW/repo1,CxRW/repo2

If --source is omitted, the script prompts for which template to use.

Requires: gh CLI authenticated (run 'gh auth login' first)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# ── hardcoded config ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceProfile:
    """A template repo to clone, plus the demo changes to apply on top of it."""

    repo: str
    branch_name: str
    pr_title: str
    pr_body: str
    changes: list[tuple[str, str]]  # (path_in_repo, file_content_to_write)

    @property
    def description(self) -> str:
        """Set as the created repo's description; used to verify ownership on delete."""
        return f"Clone of {self.repo}"


SOURCE_PROFILES: dict[str, SourceProfile] = {
    "projecthub": SourceProfile(
        repo="CxRW-Templates/ProjectHub-TR",
        branch_name="feat/update-routes",
        pr_title="feat: update routes",
        pr_body="Added admin route and downgraded dependencies for compatibility",
        changes=[
    (
        "backend/requirements.txt",
        """\
Flask==1.1.4
Flask-SQLAlchemy==2.3.2
SQLAlchemy==1.4.0
Flask-CORS==4.0.0
Flask-JWT-Extended==3.13.1
psycopg2-binary==2.9.9
PyJWT==2.8.0
Werkzeug==1.0.1
python-dotenv==0.10.0
requests==2.20.0
lxml==4.9.3
Pillow==10.0.0
python-magic==0.4.27
PyYAML==6.0.1
Jinja2==2.11.3
MarkupSafe==2.0.1
""",
    ),
    (
        "backend/app.py",
        """\
# Main Flask application
import sys
import os

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from config import Config
from models import db, User, Project, Task
from database import init_db

# Import route handlers
from routes import auth, projects, tasks, documents, messages, api
from utils.logger import setup_logger
from utils.request_context import _get_request_id, get_request_context, set_request_metadata, get_request_start_time
from utils.jinja_filters import format_datetime, user_display_name, truncate, md5_hash, request_id_filter, format_file_size, role_badge

app = Flask(__name__)
app.config.from_object(Config)

# Simple CORS configuration that works with Flask-CORS 3.0.7
CORS(app,
     resources={r"/*": {
         "origins": "*",
         "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
         "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept"],
         "expose_headers": ["Content-Type", "Authorization"],
         "supports_credentials": False
     }})

# Initialize database
db.init_app(app)
init_db(app)

# Setup logging
logger = setup_logger(app)

# Register Jinja2 template filters
app.jinja_env.filters['format_datetime'] = format_datetime
app.jinja_env.filters['user_display_name'] = user_display_name
app.jinja_env.filters['truncate'] = truncate
app.jinja_env.filters['md5_hash'] = md5_hash
app.jinja_env.filters['request_id_filter'] = request_id_filter
app.jinja_env.filters['format_file_size'] = format_file_size
app.jinja_env.filters['role_badge'] = role_badge

# Initialize request context
@app.before_request
def init_request_context():
    \"\"\"Initialize request context\"\"\"
    from flask import _request_ctx_stack
    ctx = _request_ctx_stack.top
    if ctx is not None:
        # Initialize request ID
        _get_request_id()
        # Set request start time
        get_request_start_time()
        # Store request metadata
        set_request_metadata('ip_address', request.remote_addr)
        set_request_metadata('user_agent', request.headers.get('User-Agent', 'Unknown'))
        set_request_metadata('method', request.method)
        set_request_metadata('path', request.path)

# Register blueprints
app.register_blueprint(auth.bp, url_prefix='/api/auth')
app.register_blueprint(projects.bp, url_prefix='/api/projects')
app.register_blueprint(tasks.bp, url_prefix='/api/tasks')
app.register_blueprint(documents.bp, url_prefix='/api/documents')
app.register_blueprint(messages.bp, url_prefix='/api/messages')
app.register_blueprint(api.bp, url_prefix='/api/v1')

# Register analytics routes
from routes import analytics
app.register_blueprint(analytics.bp, url_prefix='/api')

# Create upload directory
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(Config.LOG_FILE), exist_ok=True)

@app.route('/')
def index():
    return jsonify({
        'message': 'ProjectHub API',
        'version': '1.0.0',
        'status': 'running'
    })

@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy'})

@app.errorhandler(404)
def not_found(error):
    \"\"\"404 error handler\"\"\"
    from utils.request_context import get_request_context
    ctx = get_request_context()
    request_id = ctx.request_id if ctx and hasattr(ctx, 'request_id') else 'N/A'

    # Support both JSON and HTML responses
    if request.headers.get('Accept', '').startswith('text/html'):
        return render_template('error.html',
                             error_code=404,
                             error_message='Page Not Found',
                             error_details='The requested resource could not be found.',
                             request_id=request_id), 404
    return jsonify({'error': 'Not found', 'request_id': request_id}), 404

@app.errorhandler(500)
def internal_error(error):
    \"\"\"500 error handler\"\"\"
    db.session.rollback()
    from utils.request_context import get_request_context
    ctx = get_request_context()
    request_id = ctx.request_id if ctx and hasattr(ctx, 'request_id') else 'N/A'

    logger.error(f"[{request_id}] Internal error: {str(error)}")

    # Support both JSON and HTML responses
    if request.headers.get('Accept', '').startswith('text/html'):
        return render_template('error.html',
                             error_code=500,
                             error_message='Internal Server Error',
                             error_details='An unexpected error occurred. Please try again later.',
                             request_id=request_id), 500
    return jsonify({'error': 'Internal server error', 'request_id': request_id}), 500

@app.route('/admin')
def admin_dashboard():
    \"\"\"Admin dashboard\"\"\"
    from utils.request_context import get_request_context
    ctx = get_request_context()
    request_id = ctx.request_id if ctx and hasattr(ctx, 'request_id') else 'N/A'

    # Get data
    users = User.query.all()
    projects = Project.query.all()
    tasks = Task.query.all()

    return render_template('admin.html',
                         users=users,
                         projects=projects,
                         tasks=tasks,
                         request_id=request_id)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
""",
    ),
        ],
    ),
    "totallysecure": SourceProfile(
        repo="CxRW-Templates/TotallySecure-TR",
        branch_name="feat/add-code-injection-endpoint",
        pr_title="feat: add code injection endpoint",
        pr_body="Added a code injection vulnerability endpoint for the AI Triage & Remediation demo",
        changes=[
    (
        "src/main/java/org/t246osslab/easybuggy4sb/vulnerabilities/CodeInjectionController.java",
        """\
package org.t246osslab.easybuggy4sb.vulnerabilities;

import java.util.Locale;

import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

import org.apache.commons.lang.StringUtils;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.ModelAndView;
import org.t246osslab.easybuggy4sb.Config;
import org.t246osslab.easybuggy4sb.controller.AbstractController;

@Controller
public class CodeInjectionController extends AbstractController {

	@RequestMapping(value = Config.APP_ROOT + "/codeijc")
	public ModelAndView process(@RequestParam(value = "jsonString", required = false) String jsonString,
			ModelAndView mav, Locale locale) {
		setViewAndCommonObjects(mav, locale, "codeinjection");
        if (!StringUtils.isBlank(jsonString)) {
            parseJson(jsonString, mav, locale);
        } else {
            mav.addObject("msg", msg.getMessage("msg.enter.json.string", null, locale));
        }
		return mav;
	}

    private void parseJson(String jsonString, ModelAndView mav, Locale locale) {
        /* Remove spaces and line breaks to parse as JSON */
        String convertedJsonString = jsonString.replaceAll(" ", "");
        convertedJsonString = convertedJsonString.replaceAll("\\r\\n", "");
        convertedJsonString = convertedJsonString.replaceAll("\\n", "");
        try {
            /* Parse the input string as JSON */
        	ScriptEngineManager manager = new ScriptEngineManager();
        	ScriptEngine scriptEngine = manager.getEngineByName("JavaScript");
        	scriptEngine.eval("JSON.parse('" + convertedJsonString + "')");
        	mav.addObject("msg", msg.getMessage("msg.valid.json", null, locale));
        } catch (ScriptException e) {
        	mav.addObject("errmsg", msg.getMessage("msg.invalid.json",
        			new String[] { e.getMessage() }, null, locale));
        } catch (Exception e) {
        	log.error("Exception occurs: ", e);
        	mav.addObject("errmsg", msg.getMessage("msg.invalid.json",
        			new String[] { e.getMessage() }, null, locale));
        }
    }
}
""",
    ),
        ],
    ),
}

# ── helpers ───────────────────────────────────────────────────────────────────

class GhApiError(RuntimeError):
    """Raised by gh_api on a non-2xx response. Carries the HTTP status when known."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def gh_api(method: str, endpoint: str, body: dict | None = None) -> dict:
    cmd = ["gh", "api", "-X", method, endpoint]
    inp = None
    if body is not None:
        cmd += ["--input", "-"]
        inp = json.dumps(body)
    r = subprocess.run(cmd, input=inp, capture_output=True, text=True)
    if r.returncode != 0:
        # Try to extract a human-readable message from the JSON error body
        detail = r.stderr.strip()
        status_match = re.search(r"\(HTTP (\d+)\)", detail)
        status = int(status_match.group(1)) if status_match else None
        try:
            err = json.loads(r.stdout)
            msg = err.get("message", "")
            errors = err.get("errors", [])
            if errors:
                sub = "; ".join(e.get("message", str(e)) for e in errors if isinstance(e, dict))
                if sub:
                    msg = f"{msg}: {sub}"
            if msg:
                detail = msg
        except (json.JSONDecodeError, AttributeError):
            pass
        raise GhApiError(detail, status=status)
    return json.loads(r.stdout) if r.stdout.strip() else {}


def run_gh(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    cmd = ["gh", *args]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {r.stderr or r.stdout}")
    return r


def run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["git", *args]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{r.stderr or r.stdout}")
    return r


def get_authenticated_username() -> str:
    """Return the login of the currently authenticated gh user. Doubles as an auth check."""
    try:
        user = gh_api("GET", "user")
    except FileNotFoundError:
        print("Error: gh CLI not found. Install it from https://cli.github.com/ and run 'gh auth login'.", file=sys.stderr)
        sys.exit(1)
    except RuntimeError:
        print("Error: gh is not authenticated. Run 'gh auth login' first.", file=sys.stderr)
        sys.exit(1)
    return user.get("login", "unknown")


def get_account_type(target_owner: str) -> str:
    """Return 'User' or 'Organization' for the given GitHub account name."""
    try:
        account = gh_api("GET", f"users/{target_owner}")
    except GhApiError as e:
        if e.status == 404:
            print(f"Error: GitHub account '{target_owner}' not found.", file=sys.stderr)
        else:
            print(f"Error: could not look up account '{target_owner}': {e}", file=sys.stderr)
        sys.exit(1)
    return account.get("type", "Organization")


def check_repo_does_not_exist(target_owner: str, repo_name: str) -> None:
    """Exit if the target repo already exists, to avoid a cryptic failure mid-run."""
    try:
        gh_api("GET", f"repos/{target_owner}/{repo_name}")
    except GhApiError as e:
        if e.status == 404:
            return  # repo doesn't exist — good
        print(f"Error: could not verify whether '{target_owner}/{repo_name}' exists: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Error: '{target_owner}/{repo_name}' already exists. Pick a different name or delete the existing repo first.", file=sys.stderr)
    sys.exit(1)


def check_org_access(target_owner: str, account_type: str, username: str) -> None:
    """Verify the authenticated user can create repos in the target account."""
    if account_type == "User":
        if username.lower() != target_owner.lower():
            print(f"Error: '{username}' cannot create repos in '{target_owner}' — you can only target your own account.", file=sys.stderr)
            sys.exit(1)
        return

    try:
        membership = gh_api("GET", f"user/memberships/orgs/{target_owner}")
    except RuntimeError:
        print(f"Error: '{username}' does not appear to be a member of the '{target_owner}' org. Verify your account has access.", file=sys.stderr)
        sys.exit(1)
    if membership.get("state") == "pending":
        print(f"Error: Your membership in '{target_owner}' is pending — accept the GitHub invite before running this script.", file=sys.stderr)
        sys.exit(1)


# ── core steps ────────────────────────────────────────────────────────────────

def create_repo(target_owner: str, repo_name: str, account_type: str, profile: SourceProfile) -> None:
    source = gh_api("GET", f"repos/{profile.repo}")
    body = {
        "name": repo_name,
        "description": profile.description,
        "private": source["private"],
        "auto_init": False,
    }
    if account_type == "User":
        gh_api("POST", "user/repos", body=body)
    else:
        gh_api("POST", f"orgs/{target_owner}/repos", body=body)
    print(f"  Created repo: {target_owner}/{repo_name}")


def clone_and_push(target_owner: str, repo_name: str, workdir: Path, profile: SourceProfile) -> str:
    """Clone source into workdir and push to the new repo. Returns default branch name."""
    run_gh("repo", "clone", profile.repo, ".", "--", "--depth", "1", cwd=workdir)

    run_git(workdir, "fetch", "origin", "--unshallow")
    default_branch = run_git(workdir, "rev-parse", "--abbrev-ref", "origin/HEAD").stdout.strip()
    default_branch = re.sub(r"^origin/", "", default_branch)

    workflows_dir = workdir / ".github" / "workflows"
    if workflows_dir.exists():
        run_git(workdir, "checkout", "-B", default_branch, f"origin/{default_branch}")
        run_git(workdir, "rm", "-rf", ".github/workflows")
        run_git(workdir, "commit", "-m", "chore: remove workflow files")
        print("  Removed .github/workflows before push")

    url = f"https://github.com/{target_owner}/{repo_name}.git"
    run_git(workdir, "remote", "add", "target", url)
    run_git(workdir, "push", "target", f"HEAD:refs/heads/{default_branch}")
    run_git(workdir, "remote", "remove", "target")
    print(f"  Pushed to {target_owner}/{repo_name}")
    return default_branch


def apply_and_pr(target_owner: str, repo_name: str, default_branch: str, workdir: Path, profile: SourceProfile) -> str | None:
    """Create branch, write hardcoded changes, commit, push, open PR. Returns PR URL or None."""
    url = f"https://github.com/{target_owner}/{repo_name}.git"

    run_git(workdir, "checkout", "-B", default_branch, f"origin/{default_branch}")
    run_git(workdir, "reset", "--hard")
    run_git(workdir, "clean", "-fd")

    run_git(workdir, "remote", "add", "target", url)
    run_git(workdir, "fetch", "target")
    run_git(workdir, "checkout", "-B", profile.branch_name, f"target/{default_branch}")
    run_git(workdir, "remote", "remove", "target")
    print(f"  Creating branch {profile.branch_name}")

    for repo_path, content in profile.changes:
        print(f"  Updating {repo_path}")
        dest = workdir / repo_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    run_git(workdir, "add", "-A")
    diff = run_git(workdir, "diff", "--cached", "--quiet", check=False)
    if diff.returncode == 0:
        return None  # nothing changed

    run_git(workdir, "commit", "-m", profile.pr_title)
    run_git(workdir, "remote", "add", "target", url)
    run_git(workdir, "push", "target", profile.branch_name)
    run_git(workdir, "remote", "remove", "target")

    pr = gh_api("POST", f"repos/{target_owner}/{repo_name}/pulls", body={
        "title": profile.pr_title,
        "body": profile.pr_body,
        "head": profile.branch_name,
        "base": default_branch,
    })
    return pr["html_url"]


# ── delete flow ───────────────────────────────────────────────────────────────

def delete_repos(targets: list[tuple[str, str]]) -> int:
    """Confirm and delete each target repo. Returns exit code."""
    try:
        # ── verify each repo exists and check ownership ───────────────────────
        print("Checking repos...")
        verified: list[tuple[str, str, bool]] = []  # (owner, repo, created_by_tool)
        for target_owner, repo_name in targets:
            tag = f"[{target_owner}/{repo_name}]"
            try:
                info = gh_api("GET", f"repos/{target_owner}/{repo_name}")
            except RuntimeError:
                print(f"{tag} Not found — skipping.", file=sys.stderr)
                continue
            known_descriptions = {p.description for p in SOURCE_PROFILES.values()}
            created_by_tool = info.get("description", "") in known_descriptions
            if created_by_tool:
                print(f"{tag} Found. Description matches — created by this tool.")
            else:
                actual_desc = info.get("description") or "(no description)"
                print(f"{tag} Found. Description does NOT match (got: {actual_desc!r}).")
            verified.append((target_owner, repo_name, created_by_tool))

        if not verified:
            print("\nNo repos to delete.", file=sys.stderr)
            return 1

        unrecognized = [(o, r) for o, r, owned in verified if not owned]

        print()

        # ── confirmation prompt ───────────────────────────────────────────────
        print("The following repos will be PERMANENTLY DELETED:")
        for o, r, _ in verified:
            print(f"  {o}/{r}")
        print()

        try:
            reply = input("Confirm deletion? [y/N]: ").strip().lower()
        except EOFError:
            reply = "n"
        if reply not in ("y", "yes"):
            print("Aborted. No repos were deleted.")
            return 0

        # ── second confirmation for unrecognized repos ────────────────────────
        if unrecognized:
            print()
            print("WARNING: the following repos were NOT created by this tool (description mismatch):")
            for o, r in unrecognized:
                print(f"  {o}/{r}")
            print()
            try:
                reply2 = input("Delete these unrecognized repos too? [y/N]: ").strip().lower()
            except EOFError:
                reply2 = "n"
            if reply2 not in ("y", "yes"):
                print("Skipping unrecognized repos.")
                unrecognized_set = set(unrecognized)
                verified = [(o, r, owned) for o, r, owned in verified if (o, r) not in unrecognized_set]

        if not verified:
            print("No repos to delete.")
            return 0

        # ── delete ────────────────────────────────────────────────────────────
        print()
        failed: list[str] = []
        for target_owner, repo_name, _ in verified:
            tag = f"[{target_owner}/{repo_name}]"
            print(f"{tag} Deleting...")
            result = subprocess.run(
                ["gh", "repo", "delete", f"{target_owner}/{repo_name}", "--yes"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                msg = result.stderr.strip() or result.stdout.strip()
                print(f"{tag} Failed: {msg}", file=sys.stderr)
                failed.append(f"{target_owner}/{repo_name}")
            else:
                print(f"{tag} Deleted.")

        if failed:
            print(f"\nThe following repos could not be deleted: {', '.join(failed)}", file=sys.stderr)
            return 1
        return 0

    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        return 130


# ── entry point ───────────────────────────────────────────────────────────────

def parse_targets(raw: str) -> list[tuple[str, str]]:
    """Parse a comma-separated list of owner/repo strings into (owner, repo) tuples."""
    targets = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "/" not in token or token.count("/") != 1:
            print(f"Error: '{token}' is not in the required <owner>/<repo> format.", file=sys.stderr)
            sys.exit(1)
        owner, repo = token.split("/", 1)
        if not owner or not repo:
            print(f"Error: '{token}' has an empty owner or repo name.", file=sys.stderr)
            sys.exit(1)
        targets.append((owner, repo))
    if not targets:
        print("Error: no valid targets provided.", file=sys.stderr)
        sys.exit(1)
    return targets


def prompt_source_choice() -> SourceProfile:
    """Ask the user which source profile to use when --source wasn't given."""
    keys = list(SOURCE_PROFILES)
    print("Which source repo do you want to use as the template?")
    for i, key in enumerate(keys, start=1):
        print(f"  {i}) {key} — {SOURCE_PROFILES[key].repo}")
    print()
    while True:
        try:
            reply = input(f"Select [1-{len(keys)}]: ").strip()
        except EOFError:
            print("Error: no --source given and input is not interactive.", file=sys.stderr)
            sys.exit(1)
        if reply.isdigit() and 1 <= int(reply) <= len(keys):
            return SOURCE_PROFILES[keys[int(reply) - 1]]
        print(f"Invalid selection: {reply!r}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Clone a template repo into one or more target repos, apply hardcoded changes, and open a PR for each. "
            "Use --delete to permanently remove repos created by this tool. "
            "Targets are provided as a comma-separated list of <owner>/<repo> pairs."
        )
    )
    parser.add_argument(
        "targets",
        metavar="owner/repo[,owner/repo,...]",
        help="One or more target repositories in <owner>/<repo> format, comma-separated (e.g. CxRW/repo1,CxRW/repo2)",
    )
    parser.add_argument(
        "--source",
        choices=list(SOURCE_PROFILES),
        help=(
            "Template repo to use: "
            + ", ".join(f"{key}={profile.repo}" for key, profile in SOURCE_PROFILES.items())
            + ". Prompted if omitted. Ignored with --delete."
        ),
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete the specified repos instead of creating them. Requires confirmation.",
    )
    args = parser.parse_args()

    targets = parse_targets(args.targets)

    username = get_authenticated_username()  # also doubles as auth check

    if args.delete:
        return delete_repos(targets)

    profile = SOURCE_PROFILES[args.source] if args.source else prompt_source_choice()
    print()

    # ── preflight: validate all targets before doing any work ────────────────
    print("Running preflight checks...")
    account_types: dict[tuple[str, str], str] = {}
    for target_owner, repo_name in targets:
        account_type = get_account_type(target_owner)
        check_repo_does_not_exist(target_owner, repo_name)
        check_org_access(target_owner, account_type, username)
        account_types[(target_owner, repo_name)] = account_type
    print("  All targets OK.")
    print()

    print(f"Source:   {profile.repo}")
    print(f"Targets:  {', '.join(f'{o}/{r}' for o, r in targets)}")
    print(f"Branch:   {profile.branch_name}")
    print(f"PR:       {profile.pr_title!r}")
    print()

    created_repos: list[str] = []
    default_branches: dict[tuple[str, str], str] = {}

    try:
        # ── phase 1: create and push all repos ───────────────────────────────
        for target_owner, repo_name in targets:
            tag = f"[{target_owner}/{repo_name}]"
            account_type = account_types[(target_owner, repo_name)]

            print(f"{tag} Creating repo...")
            create_repo(target_owner, repo_name, account_type, profile)
            created_repos.append(f"{target_owner}/{repo_name}")

            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp)
                print(f"{tag} Cloning source and pushing to target repo...")
                default_branch = clone_and_push(target_owner, repo_name, workdir, profile)
                default_branches[(target_owner, repo_name)] = default_branch
                print(f"{tag} Default branch: {default_branch}")
            print()

        # ── phase 2: shared pause for CxOne import ───────────────────────────
        print("Import the following repos into Checkmarx One using Code Repository Integration:")
        for target_owner, repo_name in targets:
            branch = default_branches[(target_owner, repo_name)]
            print(f"  {target_owner}/{repo_name}  (default branch: {branch})")
        print()
        print("For each repo:")
        print("  - Enable Push/PR scan trigger, PR Decoration, and AI Triage & Remediation")
        print("  - Scan the default branch on project creation")
        print()
        print("Waiting ", end="", flush=True)
        for _ in range(30):
            time.sleep(2)
            print(".", end="", flush=True)
        print()
        print()

        try:
            reply = input("Proceed with creating branches, applying changes, and opening PRs? [y/N]: ").strip().lower()
        except EOFError:
            reply = "n"
        if reply not in ("y", "yes"):
            print("Aborted.")
            return 0

        # ── phase 3: apply changes and open PRs for all repos ────────────────
        pr_urls: list[tuple[str, str | None]] = []
        for target_owner, repo_name in targets:
            tag = f"[{target_owner}/{repo_name}]"
            default_branch = default_branches[(target_owner, repo_name)]

            print(f"\n{tag} Applying changes...")
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp)
                run_gh("repo", "clone", profile.repo, ".", "--", "--depth", "1", cwd=workdir)
                run_git(workdir, "fetch", "origin", "--unshallow")
                pr_url = apply_and_pr(target_owner, repo_name, default_branch, workdir, profile)
            pr_urls.append((f"{target_owner}/{repo_name}", pr_url))

        print()
        print("Done.")
        for repo_slug, pr_url in pr_urls:
            if pr_url:
                print(f"  {repo_slug}: PR opened: {pr_url}")
            else:
                print(f"  {repo_slug}: No changes detected; PR skipped.")

    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        if created_repos:
            repos_list = ", ".join(f"'{r}'" for r in created_repos)
            print(f"Note: the following repos were created but the script did not complete. Delete them manually before retrying: {repos_list}", file=sys.stderr)
        return 130
    except RuntimeError as e:
        print(f"\nError: {e}", file=sys.stderr)
        if created_repos:
            repos_list = ", ".join(f"'{r}'" for r in created_repos)
            print(f"Note: the following repos were created but the script did not complete. Delete them manually before retrying: {repos_list}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
