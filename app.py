import streamlit as st
import pandas as pd
from datetime import timedelta
from fpdf import FPDF

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
    basit bir haritalama yapar."""
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
        
        # Metadata bilgilerini yaz
        self.cell(40, 6, tr_fix("Birim:"), border=0)
        self.cell(0, 6, tr_fix(self.metadata.get('Birim', '-')), ln=True)
        
        self.cell(40, 6, tr_fix("Depo:"), border=0)
        self.cell(0, 6, tr_fix(self.metadata.get('Depo', '-')), ln=True)
        
        self.cell(40, 6, tr_fix("Stok Birimi:"), border=0)
        self.cell(0, 6, tr_fix(self.metadata.get('Stok', '-')), ln=True)
        
        self.cell(40, 6, tr_fix("Rapor Tarih Aralığı:"), border=0)
        val = f"{self.metadata.get('Baslangic', '-')} -- {self.metadata.get('Bitis', '-')}"
        self.cell(0, 6, val, ln=True)
        
        self.ln(5)
        self.line(10, self.get_y(), 200, self.get_y()) # Ayırıcı çizgi
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Sayfa {self.page_no()}', 0, 0, 'C')

    def add_table(self, df):
        # Basit tablo çizimi
        if df.empty:
            self.cell(0, 10, tr_fix("Veri bulunamadi."), ln=True, align='C')
            return

        # Sütun Genişlikleri
        col_width = 190 / len(df.columns)
        
        # Başlıklar
        self.set_font('
