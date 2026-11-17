-- Raw JSON dipertahankan untuk semua kategori yang berhasil dicrawl.
CREATE TABLE public.articles (
    urlhash TEXT PRIMARY KEY,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

