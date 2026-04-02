"""
Парсеры источников истекающих/брошенных доменов.

Источники:
1. ExpiredDomains.net — крупнейшая база истекших доменов (нужна регистрация)
2. Генератор ниш — генерирует ключевые слова для поиска доменов
3. Wayback Machine CDX — поиск доменов с большим количеством снапшотов
"""

import re
import requests
from typing import Optional


# Популярные ниши для поиска доменов
NICHES = {
    "digital_products": [
        "digital downloads", "ebook store", "online templates",
        "printable planners", "stock photos", "icon packs",
        "wordpress themes", "font shop", "preset store",
    ],
    "saas": [
        "project management app", "crm tool", "email marketing",
        "analytics dashboard", "scheduling tool", "invoice generator",
        "form builder", "survey tool", "chatbot platform",
    ],
    "blog": [
        "tech blog", "travel blog", "food blog", "fitness blog",
        "finance blog", "lifestyle blog", "photography blog",
        "diy crafts blog", "parenting blog", "gaming blog",
    ],
    "ecommerce": [
        "dropshipping store", "print on demand", "handmade jewelry",
        "organic skincare", "pet supplies", "home decor shop",
    ],
    "education": [
        "online courses", "coding tutorials", "language learning",
        "math tutoring", "test prep", "study guides",
    ],
}


def fetch_expireddomains_list(
    keyword: str = "",
    tld: str = "com",
    min_backlinks: int = 5,
    timeout: int = 15,
) -> list:
    """
    Парсит ExpiredDomains.net для поиска доменов по ключевому слову.
    Требует cookie авторизации (бесплатная регистрация).
    Возвращает список доменов.
    """
    # ExpiredDomains.net требует авторизацию через cookie.
    # Для демо возвращаем инструкцию — пользователь должен
    # зарегистрироваться и добавить свой cookie.
    return {
        "source": "expireddomains.net",
        "instruction": (
            "Зарегистрируйтесь бесплатно на https://expireddomains.net, "
            "затем добавьте cookie в переменную окружения EXPIRED_DOMAINS_COOKIE. "
            "Это откроет доступ к 10M+ истекших доменов с фильтрацией."
        ),
        "domains": [],
    }


def generate_keyword_domains(niche: str, tlds: Optional[list] = None) -> list:
    """
    Генерирует потенциальные доменные имена по нише.
    """
    if tlds is None:
        tlds = ["com", "net", "org", "io"]

    keywords = NICHES.get(niche, [])
    domains = []
    for kw in keywords:
        slug = kw.replace(" ", "").lower()
        slug_dash = kw.replace(" ", "-").lower()
        for tld in tlds:
            domains.append(f"{slug}.{tld}")
            domains.append(f"{slug_dash}.{tld}")
    return domains


def search_wayback_by_keyword(keyword: str, limit: int = 20, timeout: int = 15) -> list:
    """
    Ищет домены в Wayback Machine CDX API по ключевому слову.
    Возвращает уникальные домены, отсортированные по количеству снапшотов.
    """
    url = "https://web.archive.org/cdx/search/cdx"
    params = {
        "url": f"*{keyword}*",
        "output": "json",
        "fl": "original",
        "collapse": "urlkey",
        "limit": limit * 5,  # запрашиваем больше, потом фильтруем
    }
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    if len(data) <= 1:
        return []

    # Извлекаем уникальные домены
    seen = set()
    domains = []
    for row in data[1:]:
        raw_url = row[0]
        match = re.search(r'https?://([^/]+)', raw_url)
        if match:
            domain = match.group(1).lower()
            domain = re.sub(r'^www\.', '', domain)
            if domain not in seen and '.' in domain:
                seen.add(domain)
                domains.append(domain)
        if len(domains) >= limit:
            break

    return domains


def get_niches() -> dict:
    """Возвращает все доступные ниши."""
    return NICHES
