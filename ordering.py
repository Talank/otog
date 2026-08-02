"""Single implementation of candidate parsing and applied-order construction."""
import re


def read_candidates(path):
    parts = (l.rstrip("\n").split("\t") for l in open(path) if l.strip())
    return [(test, d, flags) for test, d, _rank, flags in parts]


def block_members(flags):
    m = re.search(r"members=([^\]]+)\]", flags)
    return m.group(1).split(",") if m else []



def single_move(original, test, direction, flags=""):
    """Order for ONE candidate's targeted move."""
    if direction == "blockback":
        members = set(block_members(flags))
        return [t for t in original if t not in members] + [t for t in original if t in members]
    if direction.startswith("swap:"):
        other = direction.split(":", 1)[1]
        moved, (i, j) = original[:], (original.index(test), original.index(other))
        moved[i], moved[j] = moved[j], moved[i]
        return moved
    rest = [t for t in original if t != test]
    return [test] + rest if direction == "front" else rest + [test]


def apply_all(original, candidates):
    """Applied order for a candidate set: front + middle(+swaps) + ranked backs + block tail."""
    front, back, dirs, swaps, block = [], [], {}, [], set()
    for test, d, flags in candidates:
        if d == "blockback":
            block = set(block_members(flags))
        elif d.startswith("swap:"):
            swaps.append((test, d.split(":", 1)[1]))
        else:
            dirs[test] = d
            (front if d == "front" else back).append(test)
    blockset = block - set(dirs)
    middle = [t for t in original if t not in dirs and t not in blockset]
    for a, b in swaps:
        if a in middle and b in middle:
            i, j = middle.index(a), middle.index(b)
            middle[i], middle[j] = middle[j], middle[i]
    applied = front + middle + back + [t for t in original if t in blockset]
    assert sorted(applied) == sorted(original)
    return applied
