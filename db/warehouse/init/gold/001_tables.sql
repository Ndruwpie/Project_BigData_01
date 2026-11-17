CREATE TABLE public.dim_date (
    id_date INTEGER PRIMARY KEY,
    tanggal DATE NOT NULL UNIQUE,
    bulan INTEGER NOT NULL CHECK (bulan BETWEEN 1 AND 12),
    tahun INTEGER NOT NULL,
    hari TEXT NOT NULL
);
CREATE TABLE public.dim_topic (
    id_topic BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nama_topik TEXT NOT NULL,
    kategori TEXT NOT NULL,
    UNIQUE (nama_topik, kategori)
);
CREATE TABLE public.dim_author (
    id_author BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nama_penulis TEXT NOT NULL UNIQUE
);
CREATE TABLE public.dim_article (
    id_article BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    article_id TEXT NOT NULL UNIQUE,
    judul TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE
);
-- Grain: satu baris per artikel, satu topik utama, satu identitas penulis.
-- ETL memuat semua kategori; dim_topic.kategori berasal dari silver.category.
CREATE TABLE public.fact_news (
    id_article BIGINT PRIMARY KEY REFERENCES public.dim_article(id_article),
    id_date INTEGER NOT NULL REFERENCES public.dim_date(id_date),
    id_topic BIGINT NOT NULL REFERENCES public.dim_topic(id_topic),
    id_author BIGINT NOT NULL REFERENCES public.dim_author(id_author),
    published_at TIMESTAMPTZ NOT NULL,
    jumlah_berita INTEGER NOT NULL DEFAULT 1 CHECK (jumlah_berita = 1)
);
CREATE INDEX ON public.fact_news(id_date);
CREATE INDEX ON public.fact_news(id_topic);
CREATE INDEX ON public.fact_news(id_author);
