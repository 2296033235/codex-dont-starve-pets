# 威尔逊桌宠 · 官方素材清单（节点①：官方贴图提取完成）

## 解码器状态

- `official/ktex.py`：纯 Python KTEX 解码器，依据开源工具 `ktech`（nsimplex，GPL）的格式定义实现。
- 容器结构：`KTEX` + 32 位字段（platform/compression/texture_type/mipmap_count/flags/fill）+ 每级 mip 的
  `u16 width, u16 height, u16 pitch, u32 datasize` 表 + 连续 S3TC 数据。
- 验收：模组 `screecher/images/hud/map.tex` 与同名 `map.png` 逐像素比对，解码结果干净无噪点（仅整体旋转 180°，
  说明游戏纹理按自下而上存储，解码后需垂直翻转）。
- 因此 `wilson_atlas_*.tex` 的解码流程为：解析 mip 表 → 取 mip0 → 标准 DXT5 解码 → 垂直翻转。

## 已提取文件

| 文件 | 说明 |
| --- | --- |
| `wilson_atlas_ds.png` | 单机版威尔逊官方贴图集（2048×1024，225 个部件） |
| `wilson_atlas_dst.png` | 联机版威尔逊官方贴图集（2048×1024，205 个部件） |
| `parts_ds/`, `parts_dst/` | 切分出的部件 PNG，附 `manifest.json`（坐标、尺寸、像素数） |
| `parts_contact_ds.png`, `parts_contact_dst.png` | 部件接触表 |
| `wilson_portrait.png`, `wilson_portrait_dst.png` | 官方立绘（1024×1024，已纠正方向） |
| `palette_ds.json`, `palette_dst.json` | 主色板（按占比排序） |
| `inventory.json` | 全部动画名清单（单机版 / 联机版） |
| `material_preview.png` | 预览图（立绘 + 部件接触表） |

色板主色：纯黑描边、奶白/浅灰（皮肤与衬衫）、灰蓝阴影，点缀色为暗红棕（马甲 `#AC403B` 左右）、
橄榄棕（道具木质 `#786F4C` 左右）。

## 动画清单要点（决定图集每一行用哪段官方动作）

单机版：

- 走路：`player_basic.zip` → `run_pre / run_loop / run_pst`
- 待机：`player_idles.zip` → `idle` / `idle_loop`
- 精神崩溃：`player_idles.zip` → `idle_sanity_pre / idle_sanity_loop`，以及 `idle_inaction_sanity`
- **制作物品：`player_actions_item.zip` → `build_pre / build_loop / build_pst`**（原计划里担心的缺失项，实际存在）
- 发呆小动作：`player_idles.zip` → `idle_inaction`
- 其它可用小动作：`hungry`（捂肚子）、`mime1-8`、`dial_loop`、`jump`

联机版：

- 威尔逊专属待机：`player_idles_wilson.zip` → `idle_wilson` / `idle_wilson_beard`（掏耳朵首选候选）
- 官方招手：`player_emotes.zip` → `emote_waving`（掏耳朵找不到时的兜底）
- 研究/思考：`player_actions.zip` → `research`

## 下一步（节点②）

1. 用开源 `ktools/krane` 的格式定义（或联网找现成实现）解析 `anim.bin`，把候选动作渲染成关键姿势参考条：
   `run_loop`、`build_pre/loop/pst`、`idle_sanity_loop`、`idle_inaction`、`idle_wilson`。
2. 从参考条里确认「掏耳朵」出现在 `idle_inaction` 还是 `idle_wilson`，记录起止帧。
3. 产出「图集行 → 官方动作 + 关键帧」映射表、参考帧条、生成提示词草案，然后通知节点②并暂停。
