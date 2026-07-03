import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import timedelta
from fpdf import FPDF
import io
import re

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Aşı Dolabı Analiz Raporu", layout="wide")

st.title("🌡️ Detaylı Aşı/İlaç Dolabı Sıcaklık Analizi")
st.markdown("Yüklenen sensör verilerini analiz eder; kesintileri, ihlalleri, trendleri ve **Ortalama Kinetik Sıcaklık (MKT)** bazlı otomatik kararları raporlar.")

# --- Ayarlar Sidebar ---
st.sidebar.header("⚙️ Analiz Ayarları")
uploaded_file = st.sidebar.file_uploader("CSV veya Excel Dosyası Yükle", type=["csv", "xlsx", "xls"])

st.sidebar.divider()
st.sidebar.subheader("Limitler")
gap_threshold_hours = st.sidebar.number_input("Kesinti Limiti (Saat)", min_value=1, value=2)
min_temp_limit = st.sidebar.number_input("Min Sıcaklık (°C)", value=2.0)
max_temp_limit = st.sidebar.number_input("Max Sıcaklık (°C)", value=8.0)

st.sidebar.divider()
st.sidebar.subheader("Müdahale / Transfer Durumu")
has_intervention = st.sidebar.checkbox("Aşılar Transfer Edildi mi?")
intervention_dt = None

if has_intervention:
    int_date = st.sidebar.date_input("Müdahale Tarihi")
    int_time = st.sidebar.time_input("Müdahale Saati")
    if int_date and int_time:
        intervention_dt = pd.to_datetime(f"{int_date} {int_time}")
        st.sidebar.info(f"Analiz **{intervention_dt.strftime('%d.%m.%Y %H:%M')}** tarihine kadar sınırlandırılmıştır.")

# --- Yardımcı Fonksiyonlar ---
def tr_fix(text):
    if not isinstance(text, str): return str(text)
    mapping = {'Ğ': 'G', 'ğ': 'g', 'Ü': 'U', 'ü': 'u', 'Ş': 'S', 'ş': 's', 'İ': 'I', 'ı': 'i', 'Ö': 'O', 'ö': 'o', 'Ç': 'C', 'ç': 'c'}
    for k, v in mapping.items(): text = text.replace(k, v)
    return text

def normalize_str(s):
    if not isinstance(s, str): return ""
    return s.replace('ı','i').replace('İ','I').replace('ğ','g').replace('Ğ','G').replace('ş','s').replace('Ş','S').replace('ö','o').replace('Ö','O').replace('ç','c').replace('Ç','C').upper()

def format_duration(td):
    return str(td).split('.')[0]

def calculate_mkt(temps_celsius):
    temps = pd.to_numeric(temps_celsius, errors='coerce').dropna()
    if temps.empty: return None
    temps_kelvin = temps.values + 273.15
    dh_r = 10000 
    exp_terms = np.exp(-dh_r / temps_kelvin)
    avg_exp = exp_terms.mean()
    if avg_exp == 0: return None
    return (dh_r / (-np.log(avg_exp))) - 273.15

# --- Özel Veri Dönüştürücüler ---
def parse_date_robust(date_str):
    if pd.isna(date_str): return pd.NaT
    s = str(date_str).strip()
    m = re.search(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?', s)
    if m:
        d, mon, y, h, min, sec = m.groups()
        sec = int(sec) if sec else 0
        try:
            return pd.Timestamp(year=int(y), month=int(mon), day=int(d), hour=int(h), minute=int(min), second=sec)
        except:
            return pd.NaT
    try:
        return pd.to_datetime(s, dayfirst=True)
    except:
        return pd.NaT

def parse_temp_robust(temp_str):
    if pd.isna(temp_str): return np.nan
    s = str(temp_str).strip()
    m = re.search(r'(-?\d+[,.]\d+|-?\d+)', s)
    if m:
        val = m.group(1).replace(',', '.')
        try:
            return float(val)
        except:
            return np.nan
    return np.nan

# --- PDF Sınıfı ve Oluşturucu ---
class ReportPDF(FPDF):
    def __init__(self, metadata, report_title):
        super().__init__()
        self.metadata = metadata
        self.report_title = report_title
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, tr_fix(self.report_title), ln=True, align='C')
        self.set_font('Arial', '', 9)
        self.cell(40, 6, tr_fix("Birim:"), border=0)
        self.cell(0, 6, tr_fix(self.metadata.get('Birim', '-')), ln=True)
        self.cell(40, 6, tr_fix("Depo:"), border=0)
        self.cell(0, 6, tr_fix(self.metadata.get('Depo', '-')), ln=True)
        self.cell(40, 6, tr_fix("Stok Birimi:"), border=0)
        self.cell(0, 6, tr_fix(self.metadata.get('Stok', '-')), ln=True)
        
        if self.metadata.get('expected_start') and self.metadata.get('expected_end'):
            start_str = self.metadata['expected_start'].strftime('%d.%m.%Y %H:%M')
            end_str = self.metadata['expected_end'].strftime('%d.%m.%Y %H:%M')
            self.cell(40, 6, tr_fix("Rapor Donemi:"), border=0)
            self.cell(0, 6, f"{start_str} - {end_str}", ln=True)
            
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Sayfa {self.page_no()}', 0, 0, 'C')

    def add_violation_summary(self, summary_data):
        self.set_font('Arial', 'B', 11)
        self.cell(0, 8, tr_fix("IHLAL VE TERMAL STRES OZETI"), ln=True)
        self.set_font('Arial', '', 10)
        col_w = 45
        self.cell(col_w, 7, tr_fix("Kriter"), 1)
        self.cell(col_w, 7, tr_fix("Toplam Sure"), 1)
        self.cell(col_w, 7, tr_fix("En Uc Deger"), 1)
        self.ln()
        self.cell(col_w, 7, tr_fix("Ust Limit Asimi"), 1)
        self.cell(col_w, 7, tr_fix(summary_data['max_dur']), 1)
        self.cell(col_w, 7, tr_fix(summary_data['max_val']), 1)
        self.ln()
        self.cell(col_w, 7, tr_fix("Alt Limit Asimi"), 1)
        self.cell(col_w, 7, tr_fix(summary_data['min_dur']), 1)
        self.cell(col_w, 7, tr_fix(summary_data['min_val']), 1)
        self.ln(5)
        if summary_data.get('mkt_val'):
            self.cell(0, 6, tr_fix(f"Ortalama Kinetik Sicaklik (MKT): {summary_data['mkt_val']}"), ln=True)
        self.ln(5)
        self.set_font('Arial', 'B', 11)
        self.multi_cell(0, 8, tr_fix(f"KARAR: {summary_data.get('status')} - {summary_data.get('decision', '-')}"), border=1, align='C')
        self.ln(5)

    def add_table(self, df, empty_msg="Veri bulunamadi."):
        if df.empty:
            self.set_font('Arial', 'I', 10)
            self.cell(0, 10, tr_fix(empty_msg), ln=True, align='C')
            return
            
        col_width = 190 / len(df.columns)
        self.set_font('Arial', 'B', 9)
        self.set_fill_color(200, 220, 255) 
        for col in df.columns:
            self.cell(col_width, 8, tr_fix(col), border=1, fill=True, align='C')
        self.ln()
        self.set_font('Arial', '', 8)
        self.set_fill_color(255, 255, 255)
        for index, row in df.iterrows():
            for item in row:
                self.cell(col_width, 7, tr_fix(str(item)), border=1, align='C')
            self.ln()

def create_pdf_bytes(df, metadata, title, violation_summary=None, empty_msg="Veri bulunamadi."):
    pdf = ReportPDF(metadata, title)
    pdf.add_page()
    if violation_summary: pdf.add_violation_summary(violation_summary)
    pdf.add_table(df, empty_msg)
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- Veri Ayrıştırma Modülü ---
def extract_metadata_from_text(text):
    meta = {}
    try:
        lines = text.splitlines()
        for line in lines[:50]:
            parts = [p.strip().replace('"', '') for p in line.replace(';', ',').split(',')]
            for i in range(len(parts)-1):
                key = normalize_str(parts[i])
                val = parts[i+1]
                
                if "DONEM" in key and "-" in val:
                    d_parts = val.split("-")
                    meta['Baslangic'] = d_parts[0].strip()
                    meta['Bitis'] = d_parts[1].strip()
                
                if not val:
                    for j in range(i+1, len(parts)):
                        if parts[j]:
                            val = parts[j]
                            break
                if not val: continue
                
                if "STOK BIRIMI" in key:
                    for j in range(i+1, len(parts)):
                        if parts[j] and not re.match(r'^\d+(\.\d+)?$', parts[j]):
                            meta['Stok'] = parts[j]
                            break
                
                if "BIRIM" == key and "STOK" not in key: meta['Birim'] = val
                elif "DEPO" == key: meta['Depo'] = val
    except:
        pass
    return meta

def analyze_data(file):
    filename = file.name.lower()
    metadata = {}
    df = None
    
    try:
        file_bytes = file.getvalue() 
        
        if filename.endswith(('.xlsx', '.xls')) and not filename.endswith('.csv'):
            try:
                df_raw = pd.read_excel(io.BytesIO(file_bytes), header=None)
                header_idx = 0
                for i in range(min(30, len(df_raw))):
                    row_vals = [normalize_str(x) for x in df_raw.iloc[i].tolist()]
                    
                    if "DONEM" in row_vals:
                        idx = row_vals.index("DONEM")
                        if idx + 1 < len(row_vals):
                            val = df_raw.iloc[i, idx+1]
                            if isinstance(val, str) and "-" in val:
                                d_parts = val.split("-")
                                metadata['Baslangic'] = d_parts[0].strip()
                                metadata['Bitis'] = d_parts[1].strip()

                    # B8, B9, C9 Hedefli Eşleştirmeler
                    if "BIRIM" in row_vals and not any("STOK" in v for v in row_vals):
                        b_idx = row_vals.index("BIRIM")
                        if b_idx + 1 < len(row_vals):
                            metadata['Birim'] = df_raw.iloc[i, b_idx+1]
                            
                    if "DEPO" in row_vals:
                        d_idx = row_vals.index("DEPO")
                        if d_idx + 1 < len(row_vals):
                            metadata['Depo'] = df_raw.iloc[i, d_idx+1]

                    if "STOK BIRIMI" in row_vals:
                        s_idx = row_vals.index("STOK BIRIMI")
                        for k in range(s_idx + 1, min(s_idx + 5, len(row_vals))):
                            val = df_raw.iloc[i, k]
                            if isinstance(val, str) and len(val) > 3 and not re.match(r'^\d+(\.\d+)?$', val):
                                metadata['Stok'] = val
                                break

                    if any("SICAKLIK" in v for v in row_vals) and any(("ZAMAN" in v or "TARIH" in v) for v in row_vals):
                        header_idx = i
                        
                df = pd.read_excel(io.BytesIO(file_bytes), header=header_idx)
            except Exception as e:
                return None, {}, f"Excel Hatası: {str(e)}"
        
        else:
            try: text = file_bytes.decode('utf-8-sig')
            except: text = file_bytes.decode('ISO-8859-9')
                
            metadata = extract_metadata_from_text(text)
            
            lines = text.splitlines()
            if not lines: return None, {}, "Dosya tamamen boş."
                
            header_idx = 0
            for idx, line in enumerate(lines[:50]):
                norm_line = normalize_str(line)
                if ("SICAKLIK" in norm_line or "TEMP" in norm_line) and ("ZAMAN" in norm_line or "TARIH" in norm_line):
                    header_idx = idx
                    break
            
            header_line = lines[header_idx]
            sep = ';' if header_line.count(';') >= header_line.count(',') else ','
            try: df = pd.read_csv(io.StringIO(text), header=header_idx, sep=sep, engine='python', on_bad_lines='skip')
            except Exception as e: return None, {}, f"CSV Ayraç Hatası: {str(e)}"

        if df is None or df.empty: return None, {}, "Tablo verisi bulunamadı."
        
        df = df.dropna(axis=1, how='all')
        df.columns = [str(c).strip().replace('"', '').replace('\r', '') for c in df.columns]
        
        time_col = None
        temp_col = None

        for col in df.columns:
            norm_col = normalize_str(col)
            if any(k in norm_col for k in ["ZAMAN", "TARIH", "DATE"]):
                if "KAYIT" not in norm_col and time_col is None: time_col = col
            if any(k in norm_col for k in ["SICAK", "TEMP", "ISI"]):
                if not any(k in norm_col for k in ["CIHAZ", "SENSOR", "LIMIT", "DURUM", "NO", "ID"]):
                    if temp_col is None: temp_col = col
                        
        if not time_col:
            for col in df.columns:
                if "TARIH" in normalize_str(col): 
                    time_col = col
                    break
        
        if not time_col or not temp_col: 
            return None, {}, f"Sıcaklık veya Tarih sütunu bulunamadı. Tespit Edilen Sütunlar: {', '.join(df.columns)}"

        metadata['expected_start'] = parse_date_robust(metadata.get('Baslangic'))
        metadata['expected_end'] = parse_date_robust(metadata.get('Bitis'))

        df['Timestamp'] = df[time_col].apply(parse_date_robust)
        df['Temp'] = df[temp_col].apply(parse_temp_robust)
            
        df = df.dropna(subset=['Timestamp', 'Temp']).sort_values('Timestamp')
        
        if len(df) == 0:
            return None, {}, "Sütunlar bulundu ancak veriler sayıya veya tarihe çevrilemedi."

        return df, metadata, ""

    except Exception as e:
        import traceback
        return None, {}, f"Bilinmeyen Hata: {str(e)}"

# --- ANA AKIŞ ---
if uploaded_file is not None:
    df, metadata, error_message = analyze_data(uploaded_file)
    
    if df is not None and not df.empty:
        
        expected_start = metadata.get('expected_start')
        expected_end = metadata.get('expected_end')
        
        actual_start_dt = df['Timestamp'].min()
        actual_end_dt = df['Timestamp'].max()
        
        ref_start_str = expected_start.strftime('%d.%m.%Y %H:%M') if pd.notna(expected_start) else actual_start_dt.strftime('%d.%m.%Y %H:%M')
        ref_end_str = expected_end.strftime('%d.%m.%Y %H:%M') if pd.notna(expected_end) else actual_end_dt.strftime('%d.%m.%Y %H:%M')

        # --- DOSYA VE DOLAP BİLGİLERİ (BİRİM, DEPO, STOK) ---
        st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; margin-bottom: 20px; border-left: 5px solid #0052cc;">
            <h4 style="margin-top: 0; color: #0052cc;">📋 Özet Bilgi Kartı</h4>
            <div style="display: flex; justify-content: space-between;">
                <div>
                    <b>🏢 Birim Adı:</b> {metadata.get('Birim', 'Otomatik algılanamadı')}<br>
                    <b>🏢 Depo Adı:</b> {metadata.get('Depo', 'Otomatik algılanamadı')}<br>
                    <b>📦 Stok Birimi:</b> {metadata.get('Stok', 'Otomatik algılanamadı')}
                </div>
                <div>
                    <b>📅 Rapor Dönemi (Başlangıç):</b> {ref_start_str}<br>
                    <b>📅 Rapor Dönemi (Bitiş):</b> {ref_end_str}<br>
                    <b>📊 Geçerli Sıcaklık Kaydı:</b> {len(df)} adet
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if has_intervention and intervention_dt:
            st.warning(f"⚠️ DİKKAT: {intervention_dt.strftime('%d.%m.%Y %H:%M')} sonrası veriler yoksayıldı.")

        # --- KESİNTİ (BOŞLUK) TESPİTİ ---
        gap_threshold = timedelta(hours=gap_threshold_hours)
        all_gaps = []
        
        if pd.notna(expected_start):
            start_diff = actual_start_dt - expected_start
            if start_diff >= gap_threshold:
                all_gaps.append({"Tip": "Başlangıç Veri Kaybı", "Baslangic": expected_start, "Bitis": actual_start_dt, "Sure": start_diff})

        df['TimeDiff'] = df['Timestamp'].diff()
        df['PrevTimestamp'] = df['Timestamp'].shift(1)
        for _, row in df[df['TimeDiff'] >= gap_threshold].iterrows():
            all_gaps.append({"Tip": "Sensör Veri Kesintisi (Ara Boşluk)", "Baslangic": row['PrevTimestamp'], "Bitis": row['Timestamp'], "Sure": row['TimeDiff']})

        if pd.notna(expected_end):
            end_diff = expected_end - actual_end_dt
            if end_diff >= gap_threshold:
                all_gaps.append({"Tip": "Bitiş Veri Kaybı", "Baslangic": actual_end_dt, "Bitis": expected_end, "Sure": end_diff})

        df_gaps_report = pd.DataFrame()
        if all_gaps:
            df_gaps_report = pd.DataFrame(all_gaps).sort_values('Baslangic')
            df_gaps_report['Baslangic'] = df_gaps_report['Baslangic'].dt.strftime('%d.%m.%Y %H:%M:%S')
            df_gaps_report['Bitis'] = df_gaps_report['Bitis'].dt.strftime('%d.%m.%Y %H:%M:%S')
            df_gaps_report['Sure'] = df_gaps_report['Sure'].astype(str).apply(lambda x: x.split('.')[0])
            df_gaps_report.rename(columns={
                "Tip": "Kesinti Türü", 
                "Baslangic": "Başlangıç Tarih/Saat", 
                "Bitis": "Bitiş Tarih/Saat", 
                "Sure": "Toplam Kesinti Süresi"
            }, inplace=True)

        # --- İHLAL VE KARAR MANTIĞI ---
        df_clean = df.copy()
        if has_intervention and intervention_dt:
            df_decision_scope = df_clean[df_clean['Timestamp'] <= intervention_dt].copy()
        else:
            df_decision_scope = df_clean.copy()

        mkt_value = calculate_mkt(df_decision_scope['Temp'])

        df_decision_scope['Status'] = 0 
        df_decision_scope.loc[df_decision_scope['Temp'] < min_temp_limit, 'Status'] = -1
        df_decision_scope.loc[df_decision_scope['Temp'] > max_temp_limit, 'Status'] = 1
        df_decision_scope['Group'] = (df_decision_scope['Status'] != df_decision_scope['Status'].shift()).cumsum()
        
        violation_events = []
        total_max_duration = timedelta(0)
        total_min_duration = timedelta(0)
        global_max_val = None
        global_min_val = None
        
        for _, group in df_decision_scope[df_decision_scope['Status'] != 0].groupby('Group'):
            status = group['Status'].iloc[0]
            v_type = "Min Alti" if status == -1 else "Max Ustu"
            s_t = group['Timestamp'].min()
            e_t = group['Timestamp'].max()
            dur = e_t - s_t
            extreme = group['Temp'].min() if status == -1 else group['Temp'].max()
            
            if status == 1: 
                total_max_duration += dur
                if global_max_val is None or extreme > global_max_val: global_max_val = extreme
            else: 
                total_min_duration += dur
                if global_min_val is None or extreme < global_min_val: global_min_val = extreme

            violation_events.append({"Tur": v_type, "Baslangic": s_t.strftime('%d.%m.%Y %H:%M:%S'), "Bitis": e_t.strftime('%d.%m.%Y %H:%M:%S'), "Sure": format_duration(dur), "En Uc Deger": extreme})
        
        df_violations = pd.DataFrame(violation_events)
        
        decision_msg = ""
        status_term = ""
        
        # Kesinti Kararı Eziyor
        if len(all_gaps) > 0:
            decision_msg = "VERİ KESİNTİSİ MEVCUT, İKİNCİL SICAKLIK ÖLÇÜMLERİNİ DEĞERLENDİR"
            status_term = "Acil Müdahale"
        elif total_max_duration.total_seconds() == 0 and total_min_duration.total_seconds() == 0:
            decision_msg = "TÜM VERİLER NORMAL"
            status_term = "Başarılı"
        elif total_max_duration.total_seconds() / 3600 >= 8 and (global_max_val and global_max_val >= 15):
            decision_msg = "IMHA ONERILIR (SURE > 8s VE ISI > 15C)"
            status_term = "Acil Müdahale"
        else:
            decision_msg = "RISKLI VERILER VAR - MANUEL KONTROL"
            status_term = "Geliştirilmeli"

        summary_stats = {
            "max_dur": format_duration(total_max_duration) if total_max_duration > timedelta(0) else "-",
            "max_val": f"{global_max_val} C" if global_max_val is not None else "-",
            "min_dur": format_duration(total_min_duration) if total_min_duration > timedelta(0) else "-",
            "min_val": f"{global_min_val} C" if global_min_val is not None else "-",
            "mkt_val": f"{mkt_value:.2f} C" if mkt_value is not None else "-",
            "status": status_term,
            "decision": decision_msg,
        }

        # --- ARAYÜZ GRAFİK VE TABLOLAR ---
        tab1, tab2, tab3 = st.tabs(["📈 Genel Sıcaklık Grafiği", "🚨 İhlal Raporları", "⚠️ Veri Kesintileri"])

        with tab1:
            st.subheader("Dolap Sıcaklık Seyri")
            st.markdown("Aşağıdaki grafikte okunan tüm sıcaklık değerlerini saniye saniye görebilirsiniz.")
            
            fig_line = px.line(df_clean, x='Timestamp', y='Temp', title='Sıcaklık Grafiği')
            fig_line.add_hline(y=max_temp_limit, line_dash="dash", line_color="red", annotation_text=f"Max Limit ({max_temp_limit}°C)")
            fig_line.add_hline(y=min_temp_limit, line_dash="dash", line_color="blue", annotation_text=f"Min Limit ({min_temp_limit}°C)")
            fig_line.update_layout(yaxis_title="Sıcaklık (°C)", xaxis_title="Tarih / Saat")
            st.plotly_chart(fig_line, use_container_width=True)

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### 📂 Tüm Sıcaklık Verileri (Liste)")
                df_display = df_clean[['Timestamp', 'Temp']].copy()
                df_display['Timestamp'] = df_display['Timestamp'].dt.strftime('%d.%m.%Y %H:%M:%S')
                df_display.rename(columns={'Timestamp': 'Zaman', 'Temp': 'Sıcaklık (°C)'}, inplace=True)
                st.dataframe(df_display, use_container_width=True, height=300)
            
            with col_b:
                st.markdown("#### 🖨️ Tam Rapor (Tüm Veriler)")
                st.info("Bu buton ile ihlal olsun veya olmasın okunan bütün sıcaklık verilerinin tam dökümünü formatlı PDF olarak indirebilirsiniz.")
                pdf_full_data = create_pdf_bytes(df_display, metadata, "Tum Sicaklik Raporu (Tam Liste)")
                st.download_button("📄 Tüm Verilerin PDF Raporunu İndir", pdf_full_data, "tum_sicaklik_verileri.pdf", "application/pdf")

        with tab2:
            st.subheader("Otomatik Karar & İhlal Tespiti")
            
            if status_term == "Başarılı":
                st.success(f"✅ **KARAR DURUMU:** {status_term} | {decision_msg}")
            elif status_term == "Acil Müdahale":
                st.error(f"🚨 **KARAR DURUMU:** {status_term} | {decision_msg}")
            else:
                st.warning(f"⚠️ **KARAR DURUMU:** {status_term} | {decision_msg}")

            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Toplam Üst Limit Aşım", summary_stats["max_dur"])
            col2.metric("En Yüksek Sıcaklık", summary_stats["max_val"])
            col3.metric("Toplam Alt Limit Aşım", summary_stats["min_dur"])
            col4.metric("En Düşük Sıcaklık", summary_stats["min_val"])
            col5.metric("Kinetik Sıcaklık (MKT)", f"{mkt_value:.2f} °C" if mkt_value else "-")
            
            st.markdown("#### 🚨 Limit Aşımı (İhlal) Olan Anlar")
            if not df_violations.empty:
                st.dataframe(df_violations, use_container_width=True)
                pdf_data_v = create_pdf_bytes(df_violations, metadata, "Sicaklik Ihlal Raporu", summary_stats)
                st.download_button("📄 Sadece İhlalleri (PDF) İndir", pdf_data_v, "sicaklik_ihlal.pdf", "application/pdf")
            else:
                st.success("Tebrikler! Bu tarih aralığında veriler normal sınırlar içerisindedir, sıcaklık ihlali tespit edilmemiştir.")
                pdf_data_v = create_pdf_bytes(pd.DataFrame(), metadata, "Sicaklik Ihlal Raporu", summary_stats, empty_msg="TEBRIKLER: Bu tarih araliginda hicbir sicaklik ihlali (limit asimi) tespit edilmemistir.")
                st.download_button("📄 Boş İhlal Raporunu PDF İndir", pdf_data_v, "sicaklik_ihlal.pdf", "application/pdf")

        with tab3:
            st.subheader(f"Veri Kesintisi Raporu (>{gap_threshold_hours} Saat)")
            
            if not df_gaps_report.empty:
                st.error(f"🚨 DİKKAT: Cihazda **{len(df_gaps_report)} adet** (belirlenen {gap_threshold_hours} saat limitini aşan) veri kesintisi veya kayıp ölçüm tespit edilmiştir!")
                st.markdown("Cihaz pilinin bitmesi, bağlantı kopukluğu veya verinin 'boş' geçilmesi sebebiyle aşağıdaki zaman aralıklarında veri eksikliği (Kör Nokta) yaşanmıştır.")
                st.dataframe(df_gaps_report, use_container_width=True)
                
                pdf_data_gaps = create_pdf_bytes(df_gaps_report, metadata, "Veri Kesintisi Raporu")
                st.download_button("📄 Kesinti Raporunu PDF İndir", pdf_data_gaps, "veri_kesintisi_raporu.pdf", "application/pdf")
            else:
                st.success(f"✅ Sistem, referans alınan başlangıç ve bitiş tarihleri ({ref_start_str} - {ref_end_str}) dahil olmak üzere, belirlenen kriterlerde ({gap_threshold_hours} saati aşan) hiçbir veri kesintisi bulamadı. Sensör aralıksız veri kaydetmiştir.")

    else:
        st.error(f"Dosya okunamadı! Hata Sebebi: **{error_message}**")
else:
    st.info("Lütfen CSV veya Excel uzantılı dosyanızı yükleyin.")
