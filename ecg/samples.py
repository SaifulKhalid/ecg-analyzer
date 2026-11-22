"""Local MIT-BIH demo catalog with deterministic synthetic offline alternatives."""

from . import config as cfg
from .preprocess import Signal
from .synth import generate_ecg

SYNTHETIC_DEMOS = {
    "synth-regular": {"label": "Synthetic • 72 bpm • regular timing", "hr": 72},
    "synth-brady": {"label": "Synthetic • 45 bpm • slow timing", "hr": 45},
    "synth-tachy": {"label": "Synthetic • 130 bpm • fast timing", "hr": 130},
    "synth-irregular": {"label": "Synthetic • varying RR timing", "hr": 75, "irregular": True},
}


def list_samples() -> list[dict]:
    catalog = []
    for record in cfg.VALIDATION_RECORDS:
        if all((cfg.DATA_DIR / f"{record}.{ext}").exists() for ext in ("hea", "dat", "atr")):
            catalog.append({"sample_id": f"mitdb-{record}", "label": f"MIT-BIH {record} • lead 0 • 60 s",
                            "source": "MIT-BIH", "duration_s": cfg.VALIDATION_SECONDS})
    catalog.extend({"sample_id": identifier, "label": spec["label"], "source": "synthetic",
                    "duration_s": cfg.SYNTH_DEFAULT_DURATION} for identifier, spec in SYNTHETIC_DEMOS.items())
    return catalog


def load_sample(sample_id: str) -> Signal:
    if sample_id in SYNTHETIC_DEMOS:
        specification = {key: value for key, value in SYNTHETIC_DEMOS[sample_id].items() if key != "label"}
        generated = generate_ecg(**specification, mains_amplitude=0.10, baseline_wander=0.15)
        generated.signal.metadata.update(sample_id=sample_id, label=SYNTHETIC_DEMOS[sample_id]["label"])
        return generated.signal
    allowed = {entry["sample_id"] for entry in list_samples() if entry["source"] == "MIT-BIH"}
    if sample_id not in allowed:
        raise ValueError("Unknown sample_id; choose a record returned by /samples.")
    import wfdb

    record_id = sample_id.removeprefix("mitdb-")
    path = str(cfg.DATA_DIR / record_id)
    header = wfdb.rdheader(path)
    record = wfdb.rdrecord(path, sampto=min(header.sig_len, int(cfg.VALIDATION_SECONDS * header.fs)), channels=[0])
    return Signal(record.p_signal[:, 0], record.fs,
                  {"source": "MIT-BIH", "sample_id": sample_id, "lead": record.sig_name[0],
                   "label": f"MIT-BIH {record_id}, {record.sig_name[0]}, first 60 s"})
