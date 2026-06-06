from __future__ import annotations

import math
from typing import Any

import numpy as np
import tmm

from .materials import MaterialDatabase, load_am15g
from .models import Layer
from .templates import get_template

Q = 1.60217663e-19
H = 6.62607015e-34
C = 299792458.0


def run_tmm(payload: dict[str, Any], material_db: MaterialDatabase) -> dict[str, Any]:
    wavelengths = _wavelength_grid(payload)
    layers = _layers_from_payload(payload)
    if len(layers) < 3:
        raise ValueError("At least incident medium, one layer, and substrate are required.")

    d_list = [layer.thickness_value() for layer in layers]
    if not math.isinf(d_list[0]):
        d_list[0] = float("inf")
    if not math.isinf(d_list[-1]):
        d_list[-1] = float("inf")

    nk_by_layer = [material_db.get(layer.material).nk(wavelengths) for layer in layers]
    absorption = np.zeros((len(layers), len(wavelengths)), dtype=float)
    reflection = np.zeros(len(wavelengths), dtype=float)
    transmission = np.zeros(len(wavelengths), dtype=float)

    for idx, wl in enumerate(wavelengths):
        n_list = [nk[idx] for nk in nk_by_layer]
        result = tmm.coh_tmm("s", n_list, d_list, 0.0, float(wl))
        absorption[:, idx] = np.maximum(np.real(tmm.absorp_in_each_layer(result)), 0.0)
        reflection[idx] = float(np.real(result["R"]))
        transmission[idx] = float(np.real(result["T"]))

    jsc = _calculate_jsc(wavelengths, absorption, layers)
    return _result_dict("tmm", wavelengths, layers, reflection, transmission, absorption, jsc)


def _wavelength_grid(payload: dict[str, Any]) -> np.ndarray:
    w = payload.get("wavelength", {})
    start = float(w.get("start_nm", 300))
    stop = float(w.get("stop_nm", 1100))
    step = float(w.get("step_nm", 10))
    if start <= 0 or stop <= start or step <= 0:
        raise ValueError("Invalid wavelength range.")
    count = int(np.floor((stop - start) / step)) + 1
    return start + np.arange(count) * step


def _layers_from_payload(payload: dict[str, Any]) -> list[Layer]:
    if "layers" in payload and payload["layers"]:
        return [Layer.from_dict(item) for item in payload["layers"]]
    return get_template(str(payload.get("template_id", "all_perovskite")))


def _calculate_jsc(wavelengths_nm: np.ndarray, absorption: np.ndarray, layers: list[Layer]) -> dict[str, float]:
    return _calculate_layer_currents(wavelengths_nm, absorption, layers)["active_currents"]


def _calculate_layer_currents(wavelengths_nm: np.ndarray, absorption: np.ndarray, layers: list[Layer]) -> dict[str, dict[str, float] | float]:
    solar_w_m2_nm = load_am15g(wavelengths_nm)
    photon_energy = H * C / (wavelengths_nm * 1e-9)
    photon_flux = np.divide(solar_w_m2_nm, photon_energy, out=np.zeros_like(solar_w_m2_nm), where=photon_energy != 0)
    layer_currents: dict[str, float] = {}
    active_currents: dict[str, float] = {}
    active_values = []
    seen_names: dict[str, int] = {}
    for idx, layer in enumerate(layers):
        if math.isinf(layer.thickness_value()) or layer.thickness_value() <= 0:
            continue
        seen_names[layer.name] = seen_names.get(layer.name, 0) + 1
        current_name = layer.name if seen_names[layer.name] == 1 else f"{layer.name} ({seen_names[layer.name]})"
        absorbed_photons = photon_flux * absorption[idx, :]
        j_a_m2 = Q * np.trapezoid(absorbed_photons, wavelengths_nm)
        value = float(j_a_m2 * 0.1)
        layer_currents[current_name] = value
        if not layer.active:
            continue
        active_currents[current_name] = value
        active_values.append(value)
    if active_values:
        active_currents["matched"] = float(min(active_values))
        active_currents["sum_active"] = float(sum(active_values))
    return {
        "layer_currents": layer_currents,
        "active_currents": active_currents,
        "matched": float(min(active_values)) if active_values else 0.0,
    }


def _result_dict(
    method: str,
    wavelengths: np.ndarray,
    layers: list[Layer],
    reflection: np.ndarray,
    transmission: np.ndarray,
    absorption: np.ndarray,
    jsc: dict[str, float],
) -> dict[str, Any]:
    current_payload = _calculate_layer_currents(wavelengths, absorption, layers)
    layer_payload = []
    for idx, layer in enumerate(layers):
        layer_payload.append(
            {
                **layer.to_dict(),
                "absorption": _clean(absorption[idx, :]),
                "absorption_mean": float(np.mean(absorption[idx, :])),
            }
        )
    return {
        "method": method,
        "geometry": "planar",
        "model_note": "TMM supports planar multilayer structures only.",
        "wavelength_nm": _clean(wavelengths),
        "reflection": _clean(reflection),
        "transmission": _clean(transmission),
        "layers": layer_payload,
        "jsc_mA_cm2": jsc,
        "layer_currents_mA_cm2": current_payload["layer_currents"],
        "active_currents_mA_cm2": current_payload["active_currents"],
        "matched_current_mA_cm2": current_payload["matched"],
    }


def _clean(values: np.ndarray) -> list[float]:
    arr = np.nan_to_num(np.asarray(values, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    return [float(x) for x in arr]
