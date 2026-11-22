"""Report figures for the API; the frozen benchmark renderer stays untouched."""

import base64
import io
import threading

import cv2
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator

from .preprocess import Preprocessed, Signal, preprocess

NAVY = "#1f3a5f"
TRACE = "#171717"
DPI = 200
MAX_SECONDS = 10
_lock = threading.Lock()


def _figure(height=3.2):
    return Figure(figsize=(8.6, height), dpi=DPI, layout="constrained", facecolor="white")


def _axes(axis, ylabel, xlabel="Time (s)", paper=False):
    axis.set_xlabel(xlabel, fontsize=10)
    axis.set_ylabel(ylabel, fontsize=10)
    axis.tick_params(labelsize=9, colors=TRACE)
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#777777")
    if paper:
        axis.xaxis.set_major_locator(MultipleLocator(0.2))
        axis.xaxis.set_minor_locator(MultipleLocator(0.04))
        axis.yaxis.set_major_locator(MultipleLocator(0.5))
        axis.yaxis.set_minor_locator(MultipleLocator(0.1))
        # Keep paper lines at their physical intervals; label seconds sparsely.
        axis.xaxis.set_major_formatter(lambda value, position: f"{value:g}" if abs(value-round(value)) < 1e-6 else "")
        axis.grid(which="minor", color="#f9dce2", linewidth=0.35)
        axis.grid(which="major", color="#eeb3c0", linewidth=0.65)
        axis.tick_params(which="minor", length=0)
    else:
        axis.grid(color="#dddddd", linewidth=0.5)


def _png(figure):
    buffer = io.BytesIO()
    FigureCanvasAgg(figure).print_png(buffer)
    figure.clear()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def render_plots(processed: Preprocessed, peaks: np.ndarray, *, amplitude_calibrated=True) -> dict[str, str]:
    """Four figures, without titles, using exactly the already measured events."""
    with _lock:
        count = min(processed.raw.size, round(MAX_SECONDS * processed.fs))
        time = np.arange(count) / processed.fs
        shown = count / processed.fs
        plots = {}
        figure = _figure(4.5)
        raw, filtered = figure.subplots(2, 1, sharex=True)
        unit = "mV" if amplitude_calibrated else "a.u."
        for axis, samples, label in ((raw, processed.raw, f"Raw ({unit})"),
                                     (filtered, processed.filtered, f"Filtered ({unit})")):
            axis.plot(time, samples[:count], color=TRACE, linewidth=0.65)
            _axes(axis, label, "" if axis is raw else "Time (s)", paper=amplitude_calibrated)
            axis.set_xlim(0, shown)
        plots["raw_filtered"] = _png(figure)

        figure = _figure()
        axis = figure.subplots()
        before = 10 * np.log10(np.maximum(processed.raw_power, 1e-15))
        after = 10 * np.log10(np.maximum(processed.filtered_power, 1e-15))
        axis.plot(processed.frequencies, before, color="#888888", linewidth=0.6, label="Before filtering")
        axis.plot(processed.frequencies, after, color=NAVY, linewidth=0.9, label="After filtering")
        if processed.notch_hz:
            axis.axvline(processed.notch_hz, color=TRACE, linestyle="--", linewidth=0.7,
                         label=f"Mains ({processed.notch_hz:g} Hz)")
        _axes(axis, f"PSD (dB re 1 {unit}²/Hz)", "Frequency (Hz)")
        axis.set_xlim(0, min(processed.fs / 2, 80))
        ceiling = float(max(before.max(), after.max())) + 5
        axis.set_ylim(ceiling - 105, ceiling)
        axis.legend(fontsize=9, frameon=False)
        plots["spectrum"] = _png(figure)

        figure = _figure()
        axis = figure.subplots()
        axis.plot(time, processed.filtered[:count], color=TRACE, linewidth=0.65)
        visible = peaks[(peaks >= 0) & (peaks < count)]
        axis.scatter(visible / processed.fs, processed.filtered[visible], s=15,
                     facecolors="#e00000", edgecolors="#e00000", linewidths=0, zorder=4)
        _axes(axis, f"Filtered ({unit})", paper=amplitude_calibrated)
        axis.set_xlim(0, shown)
        plots["r_peaks"] = _png(figure)

        figure = _figure()
        axis = figure.subplots()
        if peaks.size >= 2:
            axis.plot(peaks[1:] / processed.fs, np.diff(peaks) / processed.fs * 1000,
                      color=NAVY, linewidth=0.8, marker="o", markersize=2.5)
        _axes(axis, "RR interval (ms)")
        axis.set_xlim(0, processed.raw.size / processed.fs)
        plots["rr_tachogram"] = _png(figure)
        return plots


def for_signal(signal: Signal, measurements: dict, notch_hz=50, *, amplitude_calibrated=True) -> dict[str, str]:
    processed = preprocess(signal, notch_hz=notch_hz)
    peaks = np.rint(np.asarray(measurements["r_peak_times_s"]) * processed.fs).astype(int)
    return render_plots(processed, peaks, amplitude_calibrated=amplitude_calibrated)


def encode_image(rgb: np.ndarray) -> str:
    """Prefer lossless plots, bound photographic previews without new dependencies."""
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok, image = cv2.imencode(".png", bgr, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    if not ok:
        raise ValueError("Image could not be encoded.")
    if image.size > 750_000:
        for quality in (90, 80, 70, 60):
            ok, image = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if image.size <= 750_000:
                break
    return base64.b64encode(image.tobytes()).decode("ascii")


def trace_overlay(rgb: np.ndarray, recovered, measurement_image=None) -> str:
    """Place the recovered trace on the full prepared page, one pixel wide."""
    # The frozen digitizer's overlay contains the exact column positions. Retain
    # those positions but omit its crop rectangle and use a contrasting trace.
    original = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    debug = cv2.imdecode(np.frombuffer(recovered.debug_overlay, np.uint8), cv2.IMREAD_COLOR)
    green = (debug[:, :, 1].astype(int) > debug[:, :, 0].astype(int) + 35) & (debug[:, :, 1].astype(int) > debug[:, :, 2].astype(int) + 35)
    if measurement_image is not None:
        green &= np.any(debug != cv2.cvtColor(measurement_image, cv2.COLOR_RGB2BGR), axis=2)
    original[green] = (190, 70, 0)
    return encode_image(cv2.cvtColor(original, cv2.COLOR_BGR2RGB))
