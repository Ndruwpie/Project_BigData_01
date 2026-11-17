-- Jalankan pada database Silver. content tetap berupa kalimat bersih.
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS nlp_stages JSONB;
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS content_nlp TEXT;
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS nlp_processed_at TIMESTAMPTZ;
