-- Untuk database yang sudah memakai tabel fakta lama. Aman dijalankan ulang.
BEGIN;
DO $$
BEGIN
    IF to_regclass('gold.fact_national_news') IS NOT NULL THEN
        IF to_regclass('gold.fact_news') IS NOT NULL THEN
            RAISE EXCEPTION 'Kedua tabel fakta ada; periksa sebelum migrasi.';
        END IF;
        ALTER TABLE gold.fact_national_news RENAME TO fact_news;
    ELSIF to_regclass('gold.fact_news') IS NULL THEN
        RAISE EXCEPTION 'Tabel fakta belum ada; jalankan inisialisasi database.';
    END IF;
END $$;
COMMIT;
