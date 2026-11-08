"""Render the two D charts as PNG for the report (static, light surface)."""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

OUT = Path(sys.argv[1])
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()

SURFACE, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
LABELS = ["Good", "Needs edit", "Not acceptable"]
COLORS = {"Good": "#0ca30c", "Needs edit": "#fab219", "Not acceptable": "#d03b3b"}
TEXT_ON = {"Good": "#ffffff", "Needs edit": INK, "Not acceptable": "#ffffff"}
GAP = 2  # px surface gap between segments


def stacked(ax, rows, total_label):
    """rows: list of (name, {label: count}). Horizontal stacked bars with direct labels."""
    for i, (name, counts) in enumerate(rows):
        left = 0
        for label in LABELS:
            n = counts[label]
            if n:
                ax.barh(i, n, left=left, height=0.56, color=COLORS[label],
                        edgecolor=SURFACE, linewidth=GAP)
                text = total_label(n, counts) if total_label else str(n)
                ax.text(left + n / 2, i, text, ha="center", va="center",
                        color=TEXT_ON[label], fontsize=10, fontweight="bold")
            left += n
    ax.set_yticks(range(len(rows)), [r[0] for r in rows], color=INK2, fontsize=11)
    ax.invert_yaxis()
    ax.tick_params(axis="y", length=0)
    ax.set_xticks([])
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(AXIS)
    ax.set_facecolor(SURFACE)


def legend(fig):
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[l]) for l in LABELS]
    fig.legend(handles, LABELS, loc="upper left", bbox_to_anchor=(0.02, 0.98), ncol=3,
               frameon=False, fontsize=10, labelcolor=INK2, handlelength=1, handleheight=1)


def fig1():
    counts = {"Good": 75, "Needs edit": 54, "Not acceptable": 21}
    fig, ax = plt.subplots(figsize=(8, 1.9), dpi=200, facecolor=SURFACE)
    stacked(ax, [("150 messages", counts)], lambda n, c: f"{n}\n{n / 150:.0%}")
    legend(fig)
    fig.subplots_adjust(left=0.13, right=0.98, top=0.62, bottom=0.08)
    fig.savefig(OUT / "fig1_labels.png", facecolor=SURFACE)


def fig2():
    rows = [
        ("Birthday and festive greetings", {"Good": 6, "Needs edit": 7, "Not acceptable": 5}),
        ("Product recommendation", {"Good": 14, "Needs edit": 9, "Not acceptable": 4}),
        ("Post-purchase care", {"Good": 17, "Needs edit": 8, "Not acceptable": 2}),
        ("Reactivation", {"Good": 7, "Needs edit": 11, "Not acceptable": 6}),
        ("Event invitation", {"Good": 16, "Needs edit": 7, "Not acceptable": 4}),
        ("Price objection", {"Good": 15, "Needs edit": 12, "Not acceptable": 0}),
    ]
    fig, ax = plt.subplots(figsize=(9, 3.8), dpi=200, facecolor=SURFACE)
    stacked(ax, rows, None)
    legend(fig)
    fig.subplots_adjust(left=0.30, right=0.98, top=0.86, bottom=0.04)
    fig.savefig(OUT / "fig2_scenarios.png", facecolor=SURFACE)


fig1()
fig2()
