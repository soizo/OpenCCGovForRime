# 构建与验证

## 已验证范围（2026-09-09）

在 macOS 26.6.2 arm64 上，使用 OpenCC 1.4.2 构建，并在两套含 Lua 的运行库上分别完成全部 11 个方案的隔离部署和候选检查：

- 官方 librime 1.17.0：11/11 通过。
- 本机鼠须管附带的 librime 1.16.0：11/11 通过，未操作正在使用的输入法或其用户目录。

11 项单元/工作流行为测试、actionlint 和语言诊断通过。

每个方案均验证原版与派生版可部署、简体前 50 个候选保持不变、繁体包含预期规范字、繁体前 50 个候选不重复、默认文字模式正确。测试通过 C API 设置文字模式，不是客户端选单的 GUI 自动化测试，也不是对所有字词的穷举验证。

| 方案 | 输入 | 繁体预期候选 |
| --- | --- | --- |
| 雾凇全拼、朙月 | `wei` | `爲` |
| 自然码、微软、搜狗双拼 | `wz` | `爲` |
| 智能 ABC 双拼 | `wq` | `爲` |
| 小鹤、拼音加加双拼 | `ww` | `爲` |
| 紫光双拼 | `wk` | `爲` |
| 仓颉五代 | `oikf` | `僞` |
| 五笔86 | `wyl` | `僞` |

尚未完成 Windows/Linux 客户端实测、三端 GUI 交互验证或 GitHub 托管环境中的工作流执行。远端发布需要用户推送仓库并启用 Actions；本次不推送。

## 本地交付包

- 文件：`dist/OpenCCGovForRime.zip`，共 27 个文件，1,000,687 字节。
- SHA-256：`8e87a34d0f625fa6dd2252cdf93989434819f42a7a6cceeb78dbb3eb33f3d574`。
- 已核对 ZIP 内每个文件的 SHA-256 与清单、验证报告一致；包内报告来自官方 librime 1.17.0。
- ZIP 属于生成产物，不提交到 Git；后续运行的 ZIP 时间戳和摘要可能不同。

## 输入版本

| 上游 | 本次提交 |
| --- | --- |
| TerryTian-tech gov 数据 | `826fdc1f9e70ca0fdd2755f215107786ba59e4bc` |
| 雾凇 | `fbb516b2786e4d5444383706d13c31c2e4d10c08` |
| 朙月 | `56b934b099dfbeab842320f13aa8b461a6ab3e42` |
| 仓颉 | `52d90a1b1312e74042b38c1cbc8142defbc53171` |
| 五笔 | `152a0d3f3efe40cae216d1e3b338242446848d07` |
| OpenCC 测试基线 ver.1.1.9 | `556ed22496d650bd0b13b6c163be9814637970ae` |

包内 `manifest.json` 还记录 prelude、stroke、pinyin-simp、essay 等公开测试依赖的提交，以及所有包文件的 SHA-256。`verification.json` 绑定同一组文件摘要；验证后修改文件会导致打包失败。

## 本地复现（macOS）

需要 Python 3.12、OpenCC CLI、C 编译器和 `gh`。安装 Python 依赖：

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

获取公开上游到一个尚不存在的目录；不读取本机 Rime 用户目录：

```sh
mkdir -p .cache
UPSTREAMS=/path/to/fresh/upstreams
python3 scripts/release.py fetch "$UPSTREAMS" .cache/revisions.json
```

`fetch` 默认获取当前上游，因而未来运行的提交可能与上表不同。报告与包内清单以当次实际提交为准。

下载并校验固定的官方运行库：

```sh
mkdir -p .cache/runtime
archive=rime-33e7814-macOS-universal.tar.bz2
gh release download 1.17.0 --repo rime/librime \
  --pattern "$archive" --dir .cache/runtime
(cd .cache/runtime && \
  echo "11d8dc663c6ec06d5ccb6111ba664a9e7b631b703ac6acd07cffbac664021850  $archive" | \
  shasum -a 256 -c - && tar -xjf "$archive")
runtime="$PWD/.cache/runtime/dist"
cc -Wall -Wextra -Werror tests/rime_probe.c -I "$runtime/include" \
  "$runtime/lib/librime.1.dylib" \
  "$runtime/lib/rime-plugins/librime-lua.dylib" \
  -Wl,-rpath,"$runtime/lib" -Wl,-rpath,"$runtime/lib/rime-plugins" \
  -o .cache/rime_probe
```

生成、验证、打包：

```sh
python3 scripts/generate.py --upstreams "$UPSTREAMS" --output .cache/package
python3 scripts/verify.py --upstreams "$UPSTREAMS" --package .cache/package \
  --probe .cache/rime_probe --report .cache/verification.json
python3 scripts/release.py pack .cache/package .cache/verification.json \
  .cache/revisions.json dist/OpenCCGovForRime.zip
```

上游目录、生成目录和 ZIP 输出要求尚不存在，防止覆盖已有内容。重复运行时换用新路径。生成器不会删除旧目录。

## 自动发布与静态检查

工作流：`.github/workflows/release.yml`。

- 每日 UTC 03:17 唤醒日期检查，以 2026-09-09 为锚点，每三天才执行上游检查；支持手动触发。GitHub 可能延迟或跳过定时任务，不保证精确到时刻。
- 上游有效数据和本项目构建代码未变化时跳过重新发布。
- push/PR 执行检查但不发布；只有默认分支的定时/手动运行可发布。
- 构建任务仅持有只读仓库权限；独立发布任务获得写权限。
- 先上传到草稿 Release，上传成功后再公开；上传失败保留草稿和上一版，重试可以继续。

工作流检查命令：

```sh
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 .github/workflows/release.yml
git diff --check
```

`tests/test_workflow.py` 用本地假远端执行发布 shell，验证上传失败不会公开空包、重试能恢复；它不代表 GitHub API 已被实际调用验证。

## 已定位并覆盖的问题

1. Rime 在展开继承前读取顶层 `schema_id`，不能只将 ID 放在 `__patch` 中；生成器现提供顶层方案信息，真实部署检查覆盖该路径。
2. 本机 OpenCC 1.4 的默认配置不能直接充当这些 Rime 运行库的内置转换基线。测试改为从官方 OpenCC ver.1.1.9 编译经典配置所需字典，且任何 OpenCC 加载错误直接失败。这不改变发布包使用的最新 gov 数据，也不覆盖用户原来的基础转换文件。
3. 新版 gov 配置的 normalization 必须在 Rime 转换路径中执行；生成器将其放入转换链，并用实际 OpenCC 转换验证相容字正规化。
