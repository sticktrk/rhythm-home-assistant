#!/usr/bin/env python3
"""Build an immutable local candidate; publishing is outside this repository."""
import argparse
import json
import platform
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_lock():
    lock = json.loads((ROOT / "source.lock.json").read_text())
    if lock["repository"] != "https://github.com/sticktrk/rhythm-os" or not re.fullmatch(r"[0-9a-f]{40}", lock["revision"]):
        raise ValueError("Expected an immutable public rhythm-os revision")
    dockerfile = (ROOT / "rhythm/Dockerfile").read_text()
    if dockerfile.count("ARG RHYTHM_SOURCE_SHA=" + lock["revision"]) != 2:
        raise ValueError("Dockerfile and source.lock.json disagree")
    return lock


def command(args):
    load_lock()
    arch = args.platform or ("linux/arm64" if platform.machine() in ("arm64", "aarch64") else "linux/amd64")
    if any(p not in ("linux/arm64", "linux/amd64") for p in arch.split(",")):
        raise ValueError("Only amd64 and arm64 are supported")
    result = ["docker", "buildx", "build", "--platform", arch, "--tag", args.tag]
    if args.output:
        result += ["--output", "type=oci,dest=" + str(Path(args.output).resolve())]
    elif "," in arch:
        raise ValueError("A multi-architecture candidate requires --output candidate.oci.tar")
    else:
        result += ["--load"]
    return result + [str(ROOT / "rhythm")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", help="linux/amd64, linux/arm64, or both comma-separated")
    parser.add_argument("--tag", default="rhythm-home-assistant:review")
    parser.add_argument("--output", help="Save an OCI archive instead of loading locally")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cmd = command(args)
    print(" ".join(cmd), flush=True)
    if not args.dry_run:
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
