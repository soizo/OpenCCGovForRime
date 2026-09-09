# OpenCCGovForRime Implementation Plan

> **For agentic workers:** 使用 executing-plans 在当前会话执行，不启动子代理。每项按测试先行、实现、验证、本地提交推进。

**Goal:** 生成并验证首批 11 个大陆规范繁体派生方案，提供三天检查与自动 Release 的工作流。

**Architecture:** Python 生成项目专用 OpenCC 配置和四类 Rime 继承补丁；真实 OpenCC 和 librime 检查产物。Actions 获取固定提交的上游，隔离构建和验证后发布，不写回用户配置。

**Tech Stack:** Python 3、PyYAML、OpenCC CLI、librime C API、GitHub Actions。

**Spec:** [设计](../specs/2026-09-09-opencc-gov-rime-design.md)

## Global Constraints

- 11 个首批方案，自动发现新增雾凇双拼；不自动纳入其他类别。
- 名称看 `schema/name`，模糊项显式配置；内部 ID 后缀 `_gov`。
- 简体输出不变，繁体大陆规范化，默认模式不变；朙月仅两态。
- 不覆盖原方案或通用 OpenCC 文件；不读取私人 Rime 数据。
- 三端共同产物；三天检查，手动可触发；验证失败不得发布。
- 用户已授权自动本地提交和忽略规则；不推送、不启动子代理。

## Task 1：OpenCC 编译与方案生成

Files: `scripts/generate.py`、`tests/test_generate.py`、`requirements.txt`。

Interfaces: `compile_opencc(source: Path, target: Path) -> None`、`generate_schema(source: dict, family: str, suffix: str) -> dict`。CLI 接收 `--upstreams` 和全新 `--output` 目录。

- [x] 写受控 TXT/JSON 编译、正规化、命名前缀和路径穿越测试；未知配置或缺失字典时失败。
- [x] 写四类 schema 的开关、默认值、ID、去重顺序与未知结构测试。
- [x] 运行测试确认生成器缺失导致失败，再实现生成器。
- [x] 使用 stdlib 和 PyYAML，递归编译字典闭包，保留转换链顺序；仅读取适配所需的顶层 YAML 块。
- [x] 保持非文字选项与过滤器，在去重之前完成转换；顶层声明 schema ID 供部署器读取。
- [x] 在真实上游生成 11 个方案并提交，另提交部署前 ID 检查的修复。

受控测试字表验证 `神裏` → `神里`，用于检查两个转换阶段是否都被执行；这不是上游实际规范映射。真实字形预期及命令见[验证记录](../../verification.md)。

## Task 2：隔离部署与行为验证

Files: `tests/rime_probe.c`、`scripts/verify.py`、`tests/test_verify.py`。

Interfaces: `rime_probe` 接收临时 shared/user 目录、schema ID、按键和选项；输出候选文字与状态。`verify.py --upstreams PATH --package PATH` 失败返回非零。

- [x] 编写候选比对、规范字预期、默认状态和两态模式检查，先看到失败再修复。
- [x] 编译 C API 探针，复现并修复顶层 ID 缺失及测试基础 OpenCC 配置不兼容的问题。
- [x] 使用公开依赖和隔离 shared/user 目录真实部署；补充固定的官方 OpenCC ver.1.1.9 测试基线。
- [x] 在官方 librime 1.17.0 和鼠须管附带的 1.16.0 上，各验证全部 11 个方案。
- [x] 将实际验证范围、输入版本和未验证项目写入验证记录。
- [x] 完成单元与集成测试，纳入本地提交。

## Task 3：更新、打包与自动发布

Files: `scripts/release.py`、`tests/test_release.py`、`tests/test_workflow.py`、`.github/workflows/release.yml`。

Interfaces: `scheduled_day(date) -> bool` 以固定 UTC 日期为锚点，日差模 3 判定；手动触发绕过日期条件。构建清单记录所有输入提交、文件摘要和工具版本。

- [x] 测试跨月、跨年日期及数据变化指纹；验证缺失功能、验证后篡改、上传失败等失败路径。
- [x] 每日轻量日期门按三天间隔放行，手动触发可绕过日期门。
- [x] 从固定仓库清单获取公开提交并记录；不执行 gov 上游转换程序。
- [x] 打包项目专用文件、许可和清单；验证结果绑定包文件摘要，失败禁止打包。
- [x] 构建与发布权限分离、运行互斥；草稿上传完成后再公开，失败可恢复。
- [x] 通过单元测试、actionlint、本地端到端构建及 ZIP 摘要核验，纳入本地提交。

## Task 4：用户教学与交付复核

Files: `README.md`、`docs/verification.md`、本计划。

- [x] README 仅提供用户安装和使用教学，开发记录放在 docs/。
- [x] 写入工具版本、输入提交、命令、验证边界和本地包摘要。
- [x] 运行语言诊断、相关测试、工作流检查及 ZIP 内容和摘要检查。
- [x] 本地提交交付；不推送，远端 Actions 与 Windows/Linux 客户端实测保持未完成状态。

## 当前进度

本地实现、测试和打包已完成。交付物为 `dist/OpenCCGovForRime.zip`（Git 忽略的构建产物），详细证据见[验证记录](../../verification.md)。用户推送后可手动运行 Actions 首次发布；本次没有创建远端仓库或推送。
