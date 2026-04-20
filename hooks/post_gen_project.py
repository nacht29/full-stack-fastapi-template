"""
Normalises .sh script syntax

1.	Search recursively through this directory and all subdirectories
2.	Match files whose names end in .sh
3.	The reason this script matters: shell scripts often fail or behave weirdly on Linux/macOS if they have Windows CRLF line endings.
	For example, a script may produce errors involving ^M. This hook normalizes all .sh files after the project is generated.
"""

from pathlib import Path

path: Path
for path in Path(".").glob("**/*.sh"): # Loops over every .sh file under the current directory as binary
    data = path.read_bytes()
    lf_data = data.replace(b"\r\n", b"\n") # Replaces every Windows line ending, \r\n, with a Unix line ending, \n
    path.write_bytes(lf_data)
