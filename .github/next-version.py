"""Print the next stable release tag, or nothing when no release is due."""

import re
import subprocess


def git(*args):
    return subprocess.check_output(["git", *args]).decode("utf-8", errors="replace")


def bump(message):
    header, _, body = message.partition("\n")
    commit = re.fullmatch(r"([a-z]+)(?:\([^()]+\))?(!)?: .+", header)
    if re.search(r"^BREAKING[ -]CHANGE: \S", body, re.MULTILINE) or (commit and commit[2]):
        return 3
    if commit and commit[1] == "feat":
        return 2
    return 1 if commit and commit[1] in ("fix", "perf") else 0


def main():
    number = r"(0|[1-9][0-9]*)"
    versions = []
    for tag in git("tag", "--merged", "HEAD").splitlines():
        match = re.fullmatch(rf"v{number}\.{number}\.{number}", tag)
        if match:
            versions.append(tuple(map(int, match.groups())))
    major, minor, patch = max(versions, default=(0, 0, 0))
    base = f"v{major}.{minor}.{patch}"
    history = git("log", "--no-merges", "-z", "--format=%B", f"{base}..HEAD" if versions else "HEAD")
    level = max(map(bump, history.split("\0")))
    if level:
        print({1: f"v{major}.{minor}.{patch + 1}", 2: f"v{major}.{minor + 1}.0", 3: f"v{major + 1}.0.0"}[level])


if __name__ == "__main__":
    main()
