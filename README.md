# EP_Annotaion

A small interactive tool for annotating gel electrophoresis photos:
measure the distance from each band to the loading line, mark marker lanes, label
relative molecular masses, and export an annotated image plus a long-format CSV.

一个用于凝胶电泳照片的交互式标注与测量小工具：直接标注原图
（可选 `--rectify` 自动提取凝胶区域、`--flip` 翻转）、点击泳道与条带、测量条带
中心到加样参考线的距离和条带厚度、标注 Marker 的相对分子质量、标注指示剂前沿
（dye front），并导出带标注的 PNG 与长表格 CSV。

## 功能

- **直接使用原图**：默认不裁胶、不翻转，打开什么图就标注什么图。
- **可选凝胶提取**：加 `--rectify` 自动检测凝胶四角并透视校正，`--flip` 水平翻转，
  检测不准时用 `--manual-corners` 手动点四角。
- **泳道与条带标注**：点击泳道中心自动编号，点击条带上、下边缘完成一条带。
- **距离与厚度**：以加样参考线为基准，输出每条带的中心距离与厚度（默认 mm）。
- **Marker**：任意泳道可按 `m` 设为 Marker，可连续测量任意多条带。
- **相对分子质量**：为靠近图像边缘的 Marker 输入 kDa，在图片左/右侧生成标尺。
- **指示剂前沿（dye front）**：按 `t` 点击指示剂前沿位置，全图绘制一条横贯的虚线，
  并标注其到加样参考线的距离（mm）。
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
python gel_mark_interactive.py
# 也可直接指定图片
python gel_mark_interactive.py --src 4-8_Merge.tif
```

启动后（省略 `--src` 会弹出文件选择框，默认定位在脚本所在文件夹）：

1. 默认直接使用原图；需要提取凝胶区域时加 `--rectify`（--manual-corners 手动点四角），需要左右翻转时加 `--flip`。
2. **第 1 步**：点击凝胶上侧加样参考线的位置；直接按 `Enter` 用图像上边缘。
3. **第 2 步**：从左到右点击每条泳道中心，按 `Enter` 进入条带测量。
4. **第 3 步**：点击条带上边缘、再点下边缘；Marker 泳道按 `m` 标记后可连续测多条带。
5. **第 4 步**：Marker 泳道按 `k` 输入各条带的分子量（kDa），保存时也会询问。
6. 需要时按 `t` 标注指示剂前沿（dye front）：点击前沿位置即可，`Delete` 可删除。
7. 确认无误后按 `q` 保存退出。

### 常用按键

| 按键 | 作用 |
| --- | --- |
| 左键 | 设定参考线 / 添加泳道中心 / 点条带上、下边缘 |
| `Enter` / `n` | 完成当前泳道，进入下一条（最后一条不会自动保存） |
| `m` | 当前泳道设为 / 取消 Marker |
| `k` | 输入当前 Marker 各条带的分子量（kDa） |
| `s` | 跳过当前泳道（无可见条带） |
| `t` | 标注指示剂前沿（dye front）；进入后点击位置，`Delete` 删除，`Esc` 取消 |
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
| `--rectify` | 自动检测凝胶四角并透视校正（默认关闭，直接用原图） |
| `--manual-corners` | 手动点击凝胶四角（隐含 `--rectify`） |
| `--flip` | 水平翻转图像（默认不翻转） |
| `--demo` | 无交互，用预设示例生成一张标注图 |
| `--mm-per-px` | 覆盖比例（mm/像素）；未用 `--rectify` 时给出才会以 mm 为单位 |
| `--no-crop` | （兼容旧参数）等同于默认行为：不自动提取凝胶区域 |
| `--no-flip` | （兼容旧参数）不翻转；现在默认就不翻转 |
| `--marker-kda` | Marker 分子量，按从上到下用逗号分隔，如 `180,130,100,70,55,40,35` |
| `--from-csv` | 从已有的 `*_lane_measurements.csv` 还原并重绘，默认不再交互（常配合 `--marker-kda`） |
| `--edit` | 配合 `--from-csv`：打开交互窗口继续手动编辑（泳道、条带、kDa 全部保留），`q` 保存 |
| `--dye-front-mm` | 指示剂前沿距加样参考线的距离（mm），与 `--from-csv` 配合可直接补标 |
| `--dye-front-px` | 指示剂前沿的 y 像素坐标（凝胶图内），优先级高于 `--dye-front-mm` |
| `--crop-rect x0,y0,x1,y1` | 配合 `--from-csv`：手动指定旧结果的裁剪区域（像素坐标） |

示例：给已有测量结果补加分子量标尺，无需重新点击：

```bash
python gel_mark_interactive.py --from-csv 4-8_Merge_lane_measurements.csv \
    --marker-kda "180,130,100,70,55,40,35"
```

**推荐：打开已有结果手动补标指示剂前沿**（不用自己量，直接点）：

```bash
python gel_mark_interactive.py --from-csv 4-8_Merge_lane_measurements.csv --edit
```

打开后原有的泳道、条带、分子量都在，程序停在「③ 测量条带」：
按 `t` → 在指示剂前沿位置点一下 → 按 `q` 保存，同名的 CSV / PNG 会被更新。
`Delete` 可移除已标的前沿，`Esc` 取消本次设置。

示例：给已有结果补标指示剂前沿（距离单位 mm，从加样参考线量起，无需打开界面）：

```bash
python gel_mark_interactive.py --from-csv 4-8_Merge_lane_measurements.csv \
    --dye-front-mm 32.5
```

也可以用像素坐标（y 值，越大越靠下）：

```bash
python gel_mark_interactive.py --from-csv 4-8_Merge_lane_measurements.csv \
    --dye-front-px 496
```

多个参数可以叠加，例如同时补分子量与指示剂前沿：

```bash
python gel_mark_interactive.py --from-csv 4-8_Merge_lane_measurements.csv \
    --marker-kda "180,130,100,70,55,40,35" --dye-front-mm 32.5
```

> 注意：`--from-csv` 会重写同名的 `*_lane_measurements.csv` 和 `*_lane_annotated.png`，
> 运行前请先关闭 Excel / 看图软件；若文件被占用，程序会自动写到 `_alt` 文件。
> 生成后再次读取该 CSV 时会自动保留指示剂前沿。

> **关于应用内裁剪（`c`）**：新版 CSV 会记录 `img_x0_px / img_y0_px / img_w_px /
> img_h_px`。旧版结果如果当年按 `c` 裁剪过，`--from-csv` / `--edit` 会自动从
> `*_lane_annotated.png` 反推裁剪区域并精确复位；自动恢复失败时会给出警告，
> 可用 `--crop-rect x0,y0,x1,y1` 手动指定（坐标相对 `<前缀>_gel*.png`）。

## 输出文件

与图片同名、保存在脚本所在文件夹：

| 文件 | 内容 |
| --- | --- |
| `<前缀>_gel.png` | 实际用于标注的图（未翻转；`--from-csv` 还原时使用） |
| `<前缀>_gel_flipped.png` | 实际用于标注的图（已翻转） |
| `<前缀>_lane_annotated.png` | 最终标注图 |
| `<前缀>_lane_measurements.csv` | 长表格，一条带一行；未测泳道也会保留一行并注明 `not_measured` |

CSV 主要列：`lane_index, label, is_marker, band_index, band_count,
x_center_px, x_left_px, x_right_px, y_top_px, y_bottom_px, y_center_px,
thickness_px, thickness_value, distance_px, distance_value, marker_kda,
dye_front_px, dye_front_value,
img_x0_px, img_y0_px, img_w_px, img_h_px, unit, note`
（含有指示剂前沿的图，所有行都会填上 `dye_front_px` / `dye_front_value`；
`img_*` 记录应用内裁剪区域，便于下次精确还原）。

## 注意事项

- 输出文件正被 Excel / 看图软件打开时写入会失败，程序会自动改写到 `_alt` 文件并提示。
- 支持中文路径（内部使用 `imdecode` / `imencode` 读写）。
- 用 `--rectify` 自动提取凝胶时，比例尺按仪器“拍摄面积 12×15 cm”估算，可用 `--mm-per-px` 覆盖；
  直接用原图时默认单位为像素，给出 `--mm-per-px` 才会换算成 mm。

## License

[MIT](LICENSE)
