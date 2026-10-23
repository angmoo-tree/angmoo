"""Pass workflow inputs as argv, never interpolate them as shell code."""
import os
import subprocess
import sys


def main():
    args = [sys.executable, "-m", "scripts.release.publish"]
    for name in ("operation", "source", "tag", "windows-run", "windows-attempt", "windows-artifact", "candidate-run", "candidate-attempt", "candidate-artifact", "review-ref", "product-root", "output"):
        value = os.environ.get("RELEASE_" + name.upper().replace("-", "_"))
        if value:
            args += ["--" + name, value]
    subprocess.run(args, check=True)


if __name__ == "__main__":
    main()
