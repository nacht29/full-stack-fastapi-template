"""
Check release-notes.md and add today's date to the latest release header if missing.

1. Open release-notes.md.
2. Look from top to bottom for the first line shaped like ## 1.2.3 or ## 1.2.3 (date).
3. Treat that first matching header as the latest release.
4. If it already has a date, stop successfully.
5. If it has no date, add today’s date and rewrite the file.
6. If no release header is found at all, exit with an error.
"""

import re
import sys
from datetime import date

RELEASE_NOTES_FILE = "release-notes.md"
RELEASE_HEADER_PATTERN = re.compile(r"^## (\d+\.\d+\.\d+)\s*(\(.*\))?\s*$")


def main() -> None:
	with open(RELEASE_NOTES_FILE) as f:
		lines = f.readlines()

	for i, line in enumerate(lines):
		match = RELEASE_HEADER_PATTERN.match(line)
		if not match:
			continue

		version = match.group(1) # 	Gets the first captured regex group: the version number, like 0.7.1
		date_part = match.group(2) # Gets the second captured regex group: the parenthesized date, if present. If no date exists, this will be None.

		if date_part: # check if date is already added to release notes
			print(f"Latest release {version} already has a date: {date_part}")
			sys.exit(0)

		today = date.today().isoformat()
		lines[i] = f"## {version} ({today})\n" # Replaces the current release header line with one that includes today’s date. \n adds the newline back.
		print(f"Added date: {version} ({today})")

		with open(RELEASE_NOTES_FILE, "w") as f: #  Reopens release-notes.md in write mode. "w" overwrites the file contents.
			f.writelines(lines) # Writes the modified list of lines back into the file.
		sys.exit(0)

	print("No release header found")
	sys.exit(1)


if __name__ == "__main__":
	main()
