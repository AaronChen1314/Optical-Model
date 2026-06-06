from __future__ import annotations

import ast
import math
import re
from typing import Any

import numpy as np
from scipy.signal import savgol_filter

from .materials import MaterialDatabase
from .models import Layer
from .templates import get_template
from .tmm_engine import run_tmm

ALLOWED_NAMES = {"T", "T_ref", "pi", "e"}
ALLOWED_FUNCS = {
    "sqrt": math.sqrt,
    "log": math.log,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
}


def run_temperature_sweep(payload: dict[str, Any], material_db: MaterialDatabase) -> dict[str, Any]:
    layers = payload.get("layers", [])
    temperature = payload.get("temperature", {})
    temps = [float(t) for t in temperature.get("temperatures_K", [280, 300, 320])]
    t_ref = float(temperature.get("reference_K", 300))
    formula = str(temperature.get("eg_formula", "Eg(T)=1.64 - 0.00025*(T-300)"))
    target_materials = set(temperature.get("target_materials", ["perovskite_164", "si_crystalline"]))

    if layers:
        baseline_layers = [Layer.from_dict(item).to_dict() for item in layers]
    else:
        baseline_layers = [layer.to_dict() for layer in get_template(str(payload.get("template_id", "all_perovskite")))]
    active_layers = [Layer.from_dict(item) for item in baseline_layers if Layer.from_dict(item).active]
    bandgap_models = _bandgap_models_for_layers(active_layers, temperature, payload.get("template_id", "all_perovskite_planar_reference"), material_db)
    eg_ref = evaluate_eg(formula, t_ref, t_ref)
    runs = []
    optical_constants = []
    jsc_vs_temperature = []
    for temp in temps:
        eg = evaluate_eg(formula, temp, t_ref)
        if bandgap_models:
            adjusted = _make_adjusted_db_from_models(material_db, bandgap_models, temp)
        else:
            adjusted = _make_adjusted_db(material_db, target_materials, temp, t_ref, eg - eg_ref)
        temp_payload = dict(payload)
        temp_payload["layers"] = baseline_layers
        result = run_tmm(temp_payload, adjusted)
        eg_by_layer = {
            model["layer_name"]: bandgap_at_temperature(model, temp)
            for model in bandgap_models
        } if bandgap_models else {}
        runs.append({"temperature_K": temp, "eg_eV": eg, "eg_by_layer": eg_by_layer, "result": result})
        jsc_vs_temperature.append(
            {
                    "temperature_K": temp,
                    "eg_eV": eg,
                    "eg_by_layer": eg_by_layer,
                    **{name: float(value) for name, value in result.get("jsc_mA_cm2", {}).items()},
                }
        )
        for layer in active_layers:
            resolved = adjusted.resolve_id(layer.material)
            if resolved not in adjusted.materials:
                continue
            material = adjusted.materials[resolved]
            edge_idx = estimate_absorption_edge_index(material.wavelength_nm, material.k)
            band_edge_nm = float(material.wavelength_nm[edge_idx])
            optical_constants.append(
                {
                    "temperature_K": temp,
                    "material": resolved,
                    "layer_name": layer.name,
                    "eg_eV": eg_by_layer.get(layer.name, eg),
                    "wavelength_nm": [float(x) for x in material.wavelength_nm],
                    "n": [float(x) for x in material.n],
                    "k": [float(x) for x in material.k],
                    "quantity": "n+k",
                    "visible_default": True,
                    "valid_wavelength_range_nm": [float(np.min(material.wavelength_nm)), float(np.max(material.wavelength_nm))],
                    "band_edge_nm": band_edge_nm,
                    "nk_model_notes": "Band-edge-local k shift with tapered transparent-tail smoothing and clipped local KK n correction.",
                    "temperature_adjusted": True,
                }
            )
    return {
        "method": "temperature_sweep",
        "reference_K": t_ref,
        "eg_formula": formula,
        "bandgap_models": bandgap_models,
        "runs": runs,
        "optical_constants": optical_constants,
        "jsc_vs_temperature": jsc_vs_temperature,
    }


def _bandgap_models_for_layers(active_layers: list[Layer], temperature: dict[str, Any], template_id: str, material_db: MaterialDatabase) -> list[dict[str, Any]]:
    provided = temperature.get("bandgap_models")
    if provided:
        return [
            {
                "layer_name": str(item.get("layer_name") or item.get("name") or ""),
                "material": material_db.resolve_id(str(item.get("material") or "")),
                "Eg_ref_eV": float(item.get("Eg_ref_eV", item.get("eg_ref_eV", 1.5))),
                "alpha_eV_per_K": float(item.get("alpha_eV_per_K", item.get("alpha", -2.5e-4))),
                "reference_K": float(item.get("reference_K", temperature.get("reference_K", 300))),
            }
            for item in provided
            if item.get("layer_name") or item.get("material")
        ]
    defaults = default_bandgap_models(active_layers, str(template_id), material_db, float(temperature.get("reference_K", 300)))
    if temperature.get("eg_formula"):
        return defaults
    return defaults


def default_bandgap_models(active_layers: list[Layer], template_id: str, material_db: MaterialDatabase, reference_K: float = 300.0) -> list[dict[str, Any]]:
    models = []
    for layer in active_layers:
        material = material_db.resolve_id(layer.material)
        lower_name = layer.name.lower()
        if template_id == "perovskite_silicon":
            if material == "si_crystalline":
                eg_ref, alpha = 1.124, -2.68e-4
            else:
                eg_ref, alpha = 1.650, 5.95e-4
        else:
            if "nbg" in lower_name or material == "nbg_perovskite":
                eg_ref, alpha = 1.25, -2.5e-4
            else:
                eg_ref, alpha = 1.75, -2.5e-4
        models.append(
            {
                "layer_name": layer.name,
                "material": material,
                "Eg_ref_eV": eg_ref,
                "alpha_eV_per_K": alpha,
                "reference_K": reference_K,
            }
        )
    return models


def bandgap_at_temperature(model: dict[str, Any], temperature_K: float) -> float:
    return float(model["Eg_ref_eV"]) + float(model["alpha_eV_per_K"]) * (float(temperature_K) - float(model.get("reference_K", 300.0)))


def _make_adjusted_db_from_models(base_db: MaterialDatabase, models: list[dict[str, Any]], temp: float) -> MaterialDatabase:
    adjusted = MaterialDatabase()
    adjusted.materials = dict(base_db.materials)
    for model in models:
        resolved = base_db.resolve_id(model["material"])
        if resolved not in base_db.materials:
            continue
        delta_eg = bandgap_at_temperature(model, temp) - bandgap_at_temperature(model, float(model.get("reference_K", 300.0)))
        material = base_db.materials[resolved]
        adjusted.materials[resolved] = _shift_material(material, temp, model.get("reference_K", 300.0), delta_eg)
    return adjusted


def evaluate_eg(formula: str, temperature: float, reference: float = 300.0) -> float:
    expression = formula.strip()
    if "=" in expression:
        expression = expression.split("=", 1)[1]
    expression = expression.replace("^", "**")
    expression = re.sub(r"\\mathrm\{([^}]+)\}", r"\1", expression)
    expression = expression.replace("\\", "")
    node = ast.parse(expression, mode="eval")
    _validate_ast(node)
    return float(eval(compile(node, "<Eg(T)>", "eval"), {"__builtins__": {}}, {**ALLOWED_FUNCS, "T": temperature, "T_ref": reference, "pi": math.pi, "e": math.e}))


def _validate_ast(node: ast.AST) -> None:
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Call,
    )
    for child in ast.walk(node):
        if not isinstance(child, allowed):
            raise ValueError("Formula contains unsupported syntax.")
        if isinstance(child, ast.Name) and child.id not in ALLOWED_NAMES and child.id not in ALLOWED_FUNCS:
            raise ValueError(f"Unsupported symbol in formula: {child.id}")
        if isinstance(child, ast.Call):
            if not isinstance(child.func, ast.Name) or child.func.id not in ALLOWED_FUNCS:
                raise ValueError("Formula contains unsupported function call.")


def _make_adjusted_db(base_db: MaterialDatabase, target_materials: set[str], temp: float, t_ref: float, delta_eg: float) -> MaterialDatabase:
    adjusted = MaterialDatabase()
    adjusted.materials = dict(base_db.materials)
    for material_id in target_materials:
        resolved = base_db.resolve_id(material_id)
        if resolved not in base_db.materials:
            continue
        adjusted.materials[resolved] = _shift_material(base_db.materials[resolved], temp, t_ref, delta_eg)
    return adjusted


def _shift_material(material, temp: float, t_ref: float, delta_eg: float):
    wl = material.wavelength_nm
    energy = 1240.0 / wl
    order = np.argsort(energy)
    energy_sorted = energy[order]
    k_sorted = material.k[order]
    sample_energy = energy - delta_eg
    shifted_k = np.interp(sample_energy, energy_sorted, k_sorted, left=k_sorted[0], right=k_sorted[-1])
    k_new = constrained_k_shift(wl, material.k, shifted_k, delta_eg)
    n_delta = kk_delta_n(wl, material.k, k_new)
    n_delta = np.clip(n_delta, -0.08, 0.08)
    from .materials import Material

    return Material(
        id=material.id,
        name=f"{material.name} @ {temp:g} K",
        source=f"temperature-adjusted from {t_ref:g} K",
        wavelength_nm=wl.copy(),
        n=np.maximum(material.n + n_delta, 0.1),
        k=np.maximum(k_new, 0.0),
    )


def constrained_k_shift(wavelength_nm: np.ndarray, k_ref: np.ndarray, shifted_k: np.ndarray, delta_eg: float) -> np.ndarray:
    wl = np.asarray(wavelength_nm, dtype=float)
    base = np.maximum(np.asarray(k_ref, dtype=float), 0.0)
    shifted = np.maximum(np.asarray(shifted_k, dtype=float), 0.0)
    edge_idx = estimate_absorption_edge_index(wl, base)
    edge_wl = wl[edge_idx]
    window_nm = max(80.0, abs(delta_eg) * 1240.0 / max((1240.0 / edge_wl) ** 2, 1e-9) * 2.0)
    taper = 0.5 * (1.0 + np.tanh((wl - (edge_wl - window_nm)) / max(window_nm / 3.0, 1.0)))
    k_new = base * (1.0 - taper) + shifted * taper
    long_mask = wl > edge_wl + 120.0
    if np.any(long_mask):
        k_new[long_mask] = smooth_long_wavelength_tail(wl[long_mask], k_new[long_mask])
    k_new = smooth_series(k_new)
    return np.maximum(k_new, 0.0)


def estimate_absorption_edge_index(wavelength_nm: np.ndarray, k_values: np.ndarray) -> int:
    k = np.asarray(k_values, dtype=float)
    if np.max(k) <= 0:
        return len(k) // 2
    threshold = max(0.02, 0.08 * float(np.max(k)))
    candidates = np.where(k > threshold)[0]
    if len(candidates) == 0:
        return len(k) // 2
    return int(candidates[-1])


def smooth_long_wavelength_tail(wavelength_nm: np.ndarray, k_values: np.ndarray) -> np.ndarray:
    if len(k_values) < 5:
        return k_values
    smooth = smooth_series(k_values)
    floor = max(0.0, float(np.min(k_values)))
    # Enforce a gentle non-increasing tail where the material is mostly transparent.
    tail = smooth.copy()
    for i in range(1, len(tail)):
        tail[i] = min(tail[i], tail[i - 1] + 0.002)
    return np.maximum(tail, floor)


def smooth_series(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if len(arr) < 7:
        return arr
    window = min(15, len(arr) if len(arr) % 2 == 1 else len(arr) - 1)
    if window < 5:
        return arr
    try:
        return savgol_filter(arr, window_length=window, polyorder=2, mode="interp")
    except Exception:
        kernel = np.ones(5) / 5.0
        return np.convolve(arr, kernel, mode="same")


def kk_delta_n(wavelength_nm: np.ndarray, k_ref: np.ndarray, k_new: np.ndarray) -> np.ndarray:
    energy = 1240.0 / wavelength_nm
    order = np.argsort(energy)
    e = energy[order]
    delta_k = (k_new - k_ref)[order]
    out = np.zeros_like(e)
    for i, ei in enumerate(e):
        denom = e**2 - ei**2
        mask = np.abs(denom) > 1e-9
        integrand = np.zeros_like(e)
        integrand[mask] = e[mask] * delta_k[mask] / denom[mask]
        out[i] = (2.0 / math.pi) * np.trapezoid(integrand[mask], e[mask])
    reverse = np.empty_like(out)
    reverse[order] = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
    return reverse
