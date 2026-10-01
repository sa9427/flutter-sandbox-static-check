#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flutter 沙箱静态体检（九板斧）—— 纯标准库，无第三方依赖。

对 Flutter 工程的 lib/ 做文本静态检查，替代无法运行的 flutter analyze。
用法：
    python3 check.py --project C:/code/fitcoach

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
    'convert': {'json', 'jsonEncode', 'jsonDecode', 'utf8', 'base64', 'base64Url', 'ascii',
                'latin1', 'SystemEncoding', 'Encoding', 'Codec', 'Converter', 'Decoder',
                'Encoder', 'ClosableStringSink', 'StringConversionSink'},
    'math': {'min', 'max', 'pow', 'sqrt', 'sin', 'cos', 'tan', 'atan', 'atan2', 'exp', 'log',
             'pi', 'e', 'Random', 'Point', 'Rectangle', 'MutableRectangle'},
    'async': {'Future', 'Stream', 'StreamController', 'StreamSubscription', 'Completer', 'Timer',
              'Zone', 'scheduleMicrotask', 'runZoned', 'AsyncError', 'FutureOr'},
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
            for m in re.finditer(r'\{([^{}]*)\}', text):
                body = m.group(1)
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
        for m in re.finditer(r'\b([a-z]\w*)\s*\(([^)]*)\)', text):
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


def check_unused_imports(files, lib_dir, symbols, findings, pkg=None):
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
                # symbols 的键是相对 lib 的路径，必须同口径查；此前用绝对路径
                # 查询导致本分支永远拿不到符号 → 工程内未用 import 从未被抓到。
                imported = symbols.get(rel)
                body = re.sub(r"^\s*import\s+'[^']+'[^;]*;\s*$", '', text, flags=re.M)
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
    """file_path(rel) -> 顶层标识符集合。"""
    sym = {}
    for root, _, files in os.walk(lib_dir):
        for f in files:
            fp = os.path.join(root, f)
            if not f.endswith('.dart') or EXCLUDE_RE.search(fp):
                continue
            names = set()
            for raw in read(fp).split('\n'):
                line = raw.rstrip()
                # 只取顶层声明（无缩进）：与 analyzer 的「库公开命名空间」口径一致，
                # 类成员不参与未用 import 判定（否则 build/dispose 之类会到处命中）。
                if not line or line[0].isspace():
                    continue
                m = re.match(
                    r'(?:abstract\s+|base\s+|final\s+|sealed\s+|interface\s+|mixin\s+)*'
                    r'(?:class|enum|mixin|typedef|extension)\s+([A-Za-z_]\w*)', line)
                if m:
                    names.add(m.group(1))
                    continue
                # 顶层函数（返回类型可含泛型）
                m = re.match(
                    r'(?:external\s+)?[A-Za-z_][\w<>,\s\[\]?]*?\s+([a-z_]\w*)\s*\(', line)
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
            # 单字母标识符不做「已引用」的证据（sort((a, b) => ...) 的 b 会误命中），
            # 私有名（_ 开头）不在库公开命名空间内，同样不能作为证据。
            names = {n for n in names if len(n) >= 2 and not n.startswith('_')}
            rel = os.path.relpath(fp, lib_dir).replace('\\', '/')
            sym[rel] = names
    return sym


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


def main():
    global project_root_ref
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', default='C:/code/fitcoach')
    ap.add_argument('--with-test', action='store_true',
                    help='also scan <project>/test (test code needs checking too) / '
                         '同时体检 test/ 目录')
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    project_root_ref = project
    lib_dir = os.path.join(project, 'lib') if os.path.isdir(os.path.join(project, 'lib')) \
        else project
    if not os.path.isdir(lib_dir):
        print(bi('找不到 lib 目录：%s' % lib_dir, 'lib directory not found: %s' % lib_dir))
        sys.exit(2)

    files = find_dart_files(lib_dir)
    # 测试代码也是交付物：开启后一并体检（import 仍按 lib_dir 解析，符合
    # package: 导入语义；此前只能扫 lib/，test/ 下的断 import 完全查不到）。
    if args.with_test and os.path.isdir(os.path.join(project, 'test')):
        files = files + find_dart_files(os.path.join(project, 'test'))
    print(bi('扫描 %d 个 dart 文件（%s）' % (len(files), lib_dir),
             'Scanned %d dart files (%s)' % (len(files), lib_dir)))

    findings = []
    deps = parse_pubspec_deps(project)
    runtime_deps = parse_pubspec_runtime_deps(project)
    assets = parse_pubspec_assets(project)
    enums = collect_enums(lib_dir)
    named_params = collect_named_params(lib_dir)
    symbols = collect_file_symbols(lib_dir)
    pkg = read_pubspec_name(project)

    check_imports(files, lib_dir, project, findings, pkg)
    check_pubspec_deps(files, deps, findings, pkg)
    check_enum_usage(files, enums, findings)
    check_assets(files, assets, findings)
    check_named_params(files, named_params, findings)
    check_unused_imports(files, lib_dir, symbols, findings, pkg)
    check_brackets(files, findings)
    check_string_enum(files, findings)
    check_unused_deps(files, runtime_deps, findings)

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


if __name__ == '__main__':
    main()
