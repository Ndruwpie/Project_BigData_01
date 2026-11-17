# Warehouse: tiga PostgreSQL terpisah

Gunakan compose.yaml di folder ini. Project baru tribun-warehouse-v3 memakai
volume baru untuk setiap lapisan. Container warehouse v2 serta data lamanya
tidak dihapus atau dipindahkan otomatis. Jangan menjalankan db/docker-compose.yaml
bersamaan jika port yang sama digunakan.

Dari root proyek:

```powershell
docker compose --env-file db/warehouse/.env -f db/warehouse/compose.yaml up -d --wait
docker compose --env-file db/warehouse/.env -f db/warehouse/compose.yaml ps
```

Daftarkan tiga server di pgAdmin, semuanya host localhost:

| Server | Port | Database | User |
|---|---|---|---|
| Bronze | 5441 | bronze | l1 |
| Silver | 5442 | silver | l2 |
| Gold | 5443 | gold | l3 |

Password ketiganya memakai POSTGRES_PASSWORD dari .env folder ini.
Nama container otomatis memiliki prefix project untuk menghindari bentrok.
Tabel berada pada schema public masing-masing database.

- Bronze: articles, menyimpan payload JSON asli semua kategori.
- Silver: articles, menyimpan artikel bersih dan identitas unik.
- Gold: dim_date, dim_topic, dim_author, dim_article, fact_news, semua kategori.

SQL init aktif ada di init/bronze, init/silver, dan init/gold. File
init/001_schema.sql serta migrations/002_all_categories.sql adalah untuk
arsitektur v2 satu database dan tidak digunakan compose baru.

Foreign key antardatabase dihapus; ETL harus memvalidasi urlhash bronze ke
silver dan article_id silver ke gold. Foreign key antartabel dalam gold tetap
berlaku. Grain fakta satu baris per artikel dengan jumlah_berita = 1.
Kategori berada di dim_topic.kategori; tentukan satu topik utama per artikel.
Timestamp publikasi tersedia untuk analisis hari dan jam WIB.

Init berjalan hanya pada volume kosong. Jangan hapus volume untuk memperbarui
schema; gunakan migrasi. Ingestion, preprocessing, dan pemuatan Gold terhubung ke Airflow.

## Pipeline Gold untuk dashboard

Airflow terdiri dari tiga DAG untuk semua kategori:
1. `news_1_crawling_ingestion`: setiap jam pada menit 00 (WIB), crawl 10 halaman ke JSON lalu Bronze.
2. `news_2_etl_warehouse`: dipicu DAG 1, pembersihan Silver, NLP incremental, lalu Gold.
3. `news_3_data_analytics`: dipicu DAG 2, agregasi harian/mingguan/topik/jam dan TF-IDF.

Trigger menunggu DAG berikutnya dengan mode deferrable; satu run aktif per DAG.
DAG 2 dan 3 tidak memiliki cron terpisah. Kegagalan upstream mencegah trigger berikutnya.
DAG lama `dags_scraping` dipause; riwayatnya tetap tersedia. Jika task trigger perlu
 dicoba ulang dan run tujuan sudah ada, perbaiki/clear run tujuan terlebih dahulu;
run ID deterministik mencegah membuat salinan run secara tidak sengaja.

Analitik terjadwal disimpan atomik di `output/analytics/latest.json` (beserta backup).
TF-IDF batch memakai semua kosakata, smooth IDF, normalisasi L2 dan rata-rata dokumen
NLP selesai. Streamlit tetap membaca Gold serta menghitung TF-IDF sesuai filter
(dengan batas 20.000 fitur), sehingga skor batch dan dashboard dapat berbeda.
Grafik interaktif tetap dibuat oleh Streamlit/Plotly, bukan sebagai PNG oleh DAG 3.
Loader berada di dags/script/storage/warehouse_ingestion.py; manual:
`python dags/script/storage/warehouse_ingestion.py --gold`.
Migrasi 004_gold_dashboard.sql otomatis dijalankan loader. Gold memakai port 5443,
database gold, user l3, password dari .env warehouse.

Satu fakta per artikel, semua kategori Silver, upsert atomik dan aman dijalankan ulang.
Baris lama yang tidak ada lagi di Silver tidak dihapus otomatis. Topik utama adalah
TAG PERTAMA (fallback kategori), bukan klasifikasi subtopik simulasi pada contoh HTML.
Penulis gabungan dihitung sebagai satu identitas; kecualikan 'Tidak diketahui' dari KPI penulis.

View Streamlit:
- v_news_dashboard: detail artikel, kategori, topik, penulis, waktu dan content_nlp.
- v_news_daily: jumlah harian per kategori/topik.
- v_news_weekly: jumlah mingguan (Senin) per kategori/topik.
- v_news_publication_time: jumlah per hari dalam minggu dan jam WIB.

Semua artikel ikut statistik berita, termasuk NLP blocked. TF-IDF hanya memakai
content_nlp dengan nlp_status='completed'; skornya dihitung oleh dashboard sesuai
filter/periode, belum dihitung di Gold. Rata-rata harian perlu menyertakan hari nol artikel.

```sql
SELECT kategori, count(*) AS artikel,
       count(*) FILTER (WHERE nlp_status='completed') AS nlp_selesai
FROM public.v_news_dashboard GROUP BY kategori ORDER BY artikel DESC;
```
