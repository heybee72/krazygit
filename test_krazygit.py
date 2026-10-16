"""Run: python3 test_krazygit.py  (exercises the real git ops against a throwaway repo)"""
import os
import subprocess
import tempfile
from pathlib import Path

import krazygit as g

tmp = Path(tempfile.mkdtemp())
g.CONFIG = tmp / "config.json"
op = g.OPS


def sh(*args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def write(name, text):
    Path(repo, name).write_text(text)


def read(name):
    return Path(repo, name).read_text()


def st():
    return op["state"](repo=repo)


def snap(msg):
    op["commit"](repo=repo, message=msg, everything=True)


os.mkdir(tmp / "proj")
r = op["add_repo"](path=str(tmp / "proj"))
assert r["added"] is None and r["found"] == []
repo = op["init"](path=r["path"])
assert op["add_repo"](path=str(tmp))["found"] == [repo]
sh("config", "user.name", "Test")
sh("config", "user.email", "test@example.com")

# first commit, staging on an unborn branch
write("a.txt", "one\n")
assert st()["files"] == [{"path": "a.txt", "x": "?", "y": "?", "conflict": False, "size": 4}] and not st()["has_commits"]
op["stage"](repo=repo, paths=["a.txt"])
op["unstage"](repo=repo, paths=["a.txt"])
snap("first")
assert st()["has_commits"] and st()["files"] == []

# conflicting merge, resolved by taking one side
op["create_branch"](repo=repo, name="feature")
write("a.txt", "feature\n")
snap("on feature")
op["switch"](repo=repo, name="main")
write("a.txt", "main\n")
snap("on main")
assert op["merge_preview"](repo=repo, name="feature") == {"count": 1, "clashes": ["a.txt"]}
assert op["merge"](repo=repo, name="feature") == {"conflicts": True}
s = st()
assert s["doing"] == "merge" and s["files"][0]["conflict"]
assert "<<<<<<<" in op["read_file"](repo=repo, path="a.txt")["text"]
op["take"](repo=repo, path="a.txt", side="theirs")
op["finish"](repo=repo, kind="merge", action="continue")
assert read("a.txt") == "feature\n" and st()["doing"] is None
assert "feature" in st()["merged"]

# delete a branch, then restore it from the recycle bin
op["delete_branch"](repo=repo, name="feature")
item = next(x for x in op["bin"](repo=repo) if x["source"] == "bin")
assert item["name"] == "feature"
op["restore"](repo=repo, kind="branch", name="feature", sha=item["sha"], ref=item["ref"])
assert "feature" in [b["name"] for b in st()["branches"]]
assert not [x for x in op["bin"](repo=repo) if x["source"] == "bin"]

# a branch deleted outside KrazyGit is still found through the reflog and in the lost-work scan
sh("switch", "-c", "outside")
write("b.txt", "b\n")
snap("outside work")
sh("switch", "main")
sh("branch", "-D", "outside")
found = next(x for x in op["bin"](repo=repo) if x["name"] == "outside")
assert found["subject"] == "outside work"
assert any(c["subject"] == "outside work" for c in op["lost"](repo=repo))
op["restore"](repo=repo, kind="branch", name="outside", sha=found["sha"])
assert "outside" in [b["name"] for b in st()["branches"]]

# discarding keeps a backup stash; a dropped stash can be restored
write("a.txt", "oops\n")
write("new.txt", "new\n")
assert op["discard"](repo=repo, paths=["a.txt", "new.txt"])["backup"]
assert read("a.txt") == "feature\n" and not Path(repo, "new.txt").exists()
assert "KrazyGit backup" in st()["stashes"][0]["msg"]
op["stash_drop"](repo=repo, ref="stash@{0}")
assert st()["stashes"] == []
dropped = next(x for x in op["bin"](repo=repo) if x["kind"] == "stash")
op["restore"](repo=repo, kind="stash", sha=dropped["sha"], ref=dropped["ref"])
op["stash_apply"](repo=repo, ref="stash@{0}", pop=True)
assert read("a.txt") == "oops\n" and read("new.txt") == "new\n"

# switching with changes left behind on the old branch
op["switch"](repo=repo, name="feature", stash_first=True)
assert st()["files"] == [] and st()["stashes"][0]["msg"].endswith("KrazyGit: left on main")
op["switch"](repo=repo, name="main")
op["stash_apply"](repo=repo, ref="stash@{0}", pop=True)
assert read("a.txt") == "oops\n"

# hard reset backs up work first, and undo history can bring the commit back
snap("second")
before = st()["last_message"]
op["reset_to"](repo=repo, sha="HEAD~1", mode="hard")
assert st()["last_message"] != before
undo = next(r for r in op["reflog"](repo=repo) if r["action"] == "commit: second")
op["reset_to"](repo=repo, sha=undo["sha"], mode="hard")
assert st()["last_message"] == "second"

# undo last commit keeps the files; history and commit details
op["undo_commit"](repo=repo)
assert st()["last_message"] != "second" and st()["files"]
snap("second again")
assert op["log"](repo=repo)[0]["subject"] == "second again"
info = op["commit_info"](repo=repo, sha="HEAD")
assert info["message"] == "second again" and {f["path"] for f in info["files"]} == {"a.txt", "new.txt"}

# restore a deleted file from history
sh("rm", "-q", "new.txt")
snap("remove new")
op["restore_file"](repo=repo, sha="HEAD", path="new.txt", deleted=True)
assert read("new.txt") == "new\n"

# tags go to the recycle bin too
op["create_tag"](repo=repo, name="v1")
op["delete_tag"](repo=repo, name="v1")
tag = next(x for x in op["bin"](repo=repo) if x["kind"] == "tag")
op["restore"](repo=repo, kind="tag", name="v1", sha=tag["sha"], ref=tag["ref"])
assert [t["name"] for t in st()["tags"]] == ["v1"]

# sync: publish to a "server", pick up a teammate's commit while keeping local edits, then Undo it
snap("before sync")
server = tmp / "server.git"
subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(server)], check=True)
op["add_remote"](repo=repo, name="origin", url=str(server))
assert op["sync"](repo=repo)["sent"] == -1 and st()["upstream"] == "origin/main"
mate = tmp / "mate"
subprocess.run(["git", "clone", "-q", str(server), str(mate)], check=True)
Path(mate, "mate.txt").write_text("hi\n")
for args in (["add", "-A"], ["-c", "user.name=M", "-c", "user.email=m@x", "commit", "-qm", "from mate"], ["push", "-q"]):
    subprocess.run(["git", *args], cwd=mate, check=True, capture_output=True)
write("a.txt", "local edit\n")
op["auto_fetch"](repo=repo)
assert st()["behind"] == 1
res = g.call("sync", {"repo": repo})
assert res["ok"] and res["data"]["got"] == 1 and read("mate.txt") == "hi\n" and read("a.txt") == "local edit\n"
assert g.call("reset_to", {"repo": repo, "sha": res["data"]["before"], "mode": "keep"})["ok"]  # the Undo button
assert not Path(repo, "mate.txt").exists() and read("a.txt") == "local edit\n"

# a GitHub repo created with a README still publishes: Sync links to it and combines the two
readme_server, seed = tmp / "readme.git", tmp / "seed"
subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(readme_server)], check=True)
subprocess.run(["git", "clone", "-q", str(readme_server), str(seed)], check=True, capture_output=True)
Path(seed, "README.md").write_text("# hi\n")
for args in (["add", "-A"], ["-c", "user.name=M", "-c", "user.email=m@x", "commit", "-qm", "Initial commit"], ["push", "-q", "origin", "HEAD:main"]):
    subprocess.run(["git", *args], cwd=seed, check=True, capture_output=True)
op["remove_remote"](repo=repo, name="origin")
op["add_remote"](repo=repo, name="origin", url=str(readme_server))
res = g.call("sync", {"repo": repo})
assert res["ok"] and res["data"]["got"] == 1 and res["data"]["sent"] > 0 and read("README.md") == "# hi\n", res
assert st()["ahead"] == 0 and read("a.txt") == "local edit\n"

# committing can be undone with one click, and the changes come back
res = g.call("commit", {"repo": repo, "message": "oops", "everything": True})
assert st()["last_message"] == "oops"
g.call("reset_to", {"repo": repo, "sha": res["data"]["before"], "mode": "soft"})
assert st()["last_message"] != "oops" and read("a.txt") == "local edit\n"

# server branches: upload several at once, delete them from the server, put one back from the Recycle bin
def on_server():
    out = subprocess.run(["git", "ls-remote", "--heads", str(readme_server)], capture_output=True, text=True).stdout
    return {line.split("refs/heads/")[1] for line in out.splitlines()}


op["publish_branches"](repo=repo, names=["feature", "outside"])
assert {"feature", "outside"} <= on_server()
remote_names = {b["name"] for b in st()["remote_branches"]}
assert {"origin/feature", "origin/outside", "origin/main"} <= remote_names and "origin/HEAD" not in remote_names
gone = op["delete_remote_branches"](repo=repo, names=["origin/feature", "origin/outside"])
assert {x["name"] for x in gone} == {"origin/feature", "origin/outside"} and not {"feature", "outside"} & on_server()
parked = next(x for x in op["bin"](repo=repo) if x["kind"] == "remote" and x["name"] == "origin/feature")
op["restore"](repo=repo, kind="remote", name=parked["name"], sha=parked["sha"], ref=parked["ref"])
assert "feature" in on_server() and "origin/feature" in {b["name"] for b in st()["remote_branches"]}
op["delete_branch"](repo=repo, name="outside", force=True)
op["track_branches"](repo=repo, names=["origin/feature"])  # already have a local copy: nothing to do
assert "feature" in {b["name"] for b in st()["branches"]}

# with two servers, new branches go where the project's branches already go, not blindly to "origin"
team = tmp / "team.git"
subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(team)], check=True)
op["add_remote"](repo=repo, name="upstream", url=str(team))
sh("push", "-q", "-u", "upstream", "main", "feature")
assert st()["main_remote"] == "upstream"
op["create_branch"](repo=repo, name="fresh-work")
assert op["sync"](repo=repo)["sent"] == -1 and st()["upstream"] == "upstream/fresh-work"
write("fresh.txt", "x\n")
snap("fresh commit")
assert op["sync"](repo=repo)["sent"] == 1 and st()["ahead"] == 0  # later syncs keep going to the same server
op["set_main_remote"](repo=repo, name="origin")
assert st()["main_remote"] == "origin"
assert op["link_to"](repo=repo, remote="origin")["uploaded"]  # not on that server yet: upload it there
assert st()["upstream"] == "origin/fresh-work"
op["switch"](repo=repo, name="main")
# main follows the wrong server; the other server has its own main: just follow it, upload nothing
sh("branch", "--set-upstream-to", "origin/main", "main")
team_main = subprocess.run(["git", "rev-parse", "main"], cwd=team, capture_output=True, text=True).stdout
assert op["link_to"](repo=repo, remote="upstream") == {"uploaded": False} and st()["upstream"] == "upstream/main"
assert subprocess.run(["git", "rev-parse", "main"], cwd=team, capture_output=True, text=True).stdout == team_main

# with a team server, main/master only download: Sync pulls from the team copy (relinking if needed) and never uploads
op["set_main_remote"](repo=repo, name="upstream")
assert "main" in st()["download_only"] and "feature" not in st()["download_only"]
sh("branch", "--set-upstream-to", "origin/main", "main")  # linked to the wrong server again
mate2 = tmp / "mate2"
subprocess.run(["git", "clone", "-q", str(team), str(mate2)], check=True, capture_output=True)
Path(mate2, "team.txt").write_text("t\n")
for args in (["add", "-A"], ["-c", "user.name=M", "-c", "user.email=m@x", "commit", "-qm", "team change"], ["push", "-q"]):
    subprocess.run(["git", *args], cwd=mate2, check=True, capture_output=True)
origin_main = subprocess.run(["git", "rev-parse", "main"], cwd=readme_server, capture_output=True, text=True).stdout
res = op["sync"](repo=repo)
assert res["download_only"] and res["got"] == 1 and res["sent"] == 0 and res["relinked"] == "upstream/main", res
assert st()["upstream"] == "upstream/main" and read("team.txt") == "t\n"
assert subprocess.run(["git", "rev-parse", "main"], cwd=readme_server, capture_output=True, text=True).stdout == origin_main
# a commit made on main by mistake moves to its own branch, and main matches the team copy again
write("oops.txt", "o\n")
sh("add", "oops.txt")
sh("commit", "-qm", "oops on main")
assert st()["follow"] == {"ref": "upstream/main", "ahead": 1, "behind": 0}
op["move_commits"](repo=repo, name="oops-work")
assert st()["branch"] == "oops-work" and read("oops.txt") == "o\n"
op["switch"](repo=repo, name="main")
assert not Path(repo, "oops.txt").exists() and st()["follow"]["ahead"] == 0
op["set_download_only"](repo=repo, name="main", on=False)
assert "main" not in st()["download_only"]

# a clash gets its original text back (from before either side changed it), without touching the file on disk
write("imports.txt", "use A;\n")
snap("imports base")
op["create_branch"](repo=repo, name="imports-mate")
write("imports.txt", "use A;\nuse C;\n")
snap("mate adds C")
op["switch"](repo=repo, name="main")
write("imports.txt", "use A;\nuse B;\n")
snap("we add B")
assert op["merge"](repo=repo, name="imports-mate")["conflicts"]
on_disk = read("imports.txt")
base = op["conflict_base"](repo=repo, path="imports.txt")
assert "|||||||" in base and "use B;" in base and "use C;" in base and read("imports.txt") == on_disk
op["finish"](repo=repo, kind="merge", action="abort")

# sync a branch without switching to it: catch up, combine when both sides moved, leave clashes alone, upload
def mate_commit(branch, path, text, msg):
    for args in (["fetch", "-q", "origin"], ["switch", "-q", "-C", branch, "origin/" + branch]):
        subprocess.run(["git", *args], cwd=mate2, check=True, capture_output=True)
    Path(mate2, path).write_text(text)
    for args in (["add", "-A"], ["-c", "user.name=M", "-c", "user.email=m@x", "commit", "-qm", msg], ["push", "-q", "origin", branch]):
        subprocess.run(["git", *args], cwd=mate2, check=True, capture_output=True)


def rev(where, name):
    return subprocess.run(["git", "rev-parse", name], cwd=where, capture_output=True, text=True).stdout.strip()


sh("branch", "side", "main")
sh("push", "-q", "-u", "upstream", "side")
mate_commit("side", "side.txt", "one\n", "mate 1")
files_before, status_before = sorted(os.listdir(repo)), st()["files"]
assert op["sync_branches"](repo=repo, names=["side"]) == [{"got": 1, "sent": 0, "name": "side"}]
assert rev(repo, "side") == rev(team, "side") and st()["branch"] == "main"
assert sorted(os.listdir(repo)) == files_before and st()["files"] == status_before  # your files are never touched
sh("switch", "-q", "side")
write("local.txt", "l\n")
sh("add", "local.txt")
sh("commit", "-qm", "my side work")
sh("switch", "-q", "main")
mate_commit("side", "side2.txt", "two\n", "mate 2")
res = op["sync_branches"](repo=repo, names=["side"])[0]
assert res == {"got": 1, "sent": 2, "name": "side"}, res  # my commit plus the combining one
on_team = subprocess.run(["git", "ls-tree", "--name-only", "side"], cwd=team, capture_output=True, text=True).stdout.split()
assert {"local.txt", "side.txt", "side2.txt"} <= set(on_team) and rev(repo, "side") == rev(team, "side")
sh("switch", "-q", "side")
write("side.txt", "mine\n")
sh("add", "side.txt")
sh("commit", "-qm", "mine")
sh("switch", "-q", "main")
mate_commit("side", "side.txt", "theirs\n", "theirs")
mine = rev(repo, "side")
res = op["sync_branches"](repo=repo, names=["side"])[0]
assert "clash" in res["problem"] and rev(repo, "side") == mine, res
# a download-only branch you're not on catches up and never uploads
op["set_download_only"](repo=repo, name="main", on=True)
sh("switch", "-q", "fresh-work")
assert "only downloads" in op["sync_branches"](repo=repo, names=["main"])[0]["problem"]  # it has unshared commits: reported, not uploaded
sh("branch", "-f", "main", "upstream/main")
mate_commit("main", "news.txt", "n\n", "team news")
team_main = rev(team, "main")
assert op["sync_branches"](repo=repo, names=["main"]) == [{"got": 1, "sent": 0, "name": "main"}]
assert rev(repo, "main") == team_main == rev(team, "main") and st()["branch"] == "fresh-work"
sh("switch", "-q", "main")
op["set_download_only"](repo=repo, name="main", on=False)

# renaming a branch that's online: rename it on the server too, or unlink it so Sync publishes the new name
team_heads = lambda: set(subprocess.run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=team,
                                        capture_output=True, text=True).stdout.split())
res = op["rename_branch"](repo=repo, old="side", new="side-renamed", on_server=True)
assert {"side-renamed"} <= team_heads() and "side" not in team_heads() and res["parked"][0]["name"] == "upstream/side"
assert next(b for b in st()["branches"] if b["name"] == "side-renamed")["upstream"] == "upstream/side-renamed"
sh("branch", "solo", "main")
sh("push", "-q", "-u", "upstream", "solo")
op["rename_branch"](repo=repo, old="solo", new="solo-b")
assert next(b for b in st()["branches"] if b["name"] == "solo-b")["upstream"] == "" and "solo" in team_heads()
sh("switch", "-q", "solo-b")
assert op["sync"](repo=repo)["sent"] == -1 and st()["upstream"] == "upstream/solo-b"
sh("switch", "-q", "main")
for bad in ("solo-b", "bad name"):
    try:
        op["rename_branch"](repo=repo, old="feature", new=bad)
        raise AssertionError("renamed to " + bad)
    except g.GitError:
        pass

# a new branch started from the team's copy is new work: not linked to the team's branch, so Sync publishes it
assert st()["team_main"] == "upstream/main"
op["create_branch"](repo=repo, name="from-team", start="upstream/main")
assert st()["upstream"] is None and op["sync"](repo=repo)["sent"] == -1 and st()["upstream"] == "upstream/from-team"
sh("switch", "-q", "main")

# tags: your own note, upload one (even a plain one made elsewhere), delete on the server too
op["create_tag"](repo=repo, name="v1.0", message="First release")
sh("tag", "plain")
assert next(t for t in st()["tags"] if t["name"] == "v1.0")["subject"] == "First release"
already = set(op["remote_tags"](repo=repo))  # annotated tags travel with Sync
assert "plain" not in already
op["upload_tags"](repo=repo, names=["v1.0", "plain"])
assert set(op["remote_tags"](repo=repo)) == already | {"plain", "v1.0"}
gone = op["delete_tag"](repo=repo, name="plain", on_server=True)
assert set(op["remote_tags"](repo=repo)) == already | {"v1.0"} and gone["name"] == "plain"
op["fetch"](repo=repo)
assert "plain" not in {t["name"] for t in st()["tags"]}  # and it doesn't come back

# ignoring a file that's already committed: Git keeps tracking it until told to stop; the file stays on disk
write("build.log", "noise\n")
snap("oops, a log")
assert op["ignore"](repo=repo, pattern="*.log") == {"still_tracked": 1} and st()["ignored_tracked"] == 1
assert op["untrack_ignored"](repo=repo) == {"count": 1} and read("build.log") == "noise\n"
assert {"path": "build.log", "x": "D"}.items() <= next(f for f in st()["files"] if f["path"] == "build.log").items()
snap("stop tracking logs")
assert st()["ignored_tracked"] == 0 and st()["files"] == []

# a stash comes back with the same files ticked, and still comes back when that's impossible
write("ticked.txt", "t\n")
op["stage"](repo=repo, paths=["ticked.txt"])
write("a.txt", "not ticked\n")
op["stash_save"](repo=repo, message="half ticked")
op["stash_apply"](repo=repo, ref="stash@{0}", pop=True)
files = {f["path"]: f["x"] + f["y"] for f in st()["files"]}
assert files == {"ticked.txt": "A.", "a.txt": ".M"}, files
op["stash_save"](repo=repo)
write("ticked.txt", "t\n")
snap("same file committed meanwhile")
assert not op["stash_apply"](repo=repo, ref="stash@{0}").get("conflicts") and read("a.txt") == "not ticked\n"
sh("checkout", "--", "a.txt")
op["stash_drop"](repo=repo, ref="stash@{0}")

# history: find the commits that added or removed some code
found = op["log"](repo=repo, ref="--all", search="use B;", mode="code")
assert "we add B" in {c["subject"] for c in found} and not op["log"](repo=repo, search="use B;")

# a branch's pull request preview: its commits and the combined change, against where it split off
cmp = op["compare"](repo=repo, base="main", head="side-renamed")
assert "mine" in {c["subject"] for c in cmp["commits"]} and "local.txt" in cmp["patch"]

# pull request links: the address the server prints after an upload, or one built for GitHub, Bitbucket, GitLab
assert g.parse_remote("git@github.com:me/proj.git") == ("github.com", "me/proj")
assert g.parse_remote("https://user@bitbucket.org/team/proj.git/") == ("bitbucket.org", "team/proj")
assert g.parse_remote("/some/folder") == (None, None)
sh("remote", "add", "fork", "git@github.com:me/proj.git")
sh("remote", "add", "hub", "https://github.com/team/proj.git")
sh("config", "branch.side-renamed.remote", "fork")
for name in ("fork", "hub"):  # made-up addresses: never contact them
    sh("config", "remote.%s.skipFetchAll" % name, "true")
assert op["pr_link"](repo=repo, name="side-renamed", base="hub/main") == \
    "https://github.com/team/proj/compare/main...me:side-renamed?expand=1"
sh("remote", "set-url", "fork", "git@bitbucket.org:me/proj.git")
sh("remote", "set-url", "hub", "git@bitbucket.org:team/proj.git")
assert op["pr_link"](repo=repo, name="side-renamed", base="hub/main") == \
    "https://bitbucket.org/me/proj/pull-requests/new?source=side-renamed&dest=team%2Fproj%3A%3Amain&t=1"
hook = Path(team, "hooks", "post-receive")
hook.write_text("#!/bin/sh\necho 'Create a pull request:' >&2\necho '  https://bitbucket.org/me/proj/pull-requests/new?source=x' >&2\n")
hook.chmod(0o755)
op["create_branch"](repo=repo, name="pr-me")
assert op["sync"](repo=repo)["pr_url"] == "https://bitbucket.org/me/proj/pull-requests/new?source=x"
hook.unlink()
sh("remote", "remove", "fork")
sh("remote", "remove", "hub")
sh("switch", "-q", "main")

# a different name and email for this project only, then back to the everyday ones
op["set_identity"](repo=repo, name="Work Me", email="me@work.example", project_only=True)
assert st()["who_project"] and st()["who"]["email"] == "me@work.example"
op["clear_project_identity"](repo=repo)
assert not st()["who_project"]
sh("config", "user.name", "Test")
sh("config", "user.email", "test@example.com")

# things saved under the app's old name (EasyGit) carry over: Recycle bin items and branch settings
sh("update-ref", "refs/easygit-trash/branch/1700000000000/legacy-branch", "HEAD")
sh("config", "branch.feature.easygitDownloadOnly", "true")
s = st()
assert "feature" in s["download_only"] and any(x["name"] == "legacy-branch" for x in op["bin"](repo=repo))
assert not subprocess.run(["git", "for-each-ref", "refs/easygit-trash"], cwd=repo, capture_output=True, text=True).stdout

# the server hands out the page and the bundled libraries only, and the page can't load anything from the internet
import threading, urllib.error, urllib.request
srv = g.ThreadingHTTPServer(("127.0.0.1", 0), g.Handler)
g.PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
get = lambda path: urllib.request.urlopen("http://127.0.0.1:%d%s" % (g.PORT, path), timeout=5)
page = get("/")
assert "default-src 'none'" in page.headers["Content-Security-Policy"] and b"/vendor/highlight.min.js" in page.read()
assert get("/vendor/highlight.min.js").read().startswith(b"/*!") and get("/vendor/highlight-dark.min.css").status == 200
assert get("/guide.md").read().startswith(b"# ")
for path in ("/vendor/LICENSE-lucide.txt", "/vendor/../krazygit.py", "/krazygit.py", "/vendor/"):
    try:
        get(path)
        raise AssertionError("served " + path)
    except urllib.error.HTTPError as e:
        assert e.code == 404, path
srv.shutdown()

# the guide: every article has a unique id, and every link and "?" button in the app leads somewhere real
import re
guide, page = (Path(g.HERE, f).read_text() for f in ("guide.md", "krazygit.html"))
heads = re.findall(r"^## (.*)$", guide, re.M)
ids = [m.group(1) for h in heads if (m := re.search(r" \{#([\w-]+)\}$", h))]
assert len(ids) == len(heads) == len(set(ids)), "every ## heading needs its own {#id}"
tabs = set(re.findall(r"^  (\w+): \{ label:", page, re.M))
assert {"branches", "changes", "settings"} <= tabs
for link in re.findall(r"\]\(([^)]*)\)", guide):
    assert link.startswith("https://") or link[len("#guide:"):] in ids or link[len("#tab:"):] in tabs, "broken guide link " + link
used = re.findall(r"help\('([\w-]+)'\)", page) + re.findall(r"'guide', \{ id: '([\w-]+)' \}", page)
assert len(used) > 10 and not set(used) - set(ids), set(used) - set(ids)

# safety rails
for bad in (lambda: op["init"](path=str(Path.home())),
            lambda: op["read_file"](repo=repo, path="../../etc/passwd"),
            lambda: op["delete_branch"](repo=repo, name="--force"),
            lambda: op["forget"](repo=repo, ref="refs/heads/main")):
    try:
        bad()
        raise AssertionError("should have refused")
    except g.GitError:
        pass
assert g.hint("error: The branch 'x' is not fully merged.") == "This branch has commits that aren't merged anywhere else."

print("all good:", repo)
