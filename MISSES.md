# 漏报台账 / Escape Ledger（反哺机制的唯一载体）

> **本文件是九板斧自我进化的唯一台账**：记录每一条「宿主 `flutter analyze` / `flutter test`
> 报出、但九板斧没抓到」的问题，以及为它补/改的那一斧。
> Single source of truth for the feedback loop: every issue reported by the host's
> `flutter analyze`/`flutter test` that the checker **MISSED**, plus the axe added/changed for it.
>
> - 新增/修改检查项时**必须**在此登记。
>   Register here whenever a check is added or changed.
> - 改动任何**过滤/降噪规则**时**必须**回看相关条目并重跑其「最小复现」——
>   降噪改宽了最容易让已闭环的漏报悄悄复发。
>   When touching any filter, re-run the recorded repro: loosening de-noising is the
>   #1 way a closed escape silently comes back.

## 为什么需要 / Why

九板斧是**静态近似，不是编译器**，天然有盲区；盲区**只能**在宿主真跑 flutter 时暴露。
若每次只「修代码」不「补工具」，同类问题会反复漏——E1 那次一条漏 import 就报了 4 个 error，
而九板斧零告警。所以：**发现盲区 → 当场补斧**，别只在记忆里写「以后注意自查」。

## 反哺流程 / Feedback Loop（6 步，缺一不可）

1. **确认是漏报**：九板斧复跑该文件（v3 起默认已含 `test/`），确认确实零告警。
   Confirm it is really a miss (the checker runs `test/` by default since v3).
2. **归类 / Classify**：
   - 检查项**缺失** → 新增一斧（如 M-001/M-002）
   - 检查项存在但**被降噪滤掉** → 收紧过滤（注意别引入新误报）
   - 检查项存在但**判定口径不对** → 修正逻辑（如 M-001 的 part/export 闭包）
3. **补/改** `check.py`，并同步 `SKILL.md` / `README.md` 的检查项清单与计数。
4. **反向验证（强制）**：把问题代码**临时改回**原样 → 跑九板斧 → 确认新斧命中 →
   **还原** → `git status` 为空 + 复跑干净。**没有这一步等于没验证。**
   Reverse-validate (mandatory): temporarily reintroduce the bug, confirm the new axe
   fires, restore, confirm `git status` is clean and the run is clean again.
5. **登记本台账**：含**最小复现**（改哪个文件哪一行、改成什么），供将来改过滤规则时重跑。
6. **commit**（默认只 commit 不 push）。

---

## 台账 / Entries

### M-001 · 2026-10-03 · fitcoach E1(C26) · 符号用到但没 import → **新增 C11**

- **症状 Symptom**：`flutter analyze` 一次报 **4 个 error**
  （`Type 'VolumeTrendPoint' not found` / `Method not found: 'VolumeTrendPoint'`）。
- **根因 Root cause**：**Dart 的 import 不传递**。`VolumeTrendPoint` 定义在
  `lib/services/volume_service.dart`，被测的 `plateau_service.dart` 自己 import 并用了它，
  但 `plateau_test.dart` import `plateau_service.dart` **不会**继承到该符号。
- **旧九板斧为何漏 Why missed**：C1 只判「import 的文件**是否存在**」，
  对「压根少写一条 import」完全无感；且当时 `test/` 默认不扫。
- **补的斧 Fix**：新增 **C11（符号用到但没 import，ERROR）**
  + `test/` 改为默认扫描（`--no-test` 可关）。
- **最小复现 Repro**：删掉 `test/services/plateau_test.dart` 的
  `import 'package:fitcoach/services/volume_service.dart';` →
  应报 `C11 ... plateau_test.dart:16 符号 VolumeTrendPoint 定义在 services/volume_service.dart`。
- **降噪四道（改任一条都要重跑本复现）De-noising**：
  1. `part`/`export` **传递闭包**——「符号在哪可见」≠「符号定义在哪」；
  2. 前置 `.` → 成员/枚举访问（`CardioPhase.main`、`StatsService.dateKey`）；
  3. 后置 `:` → 命名实参（`recentPeakRpe: x`），用「前置是 `?` 则不滤」避开三元 `a ? b : c`；
  4. 本文件声明位置 → `this.x`、`Type name` 形参
     （`List<double> recentPeakRpe` 是 `planDeload` 的**形参**不是调用）、增强枚举成员。
  另：只取**唯一定义**的符号，同名多定义直接放弃。
- **首轮误报 FP seen**：`main`(×4) / `dateKey`(×5) / `recentPeakRpe`(×2)，加完四道过滤后归零。
- **状态**：✅ 已补斧并反向验证通过（2026-10-03）。

### M-002 · 2026-10-03 · fitcoach E1(C26) · 标识符含连续下划线 → **新增 C12（前半）**

- **症状**：`flutter analyze` 报 2 条 `unnecessary_underscores` info
  （`lib/features/review/review_page.dart:124`、`lib/features/training/training_record_page.dart:519`）。
- **根因**：写了 `error: (_, __)`。`__` 是「单个标识符含两个下划线」，被 lint 6 抓。
- **正确写法**：参数个数**必须与目标类型一致**（FutureProvider 的 error 是 `(Object, StackTrace)` 两参），
  每个未用参数各写一个**单** `_` → `(_, _)`。**省参数个数会 `argument_type_not_assignable`。**
- **旧九板斧为何漏**：完全不查 lint 6 命名/下划线规则。
- **补的斧**：新增 **C12（lint 6 命名与下划线，HINT）**。
- **最小复现**：把 `review_page.dart` 的 `error: (_, _)` 改回 `(_, __)` →
  应报 `C12 ... review_page.dart:124 标识符 __ 含连续下划线`。
- **状态**：✅ 已补斧并反向验证通过。

### M-003 · 2026-10-03 · fitcoach E1(C26) · 私有函数写成 UpperCamel → **新增 C12（后半）**

- **症状**：`flutter analyze` 报 1 条 `non_constant_identifier_names` info
  （`lib/widgets/plateau_card.dart:101`）。
- **根因**：`Widget _DeloadBlock(...)` 是**函数**不是类 → 函数名须 lowerCamelCase；
  私有前缀 `_` 之后仍要小写开头 → `_deloadBlock`。
- **⚠️ 易错边界**：私有**类** `_DeloadBlock` 反而是**合法**的（类走 UpperCamelCase），
  过滤时已排除 `class|enum|mixin|typedef|extension` 声明行，别误杀。
- **旧九板斧为何漏**：同 M-002。
- **补的斧**：C12 后半（顶层私有声明 `_UpperCamel`）。
- **最小复现**：把 `_deloadBlock` 改回 `_DeloadBlock` →
  应报 `C12 ... plateau_card.dart:101 私有声明 _DeloadBlock 应为 lowerCamelCase`。
- **状态**：✅ 已补斧并反向验证通过。

### M-004 · 2026-10-03 · fitcoach E9-a(C29) · 引用了但本文件从未声明的局部标识符 → **不补斧（能力边界）**

- **症状**：一次 Edit **替换代码块时吞掉了 `final power = ...` / `final hr = ...` 两行声明**，
  结果 `power` / `hr` 被引用却无定义 —— 宿主 `flutter analyze` 会报一串
  `Undefined name 'power'`，必编译失败。
- **根因**：编辑事故，非代码风格问题。`old_string` 里带了这两行、`new_string` 没带回，
  等价于静默删除（是「插入勿吞锚点行」的**删除变体**）。
- **旧九板斧为何漏**：C11 只管**跨文件 import** 层，局部声明层完全没覆盖。
- **归类**：⬜ **不补斧** —— 属**能力边界**，详见下方实验结论。
- **实验（已做，可复盘，别重复造）**：原型 C13「标识符被引用但本文件找不到声明位置」
  （HINT 级，宁可漏报策略：形参/实参/赋值左侧/调用/成员访问/命名实参一律视为已声明）。
  在已知干净的 fitcoach 上跑出**大量误报**，主要四类：
  ① 注解 `override`（以及 `protected` / `visibleForTesting` 等）；
  ② 小写**内置类型名** `bool` / `double` / `int`（出现在 `List<bool>` 泛型位，不在声明位）；
  ③ **getter** 声明（`String get setLabel =>`）没被声明正则捕获；
  ④ **import 进来的外部符号**（`databaseFactoryWeb` / `stringMapStoreFactory` /
  `showModalBottomSheet` / `muscleLabels` 等）—— 纯文本无法知道它们来自哪个包。
- **结论**：要压到可接受误报率，必须实现**作用域 + import 解析**，等价于写一遍编译器，
  与「纯文本近似」的定位冲突。**收益 < 成本，且不补斧的代价很低**：
  这类错误是**确定性编译错误**，宿主 `flutter analyze` 第一轮就会报出来。
- **改为人工纪律（已写进 SKILL.md 使用纪律）**：
  **Edit 替换/删除代码块后，重读改动处邻近 10 行，确认没有吞掉声明行。**
  （与既有记忆规则「插入勿吞锚点行」是同一条，本次补上**删除/替换变体**。）
- **状态**：⬜ 不补斧（能力边界，已记录实验证据与替代纪律）。

### M-005 · 2026-10-03 · fitcoach E9-a(C29) · ConsumerState 与 widget 不配对 → **新增 C14**

- **症状**：宿主 `flutter analyze` **唯一一条 error**
  `lib/widgets/cardio_segment_form.dart:42:53 type_argument_not_matching_bounds`
  （`_CardioSegmentFormState extends ConsumerState<CardioSegmentForm>`，
  但 `CardioSegmentForm extends StatefulWidget`）；
  `flutter test` 连带 `test/widget_test.dart` 整个 `Failed to load`（`-1`）。
- **根因**：E9-a 为了在 State 里 `ref.watch(profileProvider)` 把 `State` 改成了
  `ConsumerState`，**widget 侧忘了同步改成 `ConsumerStatefulWidget`**（createState 的
  返回类型也要改成 `ConsumerState<X>`）。
  正解：两侧**同时**改 —— `class X extends ConsumerStatefulWidget` +
  `ConsumerState<X> createState() => _XState();`。
- **危害被放大的原因**：一个 widget 编译失败 → 所有 import 它的测试文件一起
  `Failed to load`，报错量看着吓人，**实际只有一个根因**（先找 analyze 的 error 条数）。
- **旧九板斧为何漏**：只查 import / 枚举 / 括号 / 命名，**完全不查 State 与 widget 的
  基类配对**。
- **补的斧**：新增 **C14（ConsumerState ↔ ConsumerStatefulWidget 配对，ERROR）**，
  **双向**都抓（ConsumerState 配 StatefulWidget、State 配 ConsumerStatefulWidget）。
- **最小复现**：把 `cardio_segment_form.dart` 的
  `class CardioSegmentForm extends ConsumerStatefulWidget` 改回 `StatefulWidget` →
  应报 `C14 ... cardio_segment_form.dart:42 _CardioSegmentFormState extends ConsumerState<CardioSegmentForm> → CardioSegmentForm 必须 extends ConsumerStatefulWidget`。
- **降噪**：**只在本文件内配对**（widget 与 State 通常同文件），跨文件 widget 直接跳过
  不猜 → 干净工程零误报（fitcoach 81 文件复跑确认）。
- **反向验证**：临时样例 `/tmp/c14check/lib/a.dart` 含 1 组正确 + 2 组错误配对 →
  C14 **只报那 2 组**（Good 未误报）；fitcoach 修复后 C14 零告警。
- **状态**：✅ 已补斧并反向验证通过（2026-10-03）。

---

### M-006 · 2026-10-04 · fitcoach(E8/C31) · `DateTime` 上取 `.date` → **新增 C15**

- **症状**：宿主 `flutter test` 报 `Failed to load "test/services/doms_test.dart"` + 4 条
  `Error: The getter 'date' isn't defined for the type 'DateTime'`（`doms_test.dart:25/26/27/29`），
  `flutter analyze` 同步报 4 条 `undefined_getter`。
- **根因**：想把 DateTime 截断成日期时写成了 `_now.subtract(const Duration(hours: 20)).date`。
  `DateTime` 只有 `year/month/day/hour…`，**没有 `date` getter**；要"只要日期"应构造
  `DateTime(y, m, d)`（工程内已有 `StatsService.dayStart` 这类工具）。
- **旧九板斧为何漏**：C11 只查「符号用到但没 import」，对**成员名在已解析类型上不存在**
  这类 `undefined_getter` 完全无感——它假定所有前置 `.` 的访问都是合法成员访问
  （那条降噪规则本就是为了不误报 `session.date`）。
- **补的斧**：新增 **C15（DateTime 上的 `.date` 幽灵成员，ERROR 级）**，
  只在**接收者可判定为 DateTime** 时命中：显式 `DateTime x = ...` 变量 / `final x = DateTime...`
  推断 / `DateTime(...)` 字面构造 / 链式 `add·subtract·toLocal·toUtc`。
- **最小复现**：`/tmp/c15check/lib/a.dart` 含 4 处真错（`_now.subtract(...).date`、
  `DateTime.now().date`、`_now.date`、`inferred.date`）+ 3 处反例
  （对象字段 `session.date`、注释里的 `_now.date`、字符串 `'x.date'`）
  → 期望**只报那 4 处**（实测 4/4 命中、反例零误报）。
- **降噪坑（实测）**：第一版把**形参** `DateTime d` 也当 DateTime 变量，
  导致 `stats_service.dart:124` 的 `(d) => ... d.date`（`d` 是聚合对象）被误报 →
  改为**只认有初始化的变量**（`DateTime x = ...`），形参一律不算。
- **反向验证**：fitcoach 修复后复跑 → **C15 零告警**（仅剩 4 条已知 C6 HINT）。
- **状态**：✅ 已补斧并反向验证通过（2026-10-04）。
- **⭐ 2026-10-04 二次泛化（需求方指出"发现一例累加一例"）**：本条**当时就是个例斧**
  （只认 DateTime + `.date`）。现已把 C15 升格为**通用成员存在性斧**：
  机制（接收者 → 类型 → 成员集合）留在斧里，符号进 **表**
  （`DART_TYPE_MEMBERS` / `DART_STATIC_MEMBERS` / `DART_CHAIN_RETURN` + 工程类扫描）。
  新增个例 = 往表里加一行。泛化后复验：正例 6/6（DateTime.date ×2 / String.lenght /
  List.lenght / Duration.inHour / 工程类 Foo.barr），反例（对象字段、注释、字符串、
  lambda 形参、静态访问、跨作用域同名）**零误报**，fitcoach 91 文件复跑零告警。

---

### M-007 · 2026-10-04 · fitcoach(#31 S2) · lint `prefer_initializing_formals` → **新增 C16（表驱动 lint）**

- **症状**：宿主 `flutter analyze` 报 `info - Use an initializing formal to assign a parameter
  to a field ... lib\widgets\adaptive.dart:33:8 - prefer_initializing_formals`。
- **根因**：`AdaptiveLayoutInfo._({required LayoutClass layout}) : _layout = layout;`
  应写成 `required this._layout`。
- **旧九板斧为何漏**：C12 只做了**工程特有**的两条（连续下划线 / 私有命名），
  **没有一张可扩的通用 lint 表** → 每来一条新 lint 都只能手工改代码 + 再补一把斧。
- **补的斧**：新增 **C16（lint 规则表，表驱动）**，`LINT_RULES` 首批收录
  `prefer_initializing_formals`；以后新增 lint **加一项**即可。
- **最小复现**：`/tmp/c16check/lib/b.dart`：`Bad(int a, {required int b}) : _a = a, _b = b;`
  → 应报 2 处；`Good(this.a)` 与 `AlsoFine(int y) : x = y + 1;` 都不应报
  （实测 2/2 命中、反例零误报）。
- **降噪坑（实测两处）**：①右侧必须**就是**参数名（`x = y + 1` 是真初始化，不能报），
  故加 `(?=,|$)` 锚定；②命名参数段要**剥掉 `{}`**（`{required int b}` → 否则取不到 `b`）。
- **状态**：✅ 已补斧并反向验证通过（2026-10-04）。fitcoach 复跑 C16 零告警（已修）。

### M-008 · 2026-10-04 · fitcoach(#32 E14-b) · `Method not found: 'StateProvider'` → **新增 C17（第三方废弃 API 名单）**

- **症状**：宿主 `flutter analyze` 报
  `error - The function 'StateProvider' isn't defined ... lib\providers\providers.dart:216:32 - undefined_function`
  （编译期硬错，连带 `test/widget_test.dart` 整个 `Failed to load`）。
- **根因**：Riverpod **3.x** 把 `StateProvider` 等一批 API 从主入口挪进
  `package:flutter_riverpod/legacy.dart`（`ChangeNotifierProvider` 甚至整个移除）。
  工程早在 #26 就把唯一的 `StateProvider` 预迁成 `Notifier`（`theme/theme_mode.dart`），
  但 E14-b 新写的 provider 又用了旧写法 —— **升级完成后的"回潮"没有工具把门**。
- **旧九板斧为何漏**：C11「符号用到没 import」比对的是**工程内声明**的符号，
  而这类符号**既不在工程内、也不在 import 列表里**（包把它挪走了）→ 完全落在盲区。
  本质是一类新问题：**第三方 API 的废弃/迁移**，不是 import 遗漏。
- **补的斧**：新增 **C17（第三方 API 废弃/迁移名单，表驱动）** ——
  `DEPRECATED_API_RULES` 每条 = (标识符, 豁免 import, 中英提示)；
  命中即 **ERROR**；匹配在 `mask_strings_comments` 之后做（注释/字符串提及不算）；
  豁免 import 为空表示「已被移除、怎么 import 都报」。首批 7 条（Riverpod 3 legacy 6 + 已移除 1）。
- **最小复现**：临时工程 5 个文件，实测
  ①`StateProvider` + 只 import 主入口 → **报**（a.dart:2）
  ②`StateProvider` + import `flutter_riverpod/legacy.dart` → 不报
  ③只在注释里提到 `StateProvider` → 不报
  ④`ChangeNotifierProvider`（legacy 也没有）→ **报**（d.dart:2）
  ⑤`Notifier` 正常写法 → 不报。**5/5 PASS**。
- **降噪要点**：必须走 `mask_strings_comments`，否则 `theme_mode.dart` /
  `providers.dart` 里「Riverpod 3 起 StateProvider 已移入 legacy」这类**说明性注释**会被误报
  （fitcoach 全工程复跑 C17 零告警，正是靠它）。
- **状态**：✅ 已补斧并反向验证通过（2026-10-04）。

---

### M-009 · 2026-10-05 · fitcoach(#33 E15-a) · 局部 helper 写成 `_custom` → **新增 C18（局部标识符 `_` 前缀）**

- **症状**：宿主 `flutter analyze` 报
  `info - The local variable '_custom' starts with an underscore ... test\data\custom_exercise_test.dart:16:12 - no_leading_underscores_for_local_identifiers`。
- **根因**：`_custom` 是写在 `main()` 里的**局部函数**。Dart 的 `_` 前缀规则是
  **作用域相关**的 —— 顶层 / 类成员的私有名用 `_` 合法；**函数体内**的局部变量、局部函数
  用 `_` 前缀**非法**（恰恰与 C12 管的「顶层私有必须 lowerCamelCase」方向相反）。
  正解：直接改名（局部去掉 `_`）。
- **旧九板斧为何漏**：C12 只管了「下划线」的两个**工程特有**形态（连续下划线、
  顶层私有 `_UpperCamel`），**没有"作用域"这个维度** —— 它连类成员都刻意排除，
  更不会去看函数体内的声明。
- **补的斧**：新增 **C18** —— 花括号栈区分「类体 / 函数体」，只判函数体内的
  `Type _name(` 与 `(var|final|const|late) [Type] _name =` 两种声明形态。
- **最小复现**：临时工程 `lib/main.dart`，实测
  ①局部函数 `String _custom({...}) => ...` → **报**
  ②`final _localVar = 1;` / `int _typedVar = 2;` → **报**
  ③类成员 `final int _member = 1;` / 顶层 `int _topLevel()` / `final int _topVar` → 不报
  ④调用 `_custom()` / `_topLevel()`（行首无类型无修饰）→ 不报。**3 命中 / 0 误报**。
- **降噪坑（首版两处，实测 236 条里只有 1 条真）**：
  ①**调用与声明长得一样** —— `_strength('s1', ...)` 与 `Type _name(` 无法从形态区分，
  必须要求「有类型段」或「有 `var/final/const/late` 修饰」之一，否则全是误报；
  ②类型段里可能混进**语句** —— `return split ? _buildSplit(...)` 里的 `split ?`
  会被当成类型（`?` 在类型字符类里），故类型段的**每个** token 都要过关键字黑名单，
  不能只查最后一个。
- **状态**：✅ 已补斧并反向验证通过（2026-10-05）。fitcoach 全工程复跑 **0 告警**。

---

### M-010 · 2026-10-05 · fitcoach(#47 F1 计时组) · 加字段漏了构造参数 → **新增 C19（final 字段初始化）**

- **症状**：宿主 `flutter test` 报
  ```
  lib/data/models.dart:293:9: Error: No named parameter with the name 'isTimed'.
  lib/data/models.dart:248:9: Context: Found this candidate, but the arguments don't match.
  lib/data/models.dart:236:14: Error: Final field 'isTimed' is not initialized.
  ```
  —— 连带 **39 个测试文件集体 `Failed to load`**（它们都要编译 `models.dart`）。
- **根因**：给 `Exercise` 加 `final bool isTimed;` 时，构造函数里的
  `this.isTimed = false,` **没写进去**（`toJson`/`fromJson`/`archivedCopy`/`asCustomCopy`
  四处都写了，唯独漏了构造 —— 而**只有这一处是编译期硬错**，其余四处是静默丢数据）。
  ⚠️ 另记一条人的坑：那一次 Edit **返回了「Successfully edited」但没落盘**，
  我又没回读校验 → 直到宿主报错才发现。**改模型字段后必须 grep 一遍五处落点。**
- **旧九板斧为何漏**：17 项里没有任何一条管「字段声明 ↔ 构造参数」的一致性 ——
  它既不是 import、也不是命名、也不是括号，是**语义完整性**类，纯文本工具此前完全没覆盖。
- **补的斧**：新增 **C19** —— 类/枚举体第一层的 `final T x;`（声明处无初值、不带 `late`）
  必须在类体里出现 `this.x` / `super.x` / `x =`（初始化列表）之一，否则报 **ERROR**。
- **最小复现**（实测三步 / Three-step verification）：
  ① 修复态跑全工程 → **0 命中**（129 文件零误报）；
  ② 删掉 `this.isTimed = false,` → **报 1 条**，`lib/data/models.dart:236`
     （与宿主报错行号**逐字一致**）；
  ③ 边界探针（临时 `lib/tmp_c19_probe.dart`，跑完即删）：
     `this.a` / `final int b = 1` / `late final int c` / `static final int s = 2` /
     函数体内 `final int local` / 初始化列表 `d = v` / 位置参数 `this.g`
     —— **全部不报**，只有漏改的 `e` 报 → **1 命中 / 0 误报**。
- **实现坑（记下来，同类必踩）**：`_CLASS_DECL_RE` 的 `^` **必须配 `re.M`** ——
  首版漏了它，`^` 只匹配文件开头 → 一个类都扫不到 → 反向验证直接 0 命中。
  **补斧后必须重跑「先造错、再还原」两步**，只看"干净"会误判为"已生效"。
- **状态**：✅ 已补斧并反向验证通过（2026-10-05）。fitcoach 全工程复跑 **0 告警**。

---

### M-011 · 2026-10-05 · fitcoach(#50 F5 导出提醒) · `x != null && ... x!` 冗余 `!` → **不补斧（能力边界）**

- **症状**：宿主 `flutter analyze` 报
  `warning - The '!' will have no effect because the receiver can't be null ... `
  `lib/services/export_reminder.dart:126:24 - unnecessary_non_null_assertion`。
- **根因**：同一逻辑表达式里先写了 `daysSinceExport != null`，分析器已把该**局部变量**
  提升（promotion）为非空，后面再写 `daysSinceExport!` 就是多余的。
- **旧九板斧为何漏**：18 项里没有一条管「flow promotion 后的多余 `!`」——
  它属**类型流分析**类，不是 import / 命名 / 括号 / 语义完整性。
- **归类**：⬜ **不补斧** —— 属**能力边界**，详见下方实验结论（与 M-004 同类）。
- **实验（已做，可复盘，别重复造）**：原型 C20「`x != null` 后 200 字符内出现 `x!`」
  （宁可漏报策略：只报**本文件行首声明过的局部变量**，排除类字段）。
  结果**两个方向都不达标**：
  ① **误报**：`features/onboarding/equipment_collection_page.dart` 的 `_occupation`
  命中 2 条 —— 它是 **State 的字段**（`late final ... _occupation = ...`，带等号，
  原型把它误收进"局部变量"集合）→ 字段**不会**被 promotion，`!` 是合法的；
  ② **漏报**：把真阳性写法（跨三行的 `daysSinceExport != null &&\n  daysSinceExport!`）
  喂给原型 → **0 命中**（原型正则的类型段与名字段之间缺边界约束，名字被截成
  `aysSinceExport`）—— 正则写错两次，说明**这类规则极易自欺**。
- **结论**：判准需要 ①字段 / 局部变量区分 ②`final` / `late` 修饰判定
  ③`private final` 字段也会 promotion ④闭包内 promotion 失效 ——
  等价于实现 flow analysis，与「纯文本近似」定位冲突（同 M-004）。
  **且代价极低**：这是 **warning 级**，不阻断编译，宿主 `flutter analyze` 第一轮必报。
- **改为人工纪律（已写进 SKILL.md）**：
  **同一个表达式里写了 `x != null` 之后，不要再对 `x` 用 `!`**（局部变量会被自动提升）；
  跨行写法尤其容易顺手加上 `!`。字段（`_x`）不受此限。
- **状态**：⬜ 不补斧（能力边界，已记录实验证据与替代纪律）。

---

### M-012 · 2026-10-05 · fitcoach（#53 恢复小时分档）· 控制流跨行没包块 → **新增 C20**

- **症状**：宿主 `flutter analyze` 报
  `info - Statements in an if should be enclosed in a block ... lib\services\recovery_service.dart:77:55 - curly_braces_in_flow_control_structures`（1 issue）。
  原文是长条件换行后顺手写成
  `if (!exDef.targetMuscles.contains(muscle) &&\n    !exDef.synergistMuscles.contains(muscle)) continue;`。
- **根因**：Dart 要求 if/else/for/while 的 body 包块；**但同一行的 `if (x) return;` 不报**。
  正确写法是给 then 加花括号。
- **旧九板斧为何漏**：18 项里没有任何一条管「控制流体是否包块」（C8 只数括号总数平衡）。
- **补的斧**：**C20**（v4.5 起 19 项），判据 = body 与 **`if` 关键字**不同行 + 不是块。
- **最小复现**：把 `recovery_service.dart` 里那段改回 `... ) continue;` →
  报 `[C20] lib/services/recovery_service.dart:77`；改回块 → 0 条。
- **⚠️ 首版实现踩的坑（记下来防复发）**：第一版按「body 与 `)` 是否同行」判断 →
  **造错样本 0 命中**（该样本里 `continue` 与 `)` 在同一行、但与 `if` 跨行，而 lint 照样报）。
  改成「与 `if` 关键字同行」后才命中。**反向验证必须真造错、不能只看全库 0 误报。**
- **防误报两道**（各缺一即满屏）：①单行 `if (x) return;` 放行（全库 **380 处**既有风格）
  ②以 `,` 结尾的是**集合字面量里的 if 元素**（`children: [if (x) const A(),]`，本工程约 56 处），
  不是语句、lint 也不报 → 放行。
- **状态**：✅ 已补斧并反向验证通过（真阳性 if / else 各造一次均命中、行号与宿主一致；
  还原后 138 文件 0 误报）。

---

### M-013 · 2026-10-05 · fitcoach(#54 容量预警卡) · 框架控件的命名参数写错 → **不补斧（能力边界）**

- **症状**：宿主 `flutter analyze` 报
  `error - The named parameter 'onSelected' isn't defined ... lib\widgets\volume_ceiling_card.dart:89:15 - undefined_named_parameter`；
  同根因让 `flutter test` 里 **39 个文件 Failed to load**（ERROR 级，阻断编译）。
- **根因**：`SegmentedButton` 的选择回调是 **`onSelectionChanged`**（回传 `Set<T>`，单选取 `.first`），
  不是 `onSelected`。我按 `FilterChip` 的写法照抄了签名。
- **旧九板斧为何漏**：C5（命名参数拼写）的池子只收集**项目内**定义的命名参数（904 个），
  不解析 Flutter SDK 源码 —— 这是设计前提（本工具要能在**无 SDK** 的环境跑）。
- **归类**：⬜ **不补斧** —— 属**能力边界**。
- **⚠️ 关键证据：不能简单加一条「`onSelected` 禁用」**（差点就这么干）：
  全库 **9 处合法** `onSelected` —— `FilterChip` / `ChoiceChip` / `PopupMenuButton`
  都**确实有**这个参数（`exercise_edit_page.dart:134/149`、`exercise_library_page.dart`
  6 处、`create_plan_page.dart:257/271`）。**只有 `SegmentedButton` 例外。**
  判准需要「回调挂在哪个控件上」的接收者类型推导 —— 与「纯文本近似」的定位冲突
  （同 M-004 / M-011）。硬加规则 = 9 个误报换 1 个真阳性，血亏。
- **代价评估**：ERROR 级，`flutter analyze` / `flutter test` **第一轮必报**，不会拖到运行时。
- **改为人工纪律**：
  **写控件回调前先确认该控件的参数名，不要从另一个控件复制签名。** 易混的一组：
  `SegmentedButton` = `onSelectionChanged(Set<T>)` 取 `.first`；
  `FilterChip` / `ChoiceChip` / `PopupMenuButton` = `onSelected(T)` 单值。
- **状态**：⬜ 不补斧（能力边界，已记录反例证据与替代纪律）。

---

## 新条目模板 / Template for New Entries

```markdown
### M-0XX · 日期 · 项目(功能) · 一句话症状 → **新增/修改 CXX**

- **症状**：宿主报的原文（error / lint 名 + 文件:行）。
- **根因**：为什么这是错 / 正确写法是什么。
- **旧九板斧为何漏**：缺哪一斧，或被哪条降噪滤掉了。
- **补的斧**：新增 CXX / 修改 CXX 的某条过滤。
- **最小复现**：改哪个文件哪一行、改成什么 → 期望报什么。
- **状态**：✅ 已补斧并反向验证通过 / ⬜ 待处理。
```
