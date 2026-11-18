"""Checks of the published text: links, required statements and a few leak patterns.

The patterns catch slips. They do not replace reading a change before publishing it.
"""
import ast
import json
import plistlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".sh", ".zsh", ".json", ".plist", ".yml", ".yaml", ".txt", ""}
DOCS = sorted((ROOT / "docs").glob("*.md"))
READMES = [ROOT / "README.md", ROOT / "README.en.md"]


def published_files():
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if not path.is_file() or rel.parts[0] == ".git" or "__pycache__" in rel.parts:
            continue
        if path.suffix in TEXT_SUFFIXES:
            yield path


class LinkTests(unittest.TestCase):
    def test_relative_links_resolve(self):
        for path in ROOT.rglob("*.md"):
            for link in re.findall(r"\]\(([^\s)]+)\)", path.read_text(encoding="utf-8")):
                if "://" in link or link.startswith(("#", "mailto:")):
                    continue
                self.assertTrue((path.parent / link.split("#")[0]).exists(), (str(path), link))

    def test_every_doc_is_linked_from_both_readmes(self):
        for readme in READMES:
            text = readme.read_text(encoding="utf-8")
            for doc in DOCS:
                self.assertIn(f"(docs/{doc.name})", text, (readme.name, doc.name))

    def test_every_doc_links_back(self):
        for doc in DOCS:
            self.assertIn("(../README.en.md)", doc.read_text(encoding="utf-8"), doc.name)

    def test_readmes_link_each_other(self):
        self.assertIn("(README.en.md)", READMES[0].read_text(encoding="utf-8"))
        self.assertIn("(README.md)", READMES[1].read_text(encoding="utf-8"))

    def test_no_external_links(self):
        # Nothing here was checked against a public source, so nothing is linked.
        for path in ROOT.rglob("*.md"):
            self.assertIsNone(re.search(r"\]\(https?://", path.read_text(encoding="utf-8")), str(path))


class HygieneTests(unittest.TestCase):
    FORBIDDEN = {
        "home folder path": "/" + r"Users/[^/<$\s\"']+/",
        "linux home path": "/" + r"home/[^/<$\s\"']+/",
        "session id": r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "ip address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        "email address": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}",
        "bearer token": r"(?i)bearer\s+[A-Za-z0-9_-]{16,}",
        "api key": r"\bsk-[A-Za-z0-9_-]{16,}",
        "launchd user domain": r"gui/\d+",
    }

    def test_no_leak_patterns(self):
        for path in published_files():
            text = path.read_text(encoding="utf-8")
            for name, pattern in self.FORBIDDEN.items():
                found = re.search(pattern, text)
                self.assertIsNone(found, (str(path.relative_to(ROOT)), name, found and found.group(0)))

    def test_no_em_dash(self):
        for path in published_files():
            self.assertNotIn(chr(0x2014), path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))

    def test_no_run_outputs_in_the_tree(self):
        for path in ROOT.rglob("*"):
            if ".git" in path.relative_to(ROOT).parts:
                continue
            self.assertNotIn(path.suffix, {".log", ".jsonl", ".retries"}, str(path))


class StatementTests(unittest.TestCase):
    """Claims that must not get lost in an edit."""

    def text(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_limits_are_stated(self):
        self.assertIn("not through a real reboot yet", self.text("README.en.md"))
        self.assertIn("chưa qua một lần khởi động lại thật", self.text("README.md"))
        self.assertIn("not been through a real reboot yet", self.text("docs/observed-results.md"))

    def test_not_affiliated(self):
        self.assertIn("not affiliated", self.text("README.en.md"))
        self.assertIn("không liên kết", self.text("README.md"))

    def test_the_wrong_first_explanation_stays_on_record(self):
        self.assertIn("It was wrong", self.text("docs/missing-agents-root-cause.md"))
        self.assertIn("10 of 12", self.text("docs/observed-results.md"))
        self.assertIn("4 of 13", self.text("docs/observed-results.md"))

    def test_tab_repair_warns_against_ending_the_terminal(self):
        for name in ("docs/troubleshooting.md", "docs/core-environment.md", "docs/missing-agents-root-cause.md"):
            self.assertIn("hc kill", self.text(name), name)

    def test_documented_defaults_match_the_script(self):
        source = self.text("bin/hc-claude-resume")
        values = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                values[node.targets[0].id] = node.value.value
        table = self.text("docs/resume-after-reboot.md")
        for name, shown in re.findall(r"\| `([A-Z_]+)` \| ([0-9.]+) \|", table):
            self.assertEqual(float(shown), float(values[name]), name)
        self.assertGreaterEqual(len(re.findall(r"\| `[A-Z_]+` \| [0-9.]+ \|", table)), 8)


def mermaid_blocks(path):
    """The mermaid blocks of a markdown file, each as a list of lines without the fences."""
    blocks, current = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if current is None:
            if stripped == "```mermaid":
                current = []
        elif stripped == "```":
            blocks.append(current)
            current = None
        else:
            current.append(line)
    if current is not None:
        raise AssertionError(f"unclosed mermaid block in {path.name}")
    return blocks


class DiagramTests(unittest.TestCase):
    """The diagrams are rendered by the site that shows the markdown, so only their shape is checked here."""

    KINDS = ("flowchart TD", "flowchart LR", "sequenceDiagram", "stateDiagram-v2")
    PAGES = [*READMES, *DOCS]

    def test_every_page_has_a_diagram(self):
        for path in self.PAGES:
            self.assertTrue(mermaid_blocks(path), path.name)

    def test_code_fences_are_balanced(self):
        for path in self.PAGES:
            fences = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip().startswith("```")]
            self.assertEqual(len(fences) % 2, 0, path.name)

    def test_diagrams_start_with_a_known_kind(self):
        for path in self.PAGES:
            for block in mermaid_blocks(path):
                self.assertIn(block[0].strip(), self.KINDS, (path.name, block[0]))
                self.assertGreater(len(block), 2, (path.name, block[0]))

    def test_diagram_text_avoids_what_breaks_rendering(self):
        for path in self.PAGES:
            for block in mermaid_blocks(path):
                for line in block:
                    where = (path.name, line)
                    self.assertNotIn("`", line, where)
                    self.assertNotIn(";", line, where)
                    self.assertNotIn("\t", line, where)
                    # The only tag allowed in a label is a line break; "<label>" would be read as HTML.
                    self.assertIsNone(re.search(r"<(?!br/>)[A-Za-z/]", line), where)

    def test_flowchart_labels_are_quoted(self):
        for path in self.PAGES:
            for block in mermaid_blocks(path):
                if not block[0].strip().startswith("flowchart"):
                    continue
                for line in block[1:]:
                    where = (path.name, line)
                    self.assertEqual(line.count('"') % 2, 0, where)
                    # A node or edge label opens with [" or {" or |" and never with a bare bracket.
                    self.assertIsNone(re.search(r"[\[{|](?![\"\s]|$)[^\"\]}|]", line), where)

    def test_readme_diagrams_match_in_both_languages(self):
        vi, en = (mermaid_blocks(path) for path in READMES)
        self.assertEqual(len(vi), len(en))
        for a, b in zip(vi, en):
            self.assertEqual(len(a), len(b))
            self.assertEqual(a[0].strip(), b[0].strip())


class ExampleTests(unittest.TestCase):
    HOOK_EXAMPLES = ("claude-settings-hooks.json", "codex-hooks.json")

    def test_every_json_example_parses(self):
        names = sorted(path.name for path in (ROOT / "examples").glob("*.json"))
        self.assertEqual(names, sorted([*self.HOOK_EXAMPLES, "claude-account-settings.json"]))
        for name in names:
            json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))

    def test_hook_examples_call_the_tool(self):
        for name in self.HOOK_EXAMPLES:
            data = json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
            commands = [h["command"] for groups in data["hooks"].values() for g in groups for h in g["hooks"]]
            self.assertTrue(commands, name)
            for command in commands:
                self.assertIn("hc-claude-resume", command)
                self.assertIn(" hook", command)

    def test_account_settings_example_holds_a_placeholder_only(self):
        data = json.loads((ROOT / "examples/claude-account-settings.json").read_text(encoding="utf-8"))
        self.assertEqual(list(data), ["env"])
        self.assertEqual(list(data["env"]), ["CLAUDE_CODE_OAUTH_TOKEN"])
        value = data["env"]["CLAUDE_CODE_OAUTH_TOKEN"]
        self.assertTrue(value.startswith("<") and value.endswith(">"), "the example must not look like a token")
        self.assertIn(" ", value)

    def test_claude_example_has_the_three_events(self):
        data = json.loads((ROOT / "examples/claude-settings-hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(set(data["hooks"]), {"SessionStart", "UserPromptSubmit", "SessionEnd"})

    def test_plist_parses(self):
        data = plistlib.loads((ROOT / "examples/herdr-core-start.plist").read_bytes())
        self.assertEqual(data["ProgramArguments"][1:], ["server", "status"])
        self.assertTrue(data["RunAtLoad"])

    def test_python_files_compile(self):
        for path in [ROOT / "bin/hc-claude-resume", *(ROOT / "tools").glob("*.py"), *(ROOT / "tests").glob("*.py")]:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_scripts_are_executable(self):
        for path in [ROOT / "bin/hc-claude-resume", *(ROOT / "tools").glob("*.sh"), *(ROOT / "tools").glob("*.py")]:
            self.assertTrue(path.stat().st_mode & 0o111, str(path.relative_to(ROOT)))

    def test_test_tools_refuse_the_real_core(self):
        env = (ROOT / "tools/probe-env.zsh").read_text(encoding="utf-8")
        self.assertIn('"$CORE" == default', env)
        reboot = (ROOT / "tools/simulate-reboot.sh").read_text(encoding="utf-8")
        self.assertIn("refusing", reboot)


if __name__ == "__main__":
    unittest.main()
