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
assert op["link_to"](repo=repo, remote="origin") == {"uploaded": True}  # not on that server yet: upload it there
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
for path in ("/vendor/LICENSE-lucide.txt", "/vendor/../krazygit.py", "/krazygit.py", "/vendor/"):
    try:
        get(path)
        raise AssertionError("served " + path)
    except urllib.error.HTTPError as e:
        assert e.code == 404, path
srv.shutdown()

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
