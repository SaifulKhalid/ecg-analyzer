"""Deterministic, physically scaled report fixtures with independently known HR."""

from dataclasses import dataclass
import io

import cv2
import numpy as np
from PIL import Image

from ecg.synth import generate_ecg

LEADS = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")
GRID_COLORS = {
    "pink": ((255, 222, 230), (233, 165, 180)),
    "red": ((255, 220, 220), (235, 160, 160)),
    "green": ((221, 246, 225), (165, 213, 176)),
    "blue": ((221, 234, 255), (165, 188, 228)),
}


@dataclass
class ReportFixture:
    image: bytes
    hr: float
    target_box: list[int] | None
    parameters: dict


def render_report(*, hr=72.0, ppm=6, rhythm=True, layout="3x4", grid="pink", grayscale=False,
                  rotation=0, skew=0, jpeg_quality=None, photo=False, seed=1) -> ReportFixture:
    columns = 4 if layout == "3x4" else 1
    rows = 12 if layout == "12x1" else 3
    width = round(270*ppm)
    header = round(22*ppm)
    step = round(32*ppm)
    height = header + step*(rows+int(rhythm)) + round(8*ppm)
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    left, right = round(10*ppm), round(260*ppm)
    if grid:
        minor, major = GRID_COLORS[grid]
        for x in np.arange(0, width, ppm):
            index = round(x/ppm)
            cv2.line(image, (round(x), header), (round(x), height-1), major if index%5 == 0 else minor, 1)
        for y in np.arange(header, height, ppm):
            index = round((y-header)/ppm)
            cv2.line(image, (0, round(y)), (width-1, round(y)), major if index%5 == 0 else minor, 1)
    font_scale = max(0.35, ppm*0.075)
    cv2.putText(image, "ELECTROCARDIOGRAM", (left, round(8*ppm)), cv2.FONT_HERSHEY_SIMPLEX, font_scale*1.25, (20, 20, 20), 1, cv2.LINE_AA)
    cv2.putText(image, "Record: 0001    Date: 2026-11-23    25 mm/s    10 mm/mV", (left, round(16*ppm)), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (20, 20, 20), 1, cv2.LINE_AA)
    generated = generate_ecg(hr, fs=500, duration=10, noise=0, baseline_wander=0, seed=seed)
    times = np.arange(generated.signal.samples.size)/500
    beats = generated.r_peaks/500

    def signal(lead):
        values = generated.signal.samples.copy() * (0.7 + (lead%5)*0.12)
        # Leads have different T-wave amplitudes, widths and QRS smoothing.
        for beat in beats:
            values += (0.12*((lead%3)-1))*np.exp(-0.5*((times-beat-0.27)/(0.055+0.01*(lead%4)))**2)
        if lead%3 == 1:
            values = cv2.GaussianBlur(values[None, :], (5, 1), 1.1)[0]
        return -values if lead == 3 else values

    def draw_strip(x0, x1, baseline, lead, start=0, duration=10):
        positions = np.arange(x0, x1)
        t = start + np.arange(positions.size)/(25*ppm)
        samples = np.interp(t, times, signal(lead))
        ys = np.rint(baseline-samples*10*ppm).astype(int)
        points = np.column_stack((positions, ys)).astype(np.int32)
        cv2.polylines(image, [points.reshape(-1, 1, 2)], False, (12, 12, 12), max(1, round(ppm/5)), cv2.LINE_AA)
        return [x0, int(ys.min())-4, x1, int(ys.max())+5]

    target = None
    for row in range(rows):
        baseline = header + row*step + round(20*ppm)
        for column in range(columns):
            lead = row*columns+column if layout != "3-channel" else row
            cell_left = left + round((right-left)*column/columns)
            cell_right = left + round((right-left)*(column+1)/columns)
            gap = round(2*ppm) if columns > 1 else 0
            draw_strip(cell_left+gap, cell_right-gap, baseline, lead, column*2.5 if columns > 1 else 0)
            cv2.putText(image, LEADS[lead%12], (cell_left+round(2*ppm), baseline-round(12*ppm)), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (15, 15, 15), 1, cv2.LINE_AA)
            if column:
                cv2.line(image, (cell_left, baseline-round(3*ppm)), (cell_left, baseline+round(3*ppm)), (20, 20, 20), 1)
        # Leading calibration pulse, separated from trace and lead text.
        pulse = np.array([[round(ppm), baseline], [round(2*ppm), baseline], [round(2*ppm), baseline-round(10*ppm)],
                          [round(6*ppm), baseline-round(10*ppm)], [round(6*ppm), baseline], [round(8*ppm), baseline]], np.int32)
        cv2.polylines(image, [pulse.reshape(-1, 1, 2)], False, (12, 12, 12), 1)
    if rhythm:
        baseline = header + rows*step + round(20*ppm)
        target = draw_strip(left, right, baseline, 1)
        cv2.putText(image, "II", (left, baseline-round(12*ppm)), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (15, 15, 15), 1, cv2.LINE_AA)
        pulse = np.array([[round(ppm), baseline], [round(2*ppm), baseline], [round(2*ppm), baseline-round(10*ppm)],
                          [round(6*ppm), baseline-round(10*ppm)], [round(6*ppm), baseline], [round(8*ppm), baseline]], np.int32)
        cv2.polylines(image, [pulse.reshape(-1, 1, 2)], False, (12, 12, 12), 1)
    elif columns == 1:
        target = [left, header+(rows-1)*step+round(7*ppm), right, header+rows*step]
    if photo:
        rng = np.random.default_rng(seed)
        illumination = np.linspace(-20, 2, width)[None, :, None]
        image = np.clip(image.astype(float)+illumination+rng.normal(0, 2.5, image.shape), 0, 255).astype(np.uint8)
    if grayscale:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        image = np.repeat(gray[:, :, None], 3, axis=2)
    picture = Image.fromarray(image)
    if rotation:
        picture = picture.rotate(rotation, expand=True, fillcolor="white")
        target = None  # Validator maps regions in the prepared coordinate frame.
    if skew:
        picture = picture.rotate(skew, expand=True, resample=Image.Resampling.BICUBIC, fillcolor="white")
        target = None
    buffer = io.BytesIO()
    picture.save(buffer, format="JPEG" if jpeg_quality else "PNG", **({"quality": jpeg_quality} if jpeg_quality else {}))
    parameters = dict(hr=hr, ppm=ppm, rhythm=rhythm, layout=layout, grid=grid, grayscale=grayscale,
                      rotation=rotation, skew=skew, jpeg_quality=jpeg_quality, photo=photo, seed=seed)
    return ReportFixture(buffer.getvalue(), generated.true_hr, target, parameters)


def variants():
    cases = []
    for index in range(24):
        cases.append(dict(hr=(48, 60, 72, 85, 105, 120)[index%6], ppm=(4, 6, 8)[index%3],
                          grid=("pink", "red", "green", "blue")[index%4], seed=100+index,
                          grayscale=index in (5, 13), rotation=90 if index == 7 else 180 if index == 15 else 270 if index == 19 else 0,
                          skew=3 if index in (6, 18) else 0, jpeg_quality=60 if index in (3, 11, 21) else None,
                          photo=index in (9, 17, 23)))
    cases.extend([dict(rhythm=False, layout="3x4", ppm=ppm, grid=grid, seed=200+i)
                  for i, (ppm, grid) in enumerate([(4,"pink"),(6,"blue"),(8,"green"),(6,"red")])])
    cases.extend([dict(rhythm=False, layout=layout, ppm=6, seed=300+i)
                  for i, layout in enumerate(["12x1", "3-channel"])])
    cases.extend([dict(grid=None, grayscale=True, seed=401), dict(grid=None, grayscale=True, rhythm=False, seed=402)])
    return cases
