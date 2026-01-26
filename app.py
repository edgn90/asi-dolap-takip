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
        # Önce standart UTF-8 okumayı dene
        try:
            df =
