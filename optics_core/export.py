from __future__ import annotations

import io

import pandas as pd


def result_to_csv(result: dict) -> str:
    wl = result.get("wavelength_nm", [])
    data = {"wavelength_nm": wl}
    if "reflection" in result:
        data["reflection"] = result["reflection"]
    if "transmission" in result:
        data["transmission"] = result["transmission"]
    for layer in result.get("layers", []):
        name = str(layer.get("name") or layer.get("material") or "layer")
        values = layer.get("absorption", [])
        if len(values) == len(wl):
            data[f"absorption_{name}"] = values
    buffer = io.StringIO()
    for key, value in _metadata_rows(result):
        buffer.write(f"# {key},{value}\n")
    pd.DataFrame(data).to_csv(buffer, index=False)
    return buffer.getvalue()


def _metadata_rows(result: dict) -> list[tuple[str, str]]:
    rows = []
    for key in ("method", "geometry", "shape", "model_note"):
        if key in result:
            rows.append((key, str(result[key])))
    periodic = result.get("periodic_parameters")
    if isinstance(periodic, dict):
        for key in ("shape", "pitch", "height", "duty_cycle", "nG", "slices", "t_wbg", "t_nbg"):
            if key in periodic:
                rows.append((f"periodic_{key}", str(periodic[key])))
    return rows
