import argparse
import unittest
from build import candidate_identity, command, load_lock

class BuildTests(unittest.TestCase):
    def args(self, **overrides):
        return argparse.Namespace(platform="linux/amd64", tag="rhythm:test", output=None, **overrides)
    def test_source_is_immutable(self):
        self.assertEqual(len(load_lock()["revision"]), 40)
    def test_build_loads_only_local_image(self):
        cmd = command(self.args())
        self.assertIn("--load", cmd)
        self.assertNotIn("--push", cmd)
        identity = candidate_identity()
        self.assertIn("io.rhythm.packaging.revision=" + identity["addon_revision"], cmd)
        self.assertIn("io.rhythm.build.inputs=" + identity["build_inputs_sha256"], cmd)
        self.assertIn("BUILD_VERSION=" + identity["version"], cmd)
        self.assertIn("RHYTHM_SOURCE_SHA=" + identity["source_revision"], cmd)
        self.assertIn("RHYTHM_PACKAGING_REVISION=" + identity["addon_revision"], cmd)
        self.assertIn("RHYTHM_BUILD_INPUTS_SHA256=" + identity["build_inputs_sha256"], cmd)
    def test_multiarch_requires_archive(self):
        args = self.args(); args.platform = "linux/amd64,linux/arm64"
        with self.assertRaises(ValueError): command(args)
        args.output = "candidate.tar"
        self.assertTrue(any(part.startswith("type=oci,dest=") for part in command(args)))
    def test_rejects_unsupported_architecture(self):
        args = self.args(); args.platform = "linux/arm/v7"
        with self.assertRaises(ValueError): command(args)

if __name__ == "__main__": unittest.main()
