#!/usr/bin/env python3
"""
CxOne_TR_Demo: creates one copy of CxRW-Templates/ProjectHub-TR in a
target org under the given repo name, pushes its contents, then branches,
applies hardcoded changes, and opens a pull request.

Usage:
  python CxOne_TR_Demo.py <org>/<repo>

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
from pathlib import Path

# ── hardcoded config ──────────────────────────────────────────────────────────

SOURCE_REPO = "CxRW-Templates/ProjectHub-TR"
BRANCH_NAME = "feat/update-routes"
PR_TITLE    = "feat: update routes"
PR_BODY     = "Added admin route and downgraded dependencies for compatibility"

# Each entry: (path_in_repo, file_content_to_write)
CHANGES: list[tuple[str, str]] = [
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
]

# ── helpers ───────────────────────────────────────────────────────────────────

def check_gh_auth() -> None:
    try:
        r = subprocess.run(["gh", "api", "user"], capture_output=True, text=True)
    except FileNotFoundError:
        print("Error: gh CLI not found. Install it from https://cli.github.com/ and run 'gh auth login'.", file=sys.stderr)
        sys.exit(1)
    if r.returncode != 0:
        print("Error: gh is not authenticated. Run 'gh auth login' first.", file=sys.stderr)
        sys.exit(1)


def get_account_type(target_org: str) -> str:
    """Return 'User' or 'Organization' for the given GitHub account name."""
    try:
        account = gh_api("GET", f"users/{target_org}")
        return account.get("type", "Organization")
    except RuntimeError:
        print(f"Error: GitHub account '{target_org}' not found.", file=sys.stderr)
        sys.exit(1)


def check_org_access(target_org: str, account_type: str) -> None:
    """Verify the authenticated user can create repos in the target account."""
    try:
        user = gh_api("GET", "user")
        username = user.get("login", "unknown")
    except RuntimeError:
        username = "unknown"

    if account_type == "User":
        if username.lower() != target_org.lower():
            print(f"Error: '{username}' cannot create repos in '{target_org}' — you can only target your own account.", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            membership = gh_api("GET", f"user/memberships/orgs/{target_org}")
            if membership.get("state") == "pending":
                print(f"Error: Your membership in '{target_org}' is pending — accept the GitHub invite before running this script.", file=sys.stderr)
                sys.exit(1)
        except RuntimeError:
            print(f"Error: '{username}' does not appear to be a member of the '{target_org}' org. Verify your account has access.", file=sys.stderr)
            sys.exit(1)


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
        raise RuntimeError(detail)
    return json.loads(r.stdout) if r.stdout.strip() else {}


def run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["git", *args]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{r.stderr or r.stdout}")
    return r


# ── core steps ────────────────────────────────────────────────────────────────

def create_repo(target_org: str, repo_name: str, account_type: str) -> None:
    source = gh_api("GET", f"repos/{SOURCE_REPO}")
    body = {
        "name": repo_name,
        "description": f"Clone of {SOURCE_REPO}",
        "private": source["private"],
        "auto_init": False,
    }
    if account_type == "User":
        gh_api("POST", "user/repos", body=body)
    else:
        gh_api("POST", f"orgs/{target_org}/repos", body=body)
    print(f"  Created repo: {target_org}/{repo_name}")


def clone_and_push(target_org: str, repo_name: str, workdir: Path) -> str:
    """Clone source into workdir and push to the new repo. Returns default branch name."""
    r = subprocess.run(
        ["gh", "repo", "clone", SOURCE_REPO, ".", "--", "--depth", "1"],
        cwd=workdir, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh repo clone failed: {r.stderr or r.stdout}")

    run_git(workdir, "fetch", "origin", "--unshallow")
    default_branch = run_git(workdir, "rev-parse", "--abbrev-ref", "origin/HEAD").stdout.strip()
    default_branch = re.sub(r"^origin/", "", default_branch)

    workflows_dir = workdir / ".github" / "workflows"
    if workflows_dir.exists():
        run_git(workdir, "checkout", "-B", default_branch, f"origin/{default_branch}")
        run_git(workdir, "rm", "-rf", ".github/workflows")
        run_git(workdir, "commit", "-m", "chore: remove workflow files")
        print("  Removed .github/workflows before push")

    url = f"https://github.com/{target_org}/{repo_name}.git"
    run_git(workdir, "remote", "add", "target", url)
    run_git(workdir, "push", "target", f"HEAD:refs/heads/{default_branch}")
    run_git(workdir, "remote", "remove", "target")
    print(f"  Pushed to {target_org}/{repo_name}")
    return default_branch


def apply_and_pr(target_org: str, repo_name: str, default_branch: str, workdir: Path) -> str | None:
    """Create branch, write hardcoded changes, commit, push, open PR. Returns PR URL or None."""
    url = f"https://github.com/{target_org}/{repo_name}.git"

    run_git(workdir, "checkout", "-B", default_branch, f"origin/{default_branch}")
    run_git(workdir, "reset", "--hard")
    run_git(workdir, "clean", "-fd")

    run_git(workdir, "remote", "add", "target", url)
    run_git(workdir, "fetch", "target")
    run_git(workdir, "checkout", "-B", BRANCH_NAME, f"target/{default_branch}")
    run_git(workdir, "remote", "remove", "target")
    print(f"  Creating branch {BRANCH_NAME}")

    for repo_path, content in CHANGES:
        print(f"  Updating {repo_path}")
        dest = workdir / repo_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    run_git(workdir, "add", "-A")
    diff = run_git(workdir, "diff", "--cached", "--quiet", check=False)
    if diff.returncode == 0:
        return None  # nothing changed

    run_git(workdir, "commit", "-m", PR_TITLE)
    run_git(workdir, "remote", "add", "target", url)
    run_git(workdir, "push", "target", BRANCH_NAME)
    run_git(workdir, "remote", "remove", "target")

    pr = gh_api("POST", f"repos/{target_org}/{repo_name}/pulls", body={
        "title": PR_TITLE,
        "body": PR_BODY,
        "head": BRANCH_NAME,
        "base": default_branch,
    })
    return pr["html_url"]


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clone ProjectHub-TR into a target org/repo, apply hardcoded changes, open PR."
    )
    parser.add_argument(
        "target",
        metavar="org/repo",
        help="Target repository in the format <org>/<repo> (e.g. CxRW/my-project)",
    )
    args = parser.parse_args()

    if "/" not in args.target or args.target.count("/") != 1:
        parser.error("target must be in the format <org>/<repo>")
    target_org, repo_name = args.target.split("/", 1)

    check_gh_auth()
    account_type = get_account_type(target_org)
    check_org_access(target_org, account_type)

    print(f"Source:  {SOURCE_REPO}")
    print(f"Target:  {target_org}/{repo_name}")
    print(f"Branch:  {BRANCH_NAME}")
    print(f"PR:      {PR_TITLE!r}")
    print()

    try:
        print("Creating target repo...")
        create_repo(target_org, repo_name, account_type)

        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)

            print("Cloning source and pushing to target repo...")
            default_branch = clone_and_push(target_org, repo_name, workdir)
            print(f"Default branch: {default_branch}")

            print()
            print(f"Import {target_org}/{repo_name} into Checkmarx One using Code Repository Integration:")
            print(f"  Enable Push/PR scan trigger, PR Decoration, and AI Triage & Remediation")
            print(f"  Scan {default_branch} branch on project creation")
            print("  Waiting ", end="", flush=True)
            for _ in range(30):
                time.sleep(2)
                print(".", end="", flush=True)
            print()
            print()
            try:
                reply = input("Proceed with creating branch, applying changes, and opening PR? [y/N]: ").strip().lower()
            except EOFError:
                reply = "n"
            if reply not in ("y", "yes"):
                print("Aborted.")
                return 0

            print(f"\nApplying changes to {target_org}/{repo_name}...")
            pr_url = apply_and_pr(target_org, repo_name, default_branch, workdir)
            if pr_url:
                print(f"  PR opened: {pr_url}")
            else:
                print("  No changes detected; PR skipped.")

    except RuntimeError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
