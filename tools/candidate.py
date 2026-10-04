#!/usr/bin/env python3
"""Smoke-test local images and assemble a release archive without rebuilding."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from build import ROOT, candidate_identity, require_clean

IMAGE = "ghcr.io/sticktrk/rhythm-home-assistant"
INDEX_TYPE = "application/vnd.oci.image.index.v1+json"
PLATFORMS = {"linux/amd64", "linux/arm64"}
DIGEST_RE = r"sha256:[0-9a-f]{64}"


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity():
    return candidate_identity()


def validate_config(config, expected):
    platform = config.get("os", "") + "/" + config.get("architecture", "")
    if platform not in PLATFORMS:
        raise ValueError("Unsupported image platform: " + platform)
    labels = config.get("config", {}).get("Labels", {})
    for key, value in {"io.rhythm.product.revision": expected["source_revision"],
                       "io.rhythm.packaging.revision": expected["addon_revision"],
                       "io.rhythm.build.inputs": expected["build_inputs_sha256"],
                       "io.hass.version": expected["version"], "io.hass.type": "app",
                       "io.hass.arch": {"linux/arm64": "aarch64", "linux/amd64": "amd64"}[platform]}.items():
        if labels.get(key) != value:
            raise ValueError("Image provenance mismatch: " + key)
    return platform


def read_blob(layout, descriptor, *, metadata=True):
    value = descriptor.get("digest", "")
    if not re.fullmatch(DIGEST_RE, value):
        raise ValueError("Expected SHA-256 OCI descriptor")
    path = layout / "blobs" / "sha256" / value.split(":")[1]
    if path.is_symlink() or not path.is_file() or path.stat().st_size != descriptor.get("size"):
        raise ValueError("Missing OCI blob or descriptor size mismatch")
    if file_hash(path) != value.split(":")[1]:
        raise ValueError("OCI blob digest mismatch")
    if not metadata:
        return None
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Oversized OCI metadata")
    return json.loads(path.read_bytes())


def inspect_layout(layout, expected):
    """Verify image labels and every referenced blob, including layer contents."""
    platforms = {}
    descriptors = {}

    def visit(descriptor):
        document = read_blob(layout, descriptor)
        if "manifests" in document:
            for child in document["manifests"]:
                visit(child)
            return
        config = read_blob(layout, document["config"])
        platform = validate_config(config, expected)
        if platform in platforms:
            raise ValueError("Duplicate platform: " + platform)
        advertised = descriptor.get("platform")
        if advertised and (advertised.get("os") + "/" + advertised.get("architecture")) != platform:
            raise ValueError("Manifest platform and image configuration disagree")
        for layer in document["layers"]:
            read_blob(layout, layer, metadata=False)
        platforms[platform] = {"manifest_digest": descriptor["digest"],
                               "config_digest": document["config"]["digest"]}
        descriptors[platform] = {key: descriptor[key] for key in ("mediaType", "digest", "size")}
        os_name, arch = platform.split("/")
        descriptors[platform]["platform"] = {"os": os_name, "architecture": arch}

    for descriptor in json.loads((layout / "index.json").read_text())["manifests"]:
        visit(descriptor)
    return platforms, descriptors


def save_layout(archive_path, layout, version):
    """Keep Docker's native OCI bytes, including health checks and compression."""
    with tarfile.open(archive_path) as archive:
        names = set(archive.getnames())
        if {"index.json", "oci-layout"} <= names:
            copied = set()
            for member in archive:
                if member.name not in {"index.json", "oci-layout"} and not re.fullmatch(
                        r"blobs/sha256/[0-9a-f]{64}", member.name):
                    continue
                if not member.isfile() or member.name in copied:
                    raise ValueError("Invalid or duplicate Docker OCI archive member")
                copied.add(member.name)
                destination = layout / member.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
            return
    # Classic Docker stores export a Docker-save archive rather than an OCI
    # layout. Keep Docker schema 2; default OCI conversion drops Healthcheck.
    subprocess.run(["skopeo", "copy", "--format", "v2s2", "docker-archive:" + str(archive_path),
                    "oci:" + str(layout) + ":" + version], check=True)


def tested_digest(details, kind):
    if kind not in {"manifest", "config"}:
        raise ValueError("Unknown tested image digest kind")
    return details[kind + "_digest"]


def export_image(image, output):
    """The smoke and export use the same immutable Docker image ID."""
    require_clean()
    expected = identity()
    info = json.loads(subprocess.check_output(["docker", "image", "inspect", image]))[0]
    platform = validate_config({"os": info["Os"], "architecture": info["Architecture"],
                                "config": info["Config"]}, expected)
    image_id = info["Id"]
    # Containerd-backed Docker reports the manifest as Id; classic Docker
    # reports its configuration. Never compare these two different identities.
    descriptor = info.get("Descriptor")
    digest_kind = "manifest" if descriptor else "config"
    if descriptor and descriptor.get("digest") != image_id:
        raise ValueError("Docker image ID and descriptor disagree")
    if output.exists():
        raise ValueError("Export destination already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path = output.parent / (output.name + ".smoke.log")
    daemon_arch = subprocess.check_output(["docker", "info", "--format", "{{.Architecture}}"], text=True).strip()
    daemon_arch = {"aarch64": "arm64", "x86_64": "amd64"}.get(daemon_arch, daemon_arch)
    execution = "native" if platform == "linux/" + daemon_arch else "emulated"
    with log_path.open("w") as log:
        result = subprocess.run([sys.executable, str(ROOT / "tools/smoke.py"), "--image", image_id],
                                stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError("Image smoke test failed; inspect " + str(log_path))
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        layout = Path(temp) / "image"
        saved = Path(temp) / "docker-save.tar"
        subprocess.run(["docker", "image", "save", "--output", str(saved), image_id], check=True)
        save_layout(saved, layout, expected["version"])
        platforms, _ = inspect_layout(layout, expected)
        if set(platforms) != {platform} or tested_digest(platforms[platform], digest_kind) != image_id:
            raise ValueError("Export changed the tested image " + digest_kind)
        saved.unlink()
        shutil.copyfile(log_path, Path(temp) / "smoke.log")
        check = {"status": "passed", "execution": execution, "evidence": "smoke.log",
                 "evidence_sha256": file_hash(log_path),
                 "tested_config_digest": platforms[platform]["config_digest"],
                 "tested_image_id": image_id, "tested_image_digest_kind": digest_kind}
        receipt = expected | {"platforms": platforms, "smoke_tested_image_id": image_id,
                              "smoke_tested_image_digest_kind": digest_kind,
                              "checks": {platform: check}}
        (Path(temp) / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        shutil.move(temp, output)
    print("Exported smoke-tested " + platform + " image to " + str(output))


def assemble(exports, output, expected=None):
    expected = expected or identity()
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("Candidate destination already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    platforms, descriptors, checks = {}, {}, {}
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        layout = Path(temp)
        blobs = layout / "blobs/sha256"
        blobs.mkdir(parents=True)
        for export in exports:
            receipt = json.loads((export / "receipt.json").read_text())
            if any(receipt.get(key) != value for key, value in expected.items()):
                raise ValueError("Exports must have identical source, packaging and version")
            found, entries = inspect_layout(export / "image", expected)
            if len(found) != 1 or found != receipt.get("platforms"):
                raise ValueError("Export receipt does not match its image")
            details = next(iter(found.values()))
            digest_kind = receipt.get("smoke_tested_image_digest_kind")
            if tested_digest(details, digest_kind) != receipt.get("smoke_tested_image_id"):
                raise ValueError("Export is not the smoke-tested image")
            platform = next(iter(found))
            check = receipt.get("checks", {}).get(platform, {})
            if (check.get("status") != "passed" or check.get("execution") not in {"native", "emulated"}
                    or check.get("tested_config_digest") != found[platform]["config_digest"]
                    or check.get("tested_image_id") != receipt["smoke_tested_image_id"]
                    or check.get("tested_image_digest_kind") != digest_kind
                    or check.get("evidence") != "smoke.log"
                    or file_hash(export / "smoke.log") != check.get("evidence_sha256")):
                raise ValueError("Export smoke evidence does not match the tested image")
            if set(platforms) & set(found):
                raise ValueError("Duplicate exported architecture")
            platforms.update(found)
            descriptors.update(entries)
            log_path = output.with_suffix("." + platform.split("/")[1] + ".smoke.log")
            shutil.copyfile(export / "smoke.log", log_path)
            checks[platform] = check | {"evidence": log_path.name}
            for path in (export / "image/blobs/sha256").iterdir():
                if not re.fullmatch(r"[0-9a-f]{64}", path.name) or path.is_symlink() or not path.is_file():
                    raise ValueError("Invalid OCI blob path")
                if file_hash(path) != path.name:
                    raise ValueError("Invalid OCI blob content")
                if not (blobs / path.name).exists():
                    shutil.copyfile(path, blobs / path.name)
        if set(platforms) != PLATFORMS:
            raise ValueError("Candidate requires exactly linux/amd64 and linux/arm64")
        index = json_bytes({"schemaVersion": 2, "mediaType": INDEX_TYPE,
                            "manifests": [descriptors[key] for key in sorted(descriptors)]})
        index_digest = digest(index)
        (blobs / index_digest.split(":")[1]).write_bytes(index)
        (layout / "oci-layout").write_bytes(json_bytes({"imageLayoutVersion": "1.0.0"}))
        (layout / "index.json").write_bytes(json_bytes({"schemaVersion": 2, "manifests": [{
            "mediaType": INDEX_TYPE, "digest": index_digest, "size": len(index),
            "annotations": {"org.opencontainers.image.ref.name": expected["version"]}}]}))
        with tarfile.open(output, "w") as archive:
            for path in sorted(layout.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=str(path.relative_to(layout)), recursive=False)
    receipt = expected | {"artifact_sha256": file_hash(output),
                          "manifest_digest": index_digest, "platforms": platforms, "checks": checks}
    output.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    export = commands.add_parser("export", help="Smoke-test and export one locally built image")
    export.add_argument("--image", required=True)
    export.add_argument("--output", type=Path, required=True)
    merge = commands.add_parser("assemble", help="Combine two tested exports without rebuilding")
    merge.add_argument("exports", type=Path, nargs=2)
    merge.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "export":
        export_image(args.image, args.output.resolve())
    else:
        require_clean()
        receipt = assemble(args.exports, args.output.resolve())
        print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
