"""Logic tests of bin/hc-claude-resume that need no herdr-core, no agent and no network.

Everything that would call `hc`, `ps` or `sysctl` is replaced. What these tests cannot
show is the behavior in real terminals: that is what tools/ and docs/reproduce.md are for.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "hc-claude-resume"

SESSION_A = "sess-aaaa-1111"
SESSION_B = "sess-bbbb-2222"


def load():
    sys.dont_write_bytecode = True
    loader = SourceFileLoader("hc_claude_resume", str(SCRIPT))
    spec = spec_from_loader(loader.name, loader)
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


class Base(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.m.STATE_ROOT = self.tmp.name
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in ("HC_TERMINAL_SOCKET", "HC_TERMINAL_ID", "CLAUDE_ACCOUNT_LABEL",
                     "GROK_SESSION_ID", "CODEX_THREAD_ID"):
            os.environ.pop(name, None)

    def patch(self, name, value):
        patcher = mock.patch.object(self.m, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def entry(self, terminal, session=SESSION_A, agent="claude", **extra):
        data = {"terminal": terminal, "agent": agent, "session_id": session, "cwd": "",
                "account": "", "flags": [], "agent_pid": 0, "program_pid": 0,
                "recorded_at": int(time.time()), "source": "test"}
        data.update(extra)
        self.m.write_json(self.m.entry_path(terminal), data)
        return data

    def has_record(self, terminal):
        return os.path.exists(self.m.entry_path(terminal))


class IdlePromptTests(Base):
    def test_empty_input_box_is_idle(self):
        screen = "some answer\n\n────\n❯ \n────\n  status line\n"
        self.assertTrue(self.m.claude_idle_prompt(screen))

    def test_running_turn_is_not_idle(self):
        screen = "Working... (12s · esc to interrupt)\n❯\n"
        self.assertFalse(self.m.claude_idle_prompt(screen))

    def test_draft_in_the_box_is_not_idle(self):
        self.assertFalse(self.m.claude_idle_prompt("──\n❯ half a sentence\n──\n"))

    def test_dialog_or_plain_shell_is_not_idle(self):
        self.assertFalse(self.m.claude_idle_prompt("Do you trust the files in this folder?\n 1. Yes\n 2. No\n"))
        self.assertFalse(self.m.claude_idle_prompt("user@host ~ % \n"))
        self.assertFalse(self.m.claude_idle_prompt(""))

    def test_prompt_far_up_in_the_scrollback_does_not_count(self):
        screen = "❯\n" + "line\n" * 20
        self.assertFalse(self.m.claude_idle_prompt(screen))


class HeadlessTests(Base):
    def test_codex(self):
        self.assertTrue(self.m.is_headless("codex", ["codex", "exec", "do it"]))
        self.assertTrue(self.m.is_headless("codex", ["codex", "review"]))
        self.assertFalse(self.m.is_headless("codex", ["codex"]))
        self.assertFalse(self.m.is_headless("codex", ["codex", "--no-daemon"]))
        self.assertFalse(self.m.is_headless("codex", ["codex", "resume", SESSION_A]))

    def test_grok(self):
        self.assertTrue(self.m.is_headless("grok", ["grok", "-p", "hello"]))
        self.assertFalse(self.m.is_headless("grok", ["grok", "--resume", SESSION_A]))

    def test_claude_is_decided_elsewhere(self):
        self.assertFalse(self.m.is_headless("claude", ["claude", "-p", "hello"]))


class ResumeCommandTests(Base):
    def setUp(self):
        super().setUp()
        self.installed = {"claude", "claude-work", "codex", "grok"}
        self.patch("shutil", mock.Mock(which=lambda name: f"/bin/{name}" if name in self.installed else None))

    def test_account_launcher_is_used(self):
        cmd = self.m.resume_command({"agent": "claude", "session_id": SESSION_A, "account": "work",
                                     "flags": ["--dangerously-skip-permissions"]})
        self.assertEqual(cmd, f"claude-work --resume {SESSION_A}")

    def test_missing_launcher_never_falls_back(self):
        self.installed.discard("claude-work")
        self.assertIsNone(self.m.resume_command({"agent": "claude", "session_id": SESSION_A, "account": "work"}))

    def test_default_account_keeps_its_flag(self):
        cmd = self.m.resume_command({"agent": "claude", "session_id": SESSION_A, "account": "",
                                     "flags": ["--dangerously-skip-permissions", "--model", "x"]})
        self.assertEqual(cmd, f"claude --dangerously-skip-permissions --resume {SESSION_A}")

    def test_record_without_agent_field_is_claude(self):
        self.assertEqual(self.m.resume_command({"session_id": SESSION_A}), f"claude --resume {SESSION_A}")

    def test_codex_and_grok(self):
        self.assertEqual(
            self.m.resume_command({"agent": "codex", "session_id": SESSION_A, "flags": ["--no-daemon", "--bogus"]}),
            f"codex resume --no-daemon {SESSION_A}")
        self.assertEqual(
            self.m.resume_command({"agent": "grok", "session_id": SESSION_A, "flags": ["--always-approve"]}),
            f"grok --always-approve --resume {SESSION_A}")

    def test_agent_not_installed(self):
        self.installed.discard("grok")
        self.assertIsNone(self.m.resume_command({"agent": "grok", "session_id": SESSION_A}))
        self.assertIsNone(self.m.resume_command({"agent": "other", "session_id": SESSION_A}))

    def test_folder_is_quoted(self):
        folder = os.path.join(self.tmp.name, "my project")
        os.mkdir(folder)
        cmd = self.m.resume_command({"agent": "claude", "session_id": SESSION_A, "cwd": folder})
        self.assertEqual(cmd, f"cd -- '{folder}' && claude --resume {SESSION_A}")

    def test_missing_folder_means_no_command(self):
        # Never "claude --resume" without the cd: that starts the session in the
        # shell's folder (seen with an external drive that was mounted after login).
        cmd = self.m.resume_command({"agent": "claude", "session_id": SESSION_A,
                                     "cwd": os.path.join(self.tmp.name, "gone")})
        self.assertIsNone(cmd)

    def test_record_without_folder_has_no_cd(self):
        cmd = self.m.resume_command({"agent": "claude", "session_id": SESSION_A, "cwd": ""})
        self.assertEqual(cmd, f"claude --resume {SESSION_A}")


class StartQueueTests(Base):
    def test_too_soon_after_the_previous_start(self):
        self.patch("hc_terminal", lambda t: {"pid": 1, "status": {"state": "idle"}})
        self.assertFalse(self.m.previous_start_settled({"terminal": "t1", "at": 100.0}, 100.5))

    def test_previous_agent_reported(self):
        self.patch("hc_terminal", lambda t: {"pid": 1, "status": {"state": "idle"}})
        self.assertTrue(self.m.previous_start_settled({"terminal": "t1", "at": 100.0}, 105.0))

    def test_previous_agent_still_silent(self):
        self.patch("hc_terminal", lambda t: {"pid": 1, "status": None})
        self.assertFalse(self.m.previous_start_settled({"terminal": "t1", "at": 100.0}, 105.0))

    def test_silent_agent_does_not_block_forever(self):
        self.patch("hc_terminal", lambda t: {"pid": 1, "status": None})
        late = 100.0 + self.m.START_SETTLE_MAX_S
        self.assertTrue(self.m.previous_start_settled({"terminal": "t1", "at": 100.0}, late))

    def test_previous_terminal_is_gone(self):
        self.patch("hc_terminal", lambda t: None)
        self.assertTrue(self.m.previous_start_settled({"terminal": "t1", "at": 100.0}, 105.0))

    def test_first_start_does_not_wait_and_leaves_its_mark(self):
        waited = self.m.wait_for_start_slot("t1", "claude")
        self.assertLess(waited, 1.0)
        slot = json.loads(Path(self.m.state_dir(), "start-slot").read_text())
        self.assertEqual((slot["terminal"], slot["agent"]), ("t1", "claude"))

    def test_second_start_waits_for_the_first(self):
        self.patch("START_GAP_S", 0.6)
        self.patch("hc_terminal", lambda t: {"pid": 1, "status": {"state": "idle"}})
        self.m.wait_for_start_slot("t1", "claude")
        waited = self.m.wait_for_start_slot("t2", "codex")
        self.assertGreaterEqual(waited, 0.4)
        self.assertLess(waited, 3.0)


class QuietMachineTests(Base):
    def test_contention_is_a_ratio(self):
        self.assertGreater(self.m.cpu_contention(0.01), 0.5)

    def test_recent_start_is_not_quiet(self):
        self.patch("cpu_contention", lambda: 1.0)
        self.m.wait_for_start_slot("t1", "claude")
        self.assertFalse(self.m.machine_quiet())

    def test_old_start_and_free_cpu_is_quiet(self):
        self.patch("cpu_contention", lambda: 1.0)
        self.m.write_json(os.path.join(self.m.state_dir(), "start-slot"),
                          {"terminal": "t1", "at": time.time() - self.m.RESTART_QUIET_S - 1})
        self.assertTrue(self.m.machine_quiet())

    def test_contended_cpu_is_not_quiet(self):
        self.patch("cpu_contention", lambda: 6.0)
        self.assertFalse(self.m.machine_quiet())


class RetryCounterTests(Base):
    def write(self, count, at):
        os.makedirs(self.m.state_dir(), exist_ok=True)
        Path(self.m.retries_path("t1")).write_text(f"{count} {at}")

    def test_no_file(self):
        self.assertEqual(self.m.retries_done("t1"), 0)

    def test_recent_count(self):
        self.write(2, time.time())
        self.assertEqual(self.m.retries_done("t1"), 2)

    def test_forgotten_after_an_hour(self):
        self.write(2, time.time() - self.m.STATUS_RETRY_MEMORY_S - 1)
        self.assertEqual(self.m.retries_done("t1"), 0)

    def test_broken_file(self):
        os.makedirs(self.m.state_dir(), exist_ok=True)
        Path(self.m.retries_path("t1")).write_text("")
        self.assertEqual(self.m.retries_done("t1"), 0)


class WatcherTests(Base):
    """cmd_status_check with a fake terminal and no real waiting."""

    def setUp(self):
        super().setUp()
        self.term = {"pid": 4242, "status": None, "foreground": {"argv": ["claude"]}}
        self.screen = "──\n❯\n──\n"
        self.clock = [1000.0]
        self.killed = []
        self.patch("hc_terminal", lambda t: self.term)
        self.patch("screen_text", lambda t: self.screen)
        self.patch("machine_quiet", lambda: True)
        fake_time = mock.Mock(wraps=time)
        fake_time.time = lambda: self.clock[0]
        fake_time.sleep = lambda s: self.clock.__setitem__(0, self.clock[0] + s)
        self.patch("time", fake_time)
        fake_os = mock.Mock(wraps=os)
        fake_os.kill = lambda pid, sig: self.killed.append((pid, sig))
        fake_os.path = os.path
        self.patch("os", fake_os)

    def log(self):
        try:
            return Path(self.m.state_dir(), "events.log").read_text()
        except FileNotFoundError:
            return ""

    def test_reported_status_ends_the_watch(self):
        self.term["status"] = {"state": "idle"}
        self.assertEqual(self.m.cmd_status_check(["t1", "4242"]), 0)
        self.assertEqual(self.killed, [])
        self.assertIn("reports idle", self.log())

    def test_missed_probe_restarts_the_terminal_program(self):
        self.m.cmd_status_check(["t1", "4242"])
        self.assertEqual(self.killed, [(4242, 9)])
        self.assertIn("restart try 1 of 2", self.log())
        self.assertEqual(self.m.retries_done("t1"), 1)

    def test_second_miss_counts_up(self):
        self.m.cmd_status_check(["t1", "4242"])
        self.m.cmd_status_check(["t1", "4242"])
        self.assertEqual(len(self.killed), 2)
        self.assertEqual(self.m.retries_done("t1"), 2)

    def test_gives_up_after_the_limit(self):
        for _ in range(4):
            self.m.cmd_status_check(["t1", "4242"])
        self.assertEqual(len(self.killed), self.m.STATUS_RETRY_MAX)
        self.assertIn("giving up", self.log())

    def test_off_switch(self):
        os.makedirs(self.m.state_dir(), exist_ok=True)
        Path(self.m.state_dir(), "no-status-retry").touch()
        self.m.cmd_status_check(["t1", "4242"])
        self.assertEqual(self.killed, [])
        self.assertIn("restart is turned off", self.log())

    def test_busy_agent_is_left_alone(self):
        self.screen = "Working... (esc to interrupt)\n❯\n"
        self.m.cmd_status_check(["t1", "4242"])
        self.assertEqual(self.killed, [])
        self.assertIn("left alone", self.log())

    def test_draft_is_left_alone(self):
        self.screen = "❯ half a sentence\n"
        self.m.cmd_status_check(["t1", "4242"])
        self.assertEqual(self.killed, [])

    def test_codex_is_never_restarted(self):
        self.term["foreground"] = {"argv": ["codex"]}
        self.m.cmd_status_check(["t1", "4242"])
        self.assertEqual(self.killed, [])

    def test_replaced_terminal_program_ends_the_watch(self):
        self.term["pid"] = 5000
        self.m.cmd_status_check(["t1", "4242"])
        self.assertEqual(self.killed, [])
        self.assertEqual(self.log(), "")

    def test_busy_machine_delays_the_restart_but_not_forever(self):
        self.patch("machine_quiet", lambda: False)
        self.m.cmd_status_check(["t1", "4242"])
        self.assertEqual(self.killed, [(4242, 9)])
        self.assertGreaterEqual(self.clock[0] - 1000.0, self.m.RESTART_WAIT_MAX_S)


class RecordTests(Base):
    def setUp(self):
        super().setUp()
        self.running = set()
        self.patch("hc_terminal", lambda t: {"pid": 500, "foreground": {"argv": ["zsh"]}})
        self.patch("is_terminal_top_agent", lambda agent_pid, program_pid: True)
        self.patch("proc_argv", lambda pid: ["claude"])
        self.patch("claude_session_file", lambda pid: {})
        self.patch("boot_time", lambda: 0)
        self.patch("pid_runs", lambda pid, agent: pid in self.running)

    def test_record_content(self):
        self.patch("proc_argv", lambda pid: ["claude", "--dangerously-skip-permissions", "--model", "x"])
        self.assertTrue(self.m.record("t1", "claude", SESSION_A, 77, "/work", "work", "startup"))
        data = self.m.read_json(self.m.entry_path("t1"))
        self.assertEqual(data["account"], "work")
        self.assertEqual(data["flags"], ["--dangerously-skip-permissions"])
        self.assertEqual((data["agent_pid"], data["program_pid"]), (77, 500))
        self.assertNotIn("token", json.dumps(data).lower())

    def test_bad_label_is_dropped(self):
        self.m.record("t1", "claude", SESSION_A, 77, "/work", "work; rm -rf x", "startup")
        self.assertEqual(self.m.read_json(self.m.entry_path("t1"))["account"], "")

    def test_non_interactive_claude_is_not_recorded(self):
        self.patch("claude_session_file", lambda pid: {"kind": "print"})
        self.assertFalse(self.m.record("t1", "claude", SESSION_A, 77, "/work", "", "startup"))
        self.assertFalse(self.has_record("t1"))

    def test_nested_agent_is_not_recorded(self):
        self.patch("is_terminal_top_agent", lambda agent_pid, program_pid: False)
        self.assertFalse(self.m.record("t1", "claude", SESSION_A, 77, "/work", "", "startup"))

    def test_headless_codex_is_not_recorded(self):
        self.patch("proc_argv", lambda pid: ["codex", "exec", "task"])
        self.assertFalse(self.m.record("t1", "codex", SESSION_A, 77, "/work", "", "startup"))

    def test_session_moving_to_another_tab_drops_the_dead_record(self):
        self.entry("t1", agent_pid=11)
        self.assertTrue(self.m.record("t2", "claude", SESSION_A, 22, "/work", "", "resume"))
        self.assertFalse(self.has_record("t1"))
        self.assertTrue(self.has_record("t2"))

    def test_live_record_of_the_same_session_is_kept(self):
        self.entry("t1", agent_pid=11)
        self.running.add(11)
        self.m.record("t2", "claude", SESSION_A, 22, "/work", "", "resume")
        self.assertTrue(self.has_record("t1"))

    def test_other_sessions_are_untouched(self):
        self.entry("t1", session=SESSION_B, agent_pid=11)
        self.m.record("t2", "claude", SESSION_A, 22, "/work", "", "resume")
        self.assertTrue(self.has_record("t1"))


class HookTests(Base):
    def setUp(self):
        super().setUp()
        os.environ["HC_TERMINAL_ID"] = "t1"

    def hook(self, payload, want=None):
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            return self.m.cmd_hook(want)

    def test_kill_or_shutdown_keeps_the_record(self):
        self.entry("t1")
        self.hook({"hook_event_name": "SessionEnd", "session_id": SESSION_A, "reason": "other"})
        self.assertTrue(self.has_record("t1"))

    def test_deliberate_exit_removes_the_record(self):
        self.entry("t1")
        self.hook({"hook_event_name": "SessionEnd", "session_id": SESSION_A, "reason": "prompt_input_exit"})
        self.assertFalse(self.has_record("t1"))

    def test_end_of_another_session_keeps_the_record(self):
        self.entry("t1")
        self.hook({"hook_event_name": "SessionEnd", "session_id": SESSION_B, "reason": "prompt_input_exit"})
        self.assertTrue(self.has_record("t1"))

    def test_codex_record_is_not_removed_by_a_claude_style_end(self):
        self.entry("t1", agent="codex")
        self.hook({"hook_event_name": "SessionEnd", "session_id": SESSION_A, "reason": "logout"})
        self.assertTrue(self.has_record("t1"))

    def test_subagent_events_are_ignored(self):
        self.patch("nearest_agent_ancestor", lambda want=None: self.fail("must not look for an agent"))
        self.hook({"hook_event_name": "SessionStart", "session_id": SESSION_A, "agent_id": "sub-1"})
        self.assertFalse(self.has_record("t1"))

    def test_outside_a_terminal_nothing_happens(self):
        del os.environ["HC_TERMINAL_ID"]
        self.patch("nearest_agent_ancestor", lambda want=None: self.fail("must not look for an agent"))
        self.assertEqual(self.hook({"hook_event_name": "SessionStart", "session_id": SESSION_A}), 0)

    def test_garbage_on_stdin_is_harmless(self):
        with mock.patch.object(sys, "stdin", io.StringIO("not json")):
            self.assertEqual(self.m.cmd_hook(None), 0)


class CheckTests(Base):
    def setUp(self):
        super().setUp()
        os.environ["HC_TERMINAL_ID"] = "t1"
        self.terms = {"t1": {"pid": 900, "foreground": {"argv": ["zsh"]}},
                      "t2": {"pid": 901, "foreground": {"argv": ["zsh"]}}}
        self.running = set()
        self.watched = []
        self.patch("hc_terminal", lambda t: self.terms.get(t))
        self.patch("boot_time", lambda: 0)
        self.patch("pid_runs", lambda pid, agent: pid in self.running)
        self.patch("wait_for_start_slot", lambda terminal, agent: 0.0)
        self.patch("start_status_check", lambda terminal, pid: self.watched.append((terminal, pid)))
        self.patch("start_reap", lambda terminal, entry: None)
        self.patch("shutil", mock.Mock(which=lambda name: f"/bin/{name}"))

    def check(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = self.m.cmd_check()
        return rc, out.getvalue().strip()

    def test_lost_terminal_is_resumed_once(self):
        self.entry("t1", program_pid=100)
        self.assertEqual(self.check(), (0, f"claude --resume {SESSION_A}"))
        self.assertEqual(self.watched, [("t1", 900)])
        self.assertEqual(self.check(), (1, ""))

    def test_same_program_means_no_loss(self):
        self.entry("t1", program_pid=900)
        self.assertEqual(self.check(), (1, ""))
        self.assertTrue(self.has_record("t1"))

    def test_record_from_before_the_boot_is_a_loss(self):
        self.entry("t1", program_pid=900, recorded_at=1000)
        self.patch("boot_time", lambda: 2000)
        self.assertEqual(self.check()[0], 0)

    def test_agent_already_in_the_foreground(self):
        self.entry("t1", program_pid=100)
        self.terms["t1"]["foreground"] = {"argv": ["claude"]}
        self.assertEqual(self.check(), (1, ""))

    def test_no_record(self):
        self.assertEqual(self.check(), (1, ""))

    def test_session_running_elsewhere_is_not_opened_twice(self):
        self.entry("t1", program_pid=100)
        self.entry("t2", program_pid=901, agent_pid=55)
        self.running.add(55)
        self.assertEqual(self.check(), (1, ""))
        self.assertFalse(self.has_record("t1"))

    def test_later_record_of_a_live_terminal_wins(self):
        now = int(time.time())
        self.entry("t1", program_pid=100, recorded_at=now - 100)
        self.entry("t2", program_pid=100, recorded_at=now)
        self.assertEqual(self.check(), (1, ""))
        os.environ["HC_TERMINAL_ID"] = "t2"
        self.assertEqual(self.check()[0], 0)

    def test_later_record_of_a_vanished_terminal_does_not_block(self):
        now = int(time.time())
        self.entry("t1", program_pid=100, recorded_at=now - 100)
        self.entry("t2", program_pid=100, recorded_at=now)
        del self.terms["t2"]
        self.assertEqual(self.check()[0], 0)

    def log(self):
        try:
            return Path(self.m.state_dir(), "events.log").read_text()
        except FileNotFoundError:
            return ""

    def test_missing_folder_is_reported_and_nothing_is_used_up(self):
        folder = os.path.join(self.tmp.name, "drive", "project")
        self.entry("t1", program_pid=100, cwd=folder)
        self.assertEqual(self.check(), (3, folder))
        self.assertEqual(self.watched, [])
        self.assertNotIn("consumed_by", self.m.read_json(self.m.entry_path("t1")))
        self.assertIn(f"folder missing: {folder}", self.log())
        # The drive is mounted: the same shell asks again and gets the full command.
        os.makedirs(folder)
        self.assertEqual(self.check(), (0, f"cd -- {folder} && claude --resume {SESSION_A}"))
        self.assertEqual(self.watched, [("t1", 900)])

    def test_missing_launcher_wins_over_missing_folder(self):
        self.entry("t1", program_pid=100, account="work",
                   cwd=os.path.join(self.tmp.name, "gone"))
        self.patch("shutil", mock.Mock(which=lambda name: None))
        self.assertEqual(self.check(), (1, ""))


class WaitFolderTests(Base):
    """cmd_wait_folder with a fake clock."""

    def setUp(self):
        super().setUp()
        os.environ["HC_TERMINAL_ID"] = "t1"
        self.folder = os.path.join(self.tmp.name, "drive", "project")
        self.clock = [1000.0]
        self.on_sleep = lambda: None
        fake_time = mock.Mock(wraps=time)
        fake_time.time = lambda: self.clock[0]

        def sleep(seconds):
            self.clock[0] += seconds
            self.on_sleep()

        fake_time.sleep = sleep
        self.patch("time", fake_time)

    def log(self):
        try:
            return Path(self.m.state_dir(), "events.log").read_text()
        except FileNotFoundError:
            return ""

    def test_folder_already_there(self):
        os.makedirs(self.folder)
        self.entry("t1", cwd=self.folder)
        self.assertEqual(self.m.cmd_wait_folder(), 0)
        self.assertEqual(self.log(), "")

    def test_returns_when_the_folder_appears(self):
        self.entry("t1", cwd=self.folder)

        def mount():
            if self.clock[0] >= 1010:
                os.makedirs(self.folder, exist_ok=True)

        self.on_sleep = mount
        self.assertEqual(self.m.cmd_wait_folder(), 0)
        self.assertIn(f"t1 folder is back after 10s: {self.folder}", self.log())

    def test_gives_up_after_the_limit(self):
        self.entry("t1", cwd=self.folder)
        self.assertEqual(self.m.cmd_wait_folder(), 1)
        self.assertGreaterEqual(self.clock[0] - 1000, self.m.FOLDER_WAIT_MAX_S)
        self.assertIn("not resumed: folder still missing", self.log())

    def test_record_removed_meanwhile(self):
        self.entry("t1", cwd=self.folder)
        self.on_sleep = lambda: self.m.remove(self.m.entry_path("t1"))
        self.assertEqual(self.m.cmd_wait_folder(), 0)

    def test_record_pointed_at_another_folder_meanwhile(self):
        self.entry("t1", cwd=self.folder)
        other = os.path.join(self.tmp.name, "moved")
        os.makedirs(other)
        self.on_sleep = lambda: self.entry("t1", cwd=other)
        self.assertEqual(self.m.cmd_wait_folder(), 0)

    def test_no_terminal(self):
        del os.environ["HC_TERMINAL_ID"]
        self.assertEqual(self.m.cmd_wait_folder(), 0)


class SmallThingsTests(Base):
    def test_shutdown_reason_is_not_deliberate(self):
        self.assertNotIn("other", self.m.DELIBERATE_END)

    def test_no_value_flags_are_carried_over(self):
        for flags in self.m.RESUME_FLAGS.values():
            for flag in flags:
                self.assertTrue(flag.startswith("--") and "=" not in flag, flag)

    def test_terminal_name_cannot_leave_the_state_folder(self):
        path = self.m.entry_path("../../etc/x")
        self.assertEqual(os.path.dirname(path), self.m.state_dir())

    def test_core_name_comes_from_the_socket_path(self):
        os.environ["HC_TERMINAL_SOCKET"] = "/run/herdr-core/probe/terminal.sock"
        self.assertEqual(os.path.basename(self.m.state_dir()), "probe")

    def test_usage_on_unknown_command(self):
        with mock.patch.object(sys, "argv", ["hc-claude-resume"]), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.m.main(), 2)


if __name__ == "__main__":
    unittest.main()
