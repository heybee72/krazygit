#!/usr/bin/env python3
"""KrazyGit: manage your local Git projects without memorising commands.

Run:  double-click KrazyGit.app, or  python3 krazygit.py
Needs only Python 3.8+ and Git. Your project list is kept in ~/.krazygit.json, logs in ~/Library/Logs/KrazyGit.log.
Deleted branches, tags and stashes are parked under refs/krazygit-trash/ so they can be restored.
"""
import contextlib
from collections import Counter
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("KRAZYGIT_PORT", 7420))  # another port lets a test copy run beside your own
HERE = Path(__file__).resolve().parent
CONFIG = Path.home() / ".krazygit.json"
TOKEN = secrets.token_urlsafe(24)
TRASH = "refs/krazygit-trash"
LEGACY = ("easygit", Path.home() / ".easygit.json", "refs/easygit-trash")  # the name before KrazyGit: carried over, never lost
LOCK = threading.Lock()  # ponytail: one global lock serialises all git work; fine for one person clicking buttons
ENV = dict(os.environ, GIT_EDITOR="true", GIT_SEQUENCE_EDITOR="true", GIT_TERMINAL_PROMPT="0",
           GIT_PAGER="cat", LC_ALL="C", LANG="C")
if sys.platform == "darwin":  # when Git or ssh need a password, this same file shows a Mac dialog (see askpass)
    ENV.update(GIT_ASKPASS=str(Path(__file__).resolve()), SSH_ASKPASS=str(Path(__file__).resolve()), SSH_ASKPASS_REQUIRE="prefer")
# Background checks must never pop up a sign-in dialog out of nowhere.
NO_PROMPT = dict(ENV, GIT_ASKPASS="", SSH_ASKPASS="", SSH_ASKPASS_REQUIRE="never", GIT_SSH_COMMAND="ssh -o BatchMode=yes")
CMDS = []  # git commands run for the current request, shown in "What Git did"
OPS = {}
QUIET = {"repos", "pick_folder", "add_repo", "state", "diff", "log", "commit_info", "read_file",
         "bin", "lost", "reflog", "merge_preview", "stash_diff", "auto_fetch", "ping", "conflict_base"}
MOVES = {"commit", "merge", "rebase", "revert", "cherry_pick", "reset_to", "finish", "sync", "undo_commit"}  # undone by moving back
MARKERS = re.compile(r"^(<{7}|>{7}|={7})( |\r?$)", re.M)
IDLE_QUIT = 600  # seconds without any open window before KrazyGit quits itself
LAST_SEEN = time.monotonic()  # monotonic: time asleep doesn't count, so closing the lid never quits it
SERVER = None

# Plain-English explanations for the git errors people hit most. First match wins.
HINTS = [
    (r"tell me who you are|author identity unknown", "Git needs your name and email before it can commit. Add them in Settings."),
    (r"would be overwritten by", "You have uncommitted changes that would be lost. Commit or stash them first."),
    (r"not fully merged", "This branch has commits that aren't merged anywhere else."),
    (r"checked out at|cannot delete branch", "You can't delete the branch you're on. Switch to another branch first."),
    (r"not concluded your merge|merge_head exists|rebase-merge|already a rebase", "Finish or cancel the merge first (Conflicts tab)."),
    (r"CONFLICT|could not apply|automatic merge failed", "Some changes clash. Open the Conflicts tab to choose what to keep."),
    (r"unmerged|needs merge|resolve your current index", "Finish fixing the conflicts first."),
    (r"unrelated histories", "The server copy was started separately (often with its own README), so the two histories don't connect. "
     "Easiest fix: create a new, completely empty repository online and connect to that instead."),
    (r"\[rejected\]|non-fast-forward|fetch first", "The server has commits you don't have yet. Press Sync to combine them, then it uploads yours."),
    (r"no upstream|has no upstream|no tracking information", "This branch isn't on the server yet. Press Publish branch."),
    (r"src refspec .* does not match", "Make your first commit before uploading."),
    (r"could not resolve host|could not connect|network is unreachable|timed out", "Couldn't reach the server. Check your internet connection, then try again."),
    (r"repository not found|repository '.*' not found|returned error: 40[34]",
     "The server address is wrong, or your account can't open that repository. Check the address in Settings."),
    (r"could not read (from remote|username|password)|authentication failed|terminal prompts disabled|permission denied \(publickey\)|"
     r"host key verification failed", "Couldn't sign in to the server. Try again and enter your details when asked. "
     "For GitHub, use a personal access token instead of your password."),
    (r"no configured push destination|does not appear to be a git repository|no such remote",
     "This project isn't connected to GitHub (or another server) yet. Connect it in Settings."),
    (r"already exists", "That name is already taken. Pick another one."),
    (r"not a valid (branch )?name|is not a valid|bad refname", "Names can't contain spaces or any of these: ~ ^ : ? * [ \\"),
    (r"nothing to commit|no changes added to commit", "There's nothing new to commit."),
    (r"does not have any commits yet|ambiguous argument 'HEAD'|bad default revision|initial commit",
     "This project has no commits yet. Make your first commit."),
    (r"index\.lock", "Another Git program is busy with this project. Wait a moment and retry. If it's stuck, delete .git/index.lock."),
    (r"no local changes to save", "There's nothing to stash."),
    (r"not possible to fast-forward", "This branch has its own commits that aren't on the server, so it can't just download. Move them to a new branch first."),
]


class GitError(Exception):
    pass


def hint(message):
    return next((h for pattern, h in HINTS if re.search(pattern, message, re.I)), None)


def op(fn):
    OPS[fn.__name__] = fn
    return fn


def run(repo, *args, input=None, quiet=False, env=ENV, timeout=300):
    if not os.path.isdir(repo):
        raise GitError("That folder doesn't exist any more: " + repo)
    if not quiet:
        CMDS.append("git " + shlex.join(args))
    try:
        return subprocess.run(
            ["git", "-c", "core.quotepath=false", "-c", "color.ui=false", *args],
            cwd=repo, env=env, input=input, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, stdin=None if input is not None else subprocess.DEVNULL)
    except FileNotFoundError:
        raise GitError("Git isn't installed. On a Mac, open Terminal and run: xcode-select --install")
    except subprocess.TimeoutExpired:
        raise GitError("Git took too long, so KrazyGit stopped it.")


def git(repo, *args, ok=(0,), input=None, quiet=False):
    r = run(repo, *args, input=input, quiet=quiet)
    if r.returncode not in ok:
        raise GitError((r.stderr + r.stdout).strip() or "git %s failed" % args[0])
    return r.stdout


def conflicting(repo, *args):
    """Run a command that can stop on conflicts. Conflicts are a normal outcome, not an error."""
    r = run(repo, *args)
    if r.returncode == 0:
        return {"out": r.stdout}
    if git(repo, "diff", "--name-only", "--diff-filter=U", quiet=True).strip():
        return {"conflicts": True}
    raise GitError((r.stderr + r.stdout).strip())


def has_head(repo):
    return run(repo, "rev-parse", "-q", "--verify", "HEAD", quiet=True).returncode == 0


def arg(value):
    """A user-typed name must never be mistaken for a git option."""
    value = str(value or "").strip()
    if not value or value.startswith("-"):
        raise GitError("Please enter a valid name.")
    return value


def safe(repo, path):
    full = os.path.realpath(os.path.join(repo, path))
    if not full.startswith(os.path.realpath(repo) + os.sep):
        raise GitError("That file is outside the project.")
    return full


def clip(text, limit=300_000):
    return text if len(text) <= limit else text[:limit] + "\n\n... (too long, the rest is hidden)"


def backup(repo, why, *paths):
    """Stash uncommitted work (new files included) before anything that would throw it away."""
    if git(repo, "status", "--porcelain", "--", *paths, quiet=True).strip():
        git(repo, "stash", "push", "--include-untracked", "-m", "KrazyGit backup " + why, "--", *paths)
        return True
    return False


def trash(repo, kind, sha, name=""):
    """Park a deleted item under a hidden ref, so Git never garbage-collects it."""
    ref = "/".join(filter(None, [TRASH, kind, str(int(time.time() * 1000)), name]))
    git(repo, "update-ref", ref, sha, quiet=True)
    return {"ref": ref, "sha": sha, "name": name}


def saved():
    try:
        return json.loads(CONFIG.read_text())["repos"]
    except (OSError, ValueError, KeyError):
        return []


def save(repos):
    CONFIG.write_text(json.dumps({"repos": repos}, indent=2))


def remember(paths):
    repos = saved()
    save(repos + [p for p in paths if p not in repos])


def find_repos(root, depth=3):
    found = []
    for folder, subdirs, files in os.walk(root):
        if ".git" in subdirs or ".git" in files:
            found.append(folder)
            subdirs[:] = []
        elif folder[len(root):].count(os.sep) >= depth:
            subdirs[:] = []
        else:
            subdirs[:] = [d for d in subdirs if not d.startswith(".") and d != "node_modules"]
    return sorted(found)


# ---------- projects ----------

@op
def repos():
    return [{"path": p, "short": short(p), "name": os.path.basename(p), "missing": not os.path.isdir(p)} for p in saved()]


def short(path):
    """A folder as people say it: ~/code/app rather than /Users/name/code/app (also hides your username in screenshots)."""
    home = os.path.realpath(Path.home())
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path


@op
def pick_folder():
    if sys.platform != "darwin":
        raise GitError("The folder picker only works on macOS. Type the folder path instead.")
    r = subprocess.run(["osascript", "-e", "tell me to activate", "-e",
                        'POSIX path of (choose folder with prompt "Choose a code folder")'],
                       capture_output=True, text=True)
    return r.stdout.strip().rstrip("/") or None  # None = cancelled


@op
def add_repo(path):
    path = os.path.realpath(os.path.expanduser(path.strip()))
    if not os.path.isdir(path):
        raise GitError("That folder doesn't exist: " + path)
    r = run(path, "rev-parse", "--show-toplevel", quiet=True)
    if r.returncode == 0:
        remember([r.stdout.strip()])
        return {"added": r.stdout.strip()}
    return {"added": None, "path": path, "found": find_repos(path)}


@op
def add_many(paths):
    remember([p for p in paths if os.path.isdir(p)])


@op
def init(path):
    home = os.path.realpath(Path.home())
    too_big = {"/", home} | {os.path.join(home, d) for d in ("Desktop", "Documents", "Downloads", "Library", "Pictures", "Movies", "Music")}
    real = os.path.realpath(path)
    if real in too_big:
        raise GitError("That's your whole %s folder, not one project. Tracking it would pull in everything inside. "
                       "Pick the folder of the specific project instead." % ("home" if real == home else os.path.basename(real) or "computer"))
    git(path, "init", "-b", "main")
    remember([path])
    return path


@op
def forget_repo(repo):
    save([p for p in saved() if p != repo])


@op
def reveal(repo):
    subprocess.Popen([{"darwin": "open", "win32": "explorer"}.get(sys.platform, "xdg-open"), repo])


def follow_counts(repo, branch):
    """For a download-only current branch: how far it is from the copy it downloads from."""
    if branch not in download_only(repo, [branch]) or not (src := follow_ref(repo, branch)):
        return None
    ahead, behind = git(repo, "rev-list", "--left-right", "--count", "HEAD..." + src, quiet=True).split()
    return {"ref": src, "ahead": int(ahead), "behind": int(behind)}


@op
def state(repo):
    gitdir = git(repo, "rev-parse", "--absolute-git-dir").strip()
    old = git(repo, "for-each-ref", "--format=%(refname) %(objectname)", LEGACY[2], quiet=True).split("\n")
    moves = "".join("create %s%s %s\ndelete %s\n" % (TRASH, ref[len(LEGACY[2]):], sha, ref) for ref, sha in (l.split() for l in old if l))
    if moves:
        git(repo, "update-ref", "--stdin", input=moves, quiet=True)
    head, files, i = {}, [], 0
    parts = git(repo, "status", "--porcelain=v2", "--branch", "-z").split("\0")
    while i < len(parts):
        entry = parts[i]
        i += 1
        if entry.startswith("# "):
            key, _, value = entry[2:].partition(" ")
            head[key] = value
        elif entry[:2] in ("1 ", "2 ", "u "):
            n = {"1": 8, "2": 9, "u": 10}[entry[0]]
            f = entry.split(" ", n)
            files.append({"path": f[n], "x": f[1][0], "y": f[1][1], "conflict": entry[0] == "u"})
            if entry[0] == "2":
                files[-1]["orig"] = parts[i]
                i += 1
        elif entry.startswith("? "):
            files.append({"path": entry[2:], "x": "?", "y": "?", "conflict": False})
    for f in files:  # sizes let the page warn before a huge file gets committed
        full = os.path.join(repo, f["path"])
        f["size"] = os.path.getsize(full) if os.path.isfile(full) else 0
    born = head.get("branch.oid") != "(initial)"
    ahead, behind = (int(n[1:]) for n in head.get("branch.ab", "+0 -0").split())
    fmt = "%(refname:short)%00%(upstream:short)%00%(upstream:track,nobracket)%00%(committerdate:relative)%00%(subject)%00%(committerdate:unix)"
    branches = [dict(zip(("name", "upstream", "track", "when", "subject", "ts"), line.split("\0"))) for line in
                git(repo, "for-each-ref", "refs/heads", "--sort=-committerdate", "--format=" + fmt).splitlines()]
    fmt = "%(refname)%00%(refname:lstrip=2)%00%(committerdate:relative)%00%(subject)%00%(committerdate:unix)"
    remote_branches = [dict(zip(("name", "when", "subject", "ts"), line.split("\0")[1:])) for line in
                       git(repo, "for-each-ref", "refs/remotes", "--sort=-committerdate", "--format=" + fmt).splitlines()
                       if not line.split("\0")[0].endswith("/HEAD")]
    remotes = {}
    for line in git(repo, "remote", "-v").splitlines():
        name, url = line.split()[:2]
        remotes.setdefault(name, url)
    doing = next((kind for kind, marker in (("merge", "MERGE_HEAD"), ("rebase", "rebase-merge"), ("rebase", "rebase-apply"),
                                            ("cherry-pick", "CHERRY_PICK_HEAD"), ("revert", "REVERT_HEAD"))
                  if os.path.exists(os.path.join(gitdir, marker))), None)
    prev = run(repo, "rev-parse", "--abbrev-ref", "@{-1}", quiet=True).stdout.strip()
    return {
        "name": os.path.basename(repo), "path": repo, "short_path": short(repo), "files": files, "doing": doing, "has_commits": born,
        "branch": head.get("branch.head"), "detached": head.get("branch.head") == "(detached)",
        "upstream": head.get("branch.upstream"), "ahead": ahead, "behind": behind, "branches": branches,
        "merged": git(repo, "branch", "--merged", "HEAD", "--format=%(refname:short)").split() if born else [],
        "remote_branches": remote_branches,
        "remote_merged": git(repo, "branch", "-r", "--merged", "HEAD", "--format=%(refname:lstrip=2)").split() if born else [],
        "stashes": [dict(zip(("ref", "msg", "when"), line.split("\x1f")))
                    for line in git(repo, "stash", "list", "--format=%gd%x1f%gs%x1f%cr").splitlines()],
        "tags": [dict(zip(("name", "when", "subject"), line.split("\0"))) for line in
                 git(repo, "for-each-ref", "refs/tags", "--sort=-creatordate",
                     "--format=%(refname:short)%00%(creatordate:relative)%00%(subject)").splitlines()],
        "remotes": remotes,
        "main_remote": main_remote(repo) if remotes else None,
        "download_only": sorted(download_only(repo, [b["name"] for b in branches])),
        "follow": follow_counts(repo, head.get("branch.head")) if remotes else None,
        "who": {k: git(repo, "config", "user." + k, ok=(0, 1)).strip() for k in ("name", "email")},
        "last_message": git(repo, "log", "-1", "--format=%B").strip() if born else "",
        "prev_branch": prev if prev in {b["name"] for b in branches} else None,
    }


# ---------- changes ----------

@op
def diff(repo, path, orig=None, untracked=False):
    if untracked:
        if os.path.isdir(safe(repo, path)):
            return "New folder with these files:\n\n" + git(repo, "ls-files", "--others", "--exclude-standard", "--", path)
        return clip(git(repo, "diff", "--no-index", "--", "/dev/null", path, ok=(0, 1)))
    paths = [orig, path] if orig else [path]
    if has_head(repo):
        return clip(git(repo, "diff", "-M", "HEAD", "--", *paths))
    return clip(git(repo, "diff", "--cached", "--", *paths) + git(repo, "diff", "--", *paths))


@op
def stage(repo, paths=None):
    git(repo, "add", "-A", "--", *(paths or ["."]))


@op
def unstage(repo, paths=None):
    paths = paths or ["."]
    if has_head(repo):
        git(repo, "restore", "--staged", "--", *paths)
    else:
        git(repo, "rm", "-r", "-q", "--cached", "--", *paths)


@op
def discard(repo, paths):
    if backup(repo, "of discarded changes: " + ", ".join(paths)[:150], *paths):
        return {"backup": git(repo, "rev-parse", "stash@{0}", quiet=True).strip()}


@op
def commit(repo, message="", amend=False, everything=False):
    if everything:
        git(repo, "add", "-A")
    if amend and not message.strip():
        git(repo, "commit", "--amend", "--no-edit")
    elif not message.strip():
        raise GitError("Write a short message describing what you changed.")
    else:
        git(repo, "commit", *(["--amend"] if amend else []), "-m", message.strip())


@op
def undo_commit(repo):
    if run(repo, "rev-parse", "-q", "--verify", "HEAD~1", quiet=True).returncode == 0:
        git(repo, "reset", "--soft", "HEAD~1")
    else:
        git(repo, "update-ref", "-d", "HEAD")  # undoing the very first commit


@op
def ignore(repo, pattern):
    gitignore = Path(repo, ".gitignore")
    old = gitignore.read_text() if gitignore.exists() else ""
    gitignore.write_text(old + ("\n" if old and not old.endswith("\n") else "") + pattern.strip() + "\n")
    CMDS.append("echo %s >> .gitignore" % shlex.quote(pattern.strip()))


# ---------- branches ----------

@op
def create_branch(repo, name, start=None):
    git(repo, "switch", "-c", arg(name), *([arg(start)] if start else []))


@op
def switch(repo, name, remote=False, stash_first=False):
    name = arg(name)
    if stash_first:
        current = git(repo, "branch", "--show-current", quiet=True).strip()
        git(repo, "stash", "push", "--include-untracked", "-m", "KrazyGit: left on " + current)
    if not remote:
        return git(repo, "switch", name)
    local = name.split("/", 1)[1]
    if run(repo, "rev-parse", "-q", "--verify", "refs/heads/" + local, quiet=True).returncode == 0:
        return git(repo, "switch", local)
    git(repo, "switch", "--track", name)


@op
def rename_branch(repo, old, new):
    git(repo, "branch", "-m", arg(old), arg(new))


@op
def delete_branch(repo, name, force=False):
    name = arg(name)
    sha = git(repo, "rev-parse", "refs/heads/" + name, quiet=True).strip()
    git(repo, "branch", "-D" if force else "-d", name)
    return trash(repo, "branch", sha, name)


@op
def merge_preview(repo, name):
    name = arg(name)
    count = int(git(repo, "rev-list", "--count", "HEAD.." + name).strip())
    r = run(repo, "merge-tree", "--write-tree", "--name-only", "HEAD", name, quiet=True)
    clashes = sorted(set(r.stdout.split("\n\n")[0].splitlines()[1:])) if r.returncode == 1 else []
    return {"count": count, "clashes": clashes}


@op
def merge(repo, name):
    return conflicting(repo, "merge", "--no-edit", arg(name))


@op
def rebase(repo, name):
    return conflicting(repo, "rebase", arg(name))


@op
def finish(repo, kind, action):
    if kind not in ("merge", "rebase", "cherry-pick", "revert") or action not in ("continue", "abort", "skip"):
        raise GitError("Unknown action.")
    return conflicting(repo, kind, "--" + action)


# ---------- conflicts ----------

@op
def read_file(repo, path):
    data = Path(safe(repo, path)).read_bytes()
    if b"\0" in data[:8000]:
        return {"binary": True}
    return {"text": data.decode("utf-8", "surrogateescape")}  # round-trips non-UTF-8 bytes losslessly


@op
def save_file(repo, path, text):
    Path(safe(repo, path)).write_bytes(text.encode("utf-8", "surrogateescape"))
    git(repo, "add", "--", path)


@op
def take(repo, path, side):
    stage_no = {"ours": "2", "theirs": "3"}[side]
    stages = {line.split()[2] for line in git(repo, "ls-files", "-u", "--", path, quiet=True).splitlines()}
    if not stages:
        raise GitError("This file isn't in conflict any more.")
    if stage_no in stages:
        git(repo, "checkout", "--" + side, "--", path)
        git(repo, "add", "--", path)
    else:  # that side deleted the file
        git(repo, "rm", "-q", "--", path)


@op
def conflict_base(repo, path):
    """The clash markers again, but with the original text (from before either side changed it) in each clash.
    Rebuilt from Git's own copies of the three versions, so the file on disk isn't touched."""
    stages = {}
    for line in git(repo, "ls-files", "-u", "--", path, quiet=True).splitlines():
        mode, sha, stage = line.split("\t")[0].split()
        stages[stage] = sha
    if set(stages) != {"1", "2", "3"}:
        return None  # added or deleted on one side: there is no shared original
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for stage in "213":  # yours, the original, incoming: the order merge-file expects
            files.append(os.path.join(tmp, stage))
            Path(files[-1]).write_text(git(repo, "cat-file", "blob", stages[stage], quiet=True))
        r = run(repo, "merge-file", "-p", "--zdiff3", *files, quiet=True)
    return r.stdout if 0 <= r.returncode < 128 else None  # older Git without zdiff3: no originals, nothing breaks


@op
def mark_resolved(repo, path):
    full = safe(repo, path)
    if os.path.exists(full) and MARKERS.search(Path(full).read_text(errors="replace")):
        raise GitError("This file still has conflict markers (<<<<<<< ======= >>>>>>>). Finish editing it first.")
    git(repo, "add", "-A", "--", path)


# ---------- history ----------

@op
def log(repo, ref="HEAD", limit=100, search=""):
    if not has_head(repo):
        return []
    args = ["log", "--format=%H%x1f%h%x1f%an%x1f%ar%x1f%s%x1f%D%x1e", "-n", str(int(limit)),
            "--decorate-refs-exclude=" + TRASH + "/*"]
    if search:
        args += ["-i", "--grep=" + search]
    args += ["--exclude=" + TRASH + "/*", "--all"] if ref == "--all" else [arg(ref)]
    rows = (r.strip("\n").split("\x1f") for r in git(repo, *args).split("\x1e"))
    return [dict(zip(("sha", "short", "author", "when", "subject", "refs"), r)) for r in rows if len(r) == 6]


@op
def commit_info(repo, sha):
    sha = arg(sha)
    meta = git(repo, "show", "-s", "--date=format:%a %d %b %Y, %H:%M", "--format=%H%x1f%an%x1f%ad%x1f%B", sha).split("\x1f", 3)
    tokens = git(repo, "show", "--format=", "--name-status", "-z", "-M", "--diff-merges=first-parent", sha).split("\0")
    files, i = [], 0
    while i < len(tokens):
        status = tokens[i].strip()
        if not status:
            i += 1
        elif status[0] in "RC":
            files.append({"status": status[0], "orig": tokens[i + 1], "path": tokens[i + 2]})
            i += 3
        else:
            files.append({"status": status[0], "path": tokens[i + 1]})
            i += 2
    patch = git(repo, "show", "--format=", "--patch", "-M", "--diff-merges=first-parent", sha)
    return {"sha": meta[0], "author": meta[1], "date": meta[2], "message": meta[3].strip(), "files": files, "patch": clip(patch)}


def is_merge(repo, sha):
    return len(git(repo, "rev-list", "--parents", "-n1", sha, quiet=True).split()) > 2


@op
def revert(repo, sha):
    sha = arg(sha)
    return conflicting(repo, "revert", "--no-edit", *(["-m", "1"] if is_merge(repo, sha) else []), sha)


@op
def cherry_pick(repo, sha):
    sha = arg(sha)
    return conflicting(repo, "cherry-pick", *(["-m", "1"] if is_merge(repo, sha) else []), sha)


@op
def reset_to(repo, sha, mode="mixed"):
    """soft/mixed keep your files as they are; keep refuses to touch uncommitted work; hard backs it up first."""
    sha = arg(sha)
    if mode not in ("soft", "mixed", "keep", "hard"):
        raise GitError("Unknown action.")
    backed_up = mode == "hard" and backup(repo, "before going back to " + sha[:7])
    git(repo, "reset", "-q", "--" + mode, sha)
    return {"backup": backed_up}


@op
def checkout_commit(repo, sha):
    git(repo, "switch", "--detach", arg(sha))


@op
def restore_file(repo, sha, path, deleted=False):
    safe(repo, path)
    backup(repo, "before restoring " + path, path)
    git(repo, "checkout", arg(sha) + ("^" if deleted else ""), "--", path)


# ---------- stashes and tags ----------

def stash_ref(ref):
    if not re.fullmatch(r"stash@\{\d+\}|[0-9a-f]{40}", ref or ""):
        raise GitError("Unknown stash.")
    return ref


@op
def stash_save(repo, message=""):
    git(repo, "stash", "push", "--include-untracked", *(["-m", message] if message else []))


@op
def stash_apply(repo, ref, pop=False):
    return conflicting(repo, "stash", "pop" if pop else "apply", stash_ref(ref))


@op
def stash_drop(repo, ref):
    sha = git(repo, "rev-parse", stash_ref(ref), quiet=True).strip()
    git(repo, "stash", "drop", ref)
    return trash(repo, "stash", sha)


@op
def stash_diff(repo, ref):
    return clip(git(repo, "stash", "show", "-p", "--include-untracked", stash_ref(ref)))


@op
def create_tag(repo, name, sha=None):
    name = arg(name)
    git(repo, "tag", "-a", "-m", name, name, *([arg(sha)] if sha else []))


@op
def delete_tag(repo, name):
    name = arg(name)
    sha = git(repo, "rev-parse", "refs/tags/" + name, quiet=True).strip()
    git(repo, "tag", "-d", name)
    return trash(repo, "tag", sha, name)


# ---------- remotes ----------

@op
def sync(repo, force=False):
    """One button for fetch, pull and push: bring in what's new on the server, then upload your commits."""
    remote = main_remote(repo)
    git(repo, "fetch", "--all", "--prune")
    tracked = run(repo, "rev-parse", "-q", "--verify", "@{u}", quiet=True).returncode == 0
    branch = git(repo, "branch", "--show-current", quiet=True).strip()
    if branch in download_only(repo, [branch]):  # e.g. master: always get updates from the team server, never upload
        src = follow_ref(repo, branch)
        if not src:
            raise GitError("%s only downloads, but the server doesn't have it." % branch)
        relinked = run(repo, "rev-parse", "--abbrev-ref", "@{u}", quiet=True).stdout.strip() != src
        if relinked:
            git(repo, "branch", "--set-upstream-to", src, quiet=True)
        got = int(git(repo, "rev-list", "--count", "HEAD.." + src, quiet=True))
        if got:
            git(repo, "merge", "--ff-only", "--autostash", src)
        return {"got": got, "sent": 0, "download_only": True, "relinked": src if relinked else None}
    if not tracked and run(repo, "rev-parse", "-q", "--verify", "refs/remotes/%s/%s" % (remote, branch), quiet=True).returncode == 0:
        # The server already has this branch (typically a README made on GitHub): link to it and combine, don't fail.
        git(repo, "branch", "--set-upstream-to", "%s/%s" % (remote, branch), quiet=True)
        tracked = True
    got = int(git(repo, "rev-list", "--count", "HEAD..@{u}", quiet=True)) if tracked else 0
    if got and not force:
        res = conflicting(repo, "merge", "--no-edit", "--autostash", "--allow-unrelated-histories", "@{u}")
        if res.get("conflicts"):
            return dict(res, got=got)
    sent = int(git(repo, "rev-list", "--count", "@{u}..HEAD", quiet=True)) if tracked else -1  # -1: newly published
    flags = ["--follow-tags"] + (["--force-with-lease"] if force else [])
    if not tracked:
        git(repo, "push", *flags, "-u", remote, "HEAD")
    elif sent or force:  # to the server this branch is linked to, the same one "ahead/behind" is counted against
        git(repo, "push", *flags, git(repo, "config", "branch.%s.remote" % branch, quiet=True).strip())
    return {"got": got, "sent": sent}


@op
def fetch(repo):
    git(repo, "fetch", "--all", "--prune")


def download_only(repo, names):
    """Which of these branches only ever download, never upload: your choice per branch, else master/main
    when the project has several servers (a team copy plus your own), where nobody pushes to master."""
    explicit = {}
    for line in git(repo, "config", "--get-regexp", r"^branch\..*\.(easygit|krazygit)downloadonly$", ok=(0, 1), quiet=True).splitlines():
        key, _, value = line.partition(" ")
        explicit[key[len("branch."):key.rindex(".")]] = value.strip() == "true"
    several = len(git(repo, "remote", quiet=True).split()) > 1
    return {n for n in names if explicit.get(n, several and n in ("master", "main"))}


def follow_ref(repo, branch):
    """Where a download-only branch gets its updates: the main server's copy if it has one, else its own link."""
    main = main_remote(repo)
    if run(repo, "rev-parse", "-q", "--verify", "refs/remotes/%s/%s" % (main, branch), quiet=True).returncode == 0:
        return "%s/%s" % (main, branch)
    r = run(repo, "rev-parse", "--abbrev-ref", "@{u}", quiet=True)
    return r.stdout.strip() if r.returncode == 0 else None


@op
def set_download_only(repo, name, on):
    git(repo, "config", "branch.%s.krazygitDownloadOnly" % arg(name), "true" if on else "false")


@op
def move_commits(repo, name):
    """Commits made on a download-only branch by mistake: put them on a new branch, and bring the branch
    back in line with the server. Uncommitted work comes along."""
    name, branch = arg(name), git(repo, "branch", "--show-current", quiet=True).strip()
    src = follow_ref(repo, branch)
    if not src:
        raise GitError("There's no server copy of %s to go back to." % branch)
    git(repo, "branch", name)
    git(repo, "reset", "-q", "--keep", src)
    git(repo, "switch", name)


def main_remote(repo):
    """Where new branches get published: the one you picked in Settings, else wherever most of your
    branches already go, else origin. Never just "origin" when the project clearly uses another."""
    remotes = git(repo, "remote", quiet=True).split()
    if not remotes:
        raise GitError("no configured push destination")
    picked = run(repo, "config", "--get", "remote.pushDefault", quiet=True).stdout.strip()
    if picked in remotes:
        return picked
    used = Counter(u.split("/", 1)[0] for u in git(repo, "for-each-ref", "refs/heads", "--format=%(upstream:short)", quiet=True).split())
    used = sorted(((n, r) for r, n in used.items() if r in remotes), reverse=True)
    return used[0][1] if used else "origin" if "origin" in remotes else remotes[0]


@op
def set_main_remote(repo, name):
    git(repo, "config", "remote.pushDefault", arg(name))


@op
def link_to(repo, remote):
    """Make the current branch sync with another server from now on. If that server already has this branch,
    just follow it (nothing is uploaded); otherwise upload the branch there."""
    remote = arg(remote)
    branch = git(repo, "branch", "--show-current", quiet=True).strip()
    if run(repo, "rev-parse", "-q", "--verify", "refs/remotes/%s/%s" % (remote, branch), quiet=True).returncode == 0:
        git(repo, "branch", "--set-upstream-to", "%s/%s" % (remote, branch))
        return {"uploaded": False}
    git(repo, "push", "-u", remote, "HEAD")
    return {"uploaded": True}


@op
def publish_branches(repo, names):
    git(repo, "push", "-u", main_remote(repo), *[arg(n) for n in names])


@op
def track_branches(repo, names):
    """Make local copies of server branches without switching to them."""
    for name in names:
        local = arg(name).split("/", 1)[1]
        if run(repo, "rev-parse", "-q", "--verify", "refs/heads/" + local, quiet=True).returncode:
            git(repo, "branch", "--track", local, name)


@op
def delete_remote_branches(repo, names):
    """Delete branches on the server. Each one is parked in the Recycle bin first, so it can be put back."""
    groups, deleted = {}, []
    for name in names:
        remote, _, short = arg(name).partition("/")
        groups.setdefault(remote, []).append((name, short, git(repo, "rev-parse", "refs/remotes/" + name, quiet=True).strip()))
    for remote, items in groups.items():
        parked = [(trash(repo, "remote", sha, name), name) for name, _, sha in items]
        r = run(repo, "push", remote, "--delete", *[short for _, short, _ in items])
        for entry, name in parked:  # a failed push can still delete some of them; keep only those in the bin
            if r.returncode and run(repo, "rev-parse", "-q", "--verify", "refs/remotes/" + name, quiet=True).returncode == 0:
                forget(repo, entry["ref"])
            else:
                deleted.append(entry)
        if r.returncode:
            raise GitError((r.stderr + r.stdout).strip())
    return deleted


@op
def auto_fetch(repo):
    """Quietly check the server for new commits so the suggestions stay accurate. Failures are ignored."""
    with contextlib.suppress(GitError):
        if git(repo, "remote", quiet=True).split():
            run(repo, "fetch", "--all", "--prune", "--quiet", quiet=True, env=NO_PROMPT, timeout=30)


@op
def add_remote(repo, name, url):
    git(repo, "remote", "add", arg(name), arg(url))


@op
def remove_remote(repo, name):
    git(repo, "remote", "remove", arg(name))


# ---------- recycle bin and undo ----------

@op
def bin(repo):
    items, names = [], set()
    for line in git(repo, "for-each-ref", "--format=%(refname)%00%(objectname)%00%(contents:subject)", TRASH).splitlines():
        ref, sha, subject = line.split("\0")
        kind, stamp, name = (ref[len(TRASH) + 1:].split("/", 2) + [""])[:3]
        items.append({"ref": ref, "kind": kind, "name": name, "sha": sha, "subject": subject,
                      "deleted": int(stamp) // 1000, "source": "bin"})
        names.add(name)
    items.sort(key=lambda x: -x["deleted"])
    if not has_head(repo):
        return items
    # Branches deleted outside KrazyGit: the HEAD reflog still remembers where they pointed when you left them.
    existing = set(git(repo, "for-each-ref", "refs/heads", "--format=%(refname:short)").split())
    rows = [line.split("\x1f") for line in
            git(repo, "reflog", "show", "-n", "1000", "--format=%H%x1f%gs%x1f%s%x1f%cr", "HEAD").splitlines()]
    for i, (sha, action, subject, when) in enumerate(rows):
        renamed = re.match(r"Branch: renamed refs/heads/(\S+) to ", action)
        if renamed:
            names.add(renamed.group(1))
        moved = re.match(r"checkout: moving from (\S+) to ", action)
        if moved and i + 1 < len(rows):
            name = moved.group(1)
            if name not in existing and name not in names and not re.fullmatch(r"[0-9a-f]{40}", name):
                names.add(name)
                items.append({"kind": "branch", "name": name, "sha": rows[i + 1][0], "subject": rows[i + 1][2],
                              "when": rows[i + 1][3], "source": "reflog"})
    return items


@op
def lost(repo):
    """Commits nothing points to any more: deleted branches, undone commits, dropped stashes."""
    r = run(repo, "fsck", "--unreachable", "--no-reflogs", "--no-progress", quiet=True)
    shas = [line.split()[2] for line in r.stdout.splitlines() if line.startswith("unreachable commit ")]
    if not shas:
        return []
    rows = [line.split("\x1f") for line in
            git(repo, "log", "--no-walk", "--stdin", "--format=%H%x1f%P%x1f%s%x1f%cr", input="\n".join(shas)).splitlines()]
    parents = {p for row in rows for p in row[1].split()}
    return [{"sha": row[0], "subject": row[2], "when": row[3],
             "stash": len(row[1].split()) > 1 and bool(re.match(r"(WIP on|On) \S+: ", row[2]))}
            for row in rows if row[0] not in parents][:100]  # only the newest commit of each lost chain


@op
def restore(repo, kind, sha, name="", ref=""):
    sha = arg(sha)
    if kind == "branch":
        git(repo, "branch", arg(name), sha)
    elif kind == "tag":
        git(repo, "update-ref", "refs/tags/" + arg(name), sha, "")
    elif kind == "remote":  # put a deleted server branch back on the server
        remote, _, short = arg(name).partition("/")
        git(repo, "push", remote, "%s:refs/heads/%s" % (sha, short))
    elif kind == "stash":
        git(repo, "stash", "store", "-m", git(repo, "log", "-1", "--format=%s", sha, quiet=True).strip(), sha)
    else:
        raise GitError("Unknown item.")
    if ref:
        forget(repo, ref)


@op
def forget(repo, ref=""):
    refs = [ref] if ref else git(repo, "for-each-ref", "--format=%(refname)", TRASH, quiet=True).split()
    if any(not r.startswith(TRASH + "/") for r in refs):
        raise GitError("Unknown item.")
    git(repo, "update-ref", "--stdin", input="".join("delete %s\n" % r for r in refs))


@op
def reflog(repo):
    branch = run(repo, "symbolic-ref", "-q", "--short", "HEAD", quiet=True).stdout.strip()
    out = git(repo, "reflog", "show", "-n", "150", "--date=relative", "--format=%H%x1f%h%x1f%gd%x1f%gs",
              "refs/heads/" + branch if branch and has_head(repo) else "HEAD", ok=(0, 128))
    return [dict(zip(("sha", "short", "when", "action"), line.split("\x1f"))) for line in out.splitlines()]


# ---------- everything else ----------

@op
def raw(repo, command):
    args = shlex.split(command)
    if args[:1] == ["git"]:
        args = args[1:]
    if not args:
        raise GitError("Type a git command, for example: status")
    r = run(repo, *args)
    return {"code": r.returncode, "out": clip(r.stdout + r.stderr)}


@op
def set_identity(repo, name, email):
    git(repo, "config", "--global", "user.name", arg(name))
    git(repo, "config", "--global", "user.email", arg(email))


@op
def ping():
    pass  # the page calls this every 30s so KrazyGit knows a window is still open


@op
def quit():
    threading.Timer(0.3, SERVER.shutdown).start()


# ---------- web server ----------

def call(name, body):
    fn = OPS.get(name)
    try:
        if not fn:
            raise GitError("Unknown action: " + name)
        if "repo" in body and body["repo"] not in saved():
            raise GitError("That project isn't in your KrazyGit list.")
        # Remember where the branch was, so the page can offer a one-click Undo.
        before = run(body["repo"], "rev-parse", "-q", "--verify", "HEAD", quiet=True).stdout.strip() if name in MOVES else ""
        data = fn(**body)
        return {"ok": True, "data": dict(data or {}, before=before) if before else data}
    except GitError as e:
        return {"ok": False, "error": str(e), "hint": hint(str(e))}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        # Only pages served by KrazyGit itself may talk to it: blocks DNS rebinding and other websites.
        return self.headers.get("Host") in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)

    def do_GET(self):
        if not self.allowed() or self.path != "/":
            return self.send_error(404)
        page = (HERE / "krazygit.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
        self.reply(page.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        global LAST_SEEN
        if self.path != "/api" or not self.allowed() or not secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN):
            return self.send_error(403)
        LAST_SEEN = time.monotonic()
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        name = body.pop("op", "")
        if name == "pick_folder":  # no lock: the folder dialog can stay open a while
            res = call(name, body)
        else:
            with LOCK:
                CMDS.clear()
                res = call(name, body)
                if name not in QUIET:
                    res["cmds"] = list(CMDS)
        self.reply(json.dumps(res).encode(), "application/json")


def open_window(url):
    chrome = "/Applications/Google Chrome.app"
    if sys.platform == "darwin" and os.path.exists(chrome):
        subprocess.Popen(["open", "-na", chrome, "--args", "--app=" + url])  # app-style window without tabs
    else:
        webbrowser.open(url)


def askpass(prompt):
    """Git and ssh run this file when they need a password; answer with a Mac dialog instead of a terminal prompt."""
    if "continue connecting" in prompt:  # ssh meeting a server for the first time
        script, answer = 'display dialog (item 1 of argv) with title "KrazyGit" buttons {"Cancel", "Trust this server"} default button 2', "yes"
    else:
        hidden = "with hidden answer" if re.search(r"password|passphrase|token", prompt, re.I) else ""
        script, answer = 'text returned of (display dialog (item 1 of argv) default answer "" %s with title "KrazyGit: sign in")' % hidden, None
        if hidden and "github.com" in prompt:
            prompt += "\n\nGitHub needs a personal access token here, not your password. Make one at github.com/settings/tokens"
    r = subprocess.run(["osascript", "-e", "on run argv", "-e", "tell me to activate", "-e", script, "-e", "end run", prompt],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(1)  # Cancel pressed
    print(answer or r.stdout.rstrip("\n"))


def quit_when_idle():
    while True:
        time.sleep(30)
        if time.monotonic() - LAST_SEEN > IDLE_QUIT and not LOCK.locked():
            return SERVER.shutdown()


def main():
    global SERVER
    if len(sys.argv) == 2 and not sys.argv[1].startswith("--"):
        return askpass(sys.argv[1])
    url = "http://127.0.0.1:%d/" % PORT
    if not CONFIG.exists() and LEGACY[1].exists():
        CONFIG.write_text(LEGACY[1].read_text())
    try:
        SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print("KrazyGit is already running. Opening it.")
        return open_window(url)
    os.chmod(__file__, 0o755)  # askpass needs to be runnable
    print("KrazyGit is running at %s. It quits by itself 10 minutes after you close its window." % url, flush=True)
    if "--no-open" not in sys.argv:
        threading.Timer(0.3, open_window, [url]).start()
    threading.Thread(target=quit_when_idle, daemon=True).start()
    with contextlib.suppress(KeyboardInterrupt):
        SERVER.serve_forever()


if __name__ == "__main__":
    main()
