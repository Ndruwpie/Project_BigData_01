"""Dashboard analitik Tribunnews multi-kategori dari PostgreSQL Gold.

Jalankan dari root proyek:
    python -m streamlit run dashboard/app.py

Dependensi: streamlit, pandas, plotly, psycopg2-binary, scikit-learn.
Sumber: public.v_news_dashboard pada database gold.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date
from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg2
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dags"))
from script.storage.warehouse_ingestion import connection_options  # noqa: E402

st.set_page_config(page_title="Tribunnews Intelligence | Analytics", page_icon="📰", layout="wide", initial_sidebar_state="expanded")

COLORS = ["#2563EB", "#0EA5E9", "#10B981", "#F59E0B", "#8B5CF6", "#EC4899", "#64748B", "#14B8A6"]
DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], [data-testid="stAppViewContainer"] {font-family:'DM Sans',sans-serif;}
.stApp {background:#F4F7FC;color:#14233D;}
[data-testid="stSidebar"] {background:#101E39;}
[data-testid="stSidebar"] * {color:#EDF3FF;}
[data-testid="stSidebar"] input {color:#14233D !important;}
[data-testid="stSidebar"] [data-baseweb="select"] * {color:#14233D;}
[data-testid="stSidebar"] [data-testid="stDateInput"] input {color:#14233D !important;}
[data-testid="stHeader"] {background:transparent;}
.block-container {padding-top:1.7rem;max-width:1600px;padding-bottom:3rem;}
.hero {background:linear-gradient(115deg,#101F42,#164A99 64%,#1685DA);color:#fff;padding:29px 33px;border-radius:22px;box-shadow:0 12px 32px rgba(23,65,139,.15);margin-bottom:20px;}
.hero .eyebrow {font-size:12px;font-weight:800;letter-spacing:2.3px;color:#A8D9FF;}
.hero h1 {font-size:34px;letter-spacing:-.8px;margin:8px 0;color:#fff;font-weight:800;}
.hero p {color:#D7E9FF;margin:0;font-size:14px;}
[data-testid="stMetric"] {background:#fff;border:1px solid #E3EAF5;border-radius:16px;padding:17px 19px;box-shadow:0 3px 14px rgba(24,54,98,.04);}
[data-testid="stMetricLabel"] {color:#64748B;}
[data-testid="stMetricValue"] {color:#183C7A;font-weight:800;}
[data-testid="stVerticalBlockBorderWrapper"]>div {border-radius:18px;border-color:#E2EAF5;background:#fff;}
h1,h2,h3 {letter-spacing:-.4px;}
.small-note {font-size:12px;color:#64748B;}
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=600, show_spinner="Mengambil data dari PostgreSQL Gold...")
def load_data() -> pd.DataFrame:
    query = """SELECT article_id, judul, url, tanggal, minggu, hari_ke, jam, kategori,
                      nama_topik, nama_penulis, content_nlp, nlp_status, loaded_at
               FROM public.v_news_dashboard
               ORDER BY tanggal, article_id"""
    with closing(psycopg2.connect(dbname="gold", user="l3", port=5443, **connection_options())) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = [col.name for col in cur.description]
    df = pd.DataFrame(rows, columns=columns)
    if df.empty:
        return df
    df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce").dt.date
    df["minggu"] = pd.to_datetime(df["minggu"], errors="coerce").dt.date
    df["hari_ke"] = pd.to_numeric(df["hari_ke"], errors="coerce")
    df["jam"] = pd.to_numeric(df["jam"], errors="coerce")
    for column in ("kategori", "nama_topik", "nama_penulis", "content_nlp", "nlp_status", "judul", "url"):
        df[column] = df[column].fillna("").astype(str)
    df["kategori"] = df["kategori"].replace("", "Tidak diketahui")
    df["nama_topik"] = df["nama_topik"].replace("", "Tidak diketahui")
    df["nama_penulis"] = df["nama_penulis"].replace("", "Tidak diketahui")
    return df.dropna(subset=["tanggal"])


@st.cache_data(ttl=600, max_entries=16, show_spinner="Menghitung kata kunci TF-IDF...")
def get_keywords(texts: tuple[str, ...], top_n: int = 15) -> pd.DataFrame:
    if not texts:
        return pd.DataFrame(columns=["Kata", "Skor"])
    try:
        vectorizer = TfidfVectorizer(max_features=20000, token_pattern=r"(?u)\b[^\W\d_]{2,}\b")
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return pd.DataFrame(columns=["Kata", "Skor"])
    mean_scores = matrix.mean(axis=0).A1
    return (pd.DataFrame({"Kata": vectorizer.get_feature_names_out(), "Skor": mean_scores})
            .nlargest(top_n, "Skor"))


def render_chart(fig: go.Figure, height: int = 345) -> None:
    fig.update_layout(
        template="plotly_white", height=height,
        margin=dict(l=14, r=12, t=18, b=15),
        font=dict(family="DM Sans, sans-serif", color="#253A59", size=12),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="left", x=0),
        hoverlabel=dict(bgcolor="white"),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#EDF2F9", zeroline=False)
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def panel_title(title: str, explanation: str) -> None:
    st.subheader(title)
    st.caption(explanation)


with st.sidebar:
    st.markdown("## 📰 Tribunnews")
    st.caption("INTELLIGENCE · GOLD WAREHOUSE")
    st.divider()
    st.markdown("**Navigasi analisis**")
    page = st.radio("Halaman", ["Ringkasan", "Kategori & Topik", "Kata Kunci", "Pola Publikasi", "Penulis & Kualitas", "Data Artikel"], label_visibility="collapsed")
    st.divider()
    if st.button("↻ Segarkan dari PostgreSQL", use_container_width=True):
        load_data.clear()
        get_keywords.clear()
        st.rerun()

try:
    data = load_data()
except (psycopg2.Error, ValueError, OSError, ImportError) as exc:
    st.error("Tidak dapat membaca PostgreSQL Gold. Periksa Docker, koneksi, kredensial, dan view public.v_news_dashboard.")
    with st.expander("Detail teknis"):
        st.code(str(exc))
    st.stop()
if data.empty:
    st.warning("Belum ada artikel bertanggal valid di Gold. Jalankan pipeline Silver → Gold terlebih dahulu.")
    st.stop()

min_date, max_date = data["tanggal"].min(), data["tanggal"].max()
with st.sidebar:
    st.markdown("### Filter global")
    date_range = st.date_input("Rentang tanggal publikasi", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    if not isinstance(date_range, (list, tuple)) or len(date_range) != 2:
        st.info("Pilih tanggal awal dan akhir.")
        st.stop()
    start, end = date_range
    if start > end:
        st.warning("Tanggal awal harus lebih kecil atau sama dengan tanggal akhir.")
        st.stop()
    categories = sorted(data["kategori"].unique().tolist())
    selected_categories = st.multiselect("Kategori berita", categories, default=categories, help="Kosongkan untuk memilih ulang. Pilih Nasional saja untuk analisis Nasional.")
    if not selected_categories:
        st.info("Pilih minimal satu kategori.")
        st.stop()
    prefiltered = data[data["kategori"].isin(selected_categories) & data["tanggal"].between(start, end)].copy()
    topic_options = sorted(prefiltered["nama_topik"].unique().tolist())
    selected_topics = st.multiselect("Topik / tag utama", topic_options, default=[], placeholder="Semua topik (default)", help="Kosong = semua topik pada kategori dan periode yang dipilih")
    st.caption("Filter diterapkan pada semua halaman. Jam publikasi mengikuti data WIB di Gold.")

filtered = prefiltered if not selected_topics else prefiltered[prefiltered["nama_topik"].isin(selected_topics)].copy()

st.markdown("""<div class="hero"><div class="eyebrow">NEWS ANALYTICS · POSTGRESQL GOLD</div>
<h1>Tribunnews Intelligence Dashboard</h1>
<p>Eksplorasi tren publikasi, perbandingan kategori, perkembangan topik, kata kunci, dan kualitas data berita.</p></div>""", unsafe_allow_html=True)
st.caption(f"Periode: {start:%d %b %Y} – {end:%d %b %Y}  ·  Kategori: {len(selected_categories)} terpilih  ·  Topik: {'Semua' if not selected_topics else len(selected_topics)}  ·  Halaman: {page}")
st.caption("Dataset mencakup artikel yang berhasil di-crawl dan dimuat ke Gold, bukan seluruh publikasi Tribunnews. Topik berasal dari tag utama pada data Gold, bukan klasifikasi semantik otomatis.")
if filtered.empty:
    st.info("Tidak ada artikel sesuai filter. Coba perluas periode, kategori, atau topik.")
    st.stop()

filtered = filtered.drop_duplicates(subset=["article_id"])
n_days = (end - start).days + 1
n_articles = filtered["article_id"].nunique()
valid_authors = filtered[~filtered["nama_penulis"].str.casefold().isin(["tidak diketahui", "unknown", "-"])]
metrics = [
    ("Total artikel unik", f"{n_articles:,}"),
    ("Rata-rata artikel/hari", f"{n_articles/n_days:,.1f}"),
    ("Kategori aktif", f"{filtered['kategori'].nunique():,}"),
    ("Topik / tag unik", f"{filtered['nama_topik'].nunique():,}"),
    ("Identitas penulis", f"{valid_authors['nama_penulis'].nunique():,}"),
]
metric_cols = st.columns(5)
for col, (label, value) in zip(metric_cols, metrics):
    col.metric(label, value)

# View Gold diasumsikan satu baris per artikel; deduplikasi dilakukan sebelum KPI dan grafik.
if page == "Ringkasan":
    st.markdown("### Ikhtisar publikasi")
    left, right = st.columns([1.55, 1])
    with left, st.container(border=True):
        panel_title("Tren jumlah berita", "Perubahan volume artikel sepanjang periode terpilih; hari tanpa artikel ditampilkan sebagai nol.")
        granularity = st.segmented_control("Agregasi", ["Harian", "Mingguan", "Bulanan"], default="Bulanan")
        times = pd.to_datetime(filtered["tanggal"])
        if granularity == "Harian":
            series = times.value_counts().sort_index().reindex(pd.date_range(start, end, freq="D"), fill_value=0)
        elif granularity == "Mingguan":
            series = times.dt.to_period("W-SUN").dt.start_time.value_counts().sort_index()
        else:
            series = times.dt.to_period("M").dt.to_timestamp().value_counts().sort_index()
        trend = series.rename_axis("Tanggal").reset_index(name="Artikel")
        fig = px.area(trend, x="Tanggal", y="Artikel", color_discrete_sequence=[COLORS[0]], markers=True)
        fig.update_traces(line=dict(width=3), fillcolor="rgba(37,99,235,.12)")
        render_chart(fig)
    with right, st.container(border=True):
        panel_title("Distribusi kategori", "Proporsi artikel menurut kategori resmi yang tercatat di Gold.")
        cats = filtered["kategori"].value_counts()
        cat_data = cats.head(7).rename_axis("Kategori").reset_index(name="Artikel")
        if len(cats) > 7:
            cat_data = pd.concat([cat_data, pd.DataFrame([{"Kategori": "Kategori lain", "Artikel": int(cats.iloc[7:].sum())}])], ignore_index=True)
        fig = px.pie(cat_data, names="Kategori", values="Artikel", hole=.64, color_discrete_sequence=COLORS)
        fig.update_traces(textinfo="percent", hovertemplate="%{label}<br>%{value} artikel (%{percent})<extra></extra>")
        render_chart(fig)
    left, right = st.columns(2)
    with left, st.container(border=True):
        panel_title("Topik / tag teratas", "Topik paling banyak muncul pada artikel hasil crawling.")
        tops = filtered["nama_topik"].value_counts().head(10).sort_values()
        fig = px.bar(x=tops.values, y=tops.index, orientation="h", labels={"x": "Artikel", "y": "Topik"}, color_discrete_sequence=[COLORS[0]])
        render_chart(fig)
    with right, st.container(border=True):
        panel_title("Perbandingan kategori per bulan", "Membandingkan dinamika kategori teratas sepanjang periode.")
        leading = filtered["kategori"].value_counts().head(5).index
        sub = filtered[filtered["kategori"].isin(leading)].copy()
        sub["Bulan"] = pd.to_datetime(sub["tanggal"]).dt.to_period("M").dt.to_timestamp()
        grouped = sub.groupby(["Bulan", "kategori"]).size().reset_index(name="Artikel")
        fig = px.line(grouped, x="Bulan", y="Artikel", color="kategori", markers=True, color_discrete_sequence=COLORS, labels={"kategori": "Kategori"})
        render_chart(fig)

elif page == "Kategori & Topik":
    st.markdown("### Analisis kategori dan topik")
    left, right = st.columns(2)
    with left, st.container(border=True):
        panel_title("Peringkat kategori", "Kategori mana yang memiliki artikel terbanyak?")
        c = filtered["kategori"].value_counts().head(15).sort_values()
        render_chart(px.bar(x=c.values, y=c.index, orientation="h", labels={"x": "Jumlah artikel", "y": "Kategori"}, color_discrete_sequence=[COLORS[0]]), 430)
    with right, st.container(border=True):
        panel_title("Distribusi topik", "Topik paling dominan di seluruh kategori yang dipilih.")
        c = filtered["nama_topik"].value_counts()
        top_df = c.head(9).rename_axis("Topik").reset_index(name="Artikel")
        if len(c) > 9:
            top_df = pd.concat([top_df, pd.DataFrame([{"Topik": "Topik lainnya", "Artikel": int(c.iloc[9:].sum())}])], ignore_index=True)
        render_chart(px.pie(top_df, names="Topik", values="Artikel", hole=.55, color_discrete_sequence=COLORS), 430)
    with st.container(border=True):
        panel_title("Perkembangan topik per minggu", "Enam topik paling sering muncul pada periode dan kategori terpilih.")
        top6 = filtered["nama_topik"].value_counts().head(6).index.tolist()
        temp = filtered[filtered["nama_topik"].isin(top6)].copy()
        temp["Awal minggu"] = pd.to_datetime(temp["tanggal"]).dt.to_period("W-SUN").dt.start_time
        group = temp.groupby(["Awal minggu", "nama_topik"]).size().reset_index(name="Artikel")
        render_chart(px.line(group, x="Awal minggu", y="Artikel", color="nama_topik", markers=True, color_discrete_sequence=COLORS, labels={"nama_topik": "Topik"}), 390)
    with st.container(border=True):
        panel_title("Topik dominan per kategori", "Tabel perbandingan tag utama yang paling sering muncul pada setiap kategori.")
        cross = pd.crosstab(filtered["kategori"], filtered["nama_topik"])
        st.dataframe(cross.loc[:, cross.sum().nlargest(12).index], use_container_width=True)

elif page == "Kata Kunci":
    st.markdown("### Analisis kata kunci dominan")
    eligible = filtered[(filtered["nlp_status"].str.casefold() == "completed") & filtered["content_nlp"].str.strip().ne("")]
    st.info(f"{len(eligible):,} dari {len(filtered):,} artikel memiliki teks NLP dengan status completed. TF-IDF dihitung ulang dari artikel sesuai filter.")
    terms = get_keywords(tuple(eligible["content_nlp"].tolist()))
    if terms.empty:
        st.warning("Tidak tersedia cukup teks NLP untuk menghitung TF-IDF pada filter ini.")
    else:
        left, right = st.columns([1.5, 1])
        with left, st.container(border=True):
            panel_title("15 kata kunci dengan skor TF-IDF tertinggi", "Skor adalah rata-rata TF-IDF per artikel, bukan frekuensi kemunculan mentah.")
            render_chart(px.bar(terms.sort_values("Skor"), x="Skor", y="Kata", orientation="h", color_discrete_sequence=[COLORS[0]]), 500)
        with right, st.container(border=True):
            panel_title("Tabel skor TF-IDF", "Nilai yang lebih tinggi menunjukkan bobot relatif yang lebih besar dalam korpus terfilter.")
            st.dataframe(terms, hide_index=True, use_container_width=True)
            st.download_button("Unduh skor TF-IDF (CSV)", terms.to_csv(index=False).encode("utf-8-sig"), "tribunnews_tfidf.csv", "text/csv", use_container_width=True)
    st.caption("Interpretasi TF-IDF bergantung pada kualitas preprocessing, stopword, dan korpus yang dipilih. Topik/tag bukan hasil TF-IDF.")

elif page == "Pola Publikasi":
    st.markdown("### Pola waktu publikasi")
    valid = filtered[filtered["hari_ke"].between(1, 7) & filtered["jam"].between(0, 23)].copy()
    if valid.empty:
        st.warning("Data hari/jam publikasi tidak tersedia pada filter ini.")
    else:
        with st.container(border=True):
            panel_title("Heatmap hari dan jam", "Menunjukkan waktu dengan frekuensi publikasi tertinggi dalam WIB.")
            heat = (valid.groupby(["hari_ke", "jam"]).size().unstack(fill_value=0)
                    .reindex(index=range(1, 8), columns=range(24), fill_value=0))
            fig = go.Figure(go.Heatmap(z=heat.values, x=list(range(24)), y=DAY_NAMES,
                                       colorscale=[[0, "#E8F2FF"], [.4, "#79B5F7"], [1, "#174BA7"]],
                                       hovertemplate="%{y} pukul %{x}:00 WIB<br>%{z} artikel<extra></extra>"))
            fig.update_xaxes(title="Jam publikasi (WIB)", dtick=1)
            fig.update_yaxes(autorange="reversed")
            render_chart(fig, 390)
        left, right = st.columns(2)
        with left, st.container(border=True):
            panel_title("Artikel per hari", "Hari apa yang paling aktif?")
            by_day = valid.groupby("hari_ke").size().reindex(range(1, 8), fill_value=0)
            render_chart(px.bar(x=DAY_NAMES, y=by_day.values, labels={"x": "Hari", "y": "Artikel"}, color_discrete_sequence=[COLORS[0]]))
        with right, st.container(border=True):
            panel_title("Artikel per jam", "Jam publikasi paling ramai.")
            by_hour = valid.groupby("jam").size().reindex(range(24), fill_value=0)
            render_chart(px.bar(x=by_hour.index, y=by_hour.values, labels={"x": "Jam (WIB)", "y": "Artikel"}, color_discrete_sequence=[COLORS[1]]))

elif page == "Penulis & Kualitas":
    st.markdown("### Produktivitas penulis dan kualitas data")
    left, right = st.columns(2)
    with left, st.container(border=True):
        panel_title("Penulis terproduktif", "Penulis dengan jumlah artikel terbesar pada filter aktif.")
        authors = valid_authors["nama_penulis"].value_counts().head(15).sort_values()
        if authors.empty:
            st.info("Tidak ada identitas penulis yang diketahui.")
        else:
            render_chart(px.bar(x=authors.values, y=authors.index, orientation="h", labels={"x": "Artikel", "y": "Penulis"}, color_discrete_sequence=[COLORS[0]]), 470)
    with right, st.container(border=True):
        panel_title("Kelengkapan metadata", "Persentase artikel dengan metadata tersedia, bukan penilaian kebenaran konten.")
        quality = pd.DataFrame([
            ("Judul", filtered["judul"].str.strip().ne("").mean() * 100),
            ("URL", filtered["url"].str.strip().ne("").mean() * 100),
            ("Kategori", (~filtered["kategori"].str.casefold().eq("tidak diketahui")).mean() * 100),
            ("Topik/tag", (~filtered["nama_topik"].str.casefold().eq("tidak diketahui")).mean() * 100),
            ("Penulis", len(valid_authors) / len(filtered) * 100),
            ("Teks NLP selesai", ((filtered["nlp_status"].str.casefold() == "completed") & filtered["content_nlp"].str.strip().ne("")).mean() * 100),
        ], columns=["Atribut", "Persentase"])
        fig = px.bar(quality, x="Persentase", y="Atribut", orientation="h", range_x=[0, 100], color_discrete_sequence=[COLORS[2]])
        render_chart(fig, 470)
    with st.container(border=True):
        panel_title("Status NLP", "Jumlah artikel berdasarkan status pemrosesan teks.")
        statuses = filtered["nlp_status"].replace("", "Tidak diketahui").value_counts().rename_axis("Status").reset_index(name="Artikel")
        st.dataframe(statuses, hide_index=True, use_container_width=True)

else:
    st.markdown("### Eksplorasi artikel sumber")
    st.caption("Tabel menampilkan artikel dari PostgreSQL Gold yang sesuai dengan seluruh filter global.")
    query = st.text_input("Cari judul artikel", placeholder="Ketik kata dalam judul...")
    shown = filtered[filtered["judul"].str.contains(query, case=False, regex=False, na=False)] if query else filtered
    shown = shown.sort_values("tanggal", ascending=False)
    columns = ["tanggal", "judul", "kategori", "nama_topik", "nama_penulis", "url", "nlp_status"]
    st.dataframe(shown[columns], hide_index=True, use_container_width=True, height=530,
                 column_config={"url": st.column_config.LinkColumn("Tautan artikel")})
    st.download_button("⬇ Unduh artikel terfilter (CSV)", shown[columns].to_csv(index=False).encode("utf-8-sig"),
                       "tribunnews_artikel_terfilter.csv", "text/csv", use_container_width=True)

latest = pd.to_datetime(data["loaded_at"], errors="coerce", utc=True).max()
if pd.notna(latest):
    st.caption(f"Gold terakhir dimuat: {latest.tz_convert('Asia/Jakarta'):%d %b %Y %H:%M} WIB · Cache hingga 10 menit · Gunakan Segarkan dari PostgreSQL untuk pembaruan manual.")
else:
    st.caption("Timestamp pemuatan Gold tidak tersedia · Cache hingga 10 menit.")
