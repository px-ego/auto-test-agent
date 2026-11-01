"""
知识文件加载器 - 解析 markdown frontmatter + 正文
"""
import re
from typing import Dict, Any, Tuple, Optional


def load_knowledge(file_path: str) -> Tuple[Dict[str, Any], str]:
    """
    加载知识文件，解析 frontmatter 和正文

    Args:
        file_path: 知识文件路径

    Returns:
        (frontmatter 字典, 正文内容)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    frontmatter, body = _parse_frontmatter(content)

    # 从正文中提取技能组名称
    station_name = _extract_station_name(body)
    if station_name:
        frontmatter['station'] = station_name

    return frontmatter, body


def _extract_station_name(body: str) -> Optional[str]:
    """
    从正文中提取技能组名称

    支持格式：
    - 技能组：jiaotong
    - 技能组名称：jiaotong
    """
    match = re.search(r'技能组[名称]*[：:]\s*(\S+)', body)
    if match:
        return match.group(1).strip()

    return None


def _parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    解析 frontmatter（--- 分隔的 key:value）

    支持类型：int, float, bool, 逗号分隔列表, 字符串
    """
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
    if not match:
        return {}, content

    fm_text, body = match.groups()
    frontmatter = {}

    for line in fm_text.split('\n'):
        line = line.strip()
        if not line or ':' not in line:
            continue

        key, value = line.split(':', 1)
        key = key.strip()
        value = value.strip()

        # 类型转换
        if value.lower() in ('true', 'false'):
            frontmatter[key] = value.lower() == 'true'
        elif ',' in value:
            # 逗号分隔列表
            frontmatter[key] = [v.strip() for v in value.split(',')]
        else:
            # 尝试数字
            try:
                if '.' in value:
                    frontmatter[key] = float(value)
                else:
                    frontmatter[key] = int(value)
            except ValueError:
                frontmatter[key] = value

    return frontmatter, body.strip()
