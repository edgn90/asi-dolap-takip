import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import timedelta
from fpdf import FPDF
import io

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Aşı Dolabı Analiz Raporu", layout="wide")

st.title("🌡️ Detaylı Aşı/İlaç Dolabı Sıcaklık Analizi")
st.markdown("Yüklenen sensör verilerini analiz eder, kesintileri ve ihlalleri profesyonel PDF raporu olarak sunar.")

# --- Ayarlar Sidebar ---
st.sidebar.header("⚙️ Analiz Ayarları")
uploaded_file = st.sidebar.file_uploader("CSV Dosyası Yükle", type=["csv"])

st.sidebar.divider()
st.sidebar.subheader("Limitler")
gap_threshold_hours = st.sidebar.number_input("Kesinti Limiti (Saat)", min_value=1, value=2)
min_temp_limit = st.sidebar.number_input("Min Sıcaklık (°C)", value=2.0)
max_temp_limit = st.sidebar.number_input("Max Sıcaklık (°C)", value=8.0)
HEADER_ROW = 8 

# --- Yardımcı Fonksiyon: Türkçe Karakter Düzeltme (PDF İçin) ---
def tr_fix(text):
    """FPDF standart fontları Türkçe karakterleri desteklemediği için 
    basit bir haritalama yapar. Harici font yüklemeye gerek kalmaz."""
    if not isinstance(text, str):
        return str(text)
    mapping = {
        'Ğ': 'G', 'ğ': 'g', 'Ü': 'U', 'ü': 'u', 'Ş': 'S', 'ş': 's',
        'İ': 'I', 'ı': 'i', 'Ö': 'O', 'ö': 'o', 'Ç': 'C', 'ç': 'c'
    }
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text

# --- Özel PDF Sınıfı ---
class ReportPDF(FPDF):
    def __init__(self, metadata, report_title):
        super().__init__()
        self.metadata = metadata
        self.report_title = report_title
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        # 1. Rapor Başlığı
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, tr_fix(self.report_title), ln=True, align='C')
        
        # 2. Metadata (Her sayfada görünür)
        self.set_font('Arial', '', 9)
        # Tablo şeklinde metadata
        # Birim
        self.cell(40, 6, tr_fix("Birim:"), border=0)
        self.cell(0, 6, tr_fix(self.metadata.get('Birim', '-')), ln=True)
        # Depo
        self.cell(40, 6, tr_fix("Depo:"), border=0)
        self.cell(0, 6, tr_fix(self.metadata.get('Depo', '-')), ln=True)
        # Stok
        self.cell(40, 6, tr_fix("Stok Birimi:"), border=0)
        self.cell(0, 6, tr_fix(self.metadata.get('Stok', '-')), ln=True)
        # Tarih Aralığı
        self.cell(40, 6, tr_fix("Rapor Tarih Aralığı:"), border=0)
        val = f"{self.metadata.get('Baslangic', '-')} -- {self.metadata.get('Bitis', '-')}"
        self.cell(0, 6, val, ln=True)
        
        self.ln(5)
        # Çizgi çek
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Sayfa {self.page_no()}', 0, 0, 'C')

    def add_table(self, df):
        # Sütun Genişlikleri (Otomatik ayarlama basitçe)
        # A4 genişliği ~190mm (kenar boşlukları hariç)
        col_width = 190 / len(df.columns)
        
        # Başlıklar
        self.set_font('Arial', 'B', 10)
        self.set_fill_color(200, 220, 255) # Açık mavi
        for col in df.columns:
            self.cell(col_width, 8, tr_fix(col), border=1, fill=True, align='C')
        self.ln()
        
        # Veriler
        self.set_font('Arial', '', 9)
        self.set_fill_color(255, 255, 255)
        
        for index, row in df.iterrows():
            for item in row:
                self.cell(col_width, 7, tr_fix(str(item)), border=1, align='C')
            self.ln()

# --- Veri İşleme Fonksiyonları ---
def extract_metadata(file):
    """CSV'nin ilk 8 satırından metadata okur"""
    file.seek(0)
    meta = {}
    try:
        # Satır satır oku
        lines = [file.readline().decode('ISO-8859-9').strip() for _ in range(HEADER_ROW)]
        
        # Basit ayrıştırma (CSV yapısına göre indexler değişebilir, esnek tutuyoruz)
        # Örnek yapı: ,Birim,HOSPITAL NAME,,,
        for line in lines:
            parts = line.split(',')
            # Temizle
            clean_parts = [p.strip() for p in parts if p.strip()]
            
            if len(clean_parts) >= 2:
                key = clean_parts[0].replace('"', '')
                val = clean_parts[1].replace('"', '')
                
                if "Birim" in key and "Stok" not in key: meta['Birim'] = val
                elif "Depo" in key: meta['Depo'] = val
                elif "Stok" in key: meta['Stok'] = val
                elif "Baslangiç" in key or "Baslangic" in key: meta['Baslangic'] = val
                elif "Bitis" in key: meta['Bitis'] = val
                
    except Exception as e:
        print(f"Metadata hatası: {e}")
        
    return meta

def analyze_data(file):
    # Metadata al
    metadata = extract_metadata(file)
    
    # Veriyi oku
    file.seek(0)
    try:
        try:
            df = pd.read_csv(file, header=HEADER_ROW, encoding='utf-8')
        except UnicodeDecodeError:
            file.seek(0) 
            df = pd.read_csv(file, header=HEADER_ROW, encoding='ISO-8859-9')
        
        df.columns = df.columns.str.strip()
        upper_cols = [c.upper() for c in df.columns]
        
        time_col = None
        temp_col = None

        for i, col in enumerate(upper_cols):
            if "ZAMAN" in col or "DATE" in col: time_col = df.columns[i]
            if "SICAKLIK" in col or "TEMP" in col: temp_col = df.columns[i]
        
        if not time_col or not temp_col: return None, None

        df['Timestamp'] = pd.to_datetime(df[time_col], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Timestamp']).sort_values('Timestamp')

        if df[temp_col].dtype == object:
            df['Temp'] = df[temp_col].str.replace(',', '.').astype(float)
        else:
            df['Temp'] = df[temp_col]

        return df, metadata

    except Exception:
        return None, None

def create_pdf_bytes(df, metadata, title):
    pdf = ReportPDF(metadata, title)
    pdf.add_page()
    pdf.add_table(df)
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- ANA AKIŞ ---
if uploaded_file is not None:
    df, metadata = analyze_data(uploaded_file)
    
    if df is not None:
        # --- İhlal ve Kesinti Hesaplama ---
        # 1. Kesintiler
        df['TimeDiff'] = df['Timestamp'].diff()
        gap_threshold = timedelta(hours=gap_threshold_hours)
        gaps = df[df['TimeDiff'] >= gap_threshold].copy()
        
        # 2. İhlaller (Gruplanmış)
        df['Status'] = 0 
        df.loc[df['Temp'] < min_temp_limit, 'Status'] = -1
        df.loc[df['Temp'] > max_temp_limit, 'Status'] = 1
        df['Group'] = (df['Status'] != df['Status'].shift()).cumsum()
        
        violation_events = []
        for _, group in df[df['Status'] != 0].groupby('Group'):
            status = group['Status'].iloc[0]
            v_type = "Min Alti" if status == -1 else "Max Ustu"
            violation_events.append({
                "Tur": v_type,
                "Baslangic": str(group['Timestamp'].min()),
                "Bitis": str(group['Timestamp'].max()),
                "En Uc Deger": group['Temp'].min() if status == -1 else group['Temp'].max()
            })
        df_violations = pd.DataFrame(violation_events)

        # 3. Kesinti Tablosunu Hazırla (PDF için temiz format)
        if not gaps.empty:
            df_gaps_report = pd.DataFrame({
                "Baslangic": df.loc[gaps.index - 1, 'Timestamp'].values.astype(str),
                "Bitis": gaps['Timestamp'].values.astype(str),
                "Sure": gaps['TimeDiff'].astype(str)
            })
        else:
            df_gaps_report = pd.DataFrame(columns=["Baslangic", "Bitis", "Sure"])

        # --- ARAYÜZ GÖSTERİMİ ---
        
        # Bilgi Kartları
        st.info(f"Birim: **{metadata.get('Birim','-')}** | Depo: **{metadata.get('Depo','-')}**")
        
        tab1, tab2 = st.tabs(["⚠️ Veri Kesintileri", "🚨 Sıcaklık İhlalleri"])

        # --- SEKME 1: KESİNTİLER ---
        with tab1:
            st.subheader(f"Veri Kesintisi Raporu (> {gap_threshold_hours} Saat)")
            if not df_gaps_report.empty:
                st.dataframe(df_gaps_report, use_container_width=True)
                
                # PDF İndirme Butonu
                pdf_data = create_pdf_bytes(df_gaps_report, metadata, "Veri Kesintisi Raporu")
                st.download_button(
                    label="📄 Kesinti Raporunu PDF İndir",
                    data=pdf_data,
                    file_name="veri_kesinti_raporu.pdf",
                    mime="application/pdf"
                )
            else:
                st.success("Bu kriterlere uygun veri kesintisi bulunamadı.")

        # --- SEKME 2: İHLALLER ---
        with tab2:
            st.subheader("Sıcaklık İhlal Raporu")
            if not df_violations.empty:
                st.dataframe(df_violations, use_container_width=True)
                
                # PDF İndirme Butonu
                pdf_data_v = create_pdf_bytes(df_violations, metadata, "Sicaklik Ihlal Raporu")
                st.download_button(
                    label="📄 İhlal Raporunu PDF İndir",
