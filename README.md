# Flutter Sandbox Static Check（九板斧）

纯标准库、零第三方依赖的 **Python** 静态体检脚本，用来在**无法运行 `flutter`/`dart` 的环境**（例如 WorkBuddy 沙箱、CI 里没装 SDK 的节点）里，对 Flutter/Dart 工程的 `lib/` 做编译期硬错检查，作为 `flutter analyze` 的廉价替身。

> 定位：当你跑不了 `flutter analyze` 时，用它快速拦住"断 import / 未声明依赖 / 相对导入 / 枚举值写错 / 括号不配对"这类会直接编译失败的低级错误。它不是编译器，ERROR 基本可信，HINT 需人工确认。

## 为什么需要它（与开源项目的差异）

GitHub 上同类工具不少，但路线不同：

| 项目 | 语言/依赖 | 是否需要 Dart SDK |
|---|---|---|
| dart-re-analyzer | Rust + tree-sitter | 否，但需编译二进制 |
| dart-code-linter / lint / pedant | `package:analyzer` / custom_lint | **是** |
| flutter_analyzer_script / refactoroscope | Python | 否（做 unused 分析） |

**本工具的唯一卖点**：一个 `check.py` 文件、只用 Python 标准库、双击即跑、**完全不碰 Dart SDK**，专为"沙箱里改完 Dart 代码想立刻复验"而生。我们仅从上面这些项目**吸取了概念**（跳过生成文件、未用依赖检测、severity 分级），没有复制任何代码——致谢见 [NOTICE](./NOTICE)。

## 安装

```bash
git clone https://github.com/sa9427/flutter-sandbox-static-check.git
# 仅依赖系统自带 python3，无需 pip install
```

若作为 WorkBuddy 技能使用，把仓库 clone 到技能目录即可（多设备保持一致）：

```bash
git clone https://github.com/sa9427/flutter-sandbox-static-check.git \
  ~/.workbuddy/skills/flutter-sandbox-static-check
```

## 用法

```bash
python3 check.py --project /path/to/flutter_project
# 默认 --project 为 C:/code/fitcoach
```

输出分两级：
- **ERROR**：几乎必然是编译错误（断 import、未声明依赖、相对导入残留、枚举值不存在），必须先修。
- **HINT**：启发式告警，可能误报，需人工确认。

结尾打印 `RESULT: 工程干净 ✅` 或 `RESULT: 发现 N 处问题 ⚠️`。

## 十板斧检查项

| 编号 | 检查 | 级别 | 说明 |
|---|---|---|---|
| C1 | 断 import | ERROR | `package:fitcoach/...` 目标文件不存在 |
| C2 | pubspec 依赖一致性 | ERROR | import 的 `package:X` 未在 pubspec 声明 |
| C3 | 相对导入残留 | ERROR | 出现 `./` 或 `../` |
| C4 | 枚举值存在性 | ERROR/HINT | `byName('x')` 值不存在必为错；点访问疑似错为 HINT |
| C5 | assets 引用缺失 | HINT | 代码引用未在 pubspec 声明的资源 |
| C6 | 命名参数拼写 | HINT | 小写业务函数调用里疑似拼错的命名参数 |
| C7 | 未使用 import | HINT | `as`/`show` 精确判定；`dart:` 内建库用符号表判定 |
| C8 | 括号/结构平衡 | HINT | 只数 `()[]{}`，忽略泛型/比较的 `<>` 与字符串 |
| C9 | 字符串型枚举残留 | HINT | 枚举被当裸字符串误用 |
| C10 | 未用依赖 | HINT | pubspec 声明但无任何文件 import 的运行时依赖 |

脚本自动跳过生成文件（`*.g.dart` / `*.freezed.dart` / `build/` / `.dart_tool/`）。

## 使用纪律

1. 这是**静态近似，不是编译器**：ERROR 基本可信，HINT 需结合人工判断。
2. 每次改完 Dart 代码跑一遍，确认 `RESULT: 工程干净 ✅` 再提交。
3. 权威终验仍以能跑 `flutter analyze` 的原生终端为准。

## License

[Apache License 2.0](./LICENSE)。版权与第三方致谢见 [NOTICE](./NOTICE)。
