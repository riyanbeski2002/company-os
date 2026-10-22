"""Routines — a plan spec on a cron schedule.

What must hold: the two routine events validate and never carry a top-level
task; a redefinition replaces the whole definition (last one wins); the cron
matcher agrees with cron on the syntax it claims; `due` names at most one
unfired slot per enabled routine; `fire` creates PLANNED tasks only through
the same plan checks `company plan` applies (mandatory gates included) and
fires a slot once, even when two fires race; and only `company routine`,
never from inside a worker, writes routine events.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

from eventlog import DuplicateFireError, EventLog, make_event, validate  # noqa: E402
import routines  # noqa: E402
import taskstate  # noqa: E402

CLI = HERE.parent / "tools" / "company" / "cli.py"

SPEC = {"project": "p", "request": "weekly dependency audit",
        "tasks": [{"id": "T-1", "title": "audit dependencies", "tier": 1,
                   "owned_globs": ["docs/**"]}]}


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def routine_event(name, data, **kw):
    return make_event(event=name, actor=kw.pop("actor", "riyan"),
                      project=kw.pop("project", "_org"), data=data, **kw)


class RoutineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, actor_env=None):
        env = dict(os.environ)
        env.pop("COMPANY_ACTOR", None)
        env.pop("COMPANY_PROJECT", None)
        if actor_env:
            env["COMPANY_ACTOR"] = actor_env
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                              capture_output=True, text=True, env=env)

    def define(self, *args, spec=SPEC):
        r = self.run_cli("routine", "define", "--spec", json.dumps(spec), *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def views(self):
        return routines.fold(self.log.read())


# --- validation -------------------------------------------------------------

class TestValidation(unittest.TestCase):
    GOOD = {"id": "R-001", "cron": "0 3 * * *", "spec": SPEC, "enabled": True}

    def bad(self, data, **kw):
        with self.assertRaises(ValueError):
            validate(routine_event("ROUTINE_DEFINED", data, **kw))

    def test_defined_shape(self):
        validate(routine_event("ROUTINE_DEFINED", self.GOOD))
        self.bad({**self.GOOD, "id": "G-001"})
        self.bad({**self.GOOD, "cron": "0 3 * *"})
        self.bad({**self.GOOD, "spec": {"project": "p", "tasks": []}})
        self.bad({**self.GOOD, "spec": {"tasks": SPEC["tasks"]}})
        self.bad({**self.GOOD, "enabled": "yes"})

    def test_not_project_scoped_and_no_top_level_task(self):
        self.bad(self.GOOD, project="p")
        self.bad(self.GOOD, task="T-1")
        with self.assertRaises(ValueError):
            validate(routine_event("ROUTINE_FIRED", {"routine": "R-001", "slot": "s",
                                                     "tasks": ["T-1"]}, task="T-1"))

    def test_fired_shape(self):
        validate(routine_event("ROUTINE_FIRED", {"routine": "R-001", "slot": "s", "tasks": ["T-1"]}))
        for data in ({"slot": "s", "tasks": ["T-1"]}, {"routine": "R-001", "tasks": ["T-1"]},
                     {"routine": "R-001", "slot": "s", "tasks": []}):
            with self.assertRaises(ValueError):
                validate(routine_event("ROUTINE_FIRED", data))


# --- cron -------------------------------------------------------------------

class TestCron(unittest.TestCase):
    def m(self, expr, t):
        return routines.matches(routines.parse_cron(expr), t)

    def test_star_exact_and_lists(self):
        t = utc(2026, 10, 22, 3, 15)  # a Thursday
        self.assertTrue(self.m("* * * * *", t))
        self.assertTrue(self.m("15 3 * * *", t))
        self.assertFalse(self.m("16 3 * * *", t))
        self.assertTrue(self.m("0,15,30 3 * * *", t))
        self.assertTrue(self.m("15 3 22 10 *", t))
        self.assertFalse(self.m("15 3 22 11 *", t))

    def test_ranges_and_steps(self):
        self.assertTrue(self.m("*/15 * * * *", utc(2026, 10, 22, 3, 45)))
        self.assertFalse(self.m("*/15 * * * *", utc(2026, 10, 22, 3, 46)))
        self.assertTrue(self.m("5/20 * * * *", utc(2026, 10, 22, 3, 45)))
        self.assertTrue(self.m("0 9-17/4 * * *", utc(2026, 10, 22, 13, 0)))
        self.assertFalse(self.m("0 9-17/4 * * *", utc(2026, 10, 22, 15, 0)))

    def test_day_of_week(self):
        self.assertTrue(self.m("0 3 * * 4", utc(2026, 10, 22, 3, 0)))      # Thursday
        self.assertTrue(self.m("0 3 * * 1-5", utc(2026, 10, 22, 3, 0)))
        self.assertFalse(self.m("0 3 * * 1-5", utc(2026, 10, 25, 3, 0)))   # Sunday
        self.assertTrue(self.m("0 3 * * 0", utc(2026, 10, 25, 3, 0)))
        self.assertTrue(self.m("0 3 * * 7", utc(2026, 10, 25, 3, 0)))

    def test_dom_and_dow_both_restricted_match_either(self):
        # Vixie cron: the 1st of the month, or any Sunday.
        self.assertTrue(self.m("0 0 1 * 0", utc(2026, 10, 25, 0, 0)))
        self.assertTrue(self.m("0 0 1 * 0", utc(2026, 10, 1, 0, 0)))
        self.assertFalse(self.m("0 0 1 * 0", utc(2026, 10, 22, 0, 0)))

    def test_rejects_what_it_does_not_support(self):
        for expr in ("* * * *", "60 * * * *", "* 24 * * *", "* * 0 * *", "MON * * * *",
                     "*/0 * * * *", "5-1 * * * *", "@daily"):
            with self.assertRaises(ValueError, msg=expr):
                routines.parse_cron(expr)

    def test_latest_slot(self):
        cron = routines.parse_cron("0 3 * * 1-5")
        after = utc(2026, 10, 1)
        self.assertEqual(routines.latest_slot(cron, after, utc(2026, 10, 22, 3, 0, 30)),
                         utc(2026, 10, 22, 3, 0))
        # Sunday: Friday's slot is the latest.
        self.assertEqual(routines.latest_slot(cron, after, utc(2026, 10, 25, 12)),
                         utc(2026, 10, 23, 3, 0))
        # Nothing between the anchor and now.
        self.assertIsNone(routines.latest_slot(cron, utc(2026, 10, 22, 3, 0), utc(2026, 10, 22, 4)))


# --- define, fold, due ------------------------------------------------------

class TestDefineAndFold(RoutineCase):
    def test_redefine_is_last_one_wins(self):
        self.assertEqual(self.define("--cron", "0 3 * * *")["routine"], "R-001")
        r = self.run_cli("routine", "define", "--id", "R-001", "--cron", "0 4 * * *")
        self.assertEqual(r.returncode, 1)
        self.assertIn("requires a reason", r.stderr)
        r = self.run_cli("routine", "define", "--id", "R-001", "--cron", "0 4 * * *",
                         "--reason", "later")
        self.assertEqual(r.returncode, 0, r.stderr)
        v = self.views()["R-001"]
        self.assertEqual(v["cron"], "0 4 * * *")
        self.assertEqual(v["spec"], SPEC)  # carried over from the first definition
        self.assertTrue(v["enabled"])
        self.assertEqual([x["reason"] for x in v["revisions"]], ["later"])

    def test_disable_retires_it(self):
        self.define("--cron", "* * * * *")
        self.run_cli("routine", "define", "--id", "R-001", "--disable", "--reason", "retired")
        self.assertFalse(self.views()["R-001"]["enabled"])
        listed = json.loads(self.run_cli("routine", "list").stdout)["routines"]
        self.assertEqual([(x["id"], x["enabled"]) for x in listed], [("R-001", False)])
        due = json.loads(self.run_cli("routine", "due", "--now", "2099-01-01T00:00").stdout)
        self.assertEqual(due["due"], [])

    def test_bad_cron_is_refused_at_define(self):
        r = self.run_cli("routine", "define", "--cron", "61 * * * *", "--spec", json.dumps(SPEC))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.log.read(), [])

    def test_spec_from_a_file(self):
        f = Path(self.tmp.name) / "spec.json"
        f.write_text(json.dumps(SPEC))
        r = self.run_cli("routine", "define", "--cron", "0 3 * * *", "--spec", str(f))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.views()["R-001"]["spec"], SPEC)

    def test_due_for_fixed_times(self):
        self.define("--cron", "0 3 * * 1-5")   # R-001, weekdays 03:00
        self.define("--cron", "*/15 * * * *")  # R-002
        anchor = routines.parse_time(self.views()["R-001"]["revised_at"])
        self.assertLess(anchor, utc(2099, 1, 1))

        def due(now):
            r = self.run_cli("routine", "due", "--now", now)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)["due"]

        # 2099-01-02 is a Friday, 2099-01-04 a Sunday.
        self.assertEqual(due("2099-01-02T03:07"),
                         [{"routine": "R-001", "slot": "2099-01-02T03:00Z"},
                          {"routine": "R-002", "slot": "2099-01-02T03:00Z"}])
        self.assertEqual(due("2099-01-04T10:20"),
                         [{"routine": "R-001", "slot": "2099-01-02T03:00Z"},
                          {"routine": "R-002", "slot": "2099-01-04T10:15Z"}])
        # A timezone-aware override is converted to UTC.
        self.assertEqual(due("2099-01-02T05:07+02:00")[0]["slot"], "2099-01-02T03:00Z")
        # Not due before anything matched since the definition.
        self.assertEqual(due(self.views()["R-001"]["revised_at"]), [])

    def test_fired_events_for_unknown_routines_are_ignored(self):
        self.log.append(routine_event("ROUTINE_FIRED", {"routine": "R-009", "slot": "s",
                                                        "tasks": ["T-1"]}))
        self.assertEqual(self.views(), {})
        self.assertEqual(taskstate.fold(self.log.read()), {})


# --- fire -------------------------------------------------------------------

class TestFire(RoutineCase):
    NOW = "2099-01-02T03:07"

    def fire(self, *args):
        r = self.run_cli("routine", "fire", *args, "--now", self.NOW)
        return r, json.loads(r.stdout) if r.stdout else None

    def test_fire_creates_planned_tasks_through_the_plan_checks(self):
        # "payment" fires the risk table's payments trigger: security must be
        # forced on even though the spec asked for no gates.
        spec = {"project": "p", "request": "reconcile payment ledger",
                "tasks": [{"id": "T-1", "title": "reconcile payment ledger", "tier": 1,
                           "owned_globs": ["src/ledger/**"], "gates": []},
                          {"id": "T-2", "title": "write the reconciliation report", "tier": 1,
                           "owned_globs": ["docs/**"], "depends_on": ["T-1"]}]}
        self.define("--cron", "0 3 * * *", spec=spec)
        r, out = self.fire("--due")
        self.assertEqual(r.returncode, 0, r.stderr)
        fired = out["fired"][0]
        self.assertEqual(fired["slot"], "2099-01-02T03:00Z")
        self.assertEqual(fired["tasks"], ["T-1-209901020300", "T-2-209901020300"])

        tasks = taskstate.fold(self.log.read())
        t1, t2 = tasks["T-1-209901020300"], tasks["T-2-209901020300"]
        self.assertEqual({t1["status"], t2["status"]}, {"PLANNED"})
        self.assertIn("security", t1["gates"])
        created = next(e for e in self.log.read() if e.get("task") == "T-1-209901020300")
        self.assertIn("payments", created["data"]["triggers_fired"])
        self.assertEqual(t2["depends_on"], ["T-1-209901020300"])
        self.assertEqual(t1["project"], "p")
        # Nothing launched, nothing assigned, and the PM's plan file untouched.
        names = [e["event"] for e in self.log.read()]
        self.assertNotIn("TASK_ASSIGNED", names)
        self.assertNotIn("WORKER_STARTED", names)
        self.assertFalse((self.root / "projects" / "p.json").exists())
        self.assertEqual(self.views()["R-001"]["fired"][0]["slot"], "2099-01-02T03:00Z")

    def test_fire_is_refused_by_the_plan_checks_without_burning_the_slot(self):
        self.log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                                   task="T-9", data={"title": "audit dependencies"}))
        self.define("--cron", "0 3 * * *")
        r, out = self.fire("--due")
        self.assertEqual(r.returncode, 3)
        self.assertIn("closely match", out["fired"][0]["refusal"])
        self.assertEqual(self.views()["R-001"]["fired"], [])
        self.assertEqual(set(taskstate.fold(self.log.read())), {"T-9"})

    def test_double_fire_on_one_slot_is_a_no_op(self):
        self.define("--cron", "0 3 * * *")
        self.assertEqual(self.fire("R-001")[0].returncode, 0)
        before = self.log.read()
        r, out = self.fire("R-001")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out["fired"][0]["skipped"], "already fired for this slot")
        r, out = self.fire("--due")
        self.assertEqual(out["fired"], [])
        self.assertEqual(self.log.read(), before)

    def test_the_lock_refuses_a_second_fired_event_for_one_slot(self):
        ev = routine_event("ROUTINE_FIRED", {"routine": "R-001", "slot": "s", "tasks": ["T-1"]})
        self.log.append(ev)
        with self.assertRaises(DuplicateFireError):
            self.log.append(ev)
        self.log.append(routine_event("ROUTINE_FIRED", {"routine": "R-001", "slot": "s2",
                                                        "tasks": ["T-1"]}))

    def test_concurrent_fires_create_one_set_of_tasks(self):
        self.define("--cron", "0 3 * * *")
        env = {k: v for k, v in os.environ.items() if k not in ("COMPANY_ACTOR", "COMPANY_PROJECT")}
        procs = [subprocess.Popen([sys.executable, str(CLI), "--root", str(self.root), "routine",
                                   "fire", "--due", "--now", self.NOW],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                 for _ in range(4)]
        for p in procs:
            p.communicate()
            self.assertEqual(p.returncode, 0)
        names = [e["event"] for e in self.log.read()]
        self.assertEqual(names.count("ROUTINE_FIRED"), 1)
        self.assertEqual(names.count("TASK_CREATED"), 1)

    def test_fire_needs_an_id_or_due(self):
        self.assertEqual(self.run_cli("routine", "fire").returncode, 1)
        self.assertEqual(self.run_cli("routine", "fire", "R-001", "--due").returncode, 1)
        self.assertEqual(self.run_cli("routine", "fire", "R-404").returncode, 1)


# --- guards -----------------------------------------------------------------

class TestGuards(RoutineCase):
    def test_raw_company_event_refuses_routine_events(self):
        payloads = {"ROUTINE_DEFINED": {"id": "R-001", "cron": "* * * * *", "spec": SPEC,
                                        "enabled": True},
                    "ROUTINE_FIRED": {"routine": "R-001", "slot": "s", "tasks": ["T-1"]}}
        for name, data in payloads.items():
            r = self.run_cli("event", name, "--project", "_org", "--data", json.dumps(data))
            self.assertEqual(r.returncode, 2, name)
            self.assertIn("company routine", r.stderr)
        self.assertEqual(self.log.read(), [])

    def test_mutations_refuse_inside_a_worker(self):
        self.define("--cron", "* * * * *")
        before = self.log.read()
        for argv in (["define", "--cron", "* * * * *", "--spec", json.dumps(SPEC)],
                     ["fire", "--due", "--now", "2099-01-01T00:00"],
                     ["fire", "R-001", "--now", "2099-01-01T00:00"]):
            r = self.run_cli("routine", *argv, actor_env="backend-engineer-01")
            self.assertEqual(r.returncode, 2, argv)
            self.assertIn("inside a launched worker", r.stderr)
        self.assertEqual(self.log.read(), before)

    def test_reads_are_allowed_inside_a_worker(self):
        self.define("--cron", "* * * * *")
        for argv in (["list"], ["due"]):
            self.assertEqual(self.run_cli("routine", *argv, actor_env="be-1").returncode, 0, argv)


if __name__ == "__main__":
    unittest.main()
