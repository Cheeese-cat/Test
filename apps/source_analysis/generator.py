"""用例生成：优先调用大模型，失败时退回规则模板，保证演示不中断。"""
import json
import os
import re

import requests

SCENES = {'normal', 'boundary', 'exception', 'auth'}
PRIORITIES = ['P0', 'P1', 'P2', 'P3']
MAX_CASES = 200
LLM_TIMEOUT = 120


def _llm_config():
    """优先用平台「统一配置中心」里的 writer 配置，其次读环境变量。"""
    try:
        from apps.requirement_analysis.models import AIModelConfig
        cfg = AIModelConfig.objects.filter(role='writer', is_active=True).first()
        if cfg and cfg.api_key and cfg.base_url:
            return {'base_url': cfg.base_url, 'api_key': cfg.api_key, 'model': cfg.model_name}
    except Exception:
        pass
    key = os.getenv('OPENAI_API_KEY', '')
    if key.startswith('sk-'):
        return {
            'base_url': os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com/v1'),
            'api_key': key,
            'model': os.getenv('JUDGE_MODEL', 'deepseek-chat'),
        }
    return None


def _compact(analysis):
    items = []
    for ep in analysis['endpoints']:
        item = {
            'method': ep['method'],
            'path': ep['path'],
            'module': ep['module'],
            'auth': ep['auth'],
        }
        if ep.get('body_fields'):
            item['body'] = [
                {'name': f['name'], 'type': f['type'], 'required': f['required'],
                 'rule': ','.join(a.split('.')[-1] for a in f['annotations'])}
                for f in ep['body_fields']
            ]
        if ep.get('query'):
            item['query'] = ep['query']
        if ep.get('path_vars'):
            item['path_vars'] = ep['path_vars']
        if ep.get('multipart'):
            item['multipart'] = ep['multipart']
        items.append(item)
    return items


PROMPT = """你是一名有 5 年经验的测试开发工程师。下面是对一个 {framework} 项目做静态分析后得到的接口清单（含请求体字段和校验注解）。
请为每个接口设计 2-4 条测试用例，覆盖：正常流程、参数校验（缺失/空值/超长/类型错误）、权限（未登录/越权）、业务异常（资源不存在）。

要求：
1) title 具体到场景，如「POST /api/auth/login 密码为空应返回 400」；
2) steps 写成可执行步骤，包含请求方法、路径和关键参数；
3) expected 写清楚状态码和业务提示；
4) priority 取 P0/P1/P2/P3；scene 取 normal/boundary/exception/auth；
5) 只输出 JSON 数组，不要任何解释或 Markdown 代码块。

字段：title, module, method, path, scene, priority, preconditions, steps, expected

接口清单：
{endpoints}
"""


def _extract_json(text):
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```[a-zA-Z]*\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    start, end = text.find('['), text.rfind(']')
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _normalize(raw_cases, analysis):
    by_path = {(e['method'], e['path']): e for e in analysis['endpoints']}
    result = []
    for c in raw_cases:
        if not isinstance(c, dict):
            continue
        title = str(c.get('title', '')).strip()
        if not title:
            continue
        method = str(c.get('method', '')).upper().strip()
        path = str(c.get('path', '')).strip()
        ep = by_path.get((method, path))
        scene = c.get('scene') if c.get('scene') in SCENES else 'normal'
        priority = str(c.get('priority', 'P2')).upper()
        if priority not in PRIORITIES:
            priority = 'P2'
        result.append({
            'title': title[:300],
            'module': str(c.get('module') or (ep['module'] if ep else '接口'))[:100],
            'method': method or (ep['method'] if ep else ''),
            'path': path or (ep['path'] if ep else ''),
            'scene': scene,
            'priority': priority,
            'preconditions': str(c.get('preconditions', '') or '')[:1000],
            'steps': str(c.get('steps', '') or '')[:2000],
            'expected': str(c.get('expected', '') or '')[:1000],
        })
        if len(result) >= MAX_CASES:
            break
    return result


def ai_generate(analysis):
    cfg = _llm_config()
    if not cfg:
        return None
    prompt = PROMPT.format(framework=analysis['framework'],
                           endpoints=json.dumps(_compact(analysis), ensure_ascii=False))
    url = cfg['base_url'].rstrip('/') + '/chat/completions'
    resp = requests.post(
        url,
        headers={'Authorization': 'Bearer ' + cfg['api_key'], 'Content-Type': 'application/json'},
        json={
            'model': cfg['model'],
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.2,
            'max_tokens': 8000,
        },
        timeout=LLM_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError('模型接口返回 %s: %s' % (resp.status_code, resp.text[:200]))
    content = resp.json()['choices'][0]['message']['content']
    raw = _extract_json(content)
    if not raw:
        raise RuntimeError('模型输出不是合法 JSON')
    cases = _normalize(raw, analysis)
    if not cases:
        raise RuntimeError('模型没有生成有效用例')
    return cases


def _case(title, module, ep, scene, priority, pre, steps, expected):
    return {
        'title': title, 'module': module, 'method': ep['method'], 'path': ep['path'],
        'scene': scene, 'priority': priority, 'preconditions': pre,
        'steps': steps, 'expected': expected,
    }


def _rule_cases(ep):
    m, p = ep['method'], ep['path']
    module = ep.get('module') or '接口'
    auth_pre = '服务已启动，已准备有效 JWT（Authorization: Bearer <token>）' if ep['auth'] else '服务已启动'
    cases = []

    cases.append(_case(
        '%s %s 正常请求返回成功' % (m, p), module, ep, 'normal', 'P0', auth_pre,
        '1. 构造合法请求参数\n2. 发送 %s %s\n3. 检查响应体与状态码' % (m, p),
        'HTTP 200，返回业务数据，关键字段与接口约定一致'))

    body_fields = ep.get('body_fields') or []
    required = [f for f in body_fields if f['required']]
    if required:
        f = required[0]
        cases.append(_case(
            '%s %s 缺少必填字段 %s 应被拒绝' % (m, p, f['name']), module, ep, 'exception', 'P1', auth_pre,
            '1. 请求体去掉 %s 字段（或传 null）\n2. 发送 %s %s' % (f['name'], m, p),
            'HTTP 400 或业务错误码，提示 %s 不能为空' % f['name']))

    strings = [f for f in body_fields if f['type'] in ('String',)]
    if strings:
        f = strings[0]
        cases.append(_case(
            '%s %s %s 传超长字符串触发边界校验' % (m, p, f['name']), module, ep, 'boundary', 'P2', auth_pre,
            '1. 将 %s 设为 1000 个字符\n2. 发送 %s %s' % (f['name'], m, p),
            'HTTP 400 或截断处理，返回长度校验提示，不出现 500'))

    if ep.get('query'):
        q = ep['query'][0]
        cases.append(_case(
            '%s %s 缺少查询参数 %s' % (m, p, q), module, ep, 'exception', 'P2', auth_pre,
            '1. 请求地址不带 %s 参数\n2. 发送 %s %s' % (q, m, p),
            'HTTP 400，提示参数缺失；若接口允许默认值则返回默认结果'))

    if ep['auth']:
        cases.append(_case(
            '%s %s 未携带 Token 应返回 401' % (m, p), module, ep, 'auth', 'P0', '服务已启动，不携带 Authorization',
            '1. 不设置 Authorization 请求头\n2. 发送 %s %s' % (m, p),
            'HTTP 401，提示未认证，不返回业务数据'))

    if ep.get('path_vars'):
        v = ep['path_vars'][0]
        cases.append(_case(
            '%s %s 路径参数 %s 不存在应返回 404' % (m, p, v), module, ep, 'exception', 'P2', auth_pre,
            '1. 将 %s 设为不存在的 ID（如 999999）\n2. 发送 %s %s' % (v, m, p),
            'HTTP 404 或业务错误，提示资源不存在，不出现 500'))

    return cases[:4] if len(cases) > 4 else cases


def rule_generate(analysis):
    cases = []
    for ep in analysis['endpoints']:
        cases.extend(_rule_cases(ep))
        if len(cases) >= MAX_CASES:
            break
    return cases[:MAX_CASES]


def generate(analysis):
    """返回 (cases, mode)，mode 为 ai 或 rule。"""
    try:
        cases = ai_generate(analysis)
        if cases:
            return cases, 'ai'
    except Exception as exc:  # 模型不可用不影响演示
        print('[source_analysis] AI generation failed, fallback to rules:', exc)
    return rule_generate(analysis), 'rule'
