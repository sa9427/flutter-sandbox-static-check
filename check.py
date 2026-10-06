#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flutter 沙箱静态体检（九板斧 / v4.8 起 22 项）—— 纯标准库，无第三方依赖。

对 Flutter 工程的 lib/（v3 起默认含 test/）做文本静态检查，替代无法运行的 flutter analyze。
用法：
    python3 check.py --project C:/code/fitcoach
    python3 check.py --no-test        # 只扫 lib/

设计借鉴（开源精华）：
- dart-re-analyzer / pedant：severity 分级 + 跳过生成文件（*.g.dart / *.freezed.dart 等）。
- flutter_analyzer_script / refactoroscope：unused 的"声明-引用"判定思路；
  本工具对 dart: 内建库用公开符号表、对 as/show 用精确规则。
"""
import argparse
import os
import re
import sys


def bi(zh, en):
    """返回中英双语字符串：中文为主、英文补充。
    Return a bilingual string: Chinese primary, English supplementary."""
    return '%s  /  %s' % (zh, en)

# ── 常见 Flutter/Dart 命名参数白名单（降低 C6 HINT 误报）───────────────
COMMON_PARAMS = {
    'key', 'child', 'children', 'builder', 'onPressed', 'onTap', 'onChanged', 'value',
    'label', 'title', 'color', 'padding', 'margin', 'decoration', 'style', 'text', 'icon',
    'context', 'vsync', 'controller', 'hint', 'obscureText', 'enabled', 'expanded', 'flex',
    'mainAxisAlignment', 'crossAxisAlignment', 'scrollDirection', 'shrinkWrap', 'physics',
    'itemBuilder', 'itemCount', 'onLongPress', 'leading', 'trailing', 'subtitle', 'dense',
    'elevation', 'shape', 'clipBehavior', 'alignment', 'width', 'height', 'fit', 'placeholder',
    'initialValue', 'validator', 'autofocus', 'maxLines', 'minLines', 'keyboardType',
    'textInputAction', 'onSubmitted', 'splashFactory', 'visualDensity', 'selected', 'onSelected',
    # 常见 Flutter 框架参数（签名在框架内，不在 lib/ 扫描范围）
    'seedColor', 'gaplessPlayback', 'loadingBuilder', 'horizontal', 'bodyFatPct', 'left',
    'crossAxisCount', 'applicationName', 'applicationVersion', 'semanticsLabel', 'filter',
    'restorationId', 'useMaterial3', 'scaffoldMessengerKey', 'navigatorKey', 'themeMode',
    'debugShowCheckedModeBanner', 'locale', 'supportedLocales', 'localizationsDelegates',
    # Duration / DateTime 等 dart:core 参数（签名在 SDK 内，扫描不到）
    'seconds', 'milliseconds', 'microseconds', 'minutes', 'hours', 'days',
    # dart:io 目录遍历参数（同上；2026-10-06 实踩：`Directory.listSync(recursive: true)`
    # 被 C6 报 HINT —— SDK 签名不在 lib/ 扫描范围内，属误报）
    'recursive', 'followLinks',
    # flutter widgets 的分隔构造器参数（同上；2026-10-06 实踩：
    # `ListView.separated(separatorBuilder: ...)` 被 C6 报 HINT）
    'separatorBuilder',
    # flutter_test 常用参数（测试代码的 expect(..., reason:) 等）
    'reason', 'skip', 'matcher', 'variants', 'tags',
    # 本工程自定义参数
    'workMet', 'totalSets', 'avgMet', 'withReps', 'restSeconds',
}

# 枚举常见 getter/方法（不算未知成员）
ENUM_SAFE = {'name', 'values', 'index', 'label', 'value', 'entries', 'length', 'toString',
             'runtimeType', 'nameEn'}

# ── dart: 内建库公开符号表（C7 检测未用 import 的依据）────────────────────
# 只列"可选导入"的库；以符号是否出现判定"未使用"，命中即 HINT（非 ERROR）。
DART_LIB_SYMBOLS = {
    'typed_data': {'Uint8List', 'Int8List', 'Uint16List', 'Int16List', 'Uint32List',
                   'Int32List', 'Uint64List', 'Int64List', 'Float32List', 'Float64List',
                   'Float32x4', 'Float64x2', 'Int32x4', 'ByteData', 'ByteBuffer', 'Endian',
                   'Endianness', 'TransferableTypedData'},
    'convert': {'json', 'jsonEncode', 'jsonDecode', 'JsonEncoder', 'JsonDecoder', 'JsonCodec',
                'utf8', 'base64', 'base64Url', 'ascii',
                'latin1', 'SystemEncoding', 'Encoding', 'Codec', 'Converter', 'Decoder',
                'Encoder', 'ClosableStringSink', 'StringConversionSink'},
    'math': {'min', 'max', 'pow', 'sqrt', 'sin', 'cos', 'tan', 'atan', 'atan2', 'exp', 'log',
             'pi', 'e', 'Random', 'Point', 'Rectangle', 'MutableRectangle'},
    # 'unawaited'：2026-10-05 补。此前不在表里 → `import 'dart:async'` 只用它时
    # C7 会误报「公开符号均未出现」（实踩：widgets/volume_ceiling_card.dart）。
    'async': {'Future', 'Stream', 'StreamController', 'StreamSubscription', 'Completer', 'Timer',
              'Zone', 'scheduleMicrotask', 'runZoned', 'AsyncError', 'FutureOr',
              'unawaited'},
    'collection': {'Queue', 'ListQueue', 'DoubleLinkedQueue', 'LinkedHashMap', 'LinkedHashSet',
                   'HashMap', 'HashSet', 'UnmodifiableListView', 'UnmodifiableMapView',
                   'UnmodifiableSetView', 'MapBase', 'SetBase', 'ListBase'},
    'io': {'File', 'Directory', 'FileSystemEntity', 'Platform', 'FileMode', 'IOSink',
           'HttpClient', 'HttpServer', 'HttpHeaders', 'IOException', 'Process', 'ProcessInfo'},
    'ui': {'Color', 'Rect', 'Offset', 'Size', 'Canvas', 'Paint', 'TextStyle', 'FontWeight',
           'Radius', 'BorderRadius', 'Alignment', 'EdgeInsets', 'Image', 'Picture', 'Scene',
           'Window', 'Locale', 'TextDirection', 'BlendMode', 'Clip'},
    'developer': {'log', 'timeline', 'Service', 'ServiceExtensionHandler', 'postEvent'},
    'isolate': {'Isolate', 'ReceivePort', 'SendPort', 'TransferableTypedData'},
    'ffi': {'Pointer', 'Struct', 'Union', 'Allocator', 'Arena', 'DynamicLibrary', 'Native'},
}

# 跳过的生成/无关文件（借鉴 dart-re-analyzer / pedant 的 exclude 思路）
EXCLUDE_RE = re.compile(r'(\.g\.dart$|\.freezed\.dart$|\.config\.dart$|'
                        r'[\\/]build[\\/]|[\\/]\.dart_tool[\\/])')


def find_dart_files(lib_dir):
    out = []
    for root, _, files in os.walk(lib_dir):
        for f in files:
            if not f.endswith('.dart'):
                continue
            full = os.path.join(root, f)
            if EXCLUDE_RE.search(full):
                continue
            out.append(full)
    return out


def read(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return fh.read()
    except (OSError, UnicodeError):
        return ''


def strip_strings_comments(text):
    """去掉字符串字面量（含三引号与 ${} 插值）与注释，便于括号平衡检查。"""
    out = []
    i, n = 0, len(text)
    in_line = False
    in_block = False
    while i < n:
        c = text[i]
        two = text[i:i + 2]
        three = text[i:i + 3]
        if in_line:
            if c == '\n':
                in_line = False
                out.append(' ')
            i += 1
            continue
        if in_block:
            if two == '*/':
                in_block = False
                i += 2
                out.append(' ')
            else:
                i += 1
            continue
        if two == '//':
            in_line = True
            i += 2
            continue
        if two == '/*':
            in_block = True
            i += 2
            continue
        # 三引号优先
        if three in ('"""', "'''"):
            out.append(' ')
            i += 3
            while i < n:
                if text[i:i + 3] == three:
                    i += 3
                    break
                if text[i] == '\\':
                    i += 2
                    continue
                i += 1
            continue
        if c in ('"', "'"):
            quote = c
            out.append(' ')
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def mask_strings_comments(text):
    """把字符串字面量与注释替换成**等长**空格（保留换行与字符偏移）。

    与 strip_strings_comments 的区别：后者会删除字符，在其上做正则匹配后
    无法回原文定位行号；本函数保证 `len(mask(t)) == len(t)` 且每个换行仍在
    原位，因此匹配结果的 offset 可直接用于原文。用于 C6 命名参数检查。
    """
    out = []
    i, n = 0, len(text)

    def blank(ch):
        return '\n' if ch == '\n' else ' '

    while i < n:
        c = text[i]
        two = text[i:i + 2]
        if two == '//':
            while i < n and text[i] != '\n':
                out.append(' ')
                i += 1
            continue
        if two == '/*':
            while i < n and text[i:i + 2] != '*/':
                out.append(blank(text[i]))
                i += 1
            if i < n:
                out.append('  ')
                i += 2
            continue
        if c in ('"', "'"):
            three = text[i:i + 3]
            if three in ('"""', "'''"):
                out.append('   ')
                i += 3
                while i < n and text[i:i + 3] != three:
                    out.append(blank(text[i]))
                    i += 1
                if i < n:
                    out.append('   ')
                    i += 3
                continue
            out.append(' ')
            i += 1
            while i < n:
                if text[i] == '\\':
                    out.append(' ')
                    i += 1
                    if i < n:
                        out.append(blank(text[i]))
                        i += 1
                    continue
                if text[i] == c:
                    out.append(' ')
                    i += 1
                    break
                out.append(blank(text[i]))
                i += 1
            continue
        out.append(c)
        i += 1
    return ''.join(out)


# ── 检查 1/3：import 解析 + 相对导入 ─────────────────────────────────────
def check_imports(files, lib_dir, project_root, findings, pkg=None):
    self_prefix = ('package:%s/' % pkg) if pkg else 'package:fitcoach/'
    for fp in files:
        text = read(fp)
        rel = os.path.relpath(fp, lib_dir).replace('\\', '/')
        filedir = os.path.dirname(fp)
        for m in re.finditer(r"^\s*import\s+'([^']+)'", text, re.M):
            spec = m.group(1)
            lineno = text.count('\n', 0, m.start()) + 1
            if spec.startswith('dart:'):
                continue
            if spec.startswith('./') or spec.startswith('../'):
                findings.append(('ERROR', 'C3', fp, lineno,
                                 bi('相对导入残留：%s（建议改用 package: 绝对导入）' % spec,
                                    'Relative import leftover: %s — prefer package: absolute import' % spec)))
                continue
            if spec.startswith(self_prefix):
                target = os.path.join(lib_dir, spec[len(self_prefix):])
                if not os.path.exists(target):
                    findings.append(('ERROR', 'C1', fp, lineno,
                                     bi('断 import：%s 不存在' % spec,
                                        'Broken import: %s does not exist' % spec)))
                continue
            # 其它 package:X/... —— 交给 C2 依赖一致性检查
    return


# ── 检查 2：pubspec 依赖一致性 ──────────────────────────────────────────
def read_pubspec_name(project_root):
    """取 pubspec 的 name，用于判定「本工程自身的 package: 导入」。

    原先硬编码 fitcoach，导致本工具对任何其它工程都静默失效（C1/C7 的
    工程内 import 分支永不命中）。公开后必须泛化。
    """
    text = read(os.path.join(project_root, 'pubspec.yaml'))
    m = re.search(r"^name\s*:\s*([\w_-]+)\s*$", text, re.M)
    return m.group(1) if m else None


def parse_pubspec_deps(project_root):
    p = os.path.join(project_root, 'pubspec.yaml')
    text = read(p)
    deps = set()
    for block in ('dependencies:', 'dev_dependencies:'):
        i = text.find(block)
        if i < 0:
            continue
        j = text.find('\n', i)
        seg = ''
        k = j + 1
        while k < len(text):
            line = text[k:]
            nl = line.find('\n')
            cur = line[:nl] if nl >= 0 else line
            if cur and not cur[0].isspace():
                break
            seg += cur + '\n'
            if nl < 0:
                break
            k += nl + 1
        for m in re.finditer(r"^\s{2}([A-Za-z_][\w_-]*):", seg, re.M):
            deps.add(m.group(1))
    deps.add('flutter')
    deps.add('flutter_test')
    return deps


def parse_pubspec_runtime_deps(project_root):
    """仅取 runtime dependencies（不含 dev），用于 C10 未用依赖检查。"""
    p = os.path.join(project_root, 'pubspec.yaml')
    text = read(p)
    deps = []
    i = text.find('dependencies:')
    if i < 0:
        return deps
    j = text.find('\n', i)
    k = j + 1
    while k < len(text):
        line = text[k:]
        nl = line.find('\n')
        cur = line[:nl] if nl >= 0 else line
        if cur and not cur[0].isspace():
            break
        m = re.match(r'\s{2}([A-Za-z_][\w_-]*):', cur)
        if m and m.group(1) not in ('flutter',):
            deps.append(m.group(1))
        if nl < 0:
            break
        k += nl + 1
    return deps


def check_pubspec_deps(files, deps, findings, pkg=None):
    for fp in files:
        text = read(fp)
        for m in re.finditer(r"^\s*import\s+'([^']+)'", text, re.M):
            spec = m.group(1)
            if not spec.startswith('package:'):
                continue
            p = spec[len('package:'):].split('/')[0]
            if p == pkg:  # 本工程自身（原先硬编码 fitcoach，对其它工程会误报）
                continue
            if p not in deps:
                lineno = text.count('\n', 0, m.start()) + 1
                findings.append(('ERROR', 'C2', fp, lineno,
                                 bi('import 的 package:%s 未在 pubspec 声明' % p,
                                    'imported package:%s not declared in pubspec.yaml' % p)))


# ── 检查 4：枚举值存在性 ────────────────────────────────────────────────
def collect_enums(lib_dir):
    enums = {}  # name -> set(values)
    for root, _, files in os.walk(lib_dir):
        for f in files:
            fp = os.path.join(root, f)
            if not f.endswith('.dart') or EXCLUDE_RE.search(fp):
                continue
            text = read(fp)
            for m in re.finditer(r'enum\s+(\w+)\s*(?:<[^>]*>)?\s*\{', text):
                start = m.end() - 1  # 指向 {
                depth = 0
                end = start
                while end < len(text):
                    if text[end] == '{':
                        depth += 1
                    elif text[end] == '}':
                        depth -= 1
                        if depth == 0:
                            break
                    end += 1
                body = text[start + 1:end]
                vals = set()
                for line in body.splitlines():
                    s = line.strip()
                    if not s or s.startswith('//') or s.startswith('@') \
                            or s.startswith('const') or s.startswith('final') \
                            or s.startswith('this.') or '{' in s or '=>' in s:
                        continue
                    s = s.rstrip(',;').strip()
                    if not s:
                        continue
                    # 一行多成员（light, medium, hard;）也要逐个识别
                    for mm in re.finditer(r'([A-Za-z_]\w*)\s*(?:\([^)]*\))?', s):
                        vals.add(mm.group(1))
                if vals:
                    enums[m.group(1)] = vals
    return enums


def check_enum_usage(files, enums, findings):
    # 危险项：Enum.values.byName('X') 中 X 不存在 → ERROR（运行时抛异常）
    for fp in files:
        text = read(fp)
        for m in re.finditer(r'(\w+)\.values\.byName\(\s*[\'"]([^\'"]+)[\'"]\s*\)', text):
            enum_name, val = m.group(1), m.group(2)
            if enum_name in enums and val not in enums[enum_name]:
                lineno = text.count('\n', 0, m.start()) + 1
                findings.append(('ERROR', 'C4', fp, lineno,
                                 bi('%s.values.byName(\'%s\') 的值不存在' % (enum_name, val),
                                    '%s.values.byName(\'%s\') value does not exist' % (enum_name, val))))
        # 直接点访问：Enum.x 非已知值/安全成员 → HINT
        for m in re.finditer(r'\b([A-Z]\w*)\.([A-Za-z_]\w*)\b', text):
            enum_name, member = m.group(1), m.group(2)
            if enum_name in enums and member not in enums[enum_name] and member not in ENUM_SAFE:
                lineno = text.count('\n', 0, m.start()) + 1
                findings.append(('HINT', 'C4', fp, lineno,
                                 bi('%s.%s 可能不是 %s 的枚举值/成员' % (enum_name, member, enum_name),
                                    '%s.%s may not be an enum value/member of %s' % (enum_name, member, enum_name))))


# ── 检查 5：assets 引用缺失 ─────────────────────────────────────────────
def parse_pubspec_assets(project_root):
    p = os.path.join(project_root, 'pubspec.yaml')
    text = read(p)
    assets = []
    i = text.find('flutter:')
    if i < 0:
        return assets
    seg = text[i:]
    j = seg.find('assets:')
    if j < 0:
        return assets
    seg = seg[j + len('assets:'):]
    k = 0
    while k < len(seg):
        line = seg[k:]
        nl = line.find('\n')
        cur = line[:nl] if nl >= 0 else line
        if cur and not cur[0].isspace():
            break
        mm = re.match(r'\s*-\s*([^\s#]+)', cur)
        if mm:
            assets.append(mm.group(1))
        if nl < 0:
            break
        k += nl + 1
    return assets


def check_assets(files, assets, findings):
    ref_re = re.compile(r'(?:AssetImage|exact|rootBundle\.load|loadString)\s*\(\s*[\'"]([^\'"]+)[\'"]')
    for fp in files:
        text = read(fp)
        for m in ref_re.finditer(text):
            ref = m.group(1)
            ok = any(ref == a or ref.startswith(a) or (a.endswith('/') and ref.startswith(a))
                     for a in assets)
            if not ok:
                lineno = text.count('\n', 0, m.start()) + 1
                findings.append(('HINT', 'C5', fp, lineno,
                                 bi('assets 引用可能缺失：%s（pubspec 未声明）' % ref,
                                    'asset reference possibly missing: %s (not declared in pubspec)' % ref)))


# ── 检查 6：命名参数拼写（仅小写业务函数，HINT）────────────────────────
def collect_named_params(lib_dir):
    params = set()
    for root, _, files in os.walk(lib_dir):
        for f in files:
            fp = os.path.join(root, f)
            if not f.endswith('.dart') or EXCLUDE_RE.search(fp):
                continue
            text = read(fp)
            # 只取一层花括号（[^{}] 避免跨嵌套误配）
            #
            # ⚠️ 2026-10-06 修（M-024）：`[^{}]*` **容不下一层花括号默认值** ——
            # 签名里只要出现 `const {}` / `= {}`（例如
            # `Map<String, E1rmEstimate> e1rmByExercise = const {}`），正则就无法
            # 从签名的 `{` 走到结尾的 `}`（中途撞见 `{`），只能退化成匹配
            # `const {}` 这个**空块** → 该签名的**所有命名参数都没进池子** →
            # 这些参数在调用点被误报成「拼写错误」（实踩：generators.dart 的
            # `superset:`）。改成容忍**一层**嵌套花括号即可。
            for m in re.finditer(r'\{((?:[^{}]|\{[^{}]*\})*)\}', text):
                body = m.group(1)
                # 先剥掉 `///` 文档注释行（2026-10-04 修）：
                # 参数**上方**的注释里若出现 `= `（例如「`null` = 全量」），
                # 属于同一 part（注释与参数之间没有逗号），而下面的「按 = 截断
                # 取默认值之前」会把参数名一起截掉 → 收进去的是 `null` 而不是
                # 真正的参数名 → 该参数在所有调用点被误报成「拼写错误」。
                # （实踩：buildVolumeTrend 的 exerciseIds）
                # 顺带也消掉「注释里的逗号把 part 切碎」的问题。
                body = '\n'.join(ln for ln in body.split('\n')
                                 if not ln.strip().startswith('///'))
                for part in body.split(','):
                    part = part.strip()
                    if not part:
                        continue
                    # 形式一：name: 默认值（含 required Type name: x）
                    pm = re.search(r'\b([A-Za-z_]\w*)\s*:', part)
                    if pm:
                        params.add(pm.group(1))
                        continue
                    # 形式二：Type? name / required Type name / this.name
                    # —— 无默认值的命名参数此前因要求冒号而被漏收，导致
                    #    _copy(s, weight: v) 之类被误报成拼写错误。
                    #    注意先截掉 `= 默认值`（{this.isBodyweight = false} 用的是
                    #    等号而非冒号，不截会把默认值名 false 当成参数名）。
                    pm = re.search(r'\b([A-Za-z_]\w*)\s*$', part.split('=')[0].strip())
                    if pm:
                        params.add(pm.group(1))
                # 兼容旧逻辑：整段内 name: 的取值（含逗号被泛型吞掉的情况）
                for pm in re.finditer(r'(?:required\s+)?[\w<>?,\s]*?\b([A-Za-z_]\w*)\s*:', body):
                    params.add(pm.group(1))
    return params


def check_named_params(files, all_params, findings):
    for fp in files:
        text = read(fp)
        # 先剥掉字符串与注释再匹配：否则 `debugPrint('... FlutterError: ...')`
        # 这类「字符串里带冒号的词」会被当成命名参数误报（2026-10-01 修）。
        # 用等长掩码（mask_strings_comments）而非 strip_strings_comments，
        # 保证 offset 与原文对齐，行号才不会错位。
        code = mask_strings_comments(text)
        for m in re.finditer(r'\b([a-z]\w*)\s*\(([^)]*)\)', code):
            args = m.group(2)
            for am in re.finditer(r'([A-Za-z_]\w*)\s*:', args):
                name = am.group(1)
                # 跳过 `Icons.stop : Icons.play_arrow` 这类「静态/枚举成员后紧跟
                # 三元运算符冒号」——它不是命名参数（此前是全工程最大误报源）。
                if am.start() > 0 and args[am.start() - 1] == '.':
                    continue
                if name in COMMON_PARAMS or name in all_params:
                    continue
                lineno = text.count('\n', 0, m.start()) + 1
                findings.append(('HINT', 'C6', fp, lineno,
                                 bi('命名参数可能拼写错误：%s:（未在工程任何签名中声明）' % name,
                                    'named argument possibly misspelled: %s: (not declared in any signature)' % name)))


# ── 检查 7：未使用 import（HINT）──────────────────────────────────────
def parse_show_hide(rest):
    show_syms = None
    hide_syms = None
    sm = re.search(r'\bshow\s+([^;]+)', rest)
    if sm:
        seg = sm.group(1)
        hm = re.search(r'\bhide\s+', seg)
        if hm:
            seg = seg[:hm.start()]
        show_syms = [x.strip() for x in seg.split(',') if x.strip()]
    hm2 = re.search(r'\bhide\s+([^;]+)', rest)
    if hm2:
        hide_syms = [x.strip() for x in hm2.group(1).split(',') if x.strip()]
    return show_syms, hide_syms


def check_unused_imports(files, lib_dir, symbols, findings, pkg=None, ext_members=None):
    self_prefix = ('package:%s/' % pkg) if pkg else 'package:fitcoach/'
    for fp in files:
        text = read(fp)
        filedir = os.path.dirname(fp)
        for m in re.finditer(r"^\s*import\s+'([^']+)'([^;]*);", text, re.M):
            spec = m.group(1)
            rest = m.group(2)
            lineno = text.count('\n', 0, m.start()) + 1
            as_m = re.search(r'\bas\s+(\w+)', rest)
            as_prefix = as_m.group(1) if as_m else None
            show_syms, hide_syms = parse_show_hide(rest)
            # 1) as 前缀：以 prefix. 是否出现判定（精确）
            if as_prefix:
                if not re.search(r'\b%s\.' % re.escape(as_prefix), text):
                    findings.append(('HINT', 'C7', fp, lineno,
                                     bi('import 未使用：%s（as %s 从未以 %s. 引用）'
                                        % (spec, as_prefix, as_prefix),
                                        'unused import: %s (as %s never referenced as %s.)'
                                        % (spec, as_prefix, as_prefix))))
                continue
            # 2) show 精确符号
            if show_syms:
                if not any(re.search(r'\b%s\b' % re.escape(s), text) for s in show_syms):
                    findings.append(('HINT', 'C7', fp, lineno,
                                     bi('import 未使用：%s（show 的符号 %s 均未出现）'
                                        % (spec, ','.join(show_syms)),
                                        'unused import: %s (none of shown symbols %s appear)'
                                        % (spec, ','.join(show_syms)))))
                continue
            # 3) dart: 内建库：以公开符号是否出现判定
            if spec.startswith('dart:'):
                lib = spec[5:]
                if lib in DART_LIB_SYMBOLS:
                    cands = set(DART_LIB_SYMBOLS[lib])
                    if hide_syms:
                        cands -= set(hide_syms)
                    if cands and not any(re.search(r'\b%s\b' % re.escape(s), text) for s in cands):
                        findings.append(('HINT', 'C7', fp, lineno,
                                         bi('import 未使用：%s（其公开符号均未出现）' % spec,
                                            'unused import: %s (none of its public symbols appear)' % spec)))
                continue
            # 4) 工程内（package:<self>）—— 相对导入已由 C3 处理，这里只判未使用
            if spec.startswith(self_prefix):
                rel = os.path.normpath(spec[len(self_prefix):]).replace('\\', '/')
                body = re.sub(r"^\s*import\s+'[^']+'[^;]*;\s*$", '', text, flags=re.M)
                # extension 成员以「接收者.成员」调用（如 IntensityColorX 的 .color），
                # 符号名本身不会出现在文本里，须单独按 .成员 判定，否则会误报。
                if ext_members and rel in ext_members and any(
                        re.search(r'\.%s\b' % re.escape(mem), body) and
                        (not on_type or re.search(r'\b%s\b' % re.escape(on_type), body))
                        for (mem, on_type) in ext_members[rel]):
                    continue
                # symbols 的键是相对 lib 的路径，必须同口径查；此前用绝对路径
                # 查询导致本分支永远拿不到符号 → 工程内未用 import 从未被抓到。
                imported = symbols.get(rel)
                if imported and not any(re.search(r'\b%s\b' % re.escape(s), body) for s in imported):
                    findings.append(('HINT', 'C7', fp, lineno,
                                     bi('import 可能未使用：%s' % spec,
                                        'import possibly unused: %s' % spec)))
                continue
            # 5) 外部 package（无 as/show）—— 未知导出符号，跳过以免误报
            continue


# ── 检查 8：括号/结构平衡（HINT）──────────────────────────────────────
def check_brackets(files, findings):
    # 只数 () [] {}；尖括号 <>（泛型/比较/=>）一律忽略，避免 Dart 全文件误报
    pairs = {')': '(', '}': '{', ']': '['}
    for fp in files:
        text = read(fp)
        stripped = strip_strings_comments(text)
        stack = []
        for c in stripped:
            if c in ('(', '{', '['):
                stack.append(c)
            elif c in (')', '}', ']'):
                if not stack or stack[-1] != pairs[c]:
                    findings.append(('HINT', 'C8', fp, -1, bi('括号可能不配对：%s' % c,
                                                             'brackets possibly unbalanced: %s' % c)))
                    break
                stack.pop()
        if stack:
            findings.append(('HINT', 'C8', fp, -1, bi('括号未闭合：%s 残留' % stack[-1],
                                                     'unclosed bracket: %s remains' % stack[-1])))


# ── 检查 9：字符串型枚举残留（HINT）──────────────────────────────────
LEVEL_LIKE = {'beginner', 'intermediate', 'advanced', 'light', 'medium', 'hard',
              'compound', 'isolation', 'cardio', 'bodyweight', 'running', 'cycling',
              'swimming', 'walking', 'elliptical', 'rowing', 'hiit', 'other'}


def check_string_enum(files, findings):
    for fp in files:
        text = read(fp)
        for m in re.finditer(r"'([a-z]+)'", text):
            tok = m.group(1)
            if tok in LEVEL_LIKE:
                ctx = text[max(0, m.start() - 40):m.start()]
                if re.search(r'(Level|Intensity|ExerciseType|EquipmentType|CardioType|CardioIntensity)\b', ctx) \
                        or re.search(r'\.\s*$', ctx):
                    lineno = text.count('\n', 0, m.start()) + 1
                    findings.append(('HINT', 'C9', fp, lineno,
                                     bi('疑似字符串型枚举残留：\'%s\'' % tok,
                                        'suspected string-enum residue: \'%s\'' % tok)))


# ── 文件顶层符号收集（供 C7 工程内 import 判定）──────────────────────
def collect_file_symbols(lib_dir):
    """返回 (file_path(rel) -> 顶层标识符集合, 各文件的 extension 成员名集合)。

    extension 成员（如 IntensityColorX 的 `.color`）是以「接收者.成员」调用的，
    成员名不会以独立标识符形式出现在调用方文本里，必须与顶层符号分开判定。
    """
    sym = {}
    ext_members = {}
    for root, _, files in os.walk(lib_dir):
        for f in files:
            fp = os.path.join(root, f)
            if not f.endswith('.dart') or EXCLUDE_RE.search(fp):
                continue
            names = set()
            members = []          # [(成员名, extension 的 on 类型)]
            cur_on_type = None
            in_ext = False
            for raw in read(fp).split('\n'):
                line = raw.rstrip()
                if not line:
                    continue
                # 只取顶层声明（无缩进）：与 analyzer 的「库公开命名空间」口径一致，
                # 类成员不参与未用 import 判定（否则 build/dispose 之类会到处命中）。
                if not line[0].isspace():
                    in_ext = False
                    m = re.match(
                        r'(?:abstract\s+|base\s+|final\s+|sealed\s+|interface\s+|mixin\s+)*'
                        r'(?:class|enum|mixin|typedef|extension)\s+([A-Za-z_]\w*)', line)
                    if m:
                        names.add(m.group(1))
                        if re.match(
                                r'(?:abstract\s+|base\s+|final\s+|sealed\s+|interface\s+|mixin\s+)*'
                                r'extension\s+', line):
                            in_ext = True
                            om = re.search(r'\bon\s+([A-Za-z_][\w<>,\s\[\]?]*)', line)
                            cur_on_type = om.group(1).strip() if om else None
                        continue
                    # 顶层函数（返回类型可含泛型）
                    #
                    # ⚠️ 2026-10-06 修（M-025）：函数名后的**泛型参数**此前没被容忍
                    # （`Future<T?> showAppDialog<T>({` 里的 `<T>`），导致这类顶层函数
                    # **完全收不进符号表** → 调用它的文件被 C7 误报成「import 未使用」
                    # （实踩：app_dialog.dart 的 showAppDialog / showAppSheet，12 处误报）。
                    m = re.match(
                        r'(?:external\s+)?[A-Za-z_][\w<>,\s\[\]?]*?\s+([a-z_]\w*)\s*'
                        r'(?:<[^<>]*>)?\s*\(', line)
                    if m:
                        names.add(m.group(1))
                        continue
                    # 顶层变量 / 常量（类型可含泛型，需先剥离 <...> 才能取到名字）
                    m = re.match(
                        r'(?:late\s+|final\s+|const\s+|var\s+)([\w<>,\s\[\]?]*?)\s*'
                        r'([A-Za-z_]\w*)\s*=', line)
                    if m:
                        names.add(m.group(2))
                        continue
                elif in_ext:
                    # extension 体：抽 getter / 方法名
                    m = re.search(r'\bget\s+(\w+)', line)
                    if m:
                        members.append((m.group(1), cur_on_type))
                        continue
                    m = re.match(r'\s+[A-Za-z_][\w<>,\s\[\]?]*?\s+(\w+)\s*\(', line)
                    if m:
                        members.append((m.group(1), cur_on_type))
            # 单字母标识符不做「已引用」的证据（sort((a, b) => ...) 的 b 会误命中），
            # 私有名（_ 开头）不在库公开命名空间内，同样不能作为证据。
            names = {n for n in names if len(n) >= 2 and not n.startswith('_')}
            members = [(m, t) for (m, t) in members
                       if len(m) >= 2 and not m.startswith('_')]
            rel = os.path.relpath(fp, lib_dir).replace('\\', '/')
            sym[rel] = names
            if members:
                ext_members[rel] = members
    return sym, ext_members


# ── 检查 10：声明但从未 import 的依赖（HINT，借鉴 flutter_analyzer_script）
def check_unused_deps(files, runtime_deps, findings):
    used = set()
    for fp in files:
        text = read(fp)
        for m in re.finditer(r"^\s*import\s+'([^']+)'", text, re.M):
            spec = m.group(1)
            if spec.startswith('package:'):
                used.add(spec[len('package:'):].split('/')[0])
    for dep in runtime_deps:
        if dep in ('flutter',):
            continue
        if dep not in used:
            findings.append(('HINT', 'C10', os.path.join(project_root_ref, 'pubspec.yaml'),
                             0, bi('依赖 %s 已声明但无任何文件 import（可能未使用）' % dep,
                                   'dependency %s declared but never imported (possibly unused)' % dep)))


# project_root_ref 供 C10 输出路径使用（main 中赋值）
project_root_ref = '.'


def _spec_to_rel(spec, base):
    """把 import/export 的 spec 转成相对 lib_dir 的路径；非本工程包返回 None。"""
    if spec.startswith('package:'):
        rest = spec[len('package:'):]
        if '/' in rest:
            return rest.split('/', 1)[1]
        return None
    return os.path.normpath(os.path.join(base, spec)).replace('\\', '/')


def collect_part_export(lib_dir):
    """返回 (part_map, export_map)：文件(rel) -> 其 part/export 的目标文件(rel)。

    - `part 'x.dart'`   ：x 的顶层声明**并入本文件**命名空间（import 本文件即可见 x 的符号）。
    - `export 'x.dart'` ：x 的符号被本文件再导出（import 本文件即可见 x 的符号）。

    二者都会让「符号在哪可见」≠「符号定义在哪」，C11 判定前必须先展开成闭包。
    """
    part_map, export_map = {}, {}
    for root, _, files in os.walk(lib_dir):
        for f in files:
            fp = os.path.join(root, f)
            if not f.endswith('.dart') or EXCLUDE_RE.search(fp):
                continue
            rel = os.path.relpath(fp, lib_dir).replace('\\', '/')
            base = os.path.dirname(rel)
            text = read(fp)
            parts = [os.path.normpath(os.path.join(base, m.group(1))).replace('\\', '/')
                     for m in re.finditer(r"^\s*part\s+'([^']+)'", text, re.M)]
            exports = []
            for m in re.finditer(r"^\s*export\s+'([^']+)'", text, re.M):
                t = _spec_to_rel(m.group(1), base)
                if t:
                    exports.append(t)
            part_map[rel] = parts
            export_map[rel] = exports
    return part_map, export_map


def _visible_files(seeds, part_map, export_map):
    """从 seeds 出发 BFS 展开 part/export 传递闭包，得到「可见文件」集合。"""
    seen, stack = set(), list(seeds)
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in part_map.get(cur, []):
            if nxt not in seen:
                stack.append(nxt)
        for nxt in export_map.get(cur, []):
            if nxt not in seen:
                stack.append(nxt)
    return seen


def _local_declared_names(text):
    """本文件自己声明的标识符（含私有 `_x`）——用到它们不算「没 import」。

    只取顶层会漏掉三类高频声明，都会造成 C11 误报（2026-10-03 实踩）：
    - 参数/字段声明 `List<double> recentPeakRpe`（`planDeload` 的形参，不是调用）
    - 构造参数 `this.phase`
    - 增强枚举成员 `enum CardioPhase { main('主体') }` 里的 `main`
    """
    code = mask_strings_comments(text)
    names = set()
    for raw in text.split('\n'):
        line = raw.rstrip()
        if not line or line[0].isspace():
            continue
        m = re.match(
            r'(?:abstract\s+|base\s+|final\s+|sealed\s+|interface\s+|mixin\s+)*'
            r'(?:class|enum|mixin|typedef|extension)\s+([A-Za-z_]\w*)', line)
        if m:
            names.add(m.group(1))
            continue
        m = re.match(r'(?:external\s+)?[A-Za-z_][\w<>,\s\[\]?]*?\s+([a-zA-Z_]\w*)\s*\(', line)
        if m:
            names.add(m.group(1))
            continue
        m = re.match(r'(?:late\s+|final\s+|const\s+|var\s+)?[\w<>,\s\[\]?]*?\s*'
                     r'([A-Za-z_]\w*)\s*=', line)
        if m:
            names.add(m.group(1))

    # 构造参数 this.x
    for m in re.finditer(r'\bthis\.([A-Za-z_]\w*)', code):
        names.add(m.group(1))
    # 局部变量 / 字段 / 形参声明：`Type name`（含 required/final/var 前缀）
    for m in re.finditer(
            r'\b(?:required\s+|final\s+|var\s+|const\s+|late\s+)*'
            r'(?:[A-Z]\w*(?:<[^(){};]*>)?|int|double|num|bool|String|dynamic|void)'
            r'\s+([a-z_]\w*)\b', code):
        names.add(m.group(1))
    # 增强枚举成员声明（花括号配对取出 enum 体，避免把成员当外部调用）
    for em in re.finditer(r'\benum\s+[A-Za-z_]\w*[^{]*\{', code):
        depth, i = 1, em.end()
        while i < len(code) and depth:
            if code[i] == '{':
                depth += 1
            elif code[i] == '}':
                depth -= 1
            i += 1
        for part in code[em.end():i - 1].split(','):
            pm = re.match(r'\s*([A-Za-z_]\w*)', part)
            if pm:
                names.add(pm.group(1))
    return names


# ── 检查 11：符号用到但没 import（ERROR，v3 新增）─────────────────────
# 背景（2026-10-03 fitcoach 实踩）：plateau_test.dart 用了 VolumeTrendPoint，
# 却只 import 了「同样用到它的」plateau_service.dart —— **Dart 的 import 不传递**，
# 被测文件 import 过的库不会带给调用方。宿主 flutter analyze 一次报 4 个 error，
# 而 C1 只判「import 的文件是否存在」，对「压根少写一条 import」完全无感。
def check_missing_imports(files, lib_dir, symbols, findings, pkg,
                          part_map, export_map):
    self_prefix = 'package:%s/' % pkg
    # 符号 -> 定义它的文件；**只保留唯一定义**的，同名多定义直接放弃以免误报。
    sym2files = {}
    for rel, names in symbols.items():
        for n in names:
            sym2files.setdefault(n, set()).add(rel)
    sym2file = {n: next(iter(fs)) for n, fs in sym2files.items() if len(fs) == 1}

    for fp in files:
        text = read(fp)
        # part 文件共享主库命名空间，无法独立判定其可见符号
        if re.search(r'^\s*part\s+of\s+', text, re.M):
            continue
        code = mask_strings_comments(text)
        imported = set()
        for m in re.finditer(r"^\s*import\s+'([^']+)'", text, re.M):
            spec = m.group(1)
            if spec.startswith(self_prefix):
                imported.add(os.path.normpath(spec[len(self_prefix):]).replace('\\', '/'))
        visible = _visible_files(imported, part_map, export_map)

        rel_self = None
        r = os.path.relpath(fp, lib_dir).replace('\\', '/')
        if not r.startswith('..'):
            rel_self = r
        if rel_self:
            visible |= _visible_files({rel_self}, part_map, export_map)

        local = _local_declared_names(text)
        reported = set()
        for m in re.finditer(r'\b([A-Za-z_]\w*)\b', code):
            name = m.group(1)
            if name in reported or name in local:
                continue
            # 前置字符（跳过空白）：`.` → 成员/枚举访问（CardioPhase.main、
            # StatsService.dateKey），走的是已 import 符号的成员，无需再 import
            j = m.start() - 1
            while j >= 0 and code[j] in ' \t\r\n':
                j -= 1
            prev = code[j] if j >= 0 else ''
            if prev == '.':
                continue
            # 后置字符（跳过空白）：`:` → 命名实参（recentPeakRpe: x / dateKey: d）
            # 例外：`a ? b : c` 三元里的 b 后面也跟 `:`，但前面是 `?`，不能误滤
            k = m.end()
            while k < len(code) and code[k] in ' \t\r\n':
                k += 1
            nxt = code[k] if k < len(code) else ''
            if nxt == ':' and code[k:k + 2] != '::' and prev != '?':
                continue
            defrel = sym2file.get(name)
            if not defrel or defrel in visible:
                continue
            reported.add(name)
            lineno = text.count('\n', 0, m.start()) + 1
            findings.append(('ERROR', 'C11', fp, lineno,
                             bi('符号 %s 定义在 %s，但本文件未 import 它（Dart import 不传递）'
                                % (name, defrel),
                                'symbol %s is defined in %s but this file does not import it '
                                '(Dart imports are not transitive)' % (name, defrel))))


# ── 检查 12：lint 6 命名 / 下划线（HINT，v3 新增）─────────────────────
# 2026-10-03 fitcoach 宿主 analyze 报的 3 条 info 全属此类，九板斧此前一条不查。
def check_lint_naming(files, findings):
    for fp in files:
        text = read(fp)
        code = mask_strings_comments(text)
        # 1) unnecessary_underscores：标识符里出现连续两个及以上下划线
        #    （未用参数要写 N 个单 `_`，不能写 `__`/`___`）
        seen = set()
        for m in re.finditer(r'\b([A-Za-z_]\w*)\b', code):
            name = m.group(1)
            if '__' not in name or name in seen:
                continue
            seen.add(name)
            lineno = text.count('\n', 0, m.start()) + 1
            findings.append(('HINT', 'C12', fp, lineno,
                             bi('标识符 %s 含连续下划线（lint6 unnecessary_underscores，'
                                '未用参数应写多个单 _）' % name,
                                'identifier %s has consecutive underscores '
                                '(lint6 unnecessary_underscores)' % name)))
        # 2) non_constant_identifier_names：顶层私有函数/变量写成 `_UpperCamel`
        #    ⚠️ 私有**类** `_Foo` 是合法的（类走 UpperCamelCase），必须排除。
        for i, raw in enumerate(text.split('\n')):
            line = raw.rstrip()
            if not line or line[0].isspace():
                continue
            if re.match(r'(?:abstract\s+|base\s+|final\s+|sealed\s+|interface\s+|mixin\s+)*'
                        r'(?:class|enum|mixin|typedef|extension)\s+_[A-Z]', line):
                continue
            m = re.match(r'(?:external\s+)?[A-Za-z_][\w<>,\s\[\]?]*?\s+(_[A-Z]\w*)\s*\(', line)
            if not m:
                m = re.match(r'(?:late\s+|final\s+|const\s+|var\s+)?[\w<>,\s\[\]?]*?\s*'
                             r'(_[A-Z]\w*)\s*=', line)
            if m:
                findings.append(('HINT', 'C12', fp, i + 1,
                                 bi('私有声明 %s 应为 lowerCamelCase（lint6 '
                                    'non_constant_identifier_names）' % m.group(1),
                                    'private declaration %s should be lowerCamelCase '
                                    '(lint6 non_constant_identifier_names)' % m.group(1))))


# ── 检查 14：ConsumerState ↔ ConsumerStatefulWidget 配对（ERROR，v4 新增）──
# 2026-10-03 fitcoach E9-a：State 侧为了用 ref.watch 改成 ConsumerState，
# widget 侧仍是 StatefulWidget → type_argument_not_matching_bounds。
# 危害被放大：一个 widget 编译失败 → 所有 import 它的测试文件一起
# 「Failed to load」（看着一堆错，实际一个根因），必须先抓出来。
# 判定只在本文件内配对（widget 与 State 通常同文件），跨文件不猜 → 零误报。
def check_consumer_state_pair(files, findings):
    w_re = re.compile(r'\bclass\s+(\w+)\s+extends\s+(ConsumerStatefulWidget|StatefulWidget)\b')
    s_re = re.compile(r'\bclass\s+(\w+)\s+extends\s+(ConsumerState|State)\s*<\s*(\w+)\s*>')
    for fp in files:
        text = read(fp)
        code = mask_strings_comments(text)
        widgets = {m.group(1): m.group(2).startswith('Consumer')
                   for m in w_re.finditer(code)}
        if not widgets:
            continue
        for m in s_re.finditer(code):
            base, target = m.group(2), m.group(3)
            if target not in widgets:
                continue                      # 跨文件 widget：不做猜测
            if base.startswith('Consumer') != widgets[target]:
                lineno = text.count('\n', 0, m.start()) + 1
                want = ('ConsumerStatefulWidget' if base.startswith('Consumer')
                        else 'StatefulWidget')
                findings.append(('ERROR', 'C14', fp, lineno,
                                 bi('%s extends %s<%s> → %s 必须 extends %s'
                                    '（两侧 Consumer 不一致 = '
                                    'type_argument_not_matching_bounds）'
                                    % (m.group(1), base, target, target, want),
                                    '%s extends %s<%s> → %s must extend %s '
                                    '(Consumer mismatch on the two sides = '
                                    'type_argument_not_matching_bounds)'
                                    % (m.group(1), base, target, target, want))))


# ── C15（2026-10-04 泛化版）· 成员存在性：机制是斧，符号是表 ─────────────
#
# 旧 C15 只认「DateTime + .date」一例（M-006），属于"发现一例硬编码一例"。
# 泛化后：
#   - **机制（斧）**：把「接收者 → 类型 → 成员集合」解析出来再比对；
#     **类型判定不了就跳过**，宁可漏也不误报。
#   - **数据（表）**：`DART_TYPE_MEMBERS`（dart:core 常用类型）+ 工程内类成员（动态扫描）。
# 以后遇到新的"某某类型上没有某某成员"，**往表里加一行即可，不必再写一把斧**。

# dart:core / dart:convert 常用类型的成员表（只列"容易出现笔误"的高频类型）
DART_TYPE_MEMBERS = {
    'DateTime': {
        'year', 'month', 'day', 'hour', 'minute', 'second', 'millisecond', 'microsecond',
        'millisecondsSinceEpoch', 'microsecondsSinceEpoch', 'weekday', 'timeZoneName',
        'timeZoneOffset', 'isUtc', 'add', 'subtract', 'difference', 'isAfter', 'isBefore',
        'isAtSameMomentAs', 'compareTo', 'toLocal', 'toUtc', 'toIso8601String',
    },
    'String': {
        'length', 'isEmpty', 'isNotEmpty', 'codeUnits', 'compareTo', 'contains', 'endsWith',
        'startsWith', 'indexOf', 'lastIndexOf', 'padLeft', 'padRight', 'replaceAll',
        'replaceFirst', 'replaceRange', 'replaceAllMapped', 'split', 'substring',
        'toLowerCase', 'toUpperCase', 'trim', 'trimLeft', 'trimRight', 'splitMapJoin',
        'codeUnitAt', 'allMatches', 'matchAsPrefix',
    },
    'Duration': {
        'inDays', 'inHours', 'inMinutes', 'inSeconds', 'inMilliseconds', 'inMicroseconds',
        'isNegative', 'abs', 'compareTo',
    },
    'num': {
        'isNaN', 'isNegative', 'isFinite', 'isInfinite', 'sign', 'abs', 'round', 'floor',
        'ceil', 'truncate', 'clamp', 'compareTo', 'remainder', 'toDouble', 'toInt',
        'toStringAsFixed', 'toStringAsPrecision', 'toStringAsExponential',
    },
    'int': {
        'isEven', 'isOdd', 'bitLength', 'gcd', 'modInverse', 'modPow', 'toRadixString',
    },
    'double': set(),
    'bool': set(),
    'Iterable': {
        'length', 'isEmpty', 'isNotEmpty', 'first', 'last', 'single', 'iterator', 'hashCode',
        'contains', 'elementAt', 'map', 'where', 'whereType', 'expand', 'fold', 'reduce',
        'forEach', 'every', 'any', 'join', 'take', 'skip', 'takeWhile', 'skipWhile',
        'toList', 'toSet', 'cast', 'firstWhere', 'lastWhere', 'singleWhere', 'followedBy',
    },
    'List': {
        'add', 'addAll', 'clear', 'remove', 'removeAt', 'removeLast', 'removeWhere',
        'retainWhere', 'indexOf', 'indexWhere', 'lastIndexWhere', 'insert', 'insertAll',
        'setAll', 'fillRange', 'replaceRange', 'getRange', 'setRange', 'removeRange',
        'sublist', 'asMap', 'sort', 'shuffle', 'reversed',
    },
    'Set': {
        'add', 'addAll', 'clear', 'remove', 'removeAll', 'removeWhere', 'retainAll',
        'retainWhere', 'contains', 'containsAll', 'lookup', 'union', 'intersection',
        'difference',
    },
    'Map': {
        # M-017：`Map` 此前漏了 `Iterable` 继承的 length/isEmpty/isNotEmpty
        # （DART_TYPE_PARENTS 里 Map 也没挂 Iterable）→ `_joint.isEmpty` 被误报成
        # undefined_getter。补成员比补继承链更省事且不影响其它判定。
        'length', 'isEmpty', 'isNotEmpty', 'keys', 'values', 'entries', 'containsKey',
        'containsValue', 'putIfAbsent', 'update', 'updateAll', 'remove', 'clear',
        'addAll', 'addEntries', 'removeWhere', 'map', 'forEach', 'cast',
    },
    'Future': {'then', 'catchError', 'whenComplete', 'timeout', 'asStream'},
    'Uri': {
        'scheme', 'host', 'port', 'path', 'query', 'queryParameters', 'queryParametersAll',
        'fragment', 'origin', 'userInfo', 'authority', 'hasScheme', 'hasAuthority',
        'hasPort', 'hasQuery', 'hasFragment', 'isAbsolute', 'isScheme', 'replace',
        'resolve', 'resolveUri', 'toFilePath', 'data', 'directory', 'file', 'http', 'https',
    },
    'RegExp': {
        'pattern', 'isCaseSensitive', 'isMultiLine', 'isDotAll', 'isUnicode', 'hasMatch',
        'firstMatch', 'allMatches', 'stringMatch',
    },
    'StringBuffer': {'write', 'writeAll', 'writeln', 'writeCharCode', 'clear'},
    'MapEntry': {'key', 'value'},
    'RegExpMatch': {'group', 'groupCount', 'start', 'end', 'pattern', 'input'},
}

# 类型继承（成员集合取并集）
DART_TYPE_PARENTS = {'int': 'num', 'double': 'num', 'List': 'Iterable', 'Set': 'Iterable'}

# 链式方法的返回类型（只登记**确定**的几条；查不到就整体跳过，不猜）
DART_CHAIN_RETURN = {
    ('DateTime', 'add'): 'DateTime', ('DateTime', 'subtract'): 'DateTime',
    ('DateTime', 'toLocal'): 'DateTime', ('DateTime', 'toUtc'): 'DateTime',
    ('Duration', 'abs'): 'Duration',
    ('String', 'toUpperCase'): 'String', ('String', 'toLowerCase'): 'String',
    ('String', 'trim'): 'String', ('String', 'trimLeft'): 'String',
    ('String', 'trimRight'): 'String', ('String', 'substring'): 'String',
    ('String', 'padLeft'): 'String', ('String', 'padRight'): 'String',
    ('String', 'replaceAll'): 'String', ('String', 'replaceFirst'): 'String',
    ('String', 'replaceRange'): 'String', ('String', 'replaceAllMapped'): 'String',
    ('List', 'toList'): 'List', ('Set', 'toList'): 'List', ('Iterable', 'toList'): 'List',
    ('List', 'toSet'): 'Set', ('Set', 'toSet'): 'Set', ('Iterable', 'toSet'): 'Set',
    ('Iterable', 'where'): 'Iterable', ('Iterable', 'map'): 'Iterable',
    ('Iterable', 'expand'): 'Iterable', ('Iterable', 'whereType'): 'Iterable',
    ('List', 'where'): 'Iterable', ('List', 'map'): 'Iterable',
    ('Iterable', 'reversed'): 'Iterable', ('List', 'reversed'): 'Iterable',
    ('Map', 'keys'): 'Iterable', ('Map', 'values'): 'Iterable', ('Map', 'entries'): 'Iterable',
    ('RegExp', 'firstMatch'): 'RegExpMatch', ('RegExp', 'allMatches'): 'Iterable',
    ('num', 'abs'): 'num', ('int', 'abs'): 'num', ('double', 'abs'): 'num',
    ('int', 'toDouble'): 'double', ('double', 'toInt'): 'int', ('num', 'toInt'): 'int',
}

# 任何类型都有的成员（Object）
SAFE_ANY_MEMBERS = {'toString', 'hashCode', 'runtimeType', 'noSuchMethod'}



# dart 类型的**静态**成员（DateTime.now() / List.filled() 这类；旧版把它们当实例成员查 → 误报）
DART_STATIC_MEMBERS = {
    'DateTime': {'now', 'parse', 'tryParse', 'fromMillisecondsSinceEpoch',
                 'fromMicrosecondsSinceEpoch', 'utc'},
    'Duration': set(),
    'String': {'fromCharCodes', 'fromEnvironment'},
    'int': {'parse', 'tryParse'},
    'double': {'parse', 'tryParse'},
    'num': {'parse', 'tryParse'},
    'List': {'filled', 'generate', 'empty', 'of', 'from', 'unmodifiable', 'castFrom',
             'copyRange'},
    'Set': {'from', 'of', 'identity', 'unmodifiable', 'castFrom'},
    'Map': {'from', 'of', 'fromEntries', 'identity', 'unmodifiable', 'castFrom', 'fromIterables'},
    'Iterable': {'empty', 'generate', 'castFrom'},
    'Future': {'wait', 'any', 'forEach', 'doWhile', 'sync', 'value', 'error', 'delayed',
               'microtask'},
    'Uri': {'parse', 'tryParse', 'http', 'https', 'file', 'directory', 'data'},
    'RegExp': set(),
    'StringBuffer': set(),
    'MapEntry': set(),
}


def _dart_members(t, with_static=False):
    """dart 类型的成员集合（含父类型）。不在表里 → None（不可判定，调用方跳过）。"""
    if t not in DART_TYPE_MEMBERS:
        return None
    out = set(DART_TYPE_MEMBERS[t]) | SAFE_ANY_MEMBERS
    if with_static:
        out |= DART_STATIC_MEMBERS.get(t, set())
    p = DART_TYPE_PARENTS.get(t)
    while p:
        out |= DART_TYPE_MEMBERS.get(p, set())
        if with_static:
            out |= DART_STATIC_MEMBERS.get(p, set())
        p = DART_TYPE_PARENTS.get(p)
    return out


def _iter_type_blocks(code):
    """产出 (kind, name, extra, body)，kind ∈ {class, mixin, extension}。"""
    pat = re.compile(r'\b(?:abstract\s+|base\s+|final\s+|sealed\s+|interface\s+|mixin\s+)*'
                     r'(class|mixin|extension)(?:\s+(\w+))?([^{]*)\{')
    for m in pat.finditer(code):
        start, depth, i, n = m.end(), 1, m.end(), len(code)
        while i < n and depth:
            c = code[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        yield m.group(1), (m.group(2) or ''), m.group(3), code[start:i - 1]


def _body_members(body):
    """收集类体里的成员名。**宁可多收**（多收 = 少报，不会误报）。"""
    out = set()
    for raw in body.split('\n'):
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        # 方法 / 构造函数：`... name(`
        m = re.match(r'(?:@\w+(?:\([^()]*\))?\s+)*(?:external\s+|static\s+|final\s+|late\s+|'
                     r'const\s+|covariant\s+|override\s+|factory\s+)*'
                     r'[\w<>?,\s\[\]{}]*?\s+(\w+)\s*\(', line)
        if m:
            out.add(m.group(1))
            continue
        # 字段：`... name = ...;` / `... name;`
        m = re.match(r'(?:@\w+(?:\([^()]*\))?\s+)*(?:static\s+|final\s+|late\s+|const\s+|'
                     r'covariant\s+)*[\w<>?,\s\[\]{}]+?\s+(\w+)\s*(?:=|;|,)', line)
        if m:
            out.add(m.group(1))
        m = re.search(r'\b(?:static\s+)?(?:get|set)\s+(\w+)', line)
        if m:
            out.add(m.group(1))
        out.update(re.findall(r'this\.(\w+)', line))
    return out


def _supers_of(extra):
    """解析 extends / with / implements 的类型名（先剥泛型）。"""
    flat = re.sub(r'<[^<>]*>', ' ', extra)
    out = []
    for m in re.finditer(r'\b(?:extends|with|implements)\s+([^{]+)', flat):
        out += re.findall(r'[A-Za-z_]\w*', m.group(1))
    return out


def _collect_project_types(files):
    """扫工程内 class / mixin / extension，得 {类型名: {members, supers, opaque}}。"""
    types = {}
    ext_on = {}
    for fp in files:
        code = mask_strings_comments(read(fp))
        for kind, name, extra, body in _iter_type_blocks(code):
            if kind == 'extension':
                m = re.search(r'\bon\s+([A-Za-z_]\w*)', extra)
                ext_on.setdefault(m.group(1) if m else '', set()).update(_body_members(body))
                continue
            types[name] = {'members': _body_members(body), 'supers': _supers_of(extra)}
    # extension 成员并入目标类型
    for target, members in ext_on.items():
        if target in types:
            types[target]['members'] |= members
        elif target in DART_TYPE_MEMBERS:
            DART_TYPE_MEMBERS[target] |= members
    # opaque：继承链里有工程外类型（框架 / SDK）→ 成员集合不完整，不查
    for name, info in types.items():
        info['opaque'] = any(s not in types for s in info['supers'])
    return types


def _project_members(types, name, memo, stack=()):
    """工程类型的成员集合（含工程内继承链）；不可判定（opaque / 找不到）→ None。"""
    if name in memo:
        return memo[name]
    if name not in types or name in stack:
        return None
    info = types[name]
    if info['opaque']:
        memo[name] = None
        return None
    out = set(info['members'])
    for s in info['supers']:
        sub = _project_members(types, s, memo, stack + (name,))
        if sub is None:
            memo[name] = None
            return None
        out |= sub
    memo[name] = out | SAFE_ANY_MEMBERS
    return memo[name]


def _infer_type(rhs):
    """从 `= <rhs>` 右侧推断类型；推断不了 → None。"""
    r = rhs.strip()
    r = re.sub(r'^(?:const|new|await)\s+', '', r)
    if r.startswith('DateTime'):
        return 'DateTime'
    if r[:1] in ('"', "'"):
        return 'String'
    if re.match(r'^-?\d+$', r):
        return 'int'
    if re.match(r'^-?\d+\.\d+$', r):
        return 'double'
    if r in ('true', 'false'):
        return 'bool'
    if r.startswith('[') or re.match(r'^<[^>]*>\s*\[', r):
        return 'List'
    # 只有**大写开头**才是构造调用（`Foo()`）；`obj.method()` 不能当成构造。
    # 构造后若还有链式调用（`RegExp(...).firstMatch(x)`），按返回类型继续推进。
    m = re.match(r'^([A-Z]\w*)\s*\((?:[^()]|\([^()]*\))*\)', r)
    if m:
        t = m.group(1)
        for cm in re.finditer(r'\.\s*(\w+)\s*\((?:[^()]|\([^()]*\))*\)', r[m.end():]):
            nt = DART_CHAIN_RETURN.get((t, cm.group(1)))
            if nt is None:
                return None
            t = nt
        return t
    return None


def _brace_events(code):
    """[(pos, depth_before, depth_after, is_open)]，用于按**作用域**判定变量可见性。"""
    events = []
    depth = 0
    for m in re.finditer(r'[{}]', code):
        if m.group(0) == '{':
            events.append((m.start(), depth, depth + 1, True))
            depth += 1
        else:
            depth -= 1
            events.append((m.start(), depth + 1, depth, False))
    return events


def _depth_at(events, pos):
    d = 0
    for p, _, after, _ in events:
        if p >= pos:
            break
        d = after
    return d


def _scope_end(events, decl_pos, decl_depth):
    """声明所在作用域的结束位置（第一个让它"出作用域"的 `}`）。"""
    for p, _, after, is_open in events:
        if is_open or p <= decl_pos:
            continue
        if after < decl_depth:
            return p
    return None


def check_member_exists(files, findings):
    """C15 · 成员存在性（undefined_getter）：类型可判定时，成员必须在成员集合里。

    泛化要点（2026-10-04）：本斧只提供**机制**，
    具体类型/成员写在 `DART_TYPE_MEMBERS` / `DART_STATIC_MEMBERS` 与工程类扫描里。
    **类型判定不了就跳过** —— 零误报优先于覆盖率（这是九板斧的一贯取舍）。
    """
    types = _collect_project_types(files)
    memo = {}
    arg = r'\([^()]*(?:\([^()]*\)[^()]*)*\)'
    # 变量声明 / 推断：`Type x = ...` 或 `final x = <expr>;`
    # ⚠️ **形参不算**：同名标识符跨函数可能是不同类型（实测误报过）。
    decl_re = re.compile(r'\b(?:final\s+|late\s+|const\s+|var\s+)*'
                         r'([A-Z]\w*)\s*(?:<[^<>]*>)?\s*\??\s+(\w+)\s*=')
    infer_re = re.compile(r'\b(?:final|var|late)\s+(?:final\s+)?(\w+)\s*=\s*([^;{]+?)\s*;')
    # 访问式：root(.method(arg))* .member
    access_re = re.compile(
        r'(?<![\w.])(DateTime\s*%(a)s|DateTime\.\w+\s*%(a)s|(?!(?:if|for|while|switch|catch|'
        r'return|new|const|final|var|late|else|super|this|await|case)\b)[A-Za-z_]\w*)'
        r'((?:\s*\??\.\s*\w+\s*%(a)s)*)\s*\??\.\s*(\w+)\b' % {'a': arg})

    for fp in files:
        text = read(fp)
        code = mask_strings_comments(text)
        events = _brace_events(code)
        decls = []                      # [(pos, depth, name, type)]
        for m in decl_re.finditer(code):
            decls.append((m.start(), _depth_at(events, m.start()), m.group(2), m.group(1)))
        # 推断用**未遮蔽**的原文：字符串字面量被遮蔽成空格后就认不出 String 了
        for m in infer_re.finditer(text):
            t = _infer_type(m.group(2))
            if t:
                decls.append((m.start(), _depth_at(events, m.start()), m.group(1), t))
        if not decls:
            continue

        for m in access_re.finditer(code):
            root, chain, member = m.group(1), m.group(2), m.group(3)
            if root.startswith('DateTime'):
                t = 'DateTime'
                static_like = True
            else:
                # 只在**可见作用域**内找同名声明（取最近的一条），避免跨函数同名误判
                pos, depth = m.start(), _depth_at(events, m.start())
                cand = None
                for dpos, ddepth, dname, dtype in decls:
                    if dname != root or dpos >= pos or ddepth > depth:
                        continue
                    end = _scope_end(events, dpos, ddepth)
                    if end is not None and end < pos:
                        continue
                    if cand is None or dpos > cand[0]:
                        cand = (dpos, dtype)
                if cand is None:
                    continue            # 类型判定不了 → 跳过（零误报优先）
                t = cand[1]
                static_like = False
            # 链式推进：任一段返回类型未知 → 整体跳过
            for cm in re.finditer(r'\.\s*(\w+)\s*\(', chain):
                nt = DART_CHAIN_RETURN.get((t, cm.group(1)))
                if nt is None:
                    t = None
                    break
                t = nt
            if not t:
                continue

            members = _dart_members(t, with_static=static_like)
            if members is None:
                members = _project_members(types, t, memo)
                if members is None:
                    continue            # 工程类型不可判定 → 跳过
            if member in members or member in SAFE_ANY_MEMBERS:
                continue
            lineno = text.count('\n', 0, m.start()) + 1
            recv = (root + chain).strip()
            findings.append(('ERROR', 'C15', fp, lineno,
                             bi('类型 %s 上没有成员 `%s`（undefined_getter 编译硬错），'
                                '疑似笔误：`%s.%s`。'
                                '（成员表见 check.py DART_TYPE_MEMBERS / 工程类扫描；'
                                '新增个例请往表里加，不要再写一把斧）'
                                % (t, member, recv, member),
                                'type %s has no member `%s` (undefined_getter); suspect typo '
                                '`%s.%s`' % (t, member, recv, member))))


# ── C26（2026-10-06 新增）· 工程类型**形参**的成员存在性 ───────────────────
#
# 起因（M-023，代价 = 一整轮宿主复验）：#75（F24）把 `UserProfile.jointDiscomfort`
# 当成「已存在的档案字段」写进代码 —— 实际那处是 **`TrainingSession.jointDiscomfort`**
# （#55 的单次训前状态），`UserProfile` 从来没这个字段 → 6 条 `undefined_getter`
# + 整片 `widget_test` Failed to load（`+714 -2`）。
#
# C15 当时**一条都没报**，原因写在它自己的 `decl_re` 注释里：
#   「形参不算 —— 同名标识符跨函数可能是不同类型（实测误报过）」。
# 这条取舍本身没错（零误报优先），但代价是**最常见的一类错**完全没人管：
# `void f(UserProfile p) { ... p.xxx ... }` —— 形参类型是最明确的类型信息，
# 反而被跳过了。**跨类张冠李戴**（同名不同类）恰恰只可能在这里被抓到。
#
# C26 = 把形参纳入，但用**函数体作用域**把误报风险关住：
#   ① 只认「签名后紧跟 `{` / `=>`」的括号（调用点后面是 `;`，天然被排除；
#      `if` / `while` / `catch` 等由关键字表排除）；
#   ② 成员访问**只在该函数体 span 内**校验 → 跨函数同名不再误判；
#   ③ 形参在函数体内被局部变量遮蔽 → **整条跳过**（宁可不报，不误报）；
#   ④ 类型仍是「工程内声明 + 成员集合封闭」（复用 `_project_members`，
#      `implements` 外部接口的类 = opaque → 跳过）。
#
_BODY_PARAM_KW = {'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'catch',
                  'try', 'on', 'return', 'new', 'const', 'final', 'late', 'var',
                  'assert', 'sync', 'async', 'await', 'is'}


def _split_params(src):
    """按顶层逗号切形参表（跳过 `()` / `[]` / `{}` 里的逗号，如默认值）。"""
    out, depth, cur = [], 0, ''
    for c in src:
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        if c == ',' and depth == 0:
            out.append(cur)
            cur = ''
        else:
            cur += c
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def _param_blocks(code):
    """[(body_start, body_end, params_src)] —— 只收**签名后紧跟函数体**的形参表。

    ⚠️ 带初始化列表（`: super(...)`）的构造签名**整条跳过**：初始化列表里可能
    出现 `{`（如 Map 字面量），会把「body 起点」认错 → 宁可不查。
    """
    out = []
    for m in re.finditer(r'\(', code):
        i = m.start()
        head = code[max(0, i - 80):i]
        pm = re.search(r'([A-Za-z_]\w*)\s*(?:<[^<>]*>)?\s*$', head)
        if not pm or pm.group(1) in _BODY_PARAM_KW:
            continue
        j = _match_paren(code, i)
        if j < 0:
            continue
        k, ch = _next_char(code, j + 1)
        if ch != '{' and code[k:k + 2] != '=>':
            continue
        if ch == '{':
            bstart, depth, e = k + 1, 1, k + 1
            while e < len(code):
                if code[e] == '{':
                    depth += 1
                elif code[e] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                e += 1
            bend = e
        else:
            bstart = k + 2
            bend = _stmt_terminator(code, bstart)
            if bend < 0:
                bend = len(code)
        out.append((bstart, bend, code[i + 1:j]))
    return out


_PARAM_DECL_RE = re.compile(r'^([A-Z]\w*)\s*(?:<[^<>]*>)?\s*\??\s+(\w+)$')


def check_param_member_exists(files, findings):
    """C26 · 工程类型形参的成员存在性（undefined_getter 的**跨类张冠李戴**）。

    与 C15 的分工：C15 查**局部变量 / 推断类型**，C26 查**形参**；
    两者都用 `_project_members` 判成员集合，判不了就跳过（零误报优先）。
    """
    types = _collect_project_types(files)
    memo = {}
    for fp in files:
        text = read(fp)
        code = mask_strings_comments(text)
        for bstart, bend, params_src in _param_blocks(code):
            body = code[bstart:bend]
            typed = []
            for raw in _split_params(params_src):
                p = re.sub(r'^(?:required\s+|covariant\s+)+', '', raw)
                p = p.split('=')[0].strip()          # 去掉默认值
                if 'this.' in p or 'super.' in p:
                    continue
                m = _PARAM_DECL_RE.match(p)
                if not m or m.group(1) not in types:
                    continue                          # 非工程类型（框架 / SDK）→ 不查
                members = _project_members(types, m.group(1), memo)
                if members is None:
                    continue                          # 成员集合不封闭（opaque）→ 不查
                typed.append((m.group(2), m.group(1), members))
            for name, t, members in typed:
                # ③ 被局部变量遮蔽 → 整条跳过
                if re.search(r'\b(?:final|var|late|const)\s+%s\s*=' % re.escape(name),
                             body):
                    continue
                if re.search(r'\b[A-Z]\w*\s+%s\s*=' % re.escape(name), body):
                    continue
                for am in re.finditer(r'(?<![\w.])%s\s*\??\.\s*(\w+)' % re.escape(name),
                                      body):
                    member = am.group(1)
                    if member in members:
                        continue
                    lineno = text.count('\n', 0, bstart + am.start()) + 1
                    findings.append(('ERROR', 'C26', fp, lineno,
                                     bi('形参 `%s: %s` 上访问了 `%s`，但类型 %s **没有这个成员**'
                                        '（undefined_getter 编译硬错）。'
                                        '⚠️ 高频真因 = **跨类张冠李戴**：同名成员其实在**另一个类**上'
                                        '（如 `TrainingSession.jointDiscomfort` 被当成 '
                                        '`UserProfile.jointDiscomfort`）→ 用字段前先 '
                                        '`grep -n "class X"` 确认它在**那个类的花括号里**。'
                                        % (name, t, member, t),
                                        'param `%s: %s` has no member `%s` '
                                        '(undefined_getter) — often a same-named member '
                                        'borrowed from another class' % (name, t, member))))


# ── C16（2026-10-04 新增）· lint 规则表（表驱动）─────────────────────────
#
# 与 C12 的分工：C12 是**工程特有**的两条（连续下划线 / 私有命名）；
# C16 放**通用 lint 规则**，每条规则是表里的一项 —— 新增 lint 只需加一项，
# 不必再"发现一例补一斧"。
#
# 首批：`prefer_initializing_formals`
#   （2026-10-04 宿主 `flutter analyze` 报 `lib/widgets/adaptive.dart:33`，
#    九板斧当时没抓到，只能手工修 —— 正是"缺一张 lint 表"的直接代价。）

LINT_RULES = {
    # 规则名 → (开关, 说明)
    'prefer_initializing_formals': (
        True,
        '构造器参数只为赋给同名/异名字段时，应改用初始化形参 `this.x`'),
    'unnecessary_this': (
        False,
        '（暂不开：`this.` 在工程里有可读性用途，开了噪音大于收益）'),
}

# ── 第三方 API 废弃 / 迁移名单（C17 表驱动）─────────────────────────────
# 由来（2026-10-04 宿主 `flutter analyze` 报 `lib/providers/providers.dart:216
# Method not found: 'StateProvider'`）：**major 升级后第三方符号被挪走或删掉**，
# 这类错 C11「符号用到没 import」抓不到 —— 它比对的是**工程内声明**的符号，
# 第三方包挪走导出后，符号既不在工程内、也不在 import 列表里，形成盲区。
#
# 每条 = (标识符, 豁免 import 片段, 中文提示, 英文提示)
#   - 豁免 import 非空：文件 import 了该库 → 放行（说明开发者是显式引 legacy）
#   - 豁免 import 为空：无论怎么 import 都报（API 已被整个移除）
# 匹配在 `mask_strings_comments` 之后进行 → 注释 / 字符串里提及不算数。
DEPRECATED_API_RULES = [
    ('StateProvider', 'flutter_riverpod/legacy.dart',
     'Riverpod 3 起 StateProvider 已移入 package:flutter_riverpod/legacy.dart，'
     '主入口不再导出（直接用会 Method not found）；改用 NotifierProvider + Notifier',
     'Since Riverpod 3, StateProvider moved to package:flutter_riverpod/legacy.dart; '
     'use NotifierProvider + Notifier instead'),
    ('StateProviderFamily', 'flutter_riverpod/legacy.dart',
     'Riverpod 3 起 StateProviderFamily 已移入 legacy，改用 NotifierProvider.family',
     'Since Riverpod 3, StateProviderFamily moved to legacy; use NotifierProvider.family'),
    ('StateNotifier', 'flutter_riverpod/legacy.dart',
     'Riverpod 3 起 StateNotifier 已移入 legacy，改用 Notifier',
     'Since Riverpod 3, StateNotifier moved to legacy; use Notifier'),
    ('StateController', 'flutter_riverpod/legacy.dart',
     'Riverpod 3 起 StateController 已移入 legacy，改用 Notifier 的 state',
     'Since Riverpod 3, StateController moved to legacy; use Notifier.state'),
    ('StateNotifierProvider', 'flutter_riverpod/legacy.dart',
     'Riverpod 3 起 StateNotifierProvider 已移入 legacy，改用 NotifierProvider',
     'Since Riverpod 3, StateNotifierProvider moved to legacy; use NotifierProvider'),
    ('StateNotifierProviderFamily', 'flutter_riverpod/legacy.dart',
     'Riverpod 3 起 StateNotifierProviderFamily 已移入 legacy，改用 NotifierProvider.family',
     'Since Riverpod 3, StateNotifierProviderFamily moved to legacy; '
     'use NotifierProvider.family'),
    ('ChangeNotifierProvider', '',
     'Riverpod 3 已**移除** ChangeNotifierProvider（legacy 也不再导出），'
     '改用 NotifierProvider + Notifier',
     'ChangeNotifierProvider was removed in Riverpod 3 (not even in legacy); '
     'use NotifierProvider + Notifier'),
]

_CTOR_RE_TMPL = r'\b(?:const\s+|factory\s+)?%s\s*\(([^()]*)\)\s*(?::\s*([^{;]+?))?\s*(?:\{|=>|;)'


def check_lint_table(files, findings):
    """C16 · 表驱动 lint 规则（见 LINT_RULES）。"""
    if not LINT_RULES.get('prefer_initializing_formals', (False, ''))[0]:
        return
    for fp in files:
        text = read(fp)
        code = mask_strings_comments(text)
        for kind, name, extra, body in _iter_type_blocks(code):
            if kind == 'extension' or not name:
                continue
            for cm in re.finditer(_CTOR_RE_TMPL % re.escape(name), body):
                params_txt, init_txt = cm.group(1), cm.group(2) or ''
                if not init_txt or '=' not in init_txt:
                    continue
                # 参数名：每段取最后一个标识符
                params = set()
                for seg in params_txt.split(','):
                    # 剥掉可选/命名参数的 `{` `}`（`{required int b}` → `required int b`）
                    seg = seg.strip().strip('{}[]').strip()
                    ids = re.findall(r'([A-Za-z_]\w*)\s*$', seg)
                    if ids:
                        params.add(ids[-1])
                if not params:
                    continue
                # 右侧必须**就是**参数名（后面直接是 `,` 或结尾），
                # 否则 `x = y + 1` 这种真初始化会被误报
                for am in re.finditer(r'([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*(?=,|$)',
                                      init_txt):
                    field, value = am.group(1), am.group(2)
                    if field == value or value not in params:
                        continue
                    # 已经在用初始化形参（`this.x`）的不再报
                    if re.search(r'\bthis\.%s\b' % re.escape(field), params_txt):
                        continue
                    lineno = text.count('\n', 0, code.find(body) + cm.start()) + 1
                    findings.append(('HINT', 'C16', fp, lineno,
                                     bi('%s.%s · lint prefer_initializing_formals：'
                                        '构造器里 `%s = %s` 可用初始化形参 `this.%s` 代替'
                                        '（需保证字段名与形参写法一致）'
                                        % (name, field, field, value, field),
                                        '%s.%s: lint prefer_initializing_formals — '
                                        'use an initializing formal `this.%s` instead of '
                                        '`%s = %s`' % (name, field, field, field, value))))


def check_deprecated_api(files, findings):
    """C17 · 第三方 API 废弃/迁移名单（表驱动，见 DEPRECATED_API_RULES）。

    为什么需要这一斧：major 升级后**第三方符号被挪走或删掉**时，
    C11（符号用到没 import）抓不到 —— 它比对的是工程内声明的符号，
    而这类符号既不在工程内、也不在 import 列表里。宿主 `flutter analyze`
    会报 `Method not found` / `undefined_function`，沙箱里此前只能靠人眼。
    """
    for fp in files:
        text = read(fp)
        code = mask_strings_comments(text)
        # 只看本文件的 import 行（含 as/show 前缀部分）
        imports = '\n'.join(re.findall(r"""^\s*import\s+['"]([^'"]+)['"]""",
                                       text, re.M))
        for ident, escape_import, zh, en in DEPRECATED_API_RULES:
            if escape_import and escape_import in imports:
                continue
            hit = re.search(r'\b%s\b' % re.escape(ident), code)
            if not hit:
                continue
            lineno = text.count('\n', 0, hit.start()) + 1
            # 每个标识符每文件只报一次（同一处用法重复出现没必要刷屏）
            findings.append(('ERROR', 'C17', fp, lineno,
                             bi('第三方 API 已废弃/迁移：`%s` —— %s'
                                % (ident, zh),
                                'Deprecated/moved third-party API: `%s` — %s'
                                % (ident, en))))


# ── C18（2026-10-05 新增）· 局部标识符不得以下划线开头 ──────────────────
#
# 由来（宿主 `flutter analyze` 报 test/data/custom_exercise_test.dart:16:12
# no_leading_underscores_for_local_identifiers）：测试 helper 写成
# `Exercise _custom({...})` —— 它是写在 main() 里的**局部函数**。
#
# 与 C12 的分工（易混，写死在这里）：
#   - C12 管**顶层/类成员私有**命名 —— `_foo` 合法，但必须 lowerCamelCase；
#   - C18 管**函数体内**的声明 —— Dart 里局部标识符带 `_` 反而非法。
#   ⚠️ 两条方向相反，所以 C18 必须先把「类体」排除干净，否则会跟 C12 打架。
#
# 零误报设计：
#   1. 花括号栈区分「类体 / 函数体」→ 类成员 `final _x = ...`、顶层 `void _foo()`
#      一律放行；只有某个 `{}` 内部（函数体 / 局部块）的声明才判定；
#   2. 只认**声明**形态，且必须有「类型」或「var/final/const/late」修饰之一 ——
#      否则 `_strength('s1', ...)` 这类**调用**长得跟 `Type _name(` 一模一样，
#      （2026-10-05 首版漏了这一条 → 236 条全是误报，仅 1 条为真）；
#      再用关键字黑名单挡掉 `return _foo(` / `await _foo(` 这类语句。
_LOCAL_DECL_RE = re.compile(
    r'^[ \t]*((?:late\s+|final\s+|const\s+|var\s+|static\s+)*)'
    r'([A-Za-z_][\w<>,\s\[\]?!]*?\s+)?(_[a-z]\w*)\s*(?=\(|=[^=])')
#   3. 形参名 `_x` 不报（形参不在此 lint 范围）—— 声明形态要求行首附近是类型。
# 挡掉「语句里的下划线标识符」：`return _x(` / `throw _e;` 等
_LOCAL_DECL_STOPWORDS = frozenset(
    'return if else for while do switch case try catch finally throw await yield '
    'new print expect assert rethrow break continue'.split())


def _scope_events(code):
    """[(pos, kind)] —— 每个 `{` 的位置与类别。

    kind: 'class' = 类 / 枚举 / mixin / extension 的**声明体**；
          'body'  = 函数体或局部块；'pop' = 对应的 `}`。
    用它把「类成员」（`_` 合法）与「局部声明」（`_` 非法）区分开。
    """
    events = []
    pending = False
    for m in re.finditer(r'\{|\}|;|\b(?:class|enum|mixin|extension)\b', code):
        tok = m.group(0)
        if tok == '{':
            events.append((m.start(), 'class' if pending else 'body'))
            pending = False
        elif tok == '}':
            events.append((m.start(), 'pop'))
        elif tok == ';':
            pending = False
        else:
            pending = True
    return events


def check_local_underscore(files, findings):
    """C18 · 局部标识符不得以下划线开头（no_leading_underscores_for_local_identifiers）。"""
    for fp in files:
        text = read(fp)
        code = mask_strings_comments(text)
        events = _scope_events(code)
        stack = []
        ev = 0
        off = 0
        for i, raw in enumerate(text.split('\n')):
            line_start = off
            off += len(raw) + 1
            # 重放花括号栈到本行起点（events 已按位置有序）
            while ev < len(events) and events[ev][0] < line_start:
                kind = events[ev][1]
                if kind == 'pop':
                    if stack:
                        stack.pop()
                else:
                    stack.append(kind)
                ev += 1
            if not stack or stack[-1] != 'body':
                continue
            m = _LOCAL_DECL_RE.match(raw)
            if not m:
                continue
            prefix, type_name, name = m.group(1), m.group(2), m.group(3)
            # 无修饰也无类型 → 是**调用**而非声明（`_strength('s1', ...)`），不报
            if not (prefix or type_name):
                continue
            # 类型段里出现语句关键字 → 是**语句**而非声明。
            # ⚠️ 必须查**每一个** token：首版只查最后一个，`return split ? _buildSplit(...)`
            #    里的 `split ?` 会被当成类型、把方法调用误报成声明（2026-10-05 实踩）。
            if type_name and _LOCAL_DECL_STOPWORDS.intersection(type_name.split()):
                continue
            findings.append(('HINT', 'C18', fp, i + 1,
                             bi('局部标识符 %s 不应以下划线开头'
                                '（lint no_leading_underscores_for_local_identifiers；'
                                '只有顶层/类成员的私有名才用 `_` 前缀）' % name,
                                'local identifier %s should not start with an underscore '
                                '(lint no_leading_underscores_for_local_identifiers)'
                                % name)))


# ── C19（2026-10-05 新增）· final 字段必须在构造函数里初始化 ────────────
#
# 由来（宿主 `flutter test` 报 lib/data/models.dart:236
# `Error: Final field 'isTimed' is not initialized`）：给 `Exercise` 加了
# `final bool isTimed;` 却漏了构造函数里的 `this.isTimed = false`
# —— 一处漏改，**39 个测试文件集体 Failed to load**（它们都要编译 models.dart）。
#
# ⚠️ 为什么必须补：**加字段是最高频的改动**，而「五处都要带」（字段声明 / 构造 /
# `toJson` / `fromJson` / copy 系列）里**只有这一处是编译期硬错**，其余四处都是
# 静默丢数据。沙箱没有分析器，这类错误只能靠文本体检兜住。
#
# 零误报设计（漏报可以接受，误报不行）：
#   1. 只管 `class` / `enum` / `mixin`（Dart 对类与枚举都要求 final 字段初始化）；
#   2. 字段必须带 `final`、声明处**无初值**、且**不带 late**（late 允许延后赋值）；
#   3. **只认类体第一层** —— 函数体内的 `final int x;` 是局部变量，不是字段，
#      用花括号深度 == 0 过滤（否则满屏误报）；
#   4. 只要类体文本里出现过 `this.<name>`（构造参数）或 `super.<name>` 或
#      `<name> =`（初始化列表）就放行 —— 多构造函数场景只查到其中一个也算过，
#      宁可漏报也不误报；
#   5. 类里**没有任何生成构造函数**（只有 `factory` / 纯静态类）→ 整类跳过。
# ⚠️ 必须 re.M：`^` 要匹配**每行**行首（首版漏了它 → 一个类都扫不到，
#    反向验证直接 0 命中；改完必须重跑「先造错再还原」两步验证）。
_CLASS_DECL_RE = re.compile(r'^[ \t]*(?:abstract\s+)?(?:class|enum|mixin)\s+(\w+)',
                            re.M)
# 声明处无初值：`final bool isTimed;` / `final List<String> steps;`
_FINAL_FIELD_RE = re.compile(
    r'(?:^|\n)[ \t]*(?:static\s+)?final\s+(?:covariant\s+)?[\w<>,\[\]?!\s]*?\s+(_?\w+)\s*;')


def _class_spans(code):
    """[(class_name, body_start, body_end)] —— 类 / 枚举 / mixin 的**类体**范围。"""
    spans = []
    for m in _CLASS_DECL_RE.finditer(code):
        i = code.find('{', m.end())
        if i < 0:
            continue
        depth, j = 0, i
        while j < len(code):
            c = code[j]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        spans.append((m.group(1), i + 1, j))
    return spans


def check_final_field_init(files, findings):
    """C19 · final 字段必须在构造函数里初始化（Final field 'X' is not initialized）。"""
    for fp in files:
        text = read(fp)
        code = mask_strings_comments(text)
        for cname, s, e in _class_spans(code):
            body = code[s:e]
            if not re.search(r'(?:^|\n)\s*(?:const\s+)?%s(?:\.\w+)?\s*\(' % re.escape(cname),
                             body):
                continue  # 没有生成构造函数（只有 factory / 静态类）→ 跳过，避免误报
            for m in _FINAL_FIELD_RE.finditer(body):
                name = m.group(1)
                pos = m.start() + 1 if m.group(0).startswith('\n') else m.start()
                # 只认类体第一层：深度 > 0 说明在函数体 / 局部块里（局部变量，不是字段）
                if body[:pos].count('{') - body[:pos].count('}') != 0:
                    continue
                if re.search(r'\bthis\.%s\b' % re.escape(name), body):
                    continue
                if re.search(r'\bsuper\.%s\b' % re.escape(name), body):
                    continue
                if re.search(r'(?<![\w.])%s\s*=' % re.escape(name), body):
                    continue  # 初始化列表 `X(...) : name = ...`
                ln = code[:s + pos].count('\n') + 1
                findings.append(('ERROR', 'C19', fp, ln,
                                 bi('final 字段 %s 未在构造函数里初始化'
                                    '（加字段时最容易漏掉 `this.%s`；'
                                    '宿主会报 Final field \'%s\' is not initialized）'
                                    % (name, name, name),
                                    'final field %s is not initialized in any constructor '
                                    '(adding a field commonly misses `this.%s`)' % (name, name))))


# ── C20（2026-10-05 新增）· 控制流语句跨行却没包块 ────────────────────
#
# 由来（宿主 `flutter analyze` 报 lib/services/recovery_service.dart:77
# info `curly_braces_in_flow_control_structures`）：长条件换行后顺手写成
#     if (!a.contains(m) &&
#         !b.contains(m)) continue;
# —— then 语句与 `if` **不在同一行**，Dart lint 要求包块。
# ⚠️ 关键区分：同一行的 `if (x) return;`（全库既有风格 **380 处**）lint **不报**，
# 只报跨行 —— 本斧只管跨行，否则满屏误报。
#
# 零误报设计（漏报可以接受，误报不行）：
#   1. 只认行首的 if / else if / for / while，以及不带括号的 else；
#   2. 括号计数找配对 `)`（字符串与注释已 mask 成空格，括号计数安全）；
#   3. `)` 后第一个非空字符是 `{`（含换行写的 Allman 风格）或 `;`（空语句）→ 放行；
#   4. then 语句与 **`if` 关键字在同一行** → 放行（lint 不报）。
#      ⚠️ 判据是「与 `if` 同行」，**不是**「与 `)` 同行」：
#      `if (a &&\n    b) continue;` 里 `continue` 与 `)` 同行、但与 `if` 跨行，
#      lint **照样报**（宿主实报 recovery_service.dart:77:55，首版按 `)` 判 → 漏报）；
#   5. ⚠️ **终止符必须是 `;`** —— 以 `,` 结尾的是**集合字面量里的 if 元素**
#      （`children: [if (x) const A(),]`，Flutter 里极常见），它不是语句、
#      lint 也不报 → 放行（这一条不加会满屏误报）；
#   6. `do {} while (x);` 的 while 在行尾且 then 是 `;` → 命中第 3 条放行。
_FLOW_HEAD_RE = re.compile(r'(?:^|\n)[ \t]*(?:\}\s*)?(?:else\s+)?(?:if|for|while)\s*\(')
_ELSE_HEAD_RE = re.compile(r'(?:^|\n)[ \t]*\}?\s*else\b(?!\s*\{)(?!\s+if\b)')


def _match_paren(code, open_pos):
    """从 `(` 起做括号计数，返回配对 `)` 的 offset；不配对返回 -1。"""
    depth, i, n = 0, open_pos, len(code)
    while i < n:
        c = code[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _next_char(code, pos):
    """跳过空白（注释已被 mask 成空格），返回 (offset, char)；到末尾返回 (-1, '')。"""
    i, n = pos, len(code)
    while i < n and code[i] in ' \t\r\n':
        i += 1
    return (i, code[i]) if i < n else (-1, '')


def _stmt_terminator(code, pos):
    """then 语句的终止符 offset：跟踪 () [] {} 深度，取深度 0 处第一个 `;` 或 `,`。

    返回 -1 表示没找到（宁可漏报）。
    """
    depth, i, n = 0, pos, len(code)
    while i < n:
        c = code[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if depth == 0:
                return -1
            depth -= 1
        elif depth == 0 and c in ';,':
            return i
        i += 1
    return -1


def check_flow_braces(files, findings):
    """C20 · 控制流语句跨行却没包块（curly_braces_in_flow_control_structures）。"""
    for fp in files:
        text = read(fp)
        code = mask_strings_comments(text)
        heads = [(m.end() - 1, True) for m in _FLOW_HEAD_RE.finditer(code)]
        heads += [(m.end(), False) for m in _ELSE_HEAD_RE.finditer(code)]
        for head, has_paren in heads:
            if has_paren:
                close = _match_paren(code, head)
                if close < 0:
                    continue
            else:
                close = head - 1
            tok, ch = _next_char(code, close + 1)
            if tok < 0 or ch in ';{':
                continue
            if code.count('\n', 0, tok) == code.count('\n', 0, head):
                continue  # 与 `if` 关键字同一行 → 单行写法，lint 不报
            end = _stmt_terminator(code, tok)
            if end < 0 or code[end] != ';':
                continue  # 不是以 `;` 结尾的语句（集合 if 元素等）→ 放行
            ln = code[:tok].count('\n') + 1
            findings.append(('HINT', 'C20', fp, ln,
                             bi('控制流语句跨行却没包块（给 then 加花括号；'
                                '宿主会报 curly_braces_in_flow_control_structures）',
                                'flow-control statement spans lines without braces '
                                '(wrap the then-part in a block; the host reports '
                                'curly_braces_in_flow_control_structures)')))


# ── C21（2026-10-06 新增）· library 指令必须在所有 directive 之前 ──────────
#
# 由来（宿主 `flutter analyze` 报 lib/services/exercise_history.dart:13
# error `library_directive_not_first`）：文件头先写了 `import`，把 `library;`
# 夹在了导入之后 —— Dart 要求 `library` 是**第一条 directive**（在
# import / export / part 之前）。
# ⚠️ 本工程 93 个 lib 文件里只有 1 个用过 `library;`（且是误加），**修法是删掉它**；
# 但这类错是 ERROR 级 —— 一处就让 `flutter test` 全量 `Failed to load`
# （看着像「爆发式报错」，实为一个根因），判据纯文本且零误报，值得单列一斧。
#
# 零误报设计：
#   1. 只认行首（可有缩进）的 directive 关键字 —— 字符串与注释已被 mask 成空格，
#      注释里写「library 放最前」不会被当成指令；
#   2. 只比较这些指令的**相对顺序**：`library` 不是第一条 → 报错；
#   3. 一个文件最多一个 `library`；`part of` 与它互斥，无冲突。
_DIRECTIVE_RE = re.compile(r'(?:^|\n)[ \t]*(library|import|export|part)\b')


def check_library_directive_order(files, findings):
    """C21 · library 指令必须在所有 directive 之前（library_directive_not_first）。"""
    for fp in files:
        code = mask_strings_comments(read(fp))
        seen = [(m.group(1), code[:m.start(1)].count('\n') + 1)
                for m in _DIRECTIVE_RE.finditer(code)]
        idx = -1
        for i, (kw, _) in enumerate(seen):
            if kw == 'library':
                idx = i
                break
        if idx <= 0:
            continue  # 没有 library，或 library 本来就在第一条 → 放行
        ln = seen[idx][1]
        findings.append(('ERROR', 'C21', fp, ln,
                         bi('library 指令必须排在所有 import/export/part 之前'
                            '（宿主报 library_directive_not_first；'
                            '若只是想写文件头注释，直接删掉这行 library;）',
                            'the library directive must come before all other '
                            'directives (host reports library_directive_not_first; '
                            'if you only meant a file-header comment, just delete '
                            'the line)')))


# C22 · test/ 里用 find.byType 定位「手势层 / 按钮」并喂给需要单一目标的控制器操作
# （tap / getSize / getCenter / …）——IconButton/TextButton 内部本身就是 InkWell，
# 一个步进器里就能命中 3 个 → 运行时 Bad state: Too many elements。
_FINDER_BYTYPE_RE = re.compile(r'find\.byType\((\w+)\)')
_AMBIG_WIDGETS = {
    'InkWell', 'InkResponse', 'GestureDetector', 'IconButton', 'TextButton',
    'ElevatedButton', 'OutlinedButton', 'FloatingActionButton', 'Icon',
}
_SINGLE_TARGET_OPS = (
    '.tap(', 'tester.tap(', 'getSize(', 'getCenter(', 'getTopLeft(',
    'getBottomRight(', 'press(', 'longPress(', 'drag(', 'dragFrom(',
    'scrollUntilVisible(',
)


def check_ambiguous_finder(files, findings):
    """C22 · test/ 的 find.byType(<手势层/按钮>) 用于需单一目标的操作 → 歧义风险。"""
    for fp in files:
        norm = fp.replace('\\', '/')
        if '/test/' not in norm and not norm.endswith('_test.dart'):
            continue
        lines = read(fp).split('\n')
        for i, raw in enumerate(lines, 1):
            # 整行注释（含「别用 find.byType(InkWell)」这类说明）不参与匹配，
            # 否则写注释防复发反而会被自己报出来。
            if raw.strip().startswith('//') or raw.strip().startswith('*'):
                continue
            m = _FINDER_BYTYPE_RE.search(raw)
            if not m or m.group(1) not in _AMBIG_WIDGETS:
                continue
            if not any(op in raw for op in _SINGLE_TARGET_OPS):
                continue
            # .first / .at(n) / byKey / descendant 已显式消歧 → 放行
            if re.search(r'\.first\b|\.at\(|byKey|descendant\(|ancestor\(', raw):
                continue
            findings.append(('HINT', 'C22', fp, i,
                             bi('find.byType(%s) 用于需单一目标的操作（tap/getSize/…）：'
                                '%s 在 widget 树里通常不止一个（如 IconButton 内部就是 '
                                'InkWell），运行时会抛 Bad state: Too many elements；'
                                '改用 find.byKey / .first / descendant 定位'
                                % (m.group(1), m.group(1)),
                                'find.byType(%s) feeds a single-target operation '
                                '(tap/getSize/...): %s usually occurs more than once in '
                                'the tree (e.g. IconButton embeds an InkWell) → runtime '
                                '"Bad state: Too many elements"; use find.byKey / .first '
                                '/ descendant instead' % (m.group(1), m.group(1)))))


# C23 · 静态成员必须 `类名.成员` 访问，不能裸名。
# Dart 的 static 成员**不参与继承**、也**不能裸名访问**：在 `State<X>` 子类里写
# `key: valueKey`（成员定义在 X 上）→ 宿主报 `undefined_identifier`。
_CLASS_DECL_RE = re.compile(r'^\s*(?:abstract\s+)?class\s+(\w+)')
# ⚠️ 必须**非贪婪**且用最后一个标识符：成员名在类型之后
# （`static const Key valueKey = ...` 的成员名是 `valueKey` 不是 `Key` ——
#  第一版写成 `static\s+(?:const|final|var)\s+(\w+)` 就抓成了类型名，导致 0 命中）。
_STATIC_MEMBER_RES = (
    re.compile(r'^\s*static\s+[\w<>,\[\]\s\?]+?\s+(\w+)\s*[\(=;{]'),
)


def _class_spans(lines):
    """每个 `class` 体的行范围（0-based，含端点）—— 花括号计数配平。"""
    spans = []
    for i, ln in enumerate(lines):
        if not _CLASS_DECL_RE.match(ln):
            continue
        depth = 0
        end = len(lines) - 1
        for j in range(i, len(lines)):
            depth += lines[j].count('{') - lines[j].count('}')
            if depth <= 0 and j > i:
                end = j
                break
        spans.append((i, end))
    return spans


def check_static_member_unqualified(files, findings):
    """C23 · 静态成员在「非定义类」里被裸名访问 → 宿主 `undefined_identifier`。"""
    for fp in files:
        code = mask_strings_comments(read(fp))
        lines = code.split('\n')
        spans = _class_spans(lines)
        if not spans:
            continue
        statics = []  # (成员名, 所属类 span 下标, 定义行)
        for si, (s, e) in enumerate(spans):
            for j in range(s, e + 1):
                for rx in _STATIC_MEMBER_RES:
                    m = rx.match(lines[j])
                    if m:
                        statics.append((m.group(1), si, j))
                        break
        if not statics:
            continue
        for name, si, defline in statics:
            # 降噪①：本文件里还有同名**非静态**声明（局部变量 / 参数）→ 用法可能合法
            if re.search(r'^\s*(?:final|const|var|late)\s+%s\b' % re.escape(name),
                         code, re.M):
                continue
            use_re = re.compile(r'(?<![\.\w])%s\b' % re.escape(name))
            cs, ce = spans[si]
            for j, ln in enumerate(lines):
                if j == defline or cs <= j <= ce:
                    continue  # 定义类体内裸用是合法的
                if not use_re.search(ln):
                    continue
                # 降噪③：**声明**不算用法 —— 别的类里有同名字段
                # （`final String dateKey;` / `{required this.dateKey}`）是合法且常见的，
                # 第一版把它们全报了（fitcoach 2 处误报）。
                # ⚠️ 不能误跳真错：`const SizedBox(key: valueKey)` 里 `const` 后面
                # 隔着 `SizedBox(`，`[\w\s]*` 到不了成员名 → 不会被放行。
                if re.search(r'(?:final|const|var|late)\s+[\w<>,\[\]\s\?]*\b%s\b'
                             % re.escape(name), ln) or \
                        re.search(r'this\.%s\b' % re.escape(name), ln):
                    continue
                # 降噪②：只报「落在另一个类的类体内」的用法；顶层 / 函数外的
                # 裸名太宽（可能是别的常量），放行以免噪声。
                if not any(s <= j <= e for (s, e) in spans):
                    continue
                findings.append(('ERROR', 'C23', fp, j + 1,
                                 bi('静态成员 `%s` 必须写成 `类名.%s` —— Dart 的 static '
                                    '不参与继承、也不能裸名访问，在别的类（哪怕是 '
                                    '`State<X>` 子类）里裸写会报 undefined_identifier'
                                    % (name, name),
                                    'static member `%s` must be qualified as '
                                    '`ClassName.%s` — Dart statics are not inherited '
                                    'and cannot be accessed by bare name from another '
                                    'class (not even from `State<X>`); the host '
                                    'reports undefined_identifier' % (name, name))))


# C24 · 判定函数被喂「距今 / 自上次」类参数的**字面量常量** → 判定吃假数据。
# 最危险的空心形态：`planDeload(weeksSinceLastDeload: 0, ...)` —— 0 是合法值、
# 宿主 analyze 不报错、单测也过，但整条减载判定从此**永远不成立**；
# 用户看到的是「它给了我一个结论」，实际是「它把常量当历史喂给了自己」。
# （2026-10-06 v1.6 候选盘点发现，登记为 #68 的地基欠账。）
_SINCE_LITERAL_RE = re.compile(r'\b([A-Za-z]\w*Since\w*)\s*:\s*(\d+)')


def check_since_literal_fallback(files, findings):
    """C24 · 「距今 / 自上次」类参数被喂字面量常量 → 判定吃假数据（静默失效）。"""
    for fp in files:
        norm = fp.replace('\\', '/')
        # 测试里**故意**写固定值（构造确定场景）→ 不算；只查产品代码。
        if '/test/' in norm or norm.endswith('_test.dart'):
            continue
        code = mask_strings_comments(read(fp))
        for i, ln in enumerate(code.split('\n'), 1):
            for m in _SINCE_LITERAL_RE.finditer(ln):
                # 降噪①：三元 `rawSince > 0 ? rawSince : 0` 的假分支，不是命名参数
                if '?' in ln[:m.start()]:
                    continue
                # 降噪②：声明 / 赋值（`final sessionsSinceExport = ...`）不是调用
                if re.search(r'(?:final|const|var|late|int|num)\s+%s\s*[=;]'
                             % re.escape(m.group(1)), ln):
                    continue
                findings.append(('HINT', 'C24', fp, i,
                                 bi('判定参数 `%s` 被喂字面量 `%s`：「距今/自上次」类入参'
                                    '必须是**真实历史值**，写死常量会让整条判定静默失效'
                                    '（不报错、不崩，只是永远不成立）。正确做法 = 先把'
                                    '这个历史事实落盘（如减载发生即写日期），再从存储读；'
                                    '若确实拿不到，宁可让判定返回「未知」也不要喂 0'
                                    % (m.group(1), m.group(2)),
                                    'Judgement parameter `%s` is fed the literal `%s`: '
                                    '"time-since" inputs must come from real history; a '
                                    'hardcoded constant makes the whole verdict silently '
                                    'unreachable (no error, no crash — just never fires). '
                                    'Persist the fact first, then read it; if unavailable, '
                                    'return "unknown" rather than 0'
                                    % (m.group(1), m.group(2)))))


# C25 · Web-only 库不许出现在 **VM 可达位置**（`test/` 与 L1 `core`·`services`）。
# `package:web` 依赖 `dart:js_interop`，VM 下不可用 —— 谁 import 它，`flutter test`
# 里所有（哪怕**间接**）引用它的测试文件会**集体 Failed to load**，而报错只指向
# 「加载失败的那个文件」，真凶（Web 库）完全看不出来（同 #59 的 `sembast_web` 老坑，
# 但那条是运行时、这条是编译期）。
# （2026-10-06 #63 导出文件下载引入 `package:web` 时发现 —— 该约束此前只写在
#   文件头注释里，没有任何常驻信号守着。登记 M-019。）
# （2026-10-06 **当天就漏了**：第一版只查**直接** import，而真凶是传递链 ——
#   `test/widget_test.dart → app.dart → … → export_action.dart → file_download.dart
#    → dart:js_interop`，整片 Failed to load。登记 M-021，改为**传递闭包**，
#   且必须**感知条件导入**（`if (dart.library.js_interop)` 的 Web 分支
#   在 VM 下不参与编译，不算命中）。）
_WEB_ONLY_IMPORT_RE = re.compile(
    r"^\s*(?:import|export)\s+['\"](package:web|dart:(?:js_interop|js_interop_unsafe|html|js|js_util))")

# 单条 import/export 指令（**含条件导入**）：
#   export 'file_download_stub.dart' if (dart.library.js_interop) 'file_download_web.dart';
_DIRECTIVE_RE = re.compile(
    r"^\s*(?:import|export)\s+['\"]([^'\"]+)['\"]"
    r"(?:\s+if\s*\(\s*dart\.library\.(\w+)\s*\)\s*['\"]([^'\"]+)['\"])?")

# 守卫为这些 = 当前目标是 Web → 该分支**不参与 VM 编译**。
_WEB_GUARDS = {'js_interop', 'js_interop_unsafe', 'html', 'js', 'js_util', 'ui_web'}

_WEB_URI_RE = re.compile(
    r'^(package:web|dart:(?:js_interop|js_interop_unsafe|html|js|js_util))(/|$)')


def _directives(text):
    """返回 [(行号, 指令全文)] —— 多行 import/export **先并在一行**再解析。

    条件导入经常换行写；不合并就会漏判（假阴性比误报更危险，这条尤其）。
    """
    out, buf, start = [], '', 0
    for i, ln in enumerate(text.split('\n'), 1):
        s = ln.strip()
        if not buf:
            if s.startswith('import ') or s.startswith('export '):
                buf, start = s, i
                if buf.endswith(';'):
                    out.append((start, buf))
                    buf = ''
        else:
            buf += ' ' + s
            if buf.endswith(';'):
                out.append((start, buf))
                buf = ''
    return out


def _resolve_uri(uri, from_file, pkg, root):
    """把 import 的 URI 解析成磁盘路径；不是本工程的文件返回 None。"""
    if uri.startswith('package:' + pkg + '/'):
        return os.path.join(root, 'lib', uri[len('package:' + pkg + '/'):])
    if uri.startswith('package:') or uri.startswith('dart:'):
        return None
    return os.path.join(os.path.dirname(from_file), uri)  # 相对导入


def _vm_deps(fp, pkg, root):
    """返回 (本工程依赖, Web-only URI 列表) —— 只算 **VM 下真会编译进来** 的。

    条件导入的两个分支按守卫取舍：`if (dart.library.js_interop)` 的那条
    只在 Web 下编译，VM 下**不存在**（这正是 `file_download.dart` 的修法）。
    """
    deps, web = [], []
    for _i, d in _directives(read(fp)):
        m = _DIRECTIVE_RE.match(d)
        if not m:
            continue
        for uri, guard in ((m.group(1), None), (m.group(3), m.group(2))):
            if not uri:
                continue
            if _WEB_URI_RE.match(uri):
                if guard is None or guard not in _WEB_GUARDS:
                    web.append(uri)  # 无条件 / 非 Web 守卫 → VM 真会编译 → 命中
                continue
            if guard is not None and guard in _WEB_GUARDS:
                continue  # Web 专属分支 → VM 下不编译
            p = _resolve_uri(uri, fp, pkg, root)
            if p and os.path.exists(p):
                deps.append(p.replace('\\', '/'))
    return deps, web


def check_web_only_imports(files, findings):
    """C25 · Web-only 库出现在 `test/` 或 L1 → 整片测试 Failed to load（ERROR）。

    两条判定：
      A **直接**：`test/` 或 L1 文件自己 import 了 Web-only 库。
      B **传递**（M-021）：从 `test/` 出发沿 import/export 闭包能摸到 Web-only 库
        —— 这才是 2026-10-06 的实际形态，只查直接那条根本拦不住。
    """
    root = project_root_ref
    pkg = read_pubspec_name(root) or ''
    test_files = [f for f in files if '/test/' in f.replace('\\', '/')]

    # ── A 直接命中 ──────────────────────────────────────────────
    for fp in files:
        norm = fp.replace('\\', '/')
        # ⚠️ zone 用**单语**两个变量：它要嵌进 bi() 的双语模板里，
        #    若 zone 本身已是 bi() 结果，中英文会互相插进对方的句子里。
        if '/test/' in norm:
            zone_zh, zone_en = '`test/` 里', 'in `test/`'
        elif '/lib/core/' in norm or '/lib/services/' in norm:
            zone_zh = 'L1（`lib/core/` 或 `lib/services/`）里'
            zone_en = 'in L1 (`lib/core/` or `lib/services/`)'
        else:
            # L2/L3（`lib/features/**` / `lib/widgets/**` / `lib/data/**`）= 允许区。
            continue
        for i, ln in enumerate(read(fp).split('\n'), 1):
            m = _WEB_ONLY_IMPORT_RE.search(ln)
            if not m:
                continue
            findings.append(('ERROR', 'C25', fp, i,
                             bi('%s出现了 Web-only 库 `%s`：它**在 VM 下不可用** → '
                                '`flutter test` 中所有（哪怕间接）引用本文件的测试会'
                                '**集体 Failed to load**，而报错只指向加载失败的文件，'
                                '看不出真凶。修法 = 把 Web-only 调用**收口进一个 L2/L3 '
                                '适配文件**（如 `lib/features/export/file_download.dart`），'
                                'L1 只留纯函数（能落单测的那一半），测试只测 L1。'
                                % (zone_zh, m.group(1)),
                                'the web-only library `%s` is imported %s: it is '
                                '**unavailable on the VM** → every test that reaches '
                                'this file (even indirectly) fails to load, and the '
                                'error only names the failing file, not the cause. '
                                'Fix = confine web-only calls to a single L2/L3 '
                                'adapter and keep L1 pure/testable.'
                                % (m.group(1), zone_en))))

    # ── B 传递命中（从 test/ 出发的 import/export 闭包）────────────
    for tf in test_files:
        seen, path = {tf.replace('\\', '/')}, {tf.replace('\\', '/'): [tf]}
        queue = [tf.replace('\\', '/')]
        while queue:
            n = queue.pop(0)
            deps, web = _vm_deps(n, pkg, root)
            if web:
                chain = ' → '.join(path[n] + [web[0]])
                findings.append(('ERROR', 'C25', tf, 0,
                                 bi('本测试文件**间接**引到了 Web-only 库 `%s`：\n'
                                    '    %s\n'
                                    'VM 下 `dart:js_interop` 不可用 → 本文件（而不是真凶）'
                                    '会 **Failed to load**，报错是满屏 `toJS` / `jsify` '
                                    '未定义、从 `package:web` **自己的源码**里冒出来。\n'
                                    '修法 = 在链上第一个平台相关文件处做**条件导入拆分**'
                                    '（`export \'x_stub.dart\' if (dart.library.js_interop) '
                                    '\'x_web.dart\'`），让 Web 分支在 VM 下压根不编译。'
                                    % (web[0], chain),
                                    'this test file **indirectly** reaches the web-only '
                                    'library `%s`:\n    %s\n'
                                    '`dart:js_interop` is unavailable on the VM → this '
                                    'file (not the real culprit) fails to load, with a '
                                    'wall of `toJS` / `jsify` errors reported inside '
                                    '`package:web`\'s own sources.\n'
                                    'Fix = split the first platform-dependent file on '
                                    'the chain with a **conditional export** '
                                    '(`export \'x_stub.dart\' if (dart.library.js_interop) '
                                    '\'x_web.dart\'`) so the web branch never compiles '
                                    'on the VM.' % (web[0], chain))))
                break
            for d in deps:
                if d in seen:
                    continue
                seen.add(d)
                path[d] = path[n] + [d]
                queue.append(d)


def main():
    global project_root_ref
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', default='C:/code/fitcoach')
    ap.add_argument('--no-test', action='store_true',
                    help='skip <project>/test (it is scanned by default since v3) / '
                         '跳过 test/ 目录（v3 起默认体检 test/）')
    args = ap.parse_args()
    with_test = not args.no_test

    project = os.path.abspath(args.project)
    project_root_ref = project
    lib_dir = os.path.join(project, 'lib') if os.path.isdir(os.path.join(project, 'lib')) \
        else project
    if not os.path.isdir(lib_dir):
        print(bi('找不到 lib 目录：%s' % lib_dir, 'lib directory not found: %s' % lib_dir))
        sys.exit(2)

    files = find_dart_files(lib_dir)
    # 测试代码也是交付物：**v3 起默认一并体检**（import 仍按 lib_dir 解析，符合
    # package: 导入语义）。此前默认只扫 lib/，test/ 下的断 import 完全查不到；
    # 更致命的是「少写一条 import」连 --with-test 也抓不到（见 C11）。
    if with_test and os.path.isdir(os.path.join(project, 'test')):
        files = files + find_dart_files(os.path.join(project, 'test'))
    print(bi('扫描 %d 个 dart 文件（%s）' % (len(files), lib_dir),
             'Scanned %d dart files (%s)' % (len(files), lib_dir)))

    findings = []
    deps = parse_pubspec_deps(project)
    runtime_deps = parse_pubspec_runtime_deps(project)
    assets = parse_pubspec_assets(project)
    enums = collect_enums(lib_dir)
    named_params = collect_named_params(lib_dir)
    # test/ 里也有本地函数签名（如测试里的 payload({List<X>? cardioList})），
    # 只扫 lib/ 会把这些调用全报成"拼写错误"（2026-10-01 修）。
    if with_test and os.path.isdir(os.path.join(project, 'test')):
        named_params |= collect_named_params(os.path.join(project, 'test'))
    symbols, ext_members = collect_file_symbols(lib_dir)
    part_map, export_map = collect_part_export(lib_dir)
    pkg = read_pubspec_name(project)

    check_imports(files, lib_dir, project, findings, pkg)
    check_pubspec_deps(files, deps, findings, pkg)
    check_enum_usage(files, enums, findings)
    check_assets(files, assets, findings)
    check_named_params(files, named_params, findings)
    check_unused_imports(files, lib_dir, symbols, findings, pkg, ext_members)
    check_brackets(files, findings)
    check_string_enum(files, findings)
    check_unused_deps(files, runtime_deps, findings)
    check_missing_imports(files, lib_dir, symbols, findings, pkg, part_map, export_map)
    check_lint_naming(files, findings)
    check_consumer_state_pair(files, findings)
    check_member_exists(files, findings)
    check_param_member_exists(files, findings)
    check_lint_table(files, findings)
    check_deprecated_api(files, findings)
    check_local_underscore(files, findings)
    check_final_field_init(files, findings)
    check_flow_braces(files, findings)
    check_library_directive_order(files, findings)
    check_ambiguous_finder(files, findings)
    check_static_member_unqualified(files, findings)
    check_since_literal_fallback(files, findings)
    check_web_only_imports(files, findings)

    errors = [f for f in findings if f[0] == 'ERROR']
    hints = [f for f in findings if f[0] == 'HINT']

    def show(lst):
        for sev, cid, fp, ln, msg in lst:
            rel = os.path.relpath(fp, project).replace('\\', '/')
            where = ('%s:%d' % (rel, ln)) if ln and ln > 0 else rel
            print('  [%s] %s  %s' % (cid, where, msg))

    if errors:
        print('\n' + bi('❌ ERROR（编译期硬错，必须先修）：',
                       'ERROR (compile-time hard errors, must fix first):'))
        show(errors)
    if hints:
        print('\n' + bi('⚠️ HINT（启发式，请人工确认）：',
                       'HINT (heuristic, please confirm manually):'))
        show(hints)
    print('\n' + bi('枚举定义：%d 个；命名参数池：%d 个；assets：%d 个；运行时依赖：%d 个'
                    % (len(enums), len(named_params), len(assets), len(runtime_deps)),
                    'Enums: %d; named-param pool: %d; assets: %d; runtime deps: %d'
                    % (len(enums), len(named_params), len(assets), len(runtime_deps))))
    if not errors and not hints:
        print('\nRESULT: 工程干净 ✅  /  RESULT: project is clean ✅')
    elif not errors:
        print('\n' + bi('RESULT: 无硬错，但有 %d 处 HINT ⚠️' % len(hints),
                       'RESULT: no hard errors, but %d HINT(s) ⚠️' % len(hints)))
    else:
        print('\n' + bi('RESULT: 发现 %d 处问题 ⚠️' % len(findings),
                       'RESULT: found %d issue(s) ⚠️' % len(findings)))
    # 每次运行都提醒反哺：宿主 flutter 报出本工具没抓到的问题时，必须补斧而不是只改业务代码
    print('\n' + bi('📌 宿主 flutter 若报出本工具未抓到的问题 → 走反哺流程补斧'
                    '（见 MISSES.md 漏报台账）',
                    '📌 If the host\'s flutter reports an issue this tool missed → run the '
                    'feedback loop and add an axe (see MISSES.md escape ledger)'))


if __name__ == '__main__':
    main()
