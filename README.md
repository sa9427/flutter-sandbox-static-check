# Flutter Sandbox Static Check（九板斧 / "Nine-Axe"）

纯标准库、零第三方依赖的 **Python** 静态体检脚本，用来在**无法运行 `flutter`/`dart` 的环境**（例如 WorkBuddy 沙箱、CI 里没装 SDK 的节点）里，对 Flutter/Dart 工程的 `lib/` 做编译期硬错检查，作为 `flutter analyze` 的廉价替身。
A **Python** static-check script with zero third-party dependencies and only the
standard library. It runs compile-time sanity checks over a Flutter/Dart
project's `lib/` in environments where `flutter`/`dart` **cannot run** (e.g. the
WorkBuddy sandbox, or a CI node without the SDK), acting as a cheap stand-in for
`flutter analyze`.

> 定位：当你跑不了 `flutter analyze` 时，用它快速拦住"断 import / 未声明依赖 / 相对导入 / 枚举值写错 / 括号不配对"这类会直接编译失败的低级错误。它不是编译器，ERROR 基本可信，HINT 需人工确认。
> Positioning: when you can't run `flutter analyze`, use it to quickly catch
> low-level errors that fail compilation outright — broken imports, undeclared
> dependencies, relative imports, wrong enum values, unbalanced brackets. It is
> not a compiler: ERROR is mostly trustworthy, HINT needs human confirmation.

## 为什么需要它（与开源项目的差异）/ Why It Exists (vs. Open-Source Alternatives)

GitHub 上同类工具不少，但路线不同：
Plenty of similar tools exist on GitHub, but they take different approaches:

| 项目 / Project | 语言/依赖 / Lang/Dep | 是否需要 Dart SDK / Needs Dart SDK |
|---|---|---|
| dart-re-analyzer | Rust + tree-sitter | 否，但需编译二进制 / No, but needs a compiled binary |
| dart-code-linter / lint / pedant | `package:analyzer` / custom_lint | **是 / Yes** |
| flutter_analyzer_script / refactoroscope | Python | 否（做 unused 分析）/ No (does unused analysis) |

**本工具的唯一卖点**：一个 `check.py` 文件、只用 Python 标准库、双击即跑、**完全不碰 Dart SDK**，专为"沙箱里改完 Dart 代码想立刻复验"而生。我们仅从上面这些项目**吸取了概念**（跳过生成文件、未用依赖检测、severity 分级），没有复制任何代码——致谢见 [NOTICE](./NOTICE)。
**The unique selling point of this tool**: a single `check.py` file, Python
stdlib only, runnable by double-click, **touches no Dart SDK at all** — built
specifically for "re-check Dart code right after editing it inside a sandbox".
We borrowed only **concepts** from the projects above (skip generated files,
unused-dependency detection, severity levels), copying no code — attribution in
[NOTICE](./NOTICE).

## 安装 / Install

```bash
git clone https://github.com/sa9427/flutter-sandbox-static-check.git
# 仅依赖系统自带 python3，无需 pip install
# Only depends on the system's built-in python3; no pip install needed
```
> 注 / Note: 将上面的 `sa9427` 替换为你自己的 GitHub 用户名或组织名。
> Replace `sa9427` above with your own GitHub username or org.

若作为 WorkBuddy 技能使用，把仓库 clone 到技能目录即可（多设备保持一致）：
To use it as a WorkBuddy skill, clone the repo into the skills directory (keeps multiple devices in sync):

```bash
git clone https://github.com/sa9427/flutter-sandbox-static-check.git \
  ~/.workbuddy/skills/flutter-sandbox-static-check
```

## 用法 / Usage

```bash
python3 check.py --project /path/to/flutter_project
# 默认 --project 为 C:/code/fitcoach
# Default --project is C:/code/fitcoach

# v3 起 **默认连 test/ 一起体检**（测试代码也是交付物）；
# 只想扫 lib/ 时加 --no-test
# Since v3, test/ is scanned **by default** (test code is a deliverable too);
# pass --no-test to scan lib/ only
python3 check.py --no-test
```

输出分两级 / Output has two severity levels:
- **ERROR**：几乎必然是编译错误（断 import、未声明依赖、相对导入残留、枚举值不存在、**符号用到但没 import**），必须先修。
  Almost certainly a compile error (broken import, undeclared dependency,
  relative-import leftover, non-existent enum value, **used-but-not-imported
  symbol**) — must be fixed first.
- **HINT**：启发式告警，可能误报，需人工确认。
  Heuristic warning, may be a false positive — needs human confirmation.

结尾打印 / Prints at the end: `RESULT: 工程干净 ✅` 或 / or `RESULT: 发现 N 处问题 ⚠️`.

## 十二板斧检查项 / The Twelve Checks

> 名称沿革 / Naming note：skill 名 "九板斧 / Nine-Axe" 是历史叫法；
> v2 起已有 10 项、v3 起 12 项，名字保留以免打断既有文档与记忆中的引用。
> The skill name "Nine-Axe" is historical; it had 10 checks since v2 and 12
> since v3. The name is kept to avoid breaking existing docs and references.

| 编号 / # | 检查 / Check | 级别 / Level | 说明 / Notes |
|---|---|---|---|
| C1 | 断 import / Broken import | ERROR | `package:fitcoach/...` 目标文件不存在 / Target file does not exist |
| C2 | pubspec 依赖一致性 / Dependency consistency | ERROR | import 的 `package:X` 未在 pubspec 声明 / Imported `package:X` not declared in pubspec |
| C3 | 相对导入残留 / Relative-import leftover | ERROR | 出现 `./` 或 `../` / A `./` or `../` appears |
| C4 | 枚举值存在性 / Enum value existence | ERROR/HINT | `byName('x')` 值不存在必为错；点访问疑似错为 HINT / `byName('x')` missing = error; dot-access suspect = HINT |
| C5 | assets 引用缺失 / Missing asset reference | HINT | 代码引用未在 pubspec 声明的资源 / Code references an asset not declared in pubspec |
| C6 | 命名参数拼写 / Named-arg spelling | HINT | 小写业务函数调用里疑似拼错的命名参数 / Suspected misspelled named args in lowercase business calls |
| C7 | 未使用 import / Unused import | HINT | `as`/`show` 精确判定；`dart:` 内建库用符号表判定 / Precise via `as`/`show`; `dart:` core libs via symbol table |
| C8 | 括号/结构平衡 / Bracket balance | HINT | 只数 `()[]{}`，忽略泛型/比较的 `<>` 与字符串 / Counts only `()[]{}`, ignores `<>` and strings |
| C9 | 字符串型枚举残留 / String-enum residue | HINT | 枚举被当裸字符串误用 / Enum mistakenly used as bare string |
| C10 | 未用依赖 / Unused dependency | HINT | pubspec 声明但无任何文件 import 的运行时依赖 / Declared in pubspec but never imported |
| C11 | 符号用到但没 import / Used-but-not-imported symbol | ERROR | **v3 新增**：用了某符号却没 import 定义它的文件（Dart import 不传递）；已按 part/export 闭包、成员访问、命名实参降噪 / **added in v3**: symbol used without importing its defining file (Dart imports are not transitive); de-noised via part/export closure, member access, named args |
| C12 | lint 6 命名与下划线 / lint 6 naming & underscores | HINT | **v3 新增**：标识符含连续下划线（`__`）、顶层私有函数写成 `_UpperCamel` / **added in v3**: consecutive underscores in identifiers, private top-level functions written as `_UpperCamel` |

脚本自动跳过生成文件（`*.g.dart` / `*.freezed.dart` / `build/` / `.dart_tool/`）。
The script auto-skips generated files (`*.g.dart` / `*.freezed.dart` / `build/` / `.dart_tool/`).

## 漏报反哺机制 / Miss-Feedback Loop

**宿主 `flutter analyze` / `flutter test` 报出的每一条问题，都要先问：九板斧为什么没抓到？**
是漏报就必须补斧，不能只改业务代码了事。
For **every** issue the host's `flutter analyze`/`flutter test` reports, ask first:
*why did the checker miss it?* A miss must become a new axe — never just fix the code.

六步闭环（详见 `MISSES.md`）：确认漏报 → 归类（缺斧／被降噪滤掉／口径错）→ 补/改 `check.py`
→ **反向验证（强制：把 bug 改回原样确认新斧命中，再还原）** → 登记 `MISSES.md` → commit。
Six steps (see `MISSES.md`): confirm the miss → classify → fix `check.py` →
**reverse-validate (mandatory)** → record in `MISSES.md` → commit.

📄 **`MISSES.md`** = 漏报台账（唯一真源），含每条漏报的根因、对应斧号与**最小复现**。
改动过滤/降噪规则时必须回看重跑复现——降噪改宽是已闭环漏报复发的头号原因。
`MISSES.md` is the escape ledger (single source of truth) with root cause, axe, and
a **minimal repro** per entry. Re-run the repros whenever filters change.

## 使用纪律 / Usage Discipline

1. 这是**静态近似，不是编译器**：ERROR 基本可信，HINT 需结合人工判断。
   This is a **static approximation, not a compiler**: ERROR is mostly
   trustworthy; HINT needs human judgement.
2. 每次改完 Dart 代码跑一遍，确认 `RESULT: 工程干净 ✅` 再提交。
   Run it after every Dart edit; only commit once `RESULT: 工程干净 ✅` is confirmed.
3. 权威终验仍以能跑 `flutter analyze` 的原生终端为准。
   The authoritative final check remains a native terminal that can run `flutter analyze`.

## License

[Apache License 2.0](./LICENSE)。版权与第三方致谢见 [NOTICE](./NOTICE)。
[Apache License 2.0](./LICENSE). Copyright and third-party attribution in
[NOTICE](./NOTICE).
