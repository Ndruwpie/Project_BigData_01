CREATE SCHEMA bronze;
CREATE SCHEMA silver;
CREATE SCHEMA gold;

-- Raw JSON dipertahankan untuk semua kategori yang berhasil dicrawl.
CREATE TABLE bronze.articles (
    urlhash TEXT PRIMARY KEY,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE silver.articles (
    article_id TEXT PRIMARY KEY,
    urlhash TEXT NOT NULL UNIQUE REFERENCES bronze.articles(urlhash),
    article_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    author TEXT,
    category TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    published_at TIMESTAMPTZ NOT NULL,
    crawled_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gold.dim_date (
    id_date INTEGER PRIMARY KEY,
    tanggal DATE NOT NULL UNIQUE,
    bulan INTEGER NOT NULL CHECK (bulan BETWEEN 1 AND 12),
    tahun INTEGER NOT NULL,
    hari TEXT NOT NULL
);
CREATE TABLE gold.dim_topic (
    id_topic BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nama_topik TEXT NOT NULL,
    kategori TEXT NOT NULL,
    UNIQUE (nama_topik, kategori)
);
CREATE TABLE gold.dim_author (
    id_author BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nama_penulis TEXT NOT NULL UNIQUE
);
CREATE TABLE gold.dim_article (
    id_article BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    article_id TEXT NOT NULL UNIQUE REFERENCES silver.articles(article_id),
    judul TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE
);
-- Grain: satu baris per artikel, satu topik utama, satu identitas penulis.
-- ETL memuat semua kategori; dim_topic.kategori berasal dari silver.category.
CREATE TABLE gold.fact_news (
    id_article BIGINT PRIMARY KEY REFERENCES gold.dim_article(id_article),
    id_date INTEGER NOT NULL REFERENCES gold.dim_date(id_date),
    id_topic BIGINT NOT NULL REFERENCES gold.dim_topic(id_topic),
    id_author BIGINT NOT NULL REFERENCES gold.dim_author(id_author),
    published_at TIMESTAMPTZ NOT NULL,
    jumlah_berita INTEGER NOT NULL DEFAULT 1 CHECK (jumlah_berita = 1)
);
CREATE INDEX ON gold.fact_news(id_date);
CREATE INDEX ON gold.fact_news(id_topic);
CREATE INDEX ON gold.fact_news(id_author);
