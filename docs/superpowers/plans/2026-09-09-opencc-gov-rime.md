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

- [ ] 写测试：受控 TXT/JSON 经真实 `opencc_dict` 编译后可通过 `opencc` 转换；所有引用加项目前缀；路径穿越、缺失字典或未知结构报错。
- [ ] 写测试：四类 schema 的开关、默认值、ID、去重顺序与预期一致；无法识别的结构拒绝生成。
- [ ] 运行 `python3 -m unittest discover -s tests -v`，确认缺少生成器导致失败。
- [ ] 实现生成器，以 `json`/`pathlib`/`subprocess.run(check=True)` 处理文件与工具，用 PyYAML 读写 schema，不自写 YAML 解析器。递归重写 JSON 中 TXT 字典引用，保持转换链顺序，编译闭包内字典。
- [ ] 以各家族原 schema 的完整开关及滤镜列表为输入，只替换文字转换项；保持非文字选项与过滤器。在去重之前完成转换。
- [ ] 在真实上游执行生成，运行测试，提交 `feat: generate namespaced OpenCC and Rime schemes`。

核心断言形式：

```python
self.assertEqual(result['schema']['schema_id'], 'wubi86_gov')
self.assertEqual(result['schema']['name'], '五笔86大陆')
self.assertEqual(convert('裏', compiled_config), '里')
```

## Task 2：隔离部署与行为验证

Files: `tests/rime_probe.c`、`scripts/verify.py`、`tests/test_verify.py`。

Interfaces: `rime_probe` 接收临时 shared/user 目录、schema ID、按键和选项；输出候选文字与状态。`verify.py --upstreams PATH --package PATH` 失败返回非零。

- [ ] 先写部署与输入检查：对原/派生方案输入相同按键，比较简体候选；繁体代表字词有手工期望；检查默认状态和两态切换。
- [ ] 编译探针 `cc tests/rime_probe.c -I "$RIME_INCLUDE" "$RIME_LIBRARY" -o .cache/rime_probe`，执行检查并记录生成器尚未满足的实际失败。
- [ ] 使用 librime C API 部署隔离目录，不模拟 YAML 合并或简繁转换效果；测试资源来自公开上游及其公开依赖。
- [ ] 必须覆盖雾凇全拼、全部双拼以及其他三个家族；检查转换后重复候选。失败时区分原方案环境失效与派生适配失效，均阻止发布。
- [ ] 用实际运行版本和结果写验证记录；未经运行的平台不标为通过。
- [ ] 运行单元和集成测试，提交 `test: verify derived schemes with isolated librime`。

## Task 3：更新、打包与自动发布

Files: `scripts/release.py`、`tests/test_release.py`、`.github/workflows/release.yml`。

Interfaces: `scheduled_day(date) -> bool` 以固定 UTC 日期为锚点，日差模 3 判定；手动触发绕过日期条件。构建清单记录所有输入提交、文件摘要和工具版本。

- [ ] 写跨月、跨年日期测试，写无变化跳过及输入改变生成新版本的测试，运行确认缺失功能失败。
- [ ] 每天唤醒轻量日期门，只有三天槽位才查询上游；不把月内 `*/3` 误用为固定间隔。
- [ ] 通过固定允许列表获取公开仓库提交；下载内容与所记录提交一致；不执行转换上游的 Python 程序。
- [ ] 打包项目前缀的配置/字典、派生 schema、使用说明、许可和清单；只在全部部署与行为验证成功后发布。
- [ ] 构建任务只读权限；独立发布任务获得 contents write。并发运行互斥，不因后续失败删除已有 Release。
- [ ] 运行 `python3 -m unittest discover -s tests -v`、工作流静态检查及本地端到端构建，提交 `ci: publish validated mainland schemes every three days`。

## Task 4：用户教学与交付复核

Files: `README.md`、`docs/verification.md`、本计划。

- [ ] README 写清先装原方案、复制派生与 OpenCC 文件、加入方案列表、重新部署、简繁切换和三端路径；不加入更新通知或开发讨论。
- [ ] 验证记录写工具版本、输入提交、运行命令、通过/失败和未验证平台；维护计划复选框。
- [ ] 运行语言诊断、全部相关测试、`git diff --check`、`lens_diagnostics mode=all`，检查发布包没有私人文件或通用配置覆盖。
- [ ] 本地提交，报告提交、验证证据与仍未完成的远端 Actions/平台实测。不推送。

## 当前进度

文档基线已提交；正在核对上游接口并开始 Task 1。测试框架使用 stdlib unittest，不引入 pytest。构建中发现接口差异时先复现、补测试，再修正实现和本计划。
