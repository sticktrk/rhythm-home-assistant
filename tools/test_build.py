import argparse
import unittest
from build import command, load_lock

class BuildTests(unittest.TestCase):
    def args(self, **overrides):
        return argparse.Namespace(platform="linux/amd64", tag="rhythm:test", output=None, **overrides)
    def test_source_is_immutable(self):
        self.assertEqual(len(load_lock()["revision"]), 40)
    def test_build_loads_only_local_image(self):
        cmd = command(self.args())
        self.assertIn("--load", cmd)
        self.assertNotIn("--push", cmd)
    def test_multiarch_requires_archive(self):
        args = self.args(); args.platform = "linux/amd64,linux/arm64"
        with self.assertRaises(ValueError): command(args)
        args.output = "candidate.tar"
        self.assertTrue(any(part.startswith("type=oci,dest=") for part in command(args)))
    def test_rejects_unsupported_architecture(self):
        args = self.args(); args.platform = "linux/arm/v7"
        with self.assertRaises(ValueError): command(args)

if __name__ == "__main__": unittest.main()
