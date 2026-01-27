import streamlit as st
import pandas as pd
from datetime import timedelta
from fpdf import FPDF

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Aşı Dolabı Analiz Raporu", layout="wide")

st.title("🌡️ Detaylı Aşı/İlaç Dolabı Sıcaklık Analizi")
st.markdown("Yüklenen sensör verilerini ve rapor başlığındaki tarihleri analiz eder; kesintileri ve ihlalleri profesyonel PDF raporu olarak sunar.")

# --- Ayarlar Sidebar ---
st.sidebar.header("⚙️ Analiz Ayarları")
uploaded_file = st.sidebar.file_uploader("CSV Dosyası Yükle", type=["csv"])

st.sidebar.divider()
st.sidebar.subheader("Limitler")
gap_threshold_hours = st.sidebar.number_input("Kesinti Limiti (Saat)", min_value=1, value=2)
min_temp_limit = st.sidebar.number_input("Min Sıcaklık (°C)", value=2.0)
max_temp_limit = st.sidebar.number_input("Max Sıcaklık (°C)", value=8.0)
HEADER_ROW = 8 

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
        date_str = date_str.strip().replace('"', '').replace("'", "")
        return pd.to_datetime(date_str, dayfirst=True)
    except:
        return None

def format_duration(td):
    """Timedelta'yı okunabilir string'e çevirir (Milisaniyesiz)"""
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
        self.ln(10)

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

        # Sıcaklık Dönüşümü (NaN değerleri korur)
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
        
        disp_start = meta_start_dt.strftime('%d.%m.%Y %H:%M') if meta_start_dt else "Belirtilmemiş"
        disp_end = meta_end_dt.strftime('%d.%m.%Y %H:%M') if meta_end_dt else "Belirtilmemiş"

        st.info(f"""
        **Birim:** {metadata.get('Birim','-')} | **Depo:** {metadata.get('Depo','-')}
        📅 **Rapor Tarih Aralığı (Header):** {disp_start} — {disp_end}
        """)

        # --- 1. KESİNTİ ANALİZİ ---
        gap_threshold = timedelta(hours=gap_threshold_hours)
        all_gaps = []

        # A) Zaman Farkı Kaynaklı Kesintiler (Satır Eksikliği)
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

        # B) Başlangıç Kaybı
        if meta_start_dt:
            first_data_time = df['Timestamp'].min()
            start_diff = first_data_time - meta_start_dt
            if start_diff >= gap_threshold:
                all_gaps.insert(0, {
                    "Tip": "Baslangic Kaybi",
                    "Baslangic": meta_start_dt,
                    "Bitis": first_data_time,
                    "Sure": start_diff
                })

        # C) Bitiş Kaybı
        if meta_end_dt:
            last_data_time = df['Timestamp'].max()
            end_diff = meta_end_dt - last_data_time
            if end_diff >= gap_threshold:
                all_gaps.append({
                    "Tip": "Bitis Kaybi",
                    "Baslangic": last_data_time,
                    "Bitis": meta_end_dt,
                    "Sure": end_diff
                })
        
        # D) Sıcaklık Verisi Yok (Boş Hücreler)
        # Temp sütunu NaN olan ama Timestamp olan satırlar
        missing_temps = df[df['Temp'].isna()].copy()
        if not missing_temps.empty:
            # Ardışık boş satırları grupla
            missing_temps['Group'] = (missing_temps['Timestamp'].diff() > pd.Timedelta('5min')).cumsum() 
            # Not: Yukarıdaki basit gruplama yerine index bazlı gruplama daha sağlıklıdır.
            
            # Ana DF üzerinde 'IsMissing' ile gruplama yapalım:
            df['IsMissingTemp'] = df['Temp'].isna()
            df['MissingGroup'] = (df['IsMissingTemp'] != df['IsMissingTemp'].shift()).cumsum()
            
            # Sadece True (Eksik) olan grupları al
            for _, group in df[df['IsMissingTemp']].groupby('MissingGroup'):
                s_t = group['Timestamp'].min()
                e_t = group['Timestamp'].max()
                dur = e_t - s_t
                
                # Eğer tek satırsa (dur=0), süreyi belirtmek için sembolik bir gösterim veya 0 bırakılabilir.
                # Kullanıcının seçtiği EŞİK DEĞERİNE göre filtreleyelim.
                # Tek bir boş satır genellikle 2 saati geçmez. Ancak kullanıcı eşiği 0 yaparsa görmeli.
                if dur >= gap_threshold:
                    all_gaps.append({
                        "Tip": "Sicaklik Verisi Yok",
                        "Baslangic": s_t,
                        "Bitis": e_t,
                        "Sure": dur
                    })
        
        # Kesinti Listesini Oluştur ve Sırala
        if all_gaps:
            df_gaps_report = pd.DataFrame(all_gaps)
            # Tarihe göre sırala
            df_gaps_report = df_gaps_report.sort_values('Baslangic')
            
            # Formatlama
            df_gaps_report['Baslangic'] = df_gaps_report['Baslangic'].apply(lambda x: x.strftime('%d.%m.%Y %H:%M:%S'))
            df_gaps_report['Bitis'] = df_gaps_report['Bitis'].apply(lambda x: x.strftime('%d.%m.%Y %H:%M:%S'))
            df_gaps_report['Sure'] = df_gaps_report['Sure'].astype(str).apply(lambda x: x.split('.')[0])
            
            df_gaps_report = df_gaps_report[["Tip", "Baslangic", "Bitis", "Sure"]]
        else:
            df_gaps_report = pd.DataFrame()


        # --- 2. SICAKLIK İHLALİ ve ÖZET ---
        df_clean = df.dropna(subset=['Temp']).copy() # İhlal hesabı için boş sıcaklıkları çıkar
        
        df_clean['Status'] = 0 
        df_clean.loc[df_clean['Temp'] < min_temp_limit, 'Status'] = -1
        df_clean.loc[df_clean['Temp'] > max_temp_limit, 'Status'] = 1
        df_clean['Group'] = (df_clean['Status'] != df_clean['Status'].shift()).cumsum()
        
        violation_events = []
        
        total_max_duration = timedelta(0)
        total_min_duration = timedelta(0)
        global_max_val = None
        global_min_val = None
        
        for _, group in df_clean[df_clean['Status'] != 0].groupby('Group'):
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
        
        df_violations = pd.DataFrame(violation_events)
        
        summary_stats = {
            "max_dur": format_duration(total_max_duration) if total_max_duration > timedelta(0) else "-",
            "max_val": f"{global_max_val} C" if global_max_val is not None else "-",
            "min_dur": format_duration(total_min_duration) if total_min_duration > timedelta(0) else "-",
            "min_val": f"{global_min_val} C" if global_min_val is not None else "-"
        }

        # --- SEKMELER ---
        tab1, tab2 = st.tabs(["⚠️ Veri Kesintileri", "🚨 Sıcaklık İhlalleri"])

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
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Toplam Üst Limit Aşım", summary_stats["max_dur"])
            col2.metric("En Yüksek Sıcaklık", summary_stats["max_val"])
            col3.metric("Toplam Alt Limit Aşım", summary_stats["min_dur"])
            col4.metric("En Düşük Sıcaklık", summary_stats["min_val"])
            st.divider()
            
            if not df_violations.empty:
                st.dataframe(df_violations, use_container_width=True)
                pdf_data_v = create_pdf_bytes(df_violations, metadata, "Sicaklik Ihlal Raporu", violation_summary=summary_stats)
                st.download_button("📄 İhlal Raporunu PDF İndir", pdf_data_v, "sicaklik_ihlal_raporu.pdf", "application/pdf")
            else:
                st.success("Herhangi bir sıcaklık ihlali bulunamadı.")

else:
    st.info("Lütfen CSV dosyasını yükleyin.")
