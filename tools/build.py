#!/usr/bin/env python3
"""Build an immutable local candidate; publishing is outside this repository."""
import argparse
import hashlib
import json
import platform
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-dev\.(?:0|[1-9][0-9]*))?"


def revision():
    return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()


def require_clean():
    if subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip():
        raise ValueError("Commit packaging changes before building a traceable candidate")


def build_inputs_hash():
    digest = hashlib.sha256()
    paths = [ROOT / "source.lock.json", ROOT / "rhythm/Dockerfile", ROOT / "tools/build.py"]
    paths += [path for path in (ROOT / "rhythm/rootfs").rglob("*") if path.is_file()]
    for path in sorted(paths):
        data = path.read_bytes()
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0")
        digest.update(str(len(data)).encode() + b"\0" + data)
    return digest.hexdigest()


def load_lock():
    lock = json.loads((ROOT / "source.lock.json").read_text())
    if lock["repository"] != "https://github.com/sticktrk/rhythm-os" or not re.fullmatch(r"[0-9a-f]{40}", lock["revision"]):
        raise ValueError("Expected an immutable public rhythm-os revision")
    if not re.fullmatch(VERSION_RE, lock.get("version", "")):
        raise ValueError("Expected a numeric candidate version, optionally -dev.NUMBER")
    dockerfile = (ROOT / "rhythm/Dockerfile").read_text()
    if dockerfile.count("ARG RHYTHM_SOURCE_SHA=" + lock["revision"]) != 2:
        raise ValueError("Dockerfile and source.lock.json disagree")
    return lock


def candidate_identity():
    lock = load_lock()
    return {"schema_version": 1, "image": "ghcr.io/sticktrk/rhythm-home-assistant",
            "source_revision": lock["revision"], "addon_revision": revision(),
            "version": lock["version"], "build_inputs_sha256": build_inputs_hash()}


def command(args):
    lock = load_lock()
    arch = args.platform or ("linux/arm64" if platform.machine() in ("arm64", "aarch64") else "linux/amd64")
    if any(p not in ("linux/arm64", "linux/amd64") for p in arch.split(",")):
        raise ValueError("Only amd64 and arm64 are supported")
    result = ["docker", "buildx", "build", "--platform", arch, "--tag", args.tag,
              "--build-arg", "BUILD_VERSION=" + lock["version"]]
    for key, value in {"io.rhythm.packaging.revision": revision(), "io.rhythm.build.inputs": build_inputs_hash(),
                       "io.hass.version": lock["version"], "io.hass.type": "app"}.items():
        result += ["--label", key + "=" + value]
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
    parser.add_argument("--identity", action="store_true", help="Print candidate identity without building")
    args = parser.parse_args()
    if args.identity:
        print(json.dumps(candidate_identity(), indent=2))
        return
    cmd = command(args)
    print(" ".join(cmd), flush=True)
    if not args.dry_run:
        require_clean()
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
