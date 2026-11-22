"""FastAPI measured ECG service; Node keeps serving the existing frontend."""

from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, model_validator

from . import __version__, config as cfg
from .pipeline import analyze_signal
from .preprocess import Signal
from .samples import list_samples, load_sample

app = FastAPI(title="Measured ECG screening", version=__version__, description=cfg.DISCLAIMER)


class SignalRequest(BaseModel):
    fs: float | None = None
    samples: list[float] | None = None
    sample_id: str | None = None
    explain: bool = True
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
        return analyze_signal(signal, explain=body.explain, notch_hz=body.notch_hz)
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ecg.api:app", host=cfg.API_HOST, port=cfg.API_PORT)
