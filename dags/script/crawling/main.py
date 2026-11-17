"""Crawl indeks terbaru halaman 1-10, lalu preprocessing semua kategori."""

import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import hashlib

import json

import time

from datetime import datetime, timezone, timedelta


from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import argparse

import re




from script.storage.storage import save_json, crawler_lock
from script.preprocessing.preprocessing import preprocess_article



import requests

from bs4 import BeautifulSoup





# ==================================================

# 1. KONFIGURASI CRAWLING

# ==================================================



BASE_URL = "https://www.tribunnews.com"

INDEX_URL = f"{BASE_URL}/index-news/"



HEADERS = {

    "User-Agent": "Mozilla/5.0 (compatible; AcademicResearchBot/1.0)"

}



END_PAGE = 10

DELAY_SECONDS = 3

TIMEOUT_SECONDS = 20



PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_FILE = PROJECT_ROOT / "output/pages/raw.json"
CLEAN_FILE = PROJECT_ROOT / "output/pages/clean.json"

LEGACY_FILE = Path("result.json")



# Zona waktu Indonesia Barat (WIB)

WIB = timezone(timedelta(hours=7))





# ==================================================

# 2. FUNGSI TIMESTAMP

# ==================================================



def get_current_time():

    """Menghasilkan timestamp saat ini dalam zona waktu WIB."""

    return datetime.now(WIB).isoformat(timespec="seconds")





# ==================================================

# 3. MENGAMBIL HALAMAN WEBSITE

# ==================================================



class AccessBlockedError(RuntimeError):

    """Respons proteksi situs, bukan halaman berita."""





def validate_response(response):

    body = response.text.lower()

    challenge = any(marker in body for marker in (

        "awswafintegration", "window.gokuprops", "token.awswaf.com/",

    ))

    if challenge:

        raise AccessBlockedError(

            "Situs mengirim verifikasi anti-bot AWS WAF, bukan HTML berita. "

            "Periksa akses melalui browser; mengganti tanggal tidak menyelesaikan blokir ini."

        )

    if response.status_code in (401, 403, 429):

        raise AccessBlockedError(

            f"Akses ditolak/dibatasi (HTTP {response.status_code}): {response.url}. "

            "Proses dihentikan tanpa melewati halaman ini."

        )

    response.raise_for_status()





def fetch_soup(url):

    response = requests.get(

        url,

        headers=HEADERS,

        timeout=TIMEOUT_SECONDS

    )



    validate_response(response)



    return BeautifulSoup(response.text, "html.parser")





def inspect_html(soup):

    """Laporan struktur; tidak mengeksekusi JavaScript atau menyalin token."""

    forms = []

    for form in soup.select("form"):

        controls = []

        for control in form.select("input[name], select[name], button[name]"):

            if control.get("type", "").lower() in {"hidden", "password"}:

                continue

            controls.append({

                "name": control["name"], "type": control.get("type", control.name),

                "options": [o.get("value") for o in control.select("option")][:40],

            })

        forms.append({"action": form.get("action"), "method": form.get("method", "get"), "controls": controls})

    links = article_links(soup)

    pagination = [a["href"] for a in soup.select("a[href]")

                  if "page=" in a["href"] and "index" in a["href"]]

    print(json.dumps({

        "title": soup.title.get_text(strip=True) if soup.title else None,

        "forms": forms,

        "article_count": len(links),

        "sample_article_urls": list(links)[:10],

        "pagination": pagination[:20],

    }, ensure_ascii=False, indent=2))





# ==================================================

# 4. MENGAMBIL JSON-LD ARTIKEL

# ==================================================



def news_article_jsonld(soup):



    def walk(value):

        if isinstance(value, list):

            for child in value:

                yield from walk(child)



        elif isinstance(value, dict):

            yield value



            if "@graph" in value:

                yield from walk(value["@graph"])



    for script in soup.select('script[type="application/ld+json"]'):



        raw = script.string or script.get_text()



        if not raw or not raw.strip():

            continue



        try:

            data = json.loads(raw)



        except json.JSONDecodeError:

            continue



        for item in walk(data):



            types = item.get("@type", [])



            types = [types] if isinstance(types, str) else types



            if isinstance(types, list) and any(

                str(t).rstrip("/").split("/")[-1] == "NewsArticle"

                for t in types

            ):

                return item



    return {}





# ==================================================

# 5. EKSTRAKSI NAMA PENULIS

# ==================================================



def author_name(value):



    if isinstance(value, str):

        return value.strip()



    if isinstance(value, dict):

        return str(value.get("name") or "").strip()



    if isinstance(value, list):

        return ", ".join(

            filter(None, (author_name(item) for item in value))

        )



    return ""





# ==================================================

# 6. EKSTRAKSI KEYWORDS / TAG

# ==================================================



def keywords(value):



    if isinstance(value, str):

        values = value.split(",")



    elif isinstance(value, list):

        values = value



    else:

        values = []



    return list(

        dict.fromkeys(

            str(v).strip()

            for v in values

            if str(v).strip()

        )

    )





# ==================================================

# 7. EKSTRAKSI DATA ARTIKEL

# ==================================================



def extract_article(url, soup):



    structured = news_article_jsonld(soup)



    # Judul artikel

    title = str(structured.get("headline") or "").strip()



    if not title:

        title_tag = soup.select_one(

            "meta[property='og:title'], title, h1"

        )



        if title_tag:

            title = (

                title_tag.get("content", "")

                if title_tag.name == "meta"

                else title_tag.get_text(" ", strip=True)

            ).strip()



    if not title:

        return None



    # Nama penulis

    author = author_name(structured.get("author"))



    if not author:

        tag = soup.select_one("meta[name='author']")

        author = tag.get("content", "").strip() if tag else ""



    # Tanggal publikasi

    published_date = str(

        structured.get("datePublished") or ""

    ).strip()



    if not published_date:

        tag = soup.select_one(

            "meta[property='article:published_time'], time[datetime]"

        )



        published_date = (

            (tag.get("content") or tag.get("datetime") or "").strip()

            if tag else ""

        )



    # Keywords

    tags = keywords(structured.get("keywords"))



    if not tags:

        tag = soup.select_one("meta[name='news_keywords']")

        tags = keywords(tag.get("content", "")) if tag else []



    # Isi artikel

    content = ""



    for selector in (

        ".txt-article",

        ".read__content",

        ".article-content",

        "article"

    ):



        container = soup.select_one(selector)



        if container:



            paragraphs = [

                p.get_text(" ", strip=True)

                for p in container.select("p")

            ]



            content = "\n\n".join(

                p for p in paragraphs if p

            )



            if content:

                break



    # Kategori berdasarkan URL

    category = urlparse(url).path.strip("/").split("/")[0].lower()



    return {

        "urlhash": hashlib.sha256(

            url.encode("utf-8")

        ).hexdigest(),



        "author": author,

        "category": category,

        "tag": tags,

        "url": url,

        "title": title,

        "published_date": published_date,

        "content": content,

    }





# ==================================================

# 8. MENGAMBIL URL DARI HALAMAN INDEKS

# ==================================================



def article_links(soup):

    """URL artikel semua kategori untuk mendeteksi halaman kosong/berulang."""

    links = {}

    for anchor in soup.select("ul.lsi > li h3 a[href]"):

        parsed = urlparse(urljoin(BASE_URL, anchor["href"]))

        if parsed.hostname not in {"www.tribunnews.com", "tribunnews.com"}:

            continue

        parts = parsed.path.strip("/").split("/")

        modern = len(parts) == 3 and parts[1].isdigit()

        historical = (

            len(parts) == 5 and len(parts[1]) == 4

            and len(parts[2]) == 2 and len(parts[3]) == 2

            and all(part.isdigit() for part in parts[1:4])

        )

        if modern or historical:

            links[f"{BASE_URL}{parsed.path.rstrip('/')}"] = parts[0].lower()

    return links





def read_records(path):
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not r.get("url") for r in rows):
        raise ValueError(f"Format dataset tidak valid: {path}")
    return {r["url"]: r for r in rows}


def crawl_pages(write_db=False, raw_only=False):
    with crawler_lock(OUTPUT_FILE.with_suffix(".lock")):
        raw = read_records(OUTPUT_FILE)
        clean = {} if raw_only else read_records(CLEAN_FILE)
        seen, fingerprints = set(), set()
        for page in range(1, END_PAGE + 1):
            print(f"Halaman {page}/{END_PAGE}", flush=True)
            try:
                soup = fetch_soup(f"{INDEX_URL}?{urlencode({'page': page})}")
            finally:
                time.sleep(DELAY_SECONDS)
            links = article_links(soup)
            if not links:
                raise RuntimeError(f"Halaman {page}: daftar artikel tidak ditemukan.")
            fingerprint = tuple(sorted(links))
            if fingerprint in fingerprints:
                raise RuntimeError(f"Halaman {page} berulang; periksa pagination.")
            fingerprints.add(fingerprint)
            for url in links:
                if url in seen:
                    continue
                seen.add(url)
                article = raw.get(url)
                if not article or not article.get("content"):
                    try:
                        article = extract_article(url, fetch_soup(url))
                    finally:
                        time.sleep(DELAY_SECONDS)
                    if not article or not article.get("content"):
                        raise RuntimeError(f"Konten artikel tidak terbaca: {url}")
                    article["crawled_at"] = get_current_time()
                    article["last_crawled_at"] = article["crawled_at"]
                    raw[url] = article
                    save_json(OUTPUT_FILE, list(raw.values()))
                if raw_only:
                    continue
                # Tetap proses ulang artikel tersimpan agar kegagalan silver bisa dicoba lagi.
                processed = preprocess_article(article)
                clean[url] = processed
                save_json(CLEAN_FILE, list(clean.values()))
                if write_db:
                    from script.storage.warehouse_ingestion import store_article
                    store_article(article, processed)
                print(f"Diproses: {article['title']}", flush=True)
        print(f"Selesai 10 halaman; {len(seen)} URL unik ditemukan.", flush=True)


def main():
    # Entry point DAG, tanpa membaca argumen milik Airflow.
    crawl_pages(write_db=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl 10 halaman semua kategori + preprocessing")
    parser.add_argument("--write-db", action="store_true", help="Simpan juga ke Bronze 5441 dan Silver 5442")
    args = parser.parse_args()
    try:
        crawl_pages(write_db=args.write_db)
    except (requests.RequestException, RuntimeError, ValueError, OSError) as error:
        parser.exit(1, f"Pipeline dihentikan: {error}\n")
