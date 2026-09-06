"""Fixtures for the otog test suite.

Two rules hold everywhere:

  1. Nothing writes into a real runs/ or orders/ tree. Tests build their own
     under tmp_path.
  2. Tests exercise the REAL scripts, symlinked into a throwaway tool dir, so a
     passing test is a statement about the code that actually runs.
"""

import os
import subprocess
from subprocess import PIPE
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

SCRIPTS = ("setup.sh", "run_once.sh", "run_experiment.sh",
           "lib.sh", "config_default.sh", "fix_helper.sh")


@pytest.fixture(scope="session")
def repo():
    return REPO


@pytest.fixture
def tool(tmp_path):
    """A throwaway tool dir wired to the real scripts, with its own data."""
    root = tmp_path / "otog"
    root.mkdir()

    for name in SCRIPTS:
        (root / name).symlink_to(REPO / name)
    (root / "container").mkdir()
    for name in ("engine.sh", "entrypoint.sh", "runtime.sh", "jfr.sh"):
        (root / "container" / name).symlink_to(REPO / "container" / name)
    (root / "scripts").mkdir()
    for f in (REPO / "scripts").iterdir():
        (root / "scripts" / f.name).symlink_to(f)

    (root / "data").mkdir()
    for name in ("idoft_flaky_tests.csv", "fix_registry.csv", "fix_strategies.csv"):
        (root / "data" / name).symlink_to(REPO / "data" / name)

    for d in ("orders", "runs", "workspaces", "dependency"):
        (root / d).mkdir()

    class Tool:
        path = root

        def versions(self, rows):
            """data/versions.csv from (module, version, slug, path, sha)."""
            out = ["module_id,slug,module,version,sha,compiled"]
            for module, version, slug, mpath, sha in rows:
                out.append(f"{module},{slug},{mpath},{version},{sha},1")
            (root / "data" / "versions.csv").write_text("\n".join(out) + "\n")

        def order(self, module, version, oid, tests):
            d = root / "orders" / str(module) / str(version)
            d.mkdir(parents=True, exist_ok=True)
            f = d / f"{oid}.txt"
            f.write_text("\n".join(tests) + "\n")
            return f

        def run(self, module, version, oid, rep, status="PASS", order_text=None):
            d = (root / "runs" / str(module) / str(version) /
                 f"order_{oid}" / f"run_{rep}")
            d.mkdir(parents=True, exist_ok=True)
            (d / "status").write_text(status + "\n")
            (d / "wall_time.txt").write_text("100.0 220.0\n")
            (d / "node.txt").write_text("testnode\n")
            (d / "surefire-reports").mkdir(exist_ok=True)
            if order_text is not None:
                (d / "order.txt").write_text(order_text)
            return d

        def sh(self, script, *args, env=None, dry=True):
            """Run one of the scripts and capture its output."""
            e = dict(os.environ)
            e.update({"OTOG_ENGINE": "docker",
                      "OTOG_WORKSPACE_ROOT": str(root / "workspaces")})
            if dry:
                e["OTOG_ENGINE_DRYRUN"] = "1"
            if env:
                e.update(env)
            return subprocess.run(
                ["bash", str(root / script), *[str(a) for a in args]],
                cwd=str(root), env=e, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        def call(self, snippet, env=None):
            """Call a lib.sh function and get its stdout."""
            e = dict(os.environ)
            e.update({"OTOG_ENGINE": "docker"})
            if env:
                e.update(env)
            return subprocess.run(
                ["bash", "-c", f'source "{root}/lib.sh"\n{snippet}'],
                cwd=str(root), env=e, stdout=PIPE, stderr=PIPE, universal_newlines=True)

    return Tool()


@pytest.fixture
def a_module(tool):
    """One module at v0, v-1 and v10, with 2 orders each where orders exist."""
    tool.versions([
        (7, 0,   "own/repo", "mod", "sha000"),
        (7, -1,  "own/repo", "mod", "shaneg1"),
        (7, 10,  "own/repo", "mod", "sha010"),
        (7, 5,   "own/repo", "mod", "sha005"),
    ])
    return tool
