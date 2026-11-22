"""Evidence figures as base64 PNGs; no GUI or pyplot global figures."""

import base64
import io
import threading

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from . import config as cfg
from .preprocess import Preprocessed

_plot_lock = threading.Lock()  # Matplotlib font caches are shared across API threads.


def _figure(height: float = 3.3) -> Figure:
    return Figure(figsize=(10, height), dpi=cfg.PLOT_DPI, layout="constrained", facecolor="white")


def _style(axis, title: str, ylabel: str, xlabel: str = "Time (s)") -> None:
    axis.set_title(title, loc="left", fontsize=11, color="#222222", pad=10)
    axis.set_xlabel(xlabel, fontsize=10)
    axis.set_ylabel(ylabel, fontsize=10)
    axis.grid(True, color="#e7edf2", linewidth=0.6)
    axis.tick_params(labelsize=9)
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#bcc9d3")


def _encode(figure: Figure) -> str:
    buffer = io.BytesIO()
    FigureCanvasAgg(figure).print_png(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    figure.clear()
    return encoded


def render_plots(processed: Preprocessed, r_peaks: np.ndarray) -> dict[str, str]:
    """Raw/filtered, spectrum, R events and full-strip RR tachogram.

    Waveform previews show at most ten seconds for legibility. Spectrum and
    tachogram use the entire supplied strip; all metric calculations do too.
    """
    with _plot_lock:
        fs = processed.fs
        count = min(processed.raw.size, int(cfg.PLOT_MAX_SECONDS * fs))
        time = np.arange(count) / fs
        duration = processed.raw.size / fs
        shown = count / fs
        peaks = np.asarray(r_peaks, dtype=int)
        plots = {}

        figure = _figure(4.4)
        raw_axis, clean_axis = figure.subplots(2, 1, sharex=True)
        raw_axis.plot(time, processed.raw[:count], color="#7b8792", linewidth=0.9)
        clean_axis.plot(time, processed.filtered[:count], color="#2c6394", linewidth=0.9)
        _style(raw_axis, f"Raw ECG (first {shown:g} s)", "mV", "")
        _style(clean_axis, "Filtered ECG • baseline drift / muscle artifact attenuated", "mV")
        clean_axis.set_xlim(0, shown)
        plots["raw_filtered"] = _encode(figure)

        figure = _figure()
        axis = figure.subplots()
        before = 10 * np.log10(np.maximum(processed.raw_power, cfg.NUMERICAL_EPSILON))
        after = 10 * np.log10(np.maximum(processed.filtered_power, cfg.NUMERICAL_EPSILON))
        axis.plot(processed.frequencies, before, color="#7b8792", linewidth=1, label="Before filtering")
        axis.plot(processed.frequencies, after, color="#2c6394", linewidth=1, label="After filtering")
        if processed.notch_hz:
            axis.axvline(processed.notch_hz, color="#c35060", linestyle="--", linewidth=0.9,
                         label=f"{processed.notch_hz:g} Hz mains notch")
        _style(axis, "Power spectrum • full strip", "PSD (dB re 1 mV²/Hz)", "Frequency (Hz)")
        axis.set_xlim(0, min(fs / 2, cfg.PLOT_SPECTRUM_MAX_HZ))
        axis.legend(fontsize=9, loc="best", frameon=False)
        plots["spectrum"] = _encode(figure)

        figure = _figure()
        axis = figure.subplots()
        axis.plot(time, processed.filtered[:count], color="#2c6394", linewidth=1, label="Filtered ECG")
        visible_peaks = peaks[peaks < count]
        axis.scatter(visible_peaks / fs, processed.filtered[visible_peaks], s=26, color="#c35060", zorder=3,
                     label="Detected R events")
        _style(axis, f"R events on filtered ECG • first {shown:g} s", "mV")
        axis.set_xlim(0, shown)
        axis.legend(fontsize=9, frameon=False)
        plots["r_peaks"] = _encode(figure)

        figure = _figure()
        axis = figure.subplots()
        if peaks.size >= 2:
            axis.plot(peaks[1:] / fs, np.diff(peaks) / fs * 1000, "o-", markersize=3,
                      linewidth=1, color="#2c6394")
        else:
            axis.text(0.5, 0.5, "Too few detected beats for RR intervals", transform=axis.transAxes,
                      ha="center", color="#667788")
        _style(axis, "RR tachogram • all detected intervals in full strip", "RR interval (ms)")
        axis.set_xlim(0, duration)
        plots["rr_tachogram"] = _encode(figure)
        return plots
