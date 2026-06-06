import os
import sys
import itertools
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from concurrent.futures import ProcessPoolExecutor, as_completed

# 确保能导入当前目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rcwa_engine import calculate_fully_coupled_cell, calculate_planar_cell, run_convergence_test, DATA_DIR, ensure_dirs, PLOTS_DIR

# 全局自适应状态字典
SESSION_CONFIG = {
    'shapes': ['Paraboloid'],
    'pitches': [300, 400, 500],
    'heights': [300, 400, 500],
    't_wbg': [410.0],
    't_nbg': [800.0],
    'nG': 17
}

VALID_SHAPES = ['Planar', 'Paraboloid', 'Pyramid', 'Cone']

def print_header():
    print("\n" + "=" * 60)
    print("🔬 RCWA 钙钛矿叠层电池综合仿真系统")
    print("=" * 60)
    print(f"当前配置状态:")
    print(f"  [结构形状]: {SESSION_CONFIG['shapes']}")
    print(f"  [扫描周期 Pitch]: {SESSION_CONFIG['pitches']} nm")
    print(f"  [扫描高度 Height]: {SESSION_CONFIG['heights']} nm")
    print(f"  [WBG 厚度]: {SESSION_CONFIG['t_wbg']} nm")
    print(f"  [NBG 厚度]: {SESSION_CONFIG['t_nbg']} nm")
    print(f"  [物理精度 nG]: {SESSION_CONFIG['nG']}")
    
    total_runs = 0
    for s in SESSION_CONFIG['shapes']:
        if s == 'Planar':
            total_runs += len(SESSION_CONFIG['t_wbg']) * len(SESSION_CONFIG['t_nbg'])
        else:
            total_runs += len(SESSION_CONFIG['pitches']) * len(SESSION_CONFIG['heights']) * len(SESSION_CONFIG['t_wbg']) * len(SESSION_CONFIG['t_nbg'])
        
    print(f"\n⚡ 当前组合总计算点数: {total_runs}")
    print("=" * 60)

def parse_float_list(prompt, current):
    user_input = input(f"{prompt} (当前: {current}, 逗号分隔, 留空保持): ").strip()
    if not user_input: return current
    try: return [float(x.strip()) for x in user_input.split(',')]
    except:
        print(f"❌ 输入格式有误")
        return current

def parse_int_list(prompt, current):
    user_input = input(f"{prompt} (当前: {current}, 逗号分隔, 留空保持): ").strip()
    if not user_input: return current
    try: return [int(x.strip()) for x in user_input.split(',')]
    except:
        print(f"❌ 输入格式有误")
        return current

def menu_1_convergence():
    print("\n🔍 【1】全面自检，并随时修改最佳参数 (nG收敛性测试)")
    s = SESSION_CONFIG['shapes'][0] if SESSION_CONFIG['shapes'][0] != 'Planar' else 'Paraboloid'
    p, h = SESSION_CONFIG['pitches'][0], SESSION_CONFIG['heights'][0]
    w, n = SESSION_CONFIG['t_wbg'][0], SESSION_CONFIG['t_nbg'][0]
    best_nG = run_convergence_test(s, p, h, w, n)
    SESSION_CONFIG['nG'] = best_nG
    print(f"\n✅ 已自动将全局 nG 参数更新为: {SESSION_CONFIG['nG']}")

def menu_2_shapes():
    print("\n📐 【2】识别可供设置的结构种类")
    for i, shape in enumerate(VALID_SHAPES, 1): print(f"  [{i}] {shape}")
    user_input = input("请选择需要的结构 (例如 '1,2'，留空保持): ").strip()
    if user_input:
        try:
            indices = [int(x.strip()) - 1 for x in user_input.split(',')]
            selected = [VALID_SHAPES[i] for i in indices if 0 <= i < len(VALID_SHAPES)]
            if selected: 
                SESSION_CONFIG['shapes'] = selected
                print(f"✅ 已更新结构为: {SESSION_CONFIG['shapes']}")
        except: print(f"❌ 选择错误")

def menu_3_dimensions():
    print("\n📏 【3】设置结构扫描二维参数 (Pitch & Height)")
    SESSION_CONFIG['pitches'] = parse_int_list("请输入周期列表 (nm)", SESSION_CONFIG['pitches'])
    SESSION_CONFIG['heights'] = parse_int_list("请输入高度列表 (nm)", SESSION_CONFIG['heights'])
    print(f"✅ 维度参数更新完成")

def menu_4_thicknesses():
    print("\n🥪 【4】前界面结构 - WBG/NBG 厚度联合扫描设置")
    SESSION_CONFIG['t_wbg'] = parse_float_list("请输入 WBG 厚度序列 (nm)", SESSION_CONFIG['t_wbg'])
    SESSION_CONFIG['t_nbg'] = parse_float_list("请输入 NBG 厚度序列 (nm)", SESSION_CONFIG['t_nbg'])
    print(f"✅ 厚度参数更新完成")

def plot_single_result(res, prefix):
    if 'wl' not in res:
        print(f"❌ 警告: 缺少绘图必须的 'wl' 字段")
        return
        
    wl, R, Aw, An = res['wl'], res['R'], res['A_wbg'], res['A_nbg']
    Total_Abs = 1.0 - R 
    
    plt.figure(figsize=(10, 6))
    plt.plot(wl, R, label='Reflection Loss (R)', color='#8A98C9', linestyle='--', linewidth=1.5)
    plt.plot(wl, Total_Abs, label='Total Device Absorption', color='darkgrey', linestyle='-.', linewidth=1.5)
    plt.plot(wl, Aw, label=f'WBG Abs (J={res["J_wbg"]})', color='darkorange', linewidth=2.5)
    plt.fill_between(wl, 0, Aw, color='bisque', alpha=0.7)
    plt.plot(wl, An, label=f'NBG Abs (J={res["J_nbg"]})', color='crimson', linewidth=2.5)
    plt.fill_between(wl, 0, An, color='pink', alpha=0.4)

    plt.xlim(300, 1060); plt.ylim(0, 1.05); plt.grid(True, linestyle='--', alpha=0.4)
    plt.xlabel('Wavelength (nm)', fontsize=14); plt.ylabel('Absorption Probability', fontsize=14)
    plt.title(f'Optical Absorption ({prefix}, J_match={res["J_match"]} mA/cm²)', fontsize=16)
    plt.legend(loc='upper right', fontsize=11, framealpha=0.9)
    plt.tight_layout()
    
    file_path = os.path.join(PLOTS_DIR, f"Absorption_{prefix}.png")
    plt.savefig(file_path, dpi=300)
    plt.close()
    print(f"📊 光谱图已保存至: {file_path}")

def worker_task(args):
    shape, pitch, height, wbg, nbg, nG = args
    try:
        if shape == 'Planar': 
            res = calculate_planar_cell(wbg, nbg)
            prefix = f"{shape}_W{wbg}_N{nbg}"
        else: 
            res = calculate_fully_coupled_cell(shape, pitch, height, wbg, nbg, nG=nG)
            prefix = f"{shape}_P{pitch}_H{height}_W{wbg}_N{nbg}"
            
        plot_single_result(res, prefix)
        return {"Shape": shape, "Pitch": pitch, "Height": height, "WBG": wbg, "NBG": nbg,
                "J_wbg": res.get('J_wbg'), "J_nbg": res.get('J_nbg'), "J_match": res.get('J_match'), "Status": "Success"}
    except Exception as e:
        return {"Shape": shape, "Pitch": pitch, "Height": height, "WBG": wbg, "NBG": nbg,
                "J_wbg": None, "J_nbg": None, "J_match": None, "Status": f"Error: {e}"}

def menu_5_execute():
    tasks = []
    for s in SESSION_CONFIG['shapes']:
        for w in SESSION_CONFIG['t_wbg']:
            for n in SESSION_CONFIG['t_nbg']:
                if s == 'Planar': tasks.append((s, 0, 0, w, n, SESSION_CONFIG['nG']))
                else:
                    for p in SESSION_CONFIG['pitches']:
                        for h in SESSION_CONFIG['heights']:
                            tasks.append((s, p, h, w, n, SESSION_CONFIG['nG']))
    if not tasks:
        print("❓ 空任务列表"); return
        
    print(f"\n🚀 【5】总计 {len(tasks)} 个计算任务即将执行")
    ensure_dirs()
    if len(tasks) == 1:
        shape, pitch, height, wbg, nbg, nG = tasks[0]
        print(f"⚙️ 单点仿真: {shape} P={pitch} H={height} W={wbg} N={nbg}")
        res = calculate_planar_cell(wbg, nbg) if shape == 'Planar' else calculate_fully_coupled_cell(shape, pitch, height, wbg, nbg, nG)
        print(f"\n🏆 J_match = {res['J_match']} mA/cm²")
        prefix = f"{shape}_W{wbg}_N{nbg}" if shape == 'Planar' else f"{shape}_P{pitch}_H{height}_W{wbg}_N{nbg}"
        plot_single_result(res, prefix)
        
        if shape != 'Planar':
            if input("是否附加平面基准对比出图? (y/n): ").lower() == 'y':
                rp = calculate_planar_cell(wbg, nbg)
                plot_single_result(rp, f"Planar_Base_W{wbg}_N{nbg}")
                print(f"🌟 平面基准 ({rp['J_match']}), 增益: +{(res['J_match']-rp['J_match'])/rp['J_match']*100:.2f}%")
    else:
        import multiprocessing
        cores = max(1, multiprocessing.cpu_count() - 1)
        results = []
        output_path = os.path.join(DATA_DIR, "Scan_Results.csv")
        print(f"🔄 启动 {cores} 核并行计算...")
        with ProcessPoolExecutor(max_workers=cores) as executor:
            futures = {executor.submit(worker_task, arg): arg for arg in tasks}
            for i, future in enumerate(as_completed(futures), 1):
                res = future.result()
                results.append(res)
                print(f"[{i}/{len(tasks)}] {res['Shape']} P={res['Pitch']} H={res['Height']} W={res['WBG']} N={res['NBG']} | J_match={res.get('J_match')}")
                if i % 10 == 0: pd.DataFrame(results).to_csv(output_path, index=False)
        df = pd.DataFrame(results)
        df.sort_values(by='J_match', ascending=False, inplace=True)
        df.to_csv(output_path, index=False)
        print(f"✅ 所选参数扫描完成！结果已存至: {output_path}")

def main_menu():
    ensure_dirs()
    while True:
        print_header()
        print(" 【1】 全面自检，并随时寻找/修改最佳参数 (nG收敛性测试)")
        print(" 【2】 识别可供设置的结构种类 (平面/抛物面/四棱锥/圆锥等)")
        print(" 【3】 设置结构扫描参数 (提供周期和高度自定义阵列)")
        print(" 【4】 前界面结构 - WBG/NBG 单独独立厚度扫描设置")
        print(" 【5】 开始执行配置任务 (自适应单点图像输出 / 多点自动并行寻优)")
        print(" 【0】 退出程序")
        print("-" * 60)
        
        choice = input("请输入选项执行: ").strip()
        if choice == '0':
            print("👋 再见！")
            break
        elif choice == '1':
            menu_1_convergence()
        elif choice == '2':
            menu_2_shapes()
            # 根据用户要求: 设置完2选项后，自动进入3选项（无条件）
            menu_3_dimensions()
        elif choice == '3':
            menu_3_dimensions()
        elif choice == '4':
            menu_4_thicknesses()
        elif choice == '5':
            menu_5_execute()
        else:
            print("❌ 无效。")
        input("\n按 Enter 继续...")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main_menu()
