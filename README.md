# OpenCCGovForRime

为 Rime 输入方案提供大陆规范繁体输出，保留简体／繁体切换。大陆版与原方案并存，不替换原方案或词库。

可以使用 Releases ZIP，也可以从仓库的 [rime/ 目录](https://github.com/soizo/OpenCCGovForRime/tree/master/rime)下载单独文件，无需运行构建脚本。

## 支持方案

- [雾凇拼音](https://github.com/iDvel/rime-ice)：全拼、自然码、智能 ABC、小鹤、拼音加加、微软、搜狗、紫光双拼。
- [朙月拼音](https://github.com/rime/rime-luna-pinyin)：标准版。
- [仓颉五代](https://github.com/rime/rime-cangjie)：标准版。
- [五笔86](https://github.com/rime/rime-wubi)：标准版。

面向鼠须管（macOS）、小狼毫（Windows）、中州韵（Linux），使用同一份转换文件。实际验证环境会随下载包一并记录。

## 安装

### 1. 安装原方案

先从上面的原方案仓库完成安装。本项目不包含原方案词库、Lua 或其他依赖。

### 2. 放入大陆版文件

在本仓库 **Releases** 页面下载 ZIP 并解压；也可以直接打开 [rime/ 目录](https://github.com/soizo/OpenCCGovForRime/tree/master/rime)，下载需要的方案文件及 `opencc/` 下全部 `govrime_*` 文件。单文件下载请选择 **Raw / Download raw file**，不要保存网页 HTML。

`rime/` 由 Actions 自动生成，请勿手动编辑；更新记录见其中的 `GENERATED.json`、`manifest.json` 和 `verification.json`。

将下载的文件放到以下位置：

- 将需要的 `*_gov.schema.yaml` 放入 Rime 用户目录。
- 将包内 `opencc/` 中的 `govrime_*` 文件放入用户目录的 `opencc/` 子目录；没有该目录时自行创建。
- 不要整体替换已有的 `opencc/` 目录，也不要删除原方案文件。

常见用户目录：

| 平台 | 用户目录 |
| --- | --- |
| 鼠须管 | `~/Library/Rime/` |
| 小狼毫 | 通常为 `%APPDATA%\Rime\`，以输入法菜单“用户文件夹”为准 |
| 中州韵（IBus） | `~/.config/ibus/rime/` |
| Linux（Fcitx5 Rime） | `~/.local/share/fcitx5/rime/` |

### 3. 启用方案

编辑用户目录的 `default.custom.yaml`，在现有 `patch/schema_list` 中加入所需 ID。例如：

```yaml
patch:
  schema_list:
    - schema: rime_ice
    - schema: rime_ice_gov
    - schema: double_pinyin_flypy_gov
```

已有该文件时，请合并条目，保留原来的其他设置，不要直接覆盖整份文件。

可选大陆版 ID：

```text
rime_ice_gov
double_pinyin_gov
double_pinyin_abc_gov
double_pinyin_flypy_gov
double_pinyin_jiajia_gov
double_pinyin_mspy_gov
double_pinyin_sogou_gov
double_pinyin_ziguang_gov
luna_pinyin_gov
cangjie5_gov
wubi86_gov
```

### 4. 重新部署并切换

执行输入法菜单中的“重新部署”，然后在方案选单中选择名称以“大陆”或“大陸”结尾的方案。

- 简体模式保持原方案的简体输出。
- 繁体模式输出大陆规范繁体。
- 朙月大陆版只提供简体和大陆规范繁体两种文字模式。
- 五笔86大陆版新增简繁开关，默认简体。

使用 Rime 方案选单中的文字模式开关切换；其他按键和基本输入方式沿用原方案。

## 转换来源与许可

采用 [TerryTian-tech 的 t2gov 转换方案](https://github.com/TerryTian-tech/OpenCC-Traditional-Chinese-characters-according-to-Chinese-government-standards)。该方案并非政府官方 OpenCC 项目，部分映射经过调整，不代表与《通用规范汉字表》完全一致。

下载包的 `licenses/` 保留相关上游许可；`manifest.json` 记录上游版本和文件校验值，`verification.json` 记录实际验证环境与结果。
