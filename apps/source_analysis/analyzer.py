"""源码静态分析：从本地项目目录抽取接口、DTO 字段与表结构。

设计原则：这一步是确定性的，不调用大模型，只做解析与归纳。
"""
import os
import re

SKIP_DIRS = {
    '.git', '.idea', '.vscode', '.mvn', 'node_modules', 'target', 'build', 'dist',
    'venv', '.venv', '__pycache__', 'logs', 'media', 'allure', 'static', 'static_files',
    'site-packages', '.pytest_cache', 'migrations',
}
MAX_FILES = 4000

CLASS_MAPPING_RE = re.compile(r'@RequestMapping\s*\(\s*(?:(?:value|path)\s*=\s*)?"([^"]*)"', re.S)
METHOD_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch)Mapping'
    r'(?:\s*\(\s*(?:(?:value|path)\s*=\s*)?"([^"]*)"[^)]*\))?', re.S)
SIG_RE = re.compile(r'public\s+([\w<>,\[\]\s\.]+?)\s+(\w+)\s*\(([^)]*)\)', re.S)
CLASS_DECL_RE = re.compile(r'(?:public\s+)?(?:final\s+)?class\s+(\w+)')
FIELD_RE = re.compile(
    r'((?:\s*@[\w.]+(?:\s*\([^)]*\))?)*)\s*(?:private|protected)\s+'
    r'([\w<>\[\],\s\.]+?)\s+(\w+)\s*(?:=[^;]+)?;', re.S)
REQUIRED_ANN = ('NotBlank', 'NotNull', 'NotEmpty')


def _iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.'))
        for name in filenames:
            yield os.path.join(dirpath, name)


def _detect_framework(root):
    pom = os.path.join(root, 'pom.xml')
    if os.path.exists(pom):
        try:
            text = open(pom, encoding='utf-8', errors='ignore').read()
        except OSError:
            text = ''
        if 'spring-boot' in text:
            return 'Spring Boot'
        return 'Java / Maven'
    if os.path.exists(os.path.join(root, 'requirements.txt')):
        try:
            text = open(os.path.join(root, 'requirements.txt'), encoding='utf-8', errors='ignore').read().lower()
        except OSError:
            text = ''
        if 'django' in text:
            return 'Django'
        if 'flask' in text:
            return 'Flask'
        return 'Python'
    if os.path.exists(os.path.join(root, 'package.json')):
        return 'Node.js'
    return '未知'


def _parse_params(params, endpoint):
    body = re.search(r'@RequestBody\s+([\w\.]+)', params)
    endpoint['body'] = body.group(1) if body else None
    endpoint['query'] = [m[1] for m in re.findall(
        r'@RequestParam[^,)]*?(?:\(\s*(?:value\s*=\s*)?"([^"]*)")?[^,)]*\)?\s*[\w<>\[\]]+\s+(\w+)', params)]
    endpoint['path_vars'] = [m[1] for m in re.findall(
        r'@PathVariable[^,)]*?(?:\(\s*(?:value\s*=\s*)?"([^"]*)")?[^,)]*\)?\s*[\w<>\[\]]+\s+(\w+)', params)]
    part = re.search(r'@RequestPart\s*\(\s*"([^"]+)"', params)
    endpoint['multipart'] = part.group(1) if part else None
    header = re.search(r'@RequestHeader\s*\(\s*(?:value\s*=\s*)?"([^"]+)"', params)
    endpoint['auth_header'] = header.group(1) if header else None


def _parse_dto_fields(text):
    fields = []
    for m in FIELD_RE.finditer(text):
        anns = re.findall(r'@([\w.]+)', m.group(1) or '')
        ftype = re.sub(r'\s+', ' ', m.group(2)).strip()
        fields.append({
            'name': m.group(3),
            'type': ftype,
            'annotations': anns,
            'required': any(a.split('.')[-1] in REQUIRED_ANN for a in anns),
        })
    return fields


def _parse_controllers(root):
    endpoints, dto_sources = [], {}
    for path in _iter_files(root):
        if not path.endswith('Controller.java'):
            continue
        try:
            text = open(path, encoding='utf-8', errors='ignore').read()
        except OSError:
            continue
        if '@RestController' not in text and '@Controller' not in text:
            continue
        cm = CLASS_MAPPING_RE.search(text)
        base = cm.group(1) if cm else ''
        controller = os.path.basename(path)[:-5]
        module = controller.replace('Controller', '') or controller
        for m in METHOD_MAPPING_RE.finditer(text):
            method = m.group(1).upper()
            sub = m.group(2) or ''
            sig = SIG_RE.search(text[m.end():])
            if not sig:
                continue
            endpoint = {
                'method': method,
                'path': (base + sub) or '/',
                'handler': sig.group(2),
                'controller': controller,
                'module': module,
                'returns': sig.group(1).strip(),
                'body': None, 'query': [], 'path_vars': [],
                'multipart': None, 'auth_header': None,
            }
            _parse_params(sig.group(3), endpoint)
            if endpoint['body'] and endpoint['body'] not in dto_sources:
                dto_sources[endpoint['body']] = None
            endpoints.append(endpoint)
    return endpoints, dto_sources


def _collect_dtos(root, names):
    """在项目里找到 @RequestBody 引用的 DTO 源文件并解析字段。"""
    if not names:
        return {}
    found = {}
    want = {n.split('.')[-1] for n in names}
    for path in _iter_files(root):
        if not path.endswith('.java') or path.endswith('Controller.java'):
            continue
        try:
            text = open(path, encoding='utf-8', errors='ignore').read()
        except OSError:
            continue
        decl = CLASS_DECL_RE.search(text)
        if not decl or decl.group(1) not in want or decl.group(1) in found:
            continue
        found[decl.group(1)] = _parse_dto_fields(text)
        if len(found) == len(want):
            break
    return found


def _parse_schema(root):
    tables = []
    for path in _iter_files(root):
        if not path.endswith('.sql'):
            continue
        try:
            text = open(path, encoding='utf-8', errors='ignore').read()
        except OSError:
            continue
        for m in re.finditer(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\((.*?)\)\s*;',
                             text, re.S | re.I):
            body = m.group(2)
            columns = len(re.findall(r'^\s*`?\w+`?\s+\w', body, re.M))
            tables.append({'name': m.group(1), 'columns': columns})
    return tables


def analyze(root):
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise ValueError('目录不存在：%s' % root)

    files = list(_iter_files(root))
    if len(files) > MAX_FILES:
        files = files[:MAX_FILES]

    framework = _detect_framework(root)
    endpoints, dto_names = _parse_controllers(root)
    dtos = _collect_dtos(root, set(dto_names))
    tables = _parse_schema(root)

    has_auth = False
    for path in files[:400]:
        if path.endswith('.java'):
            try:
                text = open(path, encoding='utf-8', errors='ignore').read()
            except OSError:
                continue
            if 'Authorization' in text or 'JwtFilter' in text or 'JwtInterceptor' in text:
                has_auth = True
                break

    for ep in endpoints:
        ep['body_fields'] = dtos.get((ep.get('body') or '').split('.')[-1], [])
        ep['auth'] = bool(has_auth or ep.get('auth_header')) and not ep['path'].startswith('/api/auth/')

    langs = {}
    for f in files:
        ext = os.path.splitext(f)[1].lower() or '(no ext)'
        langs[ext] = langs.get(ext, 0) + 1

    return {
        'root': root,
        'framework': framework,
        'file_count': len(files),
        'endpoints': endpoints,
        'dtos': dtos,
        'tables': tables,
        'auth': has_auth,
        'languages': dict(sorted(langs.items(), key=lambda x: -x[1])[:6]),
    }
