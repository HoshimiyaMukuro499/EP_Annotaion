# EP_Annotaion

A small interactive tool for annotating electrophoresis / Western-blot gel photos:
measure the distance from each band to the loading line, mark marker lanes, label
relative molecular masses, and export an annotated image plus a long-format CSV.

一个用于凝胶电泳 / Western Blot 照片的交互式标注与测量小工具：提取凝胶区域、
点击泳道与条带、测量条带中心到加样参考线的距离和条带厚度、标注 Marker 的相对
分子质量，并导出带标注的 PNG 与长表格 CSV。

## 功能

- **凝胶提取**：自动检测凝胶四角，透视校正并水平翻转；检测不准时可手动点四角。
- **泳道与条带标注**：点击泳道中心自动编号，点击条带上、下边缘完成一条带。
- **距离与厚度**：以加样参考线为基准，输出每条带的中心距离与厚度（默认 mm）。
- **Marker**：任意泳道可按 `m` 设为 Marker，可连续测量任意多条带。
- **相对分子质量**：为靠近图像边缘的 Marker 输入 kDa，在图片左/右侧生成标尺。
- **应用内裁剪**：按 `c` 框选，之后只显示框选范围内的图像。
- **导出**：标注图 PNG + 长表格 CSV（一条带一行，Marker 多条带不会互相覆盖）。
- **命令行**：支持直接指定图片、演示模式、从已有 CSV 还原重绘等。

## 环境要求

- Python 3.9+
- `opencv-python`、`numpy`、`matplotlib`
- `tkinter`（Windows / macOS 官方 Python 自带；Linux 需安装 `python3-tk`）

## 安装

```bash
pip install opencv-python numpy matplotlib
```

## 使用方法

```bash
python wb_mark_interactive.py
# 也可直接指定图片
python wb_mark_interactive.py --src 4-8_Merge.tif
```

启动后（省略 `--src` 会弹出文件选择框，默认定位在脚本所在文件夹）：

1. 自动检测凝胶四角 → 透视校正并翻转；失败或不准时加 `--manual-corners` 手动点四角。
2. **第 1 步**：点击凝胶上侧加样参考线的位置；直接按 `Enter` 用图像上边缘。
3. **第 2 步**：从左到右点击每条泳道中心，按 `Enter` 进入条带测量。
4. **第 3 步**：点击条带上边缘、再点下边缘；Marker 泳道按 `m` 标记后可连续测多条带。
5. **第 4 步**：Marker 泳道按 `k` 输入各条带的分子量（kDa），保存时也会询问。
6. 确认无误后按 `q` 保存退出。

### 常用按键

| 按键 | 作用 |
| --- | --- |
| 左键 | 设定参考线 / 添加泳道中心 / 点条带上、下边缘 |
| `Enter` / `n` | 完成当前泳道，进入下一条（最后一条不会自动保存） |
| `m` | 当前泳道设为 / 取消 Marker |
| `k` | 输入当前 Marker 各条带的分子量（kDa） |
| `s` | 跳过当前泳道（无可见条带） |
| `b` / `z` / `d` | 上一条泳道 / 撤销最后一条带 / 清空当前泳道 |
| `c` | 框选裁剪：拖出矩形后 `Enter` 应用，`Esc` 取消 |
| `f` | 重新设定加样参考线（已有距离自动重算） |
| `q` | 保存并退出 |
| `r` / 滚轮 / 方向键 | 复位视图 / 缩放 / 平移 |
| `h` / `?` | 显示 / 隐藏按键说明 |

## 命令行参数

| 参数 | 说明 |
| --- | --- |
| `--src` | 图片路径；省略时弹出文件选择框 |
| `--out-prefix` | 输出文件名前缀（默认为图片文件名） |
| `--manual-corners` | 手动点击凝胶四角 |
| `--demo` | 无交互，用预设示例生成一张标注图 |
| `--mm-per-px` | 覆盖自动估算的比例（mm/像素） |
| `--no-crop` | 不裁胶、不翻转，直接标注整张图（单位为 px） |
| `--no-flip` | 透视校正后不水平翻转 |
| `--marker-kda` | Marker 分子量，按从上到下用逗号分隔，如 `180,130,100,70,55,40,35` |
| `--from-csv` | 从已有的 `*_lane_measurements.csv` 还原并重绘，不再交互（常配合 `--marker-kda`） |

示例：给已有测量结果补加分子量标尺，无需重新点击：

```bash
python wb_mark_interactive.py --from-csv 4-8_Merge_lane_measurements.csv \
    --marker-kda "180,130,100,70,55,40,35"
```

## 输出文件

与图片同名、保存在脚本所在文件夹：

| 文件 | 内容 |
| --- | --- |
| `<前缀>_gel_flipped.png` | 提取并翻转后的凝胶（`--no-crop` 时不生成） |
| `<前缀>_lane_annotated.png` | 最终标注图 |
| `<前缀>_lane_measurements.csv` | 长表格，一条带一行；未测泳道也会保留一行并注明 `not_measured` |

CSV 主要列：`lane_index, label, is_marker, band_index, band_count,
x_center_px, x_left_px, x_right_px, y_top_px, y_bottom_px, y_center_px,
thickness_px, thickness_value, distance_px, distance_value, marker_kda,
unit, note`。

## 注意事项

- 输出文件正被 Excel / 看图软件打开时写入会失败，程序会自动改写到 `_alt` 文件并提示。
- 支持中文路径（内部使用 `imdecode` / `imencode` 读写）。
- 比例尺默认按仪器“拍摄面积 12×15 cm”估算，可用 `--mm-per-px` 覆盖。

## License

[MIT](LICENSE)
