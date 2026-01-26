import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import timedelta

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Aşı Dolabı Analiz", layout="wide")

st.title("🌡️ Aşı/İlaç Dolabı Sıcaklık ve Kesinti Analizi")
st.markdown("""
Bu uygulama, yüklenen CSV dosyalarındaki sensör verilerini analiz eder.
**Tespit edilenler:**
1. Belirlenen süreden uzun **Veri Kesintileri**
2. Belirlenen limitlerin dışındaki **Sıcaklık İhlalleri**
""")

# --- Sidebar (Ayarlar) ---
st.sidebar.header("Ayarlar")
uploaded_file = st.sidebar.file_uploader("CSV Dosyası Yükle", type=["csv"])

# Parametreler
gap_threshold_hours = st.sidebar.number_input("Kesinti Limiti (Saat)", min_value=1, value=2)
min_temp_limit = st.sidebar.number_input("Min Sıcaklık (°C)", value=2.0)
max_temp_limit = st.sidebar.number_input("Max Sıcaklık (°C)", value=8.0)
header_row = st.sidebar.number_input("Başlık Satırı (Genelde 8)", min_value=0, value=8)

# --- Analiz Fonksiyonu ---
def analyze_data(file):
    try:
        # Dosyayı oku (Metadata satırlarını atla)
        df = pd.read_csv(file, header=header_row)
        
        # Sütun isimlerini kontrol et ve temizle
        # Genelde: SICAKLIK, ..., ÖLÇÜM ZAMANI
        # Boşlukları temizleyelim
        df.columns = df.columns.str.strip()
        
        # Gerekli sütunları bul
        time_col = [c for c in df.columns if "ZAMAN" in c or "DATE" in c]
        temp_col = [c for c in df.columns if "SICAKLIK" in c or "TEMP" in c]
        
        if not time_col or not temp_col:
            st.error("Gerekli sütunlar (ÖLÇÜM ZAMANI, SICAKLIK) bulunamadı.")
            return None

        time_col = time_col[0]
        temp_col = temp_col[0]

        # Tarih formatını düzelt
        df['Timestamp'] = pd.to_datetime(df[time_col], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Timestamp']).sort_values('Timestamp')

        # Sıcaklık formatını düzelt (Virgül -> Nokta)
        if df[temp_col].dtype == object:
            df['Temp'] = df[temp_col].str.replace(',', '.').astype(float)
        else:
            df['Temp'] = df[temp_col]

        return df, time_col, temp_col

    except Exception as e:
        st.error(f"Dosya okuma hatası: {e}")
        return None

# --- Ana Akış ---
if uploaded_file is not None:
    result = analyze_data(uploaded_file)
    
    if result:
        df, time_col_name, temp_col_name = result
        
        # 1. Veri Kesintisi Analizi
        df['TimeDiff'] = df['Timestamp'].diff()
        gap_threshold = timedelta(hours=gap_threshold_hours)
        gaps = df[df['TimeDiff'] >= gap_threshold].copy()
        
        # 2. Sıcaklık İhlal Analizi
        anomalies = df[(df['Temp'] < min_temp_limit) | (df['Temp'] > max_temp_limit)].copy()

        # --- Özet Kartları ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Kayıt", len(df))
        col2.metric("Tarih Aralığı", f"{df['Timestamp'].min().date()} - {df['Timestamp'].max().date()}")
        col3.metric("Veri Kesintisi", f"{len(gaps)} Adet", delta_color="inverse" if len(gaps)>0 else "normal")
        col4.metric("Sıcaklık İhlali", f"{len(anomalies)} Adet", delta_color="inverse" if len(anomalies)>0 else "normal")

        st.divider()

        # --- Sekmeler ---
        tab1, tab2, tab3 = st.tabs(["📉 Grafik", "⚠️ Veri Kesintileri", "🚨 Sıcaklık İhlalleri"])

        with tab1:
            st.subheader("Sıcaklık Grafiği")
            fig = px.line(df, x='Timestamp', y='Temp', title="Zaman İçinde Sıcaklık Değişimi")
            
            # Limit çizgileri ekle
            fig.add_hline(y=min_temp_limit, line_dash="dash", line_color="red", annotation_text="Min Limit")
            fig.add_hline(y=max_temp_limit, line_dash="dash", line_color="red", annotation_text="Max Limit")
            
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader(f"{gap_threshold_hours} Saatten Uzun Veri Kesintileri")
            if not gaps.empty:
                gaps['Kesinti Başlangıcı'] = df['Timestamp'].shift(1)
                gaps['Kesinti Bitişi'] = df['Timestamp']
                gaps['Süre'] = gaps['TimeDiff'].astype(str)
                
                st.dataframe(gaps[['Kesinti Başlangıcı', 'Kesinti Bitişi', 'Süre']], use_container_width=True)
            else:
                st.success("Belirlenen sürenin üzerinde veri kesintisi yok.")

        with tab3:
            st.subheader(f"{min_temp_limit}°C Altı ve {max_temp_limit}°C Üstü Kayıtlar")
            if not anomalies.empty:
                st.dataframe(anomalies[['Timestamp', 'Temp']], use_container_width=True)
            else:
                st.success("Sıcaklık ihlali yok.")
