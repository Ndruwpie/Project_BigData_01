
import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


import json
from collections import Counter

FILE = Path(__file__).resolve().parents[3] / "output/result.json"

with open(FILE, "r", encoding="utf-8") as f:
    articles = json.load(f)

print("\n===== DATA QUALITY REPORT =====")
print("Total artikel:", len(articles))

fields = [
    "urlhash",
    "title",
    "content",
    "published_date",
    "author",
    "category",
    "tag",
    "url"
]

for field in fields:
    empty = sum(
        1 for article in articles
        if not article.get(field)
    )

    print(f"{field:20s}: {empty} kosong")

urls = [a.get("url") for a in articles]
duplicates = len(urls) - len(set(urls))

print("\nDuplikat URL:", duplicates)

categories = Counter(
    a.get("category") for a in articles
)

print("\nKategori:", dict(categories))

word_counts = [
    len(a.get("content", "").split())
    for a in articles
]

if word_counts:
    print("Rata-rata kata:", round(
        sum(word_counts) / len(word_counts), 2
    ))
    print("Konten terpendek:", min(word_counts))
    print("Konten terpanjang:", max(word_counts))

print("\n===== CONTOH ARTIKEL =====")

if articles:
    article = articles[0]

    print("Judul:", article.get("title"))
    print("Tanggal:", article.get("published_date"))
    print("Penulis:", article.get("author"))
    print("Kategori:", article.get("category"))
    print("URL:", article.get("url"))
    print(
        "Konten (300 karakter):",
        article.get("content", "")[:300]
    )
