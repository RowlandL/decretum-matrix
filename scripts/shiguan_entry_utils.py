"""Shared Shiguan index entry enrichment helpers."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import zlib
import sys

sys.dont_write_bytecode = True


TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\\/-]{2,}|[\u4e00-\u9fff]{2,}")
PATH_RE = re.compile(r"(?:[A-Za-z]:\\[^\r\n;|]+|(?:[\w.\-\u4e00-\u9fff]+[\\/])+[\w.\-()\u4e00-\u9fff]+)")
SOURCE_PATH_HINT_RE = re.compile(
    r"(?:^[A-Za-z]:\\|^references[\\/]|^\.{1,2}[\\/]|^[/\\]|"
    r"\.(?:jsonl|sqlite|db|md|py|toml|yaml|yml|json|txt|log)$)",
    re.IGNORECASE,
)
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
ENGLISH_RE = re.compile(r"[A-Za-z]")
BASE36_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

ENGLISH_TERM_ZH = {
    "menxia": "门下省",
    "zhongshu": "中书省",
    "shangshu": "尚书省",
    "court": "朝廷",
    "startup": "启动",
    "intent inference": "意图初判",
    "historical clue judgment": "历史线索初判",
    "memory clues": "历史记忆线索",
    "three departments discussion": "三省具体会审",
    "three-department discussion": "三省具体会审",
    "concrete deliberation": "具体细节讨论",
    "taizi synthesis": "太子整理回奏",
    "detail questions": "细节追问",
    "blocking detail question": "阻塞细节问题",
    "clarification is recursive": "递归澄清",
    "clarification round": "回问轮次",
    "fresh discussion": "重新会审",
    "pre-drafted backlog": "预拟问题积压",
    "one question at a time": "逐一提问",
    "clarification routing": "澄清转问",
    "shiguan web service": "史馆图谱服务",
    "ensure_shiguan_web": "史馆网页确保脚本",
    "background service": "后台服务",
    "lan": "局域网",
    "lan urls": "局域网入口",
    "lan-reachable": "局域网可访问",
    "local url": "本机入口",
    "mobile": "手机适配",
    "tablet": "平板适配",
    "phone": "手机适配",
    "responsive": "响应式适配",
    "0.0.0.0": "局域网监听地址",
    "super": "完全控制权限",
    "approval": "只读权限",
    "autonomous": "管理权限",
    "review": "复核",
    "read-only": "只读",
    "subagent": "子工匠",
    "agent": "工匠代理",
    "agents": "工匠代理",
    "agente": "工匠代理",
    "skill": "技能",
    "skills": "技能",
    "find-skills": "技能查找器",
    "skill-creator": "技能创建器",
    "catalog": "官籍目录",
    "catalog map": "官籍图谱",
    "registry": "官籍",
    "registry refresh": "官籍刷新",
    "capability": "能力",
    "capability registry": "能力官籍",
    "standing agents": "常驻工匠代理",
    "scripts": "脚本",
    "script": "脚本",
    "shiguan": "史馆",
    "web": "网页",
    "web entry": "网页入口",
    "state": "状态",
    "directory": "目录",
    "court directory": "朝廷目录",
    "startup prerequisites": "启动前置条件",
    "prerequisites": "前置条件",
    "readable": "可读取",
    "confirmed": "已确认",
    "caveat": "余限",
    "caveats": "余限",
    "fresh": "新的",
    "performed": "已执行",
    "not performed": "未执行",
    "no fresh registry refresh": "未执行新的官籍刷新",
    "sandbox": "沙盒",
    "yolo": "无沙盒直行",
    "yolo autostart": "无沙盒自启",
    "no-sandbox autostart": "无沙盒自启",
    "startup task draft": "自启任务草案",
    "startup task": "开机自启任务",
    "windows task scheduler": "Windows 计划任务",
    "codexyolostartup": "Codex 无沙盒自启任务",
    "ensure_codex_yolo_startup_task": "Codex 无沙盒自启检查脚本",
    "dangerously-bypass-approvals-and-sandbox": "无沙盒无审批启动参数",
    "codex --dangerously-bypass-approvals-and-sandbox": "Codex 无沙盒无审批启动命令",
    "package": "安装包",
    "index": "索引",
    "graph": "图谱",
    "knowledge graph": "知识图谱",
}

LAYER_CODES = {
    "史馆": "S",
    "朝廷": "C",
    "朝制": "C",
    "制度": "D",
    "官署": "G",
    "三省": "S",
    "六部": "L",
    "权限": "P",
    "史馆记忆": "M",
    "记忆": "M",
    "能力": "A",
    "图谱": "A",
    "招聘": "R",
    "官籍": "R",
    "网页": "W",
    "星图": "X",
    "树图": "T",
    "索引": "I",
    "安装包": "Z",
}

CAPABILITY_DEPARTMENT_RULES = [
    ("太子", ["太子", "taizi", "router", "synthesis"]),
    ("中书省", ["中书", "zhongshu", "draft", "intent", "decomposition", "research"]),
    ("门下省", ["门下", "menxia", "review", "privacy", "safety", "gate", "封驳", "复核"]),
    ("尚书省", ["尚书", "shangshu", "dispatch", "sequencing", "分派"]),
    ("吏部", ["吏部", "libu-hr", "registry", "capability", "官籍", "铨选", "skill"]),
    ("户部", ["户部", "hubu", "resource", "config", "version", "path", "依赖", "资源"]),
    ("礼部", ["礼部", "libu", "documentation", "report", "readme", "style", "文档"]),
    ("兵部", ["兵部", "bingbu", "runtime", "operation", "incident", "migration", "并发"]),
    ("刑部", ["刑部", "xingbu", "security", "privacy", "redact", "destructive", "安全", "隐私"]),
    ("工部", ["工部", "gongbu", "implementation", "build", "test", "script", "工程", "实现"]),
    ("史馆", ["史馆", "shiguan", "archive", "index", "graph", "lineage", "memory", "实录", "索引"]),
]

CAPABILITY_KIND_RULES = [
    ("skill", ["skill", "skills", "技能", "SKILL.md"]),
    ("script", ["script", "scripts", ".py", "脚本"]),
    ("agent", ["agent", "agents", "agente", "subagent", ".toml", "代理"]),
    ("mcp", ["mcp", "MCP"]),
    ("cli", ["cli", "command", "powershell", "python ", "命令"]),
    ("memory", ["memory", "memories", "记忆", "MEMORY.md", "USER.md"]),
    ("shiguan", ["shiguan", "史馆", "archive_checkpoint", "query_shiguan_index"]),
    ("lineage-index", ["lineage", "古制谱系", "court_code", "诏令编号", "索引"]),
    ("capability-vector", ["vector", "embedding", "向量", "能力谱系"]),
    ("conversation", ["conversation", "transcript", "session", "对话", "会话"]),
    ("bridge", ["bridge", "桥接", "接入"]),
]

CAPABILITY_TOOL_TERMS = [
    "archive_checkpoint.py",
    "query_shiguan_index.py",
    "rebuild_shiguan_index.py",
    "grow_shiguan_tree.py",
    "build_shiguan_knowledge_graph.py",
    "internal_memory_shiguan_bridge.py",
    "check_catalog.py",
    "refresh_capability_registry.py",
    "ensure_court_agent_config.py",
    "memory_decision.py",
    "court-capability-router",
    "codex",
    "hermes",
]

CONTENT_TAXONOMY = [
    (
        "朝制",
        "文书",
        "诏令",
        "拟旨格式",
        "行为分流",
        [
            "圣旨",
            "诏书",
            "敕书",
            "诏令",
            "诏令谱系",
            "格式依据",
            "执行行为类",
            "诏令行为",
            "行为分流",
            "内阁票拟",
            "奉天承运",
            "敕谕",
            "敕命",
            "谕旨",
            "上谕",
            "imperial edict",
            "edict_lineage",
            "edict_action_class",
            "edict_format_basis",
        ],
    ),
    (
        "朝制",
        "官署",
        "三省六部",
        "问策会审",
        "历史初判",
        [
            "历史线索初判",
            "意图初判",
            "历史记忆线索",
            "三省具体会审",
            "太子整理回奏",
            "细节追问",
            "待问细节",
            "递归澄清",
            "回问轮次",
            "三省复议",
            "逐轮回奏",
            "逐一提问",
            "超过两问",
            "具体细节",
            "问策",
            "澄清转问",
            "intent inference",
            "historical clue judgment",
            "three departments discussion",
            "concrete deliberation",
            "taizi synthesis",
            "detail questions",
            "blocking detail question",
            "clarification is recursive",
            "clarification round",
            "fresh discussion",
            "pre-drafted backlog",
            "one question at a time",
        ],
    ),
    (
        "朝制",
        "官署",
        "三省六部",
        "政令流转",
        "上奏回奏",
        [
            "太子",
            "三省",
            "六部",
            "门下",
            "中书",
            "尚书",
            "上奏",
            "回奏",
            "court",
            "dispatch",
        ],
    ),
    (
        "朝制",
        "权柄",
        "三权",
        "沙盒边界",
        "权限分级",
        [
            "approval",
            "autonomous",
            "super",
            "sandbox",
            "yolo autostart",
            "no-sandbox autostart",
            "startup task draft",
            "startup task",
            "windows task scheduler",
            "CodexYoloStartup",
            "ensure_codex_yolo_startup_task",
            "dangerously-bypass-approvals-and-sandbox",
            "codex --dangerously-bypass-approvals-and-sandbox",
            "开机自启",
            "计划任务",
            "自启任务",
            "自启草案",
            "无沙盒自启",
            "无沙盒无审批",
            "显式确认",
            "权限",
            "只读",
            "管理",
            "完全控制",
        ],
    ),
    (
        "官制",
        "官籍",
        "铨选",
        "工坊招聘",
        "能力任用",
        [
            "招聘",
            "官籍",
            "铨选",
            "find-skills",
            "skill-creator",
            "agent",
            "agente",
            "skill",
            "MCP",
            "CLI",
        ],
    ),
    (
        "典藏",
        "史馆",
        "实录",
        "生长树",
        "索引检索",
        [
            "史馆",
            "记忆",
            "实录",
            "索引",
            "生长树",
            "Obsidian",
            "memory",
            "archive",
            "index",
            "keyword",
        ],
    ),
    (
        "工艺",
        "界面",
        "图谱",
        "后台服务",
        "服务自启",
        [
            "史馆图谱服务",
            "史馆网页服务",
            "默认后台开启",
            "后台确保",
            "局域网",
            "局域网入口",
            "局域网可访问",
            "局域网监听",
            "本机入口",
            "手机适配",
            "平板适配",
            "响应式适配",
            "移动端",
            "触控布局",
            "0.0.0.0",
            "lan",
            "lan urls",
            "lan-reachable",
            "local url",
            "mobile",
            "phone",
            "tablet",
            "responsive",
            "端口占用",
            "ensure_shiguan_web",
            "serve_shiguan_tree",
            "background service",
            "127.0.0.1:8765",
            "8765",
        ],
    ),
    (
        "工艺",
        "界面",
        "图谱",
        "星树视图",
        "交互营造",
        [
            "网页",
            "前端",
            "星图",
            "树图",
            "缩放",
            "右键",
            "MC百科",
            "web",
            "graph",
            "app.js",
            "styles.css",
        ],
    ),
    (
        "工艺",
        "安装",
        "包验",
        "分发载入",
        "安装包",
        [
            "安装包",
            "zip",
            "打包",
            "校验",
            "quick_validate",
            "export",
            "package",
        ],
    ),
    (
        "器用",
        "能力",
        "图谱",
        "差遣考课",
        "能力调度",
        [
            "能力",
            "图谱",
            "差遣",
            "考课",
            "catalog",
            "capability",
            "registry",
            "router",
        ],
    ),
]

TAXONOMY_VERSION = "2026-08-28.beta1.0.8"
CONTENT_TAXONOMY_VERSION = TAXONOMY_VERSION
CONTENT_TAXONOMY_MIN_SCORE = 2
CONTENT_LINEAGE_FIELDS = ("root", "zhi", "men", "gang", "mu", "tiao", "zhao")
CONTENT_NEGATION_MARKERS = (
    "不涉及",
    "不包括",
    "不属于",
    "不包含",
    "不含",
    "并非",
    "不是",
    "无关",
    "无需",
    "没有",
    "排除",
    "否定",
    "does not involve",
    "doesn't involve",
    "not related to",
    "unrelated to",
    "without",
    "exclude",
    "excluded",
    "excluding",
)
CONTENT_NEGATION_RESETS = ("但是", "但", "而是", "不过", "however", "but", "instead")
CONTENT_LINEAGE_DISPLAY_RE = re.compile(
    r"^(?P<root>.+?)·(?P<zhi>.+?)志·(?P<men>.+?)门·(?P<gang>.+?)纲·"
    r"(?P<mu>.+?)目·(?P<tiao>.+?)条·(?P<zhao>.+?)诏$"
)

LINEAGE_CODE_OVERRIDES = {
    "史馆总纪": "S",
    "朝制": "C",
    "官制": "G",
    "典藏": "D",
    "工艺": "W",
    "器用": "Q",
    "文书": "D",
    "官署": "O",
    "权柄": "P",
    "官籍": "R",
    "史馆": "M",
    "界面": "I",
    "安装": "Z",
    "能力": "A",
    "三省六部": "S",
    "诏令": "ZL",
    "三权": "P",
    "铨选": "R",
    "实录": "L",
    "图谱": "GP",
    "包验": "Z",
    "问策会审": "Q",
    "历史初判": "H",
    "拟旨格式": "YZ",
    "行为分流": "XF",
    "政令流转": "ZL",
    "上奏回奏": "SZ",
    "沙盒边界": "SH",
    "权限分级": "QX",
    "工坊招聘": "GF",
    "能力任用": "NY",
    "生长树": "T",
    "索引检索": "I",
    "后台服务": "BF",
    "服务自启": "FZ",
    "星树视图": "ST",
    "交互营造": "J",
    "分发载入": "F",
    "安装包": "ZB",
    "差遣考课": "CK",
    "能力调度": "ND",
    "项目": "P",
    "本务": "B",
    "未命名": "U0",
}

PHASE_EN = {
    "太子定性": "Taizi intake",
    "三省会审": "three-department review",
    "三省上奏": "three departments petition",
    "太子回奏": "Taizi memorial",
    "太子整理回奏": "Taizi synthesis",
    "细节追问": "detail questions",
    "递归澄清": "recursive clarification",
    "回问轮次": "clarification round",
    "三省复议": "three departments renewed review",
    "逐轮回奏": "round-by-round memorial",
    "逐一提问": "one question at a time",
    "历史线索初判": "historical clue judgment",
    "意图初判": "intent inference",
    "史馆图谱服务": "Shiguan web service",
    "尚书分派": "Shangshu dispatch",
    "六部执行": "six ministries execution",
    "六部并行办差": "six ministries parallel work",
    "门下封驳": "Menxia review",
    "门下复核": "Menxia final review",
    "记忆裁定": "memory decision",
    "启动能力分类": "startup capability classification",
    "手动修订": "manual edit",
}

PHASE_STAGE_RULES = [
    ("受旨定性", ("太子定性", "启动", "归档加载", "历史线索初判", "意图初判")),
    ("拟旨考据", ("中书", "拟旨", "考据", "请太子转问", "澄清", "澄清转问", "细节追问", "递归澄清", "逐一提问")),
    ("三省会审", ("三省", "上奏", "会审", "太子回奏", "太子整理回奏", "门下封驳", "三省具体会审", "三省复议", "回问轮次", "具体细节")),
    ("尚书分派", ("尚书", "分派", "调度")),
    ("六部营造", ("六部", "工部", "兵部", "户部", "吏部", "刑部", "礼部", "执行", "营造", "办差")),
    ("门下复核", ("门下复核", "复核", "验收")),
    ("史馆实录", ("史馆", "实录", "记忆裁定", "奏报归档")),
]

STATUS_ZH = {
    "DONE": "已完成",
    "DONE_WITH_CONCERNS": "已完成但有余险",
    "APPROVED": "已准",
    "APPROVED_WITH_CAVEATS": "有条件批准",
    "REJECTED": "驳回",
    "BLOCKED": "受阻",
    "PROPOSE": "候选",
    "WRITE": "写入",
    "SKIP": "跳过",
    "DEFERRED": "暂缓",
    "DRAFT": "草稿",
}

STATUS_CODE = {
    "DONE": "D",
    "DONE_WITH_CONCERNS": "W",
    "APPROVED": "A",
    "APPROVED_WITH_CAVEATS": "V",
    "REJECTED": "R",
    "BLOCKED": "B",
    "PROPOSE": "P",
    "WRITE": "W",
    "SKIP": "S",
    "DEFERRED": "F",
    "DRAFT": "N",
}

EDICT_CONTEXT_TERMS = (
    "圣旨",
    "诏书",
    "敕书",
    "诏令",
    "敕谕",
    "敕命",
    "谕旨",
    "上谕",
    "内阁票拟",
    "奉天承运",
    "imperial edict",
    "edict",
)

EDICT_ACTION_RULES = [
    (
        "公开颁布",
        "诏",
        ("公开", "布告", "颁布", "大赦", "登基", "即位", "改元", "重大政令", "天下", "臣民"),
    ),
    (
        "任命授职",
        "敕命/敕书",
        ("任命", "授官", "授职", "除授", "差遣", "派任", "升迁", "官职", "任官"),
    ),
    (
        "封赠褒赏",
        "诰敕/敕命",
        ("封赠", "封爵", "褒奖", "褒赏", "赏赐", "恩赏", "赐", "功劳", "嘉奖"),
    ),
    (
        "戒饬禁令",
        "敕谕/谕旨",
        ("戒饬", "申饬", "禁令", "禁止", "责令", "训诫", "惩戒", "处分", "严禁"),
    ),
    (
        "行政指令",
        "谕旨/上谕/敕谕",
        ("办理", "奉行", "催办", "遵行", "传宣", "政务", "行政"),
    ),
    (
        "军机密令",
        "廷寄/密谕/谕旨",
        ("军机", "廷寄", "密谕", "密令", "调兵", "征讨", "军务", "急递", "机密"),
    ),
    (
        "礼制仪典",
        "册/诰/敕",
        ("册封", "册立", "典礼", "礼制", "仪典", "祭祀", "婚丧", "朝贺"),
    ),
]

RISK_LEVEL_ZH = {
    "S": "极高风险：可能造成不可逆破坏、泄密、付费或越权外部状态变更。",
    "A": "高风险：影响范围大、回滚困难或需要明确审计。",
    "B": "较高风险：会改动持久配置、索引、安装包或多文件行为。",
    "C": "中风险：局部可回滚改动，需常规验证。",
    "D": "低风险：小范围文本、样式、检索或只读派生物改动。",
    "E": "极低风险：纯说明、只读查询或临时输出。",
    "F": "无实质风险：无写入、无外部影响的记录性动作。",
}

VALUE_LEVEL_ZH = {
    "S": "核心价值：会长期影响三省六部制度、史馆结构或能力调度。",
    "A": "高价值：后续高频复用，适合进入默认召回。",
    "B": "较高价值：对同类任务明显有用。",
    "C": "中价值：对当前项目有用，跨任务价值有限。",
    "D": "低价值：主要是一次性过程证据。",
    "E": "极低价值：仅排查或临时上下文。",
    "F": "无长期价值：不建议召回。",
}

PRIORITY_LEVEL_ZH = {
    "S": "最高优先级：阻断核心流程或安全边界。",
    "A": "高优先级：应尽快处理，影响默认体验或交付。",
    "B": "较高优先级：排入近期改造。",
    "C": "中优先级：按需处理。",
    "D": "低优先级：可延后。",
    "E": "很低优先级：仅有余力时处理。",
    "F": "不排期：只保留记录。",
}


def truncate(value: object, limit: int = 140) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def has_chinese(value: object) -> bool:
    return bool(CHINESE_RE.search(str(value or "")))


def has_english(value: object) -> bool:
    return bool(ENGLISH_RE.search(str(value or "")))


def chinese_only_terms(values: object, limit: int = 24) -> list[str]:
    source = values if isinstance(values, list) else [values]
    return unique([str(value).strip() for value in source if has_chinese(value) and not has_english(value)], limit)


def chinese_display_fragment(value: object, limit: int = 80) -> str:
    text = str(value or "").strip()
    if not has_chinese(text):
        return ""
    text = re.sub(r"[A-Za-z][A-Za-z0-9_.\\/-]*", "", text)
    text = re.sub(r"[`'\"<>()[\]{}]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ；;，,：:-_|")
    return truncate(text, limit) if has_chinese(text) else ""


def translate_english_summary(value: object, limit: int = 120) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if not has_english(text):
        return ""
    lower = text.lower()
    if "menxia" in lower and "read-only" in lower and "startup prerequisites" in lower:
        return truncate(
            "门下只读子工匠已核验启动前置条件：朝廷工作目录、技能查找器、技能创建器、能力目录地图、常驻工匠、脚本、史馆状态与网页入口均可读取；余限为本次只读复核未刷新能力官籍。",
            limit,
        )
    phrases: list[str] = []
    for term in sorted(ENGLISH_TERM_ZH, key=len, reverse=True):
        if term in lower:
            phrases.append(ENGLISH_TERM_ZH[term])

    if "confirmed" in lower and "prerequisites" in lower:
        prefix = "已确认启动前置条件"
    elif "no fresh registry refresh" in lower or ("registry refresh" in lower and "no " in lower):
        prefix = "未执行新的官籍刷新"
    elif "readable" in lower:
        prefix = "已确认相关目录与入口可读取"
    elif phrases:
        prefix = "源摘要涉及"
    else:
        prefix = ""

    if "caveat" in lower and ("registry refresh" in lower or "refresh" in lower):
        suffix = "；余限为尚未执行新的官籍刷新"
    elif "caveat" in lower:
        suffix = "；仍有余限需复核"
    else:
        suffix = ""

    details = "、".join(unique(phrases, 12))
    if details and prefix:
        return truncate(f"{prefix}：{details}{suffix}。", limit)
    if prefix:
        return truncate(f"{prefix}{suffix}。", limit)
    return truncate("源摘要为英文；原文保留在源字段，展示摘要按阶段、状态和内容谱系生成。", limit)


def translated_english_terms(*values: object, limit: int = 16) -> list[str]:
    lower = "\n".join(str(value or "") for value in values).lower()
    terms = [
        ENGLISH_TERM_ZH[term]
        for term in sorted(ENGLISH_TERM_ZH, key=len, reverse=True)
        if term in lower
    ]
    return unique(terms, limit)


def translated_topic_label(entry: dict[str, object], limit: int = 18) -> str:
    direct = chinese_display_fragment(entry.get("topic"), limit)
    if direct:
        return direct
    text = " ".join(str(entry.get(key) or "") for key in ("topic", "summary", "memory_content")).lower()
    if "menxia" in text and "read-only" in text:
        return truncate("门下只读复核", limit)
    if "menxia" in text and "startup" in text:
        return truncate("朝廷启动门下复核", limit)
    if "startup" in text and "super" in text:
        return truncate("启动完全控制权限", limit)
    terms = translated_english_terms(text, limit=5)
    if terms:
        return truncate("".join(terms[:3]), limit)
    translated = translate_english_summary(text, limit).rstrip("。")
    return truncate(translated, limit) if translated else ""


def memory_decision_zh(value: object) -> str:
    text = str(value or "").strip().upper()
    return {
        "WRITE": "写入",
        "PROPOSE": "候选",
        "SKIP": "跳过",
        "DEFERRED": "暂缓",
    }.get(text, chinese_display_fragment(value, 24) or "未裁定")


def unique(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def base36(value: int) -> str:
    value = max(int(value), 0)
    if value == 0:
        return "0"
    digits: list[str] = []
    while value:
        value, remainder = divmod(value, 36)
        digits.append(BASE36_ALPHABET[remainder])
    return "".join(reversed(digits))


def stable_base36_code(material: str, length: int = 4) -> str:
    size = max(int(length), 1)
    value = zlib.crc32(material.encode("utf-8")) % (36**size)
    return base36(value).zfill(size)


def compact_base36_value(value: object, length: int = 4) -> str:
    text = re.sub(r"[^0-9A-Z]", "", str(value or "").upper())
    if len(text) >= length:
        return text[:length]
    return ""


def date_text(entry: dict[str, object]) -> str:
    match = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", str(entry.get("time") or ""))
    if match:
        return "".join(match.groups())
    match = re.search(r"(\d{8})", str(entry.get("source") or ""))
    if match:
        return match.group(1)
    return "00000000"


def daily_sequence(entry: dict[str, object]) -> str:
    for key in ("daily_sequence", "sequence", "day_sequence"):
        raw = entry.get(key)
        if isinstance(raw, int):
            return base36(raw)
        if isinstance(raw, str) and raw.strip():
            text = raw.strip().upper()
            if re.fullmatch(r"[0-9A-Z]+", text):
                return text
    material = "|".join(str(entry.get(key, "")) for key in ("source", "time", "topic", "phase", "summary"))
    control_sum = sum((index + 1) * ord(char) for index, char in enumerate(material))
    return base36(control_sum % (36 * 36 * 36))


def stable_entry_material(entry: dict[str, object]) -> str:
    parts = entry.get("lineage_parts")
    if isinstance(parts, dict):
        lineage = "|".join(str(parts.get(key, "")) for key in ("root", "zhi", "men", "gang", "mu", "tiao", "zhao"))
    else:
        lineage = ""
    return "|".join(
        str(entry.get(key, ""))
        for key in ("record_type", "source", "time", "topic", "phase", "status", "summary", "memory_content")
    ) + f"|{lineage}"


def kb_uid(entry: dict[str, object]) -> str:
    existing = compact_base36_value(entry.get("kb_uid"), 4) or compact_base36_value(entry.get("knowledge_base_uid"), 4)
    return existing or stable_base36_code(stable_entry_material(entry), 4)


def record_uid(entry: dict[str, object]) -> str:
    existing = compact_base36_value(entry.get("record_uid"), 8)
    return existing or stable_base36_code(stable_entry_material(entry), 8)


def level(value: object, default: str = "C") -> str:
    text = str(value or "").strip().upper()
    return text[0] if text and text[0] in "SABCDEF" else default


def status_letter(status: object) -> str:
    text = str(status or "UNKNOWN").strip().upper()
    return STATUS_CODE.get(text, text[:1] if text[:1] in "SABCDEF" else "U")


def infer_risk(entry: dict[str, object]) -> str:
    explicit = level(entry.get("risk_level"), "")
    if explicit:
        return explicit
    text = " ".join(str(entry.get(key) or "") for key in ("summary", "evidence", "next", "key_actions")).lower()
    if any(term in text for term in ("delete", "删除", "rm ", "泄密", "token", "secret", "付费", "不可逆")):
        return "A"
    if any(term in text for term in ("安装包", "zip", "配置", "agents.max_depth", "rebuild", "重建", "索引", "多文件")):
        return "B"
    if any(term in text for term in ("web", "网页", "脚本", "样式", "前端", "jsonl")):
        return "C"
    return "D"


def infer_value(entry: dict[str, object]) -> str:
    explicit = level(entry.get("knowledge_value"), "")
    if explicit:
        return explicit
    text = " ".join(str(entry.get(key) or "") for key in ("topic", "summary", "memory_content", "keywords")).lower()
    if any(
        term in text
        for term in (
            "史馆",
            "生长树",
            "能力图谱",
            "默认",
            "三省六部",
            "编号",
            "stable id",
            "skill",
            "历史线索初判",
            "意图初判",
            "三省具体会审",
            "太子整理回奏",
            "细节追问",
            "递归澄清",
            "回问轮次",
            "三省复议",
            "逐轮回奏",
            "史馆图谱服务",
        )
    ):
        return "A"
    if any(term in text for term in ("安装包", "网页", "索引", "agent", "检索")):
        return "B"
    return "C"


def infer_priority(entry: dict[str, object]) -> str:
    explicit = level(entry.get("priority_level"), "")
    if explicit:
        return explicit
    risk = infer_risk(entry)
    value = infer_value(entry)
    if risk in "SA" or value == "S":
        return "A"
    if risk == "B" or value == "A":
        return "A"
    if value == "B":
        return "B"
    return "C"


def layer_code(entry: dict[str, object]) -> str:
    return lineage_code(entry)


def ancient_lineage(entry: dict[str, object]) -> str:
    parts = entry.get("lineage_parts")
    if not isinstance(parts, dict):
        parts = content_lineage_parts(entry)
    return content_lineage_display(parts)


def enrich_court_code(entry: dict[str, object]) -> None:
    risk = infer_risk(entry)
    value = infer_value(entry)
    priority = infer_priority(entry)
    four_code = f"{status_letter(entry.get('status'))}{risk}{value}{priority}"
    existing_code = str(entry.get("court_code") or "").strip().upper()
    uid = kb_uid(entry)
    semantic_code = f"{layer_code(entry)}-{date_text(entry)}-{daily_sequence(entry)}-{four_code}"
    if re.fullmatch(r"[A-Z0-9]+-\d{8}-[0-9A-Z]+-[A-Z0-9]{4}", existing_code):
        stable_code = existing_code
        four_code = existing_code.rsplit("-", 1)[-1]
        risk = four_code[1] if len(four_code) > 1 and four_code[1] in "SABCDEF" else risk
        value = four_code[2] if len(four_code) > 2 and four_code[2] in "SABCDEF" else value
        priority = four_code[3] if len(four_code) > 3 and four_code[3] in "SABCDEF" else priority
    elif re.fullmatch(r"[A-Z0-9]+-\d{8}-[0-9A-Z]+-[A-Z0-9]{4,6}-[A-Z0-9]{4}", existing_code):
        # Historical evidence may already contain an experimental five-part code.
        # Preserve it if written, but do not emit this shape for future records.
        stable_code = existing_code
        pieces = existing_code.split("-")
        uid = pieces[-2]
        four_code = pieces[-1]
        risk = four_code[1] if len(four_code) > 1 and four_code[1] in "SABCDEF" else risk
        value = four_code[2] if len(four_code) > 2 and four_code[2] in "SABCDEF" else value
        priority = four_code[3] if len(four_code) > 3 and four_code[3] in "SABCDEF" else priority
    else:
        stable_code = semantic_code
    entry["court_code"] = stable_code
    entry.pop("court_code_v2", None)
    entry["kb_uid"] = uid
    entry["record_uid"] = record_uid(entry)
    entry["court_code_parts"] = {
        "lineage": layer_code(entry),
        "date": date_text(entry),
        "sequence": daily_sequence(entry),
        "status": four_code[0],
        "risk": risk,
        "knowledge_value": value,
        "priority": priority,
    }
    entry["court_code_legend"] = "诏令编号为：层级码串/日期/日内36进制序号/四字码；独立识别码另列为 kb_uid/record_uid/machine_uid，不进入诏令编号；四字码固定为状态/风险/知识库价值/优先级；状态是离散执行结论，不按等级量化。"
    entry["ancient_lineage"] = ancient_lineage(entry)
    entry["risk_level"] = risk
    entry["knowledge_value"] = value
    entry["priority_level"] = priority


def split_keywords(values: object) -> tuple[list[str], list[str]]:
    source = values if isinstance(values, list) else []
    zh: list[str] = []
    en: list[str] = []
    for item in source:
        text = str(item).strip()
        if not text:
            continue
        if has_chinese(text):
            zh.append(text)
        if has_english(text):
            en.append(text)
    return unique(zh, 12), unique(en, 12)


def chinese_terms_from_text(*values: object, limit: int = 24) -> list[str]:
    terms: list[str] = []
    for value in values:
        if isinstance(value, dict):
            terms.extend(str(item) for item in value.values())
            continue
        if isinstance(value, list):
            terms.extend(str(item) for item in value)
            continue
        terms.extend(TOKEN_RE.findall(str(value or "")))
    return unique([term for term in terms if has_chinese(term)], limit)


def derive_keywords_from_text(*values: object) -> list[str]:
    tokens: list[str] = []
    for value in values:
        tokens.extend(token.strip("`'\".,:()[]{}<>") for token in TOKEN_RE.findall(str(value or "")))
    return unique(tokens, 32)


def flattened_text(*values: object) -> str:
    output: list[str] = []
    for value in values:
        if isinstance(value, dict):
            output.extend(str(item) for item in value.values())
        elif isinstance(value, list):
            output.extend(str(item) for item in value)
        else:
            output.append(str(value or ""))
    return "\n".join(output)


def entry_search_text(entry: dict[str, object]) -> str:
    return flattened_text(
        entry.get("topic"),
        entry.get("phase"),
        entry.get("status"),
        entry.get("summary"),
        entry.get("evidence"),
        entry.get("next"),
        entry.get("memory_content"),
        entry.get("memory_reason"),
        entry.get("keywords"),
        entry.get("key_actions"),
        entry.get("keywords_zh"),
        entry.get("keywords_en"),
        entry.get("source"),
        entry.get("lineage_display"),
        entry.get("ancient_lineage"),
        entry.get("court_code"),
    )


def match_capability_terms(text: str, rules: list[tuple[str, list[str]]], limit: int = 12) -> list[str]:
    lowered = text.lower()
    values: list[str] = []
    for label, needles in rules:
        if any(needle.lower() in lowered for needle in needles):
            values.append(label)
    return unique(values, limit)


def extract_source_paths(entry: dict[str, object], limit: int = 16) -> list[str]:
    text = entry_search_text(entry)
    values: list[str] = []
    source = str(entry.get("source") or "").strip()
    if source:
        values.append(source)
    for match in PATH_RE.findall(text):
        cleaned = match.strip("`'\"<>()[]{}。，；;,")
        if cleaned and len(cleaned) > 2 and SOURCE_PATH_HINT_RE.search(cleaned):
            values.append(cleaned)
    return unique(values, limit)


def capability_tool_terms(text: str, limit: int = 16) -> list[str]:
    lowered = text.lower()
    values = [term for term in CAPABILITY_TOOL_TERMS if term.lower() in lowered]
    for token in TOKEN_RE.findall(text):
        if token.endswith(".py") or token.endswith(".toml") or token.endswith("SKILL.md"):
            values.append(token)
    return unique(values, limit)


def list_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [str(item) for item in value.values() if str(item).strip()]
    if value:
        return [str(value)]
    return []


def bucketed_sparse_vector(terms: list[str], dimensions: int = 64) -> list[dict[str, object]]:
    buckets: dict[int, float] = {}
    for term in terms:
        normalized = str(term or "").strip().lower()
        if not normalized:
            continue
        index = zlib.crc32(normalized.encode("utf-8", errors="ignore")) % dimensions
        buckets[index] = buckets.get(index, 0.0) + 1.0
    return [{"i": index, "w": round(weight, 3)} for index, weight in sorted(buckets.items())]


def capability_vector_fields(entry: dict[str, object]) -> dict[str, object]:
    parts = entry.get("lineage_parts")
    if not isinstance(parts, dict):
        parts = content_lineage_parts(entry)
    lineage_values = [str(parts.get(key, "")) for key in ("root", "zhi", "men", "gang", "mu", "tiao", "zhao")]
    text = entry_search_text(entry)
    departments = match_capability_terms(text, CAPABILITY_DEPARTMENT_RULES, 12)
    capability_kinds = match_capability_terms(text, CAPABILITY_KIND_RULES, 12)
    tools = capability_tool_terms(text, 16)
    source_paths = extract_source_paths(entry, 16)
    keywords = [
        str(item)
        for item in (
            list_values(entry.get("keywords"))
            + list_values(entry.get("keywords_zh"))
            + list_values(entry.get("keywords_en"))
            + list_values(entry.get("key_actions"))
        )
        if str(item).strip()
    ]
    vector_terms = unique(
        [
            *lineage_values,
            *departments,
            *capability_kinds,
            *tools,
            *keywords,
            str(entry.get("court_code") or ""),
            str(entry.get("lineage_key") or ""),
        ],
        64,
    )
    weighted_terms = [
        *lineage_values,
        *lineage_values,
        *departments,
        *departments,
        *departments,
        *capability_kinds,
        *capability_kinds,
        *tools,
        *keywords,
        str(entry.get("court_code") or ""),
    ]
    vector_text = " | ".join(
        part
        for part in [
            "能力谱系向量",
            "部门=" + ",".join(departments),
            "能力类型=" + ",".join(capability_kinds),
            "工具=" + ",".join(tools),
            "古制谱系=" + " > ".join(value for value in lineage_values if value),
            "诏令编号=" + str(entry.get("court_code") or ""),
            "关键词=" + ",".join(keywords[:24]),
            "路径=" + ",".join(source_paths[:8]),
        ]
        if part and not part.endswith("=")
    )
    return {
        "capability_vector_schema": "court.capability_lineage_vector.v1",
        "capability_vector_kind": "capability_lineage",
        "capability_lineage": {
            "departments": departments,
            "capability_kinds": capability_kinds,
            "tools": tools,
            "lineage": lineage_values,
        },
        "capability_source_paths": source_paths,
        "capability_vector_terms": vector_terms,
        "capability_vector_text": vector_text,
        "capability_vector_sparse": bucketed_sparse_vector(weighted_terms),
        "vector_text": vector_text,
        "embedding_text": vector_text,
    }


def lineage_text(entry: dict[str, object]) -> str:
    values: list[str] = []
    for key in (
        "topic",
        "summary",
        "evidence",
        "next",
        "memory_content",
        "keywords",
        "keywords_zh",
        "keywords_en",
    ):
        value = entry.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value or ""))
    return "\n".join(values)


def _taxonomy_match_is_negated(haystack: str, start: int) -> bool:
    clause_start = max(
        (haystack.rfind(marker, 0, start) for marker in ("\n", "。", "！", "？", ";", "；", "!", "?")),
        default=-1,
    )
    prefix = haystack[clause_start + 1 : start][-80:]
    reset_positions = [
        (prefix.rfind(marker), len(marker))
        for marker in CONTENT_NEGATION_RESETS
        if marker in prefix
    ]
    if reset_positions:
        reset_at, reset_length = max(reset_positions)
        prefix = prefix[reset_at + reset_length :]
    return any(marker in prefix for marker in CONTENT_NEGATION_MARKERS)


def _taxonomy_term_evidence(haystack: str, needle: object) -> tuple[bool, bool]:
    term = str(needle or "").strip().lower()
    if not term:
        return False, False
    positive = False
    negated = False
    for match in re.finditer(re.escape(term), haystack):
        if _taxonomy_match_is_negated(haystack, match.start()):
            negated = True
        else:
            positive = True
    return positive, negated


def _distinct_taxonomy_terms(values: list[str]) -> list[str]:
    terms = unique(values, len(values))
    return [
        term
        for term in terms
        if not any(
            term.casefold() != other.casefold()
            and term.casefold() in other.casefold()
            for other in terms
        )
    ]


def _taxonomy_candidate_scores(haystack: str) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for zhi, men, gang, mu, tiao, needles in CONTENT_TAXONOMY:
        positive_terms: list[str] = []
        negated_terms: list[str] = []
        for needle in needles:
            positive, negated = _taxonomy_term_evidence(haystack, needle)
            if positive:
                positive_terms.append(str(needle))
            if negated:
                negated_terms.append(str(needle))
        positive_terms = _distinct_taxonomy_terms(positive_terms)
        negated_terms = _distinct_taxonomy_terms(negated_terms)
        candidates.append(
            {
                "parts": (zhi, men, gang, mu, tiao),
                "path": "/".join((zhi, men, gang, mu, tiao)),
                "score": len(positive_terms),
                "negated_score": len(negated_terms),
                "evidence": positive_terms,
                "negated_evidence": negated_terms,
            }
        )
    return sorted(
        candidates,
        key=lambda item: (-int(item["score"]), str(item["path"])),
    )


def _lineage_zhao(entry: dict[str, object]) -> str:
    return (
        translated_topic_label(entry, 18)
        or chinese_display_fragment(
            entry.get("summary") or entry.get("memory_content"),
            18,
        )
        or "未命名"
    )


def content_lineage_parts(entry: dict[str, object]) -> dict[str, object]:
    haystack = lineage_text(entry).lower()
    candidates = _taxonomy_candidate_scores(haystack)
    best = candidates[0]
    top_score = int(best["score"])
    second_score = int(candidates[1]["score"]) if len(candidates) > 1 else 0
    margin = max(top_score - second_score, 0)
    tied = top_score > 0 and sum(
        1 for candidate in candidates if candidate["score"] == top_score
    ) > 1
    negated_evidence = unique(
        [
            str(term)
            for candidate in candidates
            for term in candidate["negated_evidence"]
        ],
        24,
    )
    confidence = (
        round(top_score / (top_score + second_score + 1), 3)
        if top_score > 0
        else 0.0
    )

    if top_score == 0:
        reason = "negated_evidence" if negated_evidence else "unknown"
    elif int(best["negated_score"]) > 0:
        reason = "conflict"
    elif tied:
        reason = "tie"
    elif top_score < CONTENT_TAXONOMY_MIN_SCORE:
        reason = "low_confidence"
    else:
        reason = "matched"
    status = "classified" if reason == "matched" else "review"
    if status == "classified":
        zhi, men, gang, mu, tiao = best["parts"]
    else:
        zhi, men, gang, mu, tiao = ("待审",) * 5

    candidate_scores = [
        {
            "path": candidate["path"],
            "score": candidate["score"],
            "negated_score": candidate["negated_score"],
        }
        for candidate in candidates
        if candidate["score"] or candidate["negated_score"]
    ][:8]
    return {
        "root": "史馆总纪",
        "zhi": zhi,
        "men": men,
        "gang": gang,
        "mu": mu,
        "tiao": tiao,
        "zhao": _lineage_zhao(entry),
        "taxonomy_version": CONTENT_TAXONOMY_VERSION,
        "classification_status": status,
        "classification_reason": reason,
        "classification_confidence": confidence,
        "classification_score": top_score,
        "classification_margin": margin,
        "classification_candidates": candidate_scores,
        "classification_evidence": list(best["evidence"]),
        "classification_negated_evidence": negated_evidence,
        "classification_negated_evidence_count": len(negated_evidence),
        "positive_evidence": list(best["evidence"]),
        "negative_evidence": negated_evidence,
        "candidates": candidate_scores,
    }


def parse_content_lineage_display(value: object) -> dict[str, str] | None:
    text = str(value or "").strip()
    match = CONTENT_LINEAGE_DISPLAY_RE.fullmatch(text)
    if match is None:
        return None
    parts = {field: match.group(field).strip() for field in CONTENT_LINEAGE_FIELDS}
    if any(not parts[field] for field in CONTENT_LINEAGE_FIELDS):
        return None
    return parts


def existing_content_lineage_parts(
    entry: dict[str, object],
) -> dict[str, object] | None:
    value = entry.get("lineage_parts")
    if not isinstance(value, dict):
        return None
    if any(not str(value.get(field) or "").strip() for field in CONTENT_LINEAGE_FIELDS):
        return None
    return dict(value)


def content_lineage_display(parts: dict[str, object]) -> str:
    return (
        f"{parts['root']}·{parts['zhi']}志·{parts['men']}门·{parts['gang']}纲·"
        f"{parts['mu']}目·{parts['tiao']}条·{parts['zhao']}诏"
    )


def content_lineage_key(parts: dict[str, object]) -> str:
    return "/".join(slug_part(parts[key]) for key in ("zhi", "men", "gang", "mu", "tiao"))


def source_kind(entry: dict[str, object]) -> str:
    source = str(entry.get("source") or "")
    if "plan-archives" in source:
        return "计划实录"
    if "memory-decisions" in source:
        return "记忆裁定"
    if "manual" in source:
        return "人工树叶"
    return str(entry.get("record_type") or "未明来源")


def phase_stage(entry: dict[str, object]) -> str:
    text = " ".join(
        str(entry.get(key) or "")
        for key in ("phase", "summary", "memory_content", "key_actions")
    )
    for stage, terms in PHASE_STAGE_RULES:
        if any(term in text for term in terms):
            return stage
    return str(entry.get("phase") or "未定")


def edict_action_facets(entry: dict[str, object]) -> list[str]:
    text = "\n".join(
        str(entry.get(key) or "")
        for key in (
            "topic",
            "phase",
            "summary",
            "evidence",
            "memory_content",
            "keywords",
            "key_actions",
            "edict_lineage",
            "edict_action_class",
            "edict_document_type",
            "edict_format_basis",
        )
    ).lower()
    explicit_action = chinese_display_fragment(entry.get("edict_action_class"), 40)
    explicit_type = chinese_display_fragment(entry.get("edict_document_type"), 40)
    explicit_lineage = chinese_display_fragment(entry.get("edict_lineage"), 40)
    has_edict_context = any(term.lower() in text for term in EDICT_CONTEXT_TERMS)
    values: list[str] = []

    if explicit_action:
        values.append(f"行为:{explicit_action}")
    if explicit_type:
        values.append(f"文种:{explicit_type}")
    if explicit_lineage:
        values.append(f"谱系:{explicit_lineage}")

    if has_edict_context or values:
        for behavior, document_types, terms in EDICT_ACTION_RULES:
            if any(term.lower() in text for term in terms):
                values.append(f"行为:{behavior}")
                values.append(f"文种候选:{document_types}")

    if has_edict_context and not values:
        values.extend(["行为:待定", "文种候选:待朱批"])

    return unique(values, 12)


def facet_dimensions(entry: dict[str, object]) -> dict[str, list[str]]:
    parts = entry.get("lineage_parts")
    if not isinstance(parts, dict):
        parts = content_lineage_parts(entry)
    values = {
        "内容谱系": [str(parts.get(key, "")) for key in ("zhi", "men", "gang", "mu", "tiao", "zhao")],
        "朝程分面": [phase_stage(entry)],
        "状态分面": [STATUS_ZH.get(str(entry.get("status") or "").upper(), str(entry.get("status") or ""))],
        "记忆分面": [str(entry.get("memory_decision") or "")],
        "评估分面": [
            f"风险:{level(entry.get('risk_level'), infer_risk(entry))}",
            f"价值:{level(entry.get('knowledge_value'), infer_value(entry))}",
            f"优先:{level(entry.get('priority_level'), infer_priority(entry))}",
        ],
        "来源分面": [
            str(entry.get("record_type") or ""),
            source_kind(entry),
        ],
        "时间分面": [date_text(entry)],
    }
    edict_facets = edict_action_facets(entry)
    if edict_facets:
        values["诏令行为谱系"] = edict_facets
    return {dimension: unique([value for value in items if value], 12) for dimension, items in values.items()}


def slug_part(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
    return text.strip("-")[:48] or "unclassified"


def lineage_code(entry: dict[str, object]) -> str:
    parts = entry.get("lineage_parts")
    if not isinstance(parts, dict):
        parts = content_lineage_parts(entry)
    codes: list[str] = []
    for key in ("root", "zhi", "men", "gang", "mu", "tiao", "zhao"):
        value = str(parts.get(key, ""))
        code = LINEAGE_CODE_OVERRIDES.get(value)
        if not code:
            code = "U" + stable_base36_code(value or key, 2)
        code = re.sub(r"[^A-Z0-9]", "", code.upper()) or ("U" + stable_base36_code(value or key, 2))
        codes.append(code)
    return "".join(codes[:7])


def build_keyword_summaries(entry: dict[str, object]) -> tuple[str, str]:
    topic = str(entry.get("topic") or "未命名")
    phase = chinese_display_fragment(entry.get("phase"), 24) or chinese_display_fragment(phase_stage(entry), 24) or "未分期"
    status = str(entry.get("status") or "UNKNOWN").upper()
    summary = truncate(entry.get("summary") or entry.get("memory_content") or entry.get("evidence"), 120)
    status_zh = STATUS_ZH.get(status, chinese_display_fragment(status, 24) or "未定")
    phase_en = PHASE_EN.get(phase, phase)
    parts = entry.get("lineage_parts")
    if not isinstance(parts, dict):
        parts = content_lineage_parts(entry)
    lineage_core = chinese_only_terms(
        [parts.get(key, "") for key in ("zhi", "men", "gang", "mu", "tiao")],
        5,
    )
    source = chinese_display_fragment(source_kind(entry), 24) or "未明来源"
    decision = memory_decision_zh(entry.get("memory_decision"))
    summary_zh = chinese_display_fragment(summary, 90) or translate_english_summary(summary, 110)

    zh_clauses = [
        f"阶段{phase}，状态{status_zh}",
        f"内容归类为{'、'.join(lineage_core) if lineage_core else '未分类'}",
        f"来源为{source}",
        f"记忆裁定为{decision}",
    ]
    if summary_zh:
        zh_clauses.append(f"要点：{summary_zh.rstrip('。；;')}")
    else:
        zh_clauses.append("原始说明保留在源字段")
    zh_summary = chinese_display_fragment("；".join(zh_clauses) + "。", 180)

    if has_english(summary):
        en_summary = f"{topic} | {phase_en} | {status}: {summary}"
    else:
        en_summary = f"{topic} | {phase_en} | {status}: Shiguan record with court evidence and memory status."

    return truncate(zh_summary, 180), truncate(en_summary, 180)


def enrich_entry(entry: dict[str, object]) -> dict[str, object]:
    keywords = entry.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        keywords = derive_keywords_from_text(
            entry.get("topic"),
            entry.get("phase"),
            entry.get("status"),
            entry.get("summary"),
            entry.get("evidence"),
            entry.get("memory_content"),
        )
        entry["keywords"] = keywords

    parts = existing_content_lineage_parts(entry) or content_lineage_parts(entry)
    lineage_values = [parts.get(key, "") for key in ("zhi", "men", "gang", "mu", "tiao", "zhao")]
    keywords_zh, keywords_en = split_keywords(keywords)
    text_keywords_zh = chinese_terms_from_text(
        entry.get("topic"),
        entry.get("phase"),
        entry.get("summary"),
        entry.get("memory_content"),
        entry.get("memory_reason"),
        entry.get("next"),
        entry.get("evidence"),
        lineage_values,
    )
    translated_keywords_zh = translated_english_terms(
        entry.get("topic"),
        entry.get("summary"),
        entry.get("memory_content"),
        entry.get("evidence"),
        keywords,
        limit=18,
    )
    keywords_zh = chinese_only_terms(lineage_values + text_keywords_zh + translated_keywords_zh + keywords_zh, 18)
    if not keywords_zh:
        keywords_zh = chinese_only_terms(
            [
                *lineage_values,
                str(entry.get("phase") or ""),
                memory_decision_zh(entry.get("memory_decision")),
            ],
            12,
        )
    if not keywords_en:
        keywords_en = unique(
            [
                str(entry.get("topic") or ""),
                str(entry.get("status") or ""),
                str(entry.get("record_type") or ""),
            ],
            12,
        )

    entry["keywords_zh"] = keywords_zh
    entry["keywords_en"] = keywords_en
    zh_summary, en_summary = build_keyword_summaries(entry)
    entry["keyword_summary_zh"] = zh_summary
    entry["keyword_summary_en"] = en_summary
    entry["display_labels_zh"] = "关键词 摘要 理由"
    entry["display_keywords_zh"] = keywords_zh
    entry["display_summary_zh"] = zh_summary
    entry["display_reason_zh"] = chinese_display_fragment(
        entry.get("memory_reason") or entry.get("next"),
        120,
    ) or "未记录理由"
    entry["lineage_parts"] = parts
    entry["lineage_key"] = content_lineage_key(parts)
    entry["lineage_display"] = content_lineage_display(parts)
    enrich_court_code(entry)
    entry["facet_dimensions"] = facet_dimensions(entry)
    entry.update(capability_vector_fields(entry))
    return entry


def index_path() -> Path:
    from shiguan_paths import reference_path

    return reference_path("shiguan-index.jsonl")


def load_entries(path: Path | None = None) -> list[dict[str, object]]:
    source = path or index_path()
    if not source.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            enrich_entry(value)
            entries.append(value)
    return entries


RECALL_EXCLUDED_FIELDS = frozenset(
    (
        "source",
        "evidence",
        "next",
        "capability_source_paths",
        "court_code_legend",
    )
)
RECALL_MIN_SCORE = 1.0
RECALL_MIN_IDF = 0.4
RECALL_ASCII_TOKEN_MIN = 3


def _weighted_searchable_parts(
    entry: dict[str, object],
) -> list[tuple[int, str]]:
    """Weighted recall fields, excluding low-value provenance/legend fields (P0-3).

    ``source``/``evidence``/``next``/``capability_source_paths`` carry file paths
    that cause substring false positives (e.g. query "archive" matched every
    ``references/plan-archives/...`` path); ``court_code_legend`` is a static
    explanatory string. None of them participate in recall scoring.
    """
    weighted_parts: list[tuple[int, str]] = []
    for key in (
        "topic",
        "phase",
        "status",
        "court_code",
        "ancient_lineage",
        "lineage_display",
        "lineage_key",
    ):
        value = entry.get(key)
        if isinstance(value, str):
            weighted_parts.append((4, value))
    lineage_parts = entry.get("lineage_parts")
    if isinstance(lineage_parts, dict):
        weighted_parts.extend((4, str(value)) for value in lineage_parts.values())
    facets = entry.get("facet_dimensions")
    if isinstance(facets, dict):
        for values in facets.values():
            if isinstance(values, list):
                weighted_parts.extend((4, str(value)) for value in values)
            else:
                weighted_parts.append((4, str(values)))
    parts = entry.get("court_code_parts")
    if isinstance(parts, dict):
        weighted_parts.extend((4, str(value)) for value in parts.values())
    for key in ("keywords", "key_actions"):
        value = entry.get(key)
        if isinstance(value, list):
            weighted_parts.extend((5, str(item)) for item in value)
    for key in ("capability_vector_terms",):
        value = entry.get(key)
        if isinstance(value, list):
            weighted_parts.extend((6, str(item)) for item in value)
    capability_lineage = entry.get("capability_lineage")
    if isinstance(capability_lineage, dict):
        for value in capability_lineage.values():
            if isinstance(value, list):
                weighted_parts.extend((6, str(item)) for item in value)
            else:
                weighted_parts.append((6, str(value)))
    for key in (
        "capability_vector_text",
        "vector_text",
        "embedding_text",
        "capability_vector_kind",
    ):
        value = entry.get(key)
        if isinstance(value, str):
            weighted_parts.append((5, value))
    for key in (
        "summary",
        "memory_content",
        "memory_reason",
        "display_labels_zh",
        "display_summary_zh",
        "display_reason_zh",
    ):
        value = entry.get(key)
        if isinstance(value, str):
            weighted_parts.append((2, value))
    for key in ("keyword_summary_zh", "keyword_summary_en"):
        value = entry.get(key)
        if isinstance(value, str):
            weighted_parts.append((4, value))
    for key in ("keywords_zh", "keywords_en"):
        value = entry.get(key)
        if isinstance(value, list):
            weighted_parts.extend((5, str(item)) for item in value)
    return weighted_parts


def _recall_any_positive_occurrence(value: str, needle: str) -> bool:
    """True when at least one occurrence of needle is outside a negated clause.

    Reuses the taxonomy clause-negation detector (P0-1): a term that only
    appears inside a negated clause (e.g. "本次不涉及 archive 清理") contributes
    no recall score.
    """
    for match in re.finditer(re.escape(needle), value):
        if not _taxonomy_match_is_negated(value, match.start()):
            return True
    return False


def _recall_query_tokens(terms: list[object]) -> list[str]:
    """Normalize query terms into recall tokens (ASCII runs / CJK runs)."""
    tokens: list[str] = []
    for term in terms:
        for token in TOKEN_RE.findall(str(term or "")):
            lowered = token.casefold()
            if lowered and lowered not in tokens:
                tokens.append(lowered)
    return tokens


def _recall_ascii_token_matches(token: str, query: str) -> bool:
    """ASCII token equality or separator-boundary prefix match.

    ``archive`` matches ``archive`` and ``archive_checkpoint.py`` (boundary
    char ``_``) but never the inside of ``plan-archives`` (P0-2/P0-3).
    """
    if token == query:
        return True
    if len(query) >= RECALL_ASCII_TOKEN_MIN and token.startswith(query):
        return len(token) > len(query) and token[len(query)] in "._-\\/"
    return False


def _recall_value_occurrences(value: str, query: str) -> int:
    """Count non-negated occurrences of a recall token inside one field value."""
    lowered = value.casefold()
    count = 0
    if CHINESE_RE.search(query):
        for match in re.finditer(re.escape(query), lowered):
            if not _taxonomy_match_is_negated(lowered, match.start()):
                count += 1
        return count
    for match in TOKEN_RE.finditer(lowered):
        if _recall_ascii_token_matches(match.group(0), query):
            if not _taxonomy_match_is_negated(lowered, match.start()):
                count += 1
    return count


def _recall_value_presence(value: str, query: str) -> bool:
    """Presence (without negation) used for document-frequency counts."""
    if CHINESE_RE.search(query):
        return query in value
    lowered = value.casefold()
    return any(
        _recall_ascii_token_matches(match.group(0), query)
        for match in TOKEN_RE.finditer(lowered)
    )


def recall_idf(entries: list[dict[str, object]], terms: list[object]) -> dict[str, float]:
    """BM25-style IDF for the query tokens over the recall fields of ``entries``."""
    query_tokens = _recall_query_tokens(terms)
    total = len(entries)
    if not query_tokens or total == 0:
        return {}
    df = {token: 0 for token in query_tokens}
    for entry in entries:
        matched: set[str] = set()
        for _, value in _weighted_searchable_parts(entry):
            for token in query_tokens:
                if token not in matched and _recall_value_presence(value, token):
                    matched.add(token)
        for token in matched:
            df[token] += 1
    return {
        token: math.log((total - df[token] + 0.5) / (df[token] + 0.5) + 1.0)
        for token in query_tokens
    }


def score_entry_recall(
    entry: dict[str, object],
    terms: list[object],
    *,
    idf: dict[str, float] | None = None,
) -> float:
    """TF-IDF recall score for one entry (used by ``select_matches``)."""
    query_tokens = _recall_query_tokens(terms)
    if not query_tokens:
        return 0.0
    if idf is None:
        idf = {token: 1.0 for token in query_tokens}
    total = 0.0
    for weight, value in _weighted_searchable_parts(entry):
        for token in query_tokens:
            count = _recall_value_occurrences(value, token)
            if count:
                total += count * weight * idf.get(token, 0.0)
    return total


def _recall_matched_discriminative(
    entry: dict[str, object],
    query_tokens: list[str],
    idf: dict[str, float],
    min_idf: float,
) -> bool:
    """True when the entry matches at least one query token with IDF >= min_idf.

    A term present in (almost) every document (e.g. ``史馆`` inside every
    lineage/capability vector) cannot discriminate; admitting entries on such
    terms alone would keep full-corpus noise. Common/structural terms are the
    job of the structured lineage/court_code filters (P2-2), not the TF-IDF
    scorer.
    """
    for _, value in _weighted_searchable_parts(entry):
        for token in query_tokens:
            if idf.get(token, 0.0) < min_idf:
                continue
            if _recall_value_occurrences(value, token) > 0:
                return True
    return False


def score_entry(entry: dict[str, object], terms: list[str]) -> int:
    if not terms:
        return 0
    score = 0
    for weight, value in _weighted_searchable_parts(entry):
        lowered = value.casefold()
        for term in terms:
            needle = term.casefold()
            if needle and needle in lowered and _recall_any_positive_occurrence(lowered, needle):
                score += weight
    return score


def select_matches(entries: list[dict[str, object]], terms: list[str]) -> list[dict[str, object]]:
    """Rank entries by TF-IDF recall score with a minimum-score admission floor.

    Terms are tokenized; ASCII matches are exact/separator-boundary tokens, CJK
    runs match by substring; IDF is computed over the passed corpus; entries
    below ``RECALL_MIN_SCORE`` or that only match non-discriminative tokens
    (IDF < ``RECALL_MIN_IDF``) are dropped. Empty terms keep the latest-first
    (time descending) order for the explicit "latest N" semantics.
    """
    query_tokens = _recall_query_tokens(terms)
    if not query_tokens:
        return sorted(entries, key=lambda entry: str(entry.get("time", "")), reverse=True)
    idf = recall_idf(entries, terms)
    if not any(idf.get(token, 0.0) >= RECALL_MIN_IDF for token in query_tokens):
        # Non-discriminative query: every token is near-corpus-wide (e.g. 史馆
        # inside every lineage/capability vector). Text ranking would be
        # meaningless, so fall back to latest-first (time descending), matching
        # the explicit "latest N" semantics (P2-3 direction).
        return sorted(entries, key=lambda entry: str(entry.get("time", "")), reverse=True)
    scored = []
    for entry in entries:
        score = score_entry_recall(entry, terms, idf=idf)
        if score >= RECALL_MIN_SCORE and _recall_matched_discriminative(
            entry, query_tokens, idf, RECALL_MIN_IDF
        ):
            scored.append((score, entry))
    scored.sort(
        key=lambda item: (item[0], str(item[1].get("time", ""))),
        reverse=True,
    )
    return [entry for _, entry in scored]
