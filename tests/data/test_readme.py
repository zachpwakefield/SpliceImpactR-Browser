from __future__ import annotations

from pathlib import Path
import re
import unittest

from backend.datasets import get_dataset_profile


ROOT = Path(__file__).resolve().parents[2]
PRACTICAL_GUIDES = {
    "README.md": 700,
    "docs/README.md": 250,
    "docs/user_guide.md": 800,
    "docs/data_preparation.md": 750,
    "docs/genome_datasets.md": 350,
    "docs/reference_setup.md": 200,
    "docs/testing.md": 850,
    "docs/limitations.md": 450,
    "desktop_app/README.md": 500,
    "CONTRIBUTING.md": 200,
    "frontend/README.md": 200,
    "r/README.md": 250,
    "spliceimpactr/README.md": 150,
}


class ReadmeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def assert_local_links_resolve(self, source: Path, markdown: str) -> None:
        for target in re.findall(r"\]\(([^)]+)\)", markdown):
            if re.match(r"^[a-z]+://", target):
                continue
            filename, _, anchor = target.partition("#")
            path = source.parent / filename if filename else source
            with self.subTest(source=source.relative_to(ROOT), target=target):
                self.assertTrue(path.is_file(), f"Missing documentation target: {target}")
                if anchor:
                    headings = re.findall(r"^#+\s+(.+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
                    slugs = {re.sub(r"[^\w -]", "", title.lower()).replace(" ", "-") for title in headings}
                    self.assertIn(anchor, slugs)

    def test_readme_local_links_and_selected_anchors_resolve(self) -> None:
        self.assert_local_links_resolve(ROOT / "README.md", self.readme)

    def test_practical_guide_links_and_anchors_resolve(self) -> None:
        for filename in PRACTICAL_GUIDES:
            source = ROOT / filename
            self.assert_local_links_resolve(source, source.read_text(encoding="utf-8"))

    def test_practical_guides_remain_concise(self) -> None:
        for filename, word_limit in PRACTICAL_GUIDES.items():
            with self.subTest(filename=filename):
                markdown = (ROOT / filename).read_text(encoding="utf-8")
                self.assertLessEqual(len(markdown.split()), word_limit)
                self.assertEqual(len(re.findall(r"^\s*```", markdown, re.MULTILINE)) % 2, 0,
                                 "Documentation contains an unclosed code block")

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
        self.assertIn("./run_local.sh --dataset mouse-gencode-m34", self.readme)

    def test_readme_remains_a_short_app_and_setup_guide(self) -> None:
        self.assertLess(len(self.readme.split()), 700)
        self.assertNotIn("Previously named", self.readme)
        self.assertIn("## Install", self.readme)
        self.assertIn("## Use", self.readme)
        self.assertIn("## Screenshots", self.readme)
        self.assertIn("### Event highlights", self.readme)
        self.assertIn("docs/LOCAL_TRANSCRIPT_BROWSER_IMPLEMENTATION_PLAN.md", self.readme)

    def test_history_is_separate_from_ordinary_usage_instructions(self) -> None:
        developer_details = re.search(r"<details>(.*?)</details>", self.readme, re.DOTALL)
        self.assertIsNotNone(developer_details)
        self.assertIn("docs/LOCAL_TRANSCRIPT_BROWSER_IMPLEMENTATION_PLAN.md", developer_details.group(1))
        index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        records = index.split("## Project records", 1)[1]
        for filename in ("setup_validation.md", "review_log.md", "LOCAL_TRANSCRIPT_BROWSER_IMPLEMENTATION_PLAN.md"):
            self.assertIn(filename, records)


if __name__ == "__main__":
    unittest.main()
