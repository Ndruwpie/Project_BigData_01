-- Tambahan data analitik; satu baris tetap mewakili satu artikel.
ALTER TABLE public.dim_article ADD COLUMN IF NOT EXISTS content_nlp TEXT;
ALTER TABLE public.dim_article ADD COLUMN IF NOT EXISTS nlp_status TEXT;
ALTER TABLE public.dim_article ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE public.dim_article ADD COLUMN IF NOT EXISTS loaded_at TIMESTAMPTZ;

CREATE OR REPLACE VIEW public.v_news_dashboard AS
SELECT a.article_id, a.judul, a.url, d.tanggal, d.hari,
       date_trunc('week', f.published_at AT TIME ZONE 'Asia/Jakarta')::date AS minggu,
       extract(isodow FROM f.published_at AT TIME ZONE 'Asia/Jakarta')::int AS hari_ke,
       extract(hour FROM f.published_at AT TIME ZONE 'Asia/Jakarta')::int AS jam,
       f.published_at, t.kategori, t.nama_topik, p.nama_penulis,
       a.tags, a.content_nlp, a.nlp_status, a.loaded_at, f.jumlah_berita
FROM public.fact_news f
JOIN public.dim_article a USING (id_article)
JOIN public.dim_date d USING (id_date)
JOIN public.dim_topic t USING (id_topic)
JOIN public.dim_author p USING (id_author);

CREATE OR REPLACE VIEW public.v_news_daily AS
SELECT tanggal, kategori, nama_topik, sum(jumlah_berita)::bigint AS jumlah_berita
FROM public.v_news_dashboard GROUP BY tanggal, kategori, nama_topik;

CREATE OR REPLACE VIEW public.v_news_weekly AS
SELECT minggu, kategori, nama_topik, sum(jumlah_berita)::bigint AS jumlah_berita
FROM public.v_news_dashboard GROUP BY minggu, kategori, nama_topik;

CREATE OR REPLACE VIEW public.v_news_publication_time AS
SELECT hari_ke, hari, jam, kategori, sum(jumlah_berita)::bigint AS jumlah_berita
FROM public.v_news_dashboard GROUP BY hari_ke, hari, jam, kategori;
