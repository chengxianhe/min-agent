"""Bounded display text; omit known sensitive files and redact common credentials."""
from __future__ import annotations

import json
import re
from pathlib import Path

SECRET_KEY = re.compile(r"(?i)(?:api.?key|token|secret|password|passwd|authorization|cookie|credential|raw_content|reasoning|encrypted_content|base_instructions|developer_instructions)")
PROTECTED = re.compile(r'''(?i)(?:auth\.json|(?:^|[/\s])\.env(?:[.\s'"\]\)]|$)|credentials|private.?key)''')


def clean_text(value, limit=1800):
    if isinstance(value, (dict, list)):
        def scrub(item):
            if isinstance(item, dict):
                return {str(k): "[已隐藏]" if SECRET_KEY.search(str(k)) else scrub(v) for k, v in item.items()}
            if isinstance(item, list):
                return [scrub(v) for v in item[:30]]
            return item
        value = json.dumps(scrub(value), ensure_ascii=False)
    text = str(value or "").replace(str(Path.home()), "~")
    text = re.sub(r"(?i)\bBearer\s+[^\s\"']+", "Bearer [已隐藏]", text)
    text = re.sub(r"\b(?:sk-|ghp_|github_pat_|AKIA)[A-Za-z0-9_\-]{12,}", "[已隐藏凭据]", text)
    text = re.sub(r'''(?ix)([\w-]*(?:api[_-]?key|token|secret|password|passwd|authorization|cookie)[\w-]*["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)''', r"\1[已隐藏]", text)
    text = re.sub(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1[已隐藏]@", text)
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[邮箱已隐藏]", text)
    text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已隐藏]", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = "".join(c for c in text if c in "\n\t" or ord(c) >= 32)
    return text if len(text) <= limit else text[:limit] + "\n…已截断"


def display_output(parameters, result):
    if PROTECTED.search(str(parameters)):
        return "涉及敏感配置的调用，结果内容不展示。"
    return clean_text(result)
