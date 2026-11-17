"""Analitik terjadwal dari Gold; snapshot JSON untuk audit dan dashboard."""

import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
from math import log, sqrt
import re
import psycopg2
from script.storage.warehouse_ingestion import connection_options
from script.storage.storage import save_json


def build_analytics():
    with closing(psycopg2.connect(dbname='gold', user='l3', port=5443, **connection_options())) as conn:
        conn.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with conn, conn.cursor() as cur:
            result = {'generated_at': datetime.now(timezone.utc).isoformat()}
            for name, sql in {
                'daily': 'SELECT tanggal::text,kategori,sum(jumlah_berita) FROM public.v_news_daily GROUP BY tanggal,kategori ORDER BY tanggal,kategori',
                'topics': 'SELECT kategori,nama_topik,count(*) FROM public.v_news_dashboard GROUP BY kategori,nama_topik ORDER BY count(*) DESC',
                'weekly': 'SELECT minggu::text,kategori,sum(jumlah_berita) FROM public.v_news_weekly GROUP BY minggu,kategori ORDER BY minggu,kategori',
                'publication_time': 'SELECT hari_ke,jam,kategori,sum(jumlah_berita) FROM public.v_news_publication_time GROUP BY hari_ke,jam,kategori',
            }.items():
                cur.execute(sql)
                result[name] = [list(row) for row in cur.fetchall()]
                # PostgreSQL SUM(bigint) adalah Decimal.
                for row in result[name]:
                    row[-1] = int(row[-1])
            cur.execute("SELECT content_nlp FROM public.v_news_dashboard WHERE nlp_status='completed' AND content_nlp IS NOT NULL")
            docs = [Counter(re.findall(r'(?u)\b[^\W\d_]{2,}\b', row[0].lower())) for row in cur.fetchall()]
            cur.execute('SELECT count(*) FROM public.fact_news')
            result['articles'] = cur.fetchone()[0]
    df = Counter()
    for doc in docs:
        df.update(doc.keys())
    scores = defaultdict(float)
    for doc in docs:
        weights = {word: count*(log((1+len(docs))/(1+df[word]))+1) for word,count in doc.items()}
        norm = sqrt(sum(v*v for v in weights.values()))
        if norm:
            for word, value in weights.items():
                scores[word] += value/norm/len(docs)
    result['tfidf_documents'] = len(docs)
    result['tfidf'] = sorted(scores.items(), key=lambda item: (-item[1],item[0]))[:100]
    result['tfidf_method'] = 'raw TF, smooth IDF, L2 normalization, mean across completed documents; all vocabulary'
    target = Path(__file__).resolve().parents[3] / 'output/analytics/latest.json'
    save_json(target, result)
    print(f"Analytics: {result['articles']} artikel; {len(docs)} dokumen NLP; {target}")
