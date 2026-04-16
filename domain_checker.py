"""
Abandoned Domain Finder — ядро системы.

Проверяет домены через:
1. Wayback Machine CDX API — история снапшотов
2. WHOIS — доступен ли домен для регистрации
3. Анализ контента — что было на сайте (блог, магазин, SaaS и т.д.)
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional


# Сигнатуры для определения типа сайта по HTML-контенту из архива
SITE_SIGNATURES = {
    "blog": [
        "wordpress", "wp-content", "blogpost", "blog-post", "article-content",
        "ghost", "jekyll", "hugo", "blogger", "tumblr", "medium",
        "post-meta", "entry-content", "blog-header", "comment-form",
    ],
    "online_store": [
        "add-to-cart", "add_to_cart", "shopify", "woocommerce", "magento",
        "product-price", "cart-total", "checkout", "buy-now", "shopping-cart",
        "bigcommerce", "opencart", "prestashop", "ecwid",
    ],
    "saas": [
        "sign-up", "signup", "free-trial", "pricing-plan", "dashboard",
        "login-form", "saas", "subscribe", "api-key", "get-started",
        "onboarding", "workspace",
    ],
    "forum": [
        "phpbb", "vbulletin", "xenforo", "discourse", "forum-post",
        "thread-title", "reply-count", "forum-category",
    ],
    "news_media": [
        "breaking-news", "news-article", "journalist", "editorial",
        "press-release", "newsroom", "headline",
    ],
    "portfolio": [
        "portfolio", "my-work", "project-showcase", "case-study",
        "dribbble", "behance",
    ],
    "digital_products": [
        "digital-download", "ebook", "online-course", "webinar",
        "gumroad", "teachable", "udemy", "skillshare", "download-now",
        "instant-download", "license-key",
    ],
}

# Минимальное кол-во снапшотов, чтобы считать домен «жившим»
MIN_SNAPSHOTS = 10

# Минимальный возраст домена в архиве (лет)
MIN_ARCHIVE_AGE_YEARS = 1


@dataclass
class DomainReport:
    domain: str
    available: Optional[bool] = None
    total_snapshots: int = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    archive_age_years: float = 0.0
    site_types: list = field(default_factory=list)
    sample_titles: list = field(default_factory=list)
    backlinks_estimate: int = 0
    score: int = 0
    error: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def check_wayback_snapshots(domain: str, timeout: int = 15) -> dict:
    """
    Запрашивает Wayback Machine CDX API — сколько снапшотов,
    когда первый и последний.
    """
    url = "https://web.archive.org/cdx/search/cdx"
    params = {
        "url": domain,
        "output": "json",
        "fl": "timestamp,statuscode",
        "collapse": "timestamp:6",  # группируем по месяцам
        "limit": 500,
    }
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e), "total": 0, "first": None, "last": None}

    if len(data) <= 1:
        return {"total": 0, "first": None, "last": None}

    rows = data[1:]  # первая строка — заголовки
    ok_rows = [r for r in rows if str(r[1]).startswith("2")]
    total = len(ok_rows)
    first_ts = ok_rows[0][0] if ok_rows else None
    last_ts = ok_rows[-1][0] if ok_rows else None

    return {"total": total, "first": first_ts, "last": last_ts}


def fetch_archived_page(domain: str, timeout: int = 15) -> Optional[str]:
    """
    Загружает последний снапшот домена из Wayback Machine.
    """
    url = f"https://web.archive.org/web/2/{domain}"
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "DomainFinder/1.0"})
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def detect_site_type(html: str) -> list:
    """
    Анализирует HTML и определяет тип сайта по сигнатурам.
    """
    html_lower = html.lower()
    detected = []
    for site_type, keywords in SITE_SIGNATURES.items():
        matches = sum(1 for kw in keywords if kw in html_lower)
        if matches >= 2:
            detected.append({"type": site_type, "confidence": min(matches / len(keywords), 1.0)})
    detected.sort(key=lambda x: x["confidence"], reverse=True)
    return detected


def extract_titles(html: str) -> list:
    """
    Извлекает заголовки страницы из архивного HTML.
    """
    titles = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            titles.append(title_tag.string.strip())
        for tag in soup.find_all(["h1", "h2"], limit=5):
            text = tag.get_text(strip=True)
            if text and len(text) > 3:
                titles.append(text)
    except Exception:
        pass
    return titles[:5]


def check_domain_available(domain: str) -> Optional[bool]:
    """
    Проверяет доступность домена через WHOIS.
    Возвращает True если домен свободен, False если занят, None при ошибке.
    """
    try:
        import whois
        w = whois.whois(domain)
        # Если expiration_date в прошлом или нет данных — домен может быть свободен
        if w.domain_name is None:
            return True
        if w.expiration_date:
            exp = w.expiration_date
            if isinstance(exp, list):
                exp = exp[0]
            if exp < datetime.now():
                return True
        return False
    except Exception:
        # Ошибка WHOIS часто означает, что домен свободен
        return None


def estimate_backlinks(domain: str, timeout: int = 10) -> int:
    """
    Оценка количества бэклинков через CommonCrawl Index API.
    Грубая оценка — считаем количество уникальных страниц, ссылающихся на домен.
    """
    url = "https://index.commoncrawl.org/CC-MAIN-2024-10-index"
    params = {
        "url": f"*.{domain}",
        "output": "json",
        "limit": 50,
    }
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code == 200:
            lines = resp.text.strip().split("\n")
            return len(lines)
    except Exception:
        pass
    return 0


def calculate_score(report: DomainReport) -> int:
    """
    Рассчитывает «ценность» домена по шкале 0-100.
    """
    score = 0

    # Снапшоты (макс 30 баллов)
    if report.total_snapshots >= 100:
        score += 30
    elif report.total_snapshots >= 50:
        score += 20
    elif report.total_snapshots >= MIN_SNAPSHOTS:
        score += 10

    # Возраст в архиве (макс 20 баллов)
    if report.archive_age_years >= 5:
        score += 20
    elif report.archive_age_years >= 3:
        score += 15
    elif report.archive_age_years >= MIN_ARCHIVE_AGE_YEARS:
        score += 10

    # Тип сайта (макс 30 баллов)
    high_value_types = {"online_store", "saas", "digital_products"}
    medium_value_types = {"blog", "news_media", "forum"}
    for st in report.site_types:
        if st["type"] in high_value_types and st["confidence"] > 0.3:
            score += 30
            break
        elif st["type"] in medium_value_types and st["confidence"] > 0.3:
            score += 20
            break

    # Бэклинки (макс 20 баллов)
    if report.backlinks_estimate >= 30:
        score += 20
    elif report.backlinks_estimate >= 10:
        score += 15
    elif report.backlinks_estimate >= 3:
        score += 10

    return min(score, 100)


def analyze_domain(domain: str) -> DomainReport:
    """
    Полный анализ одного домена.
    """
    domain = domain.strip().lower()
    domain = re.sub(r'^https?://', '', domain)
    domain = domain.rstrip('/')

    report = DomainReport(domain=domain)

    # 1. Проверяем историю в Wayback Machine
    wb = check_wayback_snapshots(domain)
    if "error" in wb:
        report.error = wb["error"]
    report.total_snapshots = wb["total"]

    if wb["first"]:
        report.first_seen = wb["first"][:8]  # YYYYMMDD
    if wb["last"]:
        report.last_seen = wb["last"][:8]

    if wb["first"] and wb["last"]:
        try:
            first_dt = datetime.strptime(wb["first"][:8], "%Y%m%d")
            last_dt = datetime.strptime(wb["last"][:8], "%Y%m%d")
            report.archive_age_years = round((last_dt - first_dt).days / 365.25, 1)
        except Exception:
            pass

    # 2. Проверяем доступность домена
    report.available = check_domain_available(domain)

    # 3. Загружаем архивную страницу и анализируем контент
    html = fetch_archived_page(domain)
    if html:
        report.site_types = detect_site_type(html)
        report.sample_titles = extract_titles(html)

    # 4. Оценка бэклинков
    report.backlinks_estimate = estimate_backlinks(domain)

    # 5. Рассчитываем скор
    report.score = calculate_score(report)

    return report


def analyze_domains_batch(domains: list, delay: float = 1.0) -> list:
    """
    Анализ списка доменов с задержкой между запросами.
    """
    results = []
    for domain in domains:
        report = analyze_domain(domain)
        results.append(report)
        time.sleep(delay)
    results.sort(key=lambda r: r.score, reverse=True)
    return results
