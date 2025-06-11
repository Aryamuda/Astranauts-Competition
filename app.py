import streamlit as st
import geopandas as gpd
from datetime import datetime, timedelta

# PENGATURAN HALAMAN DAN JUDUL APLIKASI
st.set_page_config(layout="wide")
st.title(" Smart Grass Maintenance System - Jalan Tol Indonesia")
st.markdown("Sistem Cerdas untuk **Penjadwalan Dinamis**, **Optimasi Sumber Daya**, dan **Analisis Prediktif** pemeliharaan rumput jalan tol.")
st.title("Smart Grass Maintenance System - Jalan Tol Indonesia")
st.markdown(
    "Sistem Cerdas untuk **Penjadwalan Dinamis**, **Optimasi Sumber Daya**, dan **Analisis Prediktif** pemeliharaan rumput jalan tol.")

st.info("Selamat datang! Atur parameter di sidebar dan klik 'Analisis' untuk memulai.")

# INISIALISASI & FUNGSI PEMUATAN DATA
@st.cache_data
def load_toll_road_data():
    url = 'https://data.pu.go.id/sites/default/files/geojson/ast_bpjt_tol_operasi.geojson'
    try:
        gdf = gpd.read_file(url)
        required_cols = ['ruas', 'provinsi', 'geometry']
        for col in required_cols:
            if col not in gdf.columns: return None
        return gdf
    except Exception as e:
        st.error(f"Gagal memuat data jalan tol dari sumber. Error: {e}")
        return None


gdf_semua_tol = load_toll_road_data()

# SIDEBAR
with st.sidebar:
    st.header("Parameter Analisis")
    provinsi_input = st.text_input("1. Provinsi", "Banten")

    today = datetime.now()
    start_date_input = st.date_input("2. Tanggal Mulai", today - timedelta(days=30))
    end_date_input = st.date_input("3. Tanggal Selesai", today)

    cloud_cover_input = st.slider("4. Max Tutupan Awan (%)", 0, 100, 20)
    buffer_radius_input = st.number_input("5. Radius Monitoring (meter)", 10, 200, 30, 5)
    ndvi_threshold_input = st.select_slider("6. Prioritas (NDVI)", options=[0.4, 0.5, 0.6, 0.7], value=0.6)

    st.markdown("---")
    run_button = st.button("Analisis Kondisi Rumput", type="primary", use_container_width=True)

# BAGIAN UTAMA
if run_button:
    if gdf_semua_tol is not None:
        gdf_filtered = gdf_semua_tol[gdf_semua_tol['provinsi'].str.contains(provinsi_input, case=False, na=False)]

        if gdf_filtered.empty:
            st.error(f"Tidak ada data jalan tol yang ditemukan untuk Provinsi '{provinsi_input}'.")
        else:
            st.success(
                f"Ditemukan {len(gdf_filtered)} ruas tol di {provinsi_input}. Analisis GEE akan dijalankan di sini.")
            st.dataframe(gdf_filtered[['ruas', 'provinsi']])
    else:
        st.error("Tidak dapat melanjutkan karena data jalan tol gagal dimuat.")
else:
    st.info("Silakan atur parameter di sidebar dan klik 'Analisis Kondisi Rumput' untuk memulai.")