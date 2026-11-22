"""Download only the requested MIT-BIH records, reusing complete local files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecg.config import DATA_DIR, VALIDATION_RECORDS


def download() -> None:
    import wfdb

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    missing = [record for record in VALIDATION_RECORDS
               if any(not (DATA_DIR / f"{record}.{ext}").exists()
                      for ext in ("dat", "hea", "atr"))]
    if not missing:
        print("All requested MIT-BIH records already exist; no download.")
        return
    # Fetch the exact files: dl_database also pre-reads every remote header,
    # which can fail before any file is saved when PhysioNet has a transient 502.
    files = [f"{record}.{ext}" for record in missing for ext in ("hea", "dat", "atr")
             if not (DATA_DIR / f"{record}.{ext}").exists()]
    wfdb.dl_files("mitdb", str(DATA_DIR), files=files,
                  keep_subdirs=False, overwrite=False)
    print("MIT-BIH download complete: " + ", ".join(missing))


if __name__ == "__main__":
    download()
