from __future__ import annotations

from itertools import product
from typing import Any

import numpy as np

from .materials import MaterialDatabase
from .models import Layer
from .templates import get_template
from .tmm_engine import run_tmm


def run_thickness_sweep(payload: dict[str, Any], material_db: MaterialDatabase) -> dict[str, Any]:
    layers = _layers_from_payload(payload)
    scan_specs = _scan_specs(payload, layers)
    if not scan_specs:
        raise ValueError("At least one active layer thickness range is required.")

    axes = []
    for spec in scan_specs[:2]:
        values = _range_values(spec["start_nm"], spec["stop_nm"], spec["step_nm"])
        axes.append({**spec, "values_nm": values})

    results = []
    for combo in product(*[axis["values_nm"] for axis in axes]):
        trial_layers = [layer.to_dict() for layer in layers]
        thickness_payload = {}
        for axis, value in zip(axes, combo):
            trial_layers[axis["layer_index"]]["thickness_nm"] = value
            thickness_payload[axis["layer_name"]] = float(value)
        result = run_tmm({**payload, "layers": trial_layers}, material_db)
        row = {
            **thickness_payload,
            "jsc_mA_cm2": result.get("jsc_mA_cm2", {}),
            "matched": float(result.get("matched_current_mA_cm2", result.get("jsc_mA_cm2", {}).get("matched", 0.0))),
            "sum_active": float(result.get("jsc_mA_cm2", {}).get("sum_active", 0.0)),
            "active_currents_mA_cm2": result.get("active_currents_mA_cm2", {}),
        }
        results.append(row)

    best = max(results, key=lambda item: item["matched"]) if results else None
    return {
        "method": "thickness_sweep",
        "scan_axes": axes,
        "results": results,
        "best": best,
    }


def _layers_from_payload(payload: dict[str, Any]) -> list[Layer]:
    if payload.get("layers"):
        return [Layer.from_dict(item) for item in payload["layers"]]
    return get_template(str(payload.get("template_id", "all_perovskite")))


def _scan_specs(payload: dict[str, Any], layers: list[Layer]) -> list[dict[str, Any]]:
    scan = payload.get("thickness_scan", {})
    provided = scan.get("layers", [])
    active_indices = [idx for idx, layer in enumerate(layers) if layer.active]
    if not provided:
        provided = [
            {
                "layer_name": layers[idx].name,
                "start_nm": max(1.0, layers[idx].thickness_value() - 50.0),
                "stop_nm": layers[idx].thickness_value() + 50.0,
                "step_nm": 25.0,
            }
            for idx in active_indices[:2]
        ]
    specs = []
    for item in provided:
        layer_name = str(item.get("layer_name", ""))
        layer_index = next((idx for idx, layer in enumerate(layers) if layer.name == layer_name), None)
        if layer_index is None and "layer_index" in item:
            layer_index = int(item["layer_index"])
        if layer_index is None or layer_index < 0 or layer_index >= len(layers):
            continue
        layer = layers[layer_index]
        specs.append(
            {
                "layer_index": layer_index,
                "layer_name": layer.name,
                "material": layer.material,
                "start_nm": float(item.get("start_nm", layer.thickness_value())),
                "stop_nm": float(item.get("stop_nm", layer.thickness_value())),
                "step_nm": float(item.get("step_nm", 10.0)),
            }
        )
    return specs


def _range_values(start: float, stop: float, step: float) -> list[float]:
    if step <= 0 or stop < start:
        raise ValueError("Invalid thickness scan range.")
    count = int(np.floor((stop - start) / step)) + 1
    return [float(start + i * step) for i in range(count)]
