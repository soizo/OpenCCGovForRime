# OpenCCGovForRime 需求记录

文档分工：根目录 README 面向用户，承载项目介绍和使用教学；需求、设计及开发进度保存在 docs/ 中。

项目状态：需求与[设计](superpowers/specs/2026-09-09-opencc-gov-rime-design.md)已批准，按[实施计划](superpowers/plans/2026-09-09-opencc-gov-rime.md)开发与验证。

## 目标

建立 GitHub 仓库，通过 GitHub Actions 获取上游最新 gov OpenCC 转换数据，为不同 Rime 输入方案生成“大陆规范字”版本。`__` 表示原方案名称占位，不是字面下划线。根据原方案显示名称（`schema/name`）的简繁选择名称后缀：简体用“大陆”，繁体用“大陸”；不依据默认输出或基础词库，也不是因此生成两个独立版本。保留原显示名称，直接追加“大陆”或“大陸”，不删词、不自动缩写。名称无法判断或简繁混用时，按方案明确配置；具体识别规则仍待设计。

## 首批支持范围

- 雾凇拼音及其全部双拼方案。
- 朙月拼音。
- 仓颉：采用 Rime 官方 [rime/rime-cangjie](https://github.com/rime/rime-cangjie)，仓颉五代。
- 五笔：采用 Rime 官方 [rime/rime-wubi](https://github.com/rime/rime-wubi)，五笔86。

首批清单已确认，共 11 个方案：`rime_ice`、下列七个 `double_pinyin*` 双拼方案、`luna_pinyin`、`cangjie5`、`wubi86`。暂不包含朙月语句流等衍生版、仓颉快打、五笔拼音混输、`wubi_trad`、T9、英文或反查方案。

### 上游清单核对（2026-09-09）

- `iDvel/rime-ice`：`rime_ice` 及七个双拼 `double_pinyin`、`double_pinyin_abc`、`double_pinyin_flypy`、`double_pinyin_jiajia`、`double_pinyin_mspy`、`double_pinyin_sogou`、`double_pinyin_ziguang`。另有 `t9`、英文和反查方案，不属于已确认的全拼及双拼范围。
- `rime/rime-luna-pinyin`：`luna_pinyin`、`luna_pinyin_fluency`、`luna_pinyin_simp`、`luna_pinyin_tw`、反查用途的 `luna_quanpin`。
- `rime/rime-cangjie`：`cangjie5`、`cangjie5_express`。
- `rime/rime-wubi`：`wubi86`、`wubi_pinyin`、`wubi_trad`。

兼容性发现（源码检查，尚未运行验证）：

- 最新 `luna_pinyin` 已使用传统、简化、香港、台湾四态字形选项。用户已确认派生方案收敛为“简体／大陆规范繁体”两种模式，不保留香港、台湾模式；不修改原方案。
- `cangjie5` 的 `simplification` 开关启用时输出简体，与雾凇的繁体开关方向相反。
- `wubi86` 没有简繁开关，需按已确认规则新增；`wubi_trad` 已有 `zh_trad` 开关。
- 不能将本地雾凇案例的开关名、标签范围和滤镜位置直接套用到全部方案。

## 已确认的实现结构

共用一套 OpenCC 文件，按雾凇、朙月、仓颉、五笔分别适配开关和滤镜，生成轻量继承配置。不复制完整原方案，不实现万能自动适配器。

派生方案内部 ID 统一为 `<原 schema_id>_gov`；显示名称按已确认规则追加“大陆”或“大陸”。

## 已确认的交付范围

同时面向鼠须管（macOS）、小狼毫（Windows）、中州韵（Linux）。计划三端共用产物，安装文档分别说明安装位置，并明确实际验证过的版本；支持目标不等于已完成兼容性验证。

只提供派生方案配置和所需 OpenCC 文件，用户需先安装对应原方案。不打包原方案的词库、Lua 等完整资源，避免重复维护。

## 已确认的自动更新与发布

GitHub Actions 每三天检查转换数据及原输入方案上游，并支持手动触发。相关转换数据或原方案变化时重新生成，验证通过后自动发布 Release 下载包，无需人工审核。跟踪雾凇新增双拼方案并自动纳入；兼容性验证失败时停止发布，保留上一版。每个包记录使用的上游提交版本以便追溯；验证失败不得发布。

Actions 从上游 `t2gov/` 的最新文本字表及转换配置生成、编译 Rime 所需文件，不直接依赖 `rime/` 中预编译文件的更新进度。发布前验证 Rime 兼容性；具体配置适配与依赖范围需核对后确定。

## 版本提示边界

不新增旧版原方案检测或更新通知，不主动提示用户更新原方案。发布包仍按已确认要求记录上游提交版本和实际验证版本，供追溯；不因此宣称兼容所有历史版本。

## 已确认的验证与文件安全

发布前验证：原方案与派生方案均可部署、简体输出不变、繁体符合转换预期、开关默认状态正确、转换后候选去重。任一项失败则不发布。

只新增本项目专用 OpenCC 文件，不覆盖用户已有的 `s2t.json` 等文件，避免影响其他方案。生成文件须使用项目专用命名，并同步修改配置内引用。

## 已确认的输出行为

保留原方案的简繁切换：简体输出不变，仅将繁体输出替换为大陆规范繁体。不固定为只输出繁体。原方案没有简繁开关时，允许在派生方案中新增“简／繁”开关，默认保持原方案的简繁输出模式；默认繁体时，输出大陆规范繁体。

## 指定上游

[TerryTian-tech/OpenCC-Traditional-Chinese-characters-according-to-Chinese-government-standards](https://github.com/TerryTian-tech/OpenCC-Traditional-Chinese-characters-according-to-Chinese-government-standards)

这是本项目指定的 **t2gov 转换方案来源**，不是政府发布的官方 OpenCC 项目。“获取最新标准”指跟随此上游的转换数据更新。

2026-09-09 核对上游 README 与目录：

- `t2gov/`：JSON 转换配置及 TXT 字表、词典。
- `t2gov/t2gov.json`：繁体转大陆规范繁体。
- `t2gov/t2gov_keep_simp.json`：尽量保留简体的变体；上游提示命中词典的简体仍可能转换。
- `rime/`：Rime 专用 `t2gov_keep_simp.json`，引用 `TGCharacters_keep_simp.ocd2` 与 `TGPhrases.ocd2`。
- 上游声明许可证为 Apache-2.0；分发其文件时须保留相应许可与归属。
- 上游明确说明其部分映射经过调整，不能宣称与《通用规范汉字表》完全一致。

## 本地 Rime 案例

已只读查看用户 Rime 目录中的以下配置，未修改输入法文件：

| 文件 | 继承方案 | 显示名称 |
| --- | --- | --- |
| `rime_ice_gov.schema.yaml` | `rime_ice` | 霧凇大陸 |
| `double_pinyin_flypy_gov.schema.yaml` | `double_pinyin_flypy` | 小鹤大陸 |

两个案例均使用 `__include` 继承基础方案，通过 `__patch` 追加 `simplifier@governmentize`：

- 先由基础方案的 `s2t.json` 转繁，再用 `t2gov_keep_simp.json` 转大陆规范繁体。
- 与原方案共用 `traditionalization` 开关。
- `tips: none`，`tags: [abc, number, gregorian_to_lunar]`。
- 案例是候选输出转换，不是离线重写词库。

这只是现有配置的事实记录，不代表已验证部署、转换效果或所有输入方案的兼容性。设计时需核对滤镜顺序与转换后的候选去重。

## 设计进度

- [x] 查看当前仓库、上游说明及本地案例。
- [x] 澄清命名、首批方案、更新来源与产物交付方式。
- [x] 比较实现方式并提出推荐。
- [x] 分段确认数据流、兼容性、失败处理与测试设计。
- [x] 写入经确认的设计文档。
- [x] 自查设计的完整性、一致性与范围。
- [x] 请用户审阅设计文档。
- [x] 设计批准后编写实施计划。

用户已授权自动本地提交和维护忽略规则；不推送、不创建远端仓库。不将用户私人词库、历史记录或完整 Rime 目录纳入仓库。
