#!/usr/bin/env python3
"""Advertise a published image only after anonymously verifying the whole artifact."""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from build import ROOT, VERSION_RE, build_inputs_hash, load_lock
from candidate import IMAGE, PLATFORMS, DIGEST_RE, digest, inspect_layout, tested_digest


def version_key(version):
    if not re.fullmatch(VERSION_RE, version):
        raise ValueError("Invalid release version")
    base, _, prerelease = version.partition("-dev.")
    return (*map(int, base.split(".")), not prerelease, int(prerelease or 0))


def validate_receipt(receipt):
    if receipt.get("schema_version") != 1 or receipt.get("image") != IMAGE:
        raise ValueError("Unexpected release receipt identity")
    version_key(receipt["version"])
    for key in ("source_revision", "addon_revision"):
        if not re.fullmatch(r"[0-9a-f]{40}", receipt.get(key, "")):
            raise ValueError("Invalid release revision")
    for key in ("artifact_sha256", "build_inputs_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", receipt.get(key, "")):
            raise ValueError("Invalid release hash")
    if not re.fullmatch(DIGEST_RE, receipt.get("manifest_digest", "")):
        raise ValueError("Invalid release manifest digest")
    if set(receipt.get("platforms", {})) != PLATFORMS:
        raise ValueError("Release requires both supported architectures")
    for platform, value in receipt["platforms"].items():
        if any(not re.fullmatch(DIGEST_RE, value.get(key, ""))
               for key in ("manifest_digest", "config_digest")):
            raise ValueError("Invalid platform digest")
        check = receipt.get("checks", {}).get(platform, {})
        if (check.get("status") != "passed" or check.get("execution") not in {"native", "emulated"}
                or check.get("tested_config_digest") != value["config_digest"]
                or check.get("tested_image_id") != tested_digest(value, check.get("tested_image_digest_kind"))):
            raise ValueError("Release must contain matching smoke evidence")


def verify_registry(receipt):
    validate_receipt(receipt)
    tagged = "docker://" + IMAGE + ":" + receipt["version"]

    def verify_tag():
        raw = subprocess.check_output(["skopeo", "inspect", "--no-creds", "--raw", tagged])
        if digest(raw) != receipt["manifest_digest"]:
            raise ValueError("Published version does not match candidate manifest")

    verify_tag()
    with tempfile.TemporaryDirectory() as temp:
        layout = Path(temp) / "image"
        subprocess.run(["skopeo", "copy", "--all", "--src-no-creds", "--preserve-digests",
                        "docker://" + IMAGE + "@" + receipt["manifest_digest"],
                        "oci:" + str(layout) + ":" + receipt["version"]], check=True)
        found, _ = inspect_layout(layout, receipt)
        if found != receipt["platforms"]:
            raise ValueError("Registry images differ from the tested candidate")
    verify_tag()


def validate_catalog(config, release, candidate):
    """Published catalog stays on a real image while a newer candidate is built."""
    match = re.search(r'^version: "([^"]+)"$', config, re.M)
    if not match:
        raise ValueError("Missing catalog version")
    current = match[1]
    image = re.search(r"^image:\s*(\S+)\s*$", config, re.M)
    if release is None:
        if image or current != candidate["version"]:
            raise ValueError("Development catalog must match the source candidate without an image")
        return
    validate_receipt(release)
    if not image or image[1] != IMAGE or current != release["version"]:
        raise ValueError("Catalog and published image receipt disagree")
    if version_key(candidate["version"]) < version_key(current):
        raise ValueError("Candidate version cannot go backwards")
    if candidate["version"] == current and candidate["build_inputs_sha256"] != release["build_inputs_sha256"]:
        raise ValueError("Build inputs changed: reserve a newer immutable candidate version")


def promote(receipt, root=ROOT):
    validate_receipt(receipt)
    lock = load_lock()
    if (receipt["source_revision"] != lock["revision"] or receipt["version"] != lock["version"]
            or receipt["build_inputs_sha256"] != build_inputs_hash()):
        raise ValueError("Candidate does not match this checkout's build inputs")
    release_path = root / "release.json"
    if release_path.exists():
        previous = json.loads(release_path.read_text())
        validate_receipt(previous)
        if version_key(receipt["version"]) <= version_key(previous["version"]):
            raise ValueError("Promotion requires a newer immutable version")
    verify_registry(receipt)
    config_path = root / "rhythm/config.yaml"
    config = config_path.read_text()
    config = re.sub(r'^version: "[^"]+"$', 'version: "' + receipt["version"] + '"', config, flags=re.M)
    config = re.sub(r"^image:.*\n", "", config, flags=re.M)
    config += "image: " + IMAGE + "\n"
    config_path.write_text(config)
    release_path.write_text(json.dumps(receipt, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true", help="Verify registry without editing metadata")
    args = parser.parse_args()
    receipt = json.loads(args.candidate.read_text())
    if args.check_only:
        verify_registry(receipt)
    else:
        promote(receipt)
    print("Verified anonymous access to " + IMAGE + ":" + receipt["version"])
    if not args.check_only:
        print("Updated config.yaml and release.json locally; review and commit metadata separately.")


if __name__ == "__main__":
    main()
