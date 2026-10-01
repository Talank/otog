#!/usr/bin/env python3
"""Make reduction_percentage_comparison.pdf, the paper's Figure 11.

    python3 make_reduction_figure.py

One panel per "Commit" row of Table 4, one line per approach. Each point is the
mean saving over the modules at one future version, v10..v100, computed as in
make_overall_eval_data.py, so a Table 4 cell is the mean of its panel's line.
The plotted values are also written to reduction_percentage_comparison.csv.
Agent has no -50 or -100 order, so those two panels have no Agent line.
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42   # TrueType; publisher PDF checks often reject Type 3
import matplotlib.pyplot as plt

from make_overall_eval_data import (APPROACHES, COMMITS, FUTURE, fmt,
                                    module_rows, version_saving)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PDF = os.path.join(HERE, "reduction_percentage_comparison.pdf")
OUT_CSV = os.path.join(HERE, "reduction_percentage_comparison.csv")

# approach -> (legend name, color, marker). The colors are the first four slots
# of a colorblind-checked palette; the markers tell the lines apart in print.
STYLE = {
    "naive":    ("Naive", "#2a78d6", "o"),
    "jfrsort":  ("JFRSort", "#eb6834", "s"),
    "agent":    ("Agent", "#1baf7a", "^"),
    "warmsort": ("WarmSort", "#eda100", "D"),
}
INK, MUTED, AXIS, GRID = "#0b0b0b", "#52514e", "#c3c2b7", "#e1e0d9"


def points(rows):
    """{(approach, commit): the saving at each future version}"""
    return {(a, c): [version_saving(rows, APPROACHES[a][c], v) for v in FUTURE]
            for a in APPROACHES for c in COMMITS}


def write_csv(pts):
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["commit", "version"] + list(APPROACHES))
        for c in COMMITS:
            for i, v in enumerate(FUTURE):
                writer.writerow([c, v] + [fmt(pts[(a, c)][i]) for a in APPROACHES])


def draw_panel(ax, pts, commit):
    for a, (name, color, marker) in STYLE.items():
        ys = pts[(a, commit)]
        if any(y is not None for y in ys):
            ax.plot(FUTURE, ys, label=name, color=color, marker=marker,
                    linewidth=1.5, markersize=5,
                    markeredgecolor="white", markeredgewidth=0.6)
    ax.axhline(0, color=AXIS, linewidth=1, zorder=0)
    ax.set_title("Commit #: %d" % commit, color=INK, fontsize=9)
    ax.set_xticks(FUTURE)
    ax.grid(color=GRID, linewidth=0.5)
    ax.tick_params(colors=MUTED, labelsize=7.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)


def main():
    pts = points(module_rows())
    write_csv(pts)

    fig, axes = plt.subplots(2, 3, figsize=(7.5, 4.6), sharex=True,
                             sharey=True, layout="constrained")
    cells = axes.flatten()
    for ax, c in zip(cells, COMMITS):
        draw_panel(ax, pts, c)
    cells[2].tick_params(labelbottom=True)   # no panel below it to carry them

    # The last cell holds the legend; cold start has all four approaches.
    cells[-1].axis("off")
    cells[-1].legend(*cells[len(COMMITS) - 1].get_legend_handles_labels(),
                     loc="center", frameon=False, fontsize=9)

    fig.suptitle("Average Reduction", color=INK, fontsize=10)
    fig.supxlabel("Version", color=MUTED, fontsize=9)
    fig.supylabel("Reduction Percentage", color=MUTED, fontsize=9)
    fig.savefig(OUT_PDF)
    print("wrote %s and %s" % (OUT_PDF, OUT_CSV))


if __name__ == "__main__":
    main()
