#!/usr/bin/env python3
"""Script to run selftest and capture output to run.log"""

import sys
import subprocess

if __name__ == "__main__":
    try:
        # Run the selftest command
        result = subprocess.run(
            [sys.executable, "-m", "src.app", "selftest", "--verbose", "normal"],
            capture_output=True,
            text=True,
            check=True
        )

        # Write output to run.log
        with open("run.log", "w") as f:
            f.write(result.stdout)

        print("Selftest completed successfully. Output captured to run.log")
    except subprocess.CalledProcessError as e:
        # Write error output to run.log
        with open("run.log", "w") as f:
            f.write(e.stdout)
            f.write("\nERROR:\n")
            f.write(e.stderr)

        print(f"Selftest failed. Error output captured to run.log")
        sys.exit(1)