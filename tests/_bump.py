import io, os, sys
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
old, new = sys.argv[1], sys.argv[2]
entry_path = sys.argv[3]

s = io.open("SKILL.md", encoding="utf-8", newline="").read()
assert ("version: " + old) in s, "version %s not found" % old
io.open("SKILL.md", "w", encoding="utf-8", newline="").write(
    s.replace("version: " + old, "version: " + new, 1))

entry = io.open(entry_path, encoding="utf-8").read().rstrip() + "\n\n"
s = io.open("CHANGELOG.md", encoding="utf-8", newline="").read()
head = "# Changelog\n\n"
assert s.startswith(head)
io.open("CHANGELOG.md", "w", encoding="utf-8", newline="").write(
    head + entry + s[len(head):])
io.open(entry_path, 'w', encoding='utf-8').write('')
print("bumped %s -> %s" % (old, new))
