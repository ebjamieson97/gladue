"""Publish the built website (site/) to the gh-pages branch and push it.

Run after scripts/site/build_site.py, from the project folder:
    .venv\\Scripts\\python.exe -X utf8 scripts\\site\\publish_site.py            # commit and push
    .venv\\Scripts\\python.exe -X utf8 scripts\\site\\publish_site.py --no-push  # commit only

The gh-pages branch holds the contents of site/ and nothing else. It is updated through a temporary git worktree,
so the main working folder is never switched away from main.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
BRANCH = "gh-pages"


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=check, text=True, capture_output=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true", help="commit to gh-pages but do not push")
    args = ap.parse_args()

    if not (SITE / "index.html").exists():
        sys.exit("site/index.html not found: run scripts/site/build_site.py first")

    source = git("rev-parse", "--short", "HEAD").stdout.strip()
    has_local = git("rev-parse", "--verify", "--quiet", BRANCH, check=False).returncode == 0
    if not has_local:
        git("fetch", "origin", BRANCH, check=False)
        if git("rev-parse", "--verify", "--quiet", f"origin/{BRANCH}", check=False).returncode == 0:
            git("branch", BRANCH, f"origin/{BRANCH}")
            has_local = True

    tmp = Path(tempfile.mkdtemp(prefix="gh-pages-"))
    work = tmp / "wt"
    try:
        if has_local:
            git("worktree", "add", str(work), BRANCH)
        else:
            git("worktree", "add", "--detach", str(work))
            git("checkout", "--orphan", BRANCH, cwd=work)

        # Replace everything in the worktree with the contents of site/
        for p in work.iterdir():
            if p.name == ".git":
                continue
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        shutil.copytree(SITE, work, dirs_exist_ok=True)
        (work / ".nojekyll").write_text("")   # serve files as they are, without Jekyll processing

        git("add", "-A", cwd=work)
        if git("diff", "--cached", "--quiet", cwd=work, check=False).returncode == 0:
            print("gh-pages already matches site/: nothing to publish")
            return
        git("commit", "-m", f"Publish site (built from main {source})", cwd=work)
        print(f"Committed site/ to {BRANCH}")
        if args.no_push:
            print("Not pushed (--no-push)")
        else:
            r = git("push", "origin", BRANCH, cwd=work, check=False)
            print(r.stdout + r.stderr)
            if r.returncode:
                sys.exit("push failed")
            print("Pushed. The site updates at https://ebjamieson97.github.io/gladue/ within a few minutes.")
    finally:
        git("worktree", "remove", "--force", str(work), check=False)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
