"""Stage 3 figures, drawn from the CSV tables written by flightrel.descriptive.

    python -m flightrel.figures
Each figure answers one question; titles state the question, captions give the denominator.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from .config import PROJECT_ROOT

TABLES = PROJECT_ROOT / "reports" / "tables"
FIGS = PROJECT_ROOT / "reports" / "figures"
# Colour-blind-safe palette (Okabe-Ito subset).
BLUE, ORANGE, GREEN, RED, GREY, PURPLE = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#7f7f7f", "#CC79A7"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

plt.rcParams.update({"figure.dpi": 110, "savefig.dpi": 160, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
                     "axes.titlesize": 11, "axes.titleweight": "bold", "font.size": 9})


def T(name: str) -> pd.DataFrame:
    return pd.read_csv(TABLES / f"{name}.csv")


def pct(ax, axis="y"):
    fmt = matplotlib.ticker.PercentFormatter(1.0, decimals=0)
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def save(fig, name: str, caption: str):
    fig.text(0.01, 0.005, caption, fontsize=7.5, color="#444", ha="left", va="bottom", wrap=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGS / f"{name}.png")
    plt.close(fig)


def fig_annual():
    a = T("annual")
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    styles = {"all": (GREY, "--", "All data"), "matched_months": (BLUE, "-", "Matched months (excl. Jul, Oct)"),
              "stable_matched": (ORANGE, "-", "Matched months, 10 continuously reporting carriers")}
    for s, (c, ls, lab) in styles.items():
        d = a[a.scope == s]
        ax[0].plot(d.year, d.arr_late_rate, color=c, ls=ls, marker="o", ms=4, label=lab)
        ax[0].fill_between(d.year, d.arr_late_rate_lo, d.arr_late_rate_hi, color=c, alpha=0.25)
        ax[1].plot(d.year, d.cancel_rate, color=c, ls=ls, marker="o", ms=4, label=lab)
    ax[0].set_title("Has on-time arrival performance changed over time?")
    ax[0].set_ylabel("Share of completed flights arriving >= 15 min late")
    ax[1].set_title("How have cancellation rates moved?")
    ax[1].set_ylabel("Share of scheduled flights cancelled")
    for x in ax:
        x.set_xticks(range(2009, 2019))
    pct(ax[0])
    ax[1].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=1))
    ax[0].legend(fontsize=7.5, loc="upper right")
    save(fig, "fig01_annual_trends", "Bands: 95% Wilson intervals (very narrow at n of 5-7M per year). Annual 'all data' for 2009 and "
         "2011 covers 11 months (Oct 2009 and Jul 2011 are absent); 2018 adds six regional carriers.")


def fig_calendar():
    m, w = T("month"), T("weekday")
    fig, ax = plt.subplots(1, 2, figsize=(11, 4), gridspec_kw={"width_ratios": [1.7, 1]})
    for d, x, labels, col in ((m, ax[0], MONTHS, "month"), (w, ax[1], DAYS, "day_of_week")):
        err = [d.arr_late_rate - d.arr_late_rate_lo, d.arr_late_rate_hi - d.arr_late_rate]
        x.bar(d[col] - 1, d.arr_late_rate, yerr=err, color=BLUE, alpha=0.85, capsize=2)
        x.axhline(d.arr_late_n.sum() / d.completed_n.sum(), color=RED, ls="--", lw=1)
        x.set_xticks(range(len(labels))); x.set_xticklabels(labels); pct(x)
    ax[0].set_title("Which months are least reliable?")
    ax[1].set_title("Which weekdays?")
    ax[0].set_ylabel("Share arriving >= 15 min late")
    ax[0].text(0.01, 0.95, "dashed = all-period average", transform=ax[0].transAxes, color=RED, fontsize=8, va="top")
    save(fig, "fig02_month_weekday", "Months use all years (Jul 2011 and Oct 2009 absent); weekdays use matched months. "
         "Error bars: 95% Wilson intervals. Completed flights only.")


def fig_hour():
    h = T("hour")
    big = h.completed_n >= 50_000
    cols = ["arr_late_rate", "arr_late_rate_lo", "arr_late_rate_hi", "dep_late_rate"]
    lines = h.copy()
    lines.loc[~big, cols] = np.nan  # break the line at low-volume hours instead of interpolating across them
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(lines.sched_dep_hour, lines.arr_late_rate, "-o", color=BLUE, label="Late arrival (>= 15 min)")
    ax.plot(lines.sched_dep_hour, lines.dep_late_rate, "-s", color=ORANGE, ms=4, label="Late departure (>= 15 min)")
    ax.fill_between(lines.sched_dep_hour, lines.arr_late_rate_lo, lines.arr_late_rate_hi, color=BLUE, alpha=0.2)
    ax2 = ax.twinx()
    ax2.bar(h.sched_dep_hour, h.completed_n / 1e6, color=GREY, alpha=0.18, width=0.8)
    ax2.set_ylabel("Completed flights (millions, bars)"); ax2.grid(False)
    ax.set_xticks(range(0, 24)); ax.set_xlabel("Scheduled departure hour (local)"); pct(ax)
    ax.set_ylabel("Share of flights late")
    ax.set_title("How does delay risk build through the operating day?")
    ax.legend(loc="upper left")
    ax.set_zorder(ax2.get_zorder() + 1); ax.patch.set_visible(False)
    save(fig, "fig03_departure_hour", "Matched months. Hours with fewer than 50,000 completed flights (00-04h) are omitted from the lines. "
         "Band: 95% Wilson interval.")


def fig_carriers():
    c = T("carrier"); stable = set(T("stable_carriers").op_carrier)
    c = c[c.completed_n >= 500_000].sort_values("arr_late_rate")
    fig, ax = plt.subplots(figsize=(8.5, 6))
    y = np.arange(len(c))
    cols = [BLUE if k in stable else ORANGE for k in c.op_carrier]
    ax.hlines(y, c.arr_late_rate_lo, c.arr_late_rate_hi, color=cols, lw=2)
    ax.scatter(c.arr_late_rate, y, color=cols, zorder=3)
    ax.set_yticks(y); ax.set_yticklabels([f"{k}  (n={n/1e6:.1f}M)" for k, n in zip(c.op_carrier, c.completed_n)])
    pct(ax, "x"); ax.set_xlabel("Share of completed flights arriving >= 15 min late")
    ax.set_title("How do airlines compare on late arrivals? (unadjusted)")
    ax.scatter([], [], color=BLUE, label="Reports in all 10 years"); ax.scatter([], [], color=ORANGE, label="Reports in some years only")
    ax.legend(loc="lower right")
    save(fig, "fig04_carriers", "Matched months, carriers with >= 500k completed flights. Intervals: 95% Wilson. UNADJUSTED: carriers fly different "
         "routes, years and airports; carriers present only in some years are not directly comparable (see Stage 4).")


def fig_carrier_heat():
    cy = T("carrier_year"); stable = T("stable_carriers").op_carrier.tolist()
    p = cy[cy.op_carrier.isin(stable)].pivot(index="op_carrier", columns="year", values="arr_late_rate")
    p = p.loc[p.mean(axis=1).sort_values().index]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    im = ax.imshow(p.values, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(p.shape[1])); ax.set_xticklabels(p.columns); ax.set_yticks(range(p.shape[0])); ax.set_yticklabels(p.index)
    for i in range(p.shape[0]):
        for j in range(p.shape[1]):
            ax.text(j, i, f"{p.values[i, j]*100:.0f}", ha="center", va="center", fontsize=8,
                    color="white" if p.values[i, j] > 0.22 else "black")
    ax.grid(False); fig.colorbar(im, ax=ax, format=matplotlib.ticker.PercentFormatter(1.0, decimals=0), label="Late-arrival rate")
    ax.set_title("Are airline rankings stable from year to year? (% late, continuously reporting carriers)")
    save(fig, "fig05_carrier_year_heatmap", "Matched months, completed flights. Cell labels are percentages; rows sorted by 10-year mean. "
         "Cell sizes range from tens of thousands to over a million flights.")


def fig_airports():
    o = T("airport_origin")
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.scatter(o.completed_n / 1e6, o.arr_late_rate, s=18 + 900 * o.cancel_rate, color=BLUE, alpha=0.6, edgecolor="white")
    lab = pd.concat([o.nlargest(8, "arr_late_rate"), o.nsmallest(5, "arr_late_rate"), o.nlargest(5, "completed_n")]).drop_duplicates("origin")
    for _, r in lab.iterrows():
        ax.annotate(r.origin, (r.completed_n / 1e6, r.arr_late_rate), fontsize=8, xytext=(3, 3), textcoords="offset points")
    ax.set_xscale("log"); pct(ax)
    ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(0.02))
    ax.set_xlabel("Completed flights, 2009-2018 matched months (millions, log scale)")
    ax.set_ylabel("Share of flights departing this airport that arrive >= 15 min late")
    ax.set_title("Which origin airports are structurally unreliable, and is it just a big-airport effect?")
    save(fig, "fig06_airports", "Origins with >= 50,000 completed flights (n=111). Marker area is proportional to the cancellation rate. "
         "Unadjusted for airline mix and route length.")


def fig_persistence():
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for x, name, q, title in ((ax[0], "persist_origin", 0.75, "Airports (worst quartile each year)"),
                              (ax[1], "persist_route", 0.90, "Routes (worst decile each year)")):
        d = T(name); n = len(d); yrs = d.years_observed.max(); k = np.arange(yrs + 1)
        obs = d.years_poor.value_counts().reindex(k, fill_value=0).astype(float).replace(0, np.nan)
        exp = n * stats.binom.pmf(k, yrs, 1 - q)
        x.bar(k - 0.2, obs, width=0.4, color=BLUE, label="Observed")
        x.bar(k + 0.2, exp, width=0.4, color=GREY, alpha=0.7, label="Expected if year-to-year luck")
        x.set_yscale("log"); x.set_ylim(0.3, None); x.set_xticks(k); x.set_xlabel("Number of years in the worst tail (of 10)")
        x.set_ylabel(f"Number of {'airports' if 'origin' in name else 'routes'}"); x.set_title(title); x.legend(fontsize=8)
    fig.suptitle("Is poor reliability persistent or random? (observed vs. chance expectation)", fontweight="bold", fontsize=11)
    save(fig, "fig07_persistence", "Matched months. Entities with >= 8 observed years (airports >= 5,000, routes >= 300 completed flights/year). "
         "Chance model: independent years, each with probability 1 - quantile of being in the tail.")


def fig_dep_arr():
    d = T("dep_to_arr")
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    lab = [s.split(": ")[1].replace(" (", "\n(") for s in d.dep_delay_bin]
    err = [d.arr_late_rate - d.arr_late_rate_lo, d.arr_late_rate_hi - d.arr_late_rate]
    ax[0].bar(range(len(d)), d.arr_late_rate, yerr=err, color=BLUE, capsize=2)
    for i, (r, n) in enumerate(zip(d.arr_late_rate, d.n)):
        ax[0].text(i, r + 0.02, f"{r*100:.0f}%\nn={n/1e6:.1f}M", ha="center", fontsize=7)
    ax[0].set_xticks(range(len(d))); ax[0].set_xticklabels(lab, fontsize=7); pct(ax[0]); ax[0].set_ylim(0, 1.12)
    ax[0].set_ylabel("Share arriving >= 15 min late"); ax[0].set_xlabel("Departure delay (min)")
    ax[0].set_title("Does a late departure mean a late arrival?")
    ax[1].bar(range(len(d)), d.median_change_in_delay, color=ORANGE, label="Median")
    ax[1].plot(range(len(d)), d.mean_change_in_delay, "o-", color=RED, label="Mean")
    ax[1].axhline(0, color="k", lw=0.8); ax[1].set_xticks(range(len(d))); ax[1].set_xticklabels(lab, fontsize=7)
    ax[1].set_ylabel("Arrival delay minus departure delay (min)"); ax[1].set_xlabel("Departure delay (min)")
    ax[1].set_title("How much delay is recovered between gate and gate?"); ax[1].legend()
    save(fig, "fig08_departure_to_arrival", "Matched months, completed flights with both delays known. Negative = delay recovered in flight/taxi. "
         "Bars (left): 95% Wilson intervals.")


def fig_taxi():
    d = T("taxi_out_bins")
    fig, ax = plt.subplots(figsize=(8, 4.3))
    for s, c in (("departed on time (<15)", BLUE), ("departed late (>=15)", RED)):
        x = d[d.departure_status == s]
        ax.plot(x.taxi_out_bin.str[3:], x.arr_late_rate, "-o", color=c, label=s)
        ax.fill_between(range(len(x)), x.arr_late_rate_lo, x.arr_late_rate_hi, color=c, alpha=0.2)
    pct(ax); ax.set_xlabel("Taxi-out time (min, gate to wheels-off)"); ax.set_ylabel("Share arriving >= 15 min late")
    ax.set_title("Is a long taxi-out a warning sign, even for flights that left on time?"); ax.legend()
    save(fig, "fig09_taxi_out", "Matched months, completed flights with taxi-out 0-300 min. Taxi time is part of gate-to-gate time, so part of this "
         "association is arithmetic rather than causal.")


def fig_cancellations():
    cy, cm = T("cancel_codes_year"), T("cancel_codes_month")
    names = {"A": "Carrier", "B": "Weather", "C": "National air system", "D": "Security"}
    cols = {"A": BLUE, "B": ORANGE, "C": GREEN, "D": RED}
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    py = cy.pivot_table(index="year", columns="cancellation_code", values="cancelled_n", aggfunc="sum").fillna(0)
    pm = cm.pivot_table(index="month", columns="cancellation_code", values="cancelled_n", aggfunc="sum").fillna(0)
    for p, x, lab in ((py, ax[0], None), (pm, ax[1], MONTHS)):
        bottom = np.zeros(len(p))
        for k in "ABCD":
            if k in p:
                x.bar(range(len(p)), p[k] / 1000, bottom=bottom, color=cols[k], label=names[k]); bottom += (p[k] / 1000).values
        x.set_xticks(range(len(p))); x.set_xticklabels(lab if lab else p.index.astype(str), fontsize=8)
        x.set_ylabel("Cancelled flights (thousands)")
    ax[0].set_title("Why are flights cancelled, by year?"); ax[1].set_title("... and by month (all years)")
    ax[0].legend(fontsize=8)
    save(fig, "fig10_cancellations", "Cancelled flights with a reason code, all years (Oct 2009 and Jul 2011 absent). "
         "Counts, not rates; compare with the annual cancellation rate in figure 1.")


def main():
    for f in (fig_annual, fig_calendar, fig_hour, fig_carriers, fig_carrier_heat, fig_airports, fig_persistence,
              fig_dep_arr, fig_taxi, fig_cancellations):
        f()
        print("wrote", f.__name__)


if __name__ == "__main__":
    main()
