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
