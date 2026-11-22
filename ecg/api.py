"""FastAPI measured ECG service; Node keeps serving the existing frontend."""

from typing import Literal
import json
import logging

import numpy as np
import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, model_validator

from . import __version__, config as cfg
from .pipeline import analyze_signal
from .preprocess import Signal
from .samples import list_samples, load_sample
from . import report_plots
from .imageprep import prepare_image
from .layout import select_region, unmeasured_result
from . import report

app = FastAPI(title="Measured ECG screening", version=__version__, description=cfg.DISCLAIMER)


class SignalRequest(BaseModel):
    fs: float | None = None
    samples: list[float] | None = None
    sample_id: str | None = None
    explain: bool = True
    allow_provider_default_temperature: bool = False
    notch_hz: Literal[50, 60] | None = cfg.NOTCH_HZ

    @model_validator(mode="after")
    def one_source(self):
        if self.sample_id is not None:
            if self.samples is not None or self.fs is not None:
                raise ValueError("Choose sample_id OR fs plus samples, not both.")
        elif self.samples is None or self.fs is None:
            raise ValueError("Provide sample_id OR both fs and samples.")
        if self.samples is not None and len(self.samples) > cfg.MAX_INPUT_FS * cfg.MAX_SIGNAL_SECONDS:
            raise ValueError("Too many samples; maximum duration is 300 seconds.")
        return self


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "target_fs_hz": cfg.FS_TARGET,
            "disclaimer": cfg.DISCLAIMER}


@app.get("/samples")
def samples() -> list[dict]:
    return list_samples()


@app.post("/analyze-signal")
def analyze_signal_endpoint(body: SignalRequest) -> dict:
    try:
        signal = load_sample(body.sample_id) if body.sample_id is not None else Signal(
            np.asarray(body.samples, dtype=float), float(body.fs), {"source": "uploaded signal"})
        result = analyze_signal(signal, explain=body.explain, include_plots=False, notch_hz=body.notch_hz,
                                allow_provider_default_temperature=body.allow_provider_default_temperature)
        result["plots"] = report_plots.for_signal(signal, result["measurements"], body.notch_hz)
        return result
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/analyze")
def analyze_image_endpoint(image: UploadFile = File(...), pixels_per_mm: float | None = Form(None),
                           paper_speed: float = Form(cfg.PAPER_SPEED_MM_S), gain: float = Form(cfg.GAIN_MM_MV),
                           crop_box: str | None = Form(None), explain: bool = Form(True),
                           allow_provider_default_temperature: bool = Form(False),
                           notch_hz: int = Form(int(cfg.NOTCH_HZ))) -> dict:
    try:
        bounds = json.loads(crop_box) if crop_box and crop_box.strip() else None
        if bounds is not None and (not isinstance(bounds, list) or len(bounds) != 4 or any(type(value) is not int for value in bounds)):
            raise ValueError("crop_box must contain four integer pixel bounds.")
        if notch_hz not in (50, 60):
            raise ValueError("notch_hz must be 50 or 60.")
        if any(not np.isfinite(value) or value <= 0 for value in [paper_speed, gain] + ([] if pixels_per_mm is None else [pixels_per_mm])):
            raise ValueError("Calibration values must be positive finite numbers.")
        image_bytes = image.file.read(cfg.MAX_IMAGE_BYTES + 1)
        if not image_bytes or len(image_bytes) > cfg.MAX_IMAGE_BYTES:
            raise ValueError("Choose a non-empty image under 10 MB.")
        prepared = prepare_image(image_bytes, automatic_orientation=bounds is None)
        height, width = prepared.image.shape[:2]
        if bounds is not None:
            bounds = [round(value*prepared.scale) for value in bounds]
            if not (0 <= bounds[0] < bounds[2] <= width and 0 <= bounds[1] < bounds[3] <= height):
                raise ValueError("crop_box must stay inside the image and have positive width / height.")
        selection = select_region(prepared.image, pixels_per_mm=None if pixels_per_mm is None else pixels_per_mm*prepared.scale,
                                  paper_speed=paper_speed, gain=gain, crop_box=bounds, notch_hz=notch_hz)
        result = selection.result
        result["disclaimer"] = cfg.DISCLAIMER
        notes = list(result.get("notes", []))
        if selection.candidate is not None:
            notes.append("Region set manually." if bounds is not None else f"Region selected automatically: {selection.candidate.kind}.")
        for operation in prepared.operations:
            if operation["name"] == "rotation":
                notes.append(f"Image rotated {operation['degrees']} deg.")
            elif operation["name"] == "deskew":
                notes.append(f"Image deskewed {operation['degrees']:g} deg.")
        result["notes"] = list(dict.fromkeys([*notes, *selection.notes]))
        result["region_selection"] = {"mode": "manual" if bounds is not None else "automatic",
            "kind": selection.candidate.kind if selection.candidate else None,
            "box": selection.candidate.box if selection.candidate else None,
            "image_size": [width, height], "operations": prepared.operations,
            "reason": "Quality gate passed; ranked by strip kind, SNR, beat count and vertical position." if result["status"] == "ok" else
                      "No candidate passed the quality gate; retained the available region with the most beats.",
            "candidates": selection.candidates}
        if selection.recovered is not None:
            result["plots"] = report_plots.for_signal(selection.recovered.signal, result["measurements"], notch_hz,
                                                     amplitude_calibrated=selection.amplitude_calibrated)
            result["plots"]["digitization"] = report_plots.trace_overlay(prepared.image, selection.recovered, selection.measurement_image)
        result["plots"]["prepared_image"] = report_plots.encode_image(prepared.image)
        # Selection never calls the provider. Preserve the existing optional
        # explanation contract only after the final region passes its gate.
        if explain and result["status"] == "ok":
            response = report.explain_measurements(result, allow_provider_default_temperature=True) if allow_provider_default_temperature else report.explain_measurements(result)
            result["explanation"] = response["explanation"]
            result["explanation_error"] = response.get("error")
            for source_key, target_key in (("model", "explanation_model"), ("explanation_settings", "explanation_settings"), ("explanation_grounding", "explanation_grounding")):
                if response.get(source_key):
                    result[target_key] = response[source_key]
            if response.get("error"):
                result["warnings"].append(response["error"])
            if response.get("explanation_settings", {}).get("used_provider_default"):
                result["warnings"].append("Explanation used the provider default temperature after 0.2 was rejected.")
        return result
    except (ValueError, OSError, TypeError, cv2.error) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception:
        # Valid but unsupported images always have a structured, plain response.
        logging.getLogger(__name__).exception("Image preparation failed")
        result = unmeasured_result("Image could not be prepared for measurement.")
        result["disclaimer"] = cfg.DISCLAIMER
        result["region_selection"] = {"mode": "manual" if crop_box else "automatic", "kind": None, "box": None,
                                     "operations": [], "reason": result["notes"][0], "candidates": []}
        return result
    finally:
        image.file.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ecg.api:app", host=cfg.API_HOST, port=cfg.API_PORT)
