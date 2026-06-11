#!/usr/bin/env python3
import argparse
import numpy as np
import matplotlib.pyplot as plt


def parse_matrix(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]

    header = lines[0].split()
    n = len(header)

    row_labels = []
    vals = []
    for ln in lines[1:]:
        toks = ln.split()
        if len(toks) != n + 1:
            raise ValueError(
                f"Malformed row: expected {n+1} tokens (label + {n} values), got {len(toks)} in: {ln}"
            )
        row_labels.append(toks[0])
        vals.append([float(x) for x in toks[1:]])

    mat = np.array(vals, dtype=float)
    if mat.shape != (n, n):
        raise ValueError(f"Matrix is not square: got {mat.shape}, expected ({n}, {n})")

    return header, row_labels, mat


def main():
    ap = argparse.ArgumentParser(description="Plot a text matrix as a heatmap.")
    ap.add_argument("--input", required=True, help="Path to text file with matrix")
    ap.add_argument("--output", default="matrix_heatmap.png", help="Output PNG path")
    ap.add_argument("--title", default="Matrix Heatmap", help="Plot title")
    ap.add_argument("--figsize", default="12,10", help="Figure size W,H (inches), e.g. 12,10")
    ap.add_argument("--cmap", default="viridis", help="Matplotlib colormap")
    ap.add_argument("--annot", action="store_true", help="Annotate cells with values")
    args = ap.parse_args()

    cols, rows, mat = parse_matrix(args.input)
    w, h = [float(x) for x in args.figsize.split(",")]

    fig, ax = plt.subplots(figsize=(w, h))
    im = ax.imshow(mat, cmap=args.cmap, aspect="auto", vmin=0.0, vmax=1.0)

    ax.set_xticks(np.arange(len(cols)))
    ax.set_yticks(np.arange(len(rows)))
    ax.set_xticklabels(cols, rotation=45, ha="right")
    ax.set_yticklabels(rows)
    ax.set_title(args.title)

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Value")

    if args.annot:
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                v = mat[i, j]
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if v > np.nanmax(mat) * 0.5 else "black")

    fig.tight_layout()
    fig.savefig(args.output, dpi=200)
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
