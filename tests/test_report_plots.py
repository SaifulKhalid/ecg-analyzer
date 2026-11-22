import base64
import io

import numpy as np
from PIL import Image

from ecg import report_plots
from ecg.peaks import detect_r_peaks
from ecg.preprocess import preprocess
from ecg.synth import generate_ecg


def test_report_axes_have_units_without_titles_and_physical_grid(monkeypatch):
    processed = preprocess(generate_ecg(72).signal)
    peaks = detect_r_peaks(processed.filtered, processed.fs)
    figures = []
    monkeypatch.setattr(report_plots, "_png", lambda figure: figures.append(figure) or "image")
    try:
        result = report_plots.render_plots(processed, peaks)
        assert set(result) == {"raw_filtered", "spectrum", "r_peaks", "rr_tachogram"}
        assert all(figure.dpi == 200 for figure in figures)
        assert all(axis.get_title() == "" and axis.get_title(loc="left") == "" for figure in figures for axis in figure.axes)
        assert [axis.get_ylabel() for axis in figures[0].axes] == ["Raw (mV)", "Filtered (mV)"]
        assert figures[0].axes[1].get_xlabel() == "Time (s)"
        assert figures[3].axes[0].get_ylabel() == "RR interval (ms)"
        assert figures[1].axes[0].get_ylim()[1] - figures[1].axes[0].get_ylim()[0] == 105
        marker = figures[2].axes[0].collections[0]
        assert np.allclose(marker.get_facecolors()[0, :3], [224/255, 0, 0])
    finally:
        for figure in figures:
            figure.clear()


def test_encoded_report_contains_red_peak_markers_at_200_dpi():
    processed = preprocess(generate_ecg(72).signal)
    plots = report_plots.render_plots(processed, detect_r_peaks(processed.filtered, processed.fs))
    with Image.open(io.BytesIO(base64.b64decode(plots["r_peaks"]))) as picture:
        assert abs(picture.info["dpi"][0] - 200) < 0.1
        pixels = np.array(picture.convert("RGB"))
        assert np.count_nonzero((pixels[:, :, 0] > 190) & (pixels[:, :, 1] < 30) & (pixels[:, :, 2] < 30)) > 50
