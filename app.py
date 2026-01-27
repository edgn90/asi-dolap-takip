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
    """Farklı formatlardaki tarihleri (/, ., -) datetime'a çevirir"""
    try:
        # Olası temizlik
        date_str = date_str.strip().replace('"', '').replace("'", "")
        return pd.to_datetime(date_str, dayfirst=True)
    except:
        return None

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
        
        # Metadata'daki tarihleri kullan, yoksa - koy
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
        # ISO-8859-9 (Türkçe) ile okumayı dene
        lines = [file.readline().decode('ISO-8859-9').strip() for _ in range(HEADER_ROW + 2)] # Biraz fazla oku
        for line in lines:
            parts = line.split(',')
            clean_parts = [p.strip().replace('"', '') for p in parts if p.strip()]
            
            if len(clean_parts) >= 2:
                key = clean_parts[0]
                val = clean_parts[1]
                
                # Esnek anahtar kelime kontrolü
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
        # --- Metadata Tarihleri Parse Et ---
        meta_start_dt = parse_metadata_date(metadata.get('Baslangic', ''))
        meta_end_dt = parse_metadata_date(metadata.get('Bitis', ''))
        
        # Eğer metadata'dan tarih okunamadıysa, veri setindeki min/max kullanılır
        # Ancak kullanıcı açıkça Header'ı istediği için bunu öncelikli tutuyoruz.
        # Raporlama için kullanılacak stringler:
        disp_start = meta_start_dt.strftime('%d.%m.%Y %H:%M') if meta_start_dt else "Belirtilmemiş"
        disp_end = meta_end_dt.strftime('%d.%m.%Y %H:%M') if meta_end_dt else "Belirtilmemiş"

        st.info(f"""
        **Birim:** {metadata.get('Birim','-')} | **Depo:** {metadata.get('Depo','-')}
        
        📅 **Rapor Tarih Aralığı (Header):** {disp_start} — {disp_end}
        """)

        # --- 1. KESİNTİ ANALİZİ ---
        gap_threshold = timedelta(hours=gap_threshold_hours)
        all_gaps = []

        # A) Veri İçindeki Boşluklar (Internal Gaps)
        df['TimeDiff'] = df['Timestamp'].diff()
        internal_gaps = df[df['TimeDiff'] >= gap_threshold].copy()
        
        for idx, row in internal_gaps.iterrows():
            prev_row = df.loc[idx-1] # Pandas indexlemesine dikkat (iloc değil loc, sort edilmişse)
            # Ancak diff() alındığında indexler korunur. sort_values sonrası index resetlenmediyse:
            # Garanti olsun diye iloc ile alalım:
            # Row'un sırasını bulmamız lazım.
            
            # Daha güvenli yöntem: Shiftlenmiş kolon
            pass 
        
        # Pandas ile daha temiz yapalım:
        df['PrevTimestamp'] = df['Timestamp'].shift(1)
        internal_gaps = df[df['TimeDiff'] >= gap_threshold].copy()
        
        for _, row in internal_gaps.iterrows():
            all_gaps.append({
                "Tip": "Veri Arası",
                "Baslangic": row['PrevTimestamp'],
                "Bitis": row['Timestamp'],
                "Sure": row['TimeDiff']
            })

        # B) Başlangıç Boşluğu (Header Start vs First Data)
        if meta_start_dt:
            first_data_time = df['Timestamp'].min()
            start_diff = first_data_time - meta_start_dt
            if start_diff >= gap_threshold:
                all_gaps.insert(0, { # En başa ekle
                    "Tip": "Başlangıç Kaybı",
                    "Baslangic": meta_start_dt,
                    "Bitis": first_data_time,
                    "Sure": start_diff
                })

        # C) Bitiş Boşluğu (Last Data vs Header End)
        if meta_end_dt:
            last_data_time = df['Timestamp'].max()
            end_diff = meta_end_dt - last_data_time
            if end_diff >= gap_threshold:
                all_gaps.append({
                    "Tip": "Bitiş Kaybı",
                    "Baslangic": last_data_time,
                    "Bitis": meta_end_dt,
                    "Sure": end_diff
                })

        # DataFrame'e çevir
        if all_gaps:
            df_gaps_report = pd.DataFrame(all_gaps)
            # Formatlama
            df_gaps_report['Baslangic'] = df_gaps_report['Baslangic'].apply(lambda x: x.strftime('%d.%m.%Y %H:%M:%S'))
            df_gaps_report['Bitis'] = df_gaps_report['Bitis'].apply(lambda x: x.strftime('%d.%m.%Y %H:%M:%S'))
            df_gaps_report['Sure'] = df_gaps_report['Sure'].astype(str)
            # Sütun sırası
            df_gaps_report = df_gaps_report[["Tip", "Baslangic", "Bitis", "Sure"]]
        else:
            df_gaps_report = pd.DataFrame()


        # --- 2. SICAKLIK İHLALİ ANALİZİ ---
        # Sadece mevcut veriler üzerinde yapılabilir
        df['Status'] = 0 
        df.loc[df['Temp'] < min_temp_limit, 'Status'] = -1
        df.loc[df['Temp'] > max_temp_limit, 'Status'] = 1
        df['Group'] = (df['Status'] != df['Status'].shift()).cumsum()
        
        violation_events = []
        for _, group in df[df['Status'] != 0].groupby('Group'):
            status = group['Status'].iloc[0]
            v_type = "Min Alti" if status == -1 else "Max Ustu"
            
            s_t = group['Timestamp'].min()
            e_t = group['Timestamp'].max()
            dur = e_t - s_t
            
            violation_events.append({
                "Tur": v_type,
                "Baslangic": s_t.strftime('%d.%m.%Y %H:%M:%S'),
                "Bitis": e_t.strftime('%d.%m.%Y %H:%M:%S'),
                "Sure": str(dur),
                "En Uc Deger": group['Temp'].min() if status == -1 else group['Temp'].max()
            })
        df_violations = pd.DataFrame(violation_events)

        # --- SEKMELER ---
        tab1, tab2 = st.tabs(["⚠️ Veri Kesintileri", "🚨 Sıcaklık İhlalleri"])

        with tab1:
            st.subheader(f"Veri Kesintisi Raporu (> {gap_threshold_hours} Saat)")
            if not df_gaps_report.empty:
                st.dataframe(df_gaps_report, use_container_width=True)
                
                pdf_data = create_pdf_bytes(df_gaps_report, metadata, "Veri Kesintisi Raporu")
                st.download_button(
                    label="📄 Kesinti Raporunu PDF İndir",
                    data=pdf_data,
                    file_name="veri_kesinti_raporu.pdf",
                    mime="application/pdf"
                )
            else:
                st.success("Belirlenen kriterlerde (Header Tarihleri dahil) kesinti bulunamadı.")

        with tab2:
            st.subheader("Sıcaklık İhlal Raporu")
            if not df_violations.empty:
                st.dataframe(df_violations, use_container_width=True)
                
                pdf_data_v = create_pdf_bytes(df_violations, metadata, "Sicaklik Ihlal Raporu")
                st.download_button(
                    label="📄 İhlal Raporunu PDF İndir",
                    data=pdf_data_v,
                    file_name="sicaklik_ihlal_raporu.pdf",
                    mime="application/pdf"
                )
            else:
                st.success("Herhangi bir sıcaklık ihlali bulunamadı.")

else:
    st.info("Lütfen CSV dosyasını yükleyin.")
