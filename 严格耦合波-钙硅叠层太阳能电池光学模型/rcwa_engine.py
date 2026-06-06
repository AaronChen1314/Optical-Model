import os
import numpy as np
import grcwa
import time
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

# ==========================================
# 0. 环境与路径管理 (原 rcwa_utils.py)
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
PLOTS_DIR = os.path.join(BASE_DIR, 'plots')

def ensure_dirs():
    for d in [DATA_DIR, PLOTS_DIR]:
        if not os.path.exists(d):
            os.makedirs(d)

_NK_CACHE = {}
_AM15G_CACHE = None

def load_nk_data(material_name):
    if material_name in _NK_CACHE: return _NK_CACHE[material_name]
    filename_map = {
        'glass': 'nk_glass.txt', 'ito': 'nk_ito.txt', 'nio': 'nk_nio.txt',
        'wbg': 'nk_wbg_perovskite.txt', 'c60': 'nk_c60.txt', 'sno2': 'nk_sno2.txt',
        'pedotpss': 'nk_pedot.txt', 'nbg': 'nk_nbg_perovskite.txt',
        'bcp': 'nk_bcp.txt', 'ag': 'nk_ag.txt',
    }
    filepath = os.path.join(DATA_DIR, filename_map[material_name])
    data = np.loadtxt(filepath)
    n_interp = interp1d(data[:,0], data[:,1], kind='linear', fill_value="extrapolate")
    k_interp = interp1d(data[:,0], data[:,2], kind='linear', fill_value="extrapolate")
    _NK_CACHE[material_name] = (n_interp, k_interp)
    return n_interp, k_interp

def load_am15g():
    global _AM15G_CACHE
    if _AM15G_CACHE is not None: return _AM15G_CACHE
    filepath = os.path.join(DATA_DIR, 'AM1.5G.txt')
    data = np.loadtxt(filepath)
    _AM15G_CACHE = interp1d(data[:, 0], data[:, 1], kind='linear', fill_value=0)
    return _AM15G_CACHE

# ==========================================
# 1. 几何与物理引擎 (原 rcwa_engine.py)
# ==========================================
def generate_shape_masks(shape_type, pitch, N_slices=20, Nx=60, Ny=60):
    x = np.linspace(-pitch/2, pitch/2, Nx)
    y = np.linspace(-pitch/2, pitch/2, Ny)
    X, Y = np.meshgrid(x, y)
    masks = np.zeros((N_slices, Nx, Ny), dtype=bool)
    for i in range(N_slices):
        z_norm = (i + 0.5) / N_slices 
        if shape_type == "Pyramid":
            w = pitch * z_norm 
            mask = (np.abs(X) <= w/2) & (np.abs(Y) <= w/2)
        elif shape_type == "Cone":
            r = (pitch / 2) * z_norm
            mask = (X**2 + Y**2) <= r**2
        elif shape_type == "Paraboloid":
            r = (pitch / 2) * np.sqrt(z_norm)
            mask = (X**2 + Y**2) <= r**2
        else: raise ValueError(f"Unknown shape: {shape_type}")
        masks[i, :, :] = mask
    return masks

def calculate_fully_coupled_cell(shape_type, pitch, height, t_wbg=380.0, t_nbg=800.0, nG=25, N_slices=12):
    nk_dict = {m: load_nk_data(m) for m in ['glass', 'ito', 'nio', 'wbg', 'c60', 'sno2', 'pedotpss', 'nbg', 'bcp', 'ag']}
    am15g_interp = load_am15g()
    
    def get_eps(material, wl):
        n, k = nk_dict[material][0](wl), nk_dict[material][1](wl)
        return (n + 1j * k)**2

    masks = generate_shape_masks(shape_type, pitch, N_slices=N_slices)
    Nx, Ny = masks.shape[1], masks.shape[2]
    L1, L2 = [pitch, 0.0], [0.0, pitch]
    wavelengths = np.arange(300, 1061, 10) 
    S_am15 = am15g_interp(wavelengths)
    
    A_wbg_list, A_nbg_list, R_list = [], [], []
    for wl in wavelengths:
        freq = 1.0 / wl
        obj = grcwa.obj(nG, L1, L2, freq, theta=1e-4, phi=1e-4, verbose=0)
        eps = {m: get_eps(m, wl) for m in nk_dict.keys()}
        
        obj.Add_LayerUniform(0.0, 1.0)
        dz = height / N_slices
        for _ in range(N_slices): obj.Add_LayerGrid(dz, Nx, Ny)
        obj.Add_LayerUniform(1000.0, eps['glass'])
        obj.Add_LayerUniform(100.0, eps['ito'])
        obj.Add_LayerUniform(7.0, eps['nio'])
        obj.Add_LayerUniform(t_wbg, eps['wbg'])
        obj.Add_LayerUniform(20.0, eps['c60'])
        obj.Add_LayerUniform(20.0, eps['sno2'])
        obj.Add_LayerUniform(10.0, eps['ito'])
        obj.Add_LayerUniform(18.0, eps['pedotpss'])
        obj.Add_LayerUniform(t_nbg, eps['nbg'])
        obj.Add_LayerUniform(20.0, eps['c60'])
        obj.Add_LayerUniform(4.0, eps['bcp'])
        obj.Add_LayerUniform(150.0, eps['ag'])
        obj.Add_LayerUniform(0.0, 1.0)

        obj.Init_Setup()
        ep_all = []
        for i in range(N_slices):
            eps_grid = np.ones((Nx, Ny), dtype=complex)
            eps_grid[masks[i, :, :]] = eps['glass']
            ep_all.append(eps_grid.flatten())
        obj.GridLayer_geteps(np.concatenate(ep_all))
        
        idx_wbg, idx_nbg = N_slices + 4, N_slices + 9
        A_wbg_tot, A_nbg_tot, R_tot = 0, 0, 0
        for p_amp, s_amp in [(1, 0), (0, 1)]:
            obj.MakeExcitationPlanewave(p_amp=p_amp, p_phase=0, s_amp=s_amp, s_phase=0, order=0)
            R, _ = obj.RT_Solve(normalize=1)
            def get_Sz(l, z):
                try:
                    E, H = obj.Solve_FieldFourier(l, z)
                    return np.sum(np.real(E[0] * np.conj(H[1]) - E[1] * np.conj(H[0])))
                except: return 0.0
            Abs_wbg = get_Sz(idx_wbg, 0.0) - get_Sz(idx_wbg, t_wbg)
            Abs_nbg = get_Sz(idx_nbg, 0.0) - get_Sz(idx_nbg, t_nbg)
            A_wbg_tot += max(0, Abs_wbg); A_nbg_tot += max(0, Abs_nbg); R_tot += float(R)
            
        R_list.append(R_tot/2); A_wbg_list.append(A_wbg_tot/2); A_nbg_list.append(A_nbg_tot/2)

    j_wbg = 0.1 * np.trapezoid(np.array(A_wbg_list) * S_am15 * (wavelengths/1240.0), wavelengths)
    j_nbg = 0.1 * np.trapezoid(np.array(A_nbg_list) * S_am15 * (wavelengths/1240.0), wavelengths)
    return {
        'J_wbg': round(j_wbg, 4), 'J_nbg': round(j_nbg, 4), 'J_match': round(min(j_wbg, j_nbg), 4),
        'wl': wavelengths, 'R': np.array(R_list),
        'A_wbg': np.array(A_wbg_list), 'A_nbg': np.array(A_nbg_list)
    }
def calculate_planar_cell(t_wbg=410.0, t_nbg=800.0):
    nk_dict = {m: load_nk_data(m) for m in ['glass', 'ito', 'nio', 'wbg', 'c60', 'sno2', 'pedotpss', 'nbg', 'bcp', 'ag']}
    am15g_interp = load_am15g()
    def get_eps(m, wl):
        n, k = nk_dict[m][0](wl), nk_dict[m][1](wl)
        return (n + 1j * k)**2
    wavelengths = np.arange(300, 1061, 10); S_am15 = am15g_interp(wavelengths)
    A_wbg_list, A_nbg_list, R_list = [], [], []
    for wl in wavelengths:
        freq = 1.0/wl; obj = grcwa.obj(9, [100,0], [0,100], freq, 0, 0, 0)
        eps = {m: get_eps(m, wl) for m in nk_dict.keys()}
        obj.Add_LayerUniform(0, 1); obj.Add_LayerUniform(1000, eps['glass'])
        obj.Add_LayerUniform(100, eps['ito']); obj.Add_LayerUniform(7, eps['nio'])
        obj.Add_LayerUniform(t_wbg, eps['wbg']); obj.Add_LayerUniform(20, eps['c60'])
        obj.Add_LayerUniform(20, eps['sno2']); obj.Add_LayerUniform(10, eps['ito'])
        obj.Add_LayerUniform(18, eps['pedotpss']); obj.Add_LayerUniform(t_nbg, eps['nbg'])
        obj.Add_LayerUniform(20, eps['c60']); obj.Add_LayerUniform(4, eps['bcp'])
        obj.Add_LayerUniform(150, eps['ag']); obj.Add_LayerUniform(0, 1)
        obj.Init_Setup()
        idx_wbg, idx_nbg = 4, 9
        A_wbg_tot, A_nbg_tot, R_tot = 0, 0, 0
        for p, s in [(1,0), (0,1)]:
            obj.MakeExcitationPlanewave(p, 0, s, 0, 0)
            R, _ = obj.RT_Solve(normalize=1)
            def get_Sz(l, z):
                try:
                    E, H = obj.Solve_FieldFourier(l, z)
                    return np.sum(np.real(E[0] * np.conj(H[1]) - E[1] * np.conj(H[0])))
                except: return 0.0
            A_wbg_tot += max(0, get_Sz(idx_wbg, 0.0) - get_Sz(idx_wbg, t_wbg))
            A_nbg_tot += max(0, get_Sz(idx_nbg, 0.0) - get_Sz(idx_nbg, t_nbg))
            R_tot += float(R)
        A_wbg_list.append(A_wbg_tot/2); A_nbg_list.append(A_nbg_tot/2); R_list.append(R_tot/2)
    j_wbg = 0.1 * np.trapezoid(np.array(A_wbg_list) * S_am15 * (wavelengths/1240.0), wavelengths)
    j_nbg = 0.1 * np.trapezoid(np.array(A_nbg_list) * S_am15 * (wavelengths/1240.0), wavelengths)
    return {
        'J_wbg': round(j_wbg,4), 'J_nbg': round(j_nbg,4), 'J_match': round(min(j_wbg, j_nbg), 4),
        'wl': wavelengths, 'R': np.array(R_list),
        'A_wbg': np.array(A_wbg_list), 'A_nbg': np.array(A_nbg_list)
    }
def run_convergence_test(shape="Paraboloid", pitch=500, height=500, t_wbg=410.0, t_nbg=800.0):
    nG_values = [5, 9, 13, 17, 21]
    res_list = []
    print(f"🔍 测试选定参数收敛性: {shape} P={pitch}nm H={height}nm WBG={t_wbg}nm NBG={t_nbg}nm...")
    
    converged_nG = nG_values[-1]
    for i, nG in enumerate(nG_values):
        res = calculate_fully_coupled_cell(shape, pitch, height, t_wbg, t_nbg, nG=nG)
        res_list.append(res['J_match'])
        print(f"  [测试] nG={nG:2d} | J_match={res['J_match']:.4f} mA/cm²")
        
        if i > 0:
            err = abs(res_list[i] - res_list[i-1]) / max(res_list[i-1], 1e-10) * 100.0
            if err < 0.1:  # 0.1% 收敛条件
                print(f"✅ 达到收敛条件 (误差 < 0.1%), 推荐 nG = {nG}")
                converged_nG = nG
                break
                
    if converged_nG == nG_values[-1] and len(res_list) == len(nG_values):
        print(f"⚠️ 达到预设最大测试值，建议保守选用 nG = {converged_nG}")
        
    return converged_nG
