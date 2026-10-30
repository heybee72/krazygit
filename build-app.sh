#!/bin/sh
# Builds KrazyGit.app: a tiny launcher that starts krazygit.py from the folder it sits in. Run: ./build-app.sh
set -e
cd "$(dirname "$0")"
script="$(mktemp -d)/launcher.applescript"
cat > "$script" <<'APPLESCRIPT'
on run
	set here to do shell script "dirname " & quoted form of POSIX path of (path to me)
	set py to here & "/krazygit.py"
	try
		do shell script "test -f " & quoted form of py
	on error
		display alert "KrazyGit can’t find its files" message "Keep KrazyGit.app in the same folder as krazygit.py. To put it in your Dock, drag it there instead of moving it. If macOS asked about access to a folder, choose Allow."
		return
	end try
	try
		do shell script "head -c 1 " & quoted form of py & " > /dev/null"
	on error
		display alert "macOS is stopping KrazyGit from opening its files" message "This can happen after a macOS update. Open System Settings › Privacy & Security › Files & Folders, find KrazyGit, and turn on the folder it’s in. Then open KrazyGit again."
		return
	end try
	do shell script "export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; mkdir -p ~/Library/Logs; nohup python3 " & quoted form of py & " >> ~/Library/Logs/KrazyGit.log 2>&1 &"
end run
APPLESCRIPT
rm -rf KrazyGit.app
osacompile -o KrazyGit.app "$script"
cp assets/KrazyGit.icns KrazyGit.app/Contents/Resources/applet.icns
plutil -replace CFBundleIdentifier -string app.krazygit.launcher KrazyGit.app/Contents/Info.plist
plutil -replace CFBundleName -string KrazyGit KrazyGit.app/Contents/Info.plist
codesign --force --deep --sign - KrazyGit.app 2>/dev/null
touch KrazyGit.app
echo "Built KrazyGit.app. Double-click it, or drag it to your Dock."
