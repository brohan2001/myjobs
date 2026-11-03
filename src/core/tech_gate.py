"""Is a job title tech-adjacent? (DECISIONS D27)

The feed keeps tech jobs only; everything else is dropped before it's fetched or stored. A title is
tech when the occupation taxonomy maps it to a tech occupation. Titles the taxonomy doesn't know
fall back to keywords, leaning towards keeping: losing a real tech job is worse than storing an
extra one.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse

from src.core.occupation_resolve import match_occupation

TECH_DOMAINS = frozenset({"software-engineering", "data-ai", "infrastructure-security", "product-design"})

# Occupations outside the tech domains that the user counts as tech-adjacent (D27).
TECH_OCCUPATIONS = frozenset({
    # PM, TPM and engineering management
    "technical-program-manager", "project-manager", "engineering-manager", "tech-lead", "scrum-master",
    # Sales and support engineering
    "sales-engineer", "customer-engineer", "support-engineer",
    # Analysts
    "business-analyst",
    # Hardware and data centres
    "electrical-engineer", "mechanical-engineer", "automation-engineer",
    "data-center-technician", "data-center-manager",
})

_OCCUPATIONS_CSV = Path(__file__).resolve().parents[2] / "data" / "occupations.csv"

# Fallback for titles the taxonomy doesn't match. Word-bounded; matched on the lowercased title.
_TECH_WORDS = re.compile(
    r"\b("
    r"software|developer|programmer|engineer(?:ing)?|sde|swe|sdet|mts|devops|devsecops|sre|"
    r"full[- ]?stack|front[- ]?end|back[- ]?end|web|android|"
    # Bare "mobile" matched retail roles ("Mobile Associate - Retail Sales"); only mobile software counts.
    r"mobile (?:apps?|application|develop\w*|engineer\w*|software|platform|games?)|ios|flutter|react|java|python|golang|"
    r"\.net|node(?:\.?js)?|data|analytics|machine learning|ml|mlops|ai|artificial intelligence|llm|nlp|"
    r"computer vision|deep learning|scientist|research(?:er)?|cloud|platform|infrastructure|"
    r"security|cyber|network|database|dba|systems?|it|qa|quality assurance|test(?:ing)?|automation|"
    r"apps? develop\w*|applications? develop\w*|firmware|embedded|hardware|silicon|asic|fpga|vlsi|chip|semiconductor|robotics|"
    r"product|designer|design|ux|ui|architect|technical|technology|tech|digital|blockchain|"
    r"salesforce|sap|erp|crm|servicenow"
    r")\b"
)


@lru_cache(maxsize=1)
def tech_occupations() -> frozenset[str]:
    """Every occupation slug that counts as tech: the tech domains plus ``TECH_OCCUPATIONS``."""
    with _OCCUPATIONS_CSV.open(encoding="utf-8") as f:
        in_domains = {row["slug"] for row in csv.DictReader(f) if row["domain"] in TECH_DOMAINS}
    return frozenset(in_domains | TECH_OCCUPATIONS)


# Unambiguous tech words. They outrank a non-tech occupation match ("Consultant SAP PY",
# "Incident Response Sr. Consultant").
_STRONG_TECH_WORDS = re.compile(
    r"\b(software|developer|programmer|devops|sre|sap|salesforce|servicenow|cloud|cyber\w*|"
    r"incident response|penetration|machine learning|ml|ai|llm|algorithms?|data (?:scien\w*|engineer\w*))\b"
)


def _mostly_latin(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return not letters or sum(c.isascii() or "\u00c0" <= c <= "\u024f" for c in letters) / len(letters) >= 0.6


# Non-tech roles that outrank any tech word ("Cloud Account Executive", "Security Officer - Nights", "Retail Display
# Installer – Technology", "Business Development Manager", which the taxonomy reads as engineering-manager) unless the
# title also names a tech role (_TECH_ROLE). D42.
_NON_TECH_ROLE = re.compile(
    r"\b(sales|account executive|business development|marketing|partnerships?|telesales|call cent(?:er|re)|"
    r"customer (?:service|care)|relationship (?:officer|manager|executive)|recruit\w*|talent acquisition|"
    r"cashier|retail|merchandis\w*|demonstrator|guest advocate|store (?:manager|associate|assistant)|"
    r"front end\W+(?:entry|specialist|asst|assistant|associate|supervisor|team|clerk|service)|"
    r"security (?:officer|guard|patrol|shift)|armed|unarmed|"
    r"mammography|radiolog\w*|sonograph\w*|phlebotom\w*|pharmacy|nurs(?:e|ing)|ct tech|mri tech)\b"
)
_TECH_ROLE = re.compile(
    r"\b(engineer\w*|developer|programmer|software|architect|analy[st]\w*|scien\w*|research\w*|devops|sre|sdet|"
    r"technologist|designer|pre-?sales|technical sales|marketing cloud|sales and distribution|product (?:manager|owner)|it|"
    r"information (?:systems? )?security|isso|cyber\w*)\b"
)

# Titles in Chinese, Japanese or Korean are judged by these words; other non-Latin titles are kept.
_CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
_CJK_TECH_WORDS = re.compile(
    r"工程师|开发|研发|算法|数据|数智|软件|硬件|芯片|测试|架构|运维|前端|后端|产品经理|项目经理|分析师|解决方案|技术|程序|设计|"
    r"エンジニア|開発|データ|インフラ|システム|プログラ|セキュリティ|設計|アーキテクト|プロジェクトマネ|"
    r"개발|엔지니어|데이터|소프트웨어|시스템|보안|프로젝트 매니저|"
    r"(?<![A-Za-z])(?:AI|IT|ML|LLM|DX|QA|SAP|iOS|Android|Java|Python|C\+\+|App|Web)(?![A-Za-z])"
)


def is_tech_title(title: str | None) -> bool:
    """True if the title is a tech-adjacent job.

    Empty titles are kept. Chinese, Japanese and Korean titles are judged by ``_CJK_TECH_WORDS``
    ("下一代推荐大模型算法工程师" stays, "星级咖啡师" goes); titles mostly in other non-Latin scripts are kept,
    since neither the taxonomy nor the keywords can read them.
    """
    if not title or not title.strip():
        return True
    if not _mostly_latin(title):
        return not _CJK.search(title) or bool(_CJK_TECH_WORDS.search(title))
    lowered = title.lower()
    if _NON_TECH_ROLE.search(lowered) and not _TECH_ROLE.search(lowered):
        return False
    slug = match_occupation(title)
    if slug is not None:
        return slug in tech_occupations() or bool(_STRONG_TECH_WORDS.search(lowered))
    return bool(_TECH_WORDS.search(lowered.replace("data entry", "")))


_SLUG_WORD = re.compile(r"[A-Za-z][A-Za-z+#.]+")

# Clearly non-tech roles, used only for URL slugs that contain no tech word.
_NON_TECH_WORDS = re.compile(
    r"\b(nurse|nursing|physician|therapist|pharmacist|pharmacy|caregiver|clinical|medical assistant|"
    r"dental|veterinary|restaurant|crew|cook|chef|barista|server|cashier|bartender|housekeeper|"
    r"housekeeping|janitor|custodian|driver|warehouse|forklift|picker|packer|retail|store|"
    r"merchandiser|teacher|tutor|nanny|security guard|electrician|plumber|carpenter|welder|"
    r"mechanic|technician|beauty|stylist|cleaner|laborer|labourer)\b"
)


def title_from_url(url: str) -> str | None:
    """The path segment that reads most like a job title, or None if the URL has only ids.

    Segments need two words of 3+ letters (hex ids don't qualify); ties go to the later segment,
    where ATSs put the job slug ("/en-US/External/job/Bengaluru/Software-Engineer_R123").
    """
    best, best_score = None, 1
    for segment in urlparse(url).path.split("/"):
        words = _SLUG_WORD.findall(unquote(segment).replace("-", " ").replace("_", " "))
        score = sum(1 for w in words if len(w) >= 3)
        if score >= max(best_score, 2):
            best, best_score = " ".join(words), score
    return best


_ATS_REQ_ID = re.compile(r"_[A-Za-z0-9-]*\d[A-Za-z0-9-]*$")
_UNICODE_WORD = re.compile(r"[^\W\d_][\w+#.]*")


def ats_slug_title(url: str) -> str | None:
    """The job title from a URL whose ATS puts it in a fixed place, or None.

    Workday: ``…myworkdayjobs.com/<site>/job/<location>/<Title-Words>_<ReqId>``; iCIMS:
    ``…icims.com/jobs/<id>/<title-words>/job``. One-word slugs and Workday's ``XMLNAME`` placeholder
    say too little and return None.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    segments = [unquote(s) for s in parsed.path.split("/") if s]
    if host.endswith(".myworkdayjobs.com") and "job" in segments[:-1]:
        raw = _ATS_REQ_ID.sub("", segments[-1])
    elif host.endswith(".icims.com") and len(segments) >= 3 and segments[0] == "jobs" and segments[1].isdigit():
        raw = segments[2]
    else:
        return None
    words = _UNICODE_WORD.findall(raw.replace("-", " ").replace("_", " "))
    if len(words) < 2 or "xmlname" in raw.lower():
        return None
    return " ".join(words)


def drop_at_monitor(url: str, title: str | None) -> bool:
    """Should a board check drop this posting before it is stored or scraped?

    With a real title (rich monitors), drop non-tech titles. Workday and iCIMS URLs carry the real
    title, so they are judged like one (D35). With any other URL, drop just when the slug names a
    known non-tech occupation ("…/Restaurant-Crew-Member/123"): a vague slug like "open-positions"
    must never cost a real tech job. Everything else is judged after the scrape.
    """
    if title and title.strip():
        return not is_tech_title(title)
    ats_title = ats_slug_title(url)
    if ats_title:
        return not is_tech_title(ats_title)
    slug_title = title_from_url(url)
    return bool(slug_title) and clearly_non_tech(slug_title)


def clearly_non_tech(text: str) -> bool:
    """High-precision negative for text that may not be a real title (URL slugs): it must name a
    known non-tech occupation, or contain a non-tech role word and no tech word."""
    slug = match_occupation(text)
    if slug is not None:
        return slug not in tech_occupations()
    lowered = text.lower()
    return bool(_NON_TECH_WORDS.search(lowered)) and not _TECH_WORDS.search(lowered)
