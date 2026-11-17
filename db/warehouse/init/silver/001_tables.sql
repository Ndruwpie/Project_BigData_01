CREATE TABLE public.articles (
    article_id TEXT PRIMARY KEY,
    urlhash TEXT NOT NULL UNIQUE,
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

