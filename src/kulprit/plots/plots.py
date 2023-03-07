from arviz.plots.plot_utils import _scale_fig_size
import matplotlib.pyplot as plt
import numpy as np


def plot_compare(cmp_df, legend=True, title=True, figsize=None, plot_kwargs=None):

    if plot_kwargs is None:
        plot_kwargs = {}

    if figsize is None:
        figsize = (len(cmp_df) - 1, 10)

    figsize, ax_labelsize, _, xt_labelsize, linewidth, _ = _scale_fig_size(
        figsize, None, 1, 1
    )

    xticks_pos, step = np.linspace(0, -1, ((cmp_df.shape[0]) * 2) - 2, retstep=True)
    xticks_pos[1::2] = xticks_pos[1::2] - step * 1.5

    labels = cmp_df.index.values[1:]
    xticks_labels = [""] * len(xticks_pos)
    xticks_labels[0] = labels[0]
    xticks_labels[2::2] = labels[1:]

    _, ax = plt.subplots(1, figsize=figsize)

    ax.errorbar(
        y=cmp_df["elpd_loo"][1:],
        x=xticks_pos[::2],
        yerr=cmp_df.se[1:],
        label="Submodel ELPD",
        color=plot_kwargs.get("color_eldp", "k"),
        fmt=plot_kwargs.get("marker_eldp", "o"),
        mfc=plot_kwargs.get("marker_fc_elpd", "white"),
        mew=linewidth,
        lw=linewidth,
        markersize=4,
    )
    ax.errorbar(
        y=cmp_df["elpd_loo"].iloc[1:],
        x=xticks_pos[1::2],
        yerr=cmp_df.dse[1:],
        label="ELPD difference\n(to reference model)",
        color=plot_kwargs.get("color_dse", "grey"),
        fmt=plot_kwargs.get("marker_dse", "^"),
        mew=linewidth,
        elinewidth=linewidth,
        markersize=4,
    )

    ax.axhline(
        cmp_df["elpd_loo"].iloc[0],
        ls=plot_kwargs.get("ls_reference", "--"),
        color=plot_kwargs.get("color_ls_reference", "grey"),
        lw=linewidth,
        label="Reference model ELPD",
    )

    if legend:
        ax.legend(
            loc="lower right",
            ncol=1,
            fontsize=ax_labelsize * 0.6,
        )

    if title:
        ax.set_title(
            "Model comparison",
            fontsize=ax_labelsize * 0.6,
        )

    # remove double ticks
    xticks_pos, xticks_labels = xticks_pos[::2], xticks_labels[::2]

    # set axes
    ax.set_xticks(xticks_pos)
    ax.set_ylabel("ELPD", fontsize=ax_labelsize * 0.6)
    ax.set_xlabel("Submodel size", fontsize=ax_labelsize * 0.6)
    ax.set_xticklabels(xticks_labels)
    ax.set_xlim(-1 + step, 0 - step)
    ax.tick_params(labelsize=xt_labelsize * 0.6)

    return ax
