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
MAX_RETRIES = 3
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
        "content_type": "뉴스",
        "keywords": ["AI", "인공지능", "생성형 AI", "디지털", "데이터", "알고리즘"],
    },
    {
        "name": "개인정보보호위원회",
        "type": "html",
        "url": "https://www.pipc.go.kr/np/cop/bbs/selectBoardList.do?bbsId=BS074&mCode=C020010000",
        "category": "개인정보·가이드라인",
        "content_type": "보도자료",
        "keywords": ["AI", "인공지능", "생성형", "데이터", "프라이버시", "마이데이터", "알고리즘"],
        "link_patterns": [r"/np/cop/bbs/selectBoardArticle\.do\?bbsId=BS074[^\"'#\s>]*nttId=\d+"],
    },
    {
        "name": "과학기술정보통신부",
        "type": "rss",
        "url": "https://www.msit.go.kr/user/rss/rss.do?bbsSeqNo=94",
        "category": "정부정책",
        "content_type": "보도자료",
        "keywords": ["AI", "인공지능", "디지털", "데이터", "클라우드", "플랫폼", "반도체"],
    },
    {
        "name": "행정안전부",
        "type": "rss",
        "url": "https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012",
        "category": "디지털정부",
        "content_type": "보도자료",
        "keywords": ["AI", "인공지능", "디지털정부", "공공서비스", "데이터", "행정", "플랫폼"],
    },
    {
        "name": "조달청",
        "type": "html",
        "url": "https://www.pps.go.kr/kor/bbs/list.do?key=00634",
        "category": "공공조달·디지털정부",
        "content_type": "보도자료",
        "keywords": ["AI", "인공지능", "디지털", "데이터", "나라장터", "정보화", "플랫폼", "혁신제품"],
        "link_patterns": [r"/kor/bbs/view\.do\?bbsSn=\d+[^\"'#\s>]*key=00634"],
    },
    {
        "name": "한국인터넷진흥원",
        "type": "rss",
        "url": "https://kisa.or.kr/rss/402",
        "category": "AI보안·신뢰",
        "content_type": "보도자료",
        "keywords": ["AI", "인공지능", "보안", "프라이버시", "클라우드", "사이버", "가이드라인"],
    },
]

STRICT_AI_KEYWORDS = [
    "ai",
    "인공지능",
    "생성형",
    "초거대",
    "llm",
    "aix",
    "ax",
    "온디바이스 ai",
    "ai 에이전트",
    "ai정부",
]

SECONDARY_POLICY_KEYWORDS = [
    "디지털",
    "데이터",
    "플랫폼",
    "클라우드",
    "보안",
    "알고리즘",
    "반도체",
]

BLOCKED_GENERIC_KEYWORDS = [
    "지방",
    "재난",
    "화재",
    "기부",
    "봉사",
    "지방선거",
    "국정과제",
    "민생",
    "주민등록",
    "새마을금고",
    "주유소",
    "고향사랑",
    "공장",
    "행사",
    "교육",
    "워크숍",
    "채용",
    "입찰",
    "인사",
    "광고",
]


def log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


def request_session():
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        }
    )
    return session


def fetch_with_retry(session, url, timeout=REQUEST_TIMEOUT):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            last_error = error
            if attempt == MAX_RETRIES:
                break
            wait_seconds = 1.5 * attempt
            log(f"Retrying {url} ({attempt}/{MAX_RETRIES - 1}) after error: {error}")
            time.sleep(wait_seconds)
    raise last_error


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
    url = re.sub(r"(?i)^http://", "https://", url)
    url = re.sub(r"[?&](utm_[^=&]+|fbclid|gclid)=[^&#]+", "", url)
    url = re.sub(r"[?&]call_from=rsslink", "", url)
    url = re.sub(r"[?&]$", "", url)
    url = url.replace("?&", "?")
    url = url.rstrip("?")
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


def normalize_title(value):
    text = strip_tags(value).lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[\"'“”‘’\[\]\(\)\{\}\.,!?:;/\-]", "", text)
    text = re.sub(r"\bkisa\b", "", text)
    text = re.sub(r"\bai\b", "인공지능", text)
    return text.strip()


def first_text(parent, *tags):
    for tag in tags:
        node = parent.find(tag)
        if node is not None and node.text:
            return node.text.strip()
    return ""


def parse_rss(xml_payload, source):
    root = ET.fromstring(xml_payload)
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
                "content_type": source.get("content_type", "보도자료"),
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
                "content_type": source.get("content_type", "보도자료"),
            }
        )
    return articles


def fetch_og_image(session, url):
    if not url:
        return ""
    try:
        response = fetch_with_retry(session, url, timeout=REQUEST_TIMEOUT)
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
        response = fetch_with_retry(session, url, timeout=REQUEST_TIMEOUT)
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
    parsed_final_url = urlparse(final_url)
    if parsed_final_url.path in ("", "/", "/main.do"):
        return None

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

    body_image_patterns = [
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
        r'background-image\s*:\s*url\(["\']?([^)"\']+)["\']?\)',
    ]

    title_value = strip_tags(title_match.group(1)) if title_match else ""
    summary_value = compact_summary(desc_match.group(1)) if desc_match else ""
    image_value = normalize_url(image_match.group(1)) if image_match else ""

    if not image_value:
        image_candidates = []
        for pattern in body_image_patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            for matched_value in matches:
                candidate = normalize_url(urljoin(final_url, matched_value))
                lowered_candidate = candidate.lower()
                if any(blocked in lowered_candidate for blocked in ["logo", "icon", "banner", "common", "symbol"]):
                    continue
                image_candidates.append(candidate)

        if image_candidates:
            def image_priority(candidate_url):
                lowered = candidate_url.lower()
                score = 0
                if "ckeditor/imagedownload.do" in lowered:
                    score += 100
                if "/ckeditor/" in lowered:
                    score += 40
                if any(ext in lowered for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    score += 10
                if "thumb" in lowered or "thumbnail" in lowered:
                    score -= 15
                return score

            image_candidates = sorted(
                list(dict.fromkeys(image_candidates)),
                key=image_priority,
                reverse=True,
            )
            image_value = image_candidates[0]

    if "홈페이지에 오신" in summary_value or "홈페이지에 오신" in title_value:
        return None

    return {
        "final_url": final_url,
        "title": title_value,
        "summary": summary_value,
        "image_url": image_value,
    }


def is_relevant(article, source):
    title = strip_tags(article.get("title", ""))
    summary = strip_tags(article.get("summary", ""))
    title_lower = title.lower()
    summary_lower = summary.lower()
    haystack = (title_lower + " " + summary_lower).strip()

    blocked_title_keywords = [
        "인사",
        "채용",
        "모집",
        "입찰",
        "공지",
        "교육 안내",
        "행사 안내",
        "광고",
    ]
    allowed_with_blocked = ["ai", "인공지능", "생성형", "ax", "디지털", "데이터", "알고리즘", "보안"]

    if any(keyword in title_lower for keyword in blocked_title_keywords):
        if not any(keyword in title_lower for keyword in allowed_with_blocked):
            return False

    if any(keyword in haystack for keyword in BLOCKED_GENERIC_KEYWORDS):
        if not any(keyword in haystack for keyword in STRICT_AI_KEYWORDS):
            return False

    has_strict_ai = any(keyword in title_lower for keyword in STRICT_AI_KEYWORDS) or any(
        keyword in summary_lower for keyword in STRICT_AI_KEYWORDS
    )
    if has_strict_ai:
        return True

    has_source_keyword = False
    for keyword in source.get("keywords", []):
        keyword_lower = keyword.lower()
        if keyword_lower in title_lower or keyword_lower in summary_lower:
            has_source_keyword = True
            break

    has_secondary_policy = any(keyword in haystack for keyword in SECONDARY_POLICY_KEYWORDS)

    if has_source_keyword and has_secondary_policy:
        return False

    return False


def load_source_articles(session, source):
    log(f"Source fetch started: {source['name']}")
    response = fetch_with_retry(session, source["url"], timeout=REQUEST_TIMEOUT)

    if source["type"] == "rss":
        raw_articles = parse_rss(response.content, source)
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
        if metadata["title"] and is_relevant(
            {
                "title": metadata["title"],
                "summary": article.get("summary", ""),
                "category": article.get("category", ""),
            },
            source,
        ):
            article["title"] = metadata["title"]
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


def build_supabase_headers(api_key):
    headers = {
        "apikey": api_key,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    if not api_key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def upsert_articles(session, supabase_url, service_key, articles):
    if not articles:
        log("No articles to upsert.")
        return 0

    endpoint = supabase_url.rstrip("/") + "/rest/v1/articles"
    headers = build_supabase_headers(service_key)

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
    seen_urls = set()
    seen_titles = set()
    unique = []
    for article in articles:
        article_url = normalize_url(article.get("article_url", ""))
        normalized_title = normalize_title(article.get("title", ""))
        published_key = (article.get("published_at") or "")[:10]
        source_key = (article.get("source_name") or "").strip().lower()
        title_key = source_key + "|" + normalized_title + "|" + published_key

        if not article_url:
            continue
        if article_url in seen_urls:
            continue
        if normalized_title and title_key in seen_titles:
            continue

        seen_urls.add(article_url)
        if normalized_title:
            seen_titles.add(title_key)
        article["article_url"] = article_url
        article["source_name"] = article.get("source_name") or guess_source_from_url(article_url)
        article["image_url"] = article.get("image_url") or DEFAULT_IMAGE_URL
        article["summary"] = compact_summary(article.get("summary", ""))
        article["category"] = article.get("category") or "정부정책"
        article["content_type"] = article.get("content_type") or "보도자료"
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
