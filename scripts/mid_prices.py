"""
mid_prices.py
-------------
Export and plot per-second mid-price time-series for TSE tickers.

Subcommands:
  export   Fetch orderbooks for N tickers on a Jalali date and write a CSV:
               time,<ticker_1>,<ticker_2>,...
               08:45:03,48500.00,,
               ...
           Each row is a 1-second snapshot; each ticker column holds
           (best_bid + best_ask) / 2 at that second, forward-filled between
           the ticker's first and last observed events.

  plot     Read a CSV produced by `export` and emit a standalone HTML
           visualization rendered by plotly (auto-opens in your browser).
           Modes: subplots (default), overlay, normalized.

  all      Run `export` then `plot` on the resulting CSV.

All generated files (CSV + HTML) are written under the repo's `data/`
directory by default, which is gitignored. Override with --data-dir or
pass an explicit --out.

Examples:
  uv run python scripts/mid_prices.py export \\
      --tickers 35425587644337450,46700660505281786 \\
      --year 1405 --month 2 --day 1

  uv run python scripts/mid_prices.py plot mid_prices_1405-02-01.csv --mode normalized

  uv run python scripts/mid_prices.py all \\
      --tickers 35425587644337450,46700660505281786 \\
      --year 1405 --month 2 --day 1 --mode overlay
"""

import argparse
import sys
import webbrowser
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from historical import TSETMCClient, TickerSnapshots, write_mid_price_csv


DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# path helpers
# ---------------------------------------------------------------------------

def _resolve_data_dir(data_dir: str | None) -> Path:
    d = Path(data_dir).resolve() if data_dir else DEFAULT_DATA_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_output(out: str | None, default_name: str, data_dir: Path) -> Path:
    """If --out is given, honor it as-is (absolute or relative to CWD).
    Otherwise put `default_name` inside data_dir."""
    if out:
        return Path(out).expanduser().resolve()
    return data_dir / default_name


def _resolve_input_csv(csv_arg: str, data_dir: Path) -> Path:
    """Accept an explicit path (absolute/relative to CWD) or a bare filename
    that lives under data_dir."""
    p = Path(csv_arg).expanduser()
    if p.is_file():
        return p.resolve()
    candidate = data_dir / p.name
    if candidate.is_file():
        return candidate.resolve()
    sys.exit(f"ERROR: file not found — tried {p} and {candidate}")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def do_export(tickers: list[str], date: str, out_path: Path) -> Path | None:
    client = TSETMCClient()
    books = []
    for t in tickers:
        print(f"Fetching {t} on {date} ...")
        try:
            snaps = client.fetch_orderbook_snapshots(t, date)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        if not snaps:
            print(f"  {t}: no trading-hours snapshots")
            continue
        first, last = snaps[0].time, snaps[-1].time
        print(f"  {t}: {len(snaps)} snapshots ({first} → {last})")
        books.append(TickerSnapshots(ticker=t, snapshots=snaps))

    if not books:
        print("No playable books.")
        return None

    rows = write_mid_price_csv(books, out_path)
    print(f"\nWrote {rows} rows × {len(books) + 1} columns → {out_path}")
    return out_path


def cmd_export(args) -> Path | None:
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        sys.exit("No tickers provided.")

    date = f"{args.year:04d}-{args.month:02d}-{args.day:02d}"
    data_dir = _resolve_data_dir(args.data_dir)
    out_path = _resolve_output(args.out, f"mid_prices_{date}.csv", data_dir)
    return do_export(tickers, date, out_path)


# ---------------------------------------------------------------------------
# plot
# ---------------------------------------------------------------------------

RANGE_SELECTOR_BUTTONS = [
    dict(count=15, step="minute", stepmode="backward", label="15m"),
    dict(count=30, step="minute", stepmode="backward", label="30m"),
    dict(count=1,  step="hour",   stepmode="backward", label="1h"),
    dict(count=2,  step="hour",   stepmode="backward", label="2h"),
    dict(step="all", label="All"),
]


def _load(csv_path: Path):
    df = pd.read_csv(csv_path)
    if "time" not in df.columns:
        sys.exit(f"ERROR: {csv_path} has no 'time' column — is it from `export`?")
    df["_t"] = pd.to_datetime(df["time"], format="%H:%M:%S")
    tickers = [c for c in df.columns if c not in ("time", "_t")]
    if not tickers:
        sys.exit("ERROR: no ticker columns in CSV")
    return df, tickers


def _time_axis_cfg(include_slider: bool):
    cfg = dict(
        tickformat="%H:%M:%S",
        rangeselector=dict(
            buttons=RANGE_SELECTOR_BUTTONS,
            bgcolor="#1c2128",
            activecolor="#ffb454",
            font=dict(color="#e6e1cf", size=11),
            x=0, xanchor="left", y=1.08, yanchor="bottom",
        ),
    )
    if include_slider:
        cfg["rangeslider"] = dict(visible=True, thickness=0.06, bgcolor="#1c2128")
    return cfg


def plot_subplots(df, tickers, title):
    n = len(tickers)
    fig = make_subplots(
        rows=n, cols=1,
        shared_xaxes=True,
        subplot_titles=[f"<b>{t}</b>" for t in tickers],
        vertical_spacing=0.06,
    )
    for i, t in enumerate(tickers, 1):
        fig.add_trace(
            go.Scatter(
                x=df["_t"], y=df[t], name=t, mode="lines",
                line=dict(color="#ffb454", width=1.2),
                connectgaps=False,
                hovertemplate="<b>%{fullData.name}</b><br>%{x|%H:%M:%S}<br>%{y:,.0f}<extra></extra>",
            ),
            row=i, col=1,
        )
        fig.update_yaxes(tickformat=",d", row=i, col=1)

    xaxis_key = f"xaxis{n}" if n > 1 else "xaxis"
    fig.update_layout(**{xaxis_key: _time_axis_cfg(include_slider=True)})

    fig.update_layout(
        height=max(300, 230 * n) + 60,
        showlegend=False,
        title=dict(text=title, x=0.5, xanchor="center", font=dict(size=14)),
    )
    return fig


def plot_overlay(df, tickers, title):
    fig = go.Figure()
    for t in tickers:
        fig.add_trace(go.Scatter(
            x=df["_t"], y=df[t], name=t, mode="lines",
            connectgaps=False,
            hovertemplate="<b>%{fullData.name}</b><br>%{x|%H:%M:%S}<br>%{y:,.0f}<extra></extra>",
        ))
    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center", font=dict(size=14)),
        xaxis=_time_axis_cfg(include_slider=True),
        yaxis=dict(tickformat=",d", title="mid-price"),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=1, xanchor="right"),
        height=620,
    )
    return fig


def plot_normalized(df, tickers, title):
    fig = go.Figure()
    for t in tickers:
        s = df[t].dropna()
        if s.empty:
            continue
        base = s.iloc[0]
        pct = (df[t] / base - 1.0) * 100.0
        fig.add_trace(go.Scatter(
            x=df["_t"], y=pct, name=t, mode="lines",
            connectgaps=False,
            hovertemplate="<b>%{fullData.name}</b><br>%{x|%H:%M:%S}<br>%{y:+.2f}%<extra></extra>",
        ))
    fig.add_hline(y=0, line_color="rgba(200,200,200,0.3)", line_width=0.5)
    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center", font=dict(size=14)),
        xaxis=_time_axis_cfg(include_slider=True),
        yaxis=dict(ticksuffix="%", title="% change from first observation"),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=1, xanchor="right"),
        height=620,
    )
    return fig


PLOTTERS = {
    "subplots":   plot_subplots,
    "overlay":    plot_overlay,
    "normalized": plot_normalized,
}


def do_plot(csv_path: Path, mode: str, out_path: Path, title: str | None, open_browser: bool) -> Path:
    df, tickers = _load(csv_path)
    figure_title = title or f"Mid-price · {csv_path.stem} · {len(tickers)} ticker(s)"

    fig = PLOTTERS[mode](df, tickers, figure_title)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f1419",
        plot_bgcolor="#14181f",
        margin=dict(l=70, r=40, t=80, b=60),
    )

    fig.write_html(
        out_path,
        include_plotlyjs="cdn",
        config={
            "displaylogo": False,
            "scrollZoom": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
    )
    print(f"saved → {out_path}")

    if open_browser:
        webbrowser.open(f"file://{out_path.resolve()}")
    return out_path


def cmd_plot(args) -> Path:
    data_dir = _resolve_data_dir(args.data_dir)
    csv_path = _resolve_input_csv(args.csv, data_dir)
    out_path = _resolve_output(
        args.out,
        f"{csv_path.stem}_{args.mode}.html",
        data_dir,
    )
    return do_plot(csv_path, args.mode, out_path, args.title, not args.no_open)


# ---------------------------------------------------------------------------
# all (export + plot)
# ---------------------------------------------------------------------------

def cmd_all(args):
    csv_path = cmd_export(args)
    if csv_path is None:
        sys.exit(1)

    data_dir = _resolve_data_dir(args.data_dir)
    html_out = _resolve_output(
        args.html_out,
        f"{csv_path.stem}_{args.mode}.html",
        data_dir,
    )
    do_plot(csv_path, args.mode, html_out, args.title, not args.no_open)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _add_export_args(p: argparse.ArgumentParser):
    p.add_argument("--tickers", required=True, help="Comma-separated InsCodes")
    p.add_argument("--year",  type=int, required=True, help="Jalali year")
    p.add_argument("--month", type=int, required=True, help="Jalali month")
    p.add_argument("--day",   type=int, required=True, help="Jalali day")
    p.add_argument("--out", default=None,
                   help="CSV path (default: <data-dir>/mid_prices_YYYY-MM-DD.csv)")


def _add_plot_args(p: argparse.ArgumentParser):
    p.add_argument("--mode", choices=PLOTTERS.keys(), default="subplots",
                   help="Plot layout (default: subplots)")
    p.add_argument("--no-open", action="store_true",
                   help="Write the HTML but don't auto-open the browser")
    p.add_argument("--title", help="Override the figure title")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export and plot per-second mid-price CSVs for TSE tickers.",
    )
    parser.add_argument("--data-dir", default=None,
                        help=f"Directory for generated files (default: {DEFAULT_DATA_DIR})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="Fetch orderbooks and write a mid-price CSV")
    _add_export_args(p_export)
    p_export.set_defaults(func=cmd_export)

    p_plot = sub.add_parser("plot", help="Render an HTML mid-price chart from a CSV")
    p_plot.add_argument("csv", help="Path to mid_prices_*.csv (bare filenames resolve under --data-dir)")
    p_plot.add_argument("--out", default=None,
                        help="HTML path (default: <data-dir>/<csv-stem>_<mode>.html)")
    _add_plot_args(p_plot)
    p_plot.set_defaults(func=cmd_plot)

    p_all = sub.add_parser("all", help="Export then plot in one go")
    _add_export_args(p_all)
    _add_plot_args(p_all)
    p_all.add_argument("--html-out", default=None,
                       help="HTML path (default: <data-dir>/<csv-stem>_<mode>.html)")
    p_all.set_defaults(func=cmd_all)

    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()