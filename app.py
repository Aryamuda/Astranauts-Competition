import ee
from google.oauth2 import service_account
import streamlit as st
import geopandas as gpd
import geemap.foliumap as geemap
from datetime import datetime, timedelta
import pandas as pd

# PENGATURAN HALAMAN DAN JUDUL APLIKASI
st.set_page_config(layout="wide")
st.title("Smart Grass Maintenance System - Jalan Tol Indonesia")
st.markdown(
    "Sistem Cerdas untuk **Penjadwalan Dinamis**, **Optimasi Sumber Daya**, dan **Analisis Prediktif** pemeliharaan rumput jalan tol.")


# INISIALISASI & FUNGSI PEMUATAN DATA
@st.cache_resource
def initialize_gee():
    try:
        creds_dict = dict(st.secrets["gee_credentials"])
        credentials = service_account.Credentials.from_service_account_info(creds_dict, scopes=[
            'https://www.googleapis.com/auth/earthengine'])
        ee.Initialize(credentials=credentials, opt_url='https://earthengine-highvolume.googleapis.com')
    except Exception as e:
        st.error(f"GAGAL otentikasi GEE. Pastikan 'gee_credentials' di Streamlit secrets benar. Error: {e}")
        st.stop()

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

initialize_gee()
gdf_semua_tol = load_toll_road_data()


# FUNGSI-FUNGSI UTAMA
def run_gee_analysis(aoi, start_date, end_date, cloud_cover, min_ndvi, max_ndvi=1.0):
    try:
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        s2_collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                         .filterBounds(aoi)
                         .filterDate(start_str, end_str)
                         .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_cover)))
        image_count = s2_collection.size()
        if image_count.getInfo() == 0: return None, 0
        median_image = s2_collection.median().clip(aoi)
        ndvi = median_image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        target_vegetation = ndvi.gte(min_ndvi).And(ndvi.lt(max_ndvi))
        sample_points = target_vegetation.selfMask().sample(region=aoi, scale=10, numPixels=500, geometries=True)
        if sample_points.size().getInfo() == 0: return None, image_count.getInfo()
        points_geojson = sample_points.getInfo()
        gdf_koordinat = gpd.GeoDataFrame.from_features(points_geojson['features'], crs="EPSG:4326")
        return gdf_koordinat, image_count.getInfo()
    except Exception as e:
        st.error(f"Error dalam analisis GEE: {str(e)}")
        return None, 0


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

    st.header("Hasil Analisis Pemeliharaan Rumput")
    if gdf_hasil is not None and not gdf_hasil.empty:
        gdf_hasil = gpd.sjoin_nearest(gdf_hasil, gdf_filtered[['ruas', 'geometry']])
        gdf_hasil['longitude'] = gdf_hasil.geometry.x
        gdf_hasil['latitude'] = gdf_hasil.geometry.y
        st.success(f"Berhasil! Ditemukan {len(gdf_hasil)} titik lokasi prioritas.")

        if ndvi_threshold_input >= 0.7:
            priority_level = "URGENT"
        elif ndvi_threshold_input >= 0.6:
            priority_level = "PRIORITAS TINGGI"
        else:
            priority_level = "MONITORING"
        area_ha = len(gdf_hasil) * 0.01

        # Tampilan Tabs
        tab1, tab2, tab3 = st.tabs(["Ringkasan & Peta", "Detail per Ruas", "Dashboard KPI"])

        with tab1:
            col1, col2, col3 = st.columns(3)
            col1.metric("Status Prioritas", priority_level)
            col2.metric("Total Titik", f"{len(gdf_hasil)} titik")
            col3.metric("Estimasi Area", f"{area_ha:.2f} ha")

            peta_interaktif = geemap.Map(center=[gdf_hasil.geometry.y.mean(), gdf_hasil.geometry.x.mean()], zoom=12)
            peta_interaktif.add_gdf(gdf_filtered, layer_name="Jalan Tol")
            peta_interaktif.add_gdf(gdf_hasil, layer_name="Titik Prioritas", style={'color': 'red'})
            peta_interaktif.to_streamlit(height=450)

        with tab2:
            st.subheader("Analisis Kebutuhan per Ruas Tol")
            ruas_summary = gdf_hasil.groupby('ruas').agg(jumlah_titik=('geometry', 'count'),
                                                         estimasi_area_ha=('geometry', lambda x: len(
                                                             x) * 0.01)).reset_index().sort_values('jumlah_titik',
                                                                                                   ascending=False)
            st.dataframe(ruas_summary[['ruas', 'jumlah_titik', 'estimasi_area_ha']], use_container_width=True)
            st.bar_chart(ruas_summary.set_index('ruas')['jumlah_titik'])

        with tab3:
            st.subheader("Dashboard Key Performance Indicator (KPI)")
            col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
            compliance_rate = max(0, 100 - (len(gdf_hasil) / 100))
            col_kpi1.metric("Tingkat Kepatuhan SPM", f"{compliance_rate:.1f}%")
            col_kpi2.metric("Beban Kerja", f"{len(gdf_hasil)} titik")
            col_kpi3.metric("Area Terdampak", f"{area_ha:.2f} ha")
            st.subheader("Grafik Tren Historis Area Pemeliharaan (Simulasi)")
            hist_dates = pd.date_range(end=datetime.now(), periods=12, freq='W')
            hist_data = pd.DataFrame({'Tanggal': hist_dates, 'Estimasi Area (ha)': np.maximum(0,
                                                                                              np.linspace(area_ha * 1.5,
                                                                                                          area_ha,
                                                                                                          12) + np.random.normal(
                                                                                                  0, area_ha * 0.1,
                                                                                                  12))}).set_index('Tanggal')
            st.area_chart(hist_data)
    else:
        st.warning(f"Tidak ditemukan area rumput signifikan (NDVI >= {ndvi_threshold_input}).")
