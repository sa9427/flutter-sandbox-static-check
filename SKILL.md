---
name: flutter-sandbox-static-check
description: >-
  Flutter 工程静态体检（九板斧 / "Nine-Axe" static checker，v3 起 12 项）。在无法运行
  flutter/dart 的环境（如 WorkBuddy 沙箱、未装 SDK 的 CI 节点）中，用纯文本分析替代
  flutter analyze，做 12 项检查（默认含 test/）：断 import、pubspec 依赖一致性、相对导入残留、
  枚举值存在性、assets 引用缺失、命名参数拼写、未使用 import（含 dart: 内建库）、括号平衡、
  字符串型枚举残留、未用依赖、**符号用到但没 import**、**lint6 命名与下划线**。
  Flutter/Dart static checker that runs without the Dart SDK: 12 checks
  (test/ included by default) — broken imports, dependency consistency,
  relative-import leftovers, enum value existence, asset references, named-arg
  spelling, unused imports (incl. dart: core libs), bracket balance,
  string-enum residue, unused deps, **used-but-not-imported symbols**,
  **lint 6 naming & underscores**.
  含**强制漏报反哺机制**：宿主 flutter 报出的漏报须归类 → 补斧 → 反向验证 → 登记
  `MISSES.md`（漏报台账，唯一真源）。
  Includes a **mandatory miss-feedback loop**: escapes reported by the host must be
  classified → turned into an axe → reverse-validated → recorded in `MISSES.md`
  (escape ledger, single source of truth).
---

# Flutter 沙箱静态体检（九板斧）
# Flutter Sandbox Static Check ("Nine-Axe")

## 背景与用途 / Background & Purpose

WorkBuddy 沙箱无法运行 `flutter` / `dart`（Windows 子进程管道 `ERROR_PIPE_BUSY 231`），
但改完 Dart 代码仍需验证不会引入编译期错误。本 skill 用**纯文本静态分析**替代 `flutter analyze`，
对 Flutter 工程的 `lib/`（**v3 起默认一并体检 `test/`**）做十二板斧体检，
覆盖那些最常见、最致命的编译期硬错与 lint 6 命名问题。
The WorkBuddy sandbox cannot run `flutter` / `dart` (Windows subprocess pipe
`ERROR_PIPE_BUSY 231`), yet edited Dart code still must be verified to avoid
compile-time errors. This skill replaces `flutter analyze` with **pure-text
static analysis**, running twelve checks over the project's `lib/`
(**and `test/` by default since v3**) to catch the most common and most fatal
compile errors plus lint 6 naming issues.

## 运行方式 / How to Run

自带脚本，**零第三方依赖**（纯 Python 标准库）：
The bundled script has **zero third-party dependencies** (pure Python stdlib):

```bash
python3 <skill_dir>/check.py --project C:/code/fitcoach
# v3 起 **默认连 test/ 一起体检**；只想扫 lib/ 时加 --no-test
# Since v3, test/ is scanned **by default**; pass --no-test for lib/ only
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

## 十二板斧检查项 / The Twelve Checks

> **名称沿革 / Naming note**：skill 名「九板斧 / Nine-Axe」是历史叫法，v2 起 10 项、
> v3 起 12 项。名字保留，避免打断既有文档与项目记忆里的引用。
> The skill name "Nine-Axe" is historical — 10 checks since v2, 12 since v3.
> The name is kept so existing docs and project-memory references stay valid.

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
11. **符号用到但没 import（ERROR）** / **Used-but-not-imported symbol**: 文件里用了某符号却没 import 定义它的文件——**Dart 的 import 不传递**，A import B、B import C 时 A 拿不到 C 的符号。
    A file uses a symbol without importing the file that defines it — **Dart imports are not transitive**: if A imports B and B imports C, A does not get C's symbols.
    - **v3 新增**，起因是 2026-10-03 fitcoach 实踩：`plateau_test.dart` 用了 `VolumeTrendPoint` 却只 import 了「同样用到它的」`plateau_service.dart`，宿主 `flutter analyze` 一次报 4 个 error，而旧的 C1 只判「import 的文件是否存在」，对「压根少写一条 import」完全无感。
      **Added in v3** after a real miss: `plateau_test.dart` used `VolumeTrendPoint` but only imported `plateau_service.dart` (which itself uses it); `flutter analyze` reported 4 errors, while the old C1 only checked whether an imported file exists.
    - 降噪三道 / Three de-noising filters：`part`/`export` 传递闭包（可见符号 ≠ 定义文件）、前置 `.`（成员/枚举访问）、后置 `:`（命名实参）；再排除本文件内的声明位置（含 `this.x`、`Type name` 形参、增强枚举成员）。
      `part`/`export` transitive closure (visible ≠ defining file), leading `.` (member/enum access), trailing `:` (named arg); plus declarations inside the file itself (`this.x`, `Type name` params, enhanced-enum members).
12. **lint 6 命名与下划线（HINT）** / **lint 6 naming & underscores**:
    - 标识符含**连续下划线**（`__` / `___`）→ `unnecessary_underscores`。未用参数应写 N 个**单** `_`（`(_, _)`），不能省参数个数（会 `argument_type_not_assignable`）。
      Consecutive underscores (`__` / `___`) → `unnecessary_underscores`. Use N **single** `_` for unused params (`(_, _)`); do not drop params (causes `argument_type_not_assignable`).
    - 顶层**私有函数/变量**写成 `_UpperCamel` → `non_constant_identifier_names`。⚠️ 私有**类** `_Foo` 是合法的（类走 UpperCamelCase），已排除。
      Private top-level **functions/variables** written as `_UpperCamel` → `non_constant_identifier_names`. ⚠️ Private **classes** `_Foo` are legal and are excluded.

## 设计借鉴（开源精华）/ Design Inspiration (from Open Source)

- **dart-re-analyzer / pedant**：severity 分级 + 跳过生成文件（`*.g.dart` 等）。
  severity levels + skipping generated files (`*.g.dart`, etc.).
- **flutter_analyzer_script / refactoroscope**：unused 的"声明-引用"判定思路。
  the "declare-vs-reference" reasoning for unused detection.
- 本工具仅吸取**概念与思路**，未复制任何第三方代码；如将来引入具体实现，须遵守对应许可证并保留署名。
  This tool borrows **concepts and ideas only**, copying no third-party code; any future concrete implementation must comply with the relevant license and retain attribution.

## 反哺机制：漏报 → 补斧（强制）/ Feedback Loop: Miss → New Axe (mandatory)

宿主真跑 `flutter analyze` / `flutter test` 报出的**每一条**问题，都要先问一句：
**九板斧为什么没抓到？** 如果是漏报，就必须补斧，**不能只改业务代码就完事**——
否则同类问题会反复漏（M-001 一条漏 import 就报了 4 个 error）。

For **every** issue reported by the host's real `flutter analyze` / `flutter test`,
ask first: **why did the checker miss it?** If it is a miss, add/improve an axe.
Never just fix the business code — otherwise the same class of bug keeps escaping.

完整流程与台账见 **`MISSES.md`**（漏报的唯一真源，含每条的最小复现）。
Full workflow and the ledger live in **`MISSES.md`** (single source of truth for
escapes, with a minimal repro per entry).

六步闭环 / Six-step loop：
1. **确认是漏报**——九板斧复跑该文件（默认已含 `test/`），确认零告警。
2. **归类**——检查项**缺失**（新增一斧）／被**降噪滤掉**（收紧过滤）／**口径不对**（修正逻辑）。
3. **补/改** `check.py`，同步 `SKILL.md` / `README.md` 的清单与计数。
4. **反向验证（强制）**——把问题代码临时改回原样 → 跑九板斧 → 确认新斧命中 →
   **还原** → `git status` 为空 + 复跑干净。**没做这步等于没验证。**
5. **登记 `MISSES.md`**——务必写清最小复现。
6. **commit**（默认只 commit 不 push）。

⚠️ **改动过滤/降噪规则时，必须回看 `MISSES.md` 并重跑相关复现**：
降噪改宽是「已闭环漏报悄悄复发」的头号原因。
When touching filters, re-read `MISSES.md` and re-run the affected repros:
loosening de-noising is the #1 cause of closed escapes silently returning.

## 使用纪律 / Usage Discipline

- 这是**静态近似，不是编译器**：ERROR 基本可信，HINT 可能误报，需结合人工判断。
  This is a **static approximation, not a compiler**: ERROR is mostly trustworthy, HINT may be a false positive and needs human judgement.
- 每次改完 Dart 代码跑一遍，确认 `RESULT: 工程干净 ✅` 后再提交。
  Run it after every Dart edit; only commit once `RESULT: 工程干净 ✅` is confirmed.
- **宿主复验报了问题就走反哺流程**（见上一节 `MISSES.md`）：先判断是不是漏报，
  是漏报就补斧 + 反向验证 + 登记台账。
  When the host's verification reports an issue, run the feedback loop (see
  `MISSES.md`): decide whether it was a miss; if so, add an axe, reverse-validate,
  and record it in the ledger.
- 权威终验仍以用户原生终端的 `flutter analyze` 为准（沙箱跑不了 flutter）。
  The authoritative final check remains `flutter analyze` on the user's native terminal (the sandbox cannot run flutter).

## 与 FitCoach 项目 / Relation to FitCoach

FitCoach 代码根：`C:\code\fitcoach`（本机；另一台开发机为 `D:\code\fitcoach`）。
`flutter` 必须在用户原生终端跑；本 skill 只在沙箱里做改前/改后的静态复验。
FitCoach code root: `C:\code\fitcoach` (this machine; the other dev machine is `D:\code\fitcoach`).
`flutter` must run on the user's native terminal; this skill only does pre/post-edit static re-checks inside the sandbox.
本 skill 已纳入 git 管理并推送至 GitHub，多设备通过 clone 保持一致（见仓库 README）。
This skill is git-managed and pushed to GitHub; multiple devices stay in sync via clone (see the repo README).
