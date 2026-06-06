from __future__ import annotations

import sys
from typing import Any

import numpy as np
from scipy.interpolate import interp1d

from .materials import MaterialDatabase, load_am15g
from .paths import RCWA_DIR


def run_rcwa(payload: dict[str, Any], progress=None) -> dict[str, Any]:
    if str(RCWA_DIR) not in sys.path:
        sys.path.insert(0, str(RCWA_DIR))
    try:
        import rcwa_engine as legacy_rcwa
    except Exception as exc:
        raise RuntimeError(f"Unable to import RCWA engine: {exc}") from exc
    _patch_legacy_data_loaders(legacy_rcwa)

    params = payload.get("rcwa", payload)
    rcwa_params = _validated_params(params)
    shape = rcwa_params["shape"]
    periodic = rcwa_params["periodic"]
    duty_cycle = rcwa_params["duty_cycle"]
    _patch_legacy_shapes(legacy_rcwa, duty_cycle=duty_cycle)
    t_wbg = rcwa_params["t_wbg"]
    t_nbg = rcwa_params["t_nbg"]
    if progress:
        progress(10, "RCWA engine initialized.")

    if not periodic or shape.lower() == "planar":
        shape = "Planar"
        result = legacy_rcwa.calculate_planar_cell(t_wbg=t_wbg, t_nbg=t_nbg)
        geometry = "planar"
    else:
        result = legacy_rcwa.calculate_fully_coupled_cell(
            shape_type=shape,
            pitch=rcwa_params["pitch"],
            height=rcwa_params["height"],
            t_wbg=t_wbg,
            t_nbg=t_nbg,
            nG=rcwa_params["nG"],
            N_slices=rcwa_params["slices"],
        )
        geometry = "periodic"
    if progress:
        progress(95, "Packaging RCWA result.")
    return _normalize(result, shape, geometry, rcwa_params)


def _validated_params(params: dict[str, Any]) -> dict[str, Any]:
    shape = str(params.get("shape", "Planar"))
    periodic = bool(params.get("periodic", shape.lower() != "planar"))
    pitch = float(params.get("pitch", 500.0))
    height = float(params.get("height", 500.0))
    duty_cycle = float(params.get("duty_cycle", 0.5))
    nG = int(params.get("nG", 17))
    slices = int(params.get("slices", 12))
    if pitch <= 0:
        raise ValueError("RCWA pitch must be greater than 0.")
    if height <= 0:
        raise ValueError("RCWA height must be greater than 0.")
    if duty_cycle < 0.05 or duty_cycle > 0.95:
        raise ValueError("RCWA duty cycle must be between 0.05 and 0.95.")
    if nG < 3:
        raise ValueError("RCWA nG must be at least 3.")
    if nG % 2 == 0:
        nG += 1
    if slices < 1:
        raise ValueError("RCWA slices must be at least 1.")
    return {
        "periodic": periodic,
        "shape": shape,
        "pitch": pitch,
        "height": height,
        "duty_cycle": duty_cycle,
        "nG": nG,
        "slices": slices,
        "t_wbg": float(params.get("t_wbg", 410.0)),
        "t_nbg": float(params.get("t_nbg", 800.0)),
    }


def _patch_legacy_data_loaders(legacy_rcwa) -> None:
    db = MaterialDatabase()
    material_map = {
        "glass": "glass",
        "ito": "ito",
        "nio": "nio",
        "wbg": "wbg_perovskite",
        "c60": "c60",
        "sno2": "sno2",
        "pedotpss": "pedot",
        "nbg": "nbg_perovskite",
        "bcp": "bcp",
        "ag": "ag",
    }

    def load_nk_data(material_name):
        material = db.get(material_map.get(material_name, material_name))
        n_interp = interp1d(material.wavelength_nm, material.n, kind="linear", fill_value="extrapolate")
        k_interp = interp1d(material.wavelength_nm, material.k, kind="linear", fill_value="extrapolate")
        return n_interp, k_interp

    def patched_am15g():
        wavelengths = np.arange(250.0, 1701.0, 1.0)
        values = load_am15g(wavelengths)
        return interp1d(wavelengths, values, kind="linear", bounds_error=False, fill_value=0.0)

    legacy_rcwa.load_nk_data = load_nk_data
    legacy_rcwa.load_am15g = patched_am15g


def _patch_legacy_shapes(legacy_rcwa, duty_cycle: float = 0.5) -> None:
    legacy_rcwa.generate_shape_masks = lambda shape_type, pitch, N_slices=20, Nx=60, Ny=60: generate_shape_masks(
        shape_type, pitch, N_slices=N_slices, Nx=Nx, Ny=Ny, duty_cycle=duty_cycle
    )


def generate_shape_masks(shape_type: str, pitch: float, N_slices: int = 20, Nx: int = 60, Ny: int = 60, duty_cycle: float = 0.5) -> np.ndarray:
    x = np.linspace(-pitch / 2, pitch / 2, Nx)
    y = np.linspace(-pitch / 2, pitch / 2, Ny)
    X, Y = np.meshgrid(x, y, indexing="ij")
    masks = np.zeros((N_slices, Nx, Ny), dtype=bool)
    duty = min(max(float(duty_cycle), 0.05), 0.95)
    for i in range(N_slices):
        z_norm = (i + 0.5) / N_slices
        if shape_type == "Pyramid":
            w = pitch * z_norm
            mask = (np.abs(X) <= w / 2) & (np.abs(Y) <= w / 2)
        elif shape_type == "Cone":
            r = (pitch / 2) * z_norm
            mask = (X**2 + Y**2) <= r**2
        elif shape_type == "Paraboloid":
            r = (pitch / 2) * np.sqrt(z_norm)
            mask = (X**2 + Y**2) <= r**2
        elif shape_type == "Sawtooth":
            threshold = -pitch / 2 + pitch * duty * z_norm
            mask = X <= threshold
        else:
            raise ValueError(f"Unknown shape: {shape_type}")
        masks[i, :, :] = mask
    return masks


def _normalize(result: dict[str, Any], shape: str, geometry: str, params: dict[str, Any]) -> dict[str, Any]:
    wl = np.asarray(result.get("wl", []), dtype=float)
    layers = [
        {
            "name": "WBG active layer",
            "material": "wbg_perovskite",
            "active": True,
            "absorption": _clean(result.get("A_wbg", [])),
        },
        {
            "name": "NBG active layer",
            "material": "nbg_perovskite",
            "active": True,
            "absorption": _clean(result.get("A_nbg", [])),
        },
    ]
    return {
        "method": "rcwa",
        "geometry": geometry,
        "shape": shape,
        "periodic_parameters": {
            "shape": shape,
            "pitch": params["pitch"],
            "height": params["height"],
            "duty_cycle": params["duty_cycle"],
            "nG": params["nG"],
            "slices": params["slices"],
            "t_wbg": params["t_wbg"],
            "t_nbg": params["t_nbg"],
        },
        "model_note": "RCWA planar reference calculation." if geometry == "planar" else "RCWA supports periodic/textured structures with Fourier harmonics and sliced geometry.",
        "wavelength_nm": _clean(wl),
        "reflection": _clean(result.get("R", [])),
        "layers": layers,
        "jsc_mA_cm2": {
            "WBG active layer": float(result.get("J_wbg", 0.0)),
            "NBG active layer": float(result.get("J_nbg", 0.0)),
            "matched": float(result.get("J_match", 0.0)),
        },
    }


def _clean(values) -> list[float]:
    arr = np.nan_to_num(np.asarray(values, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    return [float(x) for x in arr]
