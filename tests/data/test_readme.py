from __future__ import annotations

from pathlib import Path
import re
import unittest

from backend.datasets import get_dataset_profile


ROOT = Path(__file__).resolve().parents[2]


class ReadmeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_local_links_and_selected_anchors_resolve(self) -> None:
        for target in re.findall(r"\]\(([^)]+)\)", self.readme):
            if re.match(r"^[a-z]+://", target):
                continue
            filename, _, anchor = target.partition("#")
            path = ROOT / filename if filename else ROOT / "README.md"
            with self.subTest(target=target):
                self.assertTrue(path.is_file(), f"Missing README target: {target}")
                if anchor:
                    headings = re.findall(r"^#+\s+(.+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
                    slugs = {re.sub(r"[^\w -]", "", title.lower()).replace(" ", "-") for title in headings}
                    self.assertIn(anchor, slugs)

    def test_main_setup_uses_v45_and_its_release_matched_mouse_profile(self) -> None:
        self.assertIn("./scripts/setup_local.sh\n", self.readme)
        mouse_ids = re.findall(r"--dataset (mouse-[a-z0-9-]+)", self.readme)
        self.assertTrue(mouse_ids)
        self.assertEqual(set(mouse_ids), {"mouse-gencode-m34"})
        human = get_dataset_profile("human-gencode-v45")
        mouse = get_dataset_profile(mouse_ids[0])
        self.assertEqual(human["ensembl_release"], mouse["ensembl_release"])
        self.assertEqual(mouse["ensembl_release"], 111)
        self.assertEqual(mouse["gencode_release"], "M34")
        self.assertNotIn("human-gencode-v50", self.readme)
        self.assertNotIn("mouse-gencode-m39", self.readme)

    def test_readme_remains_a_short_app_and_setup_guide(self) -> None:
        self.assertLess(len(self.readme.split()), 1000)
        self.assertNotIn("Previously named", self.readme)
        self.assertIn("## Install", self.readme)
        self.assertIn("## Use", self.readme)
        self.assertIn("## Screenshots", self.readme)
        self.assertIn("docs/LOCAL_TRANSCRIPT_BROWSER_IMPLEMENTATION_PLAN.md", self.readme)


if __name__ == "__main__":
    unittest.main()
