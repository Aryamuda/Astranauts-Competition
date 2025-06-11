import ee
from google.oauth2 import service_account
import streamlit as st
import geopandas as gpd
import geemap.foliumap as geemap
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from fpdf import FPDF
import matplotlib.pyplot as plt
import os

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
    gdf = gpd.read_file(url)
    required_cols = ['ruas', 'provinsi', 'geometry']
    for col in required_cols:
        if col not in gdf.columns: return None
    return gdf


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

        print(f"Searching for images from {start_str} to {end_str}")
        image_count = s2_collection.size()
        print(f"Found {image_count.getInfo()} images")

        if image_count.getInfo() == 0:
            print("No images found in collection")
            return None, 0
        median_image = s2_collection.median().clip(aoi)
        ndvi = median_image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        target_vegetation = ndvi.gte(min_ndvi).And(ndvi.lt(max_ndvi))

        sample_points = target_vegetation.selfMask().sample(
            region=aoi,
            scale=10,
            numPixels=500,
            geometries=True
        )

        points_count = sample_points.size().getInfo()
        print(f"Generated {points_count} sample points")

        if points_count == 0:
            return None, image_count.getInfo()

        points_geojson = sample_points.getInfo()
        gdf_koordinat = gpd.GeoDataFrame.from_features(points_geojson['features'], crs="EPSG:4326")

        return gdf_koordinat, image_count.getInfo()

    except Exception as e:
        print(f"Error in GEE analysis: {str(e)}")
        st.error(f"Error dalam analisis GEE: {str(e)}")
        return None, 0


def create_pdf_report(summary_stats, gdf_hasil, ruas_summary, static_map_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Laporan Analisis Pemeliharaan Rumput".encode('latin-1', 'replace').decode('latin-1'), 0, 1, 'C')
    pdf.set_font("Arial", '', 11)
    pdf.cell(0, 8, f"Tanggal Laporan: {datetime.now().strftime('%Y-%m-%d')}", 0, 1, 'C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "1. Ringkasan Operasional", 0, 1)
    pdf.set_font("Arial", '', 11)
    for key, value in summary_stats.items():
        clean_key = str(key).encode('ascii', 'ignore').decode('ascii')
        clean_value = str(value).encode('ascii', 'ignore').decode('ascii')
        pdf.cell(0, 8, f"- {clean_key}: {clean_value}", 0, 1)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "2. Peta Sebaran Lokasi", 0, 1)
    if os.path.exists(static_map_path):
        pdf.image(static_map_path, x=10, y=None, w=190)
    pdf.ln(5)
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "3. Detail Beban Kerja per Ruas Tol", 0, 1)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(80, 8, "Nama Ruas", 1)
    pdf.cell(40, 8, "Jumlah Titik", 1)
    pdf.cell(40, 8, "Estimasi Area (ha)", 1)
    pdf.ln()
    pdf.set_font("Arial", '', 9)
    for index, row in ruas_summary.iterrows():
        clean_ruas = str(row['ruas']).encode('ascii', 'ignore').decode('ascii')
        pdf.cell(80, 8, clean_ruas, 1)
        pdf.cell(40, 8, str(row['jumlah_titik']), 1)
        pdf.cell(40, 8, f"{row['estimasi_area_ha']:.2f}", 1)
        pdf.ln()
    pdf.ln(5)
    return bytes(pdf.output(dest='S'))


# SIDEBAR
with st.sidebar:
    st.header("Parameter Analisis")
    provinsi_input = st.text_input("1. Provinsi", "Jakarta")

    today = datetime.now()
    start_date_input = st.date_input("2. Tanggal Mulai", today - timedelta(days=30))
    end_date_input = st.date_input("3. Tanggal Selesai", today)

    cloud_cover_input = st.slider("4. Max Tutupan Awan (%)", 0, 100, 20)
    buffer_radius_input = st.number_input("5. Radius Monitoring (meter)", 10, 200, 30, 5)
    ndvi_threshold_input = st.select_slider("6. Prioritas (NDVI)", options=[0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
                                            value=0.5)

    st.markdown("---")
    run_button = st.button("Analisis Kondisi Rumput", type="primary", use_container_width=True)

# BAGIAN UTAMA
if run_button:
    gdf_filtered = gdf_semua_tol[gdf_semua_tol['provinsi'].str.contains(provinsi_input, case=False, na=False)]
    if gdf_filtered.empty:
        st.error(f"Tidak ada data jalan tol yang ditemukan untuk Provinsi '{provinsi_input}'.")
        st.stop()


    with st.spinner("Menganalisis area prioritas..."):
        try:
            st.write(f"Mencari data satelit untuk {len(gdf_filtered)} ruas tol di {provinsi_input}")
            st.write(f"Periode: {start_date_input} sampai {end_date_input}")

            aoi_main = geemap.geopandas_to_ee(gdf_filtered).geometry().dissolve().buffer(buffer_radius_input)

            bounds = aoi_main.bounds().getInfo()

            gdf_hasil, img_count = run_gee_analysis(aoi_main, start_date_input, end_date_input, cloud_cover_input,
                                                    ndvi_threshold_input)

            st.write(f"Ditemukan {img_count} citra satelit")

            if gdf_hasil is not None and len(gdf_hasil) > 0:
                gdf_hasil = gpd.sjoin_nearest(gdf_hasil, gdf_filtered[['ruas', 'geometry']])
                gdf_hasil['longitude'] = gdf_hasil.geometry.x
                gdf_hasil['latitude'] = gdf_hasil.geometry.y
                status_message = f"Berhasil! Ditemukan {len(gdf_hasil)} titik lokasi prioritas."
            else:
                status_message = f"Tidak ditemukan area rumput signifikan (NDVI >= {ndvi_threshold_input}). Coba turunkan nilai NDVI atau perluas periode tanggal."

        except Exception as e:
            st.error(f"Error during analysis: {str(e)}")
            status_message = f"Terjadi kesalahan dalam analisis: {str(e)}"
            gdf_hasil = None

    st.header("Hasil Analisis Pemeliharaan Rumput")
    if gdf_hasil is not None and not gdf_hasil.empty:
        st.success(status_message)

        if ndvi_threshold_input >= 0.7:
            priority_level = "URGENT"
        elif ndvi_threshold_input >= 0.6:
            priority_level = "PRIORITAS TINGGI"
        else:
            priority_level = "MONITORING"
        area_ha = len(gdf_hasil) * 0.01

        summary_stats = {
            "Status Prioritas": priority_level,
            "Total Titik Terdeteksi": f"{len(gdf_hasil)} titik",
            "Estimasi Area Terdampak": f"{area_ha:.2f} ha",
            "Provinsi": provinsi_input,
            "Periode": f"{start_date_input.strftime('%Y-%m-%d')} s/d {end_date_input.strftime('%Y-%m-%d')}"
        }

        # Buat peta statis untuk PDF
        fig, ax = plt.subplots(1, 1, figsize=(10, 8))
        gdf_filtered.plot(ax=ax, color='grey', alpha=0.5)
        gdf_hasil.plot(ax=ax, marker='o', color='red', markersize=5)
        ax.set_title("Peta Sebaran Titik Prioritas")
        plt.xticks([])
        plt.yticks([])
        static_map_path = "map.png"
        plt.savefig(static_map_path, dpi=200, bbox_inches='tight')

        ruas_summary = gdf_hasil.groupby('ruas').agg(jumlah_titik=('geometry', 'count'), estimasi_area_ha=('geometry',
                                                                                                           lambda
                                                                                                               x: len(
                                                                                                               x) * 0.01)).reset_index().sort_values(
            'jumlah_titik', ascending=False)
        pdf_data = create_pdf_report(summary_stats, gdf_hasil, ruas_summary, static_map_path)

        st.download_button(
            label="Download Laporan PDF",
            data=pdf_data,
            file_name=f"Laporan_Rumput_{provinsi_input}_{today.strftime('%Y%m%d')}.pdf",
            mime="application/pdf"
        )
        st.markdown("---")

        # Tampilan Tabs
        tab1, tab2, tab3, tab4 = st.tabs(
            ["Ringkasan & Peta", "Detail per Ruas", "Dashboard KPI", "Prediksi Pertumbuhan"])

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
                                                                                                  12))}).set_index(
                'Tanggal')
            st.area_chart(hist_data)

        with tab4:
            st.subheader("Prediksi Pertumbuhan untuk Monitoring")
            st.info(
                "Fitur ini mendeteksi area yang belum menjadi prioritas, namun menunjukkan pertumbuhan aktif dan berpotensi memerlukan pemotongan dalam beberapa minggu ke depan.")

            with st.spinner("Menganalisis area untuk prediksi..."):
                pred_min_ndvi = ndvi_threshold_input - 0.15
                pred_max_ndvi = ndvi_threshold_input

                gdf_prediksi, _ = run_gee_analysis(aoi_main, start_date_input, end_date_input, cloud_cover_input,
                                                   pred_min_ndvi, pred_max_ndvi)

            if gdf_prediksi is not None and not gdf_prediksi.empty:
                gdf_prediksi = gpd.sjoin_nearest(gdf_prediksi, gdf_filtered[['ruas', 'geometry']])
                gdf_prediksi['longitude'] = gdf_prediksi.geometry.x
                gdf_prediksi['latitude'] = gdf_prediksi.geometry.y

                growth_rate_ndvi = 0.05 if datetime.now().month in [1, 2, 3, 10, 11, 12] else 0.025
                gdf_prediksi['ndvi_saat_ini'] = np.random.uniform(pred_min_ndvi, pred_max_ndvi, len(gdf_prediksi))
                gdf_prediksi['estimasi_minggu'] = (
                            (ndvi_threshold_input - gdf_prediksi['ndvi_saat_ini']) / growth_rate_ndvi).apply(
                    np.ceil).astype(int)

                st.write(f"Ditemukan **{len(gdf_prediksi)}** area potensial untuk monitoring ketat.")
                st.dataframe(gdf_prediksi[['ruas', 'longitude', 'latitude', 'estimasi_minggu']],
                             use_container_width=True)
            else:
                st.success("Tidak ada area pertumbuhan signifikan yang terdeteksi untuk monitoring prediksi.")

    else:
        st.warning(status_message)

else:
    st.info("Silakan atur parameter di sidebar dan klik 'Analisis Kondisi Rumput' untuk memulai.")
