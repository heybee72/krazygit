# Start here

## Welcome to KrazyGit {#welcome}

KrazyGit lets you use Git without typing commands. It works on the projects already on your computer, and it shows what to do next.

- **The big card at the top** suggests your next step: commit, sync, finish a merge. Press its button, or press × to hide it until you reopen KrazyGit.
- **Most actions show an Undo button** for a few seconds afterwards.
- **Deleted branches, tags and stashes go to the [Recycle bin](#guide:bin).** Nothing is gone until you empty it.
- **It keeps itself up to date.** While its window is open, KrazyGit notices edits you make in your editor within a few seconds, and checks the server for new commits every few minutes.
- **Curious what happened?** Open **What Git did** at the bottom of the sidebar to see the exact Git commands it ran.

New to Git? Read [Git in five minutes](#guide:git-basics) first.

## Git in five minutes {#git-basics}

Git keeps the history of a folder of code, so you can go back to any earlier version and work with other people without overwriting each other.

- **Repository (project):** a folder Git looks after. Its history lives in a hidden `.git` folder inside it.
- **Commit:** a save point. A snapshot of your files with a short note about what changed. You can always go back to one.
- **Branch:** a separate line of work. Try an idea on a branch without touching your main code, then [merge](#guide:merging) it in when it works.
- **Server (remote):** a copy of the project online, on GitHub, GitLab or Bitbucket. It's how you back up your work and share it.
- **Sync:** download what's new on the server, then upload your commits. In Git terms: fetch, pull and push.

A normal day looks like this:

1. Switch to a branch for the thing you're working on, or create one.
2. Edit your code in your usual editor.
3. Commit when something works.
4. Sync to back it up and share it.
5. When the work is done, open a [pull request](#guide:pull-requests) or merge it into your main branch.

## Add your projects {#projects}

Press **+** next to **Projects** and pick a folder.

- **A project folder** is added straight away.
- **A folder with several projects inside** (like `~/code`): KrazyGit finds them and adds them all.
- **A folder that isn't a Git project yet:** KrazyGit offers to start tracking it.

Click a project in the sidebar to switch to it. **Remove from KrazyGit** in [Settings](#tab:settings) only takes a project off the list: your files and history stay where they are.

> **Tip:** with more than six projects, a search box appears above the list.

## Your first commit {#first-commit}

1. Open [Changes](#tab:changes). Every new or edited file is listed.
2. Click a file to see what changed.
3. Type a short message, or leave it empty to use the suggestion.
4. Press **Commit**.

The first time, KrazyGit asks for your name and email, because Git puts them on every commit. See [Your name and email](#guide:identity).

# Everyday work

## Changes and commits {#changes}

[Changes](#tab:changes) lists every file that's different from your last commit.

- **Choose what goes in.** Tick the files for this commit. None ticked means all of them. Once some are ticked, they're listed first under **Going in the commit**, and the rest under **Not ticked**.
- **See the changes** side by side or inline: switch at the top of the diff.
- **Edited a file after ticking it?** Git would commit the version you ticked. KrazyGit asks whether to include your latest changes.
- **Add to last commit** puts the changes into your previous commit instead of making a new one. It's only offered while that commit isn't uploaded yet.
- **Discard** throws away the changes to a file. A backup goes to [Stashes](#guide:stashes) first, and Undo brings them back.
- **Undo last commit** takes the commit back but keeps the changes in your files. If it's already uploaded, KrazyGit adds a new commit that reverses it instead, which is the safe way to undo shared work.

KrazyGit checks before you commit files that look like passwords or keys (such as `.env`), and files over 50 MB. You can leave them out with one click.

See also: [Writing good commit messages](#guide:commit-messages), [Ignoring files](#guide:ignoring).

## Writing good commit messages {#commit-messages}

A good message tells your future self (and teammates) why something changed.

- **Start with a short summary**, under about 50 characters: "Fix login button on mobile".
- **Use the present tense**, like an instruction: "Add", "Fix", "Remove".
- **Need more detail?** Leave a blank line after the summary, then explain why.
- **One idea per commit.** Two unrelated changes? Tick the files for the first one, commit, then commit the rest.

## Branches {#branches}

A branch is a separate line of work. Your main branch (usually `main` or `master`) holds the finished work, and each new feature or fix gets its own branch.

[Branches](#tab:branches) has two lists:

- **On this computer:** your own branches. The one you're on is always at the top.
- **Online:** the branches on the server, including your teammates'.

What you can do:

- **New branch:** describe the work, like "fix login button". If the project has a team server, you choose where it starts: from the team's latest main branch (KrazyGit downloads it first) or from the branch you're on. Starting from the team's latest is usually right for new work.
- **Switch:** if you have uncommitted changes, choose whether to bring them along or leave them waiting on the old branch.
- **Rename:** if the branch is also online, rename it there too, or only on your computer. Then the old name stays online and the next Sync uploads the new name.
- **Delete:** it goes to the [Recycle bin](#guide:bin).
- **Tick several** to sync, upload or delete them in one go. The quick picks select branches that need a sync, are already merged, or haven't changed in three months.
- **Get a copy** of a teammate's branch from the Online list to work on it.

See also: [Syncing](#guide:sync), [Merging branches](#guide:merging).

## Syncing with GitHub and others {#sync}

The **Sync** button in the toolbar does everything needed to match the server: it downloads new commits, combines them with yours, then uploads yours.

- **The arrows** show what's waiting: ↓ commits to download, ↑ commits to upload. KrazyGit checks the server by itself every few minutes while it's open, so they stay current. To check right now, press **Check for new branches** in Branches › Online.
- **Publish** appears instead for a branch that isn't online yet. It uploads it for the first time.
- **Sync other branches without switching** from the Branches list: press **Sync** on a row, or tick several. KrazyGit catches them up and uploads them without touching your files. If one has a clash, it's left alone and reported.
- **Combining clashes?** When both you and someone else changed the same lines, Sync stops and opens [Conflicts](#guide:conflicts).
- **Tags** you made in KrazyGit are uploaded along with your commits. See [Tags](#guide:tags).

When an upload creates a branch on GitHub, GitLab or Bitbucket, a button to [open a pull request](#guide:pull-requests) appears.

## Bringing in the team's changes {#team-changes}

While you work on a branch, your teammates keep adding to the main branch. The longer you wait, the bigger the clashes get when you finally combine them.

To catch up, open [Branches](#tab:branches), go to **Online**, and press **Merge** on the team's main branch (for example `main`). KrazyGit says how many commits come in and which files might clash before anything happens.

> **Tip:** do this every day or two on long-running branches, and always before opening a pull request.

Advanced: instead of merging, **Rebase** replays your commits on top of theirs, which keeps the history in a straight line. Only rebase branches nobody else uses. Turn it on under Advanced tools in [Settings](#tab:settings).

## Merging branches {#merging}

Merging brings the commits from another branch into the one you're on.

1. Switch to the branch that should receive the work, for example `main`.
2. In [Branches](#tab:branches), press **Merge** on the branch with the work.
3. KrazyGit shows how many commits come in and which files changed on both sides. Confirm to merge.

If files clash, [Conflicts](#guide:conflicts) opens. Undo straight after a merge takes it back.

> **Tip:** branches that are fully merged get a **Merged** badge, and the next-step card offers to tidy them up.

## Pull requests {#pull-requests}

A pull request (GitLab calls it a merge request) asks your team to review a branch and merge it into the main branch. It happens on the hosting site, but KrazyGit gets you there.

- **Preview pull request** (in a branch's ⋯ menu) shows what reviewers will see: the branch's commits, and every change they make together compared with the team's main branch.
- **Open pull request** opens the page on GitHub, GitLab or Bitbucket with the branch already filled in. If the branch isn't online yet, upload it first.
- **Right after you upload** a new branch, a toast offers the same link.

It works with forks too: if a branch is on your own copy and the team's main branch is on another server, the pull request goes from your copy to theirs.

> **Tip:** before opening one, [bring in the team's changes](#guide:team-changes) so reviewers see only your work.

## Conflicts {#conflicts}

A conflict happens when two changes touch the same lines, for example you and a teammate both edited the same line. Git can't guess which is right, so it asks you.

[Conflicts](#tab:conflicts) shows each clash side by side: yours on one side, theirs on the other.

- **Lines in bold** exist only on that side. Faded lines are on both.
- **Keep this** on one side, when it already has everything the other side has.
- **Combine both, no duplicates** when each side added different things, like imports or list items.
- **Show the original** to see the lines before either change. It often makes it obvious what each side meant.
- **Edit by hand** when you need a bit of both.
- **Fix the easy ones** fixes every file where each clash has a choice that loses nothing.

Before you finish, **Cancel and go back** undoes the whole merge as if it never started. When every file is fixed, press **Finish merge**.

> **Tip:** run your app or tests after fixing conflicts, before you sync.

## History {#history}

[History](#tab:history) lists the commits on a branch, newest first. Choose another branch, or all branches, at the top.

- **Search** with **Messages** chosen finds commits by their note.
- **Search** with **Code** chosen finds the commits that added or removed some text, like a function name. Handy for "when did this appear?" and "who removed this?"
- **Click a commit** to see what it changed.
- **Undo this commit** adds a new commit that reverses it. Safe even if it's already uploaded.
- **Restore this version** puts one file back the way it was in that commit.
- **Go back to this commit** moves your branch back. You choose whether to keep the later changes in your files. Avoid it for commits already uploaded: use Undo this commit instead.

## Tags {#tags}

A tag is a permanent bookmark for an important commit, usually a release like `v1.2.0`. [Tags](#tab:tags) appears in the sidebar once a project has tags, or when Advanced tools are on in Settings.

- **Tag current commit** in [Tags](#tab:tags), or tag any commit from History. You can add a note, like "First public release". GitHub shows it on the releases page.
- **Online:** each tag says whether it's on the server or only on your computer. **Upload** sends one, **Upload all** sends the rest.
- **Deleting a tag that's online:** delete it on both. Deleted only on your computer, it comes back the next time you sync. Either way, a copy goes to the Recycle bin.

## Stashes {#stashes}

A stash is a shelf for changes you're not ready to commit. Your files go back to your last commit, and you can bring the changes back any time.

- **Stash** in [Changes](#tab:changes) puts everything on the shelf, including new files.
- **Bring back** puts them back in your files and takes them off the shelf. Files you had ticked come back ticked.
- **Apply a copy** brings them back but keeps the stash too.
- When you switch branches and choose to leave changes behind, KrazyGit stashes them and offers to bring them back when you return.
- KrazyGit also keeps safety backups here, for example when you discard changes.

If bringing a stash back clashes with your files, [Conflicts](#guide:conflicts) opens and the stash stays on the shelf.

## Ignoring files {#ignoring}

Some files don't belong in Git: generated folders like `node_modules/` or `dist/`, logs, and secrets like `.env`. The `.gitignore` file lists them, so Git doesn't track them.

- **Ignore** a new file from [Changes](#tab:changes), or add common patterns in [Settings](#tab:settings).
- **Already committed?** Ignoring doesn't stop Git tracking a file it already has. KrazyGit tells you and offers **Stop tracking them**: Git forgets the files, and they stay on your computer. Commit to finish.

> **Careful:** when teammates sync that commit, Git removes those files from their copy too. That's fine for generated files, but anything like settings or keys they'd need to recreate.

# Safety net

## Undo {#undo-button}

Most actions show a toast with an **Undo** button for a few seconds: commits, merges, syncs that downloaded something, deletes, discards, branch switches and renames. Press it to put things back exactly as they were.

Missed it? [Undo history](#guide:undo) can rewind further.

## Recycle bin {#bin}

Deleted branches, tags and stashes, and branches deleted from the server, wait in the [Recycle bin](#tab:bin) until you empty it.

- **Restore** brings one back. Branches deleted from the server go back to the server.
- **Remove forever** or **Empty bin** let Git clean them up for good. That can't be undone.

The bin also lists branches deleted outside KrazyGit, as long as Git still remembers them.

## Undo history {#undo}

[Undo history](#tab:undo) lists every change to the branch you're on: commits, merges, resets, syncs. **Go back to here** puts the branch back to that moment. Uncommitted work is backed up to Stashes first, and you can undo the jump too.

In Git this is called the reflog. It only exists on your computer.

## Finding lost work {#lost-work}

Lost a commit or a stash you dropped? In the [Recycle bin](#tab:bin), press **Search for lost work**. KrazyGit lists every commit Git still remembers that no branch points to, and you can restore any of them as a branch or a stash.

Git cleans these up eventually, usually after a few weeks, so look sooner rather than later.

# Teams and servers

## Servers (remotes) {#servers}

A server is an online copy of the project. Git calls it a remote and gives it a nickname, usually `origin`.

- **Connect** a project in [Settings](#tab:settings): create an empty repository on GitHub (no README), copy its address, paste it.
- **Two servers** are common in teams: your own copy (a fork, often `origin`) and the team's (often `upstream`). Each branch syncs with the server it's linked to.
- **New branches** are published to the server marked **New branches go here**. KrazyGit picks the one most of your branches already use; change it in Settings.
- **A branch linked to an unusual server** gets a warning, with a button to move it.

## Main branches that only download {#download-only}

When a project has a team server and your own copy, `main` and `master` **only download**: Sync keeps them the same as the team's and never uploads them. Your work goes on branches, and reaches the main branch through a [pull request](#guide:pull-requests).

- **Committed on main by mistake?** KrazyGit offers to move those commits to a new branch, and puts main back to match the team.
- **Change it** for any branch from its ⋯ menu in [Branches](#tab:branches): **Download only** or **Allow uploads**.

## Your name and email {#identity}

Git puts a name and email on every commit. GitHub uses the email to link commits to your account.

- **Set them** in [Settings](#tab:settings). By default they're used in all your projects.
- **A different email for one project**, like a work email: type it and press **This project only**. **Use my usual details here** switches back.

> **Tip:** to keep your email private on GitHub, use the "noreply" address from GitHub's email settings.

## Signing in {#signing-in}

KrazyGit uses your normal Git setup to sign in. On a Mac, saved passwords live in the Keychain.

- **When a server needs a password,** a standard macOS dialog asks for it.
- **GitHub doesn't accept your account password here.** Use a personal access token instead, or set up SSH keys.
- **Background checks never ask:** KrazyGit quietly checks for new commits every few minutes, and skips it if it would need you to sign in.

# More

## Settings {#settings}

[Settings](#tab:settings) has:

- **Your name and email**, for all projects or just this one. See [Your name and email](#guide:identity).
- **Back up online:** connect, disconnect, and choose where new branches go. See [Servers](#guide:servers).
- **Ignored files:** add common patterns to `.gitignore`.
- **Advanced tools:** rebase, copying commits between branches (cherry-pick), looking around at old commits, force push, and the command line.
- **This project:** take it off KrazyGit's list.

## Advanced tools {#advanced}

Turn these on in [Settings](#tab:settings). They're powerful, so they're hidden by default.

- **Rebase:** replay your branch's commits on top of another branch, instead of merging. Never rebase a branch others are using.
- **Copy a commit** to your branch (cherry-pick): from a commit's ⋯ menu in History.
- **Look around at an old commit:** your files change to how they were then. You're off any branch until you switch back.
- **Force push:** when your copy and the server's have split, replace the server's with yours. Anything only on the server is lost.
- **Command line:** run any Git command. See [Command line](#guide:command-line).

## Command line {#command-line}

[Command line](#tab:cli) (turn on Advanced tools in Settings) runs any Git command in this project, for anything the buttons don't cover. Type it without the `git` at the start, like `log --oneline -10`.

To learn the commands, open **What Git did** at the bottom of the sidebar: it shows every command KrazyGit ran for you.

## When something goes wrong {#troubleshooting}

- **"Couldn't sign in to the server":** see [Signing in](#guide:signing-in).
- **"The server has commits you don't have yet":** press Sync. It downloads them first, then uploads yours.
- **"Uncommitted changes would be lost":** commit or stash your changes, then try again.
- **"Finish or cancel the merge first":** open [Conflicts](#tab:conflicts) and finish, or press Cancel and go back.
- **"The two histories don't connect":** the server copy was started separately, usually with its own README. Create a new, completely empty repository online and connect to that instead.
- **"You're on an old commit, not a branch":** you're looking around at history. Switch back to a branch, or create one here to keep any commits.
- **"Another Git program is busy":** wait a moment and try again. If it's stuck, delete `.git/index.lock` in the project.
- **Something else?** Expand "What Git said" in the error for the details, and check **What Git did** for the commands that ran.

## Glossary {#glossary}

- **Branch:** a separate line of work.
- **Clone:** a full copy of a repository, history included.
- **Commit:** a save point with a note.
- **Conflict:** two changes to the same lines that you need to choose between.
- **Detached:** looking at an old commit instead of being on a branch.
- **Fetch:** download what's new on the server without changing your files.
- **Fork:** your own copy of someone else's repository on the server.
- **HEAD:** where you are right now: usually the latest commit on your current branch.
- **Merge:** bring the commits from one branch into another.
- **Origin:** the usual nickname for the server a project came from.
- **Pull:** fetch, then merge into your branch. Part of Sync.
- **Pull request:** a request to review a branch and merge it, made on the hosting site.
- **Push:** upload your commits. Part of Sync.
- **Rebase:** replay commits on top of another branch.
- **Reflog:** Git's record of where your branches have been. Shown as Undo history.
- **Remote:** a server copy of the project.
- **Revert:** a new commit that reverses an earlier one.
- **Staging:** choosing which files go in the next commit. In KrazyGit, ticking files.
- **Stash:** a shelf for uncommitted changes.
- **Tag:** a permanent bookmark for a commit, like a release.
- **Upstream:** the server branch your branch syncs with. Also the usual nickname for the team's server in a fork.
