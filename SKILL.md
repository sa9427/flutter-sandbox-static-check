---
name: flutter-sandbox-static-check
description: >-
  Flutter 工程静态体检（九板斧 / "Nine-Axe" static checker）。在无法运行
  flutter/dart 的环境（如 WorkBuddy 沙箱、未装 SDK 的 CI 节点）中，用纯文本分析替代
  flutter analyze，对 lib/ 做 10 项编译期硬错检查：断 import、pubspec 依赖一致性、相对导入残留、
  枚举值存在性、assets 引用缺失、命名参数拼写、未使用 import（含 dart: 内建库）、括号平衡、字符串型枚举残留、未用依赖。
  Flutter/Dart static checker that runs without the Dart SDK: 10 compile-time
  checks (broken imports, dependency consistency, relative-import leftovers, enum
  value existence, asset references, named-arg spelling, unused imports incl.
  dart: core libs, bracket balance, string-enum residue, unused deps).
---

# Flutter 沙箱静态体检（九板斧）
# Flutter Sandbox Static Check ("Nine-Axe")

## 背景与用途 / Background & Purpose

WorkBuddy 沙箱无法运行 `flutter` / `dart`（Windows 子进程管道 `ERROR_PIPE_BUSY 231`），
但改完 Dart 代码仍需验证不会引入编译期错误。本 skill 用**纯文本静态分析**替代 `flutter analyze`，
对 Flutter 工程的 `lib/` 目录做十板斧体检，覆盖那些最常见、最致命的编译期硬错。
The WorkBuddy sandbox cannot run `flutter` / `dart` (Windows subprocess pipe
`ERROR_PIPE_BUSY 231`), yet edited Dart code still must be verified to avoid
compile-time errors. This skill replaces `flutter analyze` with **pure-text
static analysis**, running ten checks over the project's `lib/` directory to
catch the most common and most fatal compile errors.

## 运行方式 / How to Run

自带脚本，**零第三方依赖**（纯 Python 标准库）：
The bundled script has **zero third-party dependencies** (pure Python stdlib):

```bash
python3 <skill_dir>/check.py --project C:/code/fitcoach
```

- 默认 `--project` 为 `C:/code/fitcoach`；也可指向任意 Flutter 工程根目录
  （脚本自动定位 `lib/` 与 `pubspec.yaml`，并**跳过生成文件** `*.g.dart` / `*.freezed.dart` / `build/` / `.dart_tool/`）。
  Default `--project` is `C:/code/fitcoach`; it also accepts any Flutter project
  root (auto-detects `lib/` and `pubspec.yaml`, and **skips generated files**
  `*.g.dart` / `*.freezed.dart` / `build/` / `.dart_tool/`).
- 输出分两级 / Output has two severity levels:
  - **ERROR**：几乎必然是编译错误（如断 import、引用不存在的枚举值、未声明依赖），必须先修。
    Almost certainly a compile error (broken import, non-existent enum value,
    undeclared dependency) — must be fixed first.
  - **HINT**：启发式告警，可能误报，需人工确认。
    Heuristic warning, may be a false positive — needs human confirmation.
- 结尾打印 / Prints at the end:
  `RESULT: 工程干净 ✅` 或 / or `RESULT: 发现 N 处问题 ⚠️`.

## 十板斧检查项 / The Ten Checks

1. **断 import（ERROR）** / **Broken import**: 解析 `package:fitcoach/...`，确认目标 `.dart` 文件存在。
   Resolves `package:fitcoach/...` and confirms the target `.dart` file exists.
2. **pubspec 依赖一致性（ERROR）** / **pubspec dependency consistency**: `import 'package:X/...'` 的 `X` 必须在 `pubspec.yaml` 的 `dependencies`/`dev_dependencies` 中声明。
   The `X` in `import 'package:X/...'` must be declared in `pubspec.yaml`'s `dependencies`/`dev_dependencies`.
3. **相对导入残留（ERROR）** / **Relative-import leftover**: 工程约定统一用 `package:` 绝对导入；出现 `../` 或 `./` 即告警。
   Project convention uses `package:` absolute imports; any `../` or `./` triggers a warning.
4. **枚举值存在性（ERROR/HINT）** / **Enum value existence**: 收集 `enum` 全部成员（含一行多值 `light, medium, hard;`），扫描 `Enum.value` / `Enum.values.byName('value')`，标出不存在的值。
   Collects all `enum` members (incl. one-line multi-value `light, medium, hard;`), scans `Enum.value` / `Enum.values.byName('value')` for missing values.
5. **assets 引用缺失（HINT）** / **Missing asset reference**: `pubspec` 的 `assets:` 与代码中 `AssetImage`/`rootBundle.load`/`exact` 引用交叉核对。
   Cross-checks `pubspec`'s `assets:` against `AssetImage`/`rootBundle.load`/`exact` references in code.
6. **命名参数拼写（HINT）** / **Named-arg spelling**: 对小写业务函数调用，检查命名参数是否真在签名中声明；内置 Flutter 框架参数 + 工程自定义参数白名单降噪。
   For lowercase business-function calls, checks whether named args are really declared in the signature; a whitelist of built-in Flutter params + project params reduces noise.
7. **未使用 import（HINT）** / **Unused import**:
   - `as prefix`：从未以 `prefix.` 引用 → 判未用（精确）。
     `as prefix` never referenced as `prefix.` → unused (precise).
   - `show {..}`：所列符号均未出现 → 判未用（精确）。
     `show {..}` symbols never appear → unused (precise).
   - `dart:` 内建库：维护公开符号表，符号均未出现 → 判未用（**v2 新增，修复此前对 dart: 直接跳过导致的漏报**）。
     `dart:` core libs: a public-symbol table is maintained; if none appear → unused (**added in v2, fixing the earlier miss where `dart:` was skipped entirely**).
   - 工程内 `package:fitcoach/`：目标文件顶层符号均未被引用 → 判未用。
     In-project `package:fitcoach/`: if none of the target file's top-level symbols are referenced → unused.
   - 外部 package（无 as/show）：未知导出符号，跳过以免误报。
     External packages (no as/show): unknown exports, skipped to avoid false positives.
8. **括号/结构平衡（HINT）** / **Bracket/structure balance**: **v2 重写**——只数 `()[]{}`，忽略尖括号 `<>`（泛型/比较/`=>`）与字符串/三引号/插值，消除此前对全部文件误报。
   **Rewritten in v2** — only counts `()[]{}`, ignoring angle brackets `<>` (generics/comparison/`=>`) and strings/triple-quotes/interpolation, eliminating the earlier file-wide false positives.
9. **字符串型枚举残留（HINT）** / **String-enum residue**: 检查枚举是否被当裸字符串误用。
   Checks whether an enum is mistakenly used as a bare string.
10. **未用依赖（HINT）** / **Unused dependency**: `pubspec` 声明的运行时依赖若无任何文件 `import`，提示可能未使用（**v2 新增，借鉴 flutter_analyzer_script**）。
    A runtime dependency declared in `pubspec` that no file imports may be unused (**added in v2, inspired by flutter_analyzer_script**).

## 设计借鉴（开源精华）/ Design Inspiration (from Open Source)

- **dart-re-analyzer / pedant**：severity 分级 + 跳过生成文件（`*.g.dart` 等）。
  severity levels + skipping generated files (`*.g.dart`, etc.).
- **flutter_analyzer_script / refactoroscope**：unused 的"声明-引用"判定思路。
  the "declare-vs-reference" reasoning for unused detection.
- 本工具仅吸取**概念与思路**，未复制任何第三方代码；如将来引入具体实现，须遵守对应许可证并保留署名。
  This tool borrows **concepts and ideas only**, copying no third-party code; any future concrete implementation must comply with the relevant license and retain attribution.

## 使用纪律 / Usage Discipline

- 这是**静态近似，不是编译器**：ERROR 基本可信，HINT 可能误报，需结合人工判断。
  This is a **static approximation, not a compiler**: ERROR is mostly trustworthy, HINT may be a false positive and needs human judgement.
- 每次改完 Dart 代码跑一遍，确认 `RESULT: 工程干净 ✅` 后再提交。
  Run it after every Dart edit; only commit once `RESULT: 工程干净 ✅` is confirmed.
- 权威终验仍以用户原生终端的 `flutter analyze` 为准（沙箱跑不了 flutter）。
  The authoritative final check remains `flutter analyze` on the user's native terminal (the sandbox cannot run flutter).

## 与 FitCoach 项目 / Relation to FitCoach

FitCoach 代码根：`C:\code\fitcoach`（本机；另一台开发机为 `D:\code\fitcoach`）。
`flutter` 必须在用户原生终端跑；本 skill 只在沙箱里做改前/改后的静态复验。
FitCoach code root: `C:\code\fitcoach` (this machine; the other dev machine is `D:\code\fitcoach`).
`flutter` must run on the user's native terminal; this skill only does pre/post-edit static re-checks inside the sandbox.
本 skill 已纳入 git 管理并推送至 GitHub，多设备通过 clone 保持一致（见仓库 README）。
This skill is git-managed and pushed to GitHub; multiple devices stay in sync via clone (see the repo README).
