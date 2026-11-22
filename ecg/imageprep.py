"""Deterministic image normalization before selecting a measurement region."""

from dataclasses import dataclass
import io

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_LONG_SIDE = 3000
MAX_DECODE_PIXELS = 60_000_000


@dataclass
class PreparedImage:
    image: np.ndarray  # RGB, including the whole prepared page
    operations: list[dict]
    scale: float


def _ink(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    return ((gray < 160) & ((hsv[:, :, 1] < 105) | (gray < 110))).astype(np.uint8)


def _horizontal_score(image):
    mask = cv2.morphologyEx(_ink(image), cv2.MORPH_CLOSE, np.ones((1, 3), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    width = image.shape[1]
    return sum(float(w) for x, y, w, h, area in stats[1:]
               if w >= max(25, width * 0.04) and w > 2 * h and h >= 3 and area < w*h*0.65)


def _text_top_score(image):
    _, _, stats, centers = cv2.connectedComponentsWithStats(_ink(image))
    height, width = image.shape[:2]
    top = bottom = 0
    for (x, y, w, h, area), (_, center_y) in zip(stats[1:], centers[1:]):
        if 3 <= w <= width*0.035 and 4 <= h <= min(40, height*0.08) and area >= 6:
            if center_y < height*0.18:
                top += area
            elif center_y > height*0.82:
                bottom += area
    return top - bottom


def _skew_angle(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    colored = ((hsv[:, :, 1] > 20) & (hsv[:, :, 2] > 90)).astype(np.uint8)
    if not 0.002 < colored.mean() < 0.3:
        colored = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), 60, 160)
    lines = cv2.HoughLinesP(colored, 1, np.pi/1800, threshold=max(30, image.shape[1]//12),
                            minLineLength=max(40, image.shape[1]//6), maxLineGap=15)
    if lines is None:
        return 0.0
    angles = []
    for x0, y0, x1, y1 in lines[:, 0]:
        if x1 < x0:
            x0, y0, x1, y1 = x1, y1, x0, y0
        angle = float(np.degrees(np.arctan2(y1-y0, x1-x0)))
        if abs(angle) <= 15:
            angles.append(angle)
    if len(angles) < 6:
        return 0.0
    median = float(np.median(angles))
    if np.median(np.abs(np.asarray(angles)-median)) > 0.5 or abs(median) < 0.15:
        return 0.0
    return round(median, 2)


def _deskew(image, angle):
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width/2, height/2), angle, 1)
    cosine, sine = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_width = int(np.ceil(height*sine + width*cosine))
    new_height = int(np.ceil(height*cosine + width*sine))
    matrix[0, 2] += (new_width-width)/2
    matrix[1, 2] += (new_height-height)/2
    return cv2.warpAffine(image, matrix, (new_width, new_height), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def prepare_image(image_bytes: bytes, *, automatic_orientation=True) -> PreparedImage:
    operations = []
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            if opened.width*opened.height > MAX_DECODE_PIXELS:
                raise ValueError("Image dimensions exceed the preparation limit.")
            orientation = opened.getexif().get(274, 1)
            picture = ImageOps.exif_transpose(opened)
            if orientation != 1:
                degrees = {3: 180, 6: 270, 8: 90}.get(orientation)
                operations.append({"name": "rotation", "degrees": degrees, "source": "EXIF"} if degrees else
                                  {"name": "exif_orientation", "value": orientation})
            mode = picture.mode
            if mode in ("RGBA", "LA") or (mode == "P" and "transparency" in picture.info):
                foreground = picture.convert("RGBA")
                background = Image.new("RGBA", foreground.size, "white")
                picture = Image.alpha_composite(background, foreground).convert("RGB")
                operations.append({"name": "alpha_flattened", "background": "white"})
            else:
                picture = picture.convert("RGB")
            if mode != "RGB":
                operations.append({"name": "rgb_conversion", "from": mode})
            image = np.array(picture)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("The image could not be decoded.") from error

    if automatic_orientation and min(image.shape[:2]) >= 80:
        # Analyze a small copy; apply the resulting operation to the full image.
        ratio = min(1, 1200/max(image.shape[:2]))
        probe = cv2.resize(image, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA) if ratio < 1 else image
        quarter_turns = 1 if _horizontal_score(np.rot90(probe)) > _horizontal_score(probe)*1.4 + 40 else 0
        rotated = np.rot90(probe, quarter_turns)
        if _text_top_score(rotated) < -40:
            quarter_turns += 2
        if quarter_turns:
            image = np.ascontiguousarray(np.rot90(image, quarter_turns))
            operations.append({"name": "rotation", "degrees": quarter_turns*90, "source": "layout"})
        ratio = min(1, 1500/max(image.shape[:2]))
        probe = cv2.resize(image, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA) if ratio < 1 else image
        angle = _skew_angle(probe)
        if angle:
            image = _deskew(image, angle)
            operations.append({"name": "deskew", "degrees": angle})
    scale = min(1, MAX_LONG_SIDE/max(image.shape[:2]))
    if scale < 1:
        width, height = round(image.shape[1]*scale), round(image.shape[0]*scale)
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        operations.append({"name": "downscale", "factor": scale, "size": [width, height]})
    return PreparedImage(np.ascontiguousarray(image), operations, scale)
