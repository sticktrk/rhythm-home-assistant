import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from build import build_inputs_hash
from candidate import (IMAGE, assemble, digest, export_image, file_hash,
                       inspect_layout, json_bytes, save_layout)
from promote import promote, validate_catalog, validate_receipt, verify_registry, version_key


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.expected = {"schema_version": 1, "image": IMAGE, "source_revision": "a" * 40,
                         "addon_revision": "b" * 40, "version": "0.2.0-dev.2026100401",
                         "build_inputs_sha256": "c" * 64}

    def fixture(self, arch, *, identity=None, folder=None):
        expected = identity or self.expected
        export = self.root / (folder or arch)
        layout = export / "image"
        blobs = layout / "blobs/sha256"
        blobs.mkdir(parents=True)

        def blob(value, media):
            raw = value if isinstance(value, bytes) else json_bytes(value)
            value_digest = digest(raw)
            (blobs / value_digest.split(":")[1]).write_bytes(raw)
            return {"mediaType": media, "digest": value_digest, "size": len(raw)}

        config = blob({"os": "linux", "architecture": arch, "config": {
            "Healthcheck": {"Test": ["CMD", "curl", "http://127.0.0.1:8787/health"]}, "Labels": {
            "io.rhythm.product.revision": expected["source_revision"],
            "io.rhythm.packaging.revision": expected["addon_revision"],
            "io.rhythm.build.inputs": expected["build_inputs_sha256"],
            "io.hass.version": expected["version"], "io.hass.type": "app",
            "io.hass.arch": "aarch64" if arch == "arm64" else "amd64"}}},
            "application/vnd.oci.image.config.v1+json")
        layer = blob(b"fixture layer", "application/vnd.oci.image.layer.v1.tar")
        manifest = blob({"schemaVersion": 2, "config": config, "layers": [layer]},
                        "application/vnd.oci.image.manifest.v1+json")
        (layout / "index.json").write_bytes(json_bytes({"schemaVersion": 2, "manifests": [manifest]}))
        (layout / "oci-layout").write_bytes(json_bytes({"imageLayoutVersion": "1.0.0"}))
        (export / "smoke.log").write_text("Real-image smoke completed\n")
        platform = "linux/" + arch
        receipt = expected | {"platforms": {platform: {"manifest_digest": manifest["digest"],
                                                     "config_digest": config["digest"]}},
                              "smoke_tested_image_id": config["digest"],
                              "smoke_tested_image_digest_kind": "config", "checks": {platform: {
                                  "status": "passed", "execution": "native", "evidence": "smoke.log",
                                  "evidence_sha256": file_hash(export / "smoke.log"),
                                  "tested_config_digest": config["digest"], "tested_image_id": config["digest"],
                                  "tested_image_digest_kind": "config"}}}
        (export / "receipt.json").write_text(json.dumps(receipt))
        return export, config, layer

    def candidate(self):
        amd, _, _ = self.fixture("amd64")
        arm, _, _ = self.fixture("arm64")
        output = self.root / "candidate.oci.tar"
        receipt = assemble([amd, arm], output, self.expected)
        return output, receipt

    def test_assemble_preserves_both_smoked_image_digests_and_logs(self):
        output, receipt = self.candidate()
        self.assertEqual(receipt["artifact_sha256"], file_hash(output))
        layout = self.root / "assembled"
        with tarfile.open(output) as archive:
            archive.extractall(layout, filter="data")
        platforms, _ = inspect_layout(layout, self.expected)
        self.assertEqual(platforms, receipt["platforms"])
        self.assertEqual(set(platforms), {"linux/amd64", "linux/arm64"})
        index = json.loads((layout / "index.json").read_text())["manifests"][0]
        self.assertEqual(index["digest"], receipt["manifest_digest"])
        for check in receipt["checks"].values():
            self.assertEqual(check["evidence_sha256"], file_hash(self.root / check["evidence"]))

    def test_tampered_layer_rejected(self):
        export, _, layer = self.fixture("arm64")
        path = export / "image/blobs/sha256" / layer["digest"].split(":")[1]
        path.write_bytes(b"changed layer")
        with self.assertRaisesRegex(ValueError, "size mismatch|digest mismatch"):
            inspect_layout(export / "image", self.expected)

    def test_wrong_source_packaging_or_version_rejected(self):
        for i, key in enumerate(("source_revision", "addon_revision", "version", "build_inputs_sha256")):
            changed = self.expected | {key: "wrong"}
            export, _, _ = self.fixture("arm64", identity=changed, folder=str(i))
            with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                inspect_layout(export / "image", self.expected)

    def test_duplicate_or_mixed_exports_rejected(self):
        amd, _, _ = self.fixture("amd64")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            assemble([amd, amd], self.root / "duplicate.tar", self.expected)
        arm, _, _ = self.fixture("arm64", identity=self.expected | {"version": "0.3.0"})
        with self.assertRaisesRegex(ValueError, "identical"):
            assemble([amd, arm], self.root / "mixed.tar", self.expected)

    def test_changed_smoke_log_rejected(self):
        amd, _, _ = self.fixture("amd64")
        arm, _, _ = self.fixture("arm64")
        (arm / "smoke.log").write_text("substituted evidence")
        with self.assertRaisesRegex(ValueError, "smoke evidence"):
            assemble([amd, arm], self.root / "candidate.tar", self.expected)

    def test_export_identity_cannot_substitute_config_for_manifest(self):
        amd, _, _ = self.fixture("amd64")
        arm, _, _ = self.fixture("arm64")
        receipt_path = arm / "receipt.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["smoke_tested_image_digest_kind"] = "manifest"
        receipt["checks"]["linux/arm64"]["tested_image_digest_kind"] = "manifest"
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "not the smoke-tested image"):
            assemble([amd, arm], self.root / "candidate.tar", self.expected)

    def test_promotion_rejects_wrong_tested_digest_kind(self):
        _, receipt = self.candidate()
        receipt["checks"]["linux/arm64"]["tested_image_digest_kind"] = "manifest"
        with self.assertRaisesRegex(ValueError, "matching smoke evidence"):
            validate_receipt(receipt)

    def test_export_preserves_containerd_manifest_id_config_and_healthcheck(self):
        fixture, config, _ = self.fixture("arm64")
        image_config = json.loads((fixture / "image/blobs/sha256" / config["digest"].split(":")[1]).read_text())
        manifest = json.loads((fixture / "image/index.json").read_text())["manifests"][0]
        info = [{"Os": "linux", "Architecture": "arm64", "Config": image_config["config"],
                 "Id": manifest["digest"], "Descriptor": manifest}]
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if command[0] == "docker":
                with tarfile.open(command[4], "w") as archive:
                    for path in (fixture / "image").rglob("*"):
                        if path.is_file():
                            archive.add(path, arcname=str(path.relative_to(fixture / "image")))
            else:
                kwargs["stdout"].write("Smoke passed\n")
            return subprocess.CompletedProcess(command, 0)

        with patch("candidate.require_clean"), patch("candidate.identity", return_value=self.expected), \
                patch("candidate.subprocess.check_output", side_effect=[json.dumps(info).encode(), "aarch64\n"]), \
                patch("candidate.subprocess.run", side_effect=run):
            export_image("mutable:test", self.root / "export")
        self.assertEqual(calls[0][-1], manifest["digest"])
        self.assertEqual(calls[1][:4], ["docker", "image", "save", "--output"])
        self.assertEqual(calls[1][-1], manifest["digest"])
        receipt = json.loads((self.root / "export/receipt.json").read_text())
        check = receipt["checks"]["linux/arm64"]
        self.assertEqual(check["execution"], "native")
        self.assertEqual(check["tested_image_id"], manifest["digest"])
        self.assertEqual(check["tested_config_digest"], config["digest"])
        self.assertEqual(check["tested_image_digest_kind"], "manifest")
        saved_config = self.root / "export/image/blobs/sha256" / config["digest"].split(":")[1]
        self.assertEqual(json.loads(saved_config.read_text())["config"]["Healthcheck"],
                         image_config["config"]["Healthcheck"])

    def test_classic_save_uses_schema2_and_keeps_configuration_id(self):
        fixture, config, _ = self.fixture("arm64")
        image_config = json.loads((fixture / "image/blobs/sha256" / config["digest"].split(":")[1]).read_text())
        info = [{"Os": "linux", "Architecture": "arm64", "Config": image_config["config"],
                 "Id": config["digest"]}]
        commands = []

        def run(command, **kwargs):
            commands.append(command)
            if command[0] == "docker":
                with tarfile.open(command[4], "w") as archive:
                    member = tarfile.TarInfo("manifest.json")
                    member.size = 2
                    archive.addfile(member, io.BytesIO(b"[]"))
            elif command[0] == "skopeo":
                self.assertEqual(command[:4], ["skopeo", "copy", "--format", "v2s2"])
                shutil.copytree(fixture / "image", Path(command[-1].split(":")[1]))
            else:
                kwargs["stdout"].write("Smoke passed\n")
            return subprocess.CompletedProcess(command, 0)

        with patch("candidate.require_clean"), patch("candidate.identity", return_value=self.expected), \
                patch("candidate.subprocess.check_output", side_effect=[json.dumps(info).encode(), "aarch64\n"]), \
                patch("candidate.subprocess.run", side_effect=run):
            export_image("mutable:test", self.root / "classic")
        receipt = json.loads((self.root / "classic/receipt.json").read_text())
        self.assertEqual(receipt["checks"]["linux/arm64"]["tested_image_id"], config["digest"])
        self.assertEqual(receipt["checks"]["linux/arm64"]["tested_image_digest_kind"], "config")

    def test_native_save_copies_compressed_layer_bytes_without_conversion(self):
        archive_path = self.root / "compressed.tar"
        raw = b"\x28\xb5\x2f\xfdzstd fixture bytes"
        name = "blobs/sha256/" + digest(raw).split(":")[1]
        with tarfile.open(archive_path, "w") as archive:
            for filename, data in {"oci-layout": b"{}", "index.json": b"{}", name: raw}.items():
                member = tarfile.TarInfo(filename)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        with patch("candidate.subprocess.run") as convert:
            save_layout(archive_path, self.root / "native", self.expected["version"])
        convert.assert_not_called()
        self.assertEqual((self.root / "native" / name).read_bytes(), raw)

    def test_anonymous_registry_requires_manifest_and_every_platform(self):
        output, receipt = self.candidate()
        layout = self.root / "published"
        with tarfile.open(output) as archive:
            archive.extractall(layout, filter="data")
        raw = (layout / "blobs/sha256" / receipt["manifest_digest"].split(":")[1]).read_bytes()
        calls = []

        def copy(command, **kwargs):
            calls.append(command)
            destination = Path(command[-1].split(":")[1])
            shutil.copytree(layout, destination)

        with patch("promote.subprocess.check_output", return_value=raw) as inspect, \
                patch("promote.subprocess.run", side_effect=copy):
            verify_registry(receipt)
        self.assertEqual(inspect.call_count, 2)
        self.assertTrue(all("--no-creds" in call.args[0] for call in inspect.call_args_list))
        self.assertIn("--src-no-creds", calls[0])
        self.assertIn("--all", calls[0])
        self.assertIn("docker://" + IMAGE + "@" + receipt["manifest_digest"], calls[0])
        with patch("promote.subprocess.check_output", return_value=b"wrong manifest"):
            with self.assertRaisesRegex(ValueError, "does not match"):
                verify_registry(receipt)

    def test_failed_smoke_retains_log_without_exporting(self):
        fixture, config, _ = self.fixture("arm64")
        image_config = json.loads((fixture / "image/blobs/sha256" / config["digest"].split(":")[1]).read_text())
        info = [{"Os": "linux", "Architecture": "arm64", "Config": image_config["config"],
                 "Id": config["digest"]}]
        with patch("candidate.require_clean"), patch("candidate.identity", return_value=self.expected), \
                patch("candidate.subprocess.check_output", side_effect=[json.dumps(info).encode(), "aarch64\n"]), \
                patch("candidate.subprocess.run", return_value=subprocess.CompletedProcess([], 1)) as run:
            with self.assertRaisesRegex(ValueError, "smoke test failed"):
                export_image("mutable:test", self.root / "failed")
        self.assertEqual(run.call_count, 1)
        self.assertTrue((self.root / "failed.smoke.log").exists())
        self.assertFalse((self.root / "failed").exists())

    def test_private_or_missing_image_cannot_change_catalog(self):
        self.expected["version"] = "0.2.1-dev.2026100402"
        _, receipt = self.candidate()
        (self.root / "rhythm").mkdir()
        config = 'name: Rhythm\nversion: "0.2.0"\n'
        (self.root / "rhythm/config.yaml").write_text(config)
        with patch("promote.load_lock", return_value={"revision": receipt["source_revision"], "version": receipt["version"]}), \
                patch("promote.build_inputs_hash", return_value=receipt["build_inputs_sha256"]), \
                patch("promote.subprocess.check_output", side_effect=subprocess.CalledProcessError(1, ["skopeo"])):
            with self.assertRaises(subprocess.CalledProcessError):
                promote(receipt, self.root)
        self.assertEqual((self.root / "rhythm/config.yaml").read_text(), config)
        self.assertFalse((self.root / "release.json").exists())

    def test_new_candidate_leaves_published_catalog_version_intact(self):
        _, release = self.candidate()
        config = 'version: "' + release["version"] + '"\nimage: ' + IMAGE + '\n'
        candidate = {"version": "0.2.0-dev.2026100402", "build_inputs_sha256": "d" * 64}
        validate_catalog(config, release, candidate)
        candidate["version"] = release["version"]
        with self.assertRaisesRegex(ValueError, "newer immutable"):
            validate_catalog(config, release, candidate)
        with self.assertRaisesRegex(ValueError, "disagree"):
            validate_catalog(config.replace(release["version"], "0.3.0"), release, candidate)

    def test_unpublished_candidate_retains_earlier_development_catalog(self):
        config = 'version: "0.2.0"\n'
        candidate = {"version": "0.2.1-dev.2026100402"}
        validate_catalog(config, None, candidate)
        with self.assertRaisesRegex(ValueError, "Development catalog"):
            validate_catalog(config + "image: " + IMAGE + "\n", None, candidate)
        with self.assertRaisesRegex(ValueError, "Development catalog"):
            validate_catalog('version: "0.2.2"\n', None, candidate)

    def test_verified_promotion_advances_held_catalog_and_retains_build_provenance(self):
        self.expected["version"] = "0.2.1-dev.2026100402"
        _, receipt = self.candidate()
        (self.root / "rhythm").mkdir()
        (self.root / "rhythm/config.yaml").write_text('name: Rhythm\nversion: "0.2.0"\n')
        with patch("promote.load_lock", return_value={"revision": receipt["source_revision"], "version": receipt["version"]}), \
                patch("promote.build_inputs_hash", return_value=receipt["build_inputs_sha256"]), \
                patch("promote.verify_registry") as verify:
            promote(receipt, self.root)
        verify.assert_called_once_with(receipt)
        config = (self.root / "rhythm/config.yaml").read_text()
        saved = json.loads((self.root / "release.json").read_text())
        self.assertIn('version: "0.2.1-dev.2026100402"\n', config)
        self.assertIn("image: " + IMAGE + "\n", config)
        self.assertEqual(saved, receipt)
        validate_catalog(config, saved, self.expected)

    def test_changed_build_command_requires_new_version_but_catalog_metadata_does_not(self):
        _, release = self.candidate()
        root = self.root / "checkout"
        (root / "rhythm/rootfs").mkdir(parents=True)
        (root / "tools").mkdir()
        (root / "source.lock.json").write_text("locked inputs")
        (root / "rhythm/Dockerfile").write_text("FROM runtime")
        (root / "tools/build.py").write_text("original build arguments")
        with patch("build.ROOT", root):
            original = build_inputs_hash()
            (root / "README.md").write_text("documentation changed")
            (root / "rhythm/config.yaml").write_text("image: published-image")
            self.assertEqual(build_inputs_hash(), original)
            (root / "tools/build.py").write_text("changed effective build arguments")
            changed = build_inputs_hash()
        self.assertNotEqual(original, changed)
        release["build_inputs_sha256"] = original
        config = 'version: "' + release["version"] + '"\nimage: ' + IMAGE + '\n'
        with self.assertRaisesRegex(ValueError, "newer immutable"):
            validate_catalog(config, release, {"version": release["version"], "build_inputs_sha256": changed})

    def test_version_order_and_development_fallback(self):
        self.assertLess(version_key("0.2.0-dev.9"), version_key("0.2.0-dev.10"))
        self.assertLess(version_key("0.2.0-dev.10"), version_key("0.2.0"))
        validate_catalog('version: "0.2.0"\n', None, {"version": "0.2.0"})
        with self.assertRaisesRegex(ValueError, "Development catalog"):
            validate_catalog('version: "0.2.0"\nimage: ' + IMAGE + '\n', None, {"version": "0.2.0"})


if __name__ == "__main__":
    unittest.main()
