from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

from .paths import ALL_PEROVSKITE_DIR, PEROVSKITE_SI_DIR, RCWA_DIR


@dataclass
class Material:
    id: str
    name: str
    source: str
    wavelength_nm: np.ndarray
    n: np.ndarray
    k: np.ndarray

    def nk(self, wavelengths_nm: np.ndarray) -> np.ndarray:
        if self.id == "air":
            return np.ones_like(wavelengths_nm, dtype=complex)
        n_interp = np.interp(wavelengths_nm, self.wavelength_nm, self.n)
        k_interp = np.interp(wavelengths_nm, self.wavelength_nm, self.k)
        return n_interp + 1j * np.maximum(k_interp, 0.0)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "points": int(len(self.wavelength_nm)),
            "wavelength_min_nm": float(np.min(self.wavelength_nm)),
            "wavelength_max_nm": float(np.max(self.wavelength_nm)),
            "n_min": float(np.min(self.n)),
            "n_max": float(np.max(self.n)),
            "k_min": float(np.min(self.k)),
            "k_max": float(np.max(self.k)),
        }


ALIASES = {
    "pedotpss": "pedot",
    "pedot:pss": "pedot",
    "pedot": "pedot",
    "wbg": "wbg_perovskite",
    "nbg": "nbg_perovskite",
    "pvk": "perovskite_164",
    "pvks": "perovskite_164",
    "perovskite": "perovskite_164",
    "csi": "si_crystalline",
    "si": "si_crystalline",
    "a_si_n": "si_amorphous_n",
    "a_si_i": "si_amorphous_i",
    "a_si_p": "si_amorphous_p",
    "izo": "izo",
    "ito": "ito",
    "mgf2": "mgf2",
    "ag": "ag",
    "au": "au",
    "glass": "glass",
    "air": "air",
}

MATERIAL_FILES = {
    "glass": ("Glass", ALL_PEROVSKITE_DIR / "data" / "nk_glass.txt"),
    "ito": ("ITO", ALL_PEROVSKITE_DIR / "data" / "nk_ito.txt"),
    "nio": ("NiO", ALL_PEROVSKITE_DIR / "data" / "nk_nio.txt"),
    "wbg_perovskite": ("Wide bandgap perovskite", ALL_PEROVSKITE_DIR / "data" / "nk_wbg_perovskite.txt"),
    "nbg_perovskite": ("Narrow bandgap perovskite", ALL_PEROVSKITE_DIR / "data" / "nk_nbg_perovskite.txt"),
    "c60": ("C60", ALL_PEROVSKITE_DIR / "data" / "nk_c60.txt"),
    "sno2": ("SnO2", ALL_PEROVSKITE_DIR / "data" / "nk_sno2.txt"),
    "pedot": ("PEDOT:PSS", ALL_PEROVSKITE_DIR / "data" / "nk_pedot.txt"),
    "bcp": ("BCP", ALL_PEROVSKITE_DIR / "data" / "nk_bcp.txt"),
    "ag": ("Ag", PEROVSKITE_SI_DIR / "data" / "Ag.txt"),
    "au": ("Au", ALL_PEROVSKITE_DIR / "data" / "nk_au.txt"),
    "mgf2": ("MgF2", PEROVSKITE_SI_DIR / "data" / "MgF2.txt"),
    "izo": ("IZO", PEROVSKITE_SI_DIR / "data" / "IZO_Amorphous, annealed (0.36% O2).txt"),
    "perovskite_164": ("CsFAMA perovskite 1.64 eV", PEROVSKITE_SI_DIR / "data" / "Perovskite_CsFAMAPbIBr 1.64 eV.txt"),
    "si_crystalline": ("Crystalline silicon", PEROVSKITE_SI_DIR / "data" / "Si_Crystalline.txt"),
    "si_amorphous_n": ("a-Si n", PEROVSKITE_SI_DIR / "data" / "Si_Amorphous_n.txt"),
    "si_amorphous_i": ("a-Si i", PEROVSKITE_SI_DIR / "data" / "Si_Amorphous_i.txt"),
    "si_amorphous_p": ("a-Si p", PEROVSKITE_SI_DIR / "data" / "Si_Amorphous_p.txt"),
}


class MaterialDatabase:
    def __init__(self) -> None:
        self.materials: dict[str, Material] = {}
        self._load_builtin()

    def _load_builtin(self) -> None:
        self.materials["air"] = Material(
            id="air",
            name="Air",
            source="constant n=1",
            wavelength_nm=np.array([200.0, 2500.0]),
            n=np.array([1.0, 1.0]),
            k=np.array([0.0, 0.0]),
        )
        for mat_id, (name, path) in MATERIAL_FILES.items():
            if path.exists():
                wl, n, k = parse_numeric_table(path.read_text(encoding="utf-8", errors="ignore"))
                self.materials[mat_id] = Material(mat_id, name, str(path), wl, n, k)

    def resolve_id(self, material_id: str) -> str:
        key = str(material_id).strip().lower()
        key = re.sub(r"[\s\-]+", "_", key)
        return ALIASES.get(key, key)

    def get(self, material_id: str) -> Material:
        resolved = self.resolve_id(material_id)
        if resolved not in self.materials:
            raise KeyError(f"Unknown material: {material_id}")
        return self.materials[resolved]

    def summaries(self) -> list[dict]:
        return sorted((m.summary() for m in self.materials.values()), key=lambda item: item["name"].lower())

    def add_uploaded(self, material_id: str, name: str, text: str) -> Material:
        wl, n, k = parse_numeric_table(text)
        safe_id = re.sub(r"[^a-zA-Z0-9_]+", "_", material_id.strip().lower()).strip("_")
        if not safe_id:
            safe_id = f"uploaded_{len(self.materials) + 1}"
        material = Material(safe_id, name or safe_id, "uploaded", wl, n, k)
        self.materials[safe_id] = material
        return material


def parse_numeric_table(text: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("Material data is empty.")

    try:
        df = pd.read_csv(io.StringIO(stripped))
        normalized = {str(c).strip().lower(): c for c in df.columns}
        if {"wavelength_nm", "n", "k"}.issubset(normalized):
            out = df[[normalized["wavelength_nm"], normalized["n"], normalized["k"]]].astype(float).to_numpy()
        else:
            out = _parse_lines(stripped)
    except Exception:
        out = _parse_lines(stripped)

    if out.ndim != 2 or out.shape[1] < 3:
        raise ValueError("Material data must contain wavelength_nm, n, and k columns.")
    out = out[:, :3]
    out = out[np.isfinite(out).all(axis=1)]
    if len(out) < 2:
        raise ValueError("Material data must contain at least two numeric rows.")
    out = out[np.argsort(out[:, 0])]
    wl, n, k = out[:, 0], out[:, 1], np.maximum(out[:, 2], 0.0)
    unique_wl, unique_idx = np.unique(wl, return_index=True)
    return unique_wl.astype(float), n[unique_idx].astype(float), k[unique_idx].astype(float)


def _parse_lines(text: str) -> np.ndarray:
    rows = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        parts = re.split(r"[\s,;\t]+", clean)
        numeric = []
        for part in parts:
            try:
                numeric.append(float(part))
            except ValueError:
                pass
        if len(numeric) >= 3:
            rows.append(numeric[:3])
    return np.array(rows, dtype=float)


def load_am15g(wavelengths_nm: np.ndarray) -> np.ndarray:
    candidates = [
        ALL_PEROVSKITE_DIR / "data" / "AM1.5G.txt",
        PEROVSKITE_SI_DIR / "data" / "AM1.5G.txt",
        RCWA_DIR / "data" / "AM1.5G.txt",
    ]
    for path in candidates:
        if path.exists():
            data = np.loadtxt(path)
            func = interp1d(data[:, 0], data[:, 1], bounds_error=False, fill_value=0.0)
            return np.asarray(func(wavelengths_nm), dtype=float)
    raise FileNotFoundError("AM1.5G spectrum file was not found.")

