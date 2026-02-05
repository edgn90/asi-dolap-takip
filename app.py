import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import timedelta
from fpdf import FPDF

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Aşı Dolabı Analiz Raporu", layout="wide")

st.title("🌡️ Detaylı Aşı/İlaç Dolabı Sıcaklık Analizi")
st.markdown("Yüklenen sensör verilerini analiz eder; kesintileri, ihlalleri, trendleri ve **otomatik karar önerisini** raporlar.")

# --- Ayarlar Sidebar ---
st.sidebar.header("⚙️ Analiz Ayarları")
uploaded_file = st.sidebar.file_uploader("CSV Dosyası Yükle", type=["csv"])

st.sidebar.divider()
st.sidebar.subheader("Limitler")
gap_threshold_hours = st.sidebar.number_input("Kesinti Limiti (Saat)", min_value=1, value=2)
min_temp_limit = st.sidebar.number_input("Min Sıcaklık (°C)", value=2.0)
max_temp_limit = st.sidebar.number_input("Max Sıcaklık (°C)", value=8.0)
HEADER_ROW = 8 

st.sidebar.divider()
st.sidebar.subheader("Müdahale / Transfer Durumu")
has_intervention = st.sidebar.checkbox("Aşılar Transfer Edildi mi?")
intervention_dt = None

if has_intervention:
    int_date = st.sidebar.date_input("Müdahale Tarihi")
    int_time = st.sidebar.time_input("Müdahale Saati")
    if int_date and int_time:
        intervention_dt = pd.to_datetime(f"{int_date} {int_time}")
        st.sidebar.info(f"Analiz **{intervention_dt.strftime('%d.%m.%Y %H:%M')}** tarihine kadar olan verilerle sınırlandırılacaktır.")

# --- Yardımcı Fonksiyonlar ---
def tr_fix(text):
    """FPDF için Türkçe karakter düzeltmesi"""
    if not isinstance(text, str):
        return str(text)
    mapping = {
        'Ğ': 'G', 'ğ': 'g', 'Ü': 'U', 'ü': 'u', 'Ş': 'S', 'ş': 's',
        'İ': 'I', 'ı': 'i', 'Ö': 'O', 'ö': 'o', 'Ç': 'C', 'ç': 'c'
    }
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text

def parse_metadata_date(date_str):
    try:
        if not date_str or pd.isna(date_str):
            return None
        date_str = str(date_str).strip().replace('"', '').replace("'", "")
        # NaT kontrolü
        dt = pd.to_datetime(date_str, dayfirst=True)
        if pd.isna(dt):
            return None
        return dt
    except:
        return None

def format_duration(td):
    """Timedelta'yı okunabilir string'e çevirir"""
    return str(td).split('.')[0]

# --- PDF Sınıfı ---
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
        self.cell(40, 6, tr_fix("Rapor Tarih Aralığı:"), border=0)
        
        start_str = str(self.metadata.get('Baslangic', '-'))
        end_str = str(self.metadata.get('Bitis', '-'))
        self.cell(0, 6, f"{start_str} -- {end_str}", ln=True)
        
        if self.metadata.get('Mudahale'):
            self.set_text_color(200, 0, 0)
            self.cell(0, 6, tr_fix(f"DIKKAT: {self.metadata['Mudahale']} tarihli MUDAHALE mevcuttur. Analiz bu tarihe kadar yapilmistir."), ln=True)
            self.set_text_color(0, 0, 0)

        self.ln(5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Sayfa {self.page_no()}', 0, 0, 'C')

    def add_violation_summary(self, summary_data):
        self.set_font('Arial', 'B', 11)
        self.cell(0, 8, tr_fix("IHLAL OZET TABLOSU"), ln=True)
        
        if summary_data.get('intervention'):
             self.set_font('Arial', 'B', 9)
             self.set_text_color(200, 0, 0)
             self.cell(0, 6, tr_fix(f"MUDAHALE TARIHI: {summary_data['intervention']}"), ln=True)
             self.set_font('Arial', 'I', 8)
             self.cell(0, 6, tr_fix("(Bu tarihten sonraki ihlaller toplama dahil edilmemistir)"), ln=True)
             self.set_text_color(0, 0, 0)
             self.ln(2)
        
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
        
        decision = summary_data.get('decision', '-')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 12, tr_fix(f"KARAR: {decision}"), border=1, ln=True, align='C')
        self.ln(5)

    def add_table(self, df):
        if df.empty:
            self.cell(0, 10, tr_fix("Veri bulunamadi."), ln=True, align='C')
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
                text = tr_fix(str(item))
                self.cell(col_width, 7, text, border=1, align='C')
            self.ln()

# --- Veri Okuma ---
def extract_metadata(file):
    file.seek(0)
    meta = {}
    try:
        lines = [file.readline().decode('ISO-8859-9').strip() for _ in range(HEADER_ROW + 2)]
        for line in lines:
            # Hem ; hem , ayracını destekle
            if ';' in line:
                parts = line.split(';')
            else:
                parts = line.split(',')
                
            clean_parts = [p.strip().replace('"', '') for p in parts if p.strip()]
            if len(clean_parts) >= 2:
                key = clean_parts[0]
                val = clean_parts[1]
                if "Birim" in key and "Stok" not in key: meta['Birim'] = val
                elif "Depo" in key: meta['Depo'] = val
                elif "Stok" in key: meta['Stok'] = val
                elif "Baslangiç" in key or "Baslangic" in key or "Başlangıç" in key: meta['Baslangic'] = val
                elif "Bitis" in key or "Bitiş" in key: meta['Bitis'] = val
    except Exception as e:
        pass
    return meta

def analyze_data(file):
    metadata = extract_metadata(file)
    file.seek(0)
    try:
        try:
            # sep=None ve engine='python' ile otomatik ayraç tespiti
            df = pd.read_csv(file, header=HEADER_ROW, sep=None, engine='python', encoding='utf-8')
        except UnicodeDecodeError:
            file.seek(0) 
            df = pd.read_csv(file, header=HEADER_ROW, sep=None, engine='python', encoding='ISO-8859-9')
        
        # Boş sütunları temizle (Unnamed vb)
        df = df.dropna(axis=1, how='all')
        
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

def create_pdf_bytes(df, metadata, title, violation_summary=None):
    pdf = ReportPDF(metadata, title)
    pdf.add_page()
    if violation_summary:
        pdf.add_violation_summary(violation_summary)
    pdf.add_table(df)
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- ANA AKIŞ ---
if uploaded_file is not None:
    df, metadata = analyze_data(uploaded_file)
    
    if df is not None:
        meta_start_dt = parse_metadata_date(metadata.get('Baslangic', ''))
        meta_end_dt = parse_metadata_date(metadata.get('Bitis', ''))
        
        disp_start = meta_start_dt.strftime('%d.%m.%Y %H:%M') if pd.notna(meta_start_dt) else "Belirtilmemiş"
        disp_end = meta_end_dt.strftime('%d.%m.%Y %H:%M') if pd.notna(meta_end_dt) else "Belirtilmemiş"

        st.info(f"""
        **Birim:** {metadata.get('Birim','-')} | **Depo:** {metadata.get('Depo','-')}
        📅 **Rapor Tarih Aralığı (Header):** {disp_start} — {disp_end}
        """)
        
        if has_intervention and intervention_dt:
            st.warning(f"⚠️ **DİKKAT:** {intervention_dt.strftime('%d.%m.%Y %H:%M')} tarihinden sonra aşı transferi/müdahale yapıldığı için bu tarihten sonraki veriler **karar analizine dahil edilmemiştir**.")
            metadata['Mudahale'] = intervention_dt.strftime('%d.%m.%Y %H:%M')

        # --- 1. KESİNTİ ANALİZİ ---
        gap_threshold = timedelta(hours=gap_threshold_hours)
        all_gaps = []

        # A) Zaman Farkı
        df['TimeDiff'] = df['Timestamp'].diff()
        df['PrevTimestamp'] = df['Timestamp'].shift(1)
        internal_gaps = df[df['TimeDiff'] >= gap_threshold].copy()
        for _, row in internal_gaps.iterrows():
            all_gaps.append({
                "Tip": "Veri Arası Bosluk",
                "Baslangic": row['PrevTimestamp'],
                "Bitis": row['Timestamp'],
                "Sure": row['TimeDiff']
            })

        # B) Başlangıç/Bitiş Kaybı
        if pd.notna(meta_start_dt):
            first_data_time = df['Timestamp'].min()
            start_diff = first_data_time - meta_start_dt
            if start_diff >= gap_threshold:
                all_gaps.insert(0, {
                    "Tip": "Baslangic Kaybi",
                    "Baslangic": meta_start_dt,
                    "Bitis": first_data_time,
                    "Sure": start_diff
                })

        if pd.notna(meta_end_dt):
            last_data_time = df['Timestamp'].max()
            end_diff = meta_end_dt - last_data_time
            if end_diff >= gap_threshold:
                all_gaps.append({
                    "Tip": "Bitis Kaybi",
                    "Baslangic": last_data_time,
                    "Bitis": meta_end_dt,
                    "Sure": end_diff
                })
        
        # C) Sıcaklık Verisi Yok
        df['IsMissingTemp'] = df['Temp'].isna()
        df['MissingGroup'] = (df['IsMissingTemp'] != df['IsMissingTemp'].shift()).cumsum()
        for _, group in df[df['IsMissingTemp']].groupby('MissingGroup'):
            s_t = group['Timestamp'].min()
            e_t = group['Timestamp'].max()
            dur = e_t - s_t
            if dur >= gap_threshold:
                all_gaps.append({
                    "Tip": "Sicaklik Verisi Yok",
                    "Baslangic": s_t,
                    "Bitis": e_t,
                    "Sure": dur
                })
        
        if all_gaps:
            df_gaps_report = pd.DataFrame(all_gaps).sort_values('Baslangic')
            df_gaps_report['Baslangic'] = df_gaps_report['Baslangic'].apply(lambda x: x.strftime('%d.%m.%Y %H:%M:%S'))
            df_gaps_report['Bitis'] = df_gaps_report['Bitis'].apply(lambda x: x.strftime('%d.%m.%Y %H:%M:%S'))
            df_gaps_report['Sure'] = df_gaps_report['Sure'].astype(str).apply(lambda x: x.split('.')[0])
            df_gaps_report = df_gaps_report[["Tip", "Baslangic", "Bitis", "Sure"]]
        else:
            df_gaps_report = pd.DataFrame()


        # --- 2. SICAKLIK İHLALİ ve KARAR ---
        df_clean = df.dropna(subset=['Temp']).copy()

        # Müdahale Filtresi (KARAR VERİLERİ İÇİN)
        if has_intervention and intervention_dt:
            df_decision_scope = df_clean[df_clean['Timestamp'] <= intervention_dt].copy()
        else:
            df_decision_scope = df_clean.copy()

        # 1. 0 Derece Altı Süresi
        df_decision_scope['IsFreezing'] = df_decision_scope['Temp'] < 0
        df_decision_scope['FreezeGroup'] = (df_decision_scope['IsFreezing'] != df_decision_scope['IsFreezing'].shift()).cumsum()
        total_below_zero_duration = timedelta(0)
        for _, grp in df_decision_scope[df_decision_scope['IsFreezing']].groupby('FreezeGroup'):
            total_below_zero_duration += (grp['Timestamp'].max() - grp['Timestamp'].min())

        # 2. 20 Derece Üzeri Süresi
        df_decision_scope['IsCriticalHeat'] = df_decision_scope['Temp'] > 20
        df_decision_scope['HeatGroup'] = (df_decision_scope['IsCriticalHeat'] != df_decision_scope['IsCriticalHeat'].shift()).cumsum()
        total_above_20_duration = timedelta(0)
        for _, grp in df_decision_scope[df_decision_scope['IsCriticalHeat']].groupby('HeatGroup'):
            total_above_20_duration += (grp['Timestamp'].max() - grp['Timestamp'].min())

        # 3. Limit İhlalleri
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

            violation_events.append({
                "Tur": v_type,
                "Baslangic": s_t.strftime('%d.%m.%Y %H:%M:%S'),
                "Bitis": e_t.strftime('%d.%m.%Y %H:%M:%S'),
                "Sure": format_duration(dur),
                "En Uc Deger": extreme
            })
        
        # --- KARAR MANTIĞI ---
        decision_msg = "MANUEL KONTROL GEREKLI (Ara Deger)"
        check_dur_hours = total_max_duration.total_seconds() / 3600
        check_max_val = global_max_val if global_max_val is not None else 0 
        
        if total_above_20_duration >= timedelta(hours=2):
             decision_msg = "IMHA ONERILIR (KRITIK SICAKLIK > 20C VE SURE > 2 Saat)"
        elif total_below_zero_duration >= timedelta(minutes=30):
             decision_msg = "IMHA ONERILIR (dondurulabilir aşılar hariç)"
        elif check_dur_hours >= 8 and check_max_val >= 15:
            decision_msg = "IMHA ONERILIR (SURE > 8s VE ISI > 15C)"
        elif check_dur_hours < 8 and check_max_val < 15:
            decision_msg = "KULLANILABILIR ONERILIR"
        
        df_violations = pd.DataFrame(violation_events)
        summary_stats = {
            "max_dur": format_duration(total_max_duration) if total_max_duration > timedelta(0) else "-",
            "max_val": f"{global_max_val} C" if global_max_val is not None else "-",
            "min_dur": format_duration(total_min_duration) if total_min_duration > timedelta(0) else "-",
            "min_val": f"{global_min_val} C" if global_min_val is not None else "-",
            "decision": decision_msg,
            "intervention": intervention_dt.strftime('%d.%m.%Y %H:%M') if (has_intervention and intervention_dt) else None
        }

        # --- 3. İSTATİSTİK ANALİZ ---
        df_clean['Date'] = df_clean['Timestamp'].dt.date
        daily_stats = df_clean.groupby('Date')['Temp'].agg(['mean', 'std', 'min', 'max']).reset_index()
        daily_stats.columns = ['Tarih', 'Ortalama', 'StdSapma', 'Min', 'Max']
        
        slope = 0
        if len(daily_stats) > 1:
            x = np.arange(len(daily_stats))
            y = daily_stats['Ortalama'].values
            z = np.polyfit(x, y, 1)
            slope = z[0]

        # --- ARAYÜZ GÖRÜNÜMÜ ---
        tab1, tab2, tab3 = st.tabs(["⚠️ Veri Kesintileri", "🚨 Sıcaklık İhlalleri", "📊 İstatistik & Trend"])

        with tab1:
            st.subheader(f"Veri Kesintisi Raporu (> {gap_threshold_hours} Saat)")
            if not df_gaps_report.empty:
                st.dataframe(df_gaps_report, use_container_width=True)
                pdf_data = create_pdf_bytes(df_gaps_report, metadata, "Veri Kesintisi Raporu")
                st.download_button("📄 Kesinti Raporunu PDF İndir", pdf_data, "veri_kesinti_raporu.pdf", "application/pdf")
            else:
                st.success("Belirlenen kriterlerde kesinti bulunamadı.")

        with tab2:
            st.subheader("Sıcaklık İhlal Raporu")
            
            # Karar Kutusu
            st.markdown("### 🚦 Otomatik Değerlendirme")
            if "IMHA" in decision_msg:
                st.error(f"🚨 **KARAR:** {decision_msg}")
            elif "KULLANILABILIR" in decision_msg:
                st.success(f"✅ **KARAR:** {decision_msg}")
            else:
                st.warning(f"⚠️ **KARAR:** {decision_msg}")
            
            if has_intervention and intervention_dt:
                st.caption(f"ℹ️ Hesaplamalar **{intervention_dt.strftime('%d.%m.%Y %H:%M')}** öncesi verilere göre yapılmıştır.")

            st.divider()
            
            # Özet Metrikler
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Toplam Üst Limit Aşım", summary_stats["max_dur"])
            col2.metric("En Yüksek Sıcaklık", summary_stats["max_val"])
            col3.metric("Toplam Alt Limit Aşım", summary_stats["min_dur"])
            col4.metric("En Düşük Sıcaklık", summary_stats["min_val"])
            
            if not df_violations.empty:
                st.dataframe(df_violations, use_container_width=True)
                pdf_data_v = create_pdf_bytes(df_violations, metadata, "Sicaklik Ihlal Raporu", violation_summary=summary_stats)
                st.download_button("📄 İhlal Raporunu PDF İndir", pdf_data_v, "sicaklik_ihlal_raporu.pdf", "application/pdf")
            else:
                st.info("İhlal tablosu boş (limitler içinde).")
                pdf_data_v = create_pdf_bytes(df_violations, metadata, "Sicaklik Ihlal Raporu", violation_summary=summary_stats)
                st.download_button("📄 Özet Raporunu PDF İndir", pdf_data_v, "sicaklik_ihlal_raporu.pdf", "application/pdf")
        
        with tab3:
            st.subheader("Kestirimci Bakım & İstatistik Analizi")
            c1, c2, c3 = st.columns(3)
            c1.metric("Genel Ortalama", f"{df_clean['Temp'].mean():.2f} °C")
            c2.metric("Genel Std. Sapma", f"{df_clean['Temp'].std():.2f} °C")
            
            trend_msg = "Veri yetersiz."
            trend_color = "off"
            if len(daily_stats) > 1:
                if slope > 0.05:
                    trend_msg = f"⚠️ ARTIŞ: Günlük +{slope:.3f}°C"
                    trend_color = "inverse"
                elif slope < -0.05:
                    trend_msg = f"ℹ️ AZALIŞ: Günlük -{abs(slope):.3f}°C"
                    trend_color = "normal"
                else:
                    trend_msg = "✅ STABİL"
                    trend_color = "normal"
            c3.metric("Trend", f"{slope:.4f}", delta=trend_msg, delta_color=trend_color)

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("#### 📅 Günlük Ortalama")
                fig_avg = px.bar(daily_stats, x='Tarih', y='Ortalama', color='Ortalama', color_continuous_scale='Bluered')
                if has_intervention and intervention_dt:
                     fig_avg.add_vline(x=intervention_dt.timestamp() * 1000, line_dash="dash", line_color="green", annotation_text="Müdahale")
                st.plotly_chart(fig_avg, use_container_width=True)
            with col_g2:
                st.markdown("#### 📉 Stabilite (Std. Sapma)")
                fig_std = px.line(daily_stats, x='Tarih', y='StdSapma', markers=True)
                fig_std.update_traces(line_color='#FF5733')
                st.plotly_chart(fig_std, use_container_width=True)

            st.dataframe(daily_stats, use_container_width=True)

else:
    st.info("Lütfen CSV dosyasını yükleyin.")
