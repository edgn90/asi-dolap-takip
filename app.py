import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import timedelta

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Aşı Dolabı Analiz Raporu", layout="wide")

st.title("🌡️ Detaylı Aşı/İlaç Dolabı Sıcaklık Analizi")
st.markdown("""
Bu sistem, yüklenen sıcaklık kayıtlarını analiz ederek **veri kesintilerini** ve **sıcaklık ihlallerini** olay bazlı raporlar.
""")

# --- Sidebar (Ayarlar) ---
st.sidebar.header("⚙️ Analiz Ayarları")
uploaded_file = st.sidebar.file_uploader("CSV Dosyası Yükle", type=["csv"])

st.sidebar.divider()
st.sidebar.subheader("Limitler")
gap_threshold_hours = st.sidebar.number_input("Kesinti Limiti (Saat)", min_value=1, value=2, help="Bu süreden uzun veri akışı olmazsa kesinti sayılır.")
min_temp_limit = st.sidebar.number_input("Min Sıcaklık (°C)", value=2.0)
max_temp_limit = st.sidebar.number_input("Max Sıcaklık (°C)", value=8.0)
header_row = st.sidebar.number_input("Başlık Satır No", min_value=0, value=8, help="Dosyadaki sütun isimlerinin olduğu satır (Genelde 8).")

# --- Fonksiyon: Dosya Yükleme ve Temizleme ---
def analyze_data(file):
    try:
        # 1. Okuma (Encoding Hatası Korumalı)
        try:
            df = pd.read_csv(file, header=header_row, encoding='utf-8')
        except UnicodeDecodeError:
            file.seek(0) 
            df = pd.read_csv(file, header=header_row, encoding='ISO-8859-9')
        
        # 2. Sütun Temizliği
        df.columns = df.columns.str.strip()
        upper_cols = [c.upper() for c in df.columns]
        
        time_col = None
        temp_col = None

        for i, col in enumerate(upper_cols):
            if "ZAMAN" in col or "DATE" in col:
                time_col = df.columns[i]
            if "SICAKLIK" in col or "TEMP" in col:
                temp_col = df.columns[i]
        
        if not time_col or not temp_col:
            st.error(f"Gerekli sütunlar (ZAMAN, SICAKLIK) bulunamadı. Mevcut: {list(df.columns)}")
            return None

        # 3. Format Dönüşümleri
        df['Timestamp'] = pd.to_datetime(df[time_col], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Timestamp']).sort_values('Timestamp')

        if df[temp_col].dtype == object:
            df['Temp'] = df[temp_col].str.replace(',', '.').astype(float)
        else:
            df['Temp'] = df[temp_col]

        return df

    except Exception as e:
        st.error(f"Dosya işleme hatası: {e}")
        return None

# --- Fonksiyon: İhlal Gruplama ve Analizi ---
def find_violation_events(df, min_val, max_val):
    # Her satırı etiketle: 0=Normal, -1=Min Altı, 1=Max Üstü
    df = df.copy()
    df['Status'] = 0 
    df.loc[df['Temp'] < min_val, 'Status'] = -1
    df.loc[df['Temp'] > max_val, 'Status'] = 1
    
    # Değişim noktalarını bularak grupla (Ardışık aynı durumdakiler tek grup olur)
    df['Group'] = (df['Status'] != df['Status'].shift()).cumsum()
    
    events = []
    
    # Sadece ihlal olan grupları (Status != 0) analiz et
    for _, group in df[df['Status'] != 0].groupby('Group'):
        status_code = group['Status'].iloc[0]
        start_time = group['Timestamp'].min()
        end_time = group['Timestamp'].max()
        duration = end_time - start_time
        
        if status_code == -1:
            v_type = "❄️ Min Altı (Soğuk)"
            extreme_val = group['Temp'].min()
        else:
            v_type = "🔥 Max Üstü (Sıcak)"
            extreme_val = group['Temp'].max()
            
        events.append({
            "İhlal Türü": v_type,
            "Başlangıç": start_time,
            "Bitiş": end_time,
            "Süre": str(duration).split('.')[0], # Milisaniyeyi at
            "Uç Değer (°C)": extreme_val
        })
        
    return pd.DataFrame(events)

# --- ANA EKRAN ---
if uploaded_file is not None:
    df = analyze_data(uploaded_file)
    
    if df is not None:
        # --- 1. Başlık ve Tarih Bilgisi ---
        start_date = df['Timestamp'].min()
        end_date = df['Timestamp'].max()
        
        st.info(f"📅 **Dosya Kapsamı:** {start_date.strftime('%d.%m.%Y %H:%M:%S')}  —  {end_
