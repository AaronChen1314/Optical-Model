# 本地光学模拟与分析 Web App

这是一个本地运行的 Flask 光学模拟工作台，复用当前目录中的 TMM、RCWA、材料数据库和温度依赖数据。浏览器负责结构编辑、图表和项目保存，TMM/RCWA 计算在本机 Python 环境中执行。

## 启动

```powershell
python app.py
```

打开：

```text
http://127.0.0.1:5001
```

## 主要功能

- TMM：支持默认全钙钛矿叠层、钙钛矿-硅叠层，以及用户自定义多层结构。
- RCWA：支持现有钙硅叠层的 Planar、Paraboloid、Pyramid、Cone 结构，并通过后台任务运行。
- 对比：同一参数下运行 TMM 和 RCWA，绘制活性层吸收差异。
- 材料：统一加载现有 `data` 文件，支持校验用户上传的 `wavelength_nm,n,k` CSV/TXT。
- 温度扫描：解析受限 `Eg(T)` 表达式，执行 k 值能量平移和离散 KK 近似后重新计算 TMM。
- 导出：图表 PNG/SVG/打印为 PDF，结果 CSV，项目 JSON。

## 验证

```powershell
python -m unittest discover -s tests
```

