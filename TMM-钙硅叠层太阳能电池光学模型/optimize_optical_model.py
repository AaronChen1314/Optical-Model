# -*- coding: utf-8 -*-
import os
import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import differential_evolution
import tmm
import warnings

def load_nk(file_path):
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.replace(',', ' ').split()
            try:
                if len(parts) >= 3:
                    data.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except ValueError:
                pass
    data = np.array(data)
    data = data[data[:,0].argsort()]
    return data[:, 0], data[:, 1], data[:, 2]

def load_spectrum(file_path):
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.replace(',', ' ').split()
            try:
                if len(parts) >= 2:
                    data.append([float(parts[0]), float(parts[1])])
            except ValueError:
                pass
    data = np.array(data)
    data = data[data[:,0].argsort()]
    return data[:, 0], data[:, 1]

def build_nk_interp(base_path):
    data_path = os.path.join(base_path, "data")
    # Read files
    files = [
        ("MgF2.txt", 'c'),
        ("IZO_Amorphous, annealed (0.36% O2).txt", 'c'),
        ("nk_bcp.txt", 'c'),
        ("nk_c60.txt", 'c'),
        ("Perovskite_CsFAMAPbIBr 1.64 eV.txt", 'c'),
        ("nk_ito.txt", 'c'),
        ("Si_Amorphous_n.txt", 'c'),
        ("Si_Amorphous_i.txt", 'c'),
        ("Si_Crystalline.txt", 'i'),
        ("Si_Amorphous_i.txt", 'c'),
        ("Si_Amorphous_p.txt", 'c'),
        ("nk_ito.txt", 'c'),
        ("Ag.txt", 'c')
    ]
    
    nk_funcs = [lambda w: 1.0 + 0.0j] # Layer 0: Air
    for f, t in files:
        wl, n, k = load_nk(os.path.join(data_path, f))
        n_func = interp1d(wl, n, bounds_error=False, fill_value=(n[0], n[-1]))
        k_func = interp1d(wl, k, bounds_error=False, fill_value=(k[0], k[-1]))
        def make_nk(n_f, k_f):
            return lambda w: n_f(w) + 1j * max(0.0, k_f(w))
        nk_funcs.append(make_nk(n_func, k_func))
    nk_funcs.append(lambda w: 1.0 + 0.0j) # Layer N: Air substrate
    
    c_list = ['i'] + [t for f, t in files] + ['i']
    return nk_funcs, c_list

base_path = os.path.dirname(os.path.abspath(__file__))
nk_funcs, c_list = build_nk_interp(base_path)

wavelengths = np.arange(300, 1601, 10)
num_layers = len(c_list)
NK_MATRIX = np.zeros((len(wavelengths), num_layers), dtype=complex)
for i, wl in enumerate(wavelengths):
    NK_MATRIX[i] = [nk_funcs[idx](wl) for idx in range(num_layers)]
    NK_MATRIX[i][0] = NK_MATRIX[i][0].real + 0.0j
    NK_MATRIX[i][-1] = NK_MATRIX[i][-1].real + 0.0j

# Photon flux setup
spec_wl, spec_irrad = load_spectrum(os.path.join(base_path, "data", "AM1.5G.txt"))
spec_func = interp1d(spec_wl, spec_irrad, bounds_error=False, fill_value=0.0)
S_lambda = spec_func(wavelengths)
q = 1.60217663e-19
h = 6.62607015e-34
c_const = 299792458
current_density_flux = (S_lambda * (wavelengths * 1e-9) / (h * c_const)) * q * 0.1

def calculate_jsc(x):
    # x: [MgF2, IZO_top, BCP, C60, PVKS, IZO_inter, aSi_n, aSi_i_front, cSi, aSi_i_rear, aSi_p, ITO, Ag]
    d_list = [np.inf] + list(x) + [np.inf]
    
    abs_pvk = np.zeros(len(wavelengths))
    abs_si = np.zeros(len(wavelengths))
    
    for i, wl in enumerate(wavelengths):
        n_list_wl = NK_MATRIX[i]
        res = tmm.inc_tmm('s', list(n_list_wl), d_list, c_list, 0.0, wl)
        absorp_list = tmm.inc_absorp_in_each_layer(res)
        abs_pvk[i] = absorp_list[5]
        abs_si[i] = absorp_list[9]
        
    jsc_pvk = np.trapezoid(abs_pvk * current_density_flux, x=wavelengths)
    jsc_si = np.trapezoid(abs_si * current_density_flux, x=wavelengths)
    return jsc_pvk, jsc_si


def objective(x):
    jsc_pvk, jsc_si = calculate_jsc(x)
    return -min(jsc_pvk, jsc_si)

if __name__ == "__main__":
    warnings.filterwarnings('ignore', module='tmm')
    
    # Focus on the most impactful layers: MgF2, IZO_top, PVKS, IZO_inter, ITO
    # MgF2 (ARC), IZO (Top), BCP, C60, PVKS, IZO (Inter), aSi_n, aSi_i_front, cSi, aSi_i_rear, aSi_p, ITO, Ag
    # Index: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
    
    # Standard values for fixed layers
    # BCP=4, C60=5, aSi_n=2, aSi_i_front=1, cSi=200000, aSi_i_rear=5, aSi_p=10, Ag=100
    
    print("Running 2D Grid Search (PVKS & MgF2)...")
    best_min_jsc = 0.0
    best_x = None
    best_jpvk = 0.0
    best_jsi = 0.0
    
    # Grid search ranges
    pvks_range = np.linspace(250, 600, 36)
    mgf2_range = np.linspace(60, 150, 10)
    
    for mgf2 in mgf2_range:
        for pvks in pvks_range:
            # Current structure
            x = [mgf2, 20, 4, 5, pvks, 5, 2, 1, 200000, 5, 10, 50, 100]
            j_pvk, j_si = calculate_jsc(x)
            j_tandem = min(j_pvk, j_si)
            
            if j_tandem > best_min_jsc:
                best_min_jsc = j_tandem
                best_x = x
                best_jpvk = j_pvk
                best_jsi = j_si

    print(f"\nSearch Finished.")
    print(f"Matched Tandem Jsc: {best_min_jsc:.3f} mA/cm2")
    print(f"PVK Jsc: {best_jpvk:.3f}, Si Jsc: {best_jsi:.3f}")
    
    print("\nOptimal Thicknesses for current structure (nm):")
    labels = ["MgF2 (ARC)", "IZO (Top)", "BCP", "C60", "PVKS", "IZO (Inter)", "a-Si (n)", "a-Si (i) front", "c-Si", "a-Si (i) rear", "a-Si (p)", "ITO", "Ag"]
    for label, val in zip(labels, best_x):
        print(f"{label:15}: {val:.2f} nm")



