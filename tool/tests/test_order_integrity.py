"""The orders ARE the experiment. A dropped test, a reordered file or a run
filed under the wrong order id all look like valid data afterwards."""

import subprocess
from subprocess import PIPE
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = ["a.T#one", "a.T#two", "b.U#only", "c.V#x", "c.V#y"]


def test_an_order_is_a_permutation_of_the_test_list(tool):
    # Same set, no duplicates. An order that quietly drops a test measures a
    # smaller suite and its timing is not comparable with the others.
    generator = REPO / "scripts" / "generate_random_test_order.py"
    src = tool.path / "test_list.txt"
    src.write_text("\n".join(TESTS) + "\n")
    out = tool.path / "gen"
    out.mkdir()

    subprocess.run([sys.executable, str(generator), "3", str(src), str(out)],
                   stdout=PIPE, stderr=PIPE, check=True)

    for f in out.glob("*.txt"):
        produced = f.read_text().split()
        assert sorted(produced) == sorted(TESTS)
        assert len(produced) == len(set(produced))


def test_a_class_methods_stay_contiguous(tool):
    # Interleaving classes is a different experiment: surefire pays class
    # setup/teardown per contiguous block.
    generator = REPO / "scripts" / "generate_random_test_order.py"
    src = tool.path / "test_list.txt"
    src.write_text("\n".join(TESTS) + "\n")
    out = tool.path / "gen"
    out.mkdir()
    subprocess.run([sys.executable, str(generator), "5", str(src), str(out)],
                   stdout=PIPE, stderr=PIPE, check=True)

    for f in out.glob("*.txt"):
        classes = [t.split("#")[0] for t in f.read_text().split()]
        blocks = [c for i, c in enumerate(classes) if i == 0 or classes[i - 1] != c]
        assert len(blocks) == len(set(classes)), f"{f.name} interleaves classes"


def test_adapting_an_order_keeps_shared_tests_in_their_relative_order(tool):
    # Adaptation may drop and append, but must not shuffle what both versions
    # have -- otherwise a version-to-version comparison compares two shuffles.
    adapter = REPO / "scripts" / "order_adapter.py"
    order = tool.path / "o.txt"
    target = tool.path / "t.txt"
    result = tool.path / "out.txt"
    order.write_text("a.T#one\na.T#two\nb.U#only\n")
    target.write_text("a.T#one\na.T#two\nb.U#only\nc.New#n\n")

    subprocess.run([sys.executable, str(adapter), str(order), str(target),
                    str(result)], stdout=PIPE, stderr=PIPE, check=True)

    produced = result.read_text().split()
    kept = [t for t in produced if t in ("a.T#one", "a.T#two", "b.U#only")]
    assert kept == ["a.T#one", "a.T#two", "b.U#only"]
    assert "c.New#n" in produced


def test_adapting_drops_tests_the_target_no_longer_has(tool):
    adapter = REPO / "scripts" / "order_adapter.py"
    order = tool.path / "o.txt"
    target = tool.path / "t.txt"
    result = tool.path / "out.txt"
    order.write_text("a.T#one\na.T#gone\nb.U#only\n")
    target.write_text("a.T#one\nb.U#only\n")

    subprocess.run([sys.executable, str(adapter), str(order), str(target),
                    str(result)], stdout=PIPE, stderr=PIPE, check=True)

    assert "a.T#gone" not in result.read_text().split()


def test_an_order_id_names_the_same_file_everywhere(a_module):
    # order N of a version is orders/<module>/<version>/N.txt, always. This is
    # what makes runs/<m>/<v>/order_N/ and orders/<m>/<v>/N.txt refer to one
    # thing; if the id ever drifted, runs would be filed against the wrong
    # permutation and nothing downstream would notice.
    a_module.order(7, 0, 42, TESTS)
    out = a_module.call('order_file 7 0 42')
    assert out.stdout.strip().endswith("/orders/7/0/42.txt")


def test_a_path_is_used_as_given_not_looked_up(a_module):
    out = a_module.call('order_file 7 0 /tmp/handmade.txt')
    assert out.stdout.strip() == "/tmp/handmade.txt"


def test_a_negative_version_is_not_mistaken_for_a_path(a_module):
    out = a_module.call('order_file 7 -1 1')
    assert out.stdout.strip().endswith("/orders/7/-1/1.txt")
