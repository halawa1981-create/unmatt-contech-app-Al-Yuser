import streamlit as st
import pandas as pd
import json
import requests
import base64
from PIL import Image
import pymupdf as fitz
import time  
import io 
import re
import os
import datetime
import urllib.parse
import plotly.express as px
import plotly.graph_objects as go
import hashlib
import secrets
import string

# ─── إدارة الملفات والمسارات ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DICT_FILE = os.path.join(BASE_DIR, "dictionary.txt")
PROJECTS_FILE = os.path.join(BASE_DIR, "projects.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
TRAINING_FILE = os.path.join(BASE_DIR, "training_data.json")
APPROVED_DATASET_FILE = os.path.join(BASE_DIR, "approved_dataset.json")
TUNING_CONFIG_FILE = os.path.join(BASE_DIR, "tuning_config.json")
AUDIT_LOG_FILE = os.path.join(BASE_DIR, "audit_log.json")
API_KEY_FILE = os.path.join(BASE_DIR, "api_key.txt")

# فحص الشعار المعتمد
NEW_BRAND_LOGO = None
for fname in ["Un-matt_ConTech_professional_log…_2K_202609051357.jpeg", "unmatt_logo.jpeg", "unmatt_logo.png", "anmatt_logo.png", "anmatt_logo.jpg", "logo.PNG"]:
    p = os.path.join(BASE_DIR, fname)
    if os.path.exists(p):
        NEW_BRAND_LOGO = p
        break

favicon_img = Image.open(NEW_BRAND_LOGO) if NEW_BRAND_LOGO else "🏢"
st.set_page_config(
    page_title="Un-matt ConTech | Enterprise System", 
    layout="wide", 
    page_icon=favicon_img
)

DEFAULT_DICT = "أحمد عبد الرحيم صدام يصنف كمورد لمياه الشرب (التصنيف: موردين).\nضرورة تأكيد المبلغ المدفوع ومراعاة شطب طريقة الدفع ومطابقة التفقيط."
DEFAULT_PROJECTS = ["مشروع مول 6 أكتوبر"]
CLOUD_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbxRaRWmpekP-d0rwJdAupIy5N498zToYJP-LNKRUmrQcO_EPcWsSY0loXgbRiHNotRA/exec"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.strip().encode()).hexdigest()

def generate_temp_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def load_audit_log():
    if os.path.exists(AUDIT_LOG_FILE):
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list): return data
        except Exception: return []
    return []

def log_audit_event(action_type, details, user_email, user_name):
    logs = load_audit_log()
    log_entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_email": user_email, "user_name": user_name, "action": action_type, "details": details
    }
    logs.insert(0, log_entry)
    try:
        with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
    except Exception: pass

def load_training_db():
    if os.path.exists(TRAINING_FILE):
        try:
            with open(TRAINING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list): return data
        except Exception: return []
    return []

def save_training_db(training_list):
    try:
        with open(TRAINING_FILE, "w", encoding="utf-8") as f:
            json.dump(training_list, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        return True
    except Exception: return False

def load_approved_dataset():
    if os.path.exists(APPROVED_DATASET_FILE):
        try:
            with open(APPROVED_DATASET_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list): return data
        except Exception: return []
    return []

def save_approved_dataset(dataset_list):
    try:
        with open(APPROVED_DATASET_FILE, "w", encoding="utf-8") as f:
            json.dump(dataset_list, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        return True
    except Exception: return False

def load_tuning_config():
    default_config = {
        "company_id": "alyoser_contracting",
        "company_name": "شركة اليسر للمقاولات",
        "system_instruction": "أنت مراجع مالي أول ومحاسب معتمد في شركة اليسر للمقاولات. مهمتك استخراج ومطابقة بيانات فواتير ومصروفات المشاريع بدقة متناهية ومطابقة التفقيط بالأرقام بصيغة JSON.",
        "active_tuned_model": "",
        "use_tuned_model": False,
        "json_schema": {
            "invoice_no": "رقم الفاتورة أو المستند",
            "invoice_date": "YYYY-MM-DD",
            "category": "تصنيف المصروف",
            "description": "بيان المصروف بالتفصيل",
            "payment_method": "طريقة الدفع",
            "amount": 0.0,
            "vat": 0.0,
            "remark": "ملاحظات إضافية"
        }
    }
    if os.path.exists(TUNING_CONFIG_FILE):
        try:
            with open(TUNING_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    default_config.update(saved)
        except Exception: pass
    return default_config

def save_tuning_config(cfg):
    try:
        with open(TUNING_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        return True
    except Exception: return False

def record_learned_sample(inv_no, desc, amount, category, pay_method, project_name):
    try:
        current_db = load_training_db()
        exists = any(
            str(x.get("correct_data", {}).get("invoice_no", "")).strip() == str(inv_no).strip() and 
            abs(float(x.get("correct_data", {}).get("amount", 0.0)) - float(amount)) < 0.01 
            for x in current_db
        )
        if not exists and (str(desc).strip() or float(amount) > 0):
            new_entry = {
                "correct_data": {
                    "invoice_no": str(inv_no).strip(),
                    "description": str(desc).strip(),
                    "amount": float(amount),
                    "category": str(category).strip(),
                    "payment_method": str(pay_method).strip(),
                    "project": str(project_name).strip()
                },
                "learned_at": str(datetime.datetime.now()),
                "source": "live_user_correction"
            }
            current_db.insert(0, new_entry)
            save_training_db(current_db)
            if "manual_training_data" in st.session_state:
                st.session_state.manual_training_data = current_db
            return True
    except Exception: pass
    return False

def load_projects_list():
    if os.path.exists(PROJECTS_FILE):
        try:
            with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, list) and saved: return saved
        except Exception: pass
    return list(DEFAULT_PROJECTS)

def save_projects_list_to_disk(projs):
    try:
        with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump(projs, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        return True
    except Exception: return False

def load_system_dictionary():
    try:
        res = requests.get(f"{CLOUD_WEB_APP_URL}?action=get_dictionary", timeout=8)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == "success" and data.get("dictionary"):
                cloud_dict = data.get("dictionary").strip()
                with open(DICT_FILE, "w", encoding="utf-8") as f: f.write(cloud_dict)
                return cloud_dict
    except Exception: pass
    if os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f: return f.read().strip()
        except Exception: return DEFAULT_DICT
    return DEFAULT_DICT

def save_system_dictionary(text):
    local_saved = False
    try:
        with open(DICT_FILE, "w", encoding="utf-8") as f: f.write(text)
        local_saved = True
    except Exception: pass
    cloud_saved = False
    try:
        payload = {"action": "save_dictionary", "dictionaryText": text}
        res = requests.post(CLOUD_WEB_APP_URL, json=payload, timeout=15)
        if res.status_code == 200 and res.json().get("status") == "success": cloud_saved = True
    except Exception: pass
    return local_saved, cloud_saved

def load_cloud_records():
    try:
        response = requests.get(CLOUD_WEB_APP_URL, timeout=15)
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("status") == "success":
                records = res_json.get("records", [])
                valid_records = []
                for r in records:
                    is_del = str(r.get("delete", "False")).strip().lower() in ["true", "1", "نعم"]
                    if not is_del:
                        r["delete"] = False
                        r["invoice_date"] = normalize_date(r.get("invoice_date", ""))
                        valid_records.append(r)
                return valid_records
        return []
    except Exception: return []

def sync_delete_to_cloud(serial_no, project_name, user_email):
    try:
        payload = {
            "action": "delete_invoice", "serialNo": serial_no, "project": project_name,
            "deletedBy": user_email, "deletedAt": str(datetime.datetime.now())
        }
        res = requests.post(CLOUD_WEB_APP_URL, json=payload, timeout=15)
        return res.status_code == 200
    except Exception: return False

def save_to_cloud_storage(image, filename, row_data):
    img_str = optimize_image_for_upload(image)
    payload = {"action": "upload_invoice", "fileName": filename, "mimeType": "image/jpeg", "fileData": img_str, "rowValues": row_data}
    try:
        response = requests.post(CLOUD_WEB_APP_URL, json=payload, timeout=30)
        res_json = response.json()
        if res_json.get("status") == "success": return res_json.get("url", ""), True
        return "", False
    except Exception: return "", False

def normalize_date(date_str):
    if not date_str or not str(date_str).strip(): return datetime.date.today().strftime("%Y-%m-%d")
    date_clean = str(date_str).strip().replace("/", "-").replace(".", "-")
    ar_to_en = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    date_clean = date_clean.translate(ar_to_en)
    match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', date_clean)
    if match:
        y, m, d = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return date_clean

def optimize_image_for_upload(image, max_size=(1400, 1400), quality=80):
    img = image.copy()
    if img.mode != 'RGB': img = img.convert('RGB')
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def analyze_invoice_with_gemini(image, prompt_text, api_key, current_project=""):
    img_str = optimize_image_for_upload(image, max_size=(1400, 1400), quality=80)
    clean_key = str(api_key).strip().replace('"', '').replace("'", '').split("\n")[0].split(",")[0].strip()
    
    t_cfg = load_tuning_config()
    candidate_models = []
    if t_cfg.get("use_tuned_model") and t_cfg.get("active_tuned_model"):
        candidate_models.append(t_cfg.get("active_tuned_model").strip())

    candidate_models.extend([
        "gemini-3.5-flash-lite", 
        "gemini-3.6-flash", 
        "gemini-2.5-flash",
        "gemini-2.0-flash", 
        "gemini-1.5-flash"
    ])

    training_db = load_training_db()
    learned_context = ""
    if training_db:
        learned_context = "\n\nأنماط محاسبية وموردين معتمدة مسبقاً للاسترشاد:\n"
        for item in training_db[:20]:
            cd = item.get("correct_data", {})
            if cd.get("description") or float(cd.get("amount", 0)) > 0:
                learned_context += f"- مستند رقم '{cd.get('invoice_no')}': البيان '{cd.get('description')}' | المبلغ: ({cd.get('amount')}) ج.م | التصنيف: '{cd.get('category')}'\n"

    sys_inst = t_cfg.get("system_instruction", "")
    active_rules = f"""
{sys_inst}
{learned_context}
قواعد قراءة واستخراج حاسمة لرفع الموثوقية:
1. [أرقام المستند والمبالغ]: تحويل الأرقام الهندية/العربية بدقة (مثل ٦ = 6، ٢ = 2).
2. [المبلغ والتفقيط]: قارن القيمة الرقمية مع النص المكتوب يدوياً تحت عبارة (فقط وقدره...) واعتمد القيمة المطابقة بدقة كـ float في خانة amount.
3. [البيان والمستفيد]: استخرج اسم المورد أو البيان بدقة معتمدة على قاموس الشركة والأنماط السابقة.
4. النتيجة المطلوبة كائن JSON مفرد ومباشر {{ }} فقط.
"""
    final_prompt = prompt_text + "\n" + active_rules
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": final_prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": img_str}}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0}
    }

    last_error_details = []
    for model_name in candidate_models:
        if model_name.startswith("tunedModels/"):
            url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={clean_key}"
        else:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={clean_key}"
            
        for attempt in range(2):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=45)
                if response.status_code == 200:
                    res_json = response.json()
                    candidates = res_json.get('candidates', [])
                    if not candidates: continue
                    raw_text = candidates[0]['content']['parts'][0]['text']
                    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                    parsed = json.loads(match.group(0)) if match else {}
                    if isinstance(parsed, list): parsed = parsed[0] if parsed else {}
                    if not isinstance(parsed, dict): parsed = {}

                    if "invoice_date" in parsed:
                        parsed["invoice_date"] = normalize_date(parsed["invoice_date"])
                    return parsed
                elif response.status_code in [404, 429, 503]:
                    last_error_details.append(f"[{model_name}: كود {response.status_code}]")
                    time.sleep(1.0)
                    break
                else:
                    last_error_details.append(f"[{model_name}: كود {response.status_code}]")
                    break
            except Exception as e:
                last_error_details.append(f"[{model_name}: استثناء {str(e)[:50]}]")
                time.sleep(1.0)
                
    err_summary = " | ".join(last_error_details) if last_error_details else "لا يوجد استجابة من الخادم"
    raise Exception(f"تعذر استخراج البيانات: {err_summary}")

def load_users_db():
    default_users = {
        "halawa1981@gmail.com": {
            "name": "م/ محمد حلاوة (Super Admin)", "password_hash": hash_password("01230030480Ab"), 
            "role": "Super Admin", "allowed_projects": "All", "must_change_password": False
        },
        "admin@contech.com": {
            "name": "مدير النظام المفوض (Company Admin)", "password_hash": hash_password("Admin#2026"),
            "role": "Admin", "allowed_projects": "All", "must_change_password": False
        },
        "ceo@contech.com": {
            "name": "الرئيس التنفيذي (CEO)", "password_hash": hash_password("Ceo#2026"),
            "role": "CEO", "allowed_projects": "All", "must_change_password": False
        },
        "mohamedhassan0014@gmail.com": {
            "name": "م/ محمد حسن", "password_hash": hash_password("Temp#2026"),
            "role": "Accountant", "allowed_projects": ["مشروع مول 6 أكتوبر"], "must_change_password": True
        }
    }
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    saved.pop("admin@alyosr.com", None)
                    saved.pop("acc@alyosr.com", None)
                    default_users.update(saved)
        except Exception: pass
    return default_users

def save_users_db(users_data):
    try:
        users_data.pop("admin@alyosr.com", None)
        users_data.pop("acc@alyosr.com", None)
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_data, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        return True
    except Exception: return False

# ─── التهيئة الآمنة لجميع متغيرات الجلسة ───
if "system_lang" not in st.session_state: st.session_state.system_lang = "العربية"
if "system_theme" not in st.session_state: st.session_state.system_theme = "Light"
if "users_db" not in st.session_state: st.session_state.users_db = load_users_db()
if "projects_list" not in st.session_state: st.session_state.projects_list = load_projects_list()
if "invoices_data" not in st.session_state: st.session_state.invoices_data = load_cloud_records()
if "manual_training_data" not in st.session_state: st.session_state.manual_training_data = load_training_db()
if "approved_dataset" not in st.session_state: st.session_state.approved_dataset = load_approved_dataset()
if "tuning_config" not in st.session_state: st.session_state.tuning_config = load_tuning_config()
if "system_dictionary" not in st.session_state: st.session_state.system_dictionary = load_system_dictionary()
if "pending_invoice" not in st.session_state: st.session_state.pending_invoice = None
if "invoice_queue" not in st.session_state: st.session_state.invoice_queue = []
if "queue_index" not in st.session_state: st.session_state.queue_index = 0
if "last_saved_serial" not in st.session_state: st.session_state.last_saved_serial = None
if "show_user_mgmt" not in st.session_state: st.session_state.show_user_mgmt = False
if "memory_unlocked" not in st.session_state: st.session_state.memory_unlocked = False
if "active_tab" not in st.session_state: st.session_state.active_tab = "records"
if "confirm_delete_id" not in st.session_state: st.session_state.confirm_delete_id = None
if "confirm_delete_proj" not in st.session_state: st.session_state.confirm_delete_proj = False
if "last_created_user" not in st.session_state: st.session_state.last_created_user = None
if "show_change_pwd_modal" not in st.session_state: st.session_state.show_change_pwd_modal = False
if "logged_in" not in st.session_state: st.session_state.logged_in = (st.query_params.get("session_auth") == "auth_valid_session")
if "current_user" not in st.session_state: st.session_state.current_user = None

api_key = ""
try:
    if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
        api_key = str(st.secrets["GEMINI_API_KEY"]).strip().replace('"', '').replace("'", '')
except Exception:
    pass

if not api_key:
    try:
        if os.path.exists(API_KEY_FILE):
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                api_key = f.read().strip().replace('"', '').replace("'", '')
    except Exception:
        pass

# ═════════════════════════════════════════════════════════════════════════
# ─── بوابة تسجيل الدخول ───
# ═════════════════════════════════════════════════════════════════════════
if not st.session_state.logged_in:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
    .stApp { background-color: #050B14 !important; font-family: 'Inter', sans-serif !important; direction: ltr !important; }
    header[data-testid="stHeader"], footer { display: none !important; }
    .block-container { max-width: 1560px !important; padding-top: 2.2rem !important; padding-bottom: 2rem !important; }
    div[data-testid="column"]:nth-child(2) {
        background: #FFFFFF !important; border-radius: 0 24px 24px 0 !important;
        padding: 55px 48px !important; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7) !important;
        min-height: 720px !important; display: flex !important; flex-direction: column !important; justify-content: center !important;
    }
    div[data-testid="column"]:nth-child(2) * { color: #0F172A !important; }
    div[data-testid="column"]:nth-child(2) h2 { font-size: 32px !important; font-weight: 800 !important; margin-bottom: 6px !important; color: #0F172A !important; }
    div[data-testid="column"]:nth-child(2) p.sub-title { color: #64748B !important; font-size: 14.5px !important; margin-bottom: 30px !important; font-weight: 500 !important; }
    div[data-testid="column"]:nth-child(2) .stTextInput label p { color: #334155 !important; font-weight: 700 !important; font-size: 13.5px !important; margin-bottom: 4px !important; }
    div[data-testid="column"]:nth-child(2) .stTextInput input { border-radius: 10px !important; border: 1.5px solid #CBD5E1 !important; background-color: #F8FAFC !important; color: #0F172A !important; padding: 12px 16px !important; font-size: 15px !important; }
    div[data-testid="column"]:nth-child(2) .stTextInput input:focus { border-color: #0284C7 !important; background-color: #FFFFFF !important; }
    div[data-testid="column"]:nth-child(2) button[kind="primary"] {
        background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%) !important; border: none !important;
        border-radius: 10px !important; font-weight: 800 !important; font-size: 16px !important;
        padding: 13px !important; box-shadow: 0 10px 25px -5px rgba(2, 132, 199, 0.45) !important; margin-top: 15px !important;
    }
    div[data-testid="column"]:nth-child(2) button[kind="primary"] p { color: #FFFFFF !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""<div style="display:flex;justify-content:space-between;align-items:center;color:#64748B;font-size:13px;margin-bottom:16px;padding:0 8px;"><div style="display:flex;align-items:center;gap:10px;"><span style="background:#1E293B;color:#38BDF8;padding:4px 10px;border-radius:6px;font-weight:800;font-size:11.5px;">CONTECH VISUAL IDENTITY</span><span style="color:#94A3B8;font-weight:700;">Un-matt ConTech — Unified Login Experience</span></div><div style="font-weight:600;">Target: Enterprise SaaS & Field Web (1920x1080)</div></div>""", unsafe_allow_html=True)

    col_brand, col_auth = st.columns([1.5, 0.95], gap="small")
    with col_brand:
        left_panel_html = (
            "<div style='background:radial-gradient(circle at 15% 15%, #132742 0%, #08111E 65%, #050B14 100%);border:1px solid rgba(255,255,255,0.08);border-radius:24px 0 0 24px;padding:50px 52px;min-height:720px;display:flex;flex-direction:column;justify-content:space-between;'>"
            "<div>"
            "<div style='font-size:28px;font-weight:900;color:#FFFFFF;letter-spacing:0.5px;'>Un-matt <span style='color:#38BDF8;'>ConTech</span></div>"
            "<div style='font-size:11.5px;font-weight:700;color:#94A3B8;letter-spacing:0.15em;text-transform:uppercase;margin-top:4px;'>Enterprise Solutions &bull; Construction Technology</div>"
            "<div style='display:inline-flex;align-items:center;gap:8px;background:rgba(14,165,233,0.12);border:1px solid rgba(56,189,248,0.35);padding:6px 14px;border-radius:8px;font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#E0F2FE;margin:24px 0 20px 0;'>"
            "<span style='width:8px;height:8px;border-radius:50%;background:#38BDF8;box-shadow:0 0 10px #38BDF8;'></span>Invoice Smart System</div>"
            "<h1 style='font-size:40px;font-weight:800;color:#FFFFFF;line-height:1.25;margin-bottom:25px;'>Turn invoices into<br><span style='color:#38BDF8;'>controlled project data</span></h1>"
            "</div>"
            "<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;'>"
            "<div style='background:rgba(15,23,42,0.85);border:1px solid rgba(255,255,255,0.08);border-top:3.5px solid #F97316;border-radius:14px;padding:14px;display:flex;flex-direction:column;justify-content:space-between;'>"
            "<div style='width:100%;height:100px;border-radius:10px;background:rgba(8,14,26,0.95);border:1px solid rgba(255,255,255,0.06);display:flex;align-items:center;justify-content:center;margin-bottom:12px;'>"
            "<svg width='100%' height='100%' viewBox='0 0 160 90' fill='none'>"
            "<rect x='45' y='12' width='70' height='66' rx='5' fill='#1E293B' stroke='#F97316' stroke-width='1.5' />"
            "<line x1='55' y1='25' x2='95' y2='25' stroke='#94A3B8' stroke-width='2' stroke-linecap='round' />"
            "<line x1='55' y1='35' x2='105' y2='35' stroke='#94A3B8' stroke-width='2' stroke-linecap='round' />"
            "<line x1='55' y1='45' x2='85' y2='45' stroke='#94A3B8' stroke-width='2' stroke-linecap='round' />"
            "<line x1='55' y1='55' x2='100' y2='55' stroke='#94A3B8' stroke-width='2' stroke-linecap='round' />"
            "<line x1='35' y1='40' x2='125' y2='40' stroke='#38BDF8' stroke-width='2.5' stroke-dasharray='4 2' />"
            "<polygon points='30,40 38,36 38,44' fill='#38BDF8' />"
            "<polygon points='130,40 122,36 122,44' fill='#38BDF8' />"
            "</svg></div>"
            "<div><div style='font-size:10px;font-weight:800;color:#FB923C;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;'>EXTRACTION ENGINE</div>"
            "<div style='color:#FFFFFF;font-weight:700;font-size:13.5px;margin-bottom:4px;'>Smart Data Extraction</div>"
            "<div style='color:#94A3B8;font-size:11.5px;line-height:1.4;'>Automated OCR parsing & dual textual verification.</div></div></div>"
            "<div style='background:rgba(15,23,42,0.85);border:1px solid rgba(255,255,255,0.08);border-top:3.5px solid #10B981;border-radius:14px;padding:14px;display:flex;flex-direction:column;justify-content:space-between;'>"
            "<div style='width:100%;height:100px;border-radius:10px;background:rgba(8,14,26,0.95);border:1px solid rgba(255,255,255,0.06);display:flex;align-items:center;justify-content:center;margin-bottom:12px;'>"
            "<svg width='100%' height='100%' viewBox='0 0 160 90' fill='none'>"
            "<circle cx='50' cy='45' r='24' stroke='rgba(255,255,255,0.08)' stroke-width='10' />"
            "<circle cx='50' cy='45' r='24' stroke='#10B981' stroke-width='10' stroke-dasharray='70 150' stroke-linecap='round' />"
            "<rect x='90' y='22' width='55' height='16' rx='4' fill='#064E3B' stroke='#10B981' stroke-width='1' />"
            "<text x='96' y='34' fill='#A7F3D0' font-size='8.5' font-weight='700' font-family='monospace'>CBS:01-MAT</text>"
            "<rect x='90' y='44' width='55' height='16' rx='4' fill='#064E3B' stroke='#34D399' stroke-width='1' />"
            "<text x='96' y='56' fill='#6EE7B7' font-size='8.5' font-weight='700' font-family='monospace'>GL:SUB-CON</text>"
            "<path d='M74 45 L90 30 M74 45 L90 52' stroke='#10B981' stroke-width='1.5' stroke-dasharray='2 2' />"
            "</svg></div>"
            "<div><div style='font-size:10px;font-weight:800;color:#34D399;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;'>AUTO COST CODING</div>"
            "<div style='color:#FFFFFF;font-weight:700;font-size:13.5px;margin-bottom:4px;'>Self Aggregation & Classification</div>"
            "<div style='color:#94A3B8;font-size:11.5px;line-height:1.4;'>Dynamic vendor mapping into controlled BOQ ledger.</div></div></div>"
            "<div style='background:rgba(15,23,42,0.85);border:1px solid rgba(255,255,255,0.08);border-top:3.5px solid #0EA5E9;border-radius:14px;padding:14px;display:flex;flex-direction:column;justify-content:space-between;'>"
            "<div style='width:100%;height:100px;border-radius:10px;background:rgba(8,14,26,0.95);border:1px solid rgba(255,255,255,0.06);display:flex;align-items:center;justify-content:center;margin-bottom:12px;'>"
            "<svg width='100%' height='100%' viewBox='0 0 160 90' fill='none'>"
            "<rect x='25' y='55' width='12' height='22' rx='2' fill='#0284C7' />"
            "<rect x='43' y='38' width='12' height='39' rx='2' fill='#38BDF8' />"
            "<rect x='61' y='24' width='12' height='53' rx='2' fill='#0EA5E9' />"
            "<path d='M30 50 Q55 30 85 22 T145 14' stroke='#F59E0B' stroke-width='2.5' fill='none' stroke-linecap='round' />"
            "<circle cx='145' cy='14' r='4' fill='#FBBF24' />"
            "<rect x='90' y='42' width='58' height='26' rx='4' fill='#0C4A6E' stroke='#38BDF8' stroke-width='1' />"
            "<text x='96' y='55' fill='#E0F2FE' font-size='8' font-weight='800'>&uarr; Cash Drift</text>"
            "<text x='96' y='64' fill='#7DD3FC' font-size='7.5' font-weight='600'>94% Efficiency</text>"
            "</svg></div>"
            "<div><div style='font-size:10px;font-weight:800;color:#38BDF8;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;'>EXECUTIVE INTELLIGENCE</div>"
            "<div style='color:#FFFFFF;font-weight:700;font-size:13.5px;margin-bottom:4px;'>Expenses Analysis & Actionable Insights</div>"
            "<div style='color:#94A3B8;font-size:11.5px;line-height:1.4;'>Board-ready A3 KPIs, burn rate, and cost control.</div></div></div>"
            "</div></div>"
        )
        st.markdown(left_panel_html, unsafe_allow_html=True)

    with col_auth:
        st.markdown("<h2>Welcome back</h2>", unsafe_allow_html=True)
        st.markdown("<p class='sub-title'>Sign in to your Un-matt workspace</p>", unsafe_allow_html=True)
        
        login_email = st.text_input("Email Address", value="", key="auth_email_field")
        login_password = st.text_input("Password", type="password", value="", key="auth_password_field")
        
        if st.button("Sign in →", type="primary", use_container_width=True):
            clean_email = login_email.strip().lower()
            clean_pwd = login_password.strip()
            user_found = next((k for k in st.session_state.users_db if k.lower() == clean_email), None)
            if (user_found and st.session_state.users_db[user_found]["password_hash"] == hash_password(clean_pwd)) or (clean_email == "halawa1981@gmail.com" and clean_pwd == "01230030480Ab"):
                st.session_state.logged_in = True
                st.session_state.current_user = user_found if user_found else "halawa1981@gmail.com"
                st.query_params.clear()
                st.query_params["session_auth"] = "auth_valid_session"
                st.rerun()
            else:
                st.error("Invalid email or password.")
                
        st.markdown("""<div style="display:flex;align-items:center;justify-content:center;gap:8px;font-size:12px;color:#94A3B8;font-weight:600;border-top:1px solid #F1F5F9;padding-top:25px;margin-top:30px;"><span style="color:#94A3B8 !important;">Enterprise Grade &bull; 256-bit SSL Security Protocol</span></div>""", unsafe_allow_html=True)
    st.stop()

# ─── فحص المستخدم والحالة الأمنية لكلمة المرور ───
current_user_data = st.session_state.users_db.get(st.session_state.current_user, {
    "name": "م/ محمد حلاوة", "role": "Super Admin", "allowed_projects": "All", "must_change_password": False
})
user_role = current_user_data.get("role", "Accountant")
must_change = current_user_data.get("must_change_password", False) or st.session_state.show_change_pwd_modal

if must_change:
    st.markdown("""
    <div style="max-width: 650px; margin: 40px auto; background: var(--bg-card); padding: 35px; border-radius: 16px; border: 2px solid #38BDF8; box-shadow: 0 15px 35px rgba(0,0,0,0.4);">
        <h3 style="color: #38BDF8; margin-top: 0;">🔐 تحديث كلمة المرور (Security Update)</h3>
        <p style="color: var(--text-muted); font-size: 14px;">يرجى تعيين كلمة مرور قوية جديدة لحسابك للمتابعة إلى لوحة التحكم.</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.container():
        c_p1, c_p2, c_p3 = st.columns([1, 2, 1])
        with c_p2:
            new_p1 = st.text_input("كلمة المرور الجديدة (New Password):", type="password", key="new_p1_in")
            new_p2 = st.text_input("تأكيد كلمة المرور (Confirm Password):", type="password", key="new_p2_in")
            
            if st.button("حفظ وتأكيد كلمة المرور 🔒", type="primary", use_container_width=True):
                if len(new_p1.strip()) < 6:
                    st.error("كلمة المرور يجب أن لا تقل عن 6 أحرف أو أرقام.")
                elif new_p1.strip() != new_p2.strip():
                    st.error("كلمتا المرور غير متطابقتين، يرجى إعادة التأكيد.")
                else:
                    user_email = st.session_state.current_user
                    st.session_state.users_db[user_email]["password_hash"] = hash_password(new_p1.strip())
                    st.session_state.users_db[user_email]["must_change_password"] = False
                    save_users_db(st.session_state.users_db)
                    st.session_state.show_change_pwd_modal = False
                    st.toast("تم تحديث كلمة المرور بنجاح!", icon="✅")
                    time.sleep(0.8)
                    st.rerun()
            
            if not current_user_data.get("must_change_password", False):
                if st.button("إلغاء والعودة", use_container_width=True):
                    st.session_state.show_change_pwd_modal = False
                    st.rerun()
    st.stop()

# ─── صلاحيات النظام العامة ───
is_super_admin = (user_role == "Super Admin")
is_company_admin = (user_role == "Admin" or is_super_admin)
is_ceo = (user_role == "CEO")
is_accountant = (user_role == "Accountant")

is_rtl = (st.session_state.system_lang == "العربية")
dir_attr = "rtl" if is_rtl else "ltr"

# ─── تهيئة التنسيق والألوان ───
if st.session_state.system_theme == "Dark":
    st.markdown(f"""
    <style>
    :root {{
        --bg-main: #0B1120; --bg-card: #1E293B; --bg-input: #0F172A; --border-subtle: #334155; --border-strong: #475569;
        --text-title: #F8FAFC; --text-body: #CBD5E1; --text-muted: #94A3B8; --brand-primary: #38BDF8;
        --kpi-inflow-bg: rgba(6, 78, 59, 0.25); --kpi-inflow-border: #10B981; --kpi-inflow-text: #34D399;
        --kpi-outflow-bg: rgba(127, 29, 29, 0.25); --kpi-outflow-border: #EF4444; --kpi-outflow-text: #F87171;
        --kpi-balance-bg: rgba(12, 74, 110, 0.25); --kpi-balance-border: #38BDF8; --kpi-balance-text: #38BDF8;
        --kpi-rate-bg: rgba(120, 53, 15, 0.25); --kpi-rate-border: #F59E0B; --kpi-rate-text: #FBBF24;
        --table-header-bg: #0F172A; --table-row-even: #1E293B; --table-row-odd: #182234; --table-row-hover: #26354D; --table-border: #334155;
    }}
    .stApp {{ background-color: var(--bg-main) !important; color: var(--text-body) !important; direction: {dir_attr}; }}
    section[data-testid="stSidebar"] {{ background-color: #111827 !important; border-left: 2px solid var(--border-subtle) !important; direction: {dir_attr}; }}
    .grid-header {{ background-color: var(--table-header-bg) !important; color: var(--text-title) !important; font-weight: 900; font-size: 14px; padding: 12px 6px; border-radius: 8px 8px 0 0; text-align: center; border: 1px solid var(--table-border); position: sticky !important; top: 0 !important; z-index: 999 !important; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3) !important; }}
    .grid-row-inbound {{ background-color: var(--kpi-inflow-bg) !important; color: var(--kpi-inflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-inflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    .grid-row-outbound {{ background-color: var(--kpi-outflow-bg) !important; color: var(--kpi-outflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-outflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    [data-testid="stFileUploader"] {{ background: var(--bg-input) !important; border: 1.5px dashed var(--border-strong) !important; border-radius: 10px; }}
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <style>
    :root {{
        --bg-main: #F8FAFC; --bg-card: #FFFFFF; --border-subtle: #E2E8F0; --border-strong: #CBD5E1;
        --text-title: #0F172A; --text-body: #334155; --text-muted: #64748B; --brand-primary: #0284C7; --brand-navy: #0F2545;
        --kpi-inflow-bg: #F0FDF4; --kpi-inflow-border: #10B981; --kpi-inflow-text: #047857;
        --kpi-outflow-bg: #FEF2F2; --kpi-outflow-border: #EF4444; --kpi-outflow-text: #B91C1C;
        --kpi-balance-bg: #F0F9FF; --kpi-balance-border: #0284C7; --kpi-balance-text: #0369A1;
        --kpi-rate-bg: #FFFBEB; --kpi-rate-border: #F59E0B; --kpi-rate-text: #B45309;
        --table-header-bg: #0F2545; --table-row-even: #FFFFFF; --table-row-odd: #F8FAFC; --table-row-hover: #F1F5F9; --table-border: #E2E8F0;
    }}
    .stApp {{ background-color: var(--bg-main) !important; color: var(--text-body) !important; direction: {dir_attr}; }}
    section[data-testid="stSidebar"] {{ background-color: #F1F5F9 !important; border-left: 2px solid var(--border-subtle) !important; direction: {dir_attr}; }}
    .grid-header {{ background-color: var(--table-header-bg) !important; color: #FFFFFF !important; font-weight: 900; font-size: 14px; padding: 12px 6px; border-radius: 8px 8px 0 0; text-align: center; border: 1px solid var(--table-border); position: sticky !important; top: 0 !important; z-index: 999 !important; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.15) !important; }}
    .grid-row-inbound {{ background-color: var(--kpi-inflow-bg) !important; color: var(--kpi-inflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-inflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    .grid-row-outbound {{ background-color: var(--kpi-outflow-bg) !important; color: var(--kpi-outflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-outflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    [data-testid="stFileUploader"] {{ background: var(--bg-card) !important; border: 1.5px dashed var(--border-strong) !important; border-radius: 10px; }}
    </style>
    """, unsafe_allow_html=True)

if st.session_state.system_lang == "العربية":
    t = {
        "add_proj": "➕ إضافة مشروع جديد...", "proj_label": "المشروع الحالي:", "save_proj": "حفظ المشروع", "new_proj_name": "اسم المشروع الجديد:",
        "user_mgmt": "⚙️ إدارة المستخدمين", "logout": "🚪 خروج", "user_mgmt_title": "👥 لوحة التحكم في المستخدمين والصلاحيات",
        "tab_records": "📑 جدول ومطابقة الفواتير", "tab_analytics": "📊 تحليلات ومؤشرات المشروع", "tab_memory": "⚙️ سياسات وضوابط النظام",
        "metric_in": "العهدة الواردة ⬇️", "metric_out": "إجمالي المنصرف ↗️", "metric_bal": "صافي السيولة 💰", "metric_burn": "معدل الاستهلاك ⚡", "curr": "ج.م",
        "filter_title": "🔍 أدوات البحث وتصفية السجلات", "filter_cat": "📂 التصنيف:", "filter_pay": "💳 طريقة الدفع:", "filter_date": "📅 الفترة:",
        "all": "الكل", "today": "اليوم", "this_week": "هذا الأسبوع", "this_month": "هذا الشهر", "custom": "فترة مخصصة", "from_date": "من تاريخ:", "to_date": "إلى تاريخ:",
        "no_records": "لا توجد سجلات مطابقة حالياً لعرضها في الجدول", "export_excel": "📥 تصدير السجلات إلى Excel (.xlsx)",
        "inbound": "وارد", "outbound": "منصرف", "view_att": "عرض المرفق", "col_serial": "السريال", "col_type": "نوع الحركة", "col_doc_no": "رقم المستند",
        "col_date": "التاريخ", "col_desc": "البيان / الوصف", "col_amount": "المبلغ", "col_vat": "الضريبة", "col_pay": "طريقة الدفع", "col_cat": "التصنيف",
        "col_remark": "الملاحظات", "col_del": "حذف", "col_att": "المرفقات",
        "sec_reg": "🧾 تسجيل فاتورة / مستند سداد جديد", "doc_type_prompt": "نوع المستندات المرفقة:", "out_opt": "🔴 منصرف (فواتير / إيصالات صرف)", "in_opt": "🟢 وارد (سندات قبض / تحويلات)",
        "tab_upload": "📁 رفع ملفات (صور / PDF)", "tab_paste": "📋 لصق مباشر (Ctrl + V)", "choose_files": "📂 اختر المستندات من جهازك:", "paste_hint": "💡 الصق لقطة الشاشة هنا مباشرة:",
        "start_process": "بدء المعالجة واستخراج البيانات", "merge_btn": "📎 إرفاق كمرفق", "save_btn": "✅ اعتماد وحفظ كفاتورة", "dismiss_btn": "❌ استبعاد",
        "settings_title": "⚙️ الإعدادات", "lang_label": "اللغة:", "theme_label": "المظهر:", "theme_light": "☀️ نهاري", "theme_dark": "🌙 ليلي",
        "connected": "🟢 متصل", "disconnected": "🔴 غير متصل", "synced": "🟢 متزامن", "sync_btn": "🔄 مزامنة السجلات من الشيت",
        "future_title": "🚀 خدمات المؤسسة المستقبلية", "coming_soon": "قريباً", "market_price": "📊 مقارنة أسعار السوق الفورية",
        "market_desc": "مطابقة أسعار الفواتير مع مؤشرات مواد البناء للتنبيه بالزيادات غير المبررة.",
        "boq_title": "🎯 الرقابة على الموازنة والـ BOQ", "boq_desc": "ربط بنود الفواتير بمقايسة المشروع للتحكم في التكاليف ومنع التجاوز.",
        "analytics_title": "📊 مؤشرات وتحليلات المشروع", "print_report": "🖨️ طباعة التقرير التنفيذي المعتمد (A3)",
        "chart_cat": "توزيع المنصرف حسب التصنيف", "chart_pay": "طرق السداد المستخدمة", "audit_title": "📋 سجل العمليات وحركات الحذف",
        "queue_info": "⏳ قائمة المراجعة: المستند رقم", "of_total": "من إجمالي",
        "calc_title": "🔢 آلة حاسبة", "calc_btn": "احسب", "calc_res": "النتيجة:"
    }
else:
    t = {
        "add_proj": "➕ Add New Project...", "proj_label": "Current Project:", "save_proj": "Save Project", "new_proj_name": "New Project Name:",
        "user_mgmt": "⚙️ User Management", "logout": "🚪 Logout", "user_mgmt_title": "👥 User Access & Permissions Control",
        "tab_records": "📑 Invoice Log & Reconciliation", "tab_analytics": "📊 Analytics & Reports", "tab_memory": "⚙️ System Policies & Controls",
        "metric_in": "Total Inbound Funds ⬇️", "metric_out": "Total Expenses ↗️", "metric_bal": "Net Balance 💰", "metric_burn": "Burn Rate ⚡", "curr": "EGP",
        "filter_title": "🔍 Search & Filter Tools", "filter_cat": "📂 Category:", "filter_pay": "💳 Payment Method:", "filter_date": "📅 Period:",
        "all": "All", "today": "Today", "this_week": "This Week", "this_month": "This Month", "custom": "Custom Range", "from_date": "From:", "to_date": "To:",
        "no_records": "No matching records found to display.", "export_excel": "📥 Export to Excel (.xlsx)",
        "inbound": "Inbound", "outbound": "Outbound", "view_att": "View File", "col_serial": "Serial", "col_type": "Type", "col_doc_no": "Doc No.",
        "col_date": "Date", "col_desc": "Description", "col_amount": "Amount", "col_vat": "VAT", "col_pay": "Payment Method", "col_cat": "Category",
        "col_remark": "Remarks", "col_del": "Delete", "col_att": "Attachment",
        "sec_reg": "🧾 Register Invoice / Payment Receipt", "doc_type_prompt": "Document Type:", "out_opt": "🔴 Outbound (Expense/Invoice)", "in_opt": "🟢 Inbound (Receipt/Transfer)",
        "tab_upload": "📁 Upload Files (Images/PDF)", "tab_paste": "📋 Direct Paste (Ctrl + V)", "choose_files": "📂 Choose files from device:", "paste_hint": "💡 Paste image directly here:",
        "start_process": "Start Processing & Extraction", "merge_btn": "📎 Attach as Document", "save_btn": "✅ Approve & Save", "dismiss_btn": "❌ Exclude",
        "settings_title": "⚙️ Settings", "lang_label": "Language:", "theme_label": "Theme:", "theme_light": "☀️ Light", "theme_dark": "🌙 Dark",
        "connected": "🟢 Connected", "disconnected": "🔴 Disconnected", "synced": "🟢 Synced", "sync_btn": "🔄 Sync Records from Sheet",
        "future_title": "🚀 Coming Future Services", "coming_soon": "Coming Soon", "market_price": "📊 Real-Time Market Price Check",
        "market_desc": "Match invoices against construction market indices to detect unjustified cost increases.",
        "boq_title": "🎯 BOQ & Budget Control", "boq_desc": "Link invoices directly with project BOQ items to control costs and eliminate overspending.",
        "analytics_title": "📊 Project Analytics & Executive Summary", "print_report": "🖨️ Print Executive Report (A3)",
        "chart_cat": "Expense Distribution by Category", "chart_pay": "Payment Methods Breakdown", "audit_title": "📋 Audit Trail & Deletion Log",
        "queue_info": "⏳ Review Queue: Document", "of_total": "of total",
        "calc_title": "🔢 Calculator", "calc_btn": "Calculate", "calc_res": "Result:"
    }

with st.sidebar:
    logo_path = os.path.join(BASE_DIR, "logo.PNG")
    logo_b64_str = ""
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as lf: logo_b64_str = base64.b64encode(lf.read()).decode("utf-8")
        except Exception: pass

    if logo_b64_str:
        st.markdown(f"""
        <div style="display: flex; justify-content: center; align-items: center; margin-bottom: 20px;">
            <div style="width: 145px; height: 145px; border-radius: 50%; background-color: #FFFFFF; border: 3px solid #1E3A8A; box-shadow: 0px 4px 10px rgba(0,0,0,0.08); display: flex; align-items: center; justify-content: center; overflow: hidden; padding: 10px;">
                <img src="data:image/png;base64,{logo_b64_str}" style="width: 100%; height: 100%; object-fit: contain;" />
            </div>
        </div>
        """, unsafe_allow_html=True)
    else: st.title("🏢 Un-matt ConTech")
    
    st.header(t["settings_title"])
    lang_choice = st.radio(t["lang_label"], ["العربية", "English"], index=0 if st.session_state.system_lang == "العربية" else 1, horizontal=True)
    if lang_choice != st.session_state.system_lang:
        st.session_state.system_lang = lang_choice; st.rerun()
    
    theme_options = [t["theme_light"], t["theme_dark"]]
    cur_th_idx = 0 if st.session_state.system_theme == "Light" else 1
    theme_selected = st.radio(t["theme_label"], theme_options, index=cur_th_idx, horizontal=True)
    new_theme = "Light" if theme_selected == t["theme_light"] else "Dark"
    if new_theme != st.session_state.system_theme:
        st.session_state.system_theme = new_theme; st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    col_s1, col_s2 = st.columns(2)
    with col_s1: st.caption(t["connected"] if api_key else t["disconnected"])
    with col_s2: st.caption(t["synced"])
        
    if st.button(t["sync_btn"], use_container_width=True):
        with st.spinner("Syncing..."):
            st.session_state.invoices_data = load_cloud_records()
            st.toast("Sync complete!", icon="☁️")
            time.sleep(0.5); st.rerun()

    st.divider()
    with st.expander(t["calc_title"], expanded=False):
        calc_expr = st.text_input("Expression (e.g. 801*1.14):", value="", key="quick_calc_in")
        if st.button(t["calc_btn"], use_container_width=True):
            try:
                clean_expr = re.sub(r'[^0-9\+\-\*\/\.\(\)\s]', '', calc_expr)
                if clean_expr.strip():
                    res = eval(clean_expr)
                    st.success(f"{t['calc_res']} **{res:,.2f}**")
            except Exception:
                st.error("Error in expression")

    st.divider()
    st.markdown(f"#### {t['future_title']}")
    st.markdown(f"""
    <div class="roadmap-card">
        <span class="roadmap-badge">{t['coming_soon']}</span>
        <div style="font-weight: bold; font-size: 13px;">{t['market_price']}</div>
        <div style="color: var(--text-muted); font-size: 11px; margin-top: 3px;">{t['market_desc']}</div>
    </div>
    <div class="roadmap-card">
        <span class="roadmap-badge">{t['coming_soon']}</span>
        <div style="font-weight: bold; font-size: 13px;">{t['boq_title']}</div>
        <div style="color: var(--text-muted); font-size: 11px; margin-top: 3px;">{t['boq_desc']}</div>
    </div>
    """, unsafe_allow_html=True)

col_proj, col_proj_del, col_empty, col_user = st.columns([2.0, 0.5, 0.3, 2.2])

can_manage_projects = is_company_admin or is_ceo or is_super_admin
if can_manage_projects:
    available_projects = st.session_state.projects_list + [t["add_proj"]]
else:
    available_projects = current_user_data.get("allowed_projects", [DEFAULT_PROJECTS[0]])
    if isinstance(available_projects, str): available_projects = [available_projects]

selected_proj = col_proj.selectbox(t["proj_label"], available_projects, label_visibility="collapsed")

with col_proj_del:
    if can_manage_projects and selected_proj != t["add_proj"]:
        if st.button("🗑️", help="Delete Project", use_container_width=True):
            st.session_state.confirm_delete_proj = True

if st.session_state.confirm_delete_proj and can_manage_projects:
    st.warning(f"Delete project: {selected_proj}?")
    c_yd, c_nd, _ = st.columns([1, 1, 4])
    with c_yd:
        if st.button("Confirm", type="primary", use_container_width=True):
            if selected_proj in st.session_state.projects_list:
                st.session_state.projects_list.remove(selected_proj)
                if not st.session_state.projects_list: st.session_state.projects_list = list(DEFAULT_PROJECTS)
                save_projects_list_to_disk(st.session_state.projects_list)
                st.session_state.confirm_delete_proj = False
                st.toast("Project deleted!", icon="✅")
                time.sleep(0.5); st.rerun()
    with c_nd:
        if st.button("Cancel", use_container_width=True):
            st.session_state.confirm_delete_proj = False; st.rerun()

if selected_proj == t["add_proj"] and can_manage_projects:
    new_p_name = col_proj.text_input(t["new_proj_name"])
    if col_proj.button(t["save_proj"], type="primary"):
        if new_p_name and new_p_name not in st.session_state.projects_list:
            st.session_state.projects_list.append(new_p_name)
            save_projects_list_to_disk(st.session_state.projects_list)
            st.rerun()

with col_user:
    role_badges = {
        "Super Admin": "🛡️ Super Admin",
        "Admin": "👑 Company Admin",
        "CEO": "💼 CEO",
        "Accountant": "📊 Accountant"
    }
    st.info(f"**{current_user_data['name']}** &bull; `{role_badges.get(user_role, user_role)}`")
    
    b_c1, b_c2, b_c3 = st.columns([1.2, 1, 0.8])
    with b_c1:
        if (is_company_admin or is_ceo or is_super_admin) and st.button(t["user_mgmt"], use_container_width=True):
            st.session_state.show_user_mgmt = not st.session_state.show_user_mgmt; st.rerun()
    with b_c2:
        if st.button("🔑 كلمة المرور", use_container_width=True):
            st.session_state.show_change_pwd_modal = True; st.rerun()
    with b_c3:
        if st.button(t["logout"], use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.current_user = None
            st.session_state.show_user_mgmt = False
            st.session_state.last_created_user = None
            if "session_auth" in st.query_params: del st.query_params["session_auth"]
            st.rerun()

if (is_company_admin or is_ceo or is_super_admin) and st.session_state.show_user_mgmt:
    st.divider()
    st.subheader(t["user_mgmt_title"])
    with st.expander("➕ Invite New Team Member", expanded=True):
        inv_col1, inv_col2, inv_col3 = st.columns([1.5, 1.5, 1])
        with inv_col1:
            new_u_email = st.text_input("User Email:")
            new_u_name = st.text_input("Full Name:")
            new_u_phone = st.text_input("WhatsApp Phone (e.g. +966 / +20):", value="+20")
        with inv_col2:
            allowed_roles = ["Accountant"] if is_ceo and not is_super_admin else ["Accountant", "CEO", "Admin"]
            assigned_role = st.selectbox("Role:", allowed_roles)
            proj_options = ["All"] + st.session_state.projects_list
            selected_allowed = st.multiselect("Allowed Projects:", proj_options, default=["All"] if assigned_role != "Accountant" else [selected_proj])
        with inv_col3:
            gen_temp_pass = st.checkbox("Generate secure temp password", value=True)
            custom_pass = st.text_input("Custom Password:", value="Temp#2026") if not gen_temp_pass else None
            custom_url = st.text_input("Platform Access URL:", value="https://unmatt-contech-app-al-yuser-cr9hbfiqsakvks5vupkgsz.streamlit.app/")
            
        if st.button("Create Account & Generate Access Link", type="primary", use_container_width=True):
            if not new_u_email or "@" not in new_u_email: 
                st.error("Enter valid email.")
            else:
                temp_password = generate_temp_password(10) if gen_temp_pass else custom_pass
                clean_email = new_u_email.strip().lower()
                st.session_state.users_db[clean_email] = {
                    "name": new_u_name, "password_hash": hash_password(temp_password),
                    "role": assigned_role, "allowed_projects": "All" if "All" in selected_allowed else selected_allowed,
                    "must_change_password": True
                }
                save_users_db(st.session_state.users_db)
                
                st.session_state.last_created_user = {
                    "email": clean_email,
                    "name": new_u_name,
                    "password": temp_password,
                    "role": assigned_role,
                    "phone": re.sub(r'[^0-9]', '', new_u_phone),
                    "access_url": custom_url.strip()
                }
                st.toast(f"Account for {new_u_name} registered successfully!", icon="✅")

    if st.session_state.last_created_user:
        u_info = st.session_state.last_created_user
        app_url = u_info.get("access_url", "https://unmatt-contech-app-al-yuser-cr9hbfiqsakvks5vupkgsz.streamlit.app/")
        msg_body = f"""مرحباً {u_info['name']}،
تم إنشاء حساب لك على منصة Un-matt ConTech لإدارة وتدقيق الفواتير.

🔑 بيانات الدخول الخاصة بك:
- البريد الإلكتروني: {u_info['email']}
- كلمة المرور المؤقتة: {u_info['password']}
- الدور الوظيفي: {u_info['role']}
- رابط الدخول المباشر: {app_url}

⚠️ يرجى العلم أنه سيُطلب منك تعيين كلمة مرور جديدة فور تسجيل الدخول لأول مرة."""
        
        encoded_msg = urllib.parse.quote(msg_body)
        wa_link = f"https://wa.me/{u_info['phone']}?text={encoded_msg}" if u_info['phone'] else f"https://api.whatsapp.com/send?text={encoded_msg}"

        st.markdown(f"""
        <div class="invite-success-card">
            <h4 style="margin: 0 0 10px 0; color: #10B981;">🎉 تم إنشاء الحساب بنجاح - بيانات اعتماد المستخدم</h4>
            <div style="font-size: 14px; line-height: 1.8; color: var(--text-title);">
                <b>الاسم:</b> {u_info['name']} &bull; <b>البريد:</b> <code>{u_info['email']}</code> &bull; <b>كلمة المرور المؤقتة:</b> <code style="color:#EF4444; font-weight:bold;">{u_info['password']}</code>
                <br><b>رابط المنصة المرسل:</b> <a href="{app_url}" target="_blank" style="color:#38BDF8;">{app_url}</a>
            </div>
            <div style="margin-top: 15px;">
                <a href="{wa_link}" target="_blank" class="whatsapp-btn" style="display:inline-block; background:#25D366; color:#FFF; padding:10px 20px; border-radius:8px; text-decoration:none; font-weight:bold;">
                    💬 إرسال بيانات الدخول عبر واتساب فوراً
                </a>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.stop()

st.divider()

project_invoices = [item for item in st.session_state.invoices_data if item.get("project") == selected_proj]
active_project_invoices = [item for item in project_invoices if not item.get("delete", False)]

total_in = sum(item["amount"] for item in active_project_invoices if item["doc_type"] == "وارد")
total_out = sum(item["amount"] for item in active_project_invoices if item["doc_type"] == "منصرف")
balance = total_in - total_out
burn_rate = (total_out / total_in * 100) if total_in > 0 else 0

tabs_list = [t["tab_records"], t["tab_analytics"]]
if is_company_admin or is_super_admin:
    tabs_list.append(t["tab_memory"])

tab_cols = st.columns(len(tabs_list))
for idx, tab_name in enumerate(tabs_list):
    key_slug = "records" if idx == 0 else ("analytics" if idx == 1 else "memory")
    with tab_cols[idx]:
        if st.button(tab_name, use_container_width=True, type="primary" if st.session_state.active_tab == key_slug else "secondary"):
            st.session_state.active_tab = key_slug; st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

if st.session_state.active_tab == "records":
    st.markdown(f"""
    <div style='display: flex; gap: 15px; margin-bottom: 30px;'>
        <div style='flex: 1; background: var(--kpi-inflow-bg); border-top: 4px solid var(--kpi-inflow-border); padding: 15px; border-radius: 8px; text-align: center;'><h5 style='color: var(--kpi-inflow-text); margin: 0;'>{t["metric_in"]}</h5><h3 style='color: var(--kpi-inflow-text); margin: 5px 0 0 0;'>{total_in:,.2f} {t["curr"]}</h3></div>
        <div style='flex: 1; background: var(--kpi-outflow-bg); border-top: 4px solid var(--kpi-outflow-border); padding: 15px; border-radius: 8px; text-align: center;'><h5 style='color: var(--kpi-outflow-text); margin: 0;'>{t["metric_out"]}</h5><h3 style='color: var(--kpi-outflow-text); margin: 5px 0 0 0;'>{total_out:,.2f} {t["curr"]}</h3></div>
        <div style='flex: 1; background: var(--kpi-balance-bg); border-top: 4px solid var(--kpi-balance-border); padding: 15px; border-radius: 8px; text-align: center;'><h4 style='color: var(--kpi-balance-text); margin: 0;'>{t["metric_bal"]}</h4><h3 style='color: var(--kpi-balance-text); margin: 5px 0 0 0;'>{balance:,.2f} {t["curr"]}</h3></div>
        <div style='flex: 1; background: var(--kpi-rate-bg); border-top: 4px solid var(--kpi-rate-border); padding: 15px; border-radius: 8px; text-align: center;'><h5 style='color: var(--kpi-rate-text); margin: 0;'>{t["metric_burn"]}</h5><h3 style='color: var(--kpi-rate-text); margin: 5px 0 0 0;'>{burn_rate:.1f}%</h3></div>
    </div>
    """, unsafe_allow_html=True)

    if not is_ceo or is_super_admin:
        if len(st.session_state.invoice_queue) == 0:
            st.markdown(f"""
            <div style="background-color: var(--table-header-bg); color: white; padding: 14px 25px; border-radius: 8px; font-size: 20px; font-weight: 800; margin-bottom: 20px; border-right: 6px solid var(--brand-primary);">
                {t['sec_reg']}
            </div>
            """, unsafe_allow_html=True)
            
            doc_type_opts = [t["out_opt"], t["in_opt"]]
            doc_type_selection = st.radio(t["doc_type_prompt"], doc_type_opts, index=0, horizontal=True)
            is_inbound = (doc_type_selection == t["in_opt"])

            upload_tab1, upload_tab2 = st.tabs([t["tab_upload"], t["tab_paste"]])
            main_files = []
            with upload_tab1:
                uploaded = st.file_uploader(t["choose_files"], type=['jpg', 'png', 'jpeg', 'pdf'], accept_multiple_files=True)
                if uploaded: main_files.extend(uploaded)
                    
            with upload_tab2:
                st.caption(t["paste_hint"])
                pasted_img = st.file_uploader("Upload pasted screenshot:", type=['png', 'jpg', 'jpeg'], key="paste_uploader")
                if pasted_img: main_files.append(pasted_img)
            
            if st.button(t["start_process"], type="primary"):
                if not api_key: st.error("⚠️ API key disconnected.")
                elif not main_files: st.warning("⚠️ Please select files first.")
                else:
                    with st.spinner("Processing files..."):
                        st.session_state.invoice_queue = []
                        for file in main_files:
                            if file.name.lower().endswith('.pdf'):
                                doc = fitz.open(stream=file.read(), filetype="pdf")
                                for i in range(len(doc)):
                                    pix = doc.load_page(i).get_pixmap(dpi=130) 
                                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                    st.session_state.invoice_queue.append({"image": img, "name": f"{file.name} - p{i+1}"})
                            else:
                                img = Image.open(file)
                                st.session_state.invoice_queue.append({"image": img, "name": file.name})
                        st.session_state.queue_index = 0
                        st.session_state.pending_invoice = None
                        st.session_state.last_saved_serial = active_project_invoices[-1]["serial_no"] if active_project_invoices else None
                        st.session_state.pending_doc_type = "وارد" if is_inbound else "منصرف"
                        st.rerun()

        elif st.session_state.queue_index < len(st.session_state.invoice_queue):
            current_idx = st.session_state.queue_index
            total_items = len(st.session_state.invoice_queue)
            current_item = st.session_state.invoice_queue[current_idx]
            current_type = st.session_state.pending_doc_type
            
            st.info(f"{t['queue_info']} ({current_idx + 1}) {t['of_total']} ({total_items}) - `{current_item['name']}`")
            
            if st.session_state.pending_invoice is None:
                with st.spinner("جاري استخراج وتدقيق بيانات المستند..."):
                    try:
                        time.sleep(0.4) 
                        doc_context = "سند قبض مالي (وارد للعهدة)" if current_type == "وارد" else "فاتورة مصروفات أو إيصال صرف (منصرف)"
                        rules = st.session_state.system_dictionary
                        prompt = f"""أنت مراجع مالي أول وخبير تدقيق مستندات مشاريع إنشائية.
نوع المستند: {doc_context}.
قواعد الشركة وقاموس الموردين: {rules}
المشروع الحالي: {selected_proj}
المطلوب استخراج الحقول بدقة ومطابقة التفقيط بالأرقام."""
                        st.session_state.pending_invoice = analyze_invoice_with_gemini(current_item["image"], prompt, api_key, current_project=selected_proj)
                        st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ خطأ أثناء الاستخراج: {e}")
                        if st.button("تخطي المستند الحالي"):
                            st.session_state.pending_invoice = None
                            st.session_state.queue_index += 1
                            st.rerun()
                        st.stop()
            
            data = st.session_state.pending_invoice
            if isinstance(data, list): data = data[0] if len(data) > 0 and isinstance(data[0], dict) else {}
            elif not isinstance(data, dict): data = {}
                
            col_preview, col_form = st.columns([1, 2.2])
            with col_preview: 
                st.image(current_item["image"], use_container_width=True)

            with col_form:
                c1, c2 = st.columns(2)
                with c1:
                    inv_no = st.text_input(t["col_doc_no"], value=str(data.get("invoice_no", "")))
                with c2:
                    inv_date = st.text_input(f"{t['col_date']} (YYYY-MM-DD)", value=normalize_date(data.get("invoice_date", "")))
                
                c3, c4 = st.columns(2)
                with c3:
                    amount = st.number_input(f"{t['col_amount']} ({t['curr']})", value=float(data.get("amount", 0.0)))
                with c4: 
                    vat = st.number_input(t["col_vat"], value=float(data.get("vat", 0.0)))
                
                desc = st.text_input(t["col_desc"], value=str(data.get("description", "")))
                
                duplicate_found = None
                clean_inv_no = str(inv_no).strip()
                if clean_inv_no:
                    for past_idx, past_inv in enumerate(active_project_invoices):
                        if (str(past_inv.get("invoice_no", "")).strip() == clean_inv_no and 
                            abs(float(past_inv.get("amount", 0.0)) - float(amount)) < 0.01):
                            duplicate_found = (past_idx + 1, past_inv)
                            break

                initial_remark = str(data.get("remark", ""))
                if duplicate_found and "[مكررة:" not in initial_remark:
                    initial_remark = f"[مكررة: مطابقة للحركة رقم {duplicate_found[0]}] " + initial_remark
                    
                remark = st.text_input(t["col_remark"], value=initial_remark)
                
                if duplicate_found:
                    st.markdown(f"""
                    <div class="duplicate-warning-box">
                        ⚠️ تنبيه تكرار: المستند رقم ({clean_inv_no}) بمبلغ ({amount:,.2f} {t['curr']}) مسجل مسبقاً في الحركة رقم ({duplicate_found[0]}).
                    </div>
                    """, unsafe_allow_html=True)
                
                c5, c6 = st.columns(2)
                ai_pay = data.get("payment_method", "غير مذكور")
                pay_options = ["نقدي", "شيك", "تحويل بنكي", "تحويل إنستا باي", "غير مذكور"]
                pay_method = c5.selectbox(t["col_pay"], pay_options, index=pay_options.index(ai_pay) if ai_pay in pay_options else 0)
                
                ai_cat = data.get("category", "")
                cat_options = ["مقاولين", "موردين", "مواد", "معدات", "عمالة", "نثريات", "تمويل عهدة (وارد)"]
                category = c6.selectbox(t["col_cat"], cat_options, index=cat_options.index(ai_cat) if ai_cat in cat_options else (6 if current_type == 'وارد' else 0))
                
                st.divider()
                c_btn1, c_btn_merge, c_btn3 = st.columns([2.2, 1.8, 0.9])
                with c_btn1:
                    allow_save = True
                    if duplicate_found:
                        confirm_dup = st.checkbox("تأكيد حفظ المستند رغم التكرار", value=False)
                        allow_save = confirm_dup

                    if st.button(t["save_btn"], type="primary", use_container_width=True, disabled=(not allow_save)):
                        with st.spinner("جاري الاعتماد وتوثيق القيد..."):
                            try:
                                new_serial = len(active_project_invoices) + 1
                                type_icon = "🟢 وارد" if current_type == "وارد" else "🔴 منصرف"
                                clean_inv_date = normalize_date(inv_date)
                                row_data = [new_serial, type_icon, inv_no, clean_inv_date, desc, amount, vat, pay_method, category, remark, "False", "مرفق", selected_proj]
                                drive_link, success = save_to_cloud_storage(current_item["image"], current_item["name"], row_data)
                                if success:
                                    st.session_state.invoices_data.append({
                                        "serial_no": new_serial, "doc_type": current_type, "invoice_no": inv_no, 
                                        "invoice_date": clean_inv_date, "description": desc, "remark": remark, 
                                        "amount": amount, "vat": vat, "payment_method": pay_method, 
                                        "category": category, "delete": False, "project": selected_proj, 
                                        "filename": current_item["name"], "drive_link": drive_link
                                    })
                                    st.session_state.last_saved_serial = new_serial
                                    record_learned_sample(inv_no, desc, amount, category, pay_method, selected_proj)
                                    
                                    # توثيق القيد المعتمد في مستودع العينات
                                    approved_ds = load_approved_dataset()
                                    approved_ds.insert(0, {
                                        "timestamp": str(datetime.datetime.now()),
                                        "company_id": st.session_state.tuning_config.get("company_id", "alyoser_contracting"),
                                        "input_doc": current_item["name"],
                                        "ground_truth": {
                                            "invoice_no": inv_no,
                                            "invoice_date": clean_inv_date,
                                            "category": category,
                                            "description": desc,
                                            "payment_method": pay_method,
                                            "amount": amount,
                                            "vat": vat,
                                            "remark": remark
                                        }
                                    })
                                    save_approved_dataset(approved_ds)
                                    st.session_state.approved_dataset = approved_ds
                                    
                                    log_audit_event("INSERT", f"Saved {inv_no} amount {amount:,.2f} in {selected_proj}", current_user_data.get("name", "User"), current_user_data.get("name", "User"))
                                    st.toast("تم الحفظ وتوثيق القيد بنجاح!", icon="✅")
                                    time.sleep(0.5)
                                    st.session_state.pending_invoice = None
                                    st.session_state.queue_index += 1
                                    st.rerun()
                                else: st.warning("تحذير في المزامنة السحابية.")
                            except Exception as e: st.error(f"فشل الحفظ: {e}")

                with c_btn_merge:
                    target_serial = st.session_state.last_saved_serial
                    btn_merge_label = f"{t['merge_btn']} ({target_serial})" if target_serial else t["merge_btn"]
                    if st.button(btn_merge_label, use_container_width=True, disabled=(target_serial is None)):
                        with st.spinner(f"جاري الربط بالحركة {target_serial}..."):
                            save_to_cloud_storage(current_item["image"], f"ATTACHMENT_{current_item['name']}", [target_serial, "مرفق إضافي", "", "", "مرفق تابع", 0, 0, "", "", "مرفق", "False", "مرفق", selected_proj])
                            for inv in st.session_state.invoices_data:
                                if inv.get("serial_no") == target_serial:
                                    old_rmk = str(inv.get("remark", ""))
                                    inv["remark"] = (old_rmk + f" | [ملحق: {current_item['name']}]").strip(" |")
                                    break
                            log_audit_event("ATTACHMENT_MERGE", f"Merged {current_item['name']} with #{target_serial}", current_user_data.get("name", "User"), current_user_data.get("name", "User"))
                            st.toast(f"تم الإلحاق بالحركة #{target_serial}!", icon="📎")
                            time.sleep(0.5)
                            st.session_state.pending_invoice = None
                            st.session_state.queue_index += 1
                            st.rerun()

                with c_btn3:
                    if st.button(t["dismiss_btn"], use_container_width=True):
                        st.session_state.pending_invoice = None
                        st.session_state.queue_index += 1
                        st.rerun()
        else:
            st.success("تم الانتهاء من مراجعة وتدقيق كافة المستندات.")
            if st.button("🔄 دفعة جديدة"): 
                st.session_state.invoice_queue = []
                st.session_state.queue_index = 0
                st.session_state.last_saved_serial = None
                st.rerun()

    st.write("<br>", unsafe_allow_html=True)
    
    st.markdown(f"""
    <div style="background-color: var(--table-header-bg); color: white; padding: 12px 25px; border-radius: 8px; font-size: 19px; font-weight: 800; margin-bottom: 20px; border-right: 6px solid var(--brand-primary);">
        {t['filter_title']}
    </div>
    """, unsafe_allow_html=True)
    
    with st.container():
        f_col1, f_col2, f_col3 = st.columns(3)
        cat_choices = [t["all"], "مقاولين", "موردين", "مواد", "معدات", "عمالة", "نثريات", "تمويل عهدة (وارد)"]
        filter_cat = f_col1.selectbox(t["filter_cat"], cat_choices)
        pay_choices = [t["all"], "نقدي", "شيك", "تحويل بنكي", "تحويل إنستا باي", "غير مذكور"]
        filter_pay = f_col2.selectbox(t["filter_pay"], pay_choices)
        date_choices = [t["all"], t["today"], t["this_week"], t["this_month"], t["custom"]]
        filter_date = f_col3.selectbox(t["filter_date"], date_choices)
        custom_start, custom_end = None, None
        if filter_date == t["custom"]:
            d_col1, d_col2 = st.columns(2)
            custom_start = d_col1.date_input(t["from_date"])
            custom_end = d_col2.date_input(t["to_date"])

    filtered_list = []
    for idx, item in enumerate(active_project_invoices):
        item_copy = dict(item)
        item_copy["display_serial"] = idx + 1
        if filter_cat != t["all"] and item_copy.get("category") != filter_cat: continue
        if filter_pay != t["all"] and item_copy.get("payment_method") != filter_pay: continue
        if filter_date != t["all"]:
            try:
                inv_dt = pd.to_datetime(item_copy.get("invoice_date")).normalize()
                today = pd.Timestamp.now().normalize()
                if filter_date == t["today"] and inv_dt != today: continue
                elif filter_date == t["this_week"] and inv_dt < (today - pd.Timedelta(days=today.dayofweek)): continue
                elif filter_date == t["this_month"] and (inv_dt.year != today.year or inv_dt.month != today.month): continue
                elif filter_date == t["custom"] and custom_start and custom_end:
                    if not (custom_start <= inv_dt.date() <= custom_end): continue
            except Exception: pass
        filtered_list.append(item_copy)

    # ضبط الترقيم التسلسلي الحي المتتابع دائماً
    for idx_seq, item in enumerate(filtered_list, start=1):
        item["display_serial"] = idx_seq

    can_delete_records = (not is_ceo) or is_super_admin

    if st.session_state.confirm_delete_id and can_delete_records:
        target_inv = next((x for x in active_project_invoices if x.get("serial_no") == st.session_state.confirm_delete_id), None)
        desc_info = f"({target_inv['description']} - {target_inv['amount']:,.2f} {t['curr']})" if target_inv else ""
        st.markdown(f"""
        <div style='background-color: var(--kpi-outflow-bg); padding: 18px; border-radius: 10px; border: 2px solid #DC2626; margin-bottom: 20px;'>
            <h4 style='color: #DC2626; margin: 0 0 10px 0;'>🚨 تأكيد الحذف النهائي</h4>
            <p style='font-weight: bold; margin: 0;'>هل أنت متأكد تماماً من حذف الحركة {desc_info}؟</p>
        </div>
        """, unsafe_allow_html=True)
        conf_col1, conf_col2, _ = st.columns([1.5, 1.5, 4])
        with conf_col1:
            if st.button("نعم، احذف نهائياً 🗑️", type="primary", use_container_width=True):
                with st.spinner("جاري الحذف..."):
                    del_id = st.session_state.confirm_delete_id
                    if target_inv:
                        log_audit_event("DELETE", f"Deleted {target_inv.get('invoice_no')} in {selected_proj}", current_user_data.get("name", "User"), current_user_data.get("name", "User"))
                    for inv in st.session_state.invoices_data:
                        if inv.get("serial_no") == del_id: inv["delete"] = True
                    sync_delete_to_cloud(del_id, selected_proj, current_user_data.get("name", "User"))
                    st.session_state.confirm_delete_id = None
                    st.toast("تم الحذف بنجاح!", icon="✅")
                    time.sleep(0.5); st.rerun()
        with conf_col2:
            if st.button("إلغاء التراجع ❌", use_container_width=True):
                st.session_state.confirm_delete_id = None; st.rerun()

    if len(filtered_list) > 0:
        excel_buffer = io.BytesIO()
        excel_df = pd.DataFrame([{
            t["col_serial"]: item.get("display_serial"), 
            t["col_type"]: item.get("doc_type"), 
            t["col_doc_no"]: item.get("invoice_no"), 
            t["col_date"]: item.get("invoice_date"), 
            t["col_desc"]: item.get("description"), 
            t["col_amount"]: item.get("amount"), 
            t["col_vat"]: item.get("vat"), 
            t["col_pay"]: item.get("payment_method"), 
            t["col_cat"]: item.get("category"), 
            t["col_remark"]: item.get("remark")
        } for item in filtered_list])
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer: excel_df.to_excel(writer, index=False, sheet_name=selected_proj[:30])
        ex_col1, ex_col2 = st.columns([3, 1])
        with ex_col2: st.download_button(label=t["export_excel"], data=excel_buffer.getvalue(), file_name=f"records_{selected_proj}_{datetime.date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    # ضبط عروض الأعمدة لضمان ظهور زر الحذف بوضوح
    grid_cols = [0.8, 1.1, 1.1, 1.2, 2.2, 1.2, 0.9, 1.3, 1.1, 1.6, 0.9, 1.1]
    h0, h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11 = st.columns(grid_cols)
    h0.markdown(f"<div class='grid-header'>{t['col_serial']}</div>", unsafe_allow_html=True)
    h1.markdown(f"<div class='grid-header'>{t['col_type']}</div>", unsafe_allow_html=True)
    h2.markdown(f"<div class='grid-header'>{t['col_doc_no']}</div>", unsafe_allow_html=True)
    h3.markdown(f"<div class='grid-header'>{t['col_date']}</div>", unsafe_allow_html=True)
    h4.markdown(f"<div class='grid-header'>{t['col_desc']}</div>", unsafe_allow_html=True)
    h5.markdown(f"<div class='grid-header'>{t['col_amount']}</div>", unsafe_allow_html=True)
    h6.markdown(f"<div class='grid-header'>{t['col_vat']}</div>", unsafe_allow_html=True)
    h7.markdown(f"<div class='grid-header'>{t['col_pay']}</div>", unsafe_allow_html=True)
    h8.markdown(f"<div class='grid-header'>{t['col_cat']}</div>", unsafe_allow_html=True)
    h9.markdown(f"<div class='grid-header'>{t['col_remark']}</div>", unsafe_allow_html=True)
    h10.markdown(f"<div class='grid-header'>{t['col_del']}</div>", unsafe_allow_html=True)
    h11.markdown(f"<div class='grid-header'>{t['col_att']}</div>", unsafe_allow_html=True)

    if len(filtered_list) > 0:
        for idx, row in enumerate(filtered_list):
            is_in = row.get("doc_type") == "وارد"
            row_style = "grid-row-inbound" if is_in else "grid-row-outbound"
            type_icon = f"🟢 {t['inbound']}" if is_in else f"🔴 {t['outbound']}"
            c0, c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11 = st.columns(grid_cols)
            
            c0.markdown(f"<div class='{row_style}'>{row.get('display_serial', idx+1)}</div>", unsafe_allow_html=True)
            c1.markdown(f"<div class='{row_style}'>{type_icon}</div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='{row_style}'>{row.get('invoice_no', '')}</div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='{row_style}'>{row.get('invoice_date', '')}</div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='{row_style}'>{row.get('description', '')}</div>", unsafe_allow_html=True)
            c5.markdown(f"<div class='{row_style}'>{float(row.get('amount', 0)):,.2f}</div>", unsafe_allow_html=True)
            c6.markdown(f"<div class='{row_style}'>{float(row.get('vat', 0)):,.2f}</div>", unsafe_allow_html=True)
            c7.markdown(f"<div class='{row_style}'>{row.get('payment_method', '')}</div>", unsafe_allow_html=True)
            c8.markdown(f"<div class='{row_style}'>{row.get('category', '')}</div>", unsafe_allow_html=True)
            c9.markdown(f"<div class='{row_style}'>{row.get('remark', '')}</div>", unsafe_allow_html=True)
            with c10:
                if can_delete_records:
                    if st.button("🗑️", key=f"del_btn_{row.get('serial_no')}_{idx}", use_container_width=True, help="حذف الفاتورة"):
                        st.session_state.confirm_delete_id = row.get("serial_no")
                        st.rerun()
                else:
                    st.markdown(f"<div class='{row_style}'>🔒</div>", unsafe_allow_html=True)
            with c11:
                d_link = row.get('drive_link', '')
                if d_link and str(d_link).startswith("http"):
                    st.markdown(f"<div class='{row_style}'><a href='{d_link}' target='_blank' style='text-decoration:none; color:inherit;'>🔗 {t['view_att']}</a></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='{row_style}'>☁️</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='text-align: center; color: var(--text-muted); font-weight: bold; padding: 25px; background-color: var(--bg-card); border-radius: 8px; border: 1px solid var(--border-subtle); margin-top: 5px;'>{t['no_records']}</div>", unsafe_allow_html=True)

elif st.session_state.active_tab == "analytics":
    st.markdown(f"""
    <div class="print-only-header">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h1 style="margin: 0; color: #0284C7; font-size: 28px; font-weight: 900; letter-spacing: 0.5px;">Un-matt ConTech</h1>
                <h3 style="margin: 4px 0 0 0; color: #1E293B; font-size: 18px;">Executive Project Financial Dashboard & Performance Review</h3>
            </div>
            <div style="text-align: left;">
                <div style="font-size: 16px; font-weight: 800; color: #0F172A;">المشروع: <span style="color: #0284C7;">{selected_proj}</span></div>
                <div style="font-size: 13px; color: #64748B; margin-top: 4px;">تاريخ الإصدار: {datetime.date.today().strftime('%Y-%m-%d')}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_rep_t, col_rep_btn = st.columns([3, 1.2])
    with col_rep_t:
        st.markdown(f"<h2 style='color: var(--brand-primary); margin: 0;'>{t['analytics_title']} - <span style='color: var(--text-title);'>{selected_proj}</span></h2>", unsafe_allow_html=True)
    with col_rep_btn:
        st.markdown('<div class="no-print">', unsafe_allow_html=True)
        st.components.v1.html(f"""
        <button onclick="window.parent.print()" style="background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%); color:white; padding:10px 18px; border:none; border-radius:8px; cursor:pointer; font-weight:bold; font-size:13px; width:100%; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
            {t['print_report']}
        </button>
        """, height=45)
        st.markdown('</div>', unsafe_allow_html=True)

    st.write("<br>", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="kpi-container" style='display: flex; gap: 15px; margin-bottom: 20px;'>
        <div style='flex: 1; background: var(--kpi-inflow-bg); border-top: 4px solid var(--kpi-inflow-border); padding: 14px; border-radius: 8px; text-align: center;'><h4 style='color: var(--kpi-inflow-text); margin: 0; font-size: 15px;'>{t["metric_in"]}</h4><h2 style='color: var(--kpi-inflow-text); margin: 6px 0 0 0; font-size: 22px;'>{total_in:,.2f} {t["curr"]}</h2></div>
        <div style='flex: 1; background: var(--kpi-outflow-bg); border-top: 4px solid var(--kpi-outflow-border); padding: 14px; border-radius: 8px; text-align: center;'><h4 style='color: var(--kpi-outflow-text); margin: 0; font-size: 15px;'>{t["metric_out"]}</h4><h2 style='color: var(--kpi-outflow-text); margin: 6px 0 0 0; font-size: 22px;'>{total_out:,.2f} {t["curr"]}</h2></div>
        <div style='flex: 1; background: var(--kpi-balance-bg); border-top: 4px solid var(--kpi-balance-border); padding: 14px; border-radius: 8px; text-align: center;'><h4 style='color: var(--kpi-balance-text); margin: 0; font-size: 15px;'>{t["metric_bal"]}</h4><h2 style='color: var(--kpi-balance-text); margin: 6px 0 0 0; font-size: 22px;'>{balance:,.2f} {t["curr"]}</h2></div>
        <div style='flex: 1; background: var(--kpi-rate-bg); border-top: 4px solid var(--kpi-rate-border); padding: 14px; border-radius: 8px; text-align: center;'><h4 style='color: var(--kpi-rate-text); margin: 0; font-size: 15px;'>{t["metric_burn"]}</h4><h2 style='color: var(--kpi-rate-text); margin: 6px 0 0 0; font-size: 22px;'>{burn_rate:.1f}%</h2></div>
    </div>
    """, unsafe_allow_html=True)

    if total_out > 0 or total_in > 0:
        df_all = pd.DataFrame(active_project_invoices)
        df_out = df_all[df_all["doc_type"] == "منصرف"] if not df_all.empty else pd.DataFrame()
        
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.markdown(f"### {t['chart_cat']}")
            if not df_out.empty:
                cat_sum = df_out.groupby("category")["amount"].sum().reset_index()
                fig_pie = px.pie(cat_sum, values='amount', names='category', hole=0.45, color_discrete_sequence=px.colors.qualitative.Bold)
                fig_pie.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor='rgba(0,0,0,0)', font=dict(size=12, color="#1E293B" if st.session_state.system_theme == "Light" else "#F8FAFC"))
                st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': False})
        
        with col_chart2:
            st.markdown(f"### {t['chart_pay']}")
            if not df_out.empty:
                pay_sum = df_out.groupby("payment_method")["amount"].sum().reset_index()
                fig_bar = px.bar(pay_sum, x='payment_method', y='amount', color='payment_method', text='amount', color_discrete_sequence=px.colors.qualitative.Safe)
                fig_bar.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                fig_bar.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, font=dict(size=11, color="#1E293B" if st.session_state.system_theme == "Light" else "#F8FAFC"))
                st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 💡 التحليل المالي والتوصيات التنفيذية (Actionable Insights & EDA)")
        top_cat = "غير محدد"
        top_cat_amt = 0.0
        top_cat_pct = 0.0
        if not df_out.empty:
            cat_grouped = df_out.groupby("category")["amount"].sum().sort_values(ascending=False)
            if not cat_grouped.empty:
                top_cat = cat_grouped.index[0]
                top_cat_amt = cat_grouped.iloc[0]
                top_cat_pct = (top_cat_amt / total_out * 100) if total_out > 0 else 0

        cash_amt = df_out[df_out["payment_method"] == "نقدي"]["amount"].sum() if not df_out.empty else 0
        cash_pct = (cash_amt / total_out * 100) if total_out > 0 else 0

        ins_col1, ins_col2 = st.columns(2)
        with ins_col1:
            st.markdown(f"""
            <div class="insight-card">
                <div style="font-weight: 800; font-size: 14px; color: #0284C7; margin-bottom: 4px;">🎯 تركز السيولة وأكبر بنود التكلفة:</div>
                <div style="font-size: 12.5px; line-height: 1.5;">
                    يمثل بند <b>({top_cat})</b> أعلى معدل استنزاف نقدي في المشروع بإجمالي <b>{top_cat_amt:,.2f} {t['curr']}</b> وبنسبة <b>{top_cat_pct:.1f}%</b> من إجمالي المنصرف.<br>
                    <b>التوصية:</b> مراجعة أوامر التوريد ومطابقة المستخلصات الدورية للبند للتحقق من كفاءة التسعير والكميات.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with ins_col2:
            st.markdown(f"""
            <div class="insight-card">
                <div style="font-weight: 800; font-size: 14px; color: #0284C7; margin-bottom: 4px;">⚡ كفاءة السيولة ومخاطر السداد:</div>
                <div style="font-size: 12.5px; line-height: 1.5;">
                    تبلغ نسبة السداد النقدي المباشر <b>{cash_pct:.1f}%</b> بإجمالي <b>{cash_amt:,.2f} {t['curr']}</b>.<br>
                    <b>التوصية:</b> الاعتماد المستمر على الشيكات والتحويلات البنكية الموثقة لإحكام الرقابة وتأكيد التسليم المباشر للموردين والمقاولين.
                </div>
            </div>
            """, unsafe_allow_html=True)

    if is_company_admin or is_ceo or is_super_admin:
        st.markdown('<div class="audit-section no-print">', unsafe_allow_html=True)
        st.divider()
        st.markdown(f"### {t['audit_title']}")
        audit_logs = load_audit_log()
        if audit_logs:
            audit_df = pd.DataFrame(audit_logs)
            audit_df.rename(columns={"timestamp": "Timestamp", "user_name": "User", "action": "Action", "details": "Details"}, inplace=True)
            st.dataframe(audit_df[["Timestamp", "User", "Action", "Details"]], use_container_width=True, hide_index=True)
        else:
            st.info("No audit logs yet.")
        st.markdown('</div>', unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════
# ─── تبويب سياسات وضوابط النظام المحدث (In-App Tuning & Prompt Controls) ───
# ═════════════════════════════════════════════════════════════════════════
elif st.session_state.active_tab == "memory" and (is_company_admin or is_super_admin):
    if not st.session_state.memory_unlocked:
        st.warning("🔒 التحقق الإداري مطلوب للدخول إلى مركز التحكم بالسياسات.")
        passcode = st.text_input("رمز الأمان الإداري:", type="password")
        if st.button("تأكيد الصلاحية 🗝️", type="primary"):
            if passcode == "6114": 
                st.session_state.memory_unlocked = True
                st.rerun()
            else: st.error("رمز الأمان غير صحيح!")
    else:
        st.markdown(f"""
        <div style="background-color: var(--table-header-bg); color: white; padding: 12px 25px; border-radius: 8px; font-size: 20px; font-weight: bold; margin-bottom: 20px; border-right: 6px solid var(--brand-primary);">
            {t['tab_memory']}
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔒 قفل الصلاحية", type="secondary"): 
            st.session_state.memory_unlocked = False
            st.rerun()
        
        t_tab1, t_tab2, t_tab3 = st.tabs([
            "1️⃣ ضوابط التوجيه والقيد", 
            "2️⃣ مستودع القيود والعينات المعتمدة", 
            "3️⃣ ضبط وتحديث نماذج الاستخراج"
        ])
        
        curr_cfg = st.session_state.tuning_config
        
        # ─── القسم الأول: ضوابط التوجيه المالي والقيد ───
        with t_tab1:
            st.subheader("🏢 تخصيص سياسات التوجيه المحاسبي للمشروع")
            p_col1, p_col2 = st.columns(2)
            c_name_val = p_col1.text_input("اسم الشركة / المنشأة المعتمدة:", value=curr_cfg.get("company_name", "شركة اليسر للمقاولات"))
            c_id_val = p_col2.text_input("معرّف الشركة (Company ID):", value=curr_cfg.get("company_id", "alyoser_contracting"))
            
            st.markdown("**التوجيه المحاسبي الأساسي (System Instruction):**")
            sys_inst_val = st.text_area(
                "نص التوجيه المالي المعتمد في عمليات التدقيق:",
                value=curr_cfg.get("system_instruction", ""),
                height=120
            )
            
            st.markdown("**قاموس المصطلحات والموردين المعتمد:**")
            new_dict = st.text_area("قواعد التصنيف وأسماء الموردين المعتمدة:", value=st.session_state.system_dictionary, height=150)
            
            st.markdown("**قالب الاستخراج الإلزامي (Mandatory JSON Schema):**")
            schema_json_str = st.text_area(
                "هيكل مخرجات الحقول:",
                value=json.dumps(curr_cfg.get("json_schema", {}), ensure_ascii=False, indent=2),
                height=160
            )
            
            if st.button("💾 حفظ السياسات وضوابط الاستخراج", type="primary"):
                try:
                    parsed_sch = json.loads(schema_json_str)
                    curr_cfg["company_name"] = c_name_val
                    curr_cfg["company_id"] = c_id_val
                    curr_cfg["system_instruction"] = sys_inst_val
                    curr_cfg["json_schema"] = parsed_sch
                    save_tuning_config(curr_cfg)
                    st.session_state.tuning_config = curr_cfg
                    
                    st.session_state.system_dictionary = new_dict
                    local_ok, cloud_ok = save_system_dictionary(new_dict)
                    
                    st.success("✅ تم حفظ السياسات وضوابط القاموس بنجاح!")
                except Exception as ex:
                    st.error(f"خطأ في صيغة الـ JSON: {ex}")

        # ─── القسم الثاني: مستودع القيود والعينات المعتمدة ───
        with t_tab2:
            st.subheader("🔄 مستودع القيود والعينات المعتمدة (Ground Truth Dataset)")
            approved_ds = load_approved_dataset()
            ds_count = len(approved_ds)
            
            ready_color = "#10B981" if ds_count >= 10 else "#F59E0B"
            st.markdown(f"""
            <div style='display:flex; justify-content:space-between; align-items:center; background:var(--bg-card); padding:15px; border-radius:8px; border:1px solid var(--border-subtle); margin-bottom:15px;'>
                <div>
                    <h4 style='margin:0; color:var(--text-title);'>إجمالي القيود المعتمدة: <b>{ds_count}</b></h4>
                    <small style='color:var(--text-muted);'>الحد الموصى به لضبط دقة التعرف التلقائي هو 10 عينات موثقة بكامل بياناتها.</small>
                </div>
                <div style='font-size:22px; font-weight:900; color:{ready_color};'>
                    {'اكتمال النصاب الموصى به ✅' if ds_count >= 10 else f'متبقي {10 - ds_count} عينات ⏳'}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if approved_ds:
                preview_list = []
                for idx, sample in enumerate(approved_ds):
                    gt = sample.get("ground_truth", {})
                    preview_list.append({
                        "م": idx + 1,
                        "المستند": sample.get("input_doc", ""),
                        "تاريخ الفاتورة": gt.get("invoice_date", ""),
                        "رقم المستند": gt.get("invoice_no", ""),
                        "التصنيف": gt.get("category", ""),
                        "البيان": gt.get("description", ""),
                        "طريقة الدفع": gt.get("payment_method", ""),
                        "المبلغ": f"{float(gt.get('amount', 0.0)):,.2f} ج.م",
                        "الضريبة": f"{float(gt.get('vat', 0.0)):,.2f} ج.م",
                        "الملاحظات": gt.get("remark", "")
                    })
                st.dataframe(pd.DataFrame(preview_list), use_container_width=True)
                
                col_c1, col_c2 = st.columns([2, 1])
                if col_c2.button("🗑️ مسح مستودع العينات المعتمدة", use_container_width=True):
                    save_approved_dataset([])
                    st.session_state.approved_dataset = []
                    st.session_state.manual_training_data = []
                    save_training_db([])
                    st.toast("تم مسح مستودع العينات!", icon="🧹")
                    time.sleep(0.5); st.rerun()
            else:
                st.info("لم يتم توثيق قيود بعد. عند اعتماد وحفظ أي فاتورة جديدة سيتم تسجيلها هنا تلقائياً لضبط دقة النظام.")

        # ─── القسم الثالث: محرك ضبط وتحديث نماذج الاستخراج ───
        with t_tab3:
            st.subheader("⚡ محرك ضبط نماذج الاستخراج (In-App Tuning Engine)")
            
            col_t1, col_t2 = st.columns(2)
            active_model_in = col_t1.text_input("معرّف النموذج المخصص (Custom Model ID):", value=curr_cfg.get("active_tuned_model", ""), placeholder="tunedModels/alyoser-invoice-v1")
            use_tuned_chk = col_t2.checkbox("تفعيل توجيه القراءات تلقائياً للنموذج المخصص", value=curr_cfg.get("use_tuned_model", False))
            
            if st.button("حفظ إعدادات توجيه النموذج المخصص 💾"):
                curr_cfg["active_tuned_model"] = active_model_in.strip()
                curr_cfg["use_tuned_model"] = use_tuned_chk
                save_tuning_config(curr_cfg)
                st.session_state.tuning_config = curr_cfg
                st.success("تم تحديث إعدادات التوجيه بنجاح!")
            
            st.divider()
            st.markdown("#### 🚀 إنشاء وحفظ حزمة ضبط وتدريب جديدة:")
            t_model_name = st.text_input("اسم إصدار حزمة الضبط:", value=f"alyoser-model-{datetime.date.today().strftime('%Y%m%d')}")
            
            if st.button("🚀 معالجة وتجهيز حزمة الضبط", type="primary"):
                approved_ds = load_approved_dataset()
                if not api_key:
                    st.error("⚠️ مفتاح الربط غير متصل.")
                elif len(approved_ds) == 0:
                    st.warning("⚠️ لا توجد عينات معتمدة في المستودع حتى الآن.")
                else:
                    with st.spinner("جاري تحويل البيانات وتجهيز ملفات الحزمة بصيغة JSONL..."):
                        training_dataset = []
                        for sample in approved_ds:
                            training_dataset.append({
                                "text_input": f"وثيقة فاتورة: {sample.get('input_doc')}",
                                "output": json.dumps(sample.get("ground_truth"), ensure_ascii=False)
                            })
                        
                        jsonl_path = os.path.join(BASE_DIR, "training_data.jsonl")
                        with open(jsonl_path, "w", encoding="utf-8") as jf:
                            for item in training_dataset:
                                jf.write(json.dumps(item, ensure_ascii=False) + "\n")
                        
                        st.info(f"📁 تم تجهيز ملف البيانات ({len(training_dataset)} عينة) بنجاح بصيغة JSONL.")
                        
                        new_tuned_id = f"tunedModels/{t_model_name.strip()}"
                        curr_cfg["active_tuned_model"] = new_tuned_id
                        curr_cfg["use_tuned_model"] = True
                        save_tuning_config(curr_cfg)
                        st.session_state.tuning_config = curr_cfg
                        
                        log_audit_event("TUNING_CONFIG", f"Configured model {new_tuned_id} with {len(training_dataset)} samples", current_user_data.get('name', 'Admin'), current_user_data.get('name', 'Admin'))
                        st.success(f"🎉 تم تجهيز واعتماد حزمة النموذج: `{new_tuned_id}` بنجاح!")
                        time.sleep(1)
                        st.rerun()

# ─── الفوتر ───
st.markdown("""
<div class="footer-container no-print">
    <span class="brand-footer-text">Un-matt ConTech 2026</span>
</div>
""", unsafe_allow_html=True)