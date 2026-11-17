"""Upsert Bronze kemudian Silver; aman dicoba ulang bila Silver gagal."""

import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
from contextlib import closing


def connection_options():
    env_path = Path(__file__).resolve().parents[3] / 'db/warehouse/.env'
    values = {}
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('\"\'')
    password = os.environ.get('POSTGRES_PASSWORD') or values.get('POSTGRES_PASSWORD')
    if not password:
        raise ValueError('POSTGRES_PASSWORD belum tersedia')
    return dict(host=os.environ.get('WAREHOUSE_HOST', 'localhost'),
                password=password, connect_timeout=10)


def store_article(raw, clean):
    import psycopg2
    from psycopg2.extras import Json
    common = connection_options()
    try:
        with closing(psycopg2.connect(dbname='bronze', user='l1', port=5441, **common)) as conn, conn:
            with conn.cursor() as cur:
                cur.execute('''INSERT INTO public.articles(urlhash, payload)
                    VALUES (%s, %s) ON CONFLICT(urlhash) DO UPDATE
                    SET payload=EXCLUDED.payload, ingested_at=now()''',
                    (raw['urlhash'], Json(raw)))
        with closing(psycopg2.connect(dbname='silver', user='l2', port=5442, **common)) as conn, conn:
            with conn.cursor() as cur:
                # Hash URL adalah identitas stabil, bukan penelusuran nomor artikel.
                cur.execute('''INSERT INTO public.articles
                    (article_id,urlhash,article_url,title,content,author,category,tags,published_at,crawled_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(urlhash) DO UPDATE SET
                    article_url=EXCLUDED.article_url,title=EXCLUDED.title,
                    content=EXCLUDED.content,author=EXCLUDED.author,
                    category=EXCLUDED.category,tags=EXCLUDED.tags,
                    published_at=EXCLUDED.published_at,processed_at=now()''',
                    (clean['urlhash'], clean['urlhash'], clean['url'], clean['title'],
                     clean['content'], clean.get('author'), clean['category'], clean['tag'],
                     clean['published_date'], clean.get('crawled_at')))
    except psycopg2.Error as exc:
        raise RuntimeError('Penyimpanan database gagal; hasil JSON tetap tersimpan. '
                           'Periksa koneksi, password, dan tabel Bronze/Silver.') from exc


def load_gold():
    """Snapshot Silver ke Gold: upsert atomik, semua kategori, satu fakta/artikel."""
    import psycopg2
    from psycopg2.extras import execute_values
    from datetime import timezone, timedelta

    options = connection_options()
    with closing(psycopg2.connect(dbname='silver', user='l2', port=5442, **options)) as silver:
        with silver, silver.cursor() as cur:
            cur.execute('''SELECT article_id, article_url, title, author, category, tags,
                           published_at, content_nlp, nlp_stages->>'nlp_status'
                           FROM public.articles ORDER BY article_id''')
            source = cur.fetchall()
    rows = []
    weekdays = ('Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu')
    for key, url, title, author, category, tags, published, content_nlp, status in source:
        if not key or not url or not title or not category or published is None:
            raise ValueError(f'Metadata Silver tidak lengkap: {key}')
        day = published.astimezone(timezone(timedelta(hours=7))).date()
        tags = [tag.strip() for tag in (tags or []) if tag and tag.strip()]
        rows.append((key, url, title, (author or '').strip() or 'Tidak diketahui',
                     category, tags, published, content_nlp if status == 'completed' else None,
                     status or 'pending', int(day.strftime('%Y%m%d')), day,
                     day.month, day.year, weekdays[day.weekday()], tags[0] if tags else category))
    with closing(psycopg2.connect(dbname='gold', user='l3', port=5443, **options)) as gold:
        with gold, gold.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '30s'")
            # Serialisasi pemuatan manual dan DAG; semua perubahan dalam satu transaksi.
            cur.execute('SELECT pg_advisory_xact_lock(7911591)')
            migration = Path(__file__).resolve().parents[3] / 'db/warehouse/migrations/004_gold_dashboard.sql'
            cur.execute(migration.read_text(encoding='utf-8'))
            cur.execute('''CREATE TEMP TABLE gold_source (
                article_id TEXT PRIMARY KEY, url TEXT, title TEXT, author TEXT,
                category TEXT, tags TEXT[], published_at TIMESTAMPTZ,
                content_nlp TEXT, nlp_status TEXT, id_date INTEGER, tanggal DATE,
                bulan INTEGER, tahun INTEGER, hari TEXT, topic TEXT) ON COMMIT DROP''')
            if rows:
                execute_values(cur, 'INSERT INTO gold_source VALUES %s', rows, page_size=500)
            cur.execute('''INSERT INTO public.dim_date
                SELECT DISTINCT id_date,tanggal,bulan,tahun,hari FROM gold_source
                ON CONFLICT(id_date) DO UPDATE SET tanggal=EXCLUDED.tanggal,
                bulan=EXCLUDED.bulan,tahun=EXCLUDED.tahun,hari=EXCLUDED.hari''')
            cur.execute('''INSERT INTO public.dim_author(nama_penulis)
                SELECT DISTINCT author FROM gold_source ON CONFLICT(nama_penulis) DO NOTHING''')
            cur.execute('''INSERT INTO public.dim_topic(nama_topik,kategori)
                SELECT DISTINCT topic,category FROM gold_source
                ON CONFLICT(nama_topik,kategori) DO NOTHING''')
            cur.execute('''INSERT INTO public.dim_article
                (article_id,judul,url,tags,content_nlp,nlp_status,loaded_at)
                SELECT article_id,title,url,tags,content_nlp,nlp_status,now() FROM gold_source
                ON CONFLICT(article_id) DO UPDATE SET judul=EXCLUDED.judul,url=EXCLUDED.url,
                tags=EXCLUDED.tags,content_nlp=EXCLUDED.content_nlp,
                nlp_status=EXCLUDED.nlp_status,loaded_at=EXCLUDED.loaded_at''')
            cur.execute('''INSERT INTO public.fact_news
                (id_article,id_date,id_topic,id_author,published_at,jumlah_berita)
                SELECT a.id_article,s.id_date,t.id_topic,p.id_author,s.published_at,1
                FROM gold_source s JOIN public.dim_article a USING(article_id)
                JOIN public.dim_topic t ON t.nama_topik=s.topic AND t.kategori=s.category
                JOIN public.dim_author p ON p.nama_penulis=s.author
                ON CONFLICT(id_article) DO UPDATE SET id_date=EXCLUDED.id_date,
                id_topic=EXCLUDED.id_topic,id_author=EXCLUDED.id_author,
                published_at=EXCLUDED.published_at,jumlah_berita=1''')
            cur.execute('''SELECT count(*) FROM gold_source s
                JOIN public.v_news_dashboard v USING(article_id)
                WHERE v.judul=s.title AND v.url=s.url AND v.tanggal=s.tanggal
                  AND v.kategori=s.category AND v.nama_topik=s.topic
                  AND v.nama_penulis=s.author AND v.published_at=s.published_at
                  AND v.tags=s.tags AND v.nlp_status=s.nlp_status
                  AND v.content_nlp IS NOT DISTINCT FROM s.content_nlp''')
            verified = cur.fetchone()[0]
            if verified != len(rows):
                raise RuntimeError('Verifikasi Gold gagal; transaksi dibatalkan')
    print(f'Gold: {verified} artikel Silver dimuat dan diverifikasi.', flush=True)
    return verified


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Muat semua kategori Silver ke Gold.')
    parser.add_argument('--gold', action='store_true', required=True)
    parser.parse_args()
    load_gold()


def ingest_raw_pages():
    """DAG 1: simpan JSON mentah ke Bronze tanpa preprocessing."""
    import json
    import psycopg2
    from psycopg2.extras import Json, execute_values
    source = Path(__file__).resolve().parents[3] / 'output/pages/raw.json'
    rows = json.loads(source.read_text(encoding='utf-8-sig'))
    if len({r['urlhash'] for r in rows}) != len(rows):
        raise ValueError('Duplikasi identitas pada JSON sumber')
    with closing(psycopg2.connect(dbname='bronze', user='l1', port=5441, **connection_options())) as conn:
        with conn, conn.cursor() as cur:
            execute_values(cur, '''INSERT INTO public.articles(urlhash,payload) VALUES %s
                ON CONFLICT(urlhash) DO UPDATE SET payload=EXCLUDED.payload,ingested_at=now()''',
                [(r['urlhash'], Json(r)) for r in rows], page_size=250)
    print(f'Bronze: {len(rows)} artikel mentah tersimpan')
