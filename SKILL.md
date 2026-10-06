---
name: flutter-sandbox-static-check
description: >-
  Flutter 工程静态体检（九板斧 / "Nine-Axe" static checker，v4.9 起 23 项）。在无法运行
  flutter/dart 的环境（如 WorkBuddy 沙箱、未装 SDK 的 CI 节点）中，用纯文本分析替代
  flutter analyze，做 23 项检查（默认含 test/）：断 import、pubspec 依赖一致性、相对导入残留、
  枚举值存在性、assets 引用缺失、命名参数拼写、未使用 import（含 dart: 内建库）、括号平衡、
  字符串型枚举残留、未用依赖、**符号用到但没 import**、**lint6 命名与下划线**、
  **ConsumerState 与 widget 配对**、**成员存在性**、**lint 规则表**、
  **第三方 API 废弃/迁移（如 Riverpod 3 的 StateProvider）**、
  **局部标识符不得带 `_` 前缀（局部声明与顶层私有的 `_` 规则相反）**、
  **`final` 字段必须在构造函数里初始化（加字段最易漏的一处，编译期硬错）**、
  **控制流语句跨行却没包块（`curly_braces_in_flow_control_structures`）**。
  Flutter/Dart static checker that runs without the Dart SDK: 19 checks
  (test/ included by default) — broken imports, dependency consistency,
  relative-import leftovers, enum value existence, asset references, named-arg
  spelling, unused imports (incl. dart: core libs), bracket balance,
  string-enum residue, unused deps, **used-but-not-imported symbols**,
  **lint 6 naming & underscores**, **ConsumerState ↔ widget pairing**,
  **member existence**, **lint rule table**, **deprecated third-party APIs**,
  **no leading underscore on locals**, **final fields must be initialized**,
  **flow-control statements spanning lines without braces**.
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
对 Flutter 工程的 `lib/`（**v3 起默认一并体检 `test/`**）做十五板斧体检，
覆盖那些最常见、最致命的编译期硬错与 lint 6 命名问题。
The WorkBuddy sandbox cannot run `flutter` / `dart` (Windows subprocess pipe
`ERROR_PIPE_BUSY 231`), yet edited Dart code still must be verified to avoid
compile-time errors. This skill replaces `flutter analyze` with **pure-text
static analysis**, running thirteen checks over the project's `lib/`
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

## 二十二板斧检查项 / The Twenty-Two Checks

> **名称沿革 / Naming note**：skill 名「九板斧 / Nine-Axe」是历史叫法，v2 起 10 项、
> v3 起 12 项、v4 起 13 项、v4.1 起 15 项、v4.2 起 16 项、v4.3 起 17 项、
> v4.4 起 18 项、v4.5 起 19 项、v4.6 起 20 项、v4.7 起 21 项、v4.8 起 22 项、**v4.9 起 23 项**。名字保留，避免打断既有文档与项目记忆里的引用。
> The skill name "Nine-Axe" is historical — 10 checks since v2, 12 since v3,
> 13 since v4, 15 since v4.1, 16 since v4.2, 17 since v4.3, 18 since v4.4,
> 19 since v4.5, 20 since v4.6, 21 since v4.7, 22 since v4.8, **23 since v4.9**. The name is kept so existing docs and project-memory
> references stay valid.

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
13. **ConsumerState ↔ ConsumerStatefulWidget 配对（ERROR）** / **ConsumerState pairing**: `class S extends ConsumerState<X>` 时 `X` **必须** `extends ConsumerStatefulWidget`；反之 `S extends State<X>` 时 `X` 必须 `extends StatefulWidget`。**双向**都查。
    If `class S extends ConsumerState<X>` then `X` **must** extend `ConsumerStatefulWidget`; conversely `S extends State<X>` requires plain `StatefulWidget`. Checked in **both** directions.
    - **v4 新增**，起因是 2026-10-03 fitcoach E9-a 实踩：State 侧为了用 `ref.watch` 改成了 `ConsumerState`，widget 侧仍是 `StatefulWidget` → `type_argument_not_matching_bounds`；连带所有 import 该 widget 的测试文件一起 `Failed to load`（**报错量看着吓人，实际一个根因**）。
      **Added in v4** after a real miss: the State was switched to `ConsumerState` to use `ref.watch`, but the widget stayed `StatefulWidget` → `type_argument_not_matching_bounds`; every test importing that widget then failed to load (**many errors, one root cause**).
    - 正解 / Correct fix：两侧**同时**改 —— `class X extends ConsumerStatefulWidget` + `ConsumerState<X> createState() => _XState();`。
      Change **both** sides together: `class X extends ConsumerStatefulWidget` **and** `ConsumerState<X> createState() => _XState();`.
    - 降噪 / De-noising：**只在本文件内配对**（widget 与 State 通常同文件），跨文件 widget 跳过不猜 → 干净工程零误报。
      Pairs **within the same file only** (widget and State normally live together); cross-file widgets are skipped → zero false positives on a clean project.
14. **成员存在性（ERROR，表驱动）** / **Member existence (table-driven)**: 接收者类型可判定时，访问的成员必须在成员集合里（`undefined_getter` 是**编译硬错**）。
    When the receiver type is known, the accessed member must exist in that type's member set (`undefined_getter` is a **compile error**).
    - **v4.1 泛化**（起因 M-006：原 C15 只认「DateTime + `.date`」一例）。设计原则：**机制是斧，符号是表** ——
      以后遇到"某某类型上没有某某成员"，**往 `DART_TYPE_MEMBERS` / `DART_STATIC_MEMBERS` 加一行即可，不要再写一把斧**。
      **Generalized in v4.1** (M-006: the old C15 only knew `DateTime` + `.date`). Principle: **the mechanism is the axe, the symbols are a table**.
    - 类型判定（`_infer_type` / 变量声明）：显式 `Type x = ...`、`final x = <字面量/构造>` 推断、链式返回类型表 `DART_CHAIN_RETURN`、工程内 `class/mixin/extension` 成员扫描（含工程内继承链）。
      Type resolution: declared types, literal/constructor inference, a chain-return table, and in-project `class/mixin/extension` member scanning (with in-project inheritance).
    - 降噪四道（**零误报优先于覆盖率**）：①**形参不算**（跨函数同名会误判）②变量按**可见作用域**匹配（声明深度 ≤ 使用深度且未出作用域）③**静态访问**单看 `DART_STATIC_MEMBERS`（`DateTime.now()` 不是实例成员）④工程类继承链里有工程外类型 → 判 `opaque` 整体跳过。
      Four de-noising filters (**zero false positives over coverage**): params don't count; variables are matched **within visible scope**; **static access** consults the static table; project classes with out-of-project supertypes are skipped as `opaque`.
15. **lint 规则表（HINT，表驱动）** / **Lint rules (table-driven)**: `LINT_RULES` 表里每条通用 lint 规则是一项；新增 lint **加一项**即可。
    Each generic lint rule is one entry in `LINT_RULES`; adding a lint means **adding one entry**.
    - **v4.1 新增**（起因 M-007：宿主 `analyze` 报 `prefer_initializing_formals`，C12 只覆盖工程特有两条，抓不到）。
      **Added in v4.1** (M-007: the host reported `prefer_initializing_formals`; C12 only covered two project-specific rules).
    - 首批规则 / First rule：`prefer_initializing_formals`（构造器里 `field = param` 应改用初始化形参 `this.field`）。
      降噪：右侧必须**就是**参数名（`x = y + 1` 不算）；已用 `this.x` 的不报。
    - 与 C12 分工：C12 = 工程特有（连续下划线 / 私有命名）；C16 = 通用 lint。
16. **第三方 API 废弃/迁移名单（ERROR，表驱动）** / **Deprecated third-party API (table-driven)**:
    `DEPRECATED_API_RULES` 每条 = (标识符, 豁免 import, 中英提示)；命中即 **ERROR**。
    Each entry in `DEPRECATED_API_RULES` is (identifier, exempt-import, zh/en message); a hit is an **ERROR**.
    - **v4.2 新增**（起因 M-008：Riverpod 3 把 `StateProvider` 挪进 `legacy.dart`，
      宿主报 `Method not found: 'StateProvider'`，C11 抓不到 —— 该符号既不在工程内、也不在 import 列表里）。
      **Added in v4.2** (M-008: Riverpod 3 moved `StateProvider` into `legacy.dart`; C11 can't see it —
      the symbol is neither declared in-project nor in the import list).
    - 首批 7 条：Riverpod 3 legacy 6 条（`StateProvider` / `StateProviderFamily` /
      `StateNotifier` / `StateController` / `StateNotifierProvider` / `StateNotifierProviderFamily`）
      + 已移除 1 条（`ChangeNotifierProvider`，legacy 也不再导出）。
    - 降噪：匹配在 `mask_strings_comments` **之后**做（注释里写「Riverpod 3 起 StateProvider 已移入 legacy」
      不算数）；豁免 import 命中即放行；每标识符每文件只报一次。
      Matched **after** `mask_strings_comments` (a comment mentioning it doesn't count);
      an exempt import pardons the file; one report per identifier per file.
17. **局部标识符不得带 `_` 前缀（HINT）** / **No leading underscore on locals**:
    函数体内声明的局部变量/局部函数**不能**以下划线开头（`no_leading_underscores_for_local_identifiers`）。
    Local variables/functions declared **inside a function body** must not start with `_`.
    - **v4.3 新增**（起因 M-009：宿主 `analyze` 报 `custom_exercise_test.dart:16`
      测试 helper 写成 `Exercise _custom({...})` —— 它是 `main()` 里的**局部函数**）。
      **Added in v4.3** (M-009: the host flagged `_custom` — a helper declared inside `main()`).
    - ⚠️ **与 C12 方向相反**，别混：顶层/类成员私有 `_foo` **合法**且必须 lowerCamelCase（C12 管）；
      局部 `_foo` **非法**（C18 管）。所以 C18 必须先排除类体，否则两条打架。
      Opposite of C12: top-level/class-member `_foo` is **legal**; local `_foo` is **not**.
    - 降噪三道 / Three de-noising filters：①花括号栈把**类体 / 枚举体**整片放行
      ②必须带「类型」或 `var/final/const/late` 修饰之一，否则 `_helper('x')` 这类**调用**
      与 `Type _helper(` 长得一样（首版漏这条 → 236 条误报里只有 1 条真）
      ③类型段里出现任何**语句关键字**（`return`/`if`/`await`/`?` 前的表达式…）即判为语句
18. **`final` 字段必须在构造函数里初始化（ERROR）** / **Final fields must be initialized**:
    类/枚举里 `final T x;`（声明处无初值、不带 `late`）必须在构造参数里出现 `this.x`
    （或 `super.x` / 初始化列表 `x = ...`），否则宿主报
    `Final field 'x' is not initialized`（编译期硬错）。
    A `final T x;` field (no initializer, not `late`) must be initialized via
    `this.x` / `super.x` / an initializer-list `x = ...`, or the compiler errors out.
    - **v4.4 新增**（起因 M-010：给 `Exercise` 加 `final bool isTimed;` 却漏了
      构造函数里的 `this.isTimed = false` —— **一处漏改，39 个测试文件集体
      Failed to load**，因为它们都要编译 `models.dart`）。
      **Added in v4.4** (M-010: adding `final bool isTimed;` to `Exercise` without
      `this.isTimed = false` broke **39 test files** at once).
    - ⚠️ **为什么必须补**：加字段是最高频改动，而「字段 / 构造 / `toJson` / `fromJson` /
      copy 系列」五处里**只有这一处是编译期硬错**，其余四处都是**静默丢数据**。
      Adding a field is the most common edit, and of the five places to update, only
      this one is a hard compile error — the other four fail **silently**.
    - 降噪四道 / Four de-noising filters：①只认**类体第一层**（花括号深度 == 0），
      函数体内的 `final int local;` 是局部变量不是字段
      ②带初值（`final int b = 1;`）或 `late`（允许延后赋值）放行
      ③类体里出现过 `this.x` / `super.x` / `x =` 任一项即放行 —— 多构造场景
      只查到其中一个也算过，**宁可漏报也不误报**
      ④类里没有生成构造函数（只有 `factory` / 纯静态类）→ 整类跳过。
    - ⚠️ **实现坑**：`_CLASS_DECL_RE` 的 `^` 必须配 `re.M`，否则只匹配文件开头、
      一个类都扫不到（首版漏 → 反向验证 0 命中才发现）。
      `_CLASS_DECL_RE` needs `re.M`; without it **no class is ever scanned**.
19. **控制流语句跨行却没包块（HINT）** / **Flow control spanning lines without braces**:
    `if` / `else if` / `else` / `for` / `while` 的 body **与关键字不在同一行**且没包
    `{}` → 宿主报 `curly_braces_in_flow_control_structures`（info 级）。
    A body that is **not on the same line as the keyword** and is not wrapped in
    `{}` triggers `curly_braces_in_flow_control_structures` (info level).
    - **v4.5 新增**（起因 M-012：宿主 `analyze` 报
      `recovery_service.dart:77:55` —— 长条件换行写成
      `if (!a.contains(m) &&\n    !b.contains(m)) continue;`）。
      **Added in v4.5** (M-012: the host flagged `recovery_service.dart:77:55`).
    - ⚠️ **判据是「与 `if` 关键字同行」，不是「与 `)` 同行」** —— 上面那个例子里
      `continue` 与 `)` 在同一行、但与 `if` 跨行，**lint 照样报**。
      首版按 `)` 判 → 造错样本 0 命中，反向验证才发现。
      The test is "same line as the `if` keyword", **not** "same line as `)`".
    - ⚠️ **单行写法不报**：`if (x) return;`（全库既有风格 **380 处**）lint 不报，
      本斧也放行 —— 不区分就会满屏误报。
      Single-line `if (x) return;` is fine (380 such lines exist) and is pardoned.
    - ⚠️ **终止符必须是 `;`** —— 以 `,` 结尾的是**集合字面量里的 if 元素**
      （Flutter 的 `children: [if (x) const A(),]`，本工程约 56 处），不是语句、
      lint 也不报 → 放行。这条不加就满屏误报。
      A `,`-terminated body is a **collection if-element**, not a statement → pardoned.
20. **library 指令必须在所有 directive 之前（ERROR）** /
    **The library directive must precede all other directives**:
    `library;` 出现在 `import` / `export` / `part` **之后** → 宿主报
    `library_directive_not_first`（error 级，一处就让 `flutter test` 全量
    `Failed to load`，看着像「爆发式报错」，实为一个根因）。
    A `library;` that appears **after** an `import` / `export` / `part` triggers
    `library_directive_not_first` (error level — a single occurrence fails every
    test file with `Failed to load`).
    - **v4.6 新增**（起因 M-014：宿主 `analyze` 报
      `lib/services/exercise_history.dart:13` —— 文件头先写了 `import`，
      把 `library;` 夹在了导入之后）。
      **Added in v4.6** (M-014: the host flagged `lib/services/exercise_history.dart:13`).
    - ⚠️ **本工程几乎不用 `library` 指令**（93 个 lib 文件里只有那 1 处，且是误加），
      正确修法通常是**直接删掉这行**（想写文件头说明就用 `///` 注释，
      本工程既有风格如此）—— 不要把 `import` 挪到 `library` 后面去凑。
      This project barely uses `library` — the fix is usually to **delete the line**
      (use a `///` header comment instead, as the rest of the project does);
      do not shuffle imports around it.
    - 只认**行首**关键字，且字符串与注释已 mask → 注释里写「library 放最前」不误报。
      Only line-leading keywords count, with strings/comments masked → no false
      positives from prose about `library`.
21. **test/ 里用 `find.byType(<手势层/按钮>)` 喂给需单一目标的操作（HINT）** /
    **`find.byType` on gesture/button widgets feeding a single-target op**:
    `tester.tap(find.byType(InkWell))` / `tester.getSize(find.byType(InkWell))`
    —— `IconButton` / `TextButton` 内部本身就是 `InkWell`，一个步进器就能命中 3 个，
    运行时抛 `Bad state: Too many elements`（`Iterable.single`）。
    `IconButton`/`TextButton` embed an `InkWell`, so a single stepper matches 3 →
    runtime `Bad state: Too many elements`.
    - **v4.7 新增**（起因 M-015：宿主 `flutter test` 报 TC-B-USE-05/06 两条失败，
      都是同一个根因 —— `find.byType(InkWell)` 歧义）。
      **Added in v4.7** (M-015: the host's `flutter test` failed TC-B-USE-05/06,
      both from the same root cause).
    - 正确修法 = 给目标 widget 加 `static const Key` 常量，测试用 `find.byKey`；
      临时可用 `.first` / `descendant` 消歧（本斧会放行）。
      Fix = add a `static const Key` to the widget and use `find.byKey`;
      `.first` / `descendant` also pass the check.
22. **静态成员必须 `类名.成员` 访问，不能裸名（ERROR）** /
    **Static members must be qualified with `ClassName.`**:
    Dart 的 `static` **不参与继承**、也**不能裸名访问** —— 在 `State<X>` 子类里写
    `key: valueKey`（成员定义在 `X` 上）→ 宿主报 `undefined_identifier`
    （一处就让 `flutter test` 全量 `Failed to load`）。
    Dart statics are not inherited and cannot be reached by bare name from another
    class, not even from `State<X>`.
    - **v4.8 新增**（起因 M-016：`lib/widgets/rpe_stepper.dart:149` 的
      `key: RpeStepper.valueKey` 写成了 `key: valueKey`）。
      **Added in v4.8** (M-016).
    - 只查**同文件**：某个类里定义的 `static` 成员，在**另一个类的类体内**被裸名使用。
      跨文件的情形（在别的文件里裸用）已属导入/符号分析范畴，暂不覆盖。
23. **判定参数不许被喂字面量兜底（HINT）** /
    **"Time-since" judgement args must not be fed literal constants**:
    `\b\w*Since\w*\s*:\s*\d+`（如 `planDeload(weeksSinceLastDeload: 0, ...)`）——
    「距今 / 自上次」类入参必须是**真实历史值**，写死常量会让整条判定**静默失效**：
    不报错、不崩、单测也过，只是结论永远不成立（**比编译错更危险**）。
    A hardcoded constant makes the whole verdict silently unreachable — no error,
    no crash, tests pass, the branch simply never fires.
    - **v4.9 新增**（起因 M-018：`lib/providers/providers.dart:208` 的
      `weeksSinceLastDeload: 0` → 减载建议永远不出现）。
      **Added in v4.9** (M-018).
    - 只查 `lib/`、**跳过 `test/`**（测试故意写固定值构造确定场景，属正确用法）。
    - 两道降噪：①三元假分支（`rawSince > 0 ? rawSince : 0`）放行；
      ②`final/const/var/late/int/num <名字> =` 声明赋值放行。
    - 修法 = **先把历史事实落盘、再从存储读**；真的拿不到就让判定返回「未知」，
      **不要喂 0**。
      Same-file only: a `static` member used by bare name inside **another class body**.
    - ⚠️ 三道降噪缺一不可（每一道都是反向验证时真踩出来的）：
      ① 本文件有同名**非静态**声明 → 跳过；
      ② 只报「落在另一个类体内」的用法（顶层/函数外太宽，放行）；
      ③ **声明不算用法** —— `final String dateKey;` / `{required this.dateKey}`
      这类同名字段是合法的（第一版报了 2 处误报）。
      Three denoising rules are all required, each found by real reverse-validation.
    - 只对 `InkWell / InkResponse / GestureDetector / IconButton / TextButton /
      ElevatedButton / OutlinedButton / FloatingActionButton / Icon` 报警
      （`Text` / `Container` 之类太常见，报了就是噪声）；整行注释跳过 →
      「别用 find.byType(InkWell)」这类防复发注释不会被自己报出来。
      Only gesture/button types are flagged; full-line comments are skipped so
      "do not use find.byType(InkWell)" notes do not self-report.

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

七步闭环 / Seven-step loop：
1. **确认是漏报**——九板斧复跑该文件（默认已含 `test/`），确认零告警。
2. **归类**——检查项**缺失**（新增一斧）／被**降噪滤掉**（收紧过滤）／**口径不对**（修正逻辑）。
3. **⚠️ 先问"能不能泛化"（2026-10-04 新增，防止"发现一例累加一例"）**——
   这一例是**某个通用机制的一个数据点**，还是**真需要一把新斧**？
   判断标准：**斧里会不会写死具体符号名**。会写死 → 说明缺的是一张**表**，
   应把机制抽成斧、把符号放进表（如 C15 成员存在性 / C16 lint 规则表）。
   **只改业务代码不补斧 = 同类问题必复发；补了斧但只是累加个例 = 工具越长越臃肿。**
4. **补/改** `check.py`，同步 `SKILL.md` / `README.md` 的清单与计数。
5. **反向验证（强制）**——把问题代码临时改回原样 → 跑九板斧 → 确认新斧命中 →
   **还原** → `git status` 为空 + 复跑干净。**没做这步等于没验证。**
6. **登记 `MISSES.md`**——务必写清最小复现。
7. **commit**（默认只 commit 不 push）。

⚠️ **改动过滤/降噪规则时，必须回看 `MISSES.md` 并重跑相关复现**：
降噪改宽是「已闭环漏报悄悄复发」的头号原因。
When touching filters, re-read `MISSES.md` and re-run the affected repros:
loosening de-noising is the #1 cause of closed escapes silently returning.

## 使用纪律 / Usage Discipline

- 这是**静态近似，不是编译器**：ERROR 基本可信，HINT 可能误报，需结合人工判断。
  This is a **static approximation, not a compiler**: ERROR is mostly trustworthy, HINT may be a false positive and needs human judgement.
- **本工具查不到的一类错 —— 编辑时吞掉声明行**：用 Edit **替换 / 删除**代码块时，
  若 `old_string` 含声明行而 `new_string` 没带回，等于静默删除 → 引用未定义标识符
  （如吞掉 `final power = ...` 后 `power` 无定义）。纯文本无法可靠解析局部作用域
  （见 `MISSES.md` M-004 的实验与结论），**故纪律是**：改完重读改动处邻近 10 行。
  Editing pitfall this tool cannot catch: replacing/deleting a block and silently
  dropping a declaration line (`final power = ...`) leaves undefined references.
  Pure-text analysis cannot resolve local scope reliably (see M-004), **so the rule is**:
  re-read the ~10 lines around every edit.
- **本工具查不到的另一类 —— flow promotion 后的多余 `!`**：同一个表达式里写了
  `x != null` 之后，再写 `x!` 会报 `unnecessary_non_null_assertion`（局部变量已被
  提升为非空）。**纪律：写了 `x != null` 就别再对 `x` 用 `!`**，跨行写法尤其容易
  顺手加上。判准需要 flow analysis（字段 / 局部 / `final` / 闭包四种情况各不相同），
  纯文本原型实测双向不达标（见 `MISSES.md` **M-011**），**故不补斧**。
  Another class this tool cannot catch: a redundant `!` after `x != null` in the same
  expression (`unnecessary_non_null_assertion`) — locals get promoted.
  **Rule: once you write `x != null`, do not write `x!`.** Deciding this correctly needs
  flow analysis; the pure-text prototype failed in both directions (see M-011), so no axe.
- **本工具查不到的第三类 —— 类型赋值不兼容（`argument_type_not_assignable`）**：
  C14 只判「某个类型上有没有这个成员」，**不判两个类型之间能否互相赋值**。
  实测踩坑（2026-10-05）：测试里写 `const prior = [0, 600, 600, 600];` 再传给
  `List<double>` 参数 → `const` 声明**没有上下文可推断**，Dart 把它定成 `List<int>`
  → 编译硬错（39 个测试文件 Failed to load）。
  **纪律：往 `List<double>` / `Set<double>` 传字面量时显式写 `<double>[...]` 或带 `.0`**，
  `const` 声明尤其危险（非 const 的实参有上下文类型推断，通常没问题）。
  A third class this tool cannot catch: type-assignment mismatches
  (`argument_type_not_assignable`). C14 only checks whether a member exists on a type,
  not whether one type is assignable to another. Real case: `const prior = [0, 600]`
  has no context to infer from → Dart types it `List<int>` → hard error when passed to a
  `List<double>` parameter. **Rule: write `<double>[...]` or use `.0` literals**, especially
  in `const` declarations (non-const arguments get context inference).
- **本工具查不到的第四类 —— 测试里的「时间炸弹」（硬编码绝对日期 × 真实时钟）**：
  test 里把日期写成 `DateTime(2026, 10, 5, 10)` 这种**离今天很近**的绝对值时，
  写当天全绿；但只要被测代码内部读了 `DateTime.now()`（如草稿 TTL 24h 的过期判定、
  「近 N 天」统计），隔天 `now - savedAt` 越过阈值 → 断言翻转，**必红且看不出原因**。
  实测（fitcoach 2026-10-06）：`session_draft_test` 的 `sample()` 默认 `savedAt`
  写死 2026-10-05 10:00，而 `DraftPref.load()` 不传 `now` 就取真实时钟 → 27h > TTL
  → 判过期顺手清除 → `expect(back, isNotNull)` 拿到 null。
  **纪律：测试用到的日期要么注入时钟（`now:` / `until:` 参数），要么取 `DateTime.now()`
  的相对值（`now.subtract(...)`）；绝不写「离今天 ±若干天」的绝对日期。**
  ⚠️ **不补斧**：全库 159 处硬编码日期里绝大多数是注入时钟或纯标签（如 `monthKeyOf`），
  判准需要「该日期是否与真实时钟发生比较」的数据流分析 —— 纯文本做不到，
  补了就是纯噪声（见 `MISSES.md` **M-017**）。
  A fourth class this tool cannot catch: **time bombs in tests** — a hardcoded absolute
  date *close to today* passes on the day it is written, then flips once the wall clock
  crosses the threshold inside the code under test (24h draft TTL, "last N days" stats).
  **Rule: inject the clock (`now:` / `until:`) or derive from `DateTime.now()`; never
  hardcode a date within days of today.** No axe: 159 hardcoded dates in the corpus are
  mostly injected clocks or pure labels; telling them apart needs data-flow analysis
  (see M-017), so a check would be pure noise.
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
