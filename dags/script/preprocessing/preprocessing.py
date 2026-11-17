"""Pembersihan dasar, tujuh tahap NLP, dan pemrosesan Silver; impor tidak menjalankan pipeline."""

import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import html
import argparse
import hashlib
import re
import textwrap
import unicodedata
from contextlib import closing
from datetime import datetime, timezone, timedelta
from functools import lru_cache


def _connection_options():
    from script.storage.warehouse_ingestion import connection_options
    return connection_options()

WIB = timezone(timedelta(hours=7))
EXCLUSION = re.compile(
    r"^(?:baca\s+juga|baca\s+selengkapnya|rekomendasi\s+untuk\s+anda|"
    r"artikel\s+ini\s+telah\s+tayang|lanjutkan membaca|berlangganan untuk|"
    r"langganan sekarang)\b", re.I)
SUMMARY = re.compile(r"^ringkasan\s+berita\s*[:：\-–—]?\s*", re.I)
NAVIGATION = re.compile(r"^(?:lihat\s+foto|lihat\s+selengkapnya)\s*[:>»\-]*\s*$", re.I)
BYLINE = re.compile(
    r"^laporan\s+wartawan\s+[^,\r\n]+,\s*(?P<author>[^\r\n]+)$", re.I)


def byline_author(line):
    match = BYLINE.fullmatch(line.strip())
    if not match:
        return None
    name = match['author'].strip()
    # Jangan menganggap paragraf berita yang tergabung sebagai nama penulis.
    if len(name) > 120 or re.search(r"tribunnews\.com|[!?]|\s[-–—]\s", name, re.I):
        return None
    return name


def preprocessing(content):
    text = unicodedata.normalize("NFKC", html.unescape(content or ""))
    kept = []
    for line in text.splitlines():
        line = line.strip()
        if byline_author(line) or EXCLUSION.match(line) or NAVIGATION.fullmatch(line):
            continue
        line = SUMMARY.sub('', line)
        if line:
            kept.append(line)
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def clean_tags(tags):
    if isinstance(tags, str):
        tags = tags.split(",")
    return list(dict.fromkeys(unicodedata.normalize("NFKC", str(t)).strip().lower()
                             for t in (tags or []) if str(t).strip()))


def preprocess_article(article):
    result = dict(article)
    if not (article.get('author') or '').strip():
        for line in unicodedata.normalize('NFKC', html.unescape(article.get('content') or '')).splitlines():
            author = byline_author(line)
            if author:
                result['author'] = author
                break
    result["content"] = preprocessing(article.get("content"))
    result["title"] = re.sub(r"\s+", " ", html.unescape(article.get("title") or "")).strip()
    result["tag"] = clean_tags(article.get("tag"))
    result["category"] = (article.get("category") or "").strip().lower()
    if not result["content"] or not result["title"] or not result["category"]:
        raise ValueError(f"Artikel tidak lengkap setelah dibersihkan: {article.get('url')}")
    try:
        stamp = datetime.fromisoformat((article.get("published_date") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Tanggal publikasi tidak valid: {article.get('url')}") from exc
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=WIB)
    result["published_date"] = stamp.astimezone(WIB).isoformat()
    return result


# Tujuh tahap NLP
SLANG = {
    'yg': 'yang', 'dgn': 'dengan', 'dg': 'dengan', 'utk': 'untuk',
    'tdk': 'tidak', 'gak': 'tidak', 'nggak': 'tidak', 'ga': 'tidak',
    'krn': 'karena', 'karna': 'karena', 'udah': 'sudah', 'sdh': 'sudah',
    'blm': 'belum', 'dr': 'dari', 'dlm': 'dalam', 'kalo': 'kalau',
    'tp': 'tetapi', 'tapi': 'tetapi', 'aja': 'saja', 'gimana': 'bagaimana',
}


class NLPPipeline:
    def __init__(self):
        from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
        from Sastrawi.Stemmer.Stemmer import Stemmer
        from Sastrawi.Dictionary.ArrayDictionary import ArrayDictionary
        from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
        from deep_translator import GoogleTranslator
        class IndexedDictionary(ArrayDictionary):
            def __init__(self, words):
                super().__init__(words)
                self.word_set = set(self.words)

            def contains(self, word):
                return word in self.word_set

        self.stemmer = Stemmer(IndexedDictionary(StemmerFactory().get_words()))
        self.stopwords = set(StopWordRemoverFactory().get_stop_words())
        self.translator = GoogleTranslator(source='auto', target='id')
        self.translation_error = None

    @lru_cache(maxsize=50000)
    def stem(self, word):
        return self.stemmer.stem(word)

    def process(self, cleaned):
        from langdetect import detect_langs, DetectorFactory, LangDetectException
        DetectorFactory.seed = 0
        result = {
            'version': 'translate_first_v2', 'source_language': None,
            'language_confidence': None, 'translation_target': 'id',
            'translation_status': 'pending', 'translation_error': None,
            'translate': None, 'nlp_status': 'blocked', 'content_nlp': None,
            'case_folding': None, 'regex': None, 'tokenisasi': None,
            'normalisasi': None, 'stemming': None, 'stopword': None,
        }
        try:
            candidates = detect_langs(cleaned)
        except LangDetectException:
            result['translation_status'] = 'unknown_language'
            return result
        language = candidates[0]
        result.update(source_language=language.lang, language_confidence=language.prob)
        if language.prob < 0.8:
            result['translation_status'] = 'uncertain_language'
            return result
        if language.lang == 'id':
            text = cleaned
            result['translation_status'] = 'not_needed'
        else:
            if self.translation_error:
                result.update(translation_status='blocked', translation_error=self.translation_error)
                return result
            try:
                chunks = textwrap.wrap(cleaned, width=4000, break_on_hyphens=False,
                                       replace_whitespace=False)
                text = ' '.join(self.translator.translate(chunk) for chunk in chunks)
                if not text.strip():
                    raise ValueError('Empty translation')
                result.update(translate=text, translation_status='completed')
            except Exception as exc:
                self.translation_error = type(exc).__name__
                result.update(translation_status='failed', translation_error=self.translation_error)
                return result
        folded = text.lower()
        regex = re.sub(r'https?://\S+|www\.\S+|\S+@\S+', ' ', folded)
        regex = re.sub(r'[^\w\s]|_', ' ', regex)
        regex = re.sub(r'\s+', ' ', regex).strip()
        tokens = regex.split()
        normalized = [part for token in tokens for part in SLANG.get(token, token).split()]
        stemmed = [self.stem(token) for token in normalized]
        filtered = [token for token in stemmed if token and token not in self.stopwords]
        result.update(case_folding=folded, regex=regex, tokenisasi=tokens,
                      normalisasi=normalized, stemming=stemmed, stopword=filtered,
                      content_nlp=' '.join(filtered), nlp_status='completed')
        return result


# Pemrosesan database
def run_nlp(limit=0, incremental=False):
    import psycopg2
    from psycopg2.extras import Json
    options = _connection_options()
    with closing(psycopg2.connect(dbname='bronze', user='l1', port=5441, **options)) as bronze:
        with bronze, bronze.cursor() as cur:
            cur.execute('SELECT urlhash,payload FROM public.articles ORDER BY urlhash' +
                        (' LIMIT %s' if limit else ''), (limit,) if limit else ())
            rows = cur.fetchall()
    pipeline = NLPPipeline()
    root = Path(__file__).resolve().parents[3]
    completed = 0
    with closing(psycopg2.connect(dbname='silver', user='l2', port=5442, **options)) as silver:
        with silver, silver.cursor() as cur:
            cur.execute((root / 'db/warehouse/migrations/003_silver_nlp.sql').read_text())
            if incremental:
                cur.execute("""SELECT urlhash, nlp_stages->>'source_content_sha256',
                    nlp_stages->>'version' FROM public.articles""")
                previous = {key: (digest, version) for key, digest, version in cur.fetchall()}
                rows = [(key, raw) for key, raw in rows
                        if previous.get(key) != (
                            hashlib.sha256(raw['content'].encode()).hexdigest(),
                            'translate_first_v2')]
        for index, (key, raw) in enumerate(rows, 1):
            clean = preprocess_article(raw)
            stages = pipeline.process(clean['content'])
            stages['source_content_sha256'] = hashlib.sha256(raw['content'].encode()).hexdigest()
            with silver, silver.cursor() as cur:
                cur.execute('''UPDATE public.articles SET nlp_stages=%s,
                    content_nlp=%s,nlp_processed_at=now() WHERE urlhash=%s''',
                    (Json(stages), stages['content_nlp'], key))
                if cur.rowcount != 1:
                    raise RuntimeError(f'Artikel belum ada di Silver: {key}')
                cur.execute('SELECT nlp_stages FROM public.articles WHERE urlhash=%s', (key,))
                if cur.fetchone()[0] != stages:
                    raise RuntimeError('Verifikasi tahap NLP gagal')
            completed += stages['nlp_status'] == 'completed'
            print(f'{index}/{len(rows)} tersimpan; Translate: {stages["translation_status"]}; '
                  f'error: {stages["translation_error"]}', flush=True)
    print(f'Silver: {len(rows)} artikel diproses, {completed} hasil NLP selesai.', flush=True)
    return {'processed': len(rows), 'completed': completed, 'blocked': len(rows) - completed}


def refresh_silver():
    import psycopg2
    from psycopg2.extras import execute_values
    options = _connection_options()
    with closing(psycopg2.connect(dbname='bronze', user='l1', port=5441, **options)) as conn:
        with conn, conn.cursor() as cur:
            cur.execute('SELECT urlhash, payload FROM public.articles ORDER BY urlhash')
            source = cur.fetchall()
    cleaned = []
    for urlhash, payload in source:
        if payload.get('urlhash') != urlhash:
            raise ValueError(f'Identitas Bronze tidak cocok: {urlhash}')
        cleaned.append(preprocess_article(payload))
    print(f'Snapshot Bronze: {len(cleaned)} artikel valid', flush=True)
    with closing(psycopg2.connect(dbname='silver', user='l2', port=5442, **options)) as conn:
        # Satu transaksi: kesalahan membatalkan seluruh pembaruan.
        with conn, conn.cursor() as cur:
            cur.execute('SET LOCAL lock_timeout = \'30s\'')
            cur.execute('LOCK TABLE public.articles IN SHARE ROW EXCLUSIVE MODE')
            for offset in range(0, len(cleaned), 250):
                batch = cleaned[offset:offset + 250]
                execute_values(cur, '''INSERT INTO public.articles
                    (article_id,urlhash,article_url,title,content,author,category,tags,published_at,crawled_at)
                    VALUES %s ON CONFLICT(urlhash) DO UPDATE SET
                    article_url=EXCLUDED.article_url,title=EXCLUDED.title,
                    content=EXCLUDED.content,author=EXCLUDED.author,
                    category=EXCLUDED.category,tags=EXCLUDED.tags,
                    published_at=EXCLUDED.published_at,processed_at=now()''',
                    [(r['urlhash'], r['urlhash'], r['url'], r['title'], r['content'],
                      r.get('author'), r['category'], r['tag'], r['published_date'],
                      r.get('crawled_at')) for r in batch])
            cur.execute('SELECT urlhash,content,author FROM public.articles WHERE urlhash=ANY(%s)',
                        ([r['urlhash'] for r in cleaned],))
            actual = {h: (content, author) for h, content, author in cur.fetchall()}
            for row in cleaned:
                if actual.get(row['urlhash']) != (row['content'], row.get('author')):
                    raise RuntimeError('Verifikasi isi Silver gagal; transaksi dibatalkan')
        print(f'Selesai: {len(cleaned)} artikel diperbarui dan diverifikasi di Silver.', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Pembersihan dasar dan tujuh tahap NLP ke Silver.')
    parser.add_argument('--mode', choices=('nlp', 'clean'), default='nlp',
                        help='nlp: tujuh tahap NLP; clean: perbarui seluruh teks bersih Silver')
    parser.add_argument('--limit', type=int, default=10, help='Batas sampel NLP; 0 untuk semua')
    parser.add_argument('--incremental', action='store_true', help='NLP hanya sumber baru/berubah')
    args = parser.parse_args()
    if args.limit < 0:
        parser.error('limit harus >= 0')
    if args.mode == 'clean':
        if args.incremental or args.limit != 10:
            parser.error('--limit dan --incremental hanya untuk mode nlp')
        refresh_silver()
    else:
        run_nlp(args.limit, args.incremental)


if __name__ == '__main__':
    main()
