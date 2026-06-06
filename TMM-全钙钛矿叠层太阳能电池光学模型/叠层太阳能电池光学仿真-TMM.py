import numpy as np
import matplotlib.pyplot as plt
import tmm # 导入正确的 tmm 库
from scipy.interpolate import interp1d
import os

# --- 1. 定义物理常量和仿真参数 ---
q = 1.60217662e-19  # 元电荷 (C)
h = 6.62607004e-34  # 普朗克常数 (J*s)
c = 299792458.0      # 光速 (m/s)
wavelengths_nm = np.linspace(300, 1000, 701)

# --- 2. 定义叠层太阳能电池结构 ---
structure_layers = [
    {'d': np.inf, 'mat': 'air',    'active': False, 'label': 'Air'},
    {'d': 150,    'mat': 'ito',    'active': False, 'label': 'ITO'},
    {'d': 7,      'mat': 'nio',    'active': False, 'label': 'NiO'},
    {'d': 400,    'mat': 'wbg',    'active': True,  'label': '宽带隙(WBG)有源层'},
    {'d': 20,     'mat': 'c60',    'active': False, 'label': 'C60 (1)'},
    {'d': 20,     'mat': 'sno2',   'active': False, 'label': 'SnO2'},
    {'d': 1,      'mat': 'au',     'active': False, 'label': 'Au (隧穿结)'},
    {'d': 18,     'mat': 'pedot',  'active': False, 'label': 'PEDOT:PSS'},
    {'d': 1150,   'mat': 'nbg',    'active': True,  'label': '窄带隙(NBG)有源层'},
    {'d': 20,     'mat': 'c60',    'active': False, 'label': 'C60 (2)'},
    {'d': 4,      'mat': 'bcp',    'active': False, 'label': 'BCP'},
    {'d': 150,    'mat': 'ag',     'active': False, 'label': 'Ag (背电极)'},
    {'d': np.inf, 'mat': 'glass',  'active': False, 'label': 'Glass Substrate'},
]

# --- 3. 加载并处理材料和光谱数据 ---
DATA_DIR = 'data' 

def load_nk_data(filepath, wavelengths_nm):
    data = np.loadtxt(filepath)
    if data.shape[1] == 3:
        wl_data, n_data, k_data = data[:, 0], data[:, 1], data[:, 2]
    elif data.shape[1] == 2:
        wl_data, n_data = data[:, 0], data[:, 1]
        k_data = np.zeros_like(n_data)
    else:
        raise ValueError(f"文件 {os.path.basename(filepath)} 的列数不正确，应为2或3列。")
    n_interp = np.interp(wavelengths_nm, wl_data, n_data)
    k_interp = np.interp(wavelengths_nm, wl_data, k_data)
    return n_interp + 1j * k_interp

def get_material_nk_map(wavelengths, data_dir):
    materials = {
        'air': np.ones_like(wavelengths, dtype=complex),
        'glass': load_nk_data(os.path.join(data_dir, 'nk_glass.txt'), wavelengths),
        'ito': load_nk_data(os.path.join(data_dir, 'nk_ito.txt'), wavelengths),
        'nio': load_nk_data(os.path.join(data_dir, 'nk_nio.txt'), wavelengths),
        'wbg': load_nk_data(os.path.join(data_dir, 'nk_wbg_perovskite.txt'), wavelengths),
        'c60': load_nk_data(os.path.join(data_dir, 'nk_c60.txt'), wavelengths),
        'sno2': load_nk_data(os.path.join(data_dir, 'nk_sno2.txt'), wavelengths),
        'au': load_nk_data(os.path.join(data_dir, 'nk_au.txt'), wavelengths),
        'pedot': load_nk_data(os.path.join(data_dir, 'nk_pedot.txt'), wavelengths),
        'nbg': load_nk_data(os.path.join(data_dir, 'nk_nbg_perovskite.txt'), wavelengths),
        'bcp': load_nk_data(os.path.join(data_dir, 'nk_bcp.txt'), wavelengths),
        'ag': load_nk_data(os.path.join(data_dir, 'nk_ag.txt'), wavelengths),
    }
    return materials

solar_data = np.loadtxt(os.path.join(DATA_DIR, 'AM1.5G.txt'))
power_density_func = interp1d(solar_data[:, 0], solar_data[:, 1], kind='linear', fill_value=0, bounds_error=False)
power_density_W_m2_nm = power_density_func(wavelengths_nm)
wavelengths_m = wavelengths_nm * 1e-9
photon_energy_J = h * c / wavelengths_m
photon_flux_density = np.divide(power_density_W_m2_nm, photon_energy_J, out=np.zeros_like(power_density_W_m2_nm), where=photon_energy_J!=0)

# --- 4. 运行光学仿真 ---
print("正在运行光学仿真，请稍候...")
material_nk_map = get_material_nk_map(wavelengths_nm, DATA_DIR)
reflection_spectrum = []
absorption_per_layer = np.zeros((len(structure_layers), len(wavelengths_nm)))

for i, wl_nm in enumerate(wavelengths_nm):
    n_list = [material_nk_map[s['mat']][i] for s in structure_layers]
    d_list = [s['d'] for s in structure_layers]
    
    # 核心修正：使用 tmm 库的 coh_tmm 函数
    # 注意：角度单位是度
    tmm_results = tmm.coh_tmm('s', n_list, d_list, 0, wl_nm)
    reflection_spectrum.append(tmm_results['R'])
    
    # 核心修正：使用 tmm 库的 absorp_in_each_layer 函数
    absorption = tmm.absorp_in_each_layer(tmm_results)
    absorption_per_layer[:, i] = absorption

print("仿真完成！")

# --- 5. 计算光电流密度 (Jsc) ---
Jsc_per_layer = np.zeros(len(structure_layers))
for i, layer in enumerate(structure_layers):
    if layer['active']:
        absorbed_photons = photon_flux_density * absorption_per_layer[i, :]
        Jsc_A_m2 = q * np.trapezoid(absorbed_photons, wavelengths_nm)
        Jsc_per_layer[i] = Jsc_A_m2 * 0.1 # 转换为 mA/cm^2

active_indices = [i for i, s in enumerate(structure_layers) if s['active']]
Jsc_top_cell = Jsc_per_layer[active_indices[0]]
Jsc_bottom_cell = Jsc_per_layer[active_indices[1]]
Jsc_tandem = min(Jsc_top_cell, Jsc_bottom_cell)

print("\n--- 光电流仿真结果 ---")
print(f"顶电池 (WBG) Jsc: {Jsc_top_cell:.2f} mA/cm^2")
print(f"底电池 (NBG) Jsc: {Jsc_bottom_cell:.2f} mA/cm^2")
print(f"串联电池限制电流 Jsc: {Jsc_tandem:.2f} mA/cm^2")
print("--------------------------\n")

# --- 6. 结果可视化 ---
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.style.use('seaborn-v0_8-darkgrid')
fig, (ax1, ax2, ax4) = plt.subplots(3, 1, figsize=(12, 16), sharex=True)
fig.suptitle('叠层太阳能电池光学仿真分析', fontsize=18)

ax1.plot(wavelengths_nm, np.array(reflection_spectrum) * 100, label='总反射率', color='red', lw=2)
ax1.set_ylabel('反射率 (%)')
ax1.set_title('整体反射光谱')
ax1.legend()
ax1.grid(True)

wbg_idx = [i for i, s in enumerate(structure_layers) if s['mat'] == 'wbg'][0]
nbg_idx = [i for i, s in enumerate(structure_layers) if s['mat'] == 'nbg'][0]
ax2.plot(wavelengths_nm, absorption_per_layer[wbg_idx, :] * 100, label=structure_layers[wbg_idx]['label'], lw=2)
ax2.plot(wavelengths_nm, absorption_per_layer[nbg_idx, :] * 100, label=structure_layers[nbg_idx]['label'], lw=2)
ax2.set_ylabel('有源层吸收率 (%)')
ax2.set_title('有源层吸收光谱')
ax2.legend(loc='upper left')

ax3 = ax2.twinx()
ax3.fill(wavelengths_nm, photon_flux_density, color='gray', alpha=0.2, label='AM1.5G 光子通量')
ax3.set_ylabel('光子通量 (photons/s/m²/nm)', color='gray')
ax3.tick_params(axis='y', labelcolor='gray')
ax3.legend(loc='upper right')

parasitic_indices = [i for i, s in enumerate(structure_layers) if not s['active'] and s['d'] != np.inf and s['d'] > 0]
parasitic_labels = [structure_layers[i]['label'] for i in parasitic_indices]
parasitic_absorption = absorption_per_layer[parasitic_indices, :] * 100
ax4.stackplot(wavelengths_nm, parasitic_absorption, labels=parasitic_labels, alpha=0.8)
ax4.set_xlabel('波长 (nm)')
ax4.set_ylabel('各层寄生吸收率 (%)')
ax4.set_title('寄生吸收分析')
ax4.legend(loc='upper left', fontsize='small')
ax4.set_ylim(0, 100)

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.show()