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
import threading
import string
import secrets

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
LOCAL_INVOICES_FILE = os.path.join(BASE_DIR, "invoices_local.json")
PENDING_SYNC_DIR = os.path.join(BASE_DIR, "pending_cloud_sync")

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

DEFAULT_DICT = ""
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

def ensure_hr_admin_data_files():
    required_schema = {
        "invoice_no": "رقم المستند أو إيصال الصرف المطبوع/المكتوب",
        "invoice_date": "التاريخ بصيغة YYYY-MM-DD",
        "amount": "المبلغ الإجمالي المالي كـ float (مطابقاً تماماً للتفقيط المكتوب بالحروف)",
        "vat": 0.0,
        "description": "البيان أو اسم المستفيد المكتوب بوضوح",
        "category": "اختر التصنيف الأنسب من: مقاولين / موردين / مواد / معدات / عمالة / نثريات",
        "payment_method": "حدد بدقة الخيار غير المشطوب عليه من (نقداً / شيك / تحويل)",
        "remark": "أي ملاحظات إضافية مثل رقم الشيك أو البنك"
    }
    cfg = load_tuning_config()
    needs_save = not os.path.exists(TUNING_CONFIG_FILE)
    defaults = {
        "company_id": "alyoser_contracting",
        "company_name": "شركة اليسر للمقاولات",
        "system_instruction": "أنت مراجع مالي أول ومحاسب معتمد في شركة اليسر للمقاولات. مهمتك استخراج ومطابقة بيانات فواتير ومصروفات المشاريع بدقة متناهية ومطابقة التفقيط بالأرقام بصيغة JSON.",
        "active_tuned_model": "",
        "use_tuned_model": False,
        "json_schema": required_schema
    }
    for key, value in defaults.items():
        if key not in cfg:
            cfg[key] = value
            needs_save = True
    if not isinstance(cfg.get("json_schema"), dict):
        cfg["json_schema"] = required_schema
        needs_save = True
    else:
        for sk, sv in required_schema.items():
            if sk not in cfg["json_schema"]:
                cfg["json_schema"][sk] = sv
                needs_save = True
    if needs_save:
        save_tuning_config(cfg)
    if not os.path.exists(APPROVED_DATASET_FILE):
        save_approved_dataset([])
    else:
        current_ds = load_approved_dataset()
        if not isinstance(current_ds, list):
            save_approved_dataset([])

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
    if os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    try:
        res = requests.get(f"{CLOUD_WEB_APP_URL}?action=get_dictionary", timeout=8)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == "success" and data.get("dictionary"):
                cloud_dict = data.get("dictionary").strip()
                with open(DICT_FILE, "w", encoding="utf-8") as f: f.write(cloud_dict)
                return cloud_dict
    except Exception:
        pass
    return DEFAULT_DICT

def extract_party_name_from_description(description: str) -> str:
    text = str(description or "").strip()
    if not text:
        return ""
    for sep in ["وذلك عن", "وذلك مقابل", " - ", " – ", " — "]:
        if sep in text:
            text = text.split(sep)[0].strip()
            break
    text = re.sub(r"^(يصرف إلى السيد\/السادة|يصرف الي السيد\/السادة|يصرف إلى|يصرف الي|السيد\/السادة|السادة|السيد)\s*", "", text, flags=re.IGNORECASE).strip(" :-،,.")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]

def upsert_smart_dictionary(description, category):
    party_name = extract_party_name_from_description(description)
    category = str(category or "").strip()
    if len(party_name) < 2 or not category:
        return False
    current = str(st.session_state.get("system_dictionary") or "").strip()
    if not current:
        current = load_system_dictionary() or ""
        current = str(current).strip()
    lines = [ln.rstrip() for ln in current.splitlines() if ln.strip()]
    new_line = f"- المورد: '{party_name}' | التصنيف المعتمد: '{category}'"
    name_pat = re.compile(re.escape(party_name), re.IGNORECASE)
    updated = False
    out_lines = []
    for ln in lines:
        is_same_party = bool(name_pat.search(ln)) and ("تصنيف" in ln or "المورد" in ln or "يصنف" in ln)
        if is_same_party:
            if not updated:
                out_lines.append(new_line)
                updated = True
            continue
        out_lines.append(ln)
    if not updated:
        out_lines.append(new_line)
    new_text = "\n".join(out_lines).strip()
    if new_text == current:
        st.session_state.system_dictionary = new_text
        return True
    local_ok, _cloud_ok = save_system_dictionary(new_text)
    if local_ok:
        st.session_state.system_dictionary = new_text
    return local_ok

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

def save_to_cloud_storage(image, filename, row_data, timeout=12):
    img_str = optimize_image_for_upload(image)
    payload = {"action": "upload_invoice", "fileName": filename, "mimeType": "image/jpeg", "fileData": img_str, "rowValues": row_data}
    try:
        response = requests.post(CLOUD_WEB_APP_URL, json=payload, timeout=timeout)
        res_json = response.json()
        if res_json.get("status") == "success": return res_json.get("url", ""), True
        return "", False
    except Exception:
        return "", False

def load_local_invoices():
    if not os.path.exists(LOCAL_INVOICES_FILE):
        return []
    try:
        with open(LOCAL_INVOICES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def save_local_invoices(records):
    try:
        with open(LOCAL_INVOICES_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        return True
    except Exception:
        return False

def invoice_match_key(r):
    try:
        amt = f"{float(r.get('amount') or 0):.2f}"
    except Exception:
        amt = "0.00"
    return (
        str(r.get("project", "")).strip(),
        str(r.get("serial_no", "")).strip(),
        str(r.get("invoice_no", "")).strip(),
        amt,
        str(r.get("invoice_date", "")).strip(),
    )

def merge_invoice_lists(cloud_list, local_list):
    merged = {}
    order = []
    def add(rec):
        item = dict(rec)
        k = invoice_match_key(item)
        if k not in merged:
            merged[k] = item
            order.append(k)
            return
        base = merged[k]
        if item.get("cloud_synced") is False and base.get("cloud_synced") is not False:
            keep_link = base.get("drive_link")
            merged[k] = item
            if keep_link and not item.get("drive_link"):
                merged[k]["drive_link"] = keep_link
                merged[k]["cloud_synced"] = True
        elif item.get("drive_link") and not base.get("drive_link"):
            base["drive_link"] = item.get("drive_link")
            base["cloud_synced"] = True
    for r in cloud_list or []:
        add(r)
    for r in local_list or []:
        add(r)
    return [merged[k] for k in order]

def load_invoices_local_first():
    return load_local_invoices()

def record_to_cloud_row(rec):
    type_icon = "🟢 وارد" if rec.get("doc_type") == "وارد" else "🔴 منصرف"
    return [
        rec.get("serial_no"), type_icon, rec.get("invoice_no"), rec.get("invoice_date"),
        rec.get("description"), rec.get("amount"), rec.get("vat"), rec.get("payment_method"),
        rec.get("category"), rec.get("remark"), "False", "مرفق", rec.get("project")
    ]

def save_pending_sync_image(image, project, serial_no):
    try:
        os.makedirs(PENDING_SYNC_DIR, exist_ok=True)
        safe_proj = re.sub(r"[^\w\-]+", "_", str(project))[:40]
        path = os.path.join(PENDING_SYNC_DIR, f"{safe_proj}_{serial_no}.jpg")
        img = image.copy()
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(path, format="JPEG", quality=85)
        return path
    except Exception:
        return ""

def apply_pending_sync_results():
    if "invoices_data" not in st.session_state or not os.path.isdir(PENDING_SYNC_DIR):
        return
    changed = False
    for name in list(os.listdir(PENDING_SYNC_DIR)):
        if not name.startswith("syncres_") or not name.endswith(".json"):
            continue
        path = os.path.join(PENDING_SYNC_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                res = json.load(f)
            if res.get("ok"):
                for inv in st.session_state.invoices_data:
                    if str(inv.get("serial_no")) == str(res.get("serial_no")) and str(inv.get("project")) == str(res.get("project")):
                        inv["drive_link"] = res.get("url") or inv.get("drive_link", "")
                        inv["cloud_synced"] = True
                        img_path = inv.pop("pending_image_path", None)
                        if img_path and os.path.exists(img_path):
                            try: os.remove(img_path)
                            except Exception: pass
                        changed = True
                        break
            try: os.remove(path)
            except Exception: pass
        except Exception:
            continue
    if changed:
        save_local_invoices(st.session_state.invoices_data)

def cloud_sync_invoice_background(image, filename, row_data, project, serial_no):
    url, ok = "", False
    try:
        url, ok = save_to_cloud_storage(image, filename, row_data, timeout=20)
    except Exception:
        url, ok = "", False
    try:
        os.makedirs(PENDING_SYNC_DIR, exist_ok=True)
        safe_proj = re.sub(r"[^\w\-]+", "_", str(project))[:30]
        result_path = os.path.join(PENDING_SYNC_DIR, f"syncres_{serial_no}_{safe_proj}.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({"ok": bool(ok), "url": url or "", "serial_no": serial_no, "project": project}, f, ensure_ascii=False)
    except Exception:
        pass

def retry_pending_cloud_sync():
    if "invoices_data" not in st.session_state:
        return
    for rec in st.session_state.invoices_data:
        if rec.get("cloud_synced") is not False:
            continue
        path = rec.get("pending_image_path")
        if not path or not os.path.exists(path):
            continue
        try:
            img = Image.open(path)
            url, ok = save_to_cloud_storage(img, rec.get("filename") or "invoice.jpg", record_to_cloud_row(rec), timeout=20)
            if ok:
                rec["drive_link"] = url
                rec["cloud_synced"] = True
                rec.pop("pending_image_path", None)
                try: os.remove(path)
                except Exception: pass
        except Exception:
            continue
    save_local_invoices(st.session_state.invoices_data)

def clean_remark_for_display(remark):
    text = str(remark or "")
    text = re.sub(r"\s*\|\s*\[ملحق:[^\]]*\]", "", text)
    text = re.sub(r"\[ملحق:[^\]]*\]", "", text)
    text = re.sub(r"(?i)\s*\|\s*[^\s|]+\.(jpg|jpeg|png|pdf|webp)(\s*-\s*p\d+)?", "", text)
    return text.strip(" |")

def collect_row_attachments(row):
    links = []
    main = str(row.get("drive_link") or "").strip()
    if main.startswith("http"):
        links.append(main)
    extra = row.get("attachment_links") or row.get("drive_links") or []
    if isinstance(extra, str):
        extra = [extra]
    for url in extra:
        u = str(url or "").strip()
        if u.startswith("http") and u not in links:
            links.append(u)
    extra_count = len(re.findall(r"\[ملحق:", str(row.get("remark") or "")))
    return links, extra_count

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

def optimize_image_for_upload(image, max_size=(1800, 1800), quality=88):
    img = image.copy()
    if img.mode != 'RGB': img = img.convert('RGB')
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def analyze_invoice_with_gemini(image, prompt_text, api_key, current_project=""):
    img_str = optimize_image_for_upload(image, max_size=(1800, 1800), quality=88)
    clean_key = str(api_key).strip().replace('"', '').replace("'", '').split("\n")[0].split(",")[0].strip()
    
    t_cfg = load_tuning_config()
    if os.path.exists(TUNING_CONFIG_FILE):
        try:
            with open(TUNING_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved_cfg = json.load(f)
                if isinstance(saved_cfg, dict):
                    t_cfg.update(saved_cfg)
        except Exception:
            pass
    required_schema = {
        "invoice_no": "رقم المستند أو إيصال الصرف المطبوع/المكتوب",
        "invoice_date": "التاريخ بصيغة YYYY-MM-DD",
        "amount": "المبلغ الإجمالي المالي كـ float (مطابقاً تماماً للتفقيط المكتوب بالحروف)",
        "vat": 0.0,
        "description": "البيان أو اسم المستفيد المكتوب بوضوح",
        "category": "اختر التصنيف الأنسب من: مقاولين / موردين / مواد / معدات / عمالة / نثريات",
        "payment_method": "حدد بدقة الخيار غير المشطوب عليه من (نقداً / شيك / تحويل)",
        "remark": "أي ملاحظات إضافية مثل رقم الشيك أو البنك"
    }
    if t_cfg.get("json_schema") != required_schema:
        t_cfg["json_schema"] = required_schema
        save_tuning_config(t_cfg)
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
    learned_context = "\n\nأسماء الموردين وتصنيفاتهم المعتمدة فقط. يُمنع ذكر أو استخدام أي أرقام فواتير أو مبالغ أو تواريخ سابقة:\n"
    dict_text = str(st.session_state.get("system_dictionary", "") or "").strip()
    if not dict_text and os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                dict_text = f.read().strip()
        except Exception:
            dict_text = ""
    if dict_text:
        learned_context += f"{dict_text}\n"
    seen_suppliers = set()
    if training_db:
        for item in training_db:
            cd = item.get("correct_data", {})
            supplier = str(cd.get("description", "")).strip()
            category = str(cd.get("category", "")).strip()
            if not supplier:
                continue
            key = (supplier, category)
            if key in seen_suppliers:
                continue
            seen_suppliers.add(key)
            learned_context += f"- المورد: '{supplier}' | التصنيف المعتمد: '{category}'\n"

    sys_inst = t_cfg.get("system_instruction", "")
    schema_json = json.dumps(t_cfg.get("json_schema", required_schema), ensure_ascii=False, indent=2)
    active_rules = f"""
{sys_inst}
{learned_context}
قواعد قراءة نموذج إيصال صرف (نقداً / شيك) والمستند الحالي فقط:
1. [رقم المستند]: اقرأ جدول الفاتورة أو إيصال الصرف الحالي واستخرج رقم المستند الفعلي المطبوع أو المكتوب بخط اليد. لا تنقل أي رقم فاتورة من حركات سابقة.
2. [التاريخ]: اقرأ التاريخ المكتوب بخط اليد في خانة التاريخ فقط، وأعده بصيغة YYYY-MM-DD بدقة من خانة التاريخ الفعلية للمستند وليس من أرقام الحسابات أو أرقام الشيكات.
3. [المبلغ والتفقيط]: اقرأ المبلغ الرقمي من المستند الحالي وطابقه بدقة تامة مع النص المكتوب بالحروف (مثال للتوضيح فقط: مائتان وخمسون ألف جنيه = 250000). اعتمد القيمة المطابقة كـ float في خانة amount بعد تحويل الأرقام الهندية/العربية (٦ = 6، ٢ = 2). لا تستخدم مبالغ سابقة.
4. [البيان / الوصف]: اجمع نص خانة "يصرف إلى السيد / السادة" مع خانة "وذلك عن" المكتوبتين بخط اليد نصاً كما هما داخل description. يمنع منعاً باتاً استبدالهما بأسماء من القاموس، أو ترك description فارغاً، أو تخمينه من القاموس.
5. [الملاحظات]: استخرج أي بيانات شيكات (رقم الشيك، اسم البنك) أو تفاصيل إضافية وضعها في خانة remark.
6. [طريقة الدفع]: إذا كان هناك رقم شيك مدون أو محدد "شيك"، تكون طريقة الدفع "شيك"، وإلا فتكون "نقدي".
7. إلزام بملء جميع الحقول التالية وعدم ترك أي حقل فارغاً، وخصوصاً description:
{schema_json}
8. النتيجة المطلوبة كائن JSON مفرد ومباشر {{ }} فقط.
تحذير: ممنوع اختلاق أو تخمين بيانات من مستندات سابقة. اعتمد حصرياً على النص والأرقام الظاهرة في صورة المستند الحالية.
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
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and saved:
                    saved.pop("admin@alyosr.com", None)
                    saved.pop("acc@alyosr.com", None)
                    return saved
        except Exception:
            pass
    return {
        "halawa1981@gmail.com": {
            "name": "م/ محمد حلاوة (System Owner)",
            "password_hash": hash_password("01230030480Ab"),
            "role": "Admin",
            "allowed_projects": "All",
            "must_change_password": False
        }
    }

def save_users_db(users_data):
    try:
        users_data.pop("admin@alyosr.com", None)
        users_data.pop("acc@alyosr.com", None)
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_data, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        return True
    except Exception: return False

def ask_project_assistant(user_query, project_name, invoices_list, rules_dict, api_key):
    clean_key = str(api_key).strip().replace('"', '').replace("'", '').split("\n")[0].split(",")[0].strip()
    project_records = []
    for inv in invoices_list or []:
        is_del = str(inv.get("delete", False)).strip().lower() in ["true", "1", "نعم"]
        if is_del:
            continue
        if str(inv.get("project", "")).strip() != str(project_name).strip():
            continue
        project_records.append(inv)

    context_lines = []
    for inv in project_records:
        context_lines.append(
            f"- السريال: {inv.get('serial_no', '')} | رقم المستند: {inv.get('invoice_no', '')} | "
            f"التاريخ: {inv.get('invoice_date', '')} | البيان: {inv.get('description', '')} | "
            f"المبلغ: {inv.get('amount', 0)} | طريقة الدفع: {inv.get('payment_method', '')} | "
            f"التصنيف: {inv.get('category', '')} | الملاحظات: {inv.get('remark', '')}"
        )
    records_text = "\n".join(context_lines) if context_lines else "لا توجد حركات مسجلة لهذا المشروع."
    if isinstance(rules_dict, dict):
        rules_text = json.dumps(rules_dict, ensure_ascii=False)
    else:
        rules_text = str(rules_dict or "").strip()

    system_prompt = (
        f"أنت المساعد المالي لمشروع {project_name}. أجب بدقة واختصار حصرياً ومن واقع السجلات المرفقة أدناه فقط. "
        f"اذكر أرقام المستندات والمبالغ دائماً. إذا لم تجد المعلومة في السجلات، أجب بصراحة أنها غير مدونة ولا تفترض أي مبالغ."
    )
    user_prompt = (
        f"السجلات المرفقة:\n{records_text}\n\n"
        f"قواعد المشروع (للاستئناس دون اختلاق مبالغ):\n{rules_text}\n\n"
        f"سؤال المستخدم:\n{user_query}"
    )

    candidate_models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
    ]
    headers = {'Content-Type': 'application/json'}
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }

    last_error_details = []
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={clean_key}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=45)
            if response.status_code == 200:
                res_json = response.json()
                candidates = res_json.get('candidates', [])
                if not candidates:
                    continue
                return candidates[0]['content']['parts'][0]['text']
            last_error_details.append(f"[{model_name}: كود {response.status_code}]")
            if response.status_code not in [404, 429, 503]:
                break
        except Exception as e:
            last_error_details.append(f"[{model_name}: استثناء {str(e)[:50]}]")
            time.sleep(0.5)

    err_summary = " | ".join(last_error_details) if last_error_details else "لا يوجد استجابة من الخادم"
    raise Exception(f"تعذر الحصول على رد المساعد: {err_summary}")

def render_portal_gateway():
    st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none !important; }
    .portal-hero {
        background: linear-gradient(135deg, #0F2545 0%, #0C4A6E 55%, #0369A1 100%);
        border-radius: 18px; padding: 28px 32px; margin-bottom: 22px; color: #FFFFFF;
        border: 1px solid rgba(56,189,248,0.35); box-shadow: 0 12px 32px rgba(15,37,69,0.25);
    }
    .portal-kicker { color: #7DD3FC; font-size: 12px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 8px; }
    .portal-hero h1 { margin: 0 0 8px 0; font-size: 30px; font-weight: 800; color: #FFFFFF; }
    .portal-hero p { margin: 0; color: #DBEAFE; font-size: 15px; line-height: 1.6; }
    .portal-card {
        background: var(--bg-card, #FFFFFF); border: 1px solid var(--border-subtle, #E2E8F0);
        border-radius: 14px; padding: 18px 16px 14px 16px; min-height: 210px;
        box-shadow: 0 8px 18px rgba(15,37,69,0.06);
    }
    .portal-card.active { border-top: 4px solid #10B981; }
    .portal-card.soon { border-top: 4px solid #94A3B8; opacity: 0.92; }
    .portal-card h3 { margin: 8px 0 6px 0; font-size: 16px; color: var(--text-title, #0F172A); }
    .portal-card p { margin: 0; font-size: 12.5px; color: var(--text-muted, #64748B); line-height: 1.55; min-height: 58px; }
    .portal-badge-on { display: inline-block; background: #ECFDF5; color: #047857; border: 1px solid #6EE7B7; border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 800; }
    .portal-badge-off { display: inline-block; background: #F1F5F9; color: #64748B; border: 1px solid #CBD5E1; border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 800; }
    .portal-icon { font-size: 28px; }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="portal-hero">
        <div class="portal-kicker">Un-matt ConTech • Supply Chain Platform</div>
        <h1>بوابة سلاسل الإمداد المؤسسية</h1>
        <p>منصة موحدة لإدارة الفواتير الذكية، المستودعات، المشتريات، المواد، وذكاء سلاسل الإمداد — اختر الوحدة المطلوبة للدخول.</p>
    </div>
    """, unsafe_allow_html=True)

    cards = [
        ("active", "🧾", "نظام الفواتير الذكي", "Invoice Smart System", "استخراج وتدقيق الفواتير وإيصالات الصرف مع المطابقة المالية والرقابة على العهدة."),
        ("soon", "📦", "إدارة المستودعات الذكية", "Smart Warehouse", "متابعة الأرصدة وحركات الصرف والاستلام داخل مستودعات المشروع."),
        ("soon", "🛒", "المشتريات الذكية", "Smart Procurement", "إدارة أوامر الشراء والموردين ودورة الاعتماد قبل الصرف."),
        ("soon", "🧱", "نظام المواد الذكي", "Smart Materials", "تتبع أصناف المواد وربطها بالمقايسة والتكاليف الفعلية."),
        ("soon", "📈", "لوحة ذكاء سلاسل الإمداد", "Supply Chain Intelligence", "مؤشرات تنفيذية للتنبيه المبكر والانحرافات وقرارات الإمداد."),
    ]
    cols = st.columns(5)
    for col, (kind, icon, ar_title, en_title, desc) in zip(cols, cards):
        badge = '<span class="portal-badge-on">مفعل</span>' if kind == "active" else '<span class="portal-badge-off">قريباً (Coming Soon)</span>'
        with col:
            st.markdown(f"""
            <div class="portal-card {kind}">
                <div class="portal-icon">{icon}</div>
                {badge}
                <h3>{ar_title}</h3>
                <p><b>{en_title}</b><br>{desc}</p>
            </div>
            """, unsafe_allow_html=True)
            if kind == "active":
                if st.button("دخول النظام (مفعل)", type="primary", use_container_width=True, key="enter_smart_invoice"):
                    st.session_state.active_portal_module = "smart_invoice"
                    st.rerun()
            else:
                st.button("قريباً (Coming Soon)", disabled=True, use_container_width=True, key=f"soon_{en_title}")

# ─── التهيئة الآمنة لجميع متغيرات الجلسة ───
ensure_hr_admin_data_files()
if "system_lang" not in st.session_state: st.session_state.system_lang = "العربية"
if "system_theme" not in st.session_state: st.session_state.system_theme = "Light"
st.session_state.users_db = load_users_db()
if "projects_list" not in st.session_state: st.session_state.projects_list = load_projects_list()
st.session_state.invoices_data = load_invoices_local_first()
st.session_state.manual_training_data = load_training_db()
st.session_state.approved_dataset = load_approved_dataset()
if "tuning_config" not in st.session_state: st.session_state.tuning_config = load_tuning_config()
st.session_state.system_dictionary = load_system_dictionary()
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
if "chat_messages" not in st.session_state: st.session_state.chat_messages = []
if "active_portal_module" not in st.session_state:
    st.session_state.active_portal_module = "custody"
if "show_change_pwd_modal" not in st.session_state: st.session_state.show_change_pwd_modal = False
if "logged_in" not in st.session_state: st.session_state.logged_in = (st.query_params.get("session_auth") == "auth_valid_session")
if "current_user" not in st.session_state: st.session_state.current_user = None
if "upload_doc_kind" not in st.session_state: st.session_state.upload_doc_kind = "out"

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
        <h3 style="color: #38BDF8; margin-top: 0;">🔐 تحديث كلمة المرور</h3>
        <p style="color: var(--text-muted); font-size: 14px;">يرجى تعيين كلمة مرور قوية جديدة لحسابك للمتابعة إلى لوحة التحكم.</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.container():
        c_p1, c_p2, c_p3 = st.columns([1, 2, 1])
        with c_p2:
            new_p1 = st.text_input("كلمة المرور الجديدة:", type="password", key="new_p1_in")
            new_p2 = st.text_input("تأكيد كلمة المرور:", type="password", key="new_p2_in")
            
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
can_access_system_policies = str(user_role).strip() in ("Admin", "Super Admin")
if (not can_access_system_policies) and st.session_state.get("active_tab") == "memory":
    st.session_state.active_tab = "records"
    st.session_state.memory_unlocked = False

is_rtl = (st.session_state.system_lang == "العربية")
dir_attr = "rtl" if is_rtl else "ltr"

# ─── تهيئة التنسيق والألوان ───
if st.session_state.system_theme == "Dark":
    st.markdown(f"""
    <style>
    :root {{
        --bg-main: #0B1120; --bg-card: #1E293B; --bg-input: #0F172A; --border-subtle: #334155; --border-strong: #475569;
        --text-title: #F8FAFC; --text-body: #CBD5E1; --text-muted: #94A3B8; --brand-primary: #E8B423; --brand-navy: #2C3E50; --brand-gold: #E8B423;
        --kpi-inflow-bg: rgba(6, 78, 59, 0.25); --kpi-inflow-border: #10B981; --kpi-inflow-text: #34D399;
        --kpi-outflow-bg: rgba(127, 29, 29, 0.25); --kpi-outflow-border: #EF4444; --kpi-outflow-text: #F87171;
        --kpi-card-bg: #E3F4FB; --kpi-card-border: #B7D7EA; --kpi-card-accent: #E8B423; --kpi-card-label: #C9A227; --kpi-card-value: #B8860B;
        --table-header-bg: #2C3E50; --table-row-even: #1E293B; --table-row-odd: #182234; --table-row-hover: #26354D; --table-border: #334155;
    }}
    .stApp {{ background-color: var(--bg-main) !important; color: var(--text-body) !important; direction: {dir_attr}; }}
    section[data-testid="stSidebar"] {{ background-color: #15202B !important; border-left: 2px solid #E8B423 !important; direction: {dir_attr}; }}
    button[kind="primary"] {{ background: linear-gradient(135deg, #2C3E50 0%, #1A2834 100%) !important; border: 1px solid #E8B423 !important; }}
    .grid-header {{ background-color: #2C3E50 !important; color: #FFFFFF !important; font-weight: 900; font-size: 14px; padding: 12px 6px; border-radius: 0; text-align: center; border: none; border-bottom: 3px solid #E8B423 !important; z-index: 40 !important; }}
    .grid-row-inbound {{ background-color: var(--kpi-inflow-bg) !important; color: var(--kpi-inflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-inflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    .grid-row-outbound {{ background-color: var(--kpi-outflow-bg) !important; color: var(--kpi-outflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-outflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    [data-testid="stFileUploader"] {{ background: var(--bg-input) !important; border: 1.5px dashed var(--border-strong) !important; border-radius: 10px; }}
    .kpi-card {{
        flex: 1; background: var(--kpi-card-bg) !important; border: 1px solid var(--kpi-card-border) !important;
        border-top: 3px solid var(--kpi-card-accent) !important; padding: 18px 14px; border-radius: 10px; text-align: center;
    }}
    .kpi-card h5, .kpi-card h4 {{ color: var(--kpi-card-label) !important; margin: 0 !important; font-size: 17px !important; font-weight: 800 !important; text-align: center !important; }}
    .kpi-card h3, .kpi-card h2 {{ color: var(--kpi-card-value) !important; margin: 8px 0 0 0 !important; font-size: 30px !important; font-weight: 800 !important; text-align: center !important; }}
    .att-chip {{ display: inline-block; font-size: 12px; font-weight: 800; color: #C9A227; text-decoration: none; margin: 0 3px; }}
    .att-chip:hover {{ color: #E8B423; }}
    .section-banner {{
        background-color: var(--table-header-bg); color: #FFFFFF; padding: 14px 25px; border-radius: 8px;
        font-size: 20px; font-weight: 800; margin-bottom: 20px; text-align: {"right" if is_rtl else "left"};
        direction: {dir_attr}; border-{"right" if is_rtl else "left"}: 6px solid var(--brand-primary);
    }}
    .stApp h1, .stApp h2, .stApp h3 {{ text-align: {"right" if is_rtl else "left"} !important; }}
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <style>
    :root {{
        --bg-main: #F8FAFC; --bg-card: #FFFFFF; --border-subtle: #E2E8F0; --border-strong: #CBD5E1;
        --text-title: #2C3E50; --text-body: #334155; --text-muted: #64748B; --brand-primary: #C9A227; --brand-navy: #2C3E50; --brand-gold: #E8B423;
        --kpi-inflow-bg: #F0FDF4; --kpi-inflow-border: #10B981; --kpi-inflow-text: #047857;
        --kpi-outflow-bg: #FEF2F2; --kpi-outflow-border: #EF4444; --kpi-outflow-text: #B91C1C;
        --kpi-card-bg: #E3F4FB; --kpi-card-border: #B7D7EA; --kpi-card-accent: #E8B423; --kpi-card-label: #C9A227; --kpi-card-value: #B8860B;
        --table-header-bg: #2C3E50; --table-row-even: #FFFFFF; --table-row-odd: #F8FAFC; --table-row-hover: #F7F4EC; --table-border: #E2E8F0;
    }}
    .stApp {{ background-color: var(--bg-main) !important; color: var(--text-body) !important; direction: {dir_attr}; }}
    section[data-testid="stSidebar"] {{ background-color: #F6F4EE !important; border-left: 2px solid #E8B423 !important; direction: {dir_attr}; }}
    button[kind="primary"] {{ background: linear-gradient(135deg, #2C3E50 0%, #1A2834 100%) !important; border: 1px solid #E8B423 !important; }}
    .grid-header {{ background-color: #2C3E50 !important; color: #FFFFFF !important; font-weight: 900; font-size: 14px; padding: 12px 6px; border-radius: 0; text-align: center; border: none; border-bottom: 3px solid #E8B423 !important; z-index: 40 !important; }}
    .grid-row-inbound {{ background-color: var(--kpi-inflow-bg) !important; color: var(--kpi-inflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-inflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    .grid-row-outbound {{ background-color: var(--kpi-outflow-bg) !important; color: var(--kpi-outflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-outflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    [data-testid="stFileUploader"] {{ background: var(--bg-card) !important; border: 1.5px dashed var(--border-strong) !important; border-radius: 10px; }}
    .kpi-card {{
        flex: 1; background: var(--kpi-card-bg) !important; border: 1px solid var(--kpi-card-border) !important;
        border-top: 3px solid var(--kpi-card-accent) !important; padding: 18px 14px; border-radius: 10px; text-align: center;
    }}
    .kpi-card h5, .kpi-card h4 {{ color: var(--kpi-card-label) !important; margin: 0 !important; font-size: 17px !important; font-weight: 800 !important; text-align: center !important; }}
    .kpi-card h3, .kpi-card h2 {{ color: var(--kpi-card-value) !important; margin: 8px 0 0 0 !important; font-size: 30px !important; font-weight: 800 !important; text-align: center !important; }}
    .att-chip {{ display: inline-block; font-size: 12px; font-weight: 800; color: #C9A227; text-decoration: none; margin: 0 3px; }}
    .att-chip:hover {{ color: #E8B423; }}
    .section-banner {{
        background-color: var(--table-header-bg); color: #FFFFFF; padding: 14px 25px; border-radius: 8px;
        font-size: 20px; font-weight: 800; margin-bottom: 20px; text-align: {"right" if is_rtl else "left"};
        direction: {dir_attr}; border-{"right" if is_rtl else "left"}: 6px solid var(--brand-primary);
    }}
    .stApp h1, .stApp h2, .stApp h3 {{ text-align: {"right" if is_rtl else "left"} !important; }}
    </style>
    """, unsafe_allow_html=True)

st.markdown("""
<style>
.inv-table-marker { display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }
.inv-table-head [data-testid="stHorizontalBlock"] {
    background-color: #2C3E50 !important;
    border-radius: 10px 10px 0 0 !important;
    padding: 4px 8px 2px 8px !important;
    margin-bottom: 0 !important;
}
.inv-table-head [data-testid="column"] { background-color: #2C3E50 !important; }
div[data-testid="stVerticalBlock"][style*="overflow"]:has(.inv-table-marker) {
    max-height: 62vh !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    border: 1px solid #E8B42355 !important;
    border-top: none !important;
    border-radius: 0 0 10px 10px !important;
    padding: 6px 8px 10px 8px !important;
    margin-top: 0 !important;
}
</style>
""", unsafe_allow_html=True)

if st.session_state.system_lang == "العربية":
    t = {
        "add_proj": "➕ إضافة مشروع جديد...", "proj_label": "المشروع الحالي:", "save_proj": "حفظ المشروع", "new_proj_name": "اسم المشروع الجديد:",
        "user_mgmt": "⚙️ إدارة المستخدمين", "logout": "🚪 خروج", "user_mgmt_title": "👥 لوحة التحكم في المستخدمين والصلاحيات",
        "tab_records": "📑 سجل ومطابقة الفواتير", "tab_analytics": "📊 مؤشرات وتحليلات المشروع", "tab_memory": "⚙️ سياسات وضوابط النظام",
        "metric_in": "العهدة الواردة ⬇️", "metric_out": "إجمالي المنصرف ↗️", "metric_bal": "صافي السيولة 💰", "metric_burn": "معدل الاستهلاك ⚡", "curr": "ج.م",
        "filter_title": "🔍 أدوات البحث وتصفية السجلات", "filter_cat": "📂 التصنيف:", "filter_pay": "💳 طريقة الدفع:", "filter_date": "📅 الفترة:",
        "all": "الكل", "today": "اليوم", "this_week": "هذا الأسبوع", "this_month": "هذا الشهر", "custom": "فترة مخصصة", "from_date": "من تاريخ:", "to_date": "إلى تاريخ:",
        "no_records": "لا توجد سجلات مطابقة حالياً لعرضها في الجدول", "export_excel": "📥 تصدير السجلات إلى Excel (.xlsx)",
        "inbound": "وارد", "outbound": "منصرف", "view_att": "عرض المرفق", "att_item": "مرفق", "col_serial": "السريال", "col_type": "نوع الحركة", "col_doc_no": "رقم المستند",
        "col_date": "التاريخ", "col_desc": "البيان / الوصف", "col_amount": "المبلغ", "col_vat": "الضريبة", "col_pay": "طريقة الدفع", "col_cat": "التصنيف",
        "col_remark": "الملاحظات", "col_del": "حذف", "col_att": "المرفقات",
        "sec_reg": "🧾 تسجيل فاتورة / مستند سداد جديد", "doc_type_prompt": "نوع المستند", "out_opt": "🔴 منصرف", "in_opt": "🟢 وارد",
        "out_opt_sub": "فواتير وإيصالات صرف", "in_opt_sub": "سندات قبض وتمويل عهدة", "doc_select": "تحديد",
        "tab_upload": "📁 رفع ملفات", "tab_paste": "📋 لصق مباشر", "choose_files": "أسقط الملفات هنا أو اضغط للاختيار", "paste_hint": "ارفع لقطة الشاشة",
        "start_process": "بدء المعالجة واستخراج البيانات", "merge_btn": "📎 إرفاق كمرفق", "save_btn": "✅ اعتماد وحفظ كفاتورة", "dismiss_btn": "❌ استبعاد",
        "settings_title": "⚙️ الإعدادات", "lang_label": "اللغة:", "theme_label": "المظهر:", "theme_light": "☀️ نهاري", "theme_dark": "🌙 ليلي",
        "connected": "🟢 متصل", "disconnected": "🔴 غير متصل", "synced": "🟢 متزامن", "sync_btn": "🔄 مزامنة السجلات من الشيت",
        "coming_soon": "قريباً", "in_prep": "قيد التجهيز",
        "soon_body": "هذه الوحدة قيد التجهيز وستكون متاحة في إصدار لاحق.",
        "programs_title": "الرقابة والتحكم المالي للمشاريع",
        "prog_custody": "إدارة الفواتير والعهد",
        "prog_sub": "مستخلصات مقاولي الباطن",
        "prog_client": "مستخلصات العميل",
        "prog_exec": "التحليل المالي التنفيذي",
        "sync_spinner": "جاري المزامنة...", "sync_done": "اكتملت المزامنة",
        "calc_expr": "أدخل العملية الحسابية (مثال: 801*1.14):", "calc_err": "تعذر حساب التعبير",
        "date_fmt": "التاريخ (سنة-شهر-يوم)", "process_spinner": "جاري معالجة الملفات...",
        "api_disc": "⚠️ مفتاح الاتصال غير متصل.", "footer_brand": "Un-matt ConTch @2026",
        "pwd_btn": "🔑 كلمة المرور", "del_proj_help": "حذف المشروع", "confirm": "تأكيد", "cancel": "إلغاء",
        "proj_deleted": "تم حذف المشروع", "brand_fallback": "اليسر للهندسة والمقاولات",
        "role_super": "🛡️ مدير النظام", "role_admin": "👑 مدير الشركة", "role_ceo": "💼 الرئيس التنفيذي", "role_acc": "📊 محاسب",
        "assistant_title": "💼 المساعد المالي الذكي", "assistant_info": "تحليل مباشر لبيانات المشروع:",
        "assistant_you": "أنت", "assistant_bot": "المساعد",
        "assistant_placeholder": "اكتب سؤالك هنا عن فواتير ومصروفات المشروع...",
        "assistant_clear": "مسح المحادثة 🗑️", "assistant_spinner": "جاري استرجاع البيانات والتدقيق...",
        "analytics_title": "📊 مؤشرات وتحليلات المشروع", "print_report": "🖨️ طباعة التقرير التنفيذي المعتمد (A3)",
        "analytics_scope": "نطاق التحليل:", "analytics_all": "الكل (جميع المشاريع)", "issue_date": "تاريخ الإصدار",
        "insights_title": "التحليل المالي والتوصيات التنفيذية",
        "insight_kicker": "توصية تنفيذية",
        "insight_cost_title": "تركز السيولة وأكبر بنود التكلفة",
        "insight_cash_title": "كفاءة السيولة ومخاطر السداد",
        "insight_rec_label": "التوصية",
        "chart_cat": "توزيع المنصرف حسب التصنيف", "chart_pay": "طرق السداد المستخدمة", "chart_trend": "تحليل الاتجاهات الزمنية للتدفقات المالية",
        "trend_in": "الوارد", "trend_out": "المنصرف", "audit_title": "📋 سجل العمليات وحركات الحذف",
        "audit_col_time": "التوقيت", "audit_col_user": "المستخدم", "audit_col_action": "الإجراء", "audit_col_details": "التفاصيل",
        "no_audit": "لا توجد حركات مسجلة حالياً.",
        "queue_info": "⏳ قائمة المراجعة: المستند رقم", "of_total": "من إجمالي",
        "calc_title": "🔢 آلة حاسبة", "calc_btn": "احسب", "calc_res": "النتيجة:"
    }
else:
    t = {
        "add_proj": "➕ Add New Project...", "proj_label": "Current Project:", "save_proj": "Save Project", "new_proj_name": "New Project Name:",
        "user_mgmt": "⚙️ User Management", "logout": "🚪 Logout", "user_mgmt_title": "👥 User Access & Permissions Control",
        "tab_records": "📑 Invoice Register & Reconciliation", "tab_analytics": "📊 Project Analytics & KPIs", "tab_memory": "⚙️ System Policies & Controls",
        "metric_in": "Total Inbound Funds ⬇️", "metric_out": "Total Expenses ↗️", "metric_bal": "Net Balance 💰", "metric_burn": "Burn Rate ⚡", "curr": "EGP",
        "filter_title": "🔍 Search & Filter Tools", "filter_cat": "📂 Category:", "filter_pay": "💳 Payment Method:", "filter_date": "📅 Period:",
        "all": "All", "today": "Today", "this_week": "This Week", "this_month": "This Month", "custom": "Custom Range", "from_date": "From:", "to_date": "To:",
        "no_records": "No matching records found to display.", "export_excel": "📥 Export to Excel (.xlsx)",
        "inbound": "Inbound", "outbound": "Outbound", "view_att": "View file", "att_item": "File", "col_serial": "Serial", "col_type": "Type", "col_doc_no": "Doc No.",
        "col_date": "Date", "col_desc": "Description", "col_amount": "Amount", "col_vat": "VAT", "col_pay": "Payment Method", "col_cat": "Category",
        "col_remark": "Remarks", "col_del": "Delete", "col_att": "Attachment",
        "sec_reg": "🧾 Register Invoice / Payment Receipt", "doc_type_prompt": "Document type", "out_opt": "🔴 Outbound", "in_opt": "🟢 Inbound",
        "out_opt_sub": "Invoices and payment receipts", "in_opt_sub": "Receipts and custody funding", "doc_select": "Select",
        "tab_upload": "📁 Upload files", "tab_paste": "📋 Paste image", "choose_files": "Drop files here or click to browse", "paste_hint": "Upload a screenshot",
        "start_process": "Start Processing & Extraction", "merge_btn": "📎 Attach as Document", "save_btn": "✅ Approve & Save", "dismiss_btn": "❌ Exclude",
        "settings_title": "⚙️ Settings", "lang_label": "Language:", "theme_label": "Theme:", "theme_light": "☀️ Light", "theme_dark": "🌙 Dark",
        "connected": "🟢 Connected", "disconnected": "🔴 Disconnected", "synced": "🟢 Synced", "sync_btn": "🔄 Sync Records from Sheet",
        "coming_soon": "Coming Soon", "in_prep": "In preparation",
        "soon_body": "This module is in preparation and will be available in a later release.",
        "programs_title": "Project Financial Control",
        "prog_custody": "Invoices & Custody Management",
        "prog_sub": "Subcontractors' IPCs",
        "prog_client": "Client's IPCs",
        "prog_exec": "Financial Executive Analysis",
        "sync_spinner": "Syncing...", "sync_done": "Sync complete",
        "calc_expr": "Enter expression (e.g. 801*1.14):", "calc_err": "Could not calculate the expression",
        "date_fmt": "Date (YYYY-MM-DD)", "process_spinner": "Processing files...",
        "api_disc": "⚠️ API key disconnected.", "footer_brand": "Un-matt ConTch @2026",
        "pwd_btn": "🔑 Password", "del_proj_help": "Delete project", "confirm": "Confirm", "cancel": "Cancel",
        "proj_deleted": "Project deleted", "brand_fallback": "Al Yosser Engineering & Contracting",
        "role_super": "🛡️ Super Admin", "role_admin": "👑 Company Admin", "role_ceo": "💼 CEO", "role_acc": "📊 Accountant",
        "assistant_title": "💼 Smart Financial Assistant", "assistant_info": "Live analysis for project:",
        "assistant_you": "You", "assistant_bot": "Assistant",
        "assistant_placeholder": "Ask about this project's invoices and expenses...",
        "assistant_clear": "Clear chat 🗑️", "assistant_spinner": "Retrieving records and reviewing...",
        "analytics_title": "📊 Project Analytics & Executive Summary", "print_report": "🖨️ Print Executive Report (A3)",
        "analytics_scope": "Analysis scope:", "analytics_all": "All Projects", "issue_date": "Issue date",
        "insights_title": "Financial Analysis & Executive Recommendations",
        "insight_kicker": "Executive insight",
        "insight_cost_title": "Liquidity concentration & top cost item",
        "insight_cash_title": "Cash efficiency & payment risk",
        "insight_rec_label": "Recommendation",
        "chart_cat": "Expense Distribution by Category", "chart_pay": "Payment Methods Breakdown", "chart_trend": "Cashflow Trend Analysis Over Time",
        "trend_in": "Inbound", "trend_out": "Outbound", "audit_title": "📋 Audit Trail & Deletion Log",
        "audit_col_time": "Timestamp", "audit_col_user": "User", "audit_col_action": "Action", "audit_col_details": "Details",
        "no_audit": "No audit logs yet.",
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
        <div style="display: flex; justify-content: center; align-items: center; margin: 6px 0 22px 0;">
            <div style="width: 204px; height: 204px; border-radius: 50%; background-color: #FFFFFF; border: 3.5px solid #2C3E50; outline: 3px solid rgba(232, 180, 35, 0.45); outline-offset: 3px; box-shadow: 0 6px 16px rgba(44, 62, 80, 0.16); display: flex; align-items: center; justify-content: center; overflow: hidden; padding: 19px;">
                <img src="data:image/png;base64,{logo_b64_str}" alt="{t['brand_fallback']}" style="width: 100%; height: 100%; object-fit: contain;" />
            </div>
        </div>
        """, unsafe_allow_html=True)
    else: st.title(f"🏢 {t['brand_fallback']}")

    st.markdown("""
    <style>
    section[data-testid="stSidebar"] .block-container { padding-top: 0.6rem !important; padding-bottom: 1.4rem !important; }
    section[data-testid="stSidebar"] .stButton button {
        border-radius: 10px !important; font-weight: 700 !important; min-height: 42px !important;
        white-space: normal !important; line-height: 1.35 !important;
    }
    section[data-testid="stSidebar"] button[kind="primary"] {
        background: linear-gradient(135deg, #2C3E50 0%, #1A2834 100%) !important;
        border: 1.5px solid #E8B423 !important; color: #FFFFFF !important;
    }
    .sb-programs-title {
        text-align: start; font-size: 18px; font-weight: 900; color: var(--text-title, #2C3E50);
        margin: 2px 0 12px 0; padding: 0 2px 8px 2px; letter-spacing: 0.01em; line-height: 1.35;
        border-bottom: 3px solid #E8B423;
    }
    .sb-settings-title {
        text-align: start; font-size: 18px; font-weight: 800; color: var(--text-title, #2C3E50);
        margin: 4px 0 12px 0; padding: 0 2px;
    }
    .sb-program-meta {
        text-align: start; font-size: 11px; color: var(--text-muted, #64748B);
        margin: -4px 0 8px 2px; line-height: 1.4;
    }
    .sb-status-row {
        display: flex; justify-content: space-between; align-items: center; gap: 8px;
        margin: 8px 0 10px 0; padding: 8px 10px; background: #FFFFFF;
        border: 1px solid #E6D9A8; border-radius: 10px;
    }
    .sb-status-item {
        flex: 1; text-align: center; font-size: 12.5px; font-weight: 700; color: #2C3E50;
    }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #FFFFFF !important; border: 1px solid #E6D9A8 !important;
        border-radius: 10px !important; padding: 10px 12px 8px 12px !important;
        margin: 4px 0 10px 0 !important; box-shadow: none !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] .sb-settings-title {
        margin: 0 0 10px 0; padding: 0 0 8px 0; text-align: start;
        font-size: 18px; font-weight: 800; color: var(--text-title, #2C3E50);
        border-bottom: 1px solid #E6D9A8;
    }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stRadio"] {
        margin-bottom: 4px !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stWidgetLabel"] p,
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] label p {
        font-weight: 700 !important; font-size: 13px !important; color: #2C3E50 !important;
        margin-bottom: 2px !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stRadio"] > div {
        gap: 8px !important; justify-content: flex-start !important;
    }
    .fin-info-card {
        background: #FFFFFF; color: #2C3E50; border-radius: 12px; padding: 10px 12px; margin-bottom: 10px;
        border: 1px solid #E6D9A8; border-right: 4px solid #E8B423; font-size: 13px; font-weight: 700; line-height: 1.5;
        box-shadow: 0 2px 8px rgba(44, 62, 80, 0.05);
    }
    .fin-chat-wrap {
        background: #FBF9F3; border: 1px solid #E6D9A8; border-radius: 12px; padding: 8px 8px 4px 8px;
        margin-bottom: 8px;
    }
    .fin-user-bubble {
        background: #F7F4EC; color: #2C3E50; border: 1px solid #E6D9A8;
        border-radius: 12px 12px 4px 12px; padding: 9px 11px; margin: 7px 0 7px 10px;
        font-size: 12.5px; line-height: 1.55; box-shadow: 0 1px 3px rgba(44, 62, 80, 0.06);
    }
    .fin-user-bubble b { color: #8A6A10; }
    .fin-bot-bubble {
        background: #F0FDF4; color: #065F46; border: 1px solid #BBF7D0;
        border-radius: 12px 12px 12px 4px; padding: 9px 11px; margin: 7px 10px 7px 0;
        font-size: 12.5px; line-height: 1.55; box-shadow: 0 1px 3px rgba(6, 95, 70, 0.06);
    }
    .fin-bot-bubble b { color: #047857; }
    </style>
    """, unsafe_allow_html=True)

    if st.session_state.active_portal_module not in ("custody", "subcontractor", "client", "executive"):
        st.session_state.active_portal_module = "custody"

    st.markdown(f'<div class="sb-programs-title">{t["programs_title"]}</div>', unsafe_allow_html=True)
    program_items = [
        ("custody", "🧾", t["prog_custody"], False),
        ("subcontractor", "🏗️", t["prog_sub"], True),
        ("client", "📑", t["prog_client"], True),
        ("executive", "📊", t["prog_exec"], False),
    ]
    for key, icon, title, is_soon in program_items:
        is_active = st.session_state.active_portal_module == key
        btn_type = "primary" if is_active else "secondary"
        if st.button(f"{icon}  {title}", use_container_width=True, type=btn_type, key=f"prog_btn_{key}"):
            st.session_state.active_portal_module = key
            if key == "custody":
                st.session_state.active_tab = "records"
            elif key == "executive":
                st.session_state.active_tab = "analytics"
            st.rerun()
        if is_soon:
            st.markdown(f'<div class="sb-program-meta">{t["coming_soon"]} — {t["in_prep"]}</div>', unsafe_allow_html=True)

    st.divider()
    with st.container(border=True):
        st.markdown(f'<div class="sb-settings-title">{t["settings_title"]}</div>', unsafe_allow_html=True)
        lang_choice = st.radio(t["lang_label"], ["العربية", "English"], index=0 if st.session_state.system_lang == "العربية" else 1, horizontal=True)
        if lang_choice != st.session_state.system_lang:
            st.session_state.system_lang = lang_choice; st.rerun()

        theme_options = [t["theme_light"], t["theme_dark"]]
        cur_th_idx = 0 if st.session_state.system_theme == "Light" else 1
        theme_selected = st.radio(t["theme_label"], theme_options, index=cur_th_idx, horizontal=True)
        new_theme = "Light" if theme_selected == t["theme_light"] else "Dark"
        if new_theme != st.session_state.system_theme:
            st.session_state.system_theme = new_theme; st.rerun()

    status_left = t["connected"] if api_key else t["disconnected"]
    st.markdown(f"""
    <div class="sb-status-row">
        <span class="sb-status-item">{status_left}</span>
        <span class="sb-status-item">{t["synced"]}</span>
    </div>
    """, unsafe_allow_html=True)
        
    if st.button(t["sync_btn"], use_container_width=True):
        with st.spinner(t["sync_spinner"]):
            try:
                cloud = load_cloud_records() or []
            except Exception:
                cloud = []
            st.session_state.invoices_data = merge_invoice_lists(cloud, st.session_state.invoices_data)
            retry_pending_cloud_sync()
            apply_pending_sync_results()
            save_local_invoices(st.session_state.invoices_data)
            st.toast(t["sync_done"], icon="☁️")
            time.sleep(0.5); st.rerun()

    assistant_proj = st.session_state.get("selected_proj") or (
        st.session_state.projects_list[0] if st.session_state.projects_list else DEFAULT_PROJECTS[0]
    )
    st.divider()
    with st.expander(t["assistant_title"], expanded=False):
        st.markdown(f"""
        <div class="fin-info-card">📊 {t["assistant_info"]} {assistant_proj}</div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="fin-chat-wrap">', unsafe_allow_html=True)
        for msg in st.session_state.chat_messages[-8:]:
            safe_content = str(msg.get("content", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            if msg["role"] == "user":
                st.markdown(f"""
                <div class="fin-user-bubble"><b>👤 {t["assistant_you"]}:</b><br>{safe_content}</div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="fin-bot-bubble"><b>🤖 {t["assistant_bot"]}:</b><br>{safe_content}</div>
                """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        user_query = st.chat_input(t["assistant_placeholder"], key="assistant_chat_input")
        if user_query:
            st.session_state.chat_messages.append({"role": "user", "content": user_query})
            with st.spinner(t["assistant_spinner"]):
                try:
                    ans = ask_project_assistant(
                        user_query=user_query,
                        project_name=assistant_proj,
                        invoices_list=st.session_state.invoices_data,
                        rules_dict=st.session_state.system_dictionary,
                        api_key=api_key
                    )
                except Exception as e:
                    ans = str(e)
            st.session_state.chat_messages.append({"role": "assistant", "content": ans})
            st.rerun()

        if st.session_state.chat_messages:
            if st.button(t["assistant_clear"], use_container_width=True, key="clear_assistant_chat"):
                st.session_state.chat_messages = []
                st.rerun()

    st.divider()
    with st.expander(t["calc_title"], expanded=False):
        calc_expr = st.text_input(t["calc_expr"], value="", key="quick_calc_in")
        if st.button(t["calc_btn"], use_container_width=True):
            try:
                clean_expr = re.sub(r'[^0-9\+\-\*\/\.\(\)\s]', '', calc_expr)
                if clean_expr.strip():
                    res = eval(clean_expr)
                    st.success(f"{t['calc_res']} **{res:,.2f}**")
            except Exception:
                st.error(t["calc_err"])

if st.session_state.active_portal_module in ("subcontractor", "client"):
    soon_map = {
        "subcontractor": t["prog_sub"],
        "client": t["prog_client"],
    }
    soon_title = soon_map.get(st.session_state.active_portal_module, t["coming_soon"])
    st.markdown(f"""
    <div style="max-width: 720px; margin: 48px auto; background: var(--bg-card, #FFFFFF); border: 1px solid var(--border-subtle, #E2E8F0); border-radius: 18px; padding: 36px 32px; text-align: center; box-shadow: 0 10px 28px rgba(15,37,69,0.08);">
        <div style="display:inline-block; background:#F1F5F9; color:#0369A1; border:1px solid #BAE6FD; border-radius:999px; padding:4px 12px; font-size:12px; font-weight:800; margin-bottom:14px;">{t["coming_soon"]}</div>
        <h2 style="margin: 0 0 8px 0; color: var(--text-title, #0F172A);">{soon_title}</h2>
        <p style="margin: 0; color: var(--text-muted, #64748B); font-size: 15px; line-height: 1.7;">{t["soon_body"]}</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

col_proj, col_proj_del, col_empty, col_user = st.columns([2.0, 0.5, 0.3, 2.2])

can_manage_projects = is_company_admin or is_ceo or is_super_admin
if can_manage_projects:
    available_projects = st.session_state.projects_list + [t["add_proj"]]
else:
    available_projects = current_user_data.get("allowed_projects", [DEFAULT_PROJECTS[0]])
    if isinstance(available_projects, str): available_projects = [available_projects]

selected_proj = col_proj.selectbox(t["proj_label"], available_projects, label_visibility="collapsed")
st.session_state.selected_proj = selected_proj

with col_proj_del:
    if can_manage_projects and selected_proj != t["add_proj"]:
        if st.button("🗑️", help=t["del_proj_help"], use_container_width=True):
            st.session_state.confirm_delete_proj = True

if st.session_state.confirm_delete_proj and can_manage_projects:
    st.warning(f"{t['del_proj_help']}: {selected_proj}")
    c_yd, c_nd, _ = st.columns([1, 1, 4])
    with c_yd:
        if st.button(t["confirm"], type="primary", use_container_width=True):
            if selected_proj in st.session_state.projects_list:
                st.session_state.projects_list.remove(selected_proj)
                if not st.session_state.projects_list: st.session_state.projects_list = list(DEFAULT_PROJECTS)
                save_projects_list_to_disk(st.session_state.projects_list)
                st.session_state.confirm_delete_proj = False
                st.toast(t["proj_deleted"], icon="✅")
                time.sleep(0.5); st.rerun()
    with c_nd:
        if st.button(t["cancel"], use_container_width=True):
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
        "Super Admin": t["role_super"],
        "Admin": t["role_admin"],
        "CEO": t["role_ceo"],
        "Accountant": t["role_acc"],
    }
    st.info(f"**{current_user_data['name']}** &bull; `{role_badges.get(user_role, user_role)}`")
    
    b_c1, b_c2, b_c3 = st.columns([1.2, 1, 0.8])
    with b_c1:
        if (is_company_admin or is_ceo or is_super_admin) and st.button(t["user_mgmt"], use_container_width=True):
            st.session_state.show_user_mgmt = not st.session_state.show_user_mgmt; st.rerun()
    with b_c2:
        if st.button(t["pwd_btn"], use_container_width=True):
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
if can_access_system_policies:
    tabs_list.append(t["tab_memory"])

tab_cols = st.columns(len(tabs_list))
for idx, tab_name in enumerate(tabs_list):
    key_slug = "records" if idx == 0 else ("analytics" if idx == 1 else "memory")
    with tab_cols[idx]:
        if st.button(tab_name, use_container_width=True, type="primary" if st.session_state.active_tab == key_slug else "secondary"):
            st.session_state.active_tab = key_slug; st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

if st.session_state.active_tab == "records":
    apply_pending_sync_results()
    st.markdown(f"""
    <div style='display: flex; gap: 15px; margin-bottom: 30px;'>
        <div class="kpi-card"><h5>{t["metric_in"]}</h5><h3>{total_in:,.2f} {t["curr"]}</h3></div>
        <div class="kpi-card"><h5>{t["metric_out"]}</h5><h3>{total_out:,.2f} {t["curr"]}</h3></div>
        <div class="kpi-card"><h5>{t["metric_bal"]}</h5><h3>{balance:,.2f} {t["curr"]}</h3></div>
        <div class="kpi-card"><h5>{t["metric_burn"]}</h5><h3>{burn_rate:.1f}%</h3></div>
    </div>
    """, unsafe_allow_html=True)

    if not is_ceo or is_super_admin:
        if len(st.session_state.invoice_queue) == 0:
            st.markdown(f"""
            <div class="section-banner">
                {t['sec_reg']}
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("""
            <style>
            .st-key-doc_kind_out button, .st-key-doc_kind_in button {
                min-height: 78px !important; border-radius: 12px !important; font-weight: 800 !important;
                white-space: pre-line !important; line-height: 1.35 !important; font-size: 15px !important;
            }
            .st-key-doc_kind_out button[kind="primary"] { border: 2px solid #B91C1C !important; }
            .st-key-doc_kind_in button[kind="primary"] { border: 2px solid #047857 !important; }
            div[data-testid="stFileUploader"] { min-height: 120px; }
            </style>
            """, unsafe_allow_html=True)
            kind_out = st.session_state.upload_doc_kind == "out"
            kind_in = not kind_out
            is_inbound = kind_in

            if is_rtl:
                col_type, col_input = st.columns([1.05, 1.55], gap="medium")
            else:
                col_input, col_type = st.columns([1.55, 1.05], gap="medium")

            with col_type:
                st.caption(t["doc_type_prompt"])
                if st.button(f"{t['out_opt']}\n{t['out_opt_sub']}", use_container_width=True, type="primary" if kind_out else "secondary", key="doc_kind_out"):
                    st.session_state.upload_doc_kind = "out"
                    st.rerun()
                if st.button(f"{t['in_opt']}\n{t['in_opt_sub']}", use_container_width=True, type="primary" if kind_in else "secondary", key="doc_kind_in"):
                    st.session_state.upload_doc_kind = "in"
                    st.rerun()

            with col_input:
                upload_tab1, upload_tab2 = st.tabs([t["tab_upload"], t["tab_paste"]])
                main_files = []
                with upload_tab1:
                    uploaded = st.file_uploader(t["choose_files"], type=['jpg', 'png', 'jpeg', 'pdf'], accept_multiple_files=True, label_visibility="collapsed")
                    if uploaded: main_files.extend(uploaded)
                with upload_tab2:
                    pasted_img = st.file_uploader(t["paste_hint"], type=['png', 'jpg', 'jpeg'], key="paste_uploader", label_visibility="collapsed")
                    if pasted_img: main_files.append(pasted_img)
                if st.button(t["start_process"], type="primary", use_container_width=True):
                    if not api_key: st.error(t["api_disc"])
                    elif not main_files: st.warning("⚠️ Please select files first.")
                    else:
                        with st.spinner(t["process_spinner"]):
                            st.session_state.invoice_queue = []
                            for file in main_files:
                                file_bytes = file.read()
                                if file.name.lower().endswith('.pdf'):
                                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                                    for i in range(len(doc)):
                                        page = doc.load_page(i)
                                        rot = page.rotation
                                        mat = fitz.Matrix(1.6, 1.6).prerotate(rot)
                                        pix = page.get_pixmap(matrix=mat, alpha=False)
                                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                        if img.height > img.width:
                                            img = img.rotate(90, expand=True)
                                        gray = img.convert("L")
                                        w, h = gray.size
                                        band = max(8, h // 8)
                                        top_vals = gray.crop((w // 8, 0, max(w // 8 + 1, w - w // 8), band)).getdata()
                                        bot_vals = gray.crop((w // 8, h - band, max(w // 8 + 1, w - w // 8), h)).getdata()
                                        top_dark = sum(1 for p in top_vals if p < 160)
                                        bot_dark = sum(1 for p in bot_vals if p < 160)
                                        if top_dark == 0 and bot_dark > 20:
                                            img = img.rotate(180, expand=True)
                                        st.session_state.invoice_queue.append({"image": img, "name": f"{file.name} - p{i+1}"})
                                else:
                                    img = Image.open(io.BytesIO(file_bytes))
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
                    inv_date = st.text_input(t["date_fmt"], value=normalize_date(data.get("invoice_date", "")))
                
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
                        try:
                            new_serial = len(active_project_invoices) + 1
                            type_icon = "🟢 وارد" if current_type == "وارد" else "🔴 منصرف"
                            clean_inv_date = normalize_date(inv_date)
                            row_data = [new_serial, type_icon, inv_no, clean_inv_date, desc, amount, vat, pay_method, category, remark, "False", "مرفق", selected_proj]
                            pending_path = save_pending_sync_image(current_item["image"], selected_proj, new_serial)
                            new_record = {
                                "serial_no": new_serial, "doc_type": current_type, "invoice_no": inv_no,
                                "invoice_date": clean_inv_date, "description": desc, "remark": remark,
                                "amount": amount, "vat": vat, "payment_method": pay_method,
                                "category": category, "delete": False, "project": selected_proj,
                                "filename": current_item["name"], "drive_link": "",
                                "cloud_synced": False, "pending_image_path": pending_path
                            }
                            st.session_state.invoices_data.append(new_record)
                            save_local_invoices(st.session_state.invoices_data)
                            st.session_state.last_saved_serial = new_serial
                            record_learned_sample(inv_no, desc, amount, category, pay_method, selected_proj)
                            try:
                                upsert_smart_dictionary(desc, category)
                            except Exception:
                                pass
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

                            img_copy = current_item["image"].copy()
                            fname_copy = current_item["name"]
                            sync_thread = threading.Thread(
                                target=cloud_sync_invoice_background,
                                args=(img_copy, fname_copy, row_data, selected_proj, new_serial),
                                daemon=True
                            )
                            sync_thread.start()
                            st.session_state.pending_invoice = None
                            st.session_state.queue_index += 1
                            st.rerun()
                        except Exception as e:
                            st.error(f"فشل الحفظ المحلي: {e}")

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
    <div class="section-banner">
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
            t["col_remark"]: clean_remark_for_display(item.get("remark"))
        } for item in filtered_list])
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer: excel_df.to_excel(writer, index=False, sheet_name=selected_proj[:30])
        ex_col1, ex_col2 = st.columns([3, 1])
        with ex_col2: st.download_button(label=t["export_excel"], data=excel_buffer.getvalue(), file_name=f"records_{selected_proj}_{datetime.date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    # ضبط عروض الأعمدة لضمان ظهور زر الحذف بوضوح
    grid_cols = [0.8, 1.1, 1.1, 1.2, 2.2, 1.2, 0.9, 1.3, 1.1, 1.6, 0.9, 1.1]
    st.markdown("<div class='inv-table-head'>", unsafe_allow_html=True)
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
    st.markdown("</div>", unsafe_allow_html=True)

    with st.container(height=620, border=False):
        st.markdown("<div class='inv-table-marker'></div>", unsafe_allow_html=True)
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
                c9.markdown(f"<div class='{row_style}'>{clean_remark_for_display(row.get('remark', ''))}</div>", unsafe_allow_html=True)
                with c10:
                    if can_delete_records:
                        if st.button("🗑️", key=f"del_btn_{row.get('serial_no')}_{idx}", use_container_width=True, help="حذف الفاتورة"):
                            st.session_state.confirm_delete_id = row.get("serial_no")
                            st.rerun()
                    else:
                        st.markdown(f"<div class='{row_style}'>🔒</div>", unsafe_allow_html=True)
                with c11:
                    att_links, extra_n = collect_row_attachments(row)
                    chips = []
                    if att_links:
                        for i, url in enumerate(att_links, start=1):
                            label = t["view_att"] if len(att_links) == 1 and extra_n == 0 else f"{t['att_item']} {i}"
                            chips.append(f"<a class='att-chip' href='{url}' target='_blank'>{label}</a>")
                        for j in range(len(att_links) + 1, len(att_links) + extra_n + 1):
                            chips.append(f"<span class='att-chip'>{t['att_item']} {j}</span>")
                    elif extra_n:
                        for i in range(1, extra_n + 1):
                            chips.append(f"<span class='att-chip'>{t['att_item']} {i}</span>")
                    att_html = " ".join(chips) if chips else "—"
                    st.markdown(f"<div class='{row_style}'>{att_html}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='text-align: center; color: var(--text-muted); font-weight: bold; padding: 25px; background-color: var(--bg-card); border-radius: 8px; border: 1px solid var(--border-subtle); margin-top: 5px;'>{t['no_records']}</div>", unsafe_allow_html=True)

elif st.session_state.active_tab == "analytics":
    analytics_projects = [p for p in available_projects if p != t["add_proj"]]
    if "analytics_scope" not in st.session_state:
        st.session_state.analytics_scope = selected_proj if selected_proj in analytics_projects else "__all__"
    if st.session_state.analytics_scope not in ["__all__"] + analytics_projects:
        st.session_state.analytics_scope = selected_proj if selected_proj in analytics_projects else "__all__"

    page_dir = "rtl" if is_rtl else "ltr"
    align_css = "right" if is_rtl else "left"
    issue_date_val = datetime.date.today().strftime("%Y-%m-%d")
    chart_font = "#2C3E50" if st.session_state.system_theme == "Light" else "#F8FAFC"

    st.markdown(f"""
    <style>
    .analytics-wrap {{ direction: {page_dir}; text-align: {align_css}; }}
    .analytics-wrap h2, .analytics-wrap h3, .analytics-wrap h4, .analytics-wrap p {{ text-align: {align_css} !important; }}
    .analytics-toolbar {{
        background: var(--bg-card, #FFFFFF); border: 1px solid #E6D9A8; border-radius: 12px;
        padding: 14px 16px; margin-bottom: 14px; box-shadow: 0 4px 12px rgba(44,62,80,0.05);
    }}
    .analytics-title {{ margin: 0 0 4px 0; color: #2C3E50; font-size: 22px; font-weight: 800; text-align: {align_css}; }}
    .analytics-date {{ color: var(--text-muted, #64748B); font-size: 13px; font-weight: 700; text-align: {align_css}; margin-top: 2px; }}
    .exec-insight-card {{
        background: var(--bg-card, #FFFFFF); border: 1px solid #E6D9A8; border-{ 'right' if is_rtl else 'left' }: 4px solid #E8B423;
        border-radius: 12px; padding: 16px 18px; min-height: 170px; text-align: {align_css}; direction: {page_dir};
        box-shadow: 0 4px 14px rgba(44,62,80,0.06);
    }}
    .exec-insight-kicker {{ font-size: 11px; font-weight: 800; color: #C9A227; margin-bottom: 6px; letter-spacing: 0.04em; }}
    .exec-insight-title {{ font-size: 15px; font-weight: 800; color: var(--text-title, #2C3E50); margin-bottom: 8px; }}
    .exec-insight-body {{ font-size: 13px; line-height: 1.7; color: var(--text-body, #334155); }}
    .exec-insight-action {{
        margin-top: 12px; padding: 10px 12px; background: #F7F4EC; border-radius: 8px;
        font-size: 12.5px; line-height: 1.65; color: #2C3E50;
    }}
    .audit-table {{ width: 100%; border-collapse: collapse; direction: {page_dir}; text-align: {align_css}; }}
    .audit-table th {{
        background: #2C3E50; color: #FFFFFF; padding: 10px 12px; font-size: 13px; font-weight: 800;
        text-align: {align_css}; border-bottom: 2px solid #E8B423;
    }}
    .audit-table td {{
        padding: 9px 12px; border-bottom: 1px solid #E6D9A8; font-size: 12.5px; text-align: {align_css};
        background: var(--bg-card, #FFFFFF); color: var(--text-body, #334155);
    }}
    .audit-table tr:nth-child(even) td {{ background: #FBF9F3; }}
    .audit-wrap {{
        background: var(--bg-card, #FFFFFF); border: 1px solid #E6D9A8; border-radius: 12px;
        overflow: hidden; box-shadow: 0 4px 12px rgba(44,62,80,0.05);
    }}
    .print-only-header {{ display: none !important; }}
    @media print {{
        @page {{ size: A3 landscape; margin: 10mm 12mm; }}
        html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main, .block-container {{
            background: #FFFFFF !important; color: #2C3E50 !important;
            overflow: visible !important; height: auto !important; max-width: 100% !important;
            padding: 0 !important; margin: 0 !important;
        }}
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"],
        [data-testid="stStatusWidget"],
        [data-testid="stBottomBlockContainer"],
        footer, #MainMenu, .stDeployButton, .stAppToolbar,
        .no-print, .footer-container, .analytics-toolbar,
        [data-testid="stExpander"],
        [data-testid="stSelectbox"],
        [data-testid="stIFrame"],
        [data-testid="stInfo"],
        [data-testid="stAlert"],
        [data-testid="stDivider"],
        .stButton, [data-testid="stButton"],
        .audit-section, .audit-wrap, .audit-table {{
            display: none !important; visibility: hidden !important; height: 0 !important; width: 0 !important;
            overflow: hidden !important; page-break-after: avoid !important;
        }}
        body * {{ visibility: hidden !important; }}
        .print-report, .print-report *,
        .print-only-header, .print-only-header *,
        .kpi-container, .kpi-container *, .kpi-card, .kpi-card *,
        .print-chart-block, .print-chart-block *,
        .print-keep, .print-keep *,
        .exec-insight-card, .exec-insight-card *,
        [data-testid="stPlotlyChart"], [data-testid="stPlotlyChart"] *,
        .js-plotly-plot, .js-plotly-plot *, .plot-container, .plot-container *, .svg-container, .svg-container * {{
            visibility: visible !important;
        }}
        .audit-section, .audit-section *, .audit-wrap, .audit-wrap *, .audit-table, .audit-table * {{
            display: none !important; visibility: hidden !important;
        }}
        [data-testid="stAppViewContainer"] {{ margin-left: 0 !important; }}
        section[data-testid="stSidebar"] {{ display: none !important; width: 0 !important; min-width: 0 !important; }}
        .print-only-header {{ display: block !important; margin-bottom: 10px !important; border-bottom: 3px solid #E8B423; padding-bottom: 8px; page-break-after: avoid !important; }}
        .analytics-wrap {{ direction: {page_dir} !important; text-align: {align_css} !important; }}
        .kpi-card {{
            background: #E3F4FB !important; border: 1px solid #B7D7EA !important;
            page-break-inside: avoid !important; break-inside: avoid !important;
        }}
        .kpi-container, .print-chart-block, .exec-insight-card,
        .js-plotly-plot, .plot-container, .svg-container,
        [data-testid="stPlotlyChart"], [data-testid="stHorizontalBlock"] {{
            page-break-inside: avoid !important; break-inside: avoid-page !important;
            overflow: visible !important;
        }}
        [data-testid="stPlotlyChart"], .js-plotly-plot, .plot-container, .svg-container {{
            max-height: none !important; height: auto !important;
        }}
        .exec-insight-card {{ min-height: auto !important; padding: 10px 12px !important; box-shadow: none !important; }}
        h2, h3, h4 {{ margin: 4px 0 6px 0 !important; page-break-after: avoid !important; }}
        * {{ -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
    }}
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="analytics-wrap">', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="analytics-toolbar">
        <h2 class="analytics-title">{t["analytics_title"]}</h2>
        <div class="analytics-date">{t["issue_date"]}: {issue_date_val}</div>
    </div>
    """, unsafe_allow_html=True)

    col_scope, col_print = st.columns([2.4, 1.1])
    with col_scope:
        scope_labels = [t["analytics_all"]] + analytics_projects
        current_label = t["analytics_all"] if st.session_state.analytics_scope == "__all__" else st.session_state.analytics_scope
        if current_label not in scope_labels:
            current_label = t["analytics_all"]
        picked_scope = st.selectbox(t["analytics_scope"], scope_labels, index=scope_labels.index(current_label))
        st.session_state.analytics_scope = "__all__" if picked_scope == t["analytics_all"] else picked_scope
    with col_print:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.markdown('<div class="no-print">', unsafe_allow_html=True)
        st.components.v1.html(f"""
        <button onclick="window.parent.print()" style="background: linear-gradient(135deg, #2C3E50 0%, #1A2834 100%); color:white; padding:11px 16px; border:1px solid #E8B423; border-radius:10px; cursor:pointer; font-weight:800; font-size:13px; width:100%;">
            {t['print_report']}
        </button>
        """, height=50)
        st.markdown('</div>', unsafe_allow_html=True)

    analytics_label = t["analytics_all"] if st.session_state.analytics_scope == "__all__" else st.session_state.analytics_scope
    if st.session_state.analytics_scope == "__all__":
        analytics_invoices = [
            item for item in st.session_state.invoices_data
            if (not item.get("delete", False)) and (item.get("project") in analytics_projects)
        ]
    else:
        analytics_invoices = [
            item for item in st.session_state.invoices_data
            if (not item.get("delete", False)) and (item.get("project") == st.session_state.analytics_scope)
        ]

    a_total_in = sum(item.get("amount", 0) or 0 for item in analytics_invoices if item.get("doc_type") == "وارد")
    a_total_out = sum(item.get("amount", 0) or 0 for item in analytics_invoices if item.get("doc_type") == "منصرف")
    a_balance = a_total_in - a_total_out
    a_burn_rate = (a_total_out / a_total_in * 100) if a_total_in > 0 else 0

    st.markdown('<div class="print-report">', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="print-only-header">
        <div style="display:flex; justify-content:space-between; align-items:center; direction:{page_dir}; text-align:{align_css};">
            <div>
                <h1 style="margin:0; color:#2C3E50; font-size:26px; font-weight:900;">اليسر للهندسة والمقاولات</h1>
                <h3 style="margin:4px 0 0 0; color:#64748B; font-size:16px;">{t["analytics_title"]}</h3>
            </div>
            <div>
                <div style="font-size:15px; font-weight:800; color:#2C3E50;">{analytics_label}</div>
                <div style="font-size:13px; color:#64748B; margin-top:4px;">{t["issue_date"]}: {issue_date_val}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="kpi-container" style='display: flex; gap: 15px; margin: 8px 0 20px 0; direction:{page_dir};'>
        <div class="kpi-card"><h5>{t["metric_in"]}</h5><h3>{a_total_in:,.2f} {t["curr"]}</h3></div>
        <div class="kpi-card"><h5>{t["metric_out"]}</h5><h3>{a_total_out:,.2f} {t["curr"]}</h3></div>
        <div class="kpi-card"><h5>{t["metric_bal"]}</h5><h3>{a_balance:,.2f} {t["curr"]}</h3></div>
        <div class="kpi-card"><h5>{t["metric_burn"]}</h5><h3>{a_burn_rate:.1f}%</h3></div>
    </div>
    """, unsafe_allow_html=True)

    if a_total_out > 0 or a_total_in > 0:
        df_all = pd.DataFrame(analytics_invoices)
        df_out = df_all[df_all["doc_type"] == "منصرف"] if not df_all.empty and "doc_type" in df_all.columns else pd.DataFrame()
        chart_legend = dict(x=1, xanchor="right") if is_rtl else dict(x=0, xanchor="left")

        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.markdown(f"<div class='print-chart-block'><h3 style='text-align:{align_css};'>{t['chart_cat']}</h3></div>", unsafe_allow_html=True)
            if not df_out.empty:
                cat_sum = df_out.groupby("category")["amount"].sum().reset_index()
                fig_pie = px.pie(cat_sum, values='amount', names='category', hole=0.45, color_discrete_sequence=px.colors.qualitative.Bold)
                fig_pie.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor='rgba(0,0,0,0)', font=dict(size=12, color=chart_font), legend=chart_legend)
                st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': False})

        with col_chart2:
            st.markdown(f"<div class='print-chart-block'><h3 style='text-align:{align_css};'>{t['chart_pay']}</h3></div>", unsafe_allow_html=True)
            if not df_out.empty:
                pay_sum = df_out.groupby("payment_method")["amount"].sum().reset_index()
                fig_bar = px.bar(pay_sum, x='payment_method', y='amount', color='payment_method', text='amount', color_discrete_sequence=px.colors.qualitative.Safe)
                fig_bar.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                fig_bar.update_layout(height=320, margin=dict(t=10, b=40, l=10, r=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, font=dict(size=11, color=chart_font))
                if is_rtl:
                    fig_bar.update_xaxes(autorange="reversed", title_text="")
                    fig_bar.update_yaxes(side="right", title_text="")
                else:
                    fig_bar.update_xaxes(title_text="")
                    fig_bar.update_yaxes(title_text="")
                st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})

        trend_df = df_all.copy()
        if "invoice_date" in trend_df.columns:
            trend_df["invoice_date"] = pd.to_datetime(trend_df["invoice_date"], errors="coerce")
            trend_df = trend_df.dropna(subset=["invoice_date"])
        else:
            trend_df = pd.DataFrame()
        if not trend_df.empty and "amount" in trend_df.columns:
            trend_df["month"] = trend_df["invoice_date"].dt.to_period("M").dt.to_timestamp()
            monthly = trend_df.groupby(["month", "doc_type"], dropna=False)["amount"].sum().reset_index()
            pivot = monthly.pivot_table(index="month", columns="doc_type", values="amount", aggfunc="sum").fillna(0)
            if "وارد" not in pivot.columns:
                pivot["وارد"] = 0
            if "منصرف" not in pivot.columns:
                pivot["منصرف"] = 0
            pivot = pivot.sort_index()
            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(
                x=pivot.index, y=pivot["وارد"], name=t["trend_in"],
                mode="lines+markers", line=dict(color="#10B981", width=3), marker=dict(size=7)
            ))
            fig_trend.add_trace(go.Scatter(
                x=pivot.index, y=pivot["منصرف"], name=t["trend_out"],
                mode="lines+markers", line=dict(color="#EF4444", width=3), marker=dict(size=7)
            ))
            fig_trend.update_layout(
                height=280, margin=dict(t=16, b=16, l=16, r=16),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(size=12, color=chart_font),
                legend=dict(orientation="h", y=1.12, x=1 if is_rtl else 0, xanchor="right" if is_rtl else "left"),
                hovermode="x unified",
                xaxis=dict(title="", showgrid=True, gridcolor="rgba(44,62,80,0.08)", tickformat="%Y-%m"),
                yaxis=dict(title="", showgrid=True, gridcolor="rgba(44,62,80,0.08)", side="right" if is_rtl else "left", tickformat=",.0f")
            )
            st.markdown(f"<div class='print-chart-block'><h3 style='text-align:{align_css};'>{t['chart_trend']}</h3></div>", unsafe_allow_html=True)
            st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})

        top_cat = "غير محدد" if is_rtl else "Unspecified"
        top_cat_amt = 0.0
        top_cat_pct = 0.0
        if not df_out.empty:
            cat_grouped = df_out.groupby("category")["amount"].sum().sort_values(ascending=False)
            if not cat_grouped.empty:
                top_cat = cat_grouped.index[0]
                top_cat_amt = cat_grouped.iloc[0]
                top_cat_pct = (top_cat_amt / a_total_out * 100) if a_total_out > 0 else 0

        cash_amt = df_out[df_out["payment_method"] == "نقدي"]["amount"].sum() if not df_out.empty else 0
        cash_pct = (cash_amt / a_total_out * 100) if a_total_out > 0 else 0

        if is_rtl:
            cost_body = f"يمثل بند <b>({top_cat})</b> أعلى معدل استنزاف نقدي في نطاق التحليل بإجمالي <b>{top_cat_amt:,.2f} {t['curr']}</b> وبنسبة <b>{top_cat_pct:.1f}%</b> من إجمالي المنصرف."
            cost_rec = "مراجعة أوامر التوريد ومطابقة المستخلصات الدورية للبند للتحقق من كفاءة التسعير والكميات."
            cash_body = f"تبلغ نسبة السداد النقدي المباشر <b>{cash_pct:.1f}%</b> بإجمالي <b>{cash_amt:,.2f} {t['curr']}</b>."
            cash_rec = "الاعتماد المستمر على الشيكات والتحويلات البنكية الموثقة لإحكام الرقابة وتأكيد التسليم المباشر للموردين والمقاولين."
        else:
            cost_body = f"The item <b>({top_cat})</b> is the highest cash drain in this scope, totaling <b>{top_cat_amt:,.2f} {t['curr']}</b> ({top_cat_pct:.1f}% of expenses)."
            cost_rec = "Review supply orders and periodic certificates for this item to verify pricing and quantity efficiency."
            cash_body = f"Direct cash payments represent <b>{cash_pct:.1f}%</b>, totaling <b>{cash_amt:,.2f} {t['curr']}</b>."
            cash_rec = "Continue using documented cheques and bank transfers to tighten control and confirm direct settlement with vendors."

        st.markdown(f"<h3 class='print-keep' style='text-align:{align_css}; margin-top:12px;'>{t['insights_title']}</h3>", unsafe_allow_html=True)
        ins_col1, ins_col2 = st.columns(2)
        with ins_col1:
            st.markdown(f"""
            <div class="exec-insight-card">
                <div class="exec-insight-kicker">{t["insight_kicker"]}</div>
                <div class="exec-insight-title">🎯 {t["insight_cost_title"]}</div>
                <div class="exec-insight-body">{cost_body}</div>
                <div class="exec-insight-action"><b>{t["insight_rec_label"]}:</b> {cost_rec}</div>
            </div>
            """, unsafe_allow_html=True)
        with ins_col2:
            st.markdown(f"""
            <div class="exec-insight-card">
                <div class="exec-insight-kicker">{t["insight_kicker"]}</div>
                <div class="exec-insight-title">⚡ {t["insight_cash_title"]}</div>
                <div class="exec-insight-body">{cash_body}</div>
                <div class="exec-insight-action"><b>{t["insight_rec_label"]}:</b> {cash_rec}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    if is_company_admin or is_ceo or is_super_admin:
        st.markdown('<div class="audit-section no-print">', unsafe_allow_html=True)
        st.divider()
        st.markdown(f"<h3 style='text-align:{align_css};'>{t['audit_title']}</h3>", unsafe_allow_html=True)
        audit_logs = load_audit_log()
        if audit_logs:
            rows_html = []
            for log in audit_logs:
                ts = str(log.get("timestamp", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                user = str(log.get("user_name", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                action = str(log.get("action", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                details = str(log.get("details", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                rows_html.append(f"<tr><td>{ts}</td><td>{user}</td><td>{action}</td><td>{details}</td></tr>")
            st.markdown(f"""
            <div class="audit-wrap">
                <table class="audit-table">
                    <thead>
                        <tr>
                            <th>{t["audit_col_time"]}</th>
                            <th>{t["audit_col_user"]}</th>
                            <th>{t["audit_col_action"]}</th>
                            <th>{t["audit_col_details"]}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows_html)}
                    </tbody>
                </table>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info(t["no_audit"])
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════
# ─── تبويب سياسات وضوابط النظام المحدث (In-App Tuning & Prompt Controls) ───
# ═════════════════════════════════════════════════════════════════════════
elif st.session_state.active_tab == "memory" and can_access_system_policies:
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
        <div class="section-banner">
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
st.markdown(f"""
<style>
.footer-container {{
    margin-top: 18px;
    padding: 8px 4px 14px 4px;
    text-align: left !important;
    direction: ltr !important;
}}
.brand-footer-text {{
    display: inline-block;
    font-size: 13px;
    font-weight: 700;
    color: var(--text-muted, #64748B);
}}
</style>
<div class="footer-container no-print">
    <span class="brand-footer-text">{t["footer_brand"]}</span>
</div>
""", unsafe_allow_html=True)