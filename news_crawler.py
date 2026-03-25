import json
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import requests


DEFAULT_IMAGE_URL = "https://images.unsplash.com/photo-1516321497487-e288fb19713f?auto=format&fit=crop&w=1200&q=80"
REQUEST_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

SOURCES = [
    {
        "name": "정책브리핑",
        "type": "rss",
        "url": "https://www.korea.kr/rss/policy.xml",
        "category": "정부정책",
        "keywords": ["AI", "인공지능", "생성형 AI", "디지털", "데이터", "알고리즘"],
    },
    {
        "name": "개인정보보호위원회",
        "type": "html",
        "url": "https://www.pipc.go.kr/np/cop/bbs/selectBoardList.do?bbsId=BS074&mCode=C020010000",
        "category": "개인정보·가이드라인",
        "keywords": ["AI", "인공지능", "생성형", "데이터", "프라이버시", "마이데이터", "알고리즘"],
        "link_patterns": [r"/np/cop/bbs/selectBoardArticle\.do\?bbsId=BS074[^\"'#\s>]*nttId=\d+"],
    },
    {
        "name": "과학기술정보통신부",
        "type": "rss",
        "url": "https://www.msit.go.kr/rss/rss.jsp?mPid=001",
        "category": "정부정책",
        "keywords": ["AI", "인공지능", "디지털", "데이터", "클라우드", "플랫폼", "반도체"],
    },
    {
        "name": "행정안전부",
        "type": "rss",
        "url": "https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012",
        "category": "디지털정부",
        "keywords": ["AI", "인공지능", "디지털정부", "공공서비스", "데이터", "행정", "플랫폼"],
    },
    {
        "name": "디지털플랫폼정부위원회",
        "type": "html",
        "url": "https://dpg.go.kr/DPG/contents/DPG02020000.do",
        "category": "디지털정부",
        "keywords": ["AI", "인공지능", "초거대", "디지털플랫폼정부", "공공", "데이터"],
        "link_patterns": [r"/DPG/contents/DPG02020000\.do\?id=\d+[^\"'#\s>]*"],
    },
    {
        "name": "한국인터넷진흥원",
        "type": "rss",
        "url": "https://kisa.or.kr/rss/402",
        "category": "AI보안·신뢰",
        "keywords": ["AI", "인공지능", "보안", "프라이버시", "클라우드", "사이버", "가이드라인"],
    },
]


def log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


def request_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def strip_tags(value):
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compact_summary(value, max_length=140):
    text = strip_tags(value)
    if not text:
        return "요약 정보가 아직 등록되지 않았습니다."
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "..."


def normalize_url(value):
    url = (value or "").strip()
    if url.startswith("http://www.kisa.or.kr/"):
        url = "https://" + url[len("http://") :]
    return url


def parse_datetime(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    normalized = value.replace("Z", "+00:00").strip()
    for candidate in [normalized, normalized.replace(".", "-"), normalized.replace("/", "-")]:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return None


def guess_source_from_url(url):
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host or "출처 미상"


def first_text(parent, *tags):
    for tag in tags:
        node = parent.find(tag)
        if node is not None and node.text:
            return node.text.strip()
    return ""


def parse_rss(xml_text, source):
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []

    items = []
    for item in channel.findall("item"):
        title = first_text(item, "title")
        link = normalize_url(first_text(item, "link"))
        description = first_text(item, "description")
        pub_date = first_text(item, "pubDate")

        media = item.find("{http://search.yahoo.com/mrss/}content")
        enclosure = item.find("enclosure")
        image_url = ""
        if media is not None:
            image_url = normalize_url(media.attrib.get("url", ""))
        if not image_url and enclosure is not None:
            image_url = normalize_url(enclosure.attrib.get("url", ""))

        items.append(
            {
                "title": title,
                "article_url": link,
                "summary": compact_summary(description),
                "published_at": parse_datetime(pub_date),
                "image_url": image_url,
                "source_name": source["name"],
                "category": source["category"],
            }
        )
    return items


def parse_html_list(html_text, source):
    articles = []
    seen = set()

    anchor_pattern = re.compile(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    for href, inner_html in anchor_pattern.findall(html_text):
        absolute_url = urljoin(source["url"], normalize_url(href))
        title = strip_tags(inner_html)
        if not title:
            continue
        if source.get("link_patterns") and not any(re.search(pattern, absolute_url) for pattern in source["link_patterns"]):
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)

        published_at = None
        date_match = re.search(r"(20\d{2}[.\-/]\d{2}[.\-/]\d{2})", title)
        if date_match:
            published_at = parse_datetime(date_match.group(1).replace(".", "-").replace("/", "-"))
            title = title.replace(date_match.group(1), "").strip("()[] \t-")

        articles.append(
            {
                "title": title,
                "article_url": absolute_url,
                "summary": title,
                "published_at": published_at,
                "image_url": "",
                "source_name": source["name"],
                "category": source["category"],
            }
        )
    return articles


def fetch_og_image(session, url):
    if not url:
        return ""
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception:
        return ""

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, response.text, flags=re.IGNORECASE)
        if match:
            return normalize_url(match.group(1))
    return ""


def fetch_article_metadata(session, url):
    if not url:
        return None
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception:
        return None

    content_type = response.headers.get("content-type", "").lower()
    text = response.text or ""
    lowered = text[:300].lower()

    if "text/html" not in content_type:
        return None
    if "<rss" in lowered or "<?xml" in lowered:
        return None

    final_url = normalize_url(response.url)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    desc_match = re.search(
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)["\']',
        text,
        flags=re.IGNORECASE,
    )
    image_match = re.search(
        r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
        text,
        flags=re.IGNORECASE,
    )

    return {
        "final_url": final_url,
        "title": strip_tags(title_match.group(1)) if title_match else "",
        "summary": compact_summary(desc_match.group(1)) if desc_match else "",
        "image_url": normalize_url(image_match.group(1)) if image_match else "",
    }


def is_relevant(article, source):
    haystack = " ".join(
        [
            article.get("title", ""),
            article.get("summary", ""),
            article.get("category", ""),
        ]
    ).lower()
    for keyword in source.get("keywords", []):
        if keyword.lower() in haystack:
            return True
    return False


def load_source_articles(session, source):
    log(f"Source fetch started: {source['name']}")
    response = session.get(source["url"], timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    if source["type"] == "rss":
        raw_articles = parse_rss(response.text, source)
    else:
        raw_articles = parse_html_list(response.text, source)

    filtered = []
    for article in raw_articles:
        if not article["title"] or not article["article_url"]:
            continue
        if not is_relevant(article, source):
            continue
        metadata = fetch_article_metadata(session, article["article_url"])
        if not metadata:
            continue
        article["article_url"] = metadata["final_url"] or article["article_url"]
        if metadata["summary"]:
            article["summary"] = metadata["summary"]
        if metadata["image_url"]:
            article["image_url"] = metadata["image_url"]
        elif not article["image_url"]:
            article["image_url"] = fetch_og_image(session, article["article_url"]) or DEFAULT_IMAGE_URL
        time.sleep(0.15)
        filtered.append(article)

    log(f"Source fetch complete: {source['name']} / {len(filtered)} items")
    return filtered


def chunked(values, size):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def upsert_articles(session, supabase_url, service_key, articles):
    if not articles:
        log("No articles to upsert.")
        return 0

    endpoint = supabase_url.rstrip("/") + "/rest/v1/articles"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }

    inserted = 0
    for batch in chunked(articles, 50):
        response = session.post(
            endpoint,
            headers=headers,
            params={"on_conflict": "article_url"},
            data=json.dumps(batch, ensure_ascii=False),
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        inserted += len(payload)
    return inserted


def deduplicate(articles):
    seen = set()
    unique = []
    for article in articles:
        article_url = normalize_url(article.get("article_url", ""))
        if not article_url or article_url in seen:
            continue
        seen.add(article_url)
        article["article_url"] = article_url
        article["source_name"] = article.get("source_name") or guess_source_from_url(article_url)
        article["image_url"] = article.get("image_url") or DEFAULT_IMAGE_URL
        article["summary"] = compact_summary(article.get("summary", ""))
        article["category"] = article.get("category") or "정부정책"
        unique.append(article)
    return unique


def main():
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not supabase_url or not supabase_service_key:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")

    session = request_session()
    all_articles = []

    for source in SOURCES:
        try:
            all_articles.extend(load_source_articles(session, source))
        except Exception as error:
            log(f"Source fetch failed: {source['name']} / {error}")

    unique_articles = deduplicate(all_articles)
    inserted_count = upsert_articles(session, supabase_url, supabase_service_key, unique_articles)

    log(f"Unique candidates: {len(unique_articles)} / Supabase upserted: {inserted_count}")


if __name__ == "__main__":
    main()
