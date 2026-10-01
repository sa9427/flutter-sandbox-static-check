---
name: flutter-sandbox-static-check
description: Flutter 工程静态体检（九板斧）。在沙箱无法运行 flutter/dart（Windows 子进程 ERROR_PIPE_BUSY）时，用纯文本分析替代 flutter analyze，对 lib/ 做 10 项编译期硬错检查：断 import、pubspec 依赖一致性、相对导入残留、枚举值存在性、assets 引用缺失、命名参数拼写、未使用 import（含 dart: 内建库）、括号平衡、字符串型枚举残留、未用依赖。当用户要在不能跑 flutter 的环境验证 Flutter/Dart 改动是否引入编译错误、或在 WorkBuddy 沙箱内审查 Flutter 项目代码时使用。
---

# Flutter 沙箱静态体检（九板斧）

## 背景与用途
WorkBuddy 沙箱无法运行 `flutter` / `dart`（Windows 子进程管道 `ERROR_PIPE_BUSY 231`），
但改完 Dart 代码仍需验证不会引入编译期错误。本 skill 用**纯文本静态分析**替代 `flutter analyze`，
对 Flutter 工程的 `lib/` 目录做十板斧体检，覆盖那些最常见、最致命的编译期硬错。

## 运行方式
自带脚本，**零第三方依赖**（纯 Python 标准库）：

```bash
python3 <skill_dir>/check.py --project C:/code/fitcoach
```

- 默认 `--project` 为 `C:/code/fitcoach`；也可指向任意 Flutter 工程根目录
  （脚本自动定位 `lib/` 与 `pubspec.yaml`，并**跳过生成文件** `*.g.dart` / `*.freezed.dart` / `build/` / `.dart_tool/`）。
- 输出分两级：
  - **ERROR**：几乎必然是编译错误（如断 import、引用不存在的枚举值、未声明依赖），必须先修。
  - **HINT**：启发式告警，可能误报，需人工确认。
- 结尾打印 `RESULT: 工程干净 ✅` 或 `RESULT: 发现 N 处问题 ⚠️`。

## 十板斧检查项
1. **断 import（ERROR）**：解析 `package:fitcoach/...`，确认目标 `.dart` 文件存在。
2. **pubspec 依赖一致性（ERROR）**：`import 'package:X/...'` 的 `X` 必须在 `pubspec.yaml` 的 `dependencies`/`dev_dependencies` 中声明。
3. **相对导入残留（ERROR）**：工程约定统一用 `package:` 绝对导入；出现 `../` 或 `./` 即告警。
4. **枚举值存在性（ERROR/HINT）**：收集 `enum` 全部成员（含一行多值 `light, medium, hard;`），扫描 `Enum.value` / `Enum.values.byName('value')`，标出不存在的值。
5. **assets 引用缺失（HINT）**：`pubspec` 的 `assets:` 与代码中 `AssetImage`/`rootBundle.load`/`exact` 引用交叉核对。
6. **命名参数拼写（HINT）**：对小写业务函数调用，检查命名参数是否真在签名中声明；内置 Flutter 框架参数 + 工程自定义参数白名单降噪。
7. **未使用 import（HINT）**：
   - `as prefix`：从未以 `prefix.` 引用 → 判未用（精确）。
   - `show {..}`：所列符号均未出现 → 判未用（精确）。
   - `dart:` 内建库：维护公开符号表，符号均未出现 → 判未用（**v2 新增，修复此前对 dart: 直接跳过导致的漏报**）。
   - 工程内 `package:fitcoach/`：目标文件顶层符号均未被引用 → 判未用。
   - 外部 package（无 as/show）：未知导出符号，跳过以免误报。
8. **括号/结构平衡（HINT）**：**v2 重写**——只数 `()[]{}`，忽略尖括号 `<>`（泛型/比较/`=>`）与字符串/三引号/插值，消除此前对全部文件误报。
9. **字符串型枚举残留（HINT）**：检查枚举是否被当裸字符串误用。
10. **未用依赖（HINT）**：`pubspec` 声明的运行时依赖若无任何文件 `import`，提示可能未使用（**v2 新增，借鉴 flutter_analyzer_script**）。

## 设计借鉴（开源精华）
- **dart-re-analyzer / pedant**：severity 分级 + 跳过生成文件（`*.g.dart` 等）。
- **flutter_analyzer_script / refactoroscope**：unused 的"声明-引用"判定思路。
- 本工具仅吸取**概念与思路**，未复制任何第三方代码；如将来引入具体实现，须遵守对应许可证并保留署名。

## 使用纪律
- 这是**静态近似，不是编译器**：ERROR 基本可信，HINT 可能误报，需结合人工判断。
- 每次改完 Dart 代码跑一遍，确认 `RESULT: 工程干净 ✅` 后再提交。
- 权威终验仍以用户原生终端的 `flutter analyze` 为准（沙箱跑不了 flutter）。

## 与 FitCoach 项目
FitCoach 代码根：`C:\code\fitcoach`（本机；另一台开发机为 `D:\code\fitcoach`）。
`flutter` 必须在用户原生终端跑；本 skill 只在沙箱里做改前/改后的静态复验。
本 skill 已纳入 git 管理并推送至 GitHub，多设备通过 clone 保持一致（见仓库 README）。
