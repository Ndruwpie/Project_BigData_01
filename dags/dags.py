import pendulum
from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator


def crawl_raw():
    from script.crawling.main import crawl_pages
    crawl_pages(raw_only=True)


def ingest_bronze():
    from script.storage.warehouse_ingestion import ingest_raw_pages
    ingest_raw_pages()


def clean_silver():
    from script.preprocessing.preprocessing import refresh_silver
    refresh_silver()


def nlp_silver():
    from script.preprocessing.preprocessing import run_nlp
    run_nlp(incremental=True)


def gold_load():
    from script.storage.warehouse_ingestion import load_gold
    load_gold()


def analytics():
    from script.analytics.analytics import build_analytics
    build_analytics()


COMMON = dict(start_date=pendulum.datetime(2026,11,16,tz='Asia/Jakarta'),
              catchup=False, max_active_runs=1, max_active_tasks=1,
              is_paused_upon_creation=False, tags=['tribunnews','semua-kategori'])

with DAG('news_1_crawling_ingestion', schedule='0 * * * *',
         description='Crawl 10 halaman ke JSON dan Bronze', **COMMON) as crawling_dag:
    crawl = PythonOperator(task_id='crawl_raw_json', python_callable=crawl_raw, do_xcom_push=False)
    ingest = PythonOperator(task_id='ingest_bronze', python_callable=ingest_bronze, do_xcom_push=False)
    trigger = TriggerDagRunOperator(task_id='trigger_etl', trigger_dag_id='news_2_etl_warehouse',
        trigger_run_id='etl__{{ run_id }}', wait_for_completion=True, deferrable=True,
        skip_when_already_exists=False)
    crawl >> ingest >> trigger

with DAG('news_2_etl_warehouse', schedule=None,
         description='Validasi dan pembersihan Bronze ke Silver, NLP, star schema Gold', **COMMON) as etl_dag:
    clean = PythonOperator(task_id='clean_silver', python_callable=clean_silver, do_xcom_push=False)
    nlp = PythonOperator(task_id='nlp_silver', python_callable=nlp_silver, do_xcom_push=False)
    gold = PythonOperator(task_id='load_gold', python_callable=gold_load, do_xcom_push=False)
    trigger = TriggerDagRunOperator(task_id='trigger_analytics', trigger_dag_id='news_3_data_analytics',
        trigger_run_id='analytics__{{ run_id }}', wait_for_completion=True, deferrable=True,
        skip_when_already_exists=False)
    clean >> nlp >> gold >> trigger

with DAG('news_3_data_analytics', schedule=None,
         description='Agregasi tren, topik, waktu dan TF-IDF dari Gold', **COMMON) as analytics_dag:
    PythonOperator(task_id='compute_analytics', python_callable=analytics, do_xcom_push=False)
