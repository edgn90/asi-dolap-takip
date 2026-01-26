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

# --- Sabit Ayarlar ---
# Dosya formatı standart olduğu için başlık satırı sabitlendi.
HEADER_ROW = 8 

# --- Fonksiyon: Dosya Yükleme ve Temizleme ---
def analyze_data(file):
    try:
        # 1. Okuma (Encoding Hatası Korumalı)
        try:
            df = pd.read_csv(file, header=HEADER_ROW, encoding='utf-8')
        except UnicodeDecodeError:
            file.seek(0) 
            df = pd.read_csv(file, header=HEADER_ROW, encoding='ISO-8859-9')
        
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
        
        st.info(f"📅 **Dosya Kapsamı:** {start_date.strftime('%d.%m.%Y %H:%M:%S')}  —  {end_date.strftime('%d.%m.%Y %H:%M:%S')}")

        # --- Analizler ---
        # A. Kesinti Analizi
        df['TimeDiff'] = df['Timestamp'].diff()
        gap_threshold = timedelta(hours=gap_threshold_hours)
        gaps = df[df['TimeDiff'] >= gap_threshold].copy()
        
        # B. Sıcaklık İhlal Analizi (Olay Bazlı)
        violation_events = find_violation_events(df, min_temp_limit, max_temp_limit)
        
        # --- Özet Metrikler ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Kayıt Sayısı", f"{len(df):,}")
        col2.metric("Analiz Süresi (Gün)", f"{(end_date - start_date).days} Gün")
        
        gap_count = len(gaps)
        col3.metric("Veri Kesintisi", f"{gap_count} Kez", 
                    delta="-Sorun" if gap_count > 0 else "Normal", delta_color="inverse")
        
        violation_count = len(violation_events)
        col4.metric("Sıcaklık İhlali", f"{violation_count} Olay", 
                    delta="-İhlal Var" if violation_count > 0 else "Güvenli", delta_color="inverse")

        st.divider()

        # --- Sekmeli Detay Görünümü ---
        tab_graph, tab_violations, tab_gaps, tab_data = st.tabs(["📉 Grafik", "🚨 Sıcaklık İhlal Raporu", "⚠️ Veri Kesintileri", "📄 Ham Veri"])

        with tab_graph:
            st.subheader("Zaman Serisi Sıcaklık Grafiği")
            fig = px.line(df, x='Timestamp', y='Temp', title="Sıcaklık Değişimi")
            
            # Limit Çizgileri
            fig.add_hline(y=min_temp_limit, line_dash="dash", line_color="blue", annotation_text=f"Min ({min_temp_limit}°C)")
            fig.add_hline(y=max_temp_limit, line_dash="dash", line_color="red", annotation_text=f"Max ({max_temp_limit}°C)")
            
            # İhlal bölgelerini renklendirme
            anomalies = df[(df['Temp'] < min_temp_limit) | (df['Temp'] > max_temp_limit)]
            if not anomalies.empty:
                fig.add_scatter(x=anomalies['Timestamp'], y=anomalies['Temp'], mode='markers', name='İhlaller', marker=dict(color='orange', size=6))

            st.plotly_chart(fig, use_container_width=True)

        with tab_violations:
            st.subheader("Sıcaklık İhlal Detayları")
            if not violation_events.empty:
                st.warning(f"Toplam {len(violation_events)} adet ihlal olayı tespit edildi.")
                st.dataframe(violation_events, use_container_width=True)
            else:
                st.success(f"✅ Harika! Tüm veriler {min_temp_limit}°C ile {max_temp_limit}°C arasında.")

        with tab_gaps:
            st.subheader(f"{gap_threshold_hours} Saatten Uzun Veri Kesintileri")
            if not gaps.empty:
                gaps_report = pd.DataFrame({
                    "Kesinti Başlangıcı": df.loc[gaps.index - 1, 'Timestamp'].values, # Bir önceki satır
                    "Kesinti Bitişi (Veri Gelişi)": gaps['Timestamp'],
                    "Kesinti Süresi": gaps['TimeDiff'].astype(str)
                })
                st.dataframe(gaps_report, use_container_width=True)
            else:
                st.success("✅ Veri akışında uzun süreli kesinti tespit edilmedi.")

        with tab_data:
            st.dataframe(df)

else:
    st.info("Lütfen sol menüden analiz etmek istediğiniz CSV dosyasını yükleyin.")
