"""CLDD_DATA_DIR is the only data-location knob: no author-machine fallback
(design register D4, 2026-11-03), and no such path ships in the package."""
from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_load_real_without_env_names_the_knob(monkeypatch):
    monkeypatch.delenv("CLDD_DATA_DIR", raising=False)
    code = (
        "import cldd.fidelity as f\n"
        "assert f.DEFAULT_DATA_DIR is None, f.DEFAULT_DATA_DIR\n"
        "try:\n"
        "    f.load_real()\n"
        "except FileNotFoundError as exc:\n"
        "    assert 'CLDD_DATA_DIR' in str(exc), exc\n"
        "    print('ok')\n"
        "else:\n"
        "    raise SystemExit('load_real() found data with no knob set')\n"
    )
    env = {k: v for k, v in __import__("os").environ.items() if k != "CLDD_DATA_DIR"}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"


def test_built_archives_carry_no_author_path(tmp_path):
    """Build the sdist and wheel from this tree and scan every member.

    Needs more than the rest of the suite, so it is stated here: the ``build``
    package (``python -m build``) and network access, because build isolation
    fetches ``setuptools>=77`` and ``wheel`` from PyPI.
    It takes about 11 s locally, and the sdist step rewrites the gitignored
    ``src/closed_loop_default_detection.egg-info`` in the source tree. An offline
    run deselects it with ``-k "not built_archives"``. It is never skipped
    automatically, so CI cannot pass the D4 check vacuously.
    """
    out = tmp_path / "dist"
    build = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(out), str(ROOT)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert build.returncode == 0, (
        "python -m build failed; it needs the build package and network access "
        "(see this test's docstring)\n" + build.stdout[-2000:] + build.stderr[-2000:]
    )
    archives = sorted(out.iterdir())
    assert len(archives) == 2, archives
    # The sdist ships tests/, so two needles are spelled in parts: this file must
    # not match itself. The bytes searched for are unchanged.
    needles = (b"C:" + b"/Users", b"Users" + b"/hossa", b"C:\\Users")
    hits = []
    for a in archives:
        if a.suffix == ".whl":
            with zipfile.ZipFile(a) as z:
                for m in z.namelist():
                    data = z.read(m)
                    if any(n in data for n in needles):
                        hits.append(f"{a.name}:{m}")
        else:
            with tarfile.open(a) as t:
                for m in t.getmembers():
                    if not m.isfile():
                        continue
                    data = t.extractfile(m).read()
                    if any(n in data for n in needles):
                        hits.append(f"{a.name}:{m.name}")
    assert not hits, f"author-machine path ships in the package: {hits}"
    sdist = [a for a in archives if a.suffix == ".gz"][0]
    with tarfile.open(sdist) as t:
        names = t.getnames()
    assert not any("/preregistration/" in n for n in names), "texts are repo documents, not package files"


def test_gate_report_records_the_resolved_dir(monkeypatch, tmp_path):
    """With data_dir omitted, the report's data_dir line names the CLDD_DATA_DIR
    location the gate actually read, not the string "None"."""
    import pandas as pd

    import cldd.fidelity as f

    monkeypatch.setattr(f, "DEFAULT_DATA_DIR", tmp_path)
    pd.DataFrame({"x": [1]}).to_csv(tmp_path / "train.csv", index=False)
    monkeypatch.setattr(f, "load_synthetic", lambda **kw: {})
    monkeypatch.setattr(f, "compute_fidelity", lambda real, cohort, **kw: f.FidelityReport())
    report = f.run_fidelity_gate()
    assert report.data_dir == str(tmp_path)
    assert f"data_dir: {tmp_path}" in report.to_table()
