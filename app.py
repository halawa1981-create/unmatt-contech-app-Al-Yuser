import streamlit as st
import pandas as pd
import json
import html
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
import uuid

from client_invoices_module import render_client_invoices_tab
from executive_analytics_service import get_project_executive_summary

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

def analyze_invoice_with_gemini(image, prompt_text, api_key, current_project="", module_type="custody"):
    """
    محرك استخراج مالي متقدم مدعوم بالتعلم السياقي السريع (Few-Shot In-Context Learning)
    يقرأ ديناميكياً من مستودع العينات المعتمدة لنفس نوع الوحدة لرفع دقة القراءة والتحقق.
    """
    img_str = optimize_image_for_upload(image, max_size=(1800, 1800), quality=88)
    clean_key = str(api_key).strip().replace('"', '').replace("'", '').split("\n")[0].split(",")[0].strip()

    t_cfg = load_tuning_config()
    schemas = t_cfg.get("schemas", {})

    # تحديد السياسات وهيكل المخرجات حسب الوحدة
    if module_type == "subcontractor":
        sys_inst = t_cfg.get("inst_subcontractor", "أنت مراجع عقود ومستخلصات مقاولي باطن. مهمتك استخراج نسب الإنجاز وحصر الأعمال والمستحقات بدقة بصيغة JSON.")
        active_schema = schemas.get("subcontractor", {
            "subcontractor_name": "اسم مقاول الباطن",
            "ipc_no": "رقم المستخلص",
            "current_work_value": 0.0,
            "retention_deduction": 0.0,
            "advance_recovery": 0.0,
            "net_payable": 0.0,
            "statement_period": "فترة الأعمال"
        })
    elif module_type == "client":
        sys_inst = t_cfg.get("inst_client", "أنت خبير تدقيق مستخلصات عملاء ومقايسات. مهمتك استخراج قيمة الأعمال المنجزة والضرائب والاستقطاعات بصيغة JSON.")
        active_schema = schemas.get("client", {
            "client_name": "اسم المالك",
            "invoice_no": "رقم المستخلص",
            "work_executed_amount": 0.0,
            "retention_amount": 0.0,
            "advance_payment_deduction": 0.0,
            "vat_amount": 0.0,
            "net_payable": 0.0,
            "approval_status": "معتمد"
        })
    else:
        sys_inst = t_cfg.get("inst_custody", t_cfg.get("system_instruction", "أنت مراجع مالي معتمد. مهمتك استخراج ومطابقة بيانات إيصالات وفواتير العهد والمصروفات بدقة ومطابقة التفقيط بالأرقام بصيغة JSON."))
        active_schema = schemas.get("custody", t_cfg.get("json_schema", {
            "invoice_no": "رقم الفاتورة أو المستند",
            "invoice_date": "YYYY-MM-DD",
            "amount": 0.0,
            "vat": 0.0,
            "description": "البيان أو اسم المستفيد",
            "category": "موردين / مواد / مقاولين / عمالة / نثريات",
            "payment_method": "نقدي / شيك / تحويل",
            "remark": "ملاحظات"
        }))

    # بناء سياق التعلم السريع (Few-Shot Examples) من مستودع العينات المعتمدة
    approved_ds = load_approved_dataset()
    matching_samples = [
        s for s in approved_ds
        if s.get("module_type", "custody") == module_type and isinstance(s.get("ground_truth"), dict)
    ]

    few_shot_context = ""
    if matching_samples:
        few_shot_context = "\n=== نماذج وأمثلة قياسية معتمدة سابقاً من إدارة المشروع (للاسترشاد بطريقة الاستخراج فقط دون نسخ أرقامها) ===\n"
        # أخذ أحدث 3 عينات معتمدة لضمان بقاء حجم السياق مناسباً
        for idx, sample in enumerate(matching_samples[:3], start=1):
            gt_example = json.dumps(sample.get("ground_truth"), ensure_ascii=False)
            few_shot_context += f"مثال معتمد ({idx}) - اسم المستند: {sample.get('input_doc', 'وثيقة')}\nالمخرجات المعتمدة المطابقة: {gt_example}\n---\n"

    # جلب قاموس المصطلحات والموردين
    dict_text = str(st.session_state.get("system_dictionary", "") or "").strip()
    if not dict_text and os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                dict_text = f.read().strip()
        except Exception:
            dict_text = ""

    dictionary_context = f"\nقواعد التصنيف وقاموس الأسماء المعتمدة بالمشروع:\n{dict_text}\n" if dict_text else ""
    schema_json = json.dumps(active_schema, ensure_ascii=False, indent=2)

    active_rules = f"""
{sys_inst}
{dictionary_context}
{few_shot_context}
القواعد الإلزامية لاستخراج وتدقيق الوثيقة الحالية:
1. اقرأ البيانات حصرياً من واقع صورة المستند المرفقة حالياً، ولا تفترض أو تنسخ أي أرقام من الأمثلة الاسترشادية أو السجلات السابقة.
2. طابق المبالغ الرقمية مع التفقيط المكتوب بالحروف بدقة تامة واعتمد القيمة كـ float.
3. التزم حرفياً بهيكل الحقول التالي وأعد كائن JSON مفرد ومباشر {{ }} فقط بدون نصوص تمهيدية:
{schema_json}
"""
    final_prompt = prompt_text + "\n" + active_rules
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": final_prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": img_str}}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0}
    }

    candidate_models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash"
    ]

    last_error_details = []
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={clean_key}"
        for attempt in range(2):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=45)
                if response.status_code == 200:
                    res_json = response.json()
                    candidates = res_json.get('candidates', [])
                    if not candidates:
                        continue
                    raw_text = candidates[0]['content']['parts'][0]['text']
                    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                    parsed = json.loads(match.group(0)) if match else {}
                    if isinstance(parsed, list):
                        parsed = parsed[0] if parsed else {}
                    if not isinstance(parsed, dict):
                        parsed = {}

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
    """
    المستشار المالي الشامل للمشروع:
    يقرأ من محرك الرقابة المالية التنفيذي الموسع، عقود مقاولي الباطن،
    مستخلصات العميل، وحركات العهد والمصروفات.
    """
    clean_key = str(api_key).strip().replace('"', '').replace("'", '').split("\n")[0].split(",")[0].strip()
    target_proj = str(project_name or "").strip()

    exec_summary = {}
    try:
        from executive_analytics_service import get_project_executive_summary
        exec_summary = get_project_executive_summary(target_proj) or {}
    except Exception:
        exec_summary = {}

    project_records = []
    for inv in invoices_list or []:
        is_del = str(inv.get("delete", False)).strip().lower() in ["true", "1", "نعم"]
        if is_del:
            continue
        if str(inv.get("project", "")).strip() != target_proj:
            continue
        project_records.append(inv)

    custody_lines = []
    for inv in project_records[-30:]:
        try:
            amt = float(inv.get("amount", 0) or 0)
        except Exception:
            amt = 0.0
        custody_lines.append(
            f"- [عهدة/فاتورة] سريال: {inv.get('serial_no', '')} | مستند: {inv.get('invoice_no', '')} | "
            f"التاريخ: {inv.get('invoice_date', '')} | البيان: {inv.get('description', '')} | "
            f"المبلغ: {amt:,.2f} | النوع: {inv.get('doc_type', '')} | "
            f"التصنيف: {inv.get('category', '')} | طريقة السداد: {inv.get('payment_method', '')}"
        )
    custody_text = "\n".join(custody_lines) if custody_lines else "لا توجد حركات عهد مسجلة مؤخراً."

    curr = st.session_state.get("project_currency", "ج.م")
    summary_block = f"""
=== الموقف المالي التنفيذي لمشروع ({target_proj}) ===
العملة المعتمدة: {curr}
1. التدفقات النقدية المباشرة:
   - إجمالي المقبوضات المحصلة من العميل (Cash In): {float(exec_summary.get('total_cash_in', 0.0) or 0.0):,.2f} {curr}
   - إجمالي المدفوعات التشغيلية (Cash Out): {float(exec_summary.get('total_cash_out', 0.0) or 0.0):,.2f} {curr}
   - صافي السيولة النقدية المحققة (Net Cash Flow): {float(exec_summary.get('net_cash_flow', 0.0) or 0.0):,.2f} {curr}
   - حالة السيولة: {exec_summary.get('financial_health_status', 'غير محدد')}

2. التزامات ونفقات مقاولي الباطن والموردين:
   - إجمالي قيم عقود مقاولي الباطن: {float(exec_summary.get('subcontracts_total_value', 0.0) or 0.0):,.2f} {curr}
   - الأعمال المعتمدة لمقاولي الباطن: {float(exec_summary.get('subcontractors_approved_work', 0.0) or 0.0):,.2f} {curr}
   - المسدد الفعلي لمقاولي الباطن: {float(exec_summary.get('subcontractors_paid', 0.0) or 0.0):,.2f} {curr}
   - المتبقي مستحق السداد لمقاولي الباطن: {float(exec_summary.get('subcontractors_balance_due', 0.0) or 0.0):,.2f} {curr}
   - محتجز ضمان أعمال مقاولي الباطن (Retention Payable): {float(exec_summary.get('subcontractors_retention', 0.0) or 0.0):,.2f} {curr}
   - المسدد لموردي المواد والخامات: {float(exec_summary.get('material_suppliers_paid', 0.0) or 0.0):,.2f} {curr}
   - مصاريف الموقع والنثريات: {float(exec_summary.get('general_site_expenses', 0.0) or 0.0):,.2f} {curr}

3. موقف مستخلصات العميل والضمانات:
   - إجمالي قيمة الأعمال المنفذة للعميل: {float(exec_summary.get('client_total_executed', 0.0) or 0.0):,.2f} {curr}
   - مستخلصات قيد الاعتماد والمراجعة لدى الاستشاري (Pending): {float(exec_summary.get('client_pending_approval', 0.0) or 0.0):,.2f} {curr}
   - محتجز ضمان الأعمال لدى المالك (Retention Receivable): {float(exec_summary.get('client_retention_receivable', 0.0) or 0.0):,.2f} {curr}
   - رصيد غير محصل طرف العميل: {float(exec_summary.get('client_uncollected_balance', 0.0) or 0.0):,.2f} {curr}

4. دورة الدفعة المقدمة (Advance Payment):
   - الدفعة المقدمة المستلمة: {float(exec_summary.get('advance_payment_received', 0.0) or 0.0):,.2f} {curr}
   - ما تم استقطاعه واستهلاكه منها: {float(exec_summary.get('advance_payment_recovered', 0.0) or 0.0):,.2f} {curr}
   - المتبقي كالتزام بذمة المقاول: {float(exec_summary.get('advance_payment_balance', 0.0) or 0.0):,.2f} {curr}

5. مؤشرات توقعات السيولة القادمة:
   - سيولة متوقعة قادمة (مستخلصات تحت الاعتماد): {float(exec_summary.get('short_term_forecast_inflow', 0.0) or 0.0):,.2f} {curr}
   - التزامات قريبة مستحقة للباطن: {float(exec_summary.get('short_term_forecast_outflow', 0.0) or 0.0):,.2f} {curr}
   - صافي التدفق المتوقع: {float(exec_summary.get('short_term_forecast_net', 0.0) or 0.0):,.2f} {curr}
"""

    rules_text = json.dumps(rules_dict, ensure_ascii=False) if isinstance(rules_dict, dict) else str(rules_dict or "").strip()

    system_prompt = (
        f"أنت 'المساعد المالي' المعتمد لمشروع ({target_proj}). "
        f"مهمتك تقديم تحليلات وإجابات رقابية دقيقة ومحايدة باللغة العربية بناءً على البيانات المالية المرفقة أدناه فقط. "
        f"أنت مطلع بالكامل على: موقف مستخلصات العميل، عقود ومستخلصات مقاولي الباطن، فواتير الموردين، حركة العهد، الدفعة المقدمة، والمحتجزات. "
        f"قواعد الإجابة الإلزامية:\n"
        f"1. اذكر دائماً الأرقام والمبالغ مع العملة ({curr}) بدقة كما هي مسجلة.\n"
        f"2. كن مباشراً، مهنياً، ومختصراً دون مقدمات إنشائية.\n"
        f"3. إذا سُئلت عن تفاصيل غير واردة في البيانات، أجب بصراحة أنها غير مدونة في السجلات المعتمدة ولا تفترض أي مبالغ."
    )

    user_prompt = (
        f"{summary_block}\n\n"
        f"=== عينات من أحدث حركات الفواتير والعهد ===\n{custody_text}\n\n"
        f"قواعد وتصنيفات المشروع:\n{rules_text}\n\n"
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
        "generationConfig": {"temperature": 0.15}
    }

    last_error_details = []
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={clean_key}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=40)
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

CURRENCY_AR = ["ج.م", "ر.س", "$", "د.إ"]
CURRENCY_EN = ["EGP", "SAR", "USD", "AED"]
CURRENCY_TO_EN = dict(zip(CURRENCY_AR, CURRENCY_EN))
CURRENCY_TO_AR = dict(zip(CURRENCY_EN, CURRENCY_AR))


def currency_options_for_lang(lang):
    return list(CURRENCY_AR) if lang == "العربية" else list(CURRENCY_EN)


def normalize_project_currency(value, lang):
    raw = str(value or "").strip()
    if lang == "العربية":
        if raw in CURRENCY_AR:
            return raw
        return CURRENCY_TO_AR.get(raw, "ج.م")
    if raw in CURRENCY_EN:
        return raw
    return CURRENCY_TO_EN.get(raw, "EGP")


# ─── التهيئة الآمنة لجميع متغيرات الجلسة ───
ensure_hr_admin_data_files()
if "system_lang" not in st.session_state: st.session_state.system_lang = "العربية"
if "system_theme" not in st.session_state: st.session_state.system_theme = "Light"
if "project_currency" not in st.session_state:
    st.session_state.project_currency = "ج.م" if st.session_state.get("system_lang") == "العربية" else "EGP"
else:
    st.session_state.project_currency = normalize_project_currency(
        st.session_state.project_currency, st.session_state.get("system_lang")
    )
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
if "login_lang" not in st.session_state: st.session_state.login_lang = "en"

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
    _ll = st.session_state.login_lang
    _L = {
        "en": {
            "top_badge": "CONTECH VISUAL IDENTITY",
            "top_experience": "Un-matt ConTech — Unified Login Experience",
            "brand_sub": "Enterprise Solutions • Construction Technology",
            "product_label": "PROJECT FINANCIAL CONTROL",
            "product_sub": "Invoice Management & Reconciliation",
            "hero_lead": "Turn Project Transactions into",
            "hero_highlight": "Controlled Financial Intelligence",
            "p1_tag": "EXTRACTION ENGINE", "p1_title": "Smart Data Extraction",
            "p1_desc": "Automated OCR parsing & dual textual verification.",
            "p2_tag": "AUTO COST CODING", "p2_title": "Self Aggregation & Classification",
            "p2_desc": "Dynamic vendor mapping into controlled BOQ ledger.",
            "p3_tag": "EXECUTIVE INTELLIGENCE", "p3_title": "Expenses Analysis & Actionable Insights",
            "p3_desc": "Board-ready A3 KPIs, burn rate, and cost control.",
            "welcome": "Welcome back", "welcome_sub": "Sign in to your Un-matt workspace",
            "email": "Email Address", "password": "Password",
            "remember": "Remember me", "forgot": "Forgot password?",
            "signin": "Sign in →", "err": "Invalid email or password.",
        },
        "ar": {
            "top_badge": "هوية كونتك البصرية",
            "top_experience": "أنمات كونتك — تجربة دخول موحّدة",
            "brand_sub": "حلول المؤسسات • تقنيات الإنشاء",
            "product_label": "الرقابة المالية للمشاريع",
            "product_sub": "إدارة الفواتير والمطابقة المالية",
            "hero_lead": "حوّل معاملات المشروع إلى",
            "hero_highlight": "ذكاء مالي منضبط",
            "p1_tag": "محرك الاستخراج", "p1_title": "استخراج البيانات الذكي",
            "p1_desc": "تحليل ضوئي آلي وتحقق نصي مزدوج.",
            "p2_tag": "ترميز التكاليف الآلي", "p2_title": "التصنيف والتجميع الذاتي",
            "p2_desc": "ربط الموردين بدفتر كميات منضبط.",
            "p3_tag": "الذكاء التنفيذي", "p3_title": "تحليل المصروفات ورؤى قابلة للتنفيذ",
            "p3_desc": "مؤشرات جاهزة للإدارة ومعدل الإنفاق والرقابة.",
            "welcome": "مرحباً بعودتك", "welcome_sub": "سجّل الدخول إلى مساحة عمل أنمات",
            "email": "البريد الإلكتروني", "password": "كلمة المرور",
            "remember": "تذكرني", "forgot": "نسيت كلمة المرور؟",
            "signin": "تسجيل الدخول ←", "err": "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
        },
    }[_ll]

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800;900&display=swap');
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
    .stApp button[kind="primary"],
    .stApp [data-testid="stBaseButton-primary"],
    .stApp button[data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%) !important;
        background-color: #0284C7 !important;
        border: none !important;
        border-radius: 10px !important; font-weight: 800 !important; font-size: 16px !important;
        padding: 13px !important; box-shadow: 0 10px 25px -5px rgba(14, 165, 233, 0.5) !important;
        color: #FFFFFF !important;
    }
    .stApp button[kind="primary"] p,
    .stApp [data-testid="stBaseButton-primary"] p { color: #FFFFFF !important; }
    </style>
    """, unsafe_allow_html=True)

    hdr_brand, hdr_lang = st.columns([5.2, 1.35])
    with hdr_brand:
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:10px;color:#64748B;font-size:13px;margin-bottom:8px;padding:0 8px;">
            <span style="background:#1E293B;color:#38BDF8;padding:4px 10px;border-radius:6px;font-weight:800;font-size:11.5px;">{_L["top_badge"]}</span>
            <span style="color:#94A3B8;font-weight:700;">{_L["top_experience"]}</span></div>""",
            unsafe_allow_html=True,
        )
    with hdr_lang:
        st.markdown('<div class="login-lang-row">', unsafe_allow_html=True)
        lang_en_col, lang_ar_col = st.columns(2)
        with lang_en_col:
            if st.button("EN", use_container_width=True, key="login_lang_en"):
                st.session_state.login_lang = "en"
                st.rerun()
        with lang_ar_col:
            if st.button("عربي", use_container_width=True, key="login_lang_ar"):
                st.session_state.login_lang = "ar"
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    col_brand, col_auth = st.columns([1.5, 0.95], gap="small")
    with col_brand:
        left_panel_html = (
            "<div style='background:radial-gradient(circle at 15% 15%, #132742 0%, #08111E 65%, #050B14 100%);border:1px solid rgba(255,255,255,0.08);border-radius:24px 0 0 24px;padding:50px 52px;min-height:720px;display:flex;flex-direction:column;justify-content:space-between;'>"
            "<div>"
            "<div style='font-size:28px;font-weight:900;color:#FFFFFF;letter-spacing:0.5px;'>Un-matt <span style='color:#38BDF8;'>ConTech</span></div>"
            "<div style='font-size:11.5px;font-weight:700;color:#94A3B8;letter-spacing:0.15em;text-transform:uppercase;margin-top:4px;'>" + _L["brand_sub"] + "</div>"
            "<div style='display:inline-flex;flex-direction:column;align-items:flex-start;gap:4px;background:rgba(14,165,233,0.12);border:1px solid rgba(56,189,248,0.35);padding:8px 14px;border-radius:8px;color:#E0F2FE;margin:24px 0 20px 0;'>"
            "<div style='display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;'>"
            "<span style='width:8px;height:8px;border-radius:50%;background:#38BDF8;box-shadow:0 0 10px #38BDF8;'></span>" + _L["product_label"] + "</div>"
            "<div style='font-size:10px;font-weight:600;letter-spacing:0.04em;color:#7DD3FC;padding-left:16px;text-transform:none;'>" + _L["product_sub"] + "</div></div>"
            "<h1 style='font-size:40px;font-weight:800;color:#FFFFFF;line-height:1.25;margin-bottom:25px;'>" + _L["hero_lead"] + "<br><span style='color:#38BDF8;'>" + _L["hero_highlight"] + "</span></h1>"
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
            "<div><div style='font-size:10px;font-weight:800;color:#FB923C;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;'>" + _L["p1_tag"] + "</div>"
            "<div style='color:#FFFFFF;font-weight:700;font-size:13.5px;margin-bottom:4px;'>" + _L["p1_title"] + "</div>"
            "<div style='color:#94A3B8;font-size:11.5px;line-height:1.4;'>" + _L["p1_desc"] + "</div></div></div>"
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
            "<div><div style='font-size:10px;font-weight:800;color:#34D399;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;'>" + _L["p2_tag"] + "</div>"
            "<div style='color:#FFFFFF;font-weight:700;font-size:13.5px;margin-bottom:4px;'>" + _L["p2_title"] + "</div>"
            "<div style='color:#94A3B8;font-size:11.5px;line-height:1.4;'>" + _L["p2_desc"] + "</div></div></div>"
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
            "<div><div style='font-size:10px;font-weight:800;color:#38BDF8;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;'>" + _L["p3_tag"] + "</div>"
            "<div style='color:#FFFFFF;font-weight:700;font-size:13.5px;margin-bottom:4px;'>" + _L["p3_title"] + "</div>"
            "<div style='color:#94A3B8;font-size:11.5px;line-height:1.4;'>" + _L["p3_desc"] + "</div></div></div>"
            "</div></div>"
        )
        st.markdown(left_panel_html, unsafe_allow_html=True)

    with col_auth:
        st.markdown(f"<h2>{_L['welcome']}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p class='sub-title'>{_L['welcome_sub']}</p>", unsafe_allow_html=True)
        
        login_email = st.text_input(_L["email"], value="", key="auth_email_field")
        login_password = st.text_input(_L["password"], type="password", value="", key="auth_password_field")

        opt_remember, opt_forgot = st.columns([1, 1])
        with opt_remember:
            st.checkbox(_L["remember"], value=True, key="auth_remember_me")
        with opt_forgot:
            st.markdown(f'<div style="text-align:right;padding-top:10px;"><a href="#" style="color:#0284C7 !important;font-weight:700;text-decoration:none;font-size:13px;">{_L["forgot"]}</a></div>', unsafe_allow_html=True)
        
        if st.button(_L["signin"], type="primary", use_container_width=True):
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
                st.error(_L["err"])
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
can_access_system_policies = (user_role == "Super Admin")
if (not can_access_system_policies) and st.session_state.get("active_tab") == "memory":
    st.session_state.active_tab = "records"
    st.session_state.memory_unlocked = False
    st.rerun()

is_rtl = (st.session_state.system_lang == "العربية")
dir_attr = "rtl" if is_rtl else "ltr"

# ─── تهيئة التنسيق والألوان الموحدة (Ocean Navy & Petrol Blue Palette) ───
PRIMARY_NAVY_START = "#0A2540"
PRIMARY_NAVY_END = "#005C8A"
PRIMARY_ACCENT_BLUE = "#0284C7"
PRIMARY_BORDER_BLUE = "#0369A1"
PRIMARY_NAVY_GRADIENT = f"linear-gradient(135deg, {PRIMARY_NAVY_START} 0%, {PRIMARY_NAVY_END} 100%)"

_DS_FONT = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700;800&display=swap');
html, body, .stApp, .stApp p, .stApp span, .stApp label, .stApp li,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp button, .stApp input, .stApp textarea, .stApp select,
.stApp table, .stApp td, .stApp th, .kpi-card, .kpi-card *,
[data-testid="stMarkdownContainer"], [data-testid="stSidebar"],
[data-testid="stDataFrame"], [data-baseweb="select"], [data-baseweb="input"] {
    font-family: 'IBM Plex Sans Arabic', sans-serif !important;
}
.kpi-card {
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
.kpi-card:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.06) !important;
}
"""
if st.session_state.system_theme == "Dark":
    st.markdown(f"""
    <style>
    {_DS_FONT}
    :root {{
        --bg-main: #061525; --bg-card: #0A2540; --bg-input: #071A2E; --border-subtle: #1B4B6B; --border-strong: #0369A1;
        --text-title: #F8FAFC; --text-body: #CBD5E1; --text-muted: #94A3B8;
        --brand-primary: {PRIMARY_ACCENT_BLUE}; --brand-navy: {PRIMARY_NAVY_START}; --brand-gold: {PRIMARY_ACCENT_BLUE};
        --brand-navy-end: {PRIMARY_NAVY_END}; --brand-border: {PRIMARY_BORDER_BLUE};
        --brand-gradient: {PRIMARY_NAVY_GRADIENT};
        --kpi-inflow-bg: rgba(6, 78, 59, 0.25); --kpi-inflow-border: #10B981; --kpi-inflow-text: #34D399;
        --kpi-outflow-bg: rgba(127, 29, 29, 0.25); --kpi-outflow-border: #EF4444; --kpi-outflow-text: #F87171;
        --kpi-card-bg: #0A2540; --kpi-card-border: #1B4B6B; --kpi-card-accent: {PRIMARY_ACCENT_BLUE}; --kpi-card-label: #F8FAFC; --kpi-card-value: #F8FAFC;
        --table-header-bg: {PRIMARY_NAVY_START}; --table-row-even: #0A2540; --table-row-odd: #071A2E; --table-row-hover: #0E3A5C; --table-border: #1B4B6B;
    }}
    .stApp {{ background-color: var(--bg-main) !important; color: var(--text-body) !important; direction: {dir_attr}; }}
    section[data-testid="stSidebar"] {{ background-color: #071A2E !important; border-left: 2px solid {PRIMARY_ACCENT_BLUE} !important; direction: {dir_attr}; }}
    button[kind="primary"] {{
        background: {PRIMARY_NAVY_GRADIENT} !important;
        border: 1px solid {PRIMARY_BORDER_BLUE} !important;
        color: #FFFFFF !important;
    }}
    .grid-header {{
        background: {PRIMARY_NAVY_GRADIENT} !important; color: #FFFFFF !important; font-weight: 900; font-size: 14px;
        padding: 12px 6px; border-radius: 0; text-align: center; border: none;
        border-bottom: 3px solid {PRIMARY_ACCENT_BLUE} !important; z-index: 40 !important;
    }}
    .grid-row-inbound {{ background-color: var(--kpi-inflow-bg) !important; color: var(--kpi-inflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-inflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    .grid-row-outbound {{ background-color: var(--kpi-outflow-bg) !important; color: var(--kpi-outflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-outflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    [data-testid="stFileUploader"] {{ background: var(--bg-input) !important; border: 1.5px dashed var(--border-strong) !important; border-radius: 12px; }}
    .kpi-card {{
        flex: 1; background: var(--kpi-card-bg) !important; border: 1px solid var(--kpi-card-border) !important;
        border-top: 3px solid var(--kpi-card-accent) !important; padding: 18px 14px; border-radius: 12px; text-align: center;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18);
    }}
    .kpi-card h5, .kpi-card h4 {{ color: var(--kpi-card-label) !important; margin: 0 !important; font-size: 17px !important; font-weight: 800 !important; text-align: center !important; }}
    .kpi-card h3, .kpi-card h2 {{ color: var(--kpi-card-value) !important; margin: 8px 0 0 0 !important; font-size: 30px !important; font-weight: 800 !important; text-align: center !important; }}
    .att-chip {{ display: inline-block; font-size: 12px; font-weight: 800; color: {PRIMARY_ACCENT_BLUE}; text-decoration: none; margin: 0 3px; }}
    .att-chip:hover {{ color: #38BDF8; }}
    .section-banner {{
        display: inline-flex; align-items: center;
        padding: 8px 18px; border-radius: 8px;
        font-size: 15px; font-weight: 800; margin-bottom: 14px;
        background: {PRIMARY_NAVY_GRADIENT}; color: #FFFFFF;
        width: fit-content; max-width: 100%;
        text-align: {"right" if is_rtl else "left"};
        direction: {dir_attr};
        border: none;
        border-right: 4px solid {PRIMARY_ACCENT_BLUE};
    }}
    .stApp h1, .stApp h2, .stApp h3 {{ text-align: {"right" if is_rtl else "left"} !important; }}
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <style>
    {_DS_FONT}
    :root {{
        --bg-main: #F4F8FB; --bg-card: #FFFFFF; --border-subtle: #D6E4EF; --border-strong: #A8C5D8;
        --text-title: {PRIMARY_NAVY_START}; --text-body: #334155; --text-muted: #64748B;
        --brand-primary: {PRIMARY_ACCENT_BLUE}; --brand-navy: {PRIMARY_NAVY_START}; --brand-gold: {PRIMARY_ACCENT_BLUE};
        --brand-navy-end: {PRIMARY_NAVY_END}; --brand-border: {PRIMARY_BORDER_BLUE};
        --brand-gradient: {PRIMARY_NAVY_GRADIENT};
        --kpi-inflow-bg: #F0FDF4; --kpi-inflow-border: #10B981; --kpi-inflow-text: #047857;
        --kpi-outflow-bg: #FEF2F2; --kpi-outflow-border: #EF4444; --kpi-outflow-text: #B91C1C;
        --kpi-card-bg: #FFFFFF; --kpi-card-border: #D6E4EF; --kpi-card-accent: {PRIMARY_ACCENT_BLUE}; --kpi-card-label: {PRIMARY_NAVY_START}; --kpi-card-value: {PRIMARY_NAVY_START};
        --table-header-bg: {PRIMARY_NAVY_START}; --table-row-even: #FFFFFF; --table-row-odd: #F4F8FB; --table-row-hover: #E8F3FA; --table-border: #D6E4EF;
    }}
    .stApp {{ background-color: var(--bg-main) !important; color: var(--text-body) !important; direction: {dir_attr}; }}
    section[data-testid="stSidebar"] {{ background-color: #EEF5FA !important; border-left: 2px solid {PRIMARY_ACCENT_BLUE} !important; direction: {dir_attr}; }}
    button[kind="primary"] {{
        background: {PRIMARY_NAVY_GRADIENT} !important;
        border: 1px solid {PRIMARY_BORDER_BLUE} !important;
        color: #FFFFFF !important;
    }}
    .grid-header {{
        background: {PRIMARY_NAVY_GRADIENT} !important; color: #FFFFFF !important; font-weight: 900; font-size: 14px;
        padding: 12px 6px; border-radius: 0; text-align: center; border: none;
        border-bottom: 3px solid {PRIMARY_ACCENT_BLUE} !important; z-index: 40 !important;
    }}
    .grid-row-inbound {{ background-color: var(--kpi-inflow-bg) !important; color: var(--kpi-inflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-inflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    .grid-row-outbound {{ background-color: var(--kpi-outflow-bg) !important; color: var(--kpi-outflow-text) !important; font-weight: 700; padding: 8px 4px; border-radius: 6px; border: 1px solid var(--kpi-outflow-border); text-align: center; margin-bottom: 4px; font-size: 13px; }}
    [data-testid="stFileUploader"] {{ background: var(--bg-card) !important; border: 1.5px dashed var(--border-strong) !important; border-radius: 12px; }}
    .kpi-card {{
        flex: 1; background: var(--kpi-card-bg) !important; border: 1px solid var(--kpi-card-border) !important;
        border-top: 3px solid var(--kpi-card-accent) !important; padding: 18px 14px; border-radius: 12px; text-align: center;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    }}
    .kpi-card h5, .kpi-card h4 {{ color: var(--kpi-card-label) !important; margin: 0 !important; font-size: 17px !important; font-weight: 800 !important; text-align: center !important; }}
    .kpi-card h3, .kpi-card h2 {{ color: var(--kpi-card-value) !important; margin: 8px 0 0 0 !important; font-size: 30px !important; font-weight: 800 !important; text-align: center !important; }}
    .att-chip {{ display: inline-block; font-size: 12px; font-weight: 800; color: {PRIMARY_ACCENT_BLUE}; text-decoration: none; margin: 0 3px; }}
    .att-chip:hover {{ color: {PRIMARY_BORDER_BLUE}; }}
    .section-banner {{
        display: inline-flex; align-items: center;
        padding: 8px 18px; border-radius: 8px;
        font-size: 15px; font-weight: 800; margin-bottom: 14px;
        background: {PRIMARY_NAVY_GRADIENT}; color: #FFFFFF;
        width: fit-content; max-width: 100%;
        text-align: {"right" if is_rtl else "left"};
        direction: {dir_attr};
        border: none;
        border-right: 4px solid {PRIMARY_ACCENT_BLUE};
    }}
    .stApp h1, .stApp h2, .stApp h3 {{ text-align: {"right" if is_rtl else "left"} !important; }}
    </style>
    """, unsafe_allow_html=True)

st.markdown(f"""
<style>
.section-banner {{
    display: inline-flex !important;
    align-items: center !important;
    width: auto !important;
    max-width: 100% !important;
    padding: 8px 18px !important;
    border-radius: 8px !important;
    font-size: 15px !important;
    font-weight: 800 !important;
    margin-bottom: 14px !important;
    background: {PRIMARY_NAVY_GRADIENT} !important;
    color: #FFFFFF !important;
    border: none !important;
    border-right: 4px solid {PRIMARY_ACCENT_BLUE} !important;
    box-sizing: border-box !important;
}}
div[data-testid="stMarkdownContainer"]:has(.section-banner) {{
    width: fit-content !important;
    max-width: 100% !important;
}}
div[data-testid="stMarkdownContainer"]:has(.section-banner) > div {{
    width: fit-content !important;
    max-width: 100% !important;
}}
.inv-table-marker {{ display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }}
.inv-table-head [data-testid="stHorizontalBlock"] {{
    background: {PRIMARY_NAVY_GRADIENT} !important;
    border-radius: 12px 12px 0 0 !important;
    padding: 4px 8px 2px 8px !important;
    margin-bottom: 0 !important;
}}
.inv-table-head [data-testid="column"] {{ background: transparent !important; }}
div[data-testid="stVerticalBlock"][style*="overflow"]:has(.inv-table-marker) {{
    max-height: 62vh !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    border: 1px solid #D6E4EF !important;
    border-top: none !important;
    border-radius: 0 0 12px 12px !important;
    padding: 6px 8px 10px 8px !important;
    margin-top: 0 !important;
}}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* حاوية شريط التبويبات كألسنة مجلدات */
.folder-tabs-wrapper {
    display: flex;
    align-items: flex-end;
    justify-content: flex-start;
    gap: 6px;
    border-bottom: 2px solid #005C8A;
    padding-bottom: 0px;
    margin-bottom: 20px;
    direction: rtl;
}
.folder-tab-anchor,
.invoice-drop-anchor {
    display: none !important;
}
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] .folder-tab-anchor),
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdownContainer"] .folder-tab-anchor) {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
/* زر التبويب */
div[data-testid="stHorizontalBlock"]:has(.folder-tab-anchor) {
    display: flex !important;
    align-items: flex-end !important;
    justify-content: flex-start !important;
    direction: rtl !important;
    border-bottom: 2px solid #005C8A !important;
    gap: 8px !important;
    margin-bottom: 20px !important;
    padding-bottom: 0px !important;
}
div[data-testid="stHorizontalBlock"]:has(.folder-tab-anchor) [data-testid="stColumn"] {
    width: auto !important;
    flex: 0 0 auto !important;
    min-width: max-content !important;
}
div[data-testid="stHorizontalBlock"]:has(.folder-tab-anchor) [data-testid="stColumn"]:last-child {
    flex: 1 1 auto !important;
    width: auto !important;
    min-width: 12px !important;
}
div[data-testid="stHorizontalBlock"]:has(.folder-tab-anchor) button {
    width: auto !important;
    white-space: nowrap !important;
    border-radius: 10px 10px 0 0 !important;
    border: 1px solid #CBD5E1 !important;
    border-bottom: none !important;
    padding: 8px 20px !important;
    font-weight: 800 !important;
    font-size: 14px !important;
    background: #F8FAFC !important;
    color: #475569 !important;
    box-shadow: none !important;
    margin-bottom: -2px !important;
    height: auto !important;
    min-height: 0 !important;
}
div[data-testid="stHorizontalBlock"]:has(.folder-tab-anchor) button p {
    white-space: nowrap !important;
    margin: 0 !important;
    line-height: 1.3 !important;
}
div[data-testid="stHorizontalBlock"]:has(.folder-tab-anchor) button * {
    font-weight: 800 !important;
    font-size: 14px !important;
    color: #475569 !important;
}
/* التبويب النشط المحدد */
div[data-testid="stHorizontalBlock"]:has(.folder-tab-anchor) button[kind="primary"],
div[data-testid="stHorizontalBlock"]:has(.folder-tab-anchor) button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #0A2540 0%, #005C8A 100%) !important;
    color: #FFFFFF !important;
    border: 2px solid #005C8A !important;
    border-bottom: 2px solid #005C8A !important;
}
div[data-testid="stHorizontalBlock"]:has(.folder-tab-anchor) button[kind="primary"] *,
div[data-testid="stHorizontalBlock"]:has(.folder-tab-anchor) button[data-testid="stBaseButton-primary"] * {
    color: #FFFFFF !important;
}
/* صندوق رفع المستندات — Ocean Navy، دون ضغط النص الداخلي */
div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) {
    align-items: flex-end !important;
}
.upload-paste-hint {
    margin-top: 8px;
    font-family: 'IBM Plex Sans Arabic', sans-serif;
    font-size: 12px;
    line-height: 1.5;
    font-weight: 600;
    color: #005C8A;
}
div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploader"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
    font-family: 'IBM Plex Sans Arabic', sans-serif !important;
}
div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploaderDropzone"] {
    background: #F4F8FB !important;
    border: 1.5px dashed #005C8A !important;
    border-radius: 12px !important;
    min-height: 96px !important;
    padding: 16px 18px !important;
    font-family: 'IBM Plex Sans Arabic', sans-serif !important;
}
div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"] {
    display: none !important;
    width: 0 !important;
    height: 0 !important;
    overflow: hidden !important;
    font-size: 0 !important;
}
div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploaderDropzone"] button {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    min-height: 0 !important;
    height: auto !important;
    padding: 0 !important;
    width: 100% !important;
}
div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploaderDropzone"] button p {
    font-size: 0 !important;
    line-height: 0 !important;
    margin: 0 !important;
    color: transparent !important;
}
div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploaderDropzone"] button p::after {
    content: "تصفح الملفات أو أفلتها هنا";
    display: block;
    font-family: 'IBM Plex Sans Arabic', sans-serif !important;
    font-size: 15px !important;
    line-height: 1.45 !important;
    font-weight: 800 !important;
    color: #0A2540 !important;
}
div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploaderDropzoneInstructions"],
div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploaderDropzoneInstructions"] * {
    font-size: 0 !important;
    line-height: 0 !important;
    color: transparent !important;
}
div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploaderDropzoneInstructions"]::after {
    content: "PDF أو صور  ·  حتى 200MB  ·  Ctrl+V للصق";
    display: block;
    margin-top: 6px;
    font-family: 'IBM Plex Sans Arabic', sans-serif !important;
    font-size: 12px !important;
    line-height: 1.45 !important;
    font-weight: 600 !important;
    color: #005C8A !important;
}
div[data-testid="stElementContainer"]:has(#invoice-paste-hook) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
</style>
""", unsafe_allow_html=True)

if not is_rtl:
    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploaderDropzone"] button p::after {
        content: "Browse files or drop them here";
    }
    div[data-testid="stHorizontalBlock"]:has(.invoice-drop-anchor) [data-testid="stFileUploaderDropzoneInstructions"]::after {
        content: "PDF or images · up to 200MB · Ctrl+V to paste";
    }
    </style>
    """, unsafe_allow_html=True)

if st.session_state.system_lang == "العربية":
    t = {
        "add_proj": "➕ إضافة مشروع جديد...", "proj_label": "المشروع الحالي:", "save_proj": "حفظ المشروع", "new_proj_name": "اسم المشروع الجديد:",
        "user_mgmt": "⚙️ إدارة المستخدمين", "logout": "🚪 خروج", "user_mgmt_title": "👥 لوحة التحكم في المستخدمين والصلاحيات",
        "tab_records": "📑 سجل ومطابقة الفواتير", "tab_custody_analytics": "📊 تحليلات ومؤشرات العهد والمصروفات", "tab_analytics": "📊 مؤشرات وتحليلات المشروع", "tab_memory": "⚙️ سياسات وضوابط النظام",
        "metric_in": "المقبوضات والتمويلات الواردة ⬇️", "metric_out": "المدفوعات والمصروفات التشغيلية ↗️", "metric_bal": "رصيد السيولة المتاح 💰", "metric_burn": "معدل استنزاف السيولة ⚡", "curr": "ج.م",
        "currency_label": "العملة:",
        "files_first": "⚠️ يرجى إرفاق أو سحب ملفات الفواتير أولاً.",
        "exec_status_surplus": "فائض نقدي متاح",
        "exec_status_deficit": "عجز سيولة يتطلب تمويلاً",
        "exec_status_balanced": "نقطة تعادل",
        "exec_kpi_in_title": "المقبوضات المحصلة",
        "exec_kpi_in_sub": "تحصيلات مستخلصات العميل",
        "exec_kpi_out_title": "إجمالي المدفوعات",
        "exec_kpi_out_sub": "مقاولو باطن وموردون ونثريات",
        "exec_kpi_net_title": "صافي السيولة النقدية",
        "exec_kpi_net_sub": "الفارق النقدي المحقق بالمشروع",
        "exec_coverage": "التغطية",
        "exec_kpi_pending_title": "مستخلصات قيد الاعتماد",
        "exec_kpi_pending_sub": "سيولة متوقعة تحت مراجعة الاستشاري",
        "exec_kpi_ret_title": "محتجز ضمان الأعمال",
        "exec_kpi_ret_sub": "مبالغ محتجزة طرف العميل لحين التسليم",
        "exec_kpi_adv_title": "رصيد الدفعة المقدمة المتبقي",
        "exec_kpi_adv_sub": "التزام مالي متبقٍ للاستهلاك",
        "exec_exposure_title": "تدقيق الالتزامات التعاقدية والمحتجزات ودورة الدفعة المقدمة",
        "exec_advance_cycle": "دورة الدفعة المقدمة",
        "exec_adv_received": "إجمالي الدفعة المستلمة",
        "exec_adv_recovered": "ما تم استقطاعه واستهلاكه",
        "exec_adv_remaining": "المتبقي كالتزام بذمة المقاول",
        "exec_ret_section": "محتجزات ضمان الأعمال",
        "exec_ret_client": "محتجز لدى العميل",
        "exec_ret_sub": "محتجز على مقاولي الباطن",
        "exec_ret_gap": "صافي فجوة الضمانات",
        "exec_outflow_section": "تفصيل التدفق الخارج الفعلي",
        "exec_paid_sub": "المسدد لمقاولي الباطن",
        "exec_paid_mat": "المسدد لموردي المواد والخامات",
        "exec_paid_site": "مصاريف موقع ونثريات",
        "exec_sub_due": "التزامات الباطن غير المسددة",
        "exec_chart_expense": "هيكل النفقات والمدفوعات الإنشائية",
        "exec_chart_forecast": "توقع السيولة القريب",
        "exec_no_expenses": "لا توجد حركات منصرف مسجلة للمشروع حتى الآن.",
        "exec_lbl_subs": "مقاولو الباطن",
        "exec_lbl_mat": "موردو المواد والخامات",
        "exec_lbl_site": "مصاريف موقع وعمالة",
        "exec_bar_in": "وارد متوقع من مستخلصات تحت الاعتماد",
        "exec_bar_out": "التزام مستحق لمقاولي باطن غير مسدد",
        "exec_bar_net": "صافي التدفق المتوقع",
        "exec_horizon": "الأسبوعين القادمين",
        "exec_print_company": "شركة اليسر للمقاولات العامة",
        "exec_print_title": "التقرير المالي التنفيذي الشامل وإدارة السيولة والمخاطر",
        "exec_print_project": "المشروع",
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
        "assistant_title": "💼 المساعد المالي", "assistant_info": "تحليل مباشر لبيانات المشروع:",
        "assistant_you": "أنت", "assistant_bot": "المساعد",
        "assistant_placeholder": "اكتب سؤالك هنا عن فواتير ومصروفات المشروع...",
        "assistant_send": "إرسال",
        "assistant_clear": "مسح المحادثة 🗑️", "assistant_spinner": "جاري استرجاع البيانات والتدقيق...",
        "analytics_title": "📊 تحليلات ومؤشرات حركة الفواتير والعهد", "print_report": "🖨️ طباعة التقرير التنفيذي المعتمد (A3)",
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
        "tab_records": "📑 Invoice Register & Reconciliation", "tab_custody_analytics": "📊 Custody & Expense Analytics", "tab_analytics": "📊 Project Analytics & KPIs", "tab_memory": "⚙️ System Policies & Controls",
        "metric_in": "Inbound Receipts & Funding ⬇️", "metric_out": "Operating Payments & Expenses ↗️", "metric_bal": "Available Liquidity Balance 💰", "metric_burn": "Liquidity Burn Rate ⚡", "curr": "EGP",
        "currency_label": "Currency:",
        "files_first": "⚠️ Please select files first.",
        "exec_status_surplus": "Cash surplus available",
        "exec_status_deficit": "Liquidity shortfall requiring funding",
        "exec_status_balanced": "Break-even position",
        "exec_kpi_in_title": "Collected receipts",
        "exec_kpi_in_sub": "Client certified invoice collections",
        "exec_kpi_out_title": "Total payments",
        "exec_kpi_out_sub": "Subcontractors, suppliers, and site costs",
        "exec_kpi_net_title": "Net cash position",
        "exec_kpi_net_sub": "Realized cash difference on the project",
        "exec_coverage": "Coverage",
        "exec_kpi_pending_title": "Invoices pending approval",
        "exec_kpi_pending_sub": "Expected inflow under consultant review",
        "exec_kpi_ret_title": "Retention receivable",
        "exec_kpi_ret_sub": "Amounts held by the client until handover",
        "exec_kpi_adv_title": "Remaining advance balance",
        "exec_kpi_adv_sub": "Outstanding recovery obligation",
        "exec_exposure_title": "Contractual exposure, retentions, and advance cycle",
        "exec_advance_cycle": "Advance payment cycle",
        "exec_adv_received": "Total advance received",
        "exec_adv_recovered": "Amount recovered to date",
        "exec_adv_remaining": "Remaining contractor obligation",
        "exec_ret_section": "Works retention",
        "exec_ret_client": "Retention held by the client",
        "exec_ret_sub": "Retention withheld from subcontractors",
        "exec_ret_gap": "Net retention gap",
        "exec_outflow_section": "Actual outflow breakdown",
        "exec_paid_sub": "Paid to subcontractors",
        "exec_paid_mat": "Paid to material suppliers",
        "exec_paid_site": "Site and petty expenses",
        "exec_sub_due": "Unpaid subcontractor obligations",
        "exec_chart_expense": "Construction cost and payment structure",
        "exec_chart_forecast": "Near-term liquidity forecast",
        "exec_no_expenses": "No outflow transactions are recorded for this project yet.",
        "exec_lbl_subs": "Subcontractors",
        "exec_lbl_mat": "Material suppliers",
        "exec_lbl_site": "Site and labor expenses",
        "exec_bar_in": "Expected inflow from invoices under approval",
        "exec_bar_out": "Due unpaid subcontractor obligations",
        "exec_bar_net": "Expected net cash flow",
        "exec_horizon": "Next two weeks",
        "exec_print_company": "Al Yosser General Contracting",
        "exec_print_title": "Executive financial report: liquidity and risk control",
        "exec_print_project": "Project",
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
        "assistant_title": "💼 Financial Assistant", "assistant_info": "Live analysis for project:",
        "assistant_you": "You", "assistant_bot": "Assistant",
        "assistant_placeholder": "Ask about this project's invoices and expenses...",
        "assistant_send": "Send",
        "assistant_clear": "Clear chat 🗑️", "assistant_spinner": "Retrieving records and reviewing...",
        "analytics_title": "📊 Invoices & Custody Analytics", "print_report": "🖨️ Print Executive Report (A3)",
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

t["curr"] = st.session_state.project_currency

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
        background: linear-gradient(135deg, #0A2540 0%, #005C8A 100%) !important;
        border: 1.5px solid #0369A1 !important; color: #FFFFFF !important;
    }
    .sb-programs-title {
        text-align: start; font-size: 18px; font-weight: 900; color: var(--text-title, #0A2540);
        margin: 2px 0 12px 0; padding: 0 2px 8px 2px; letter-spacing: 0.01em; line-height: 1.35;
        border-bottom: 3px solid #0284C7;
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
        border: 1px solid #D6E4EF; border-right: 4px solid #0284C7; font-size: 13px; font-weight: 700; line-height: 1.5;
        box-shadow: 0 2px 8px rgba(44, 62, 80, 0.05);
    }
    .fin-chat-wrap {
        background: #FBF9F3; border: 1px solid #E6D9A8; border-radius: 12px; padding: 8px;
        margin-bottom: 8px; height: auto !important; max-height: 36vh; overflow-y: auto;
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"] {
        height: auto !important; max-height: none !important; overflow: visible !important;
        margin-bottom: 8px !important;
    }
    section[data-testid="stSidebar"] [data-testid="stChatInput"],
    section[data-testid="stSidebar"] [data-testid="stBottomBlockContainer"] {
        position: static !important; height: auto !important;
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
        ("subcontractor", "🏗️", t["prog_sub"], False),
        ("client", "📑", t["prog_client"], False),
        ("executive", "📊", t["prog_exec"], False),
    ]
    for key, icon, title, is_soon in program_items:
        is_active = st.session_state.active_portal_module == key
        btn_type = "primary" if is_active else "secondary"
        if st.button(f"{icon}  {title}", use_container_width=True, type=btn_type, key=f"prog_btn_{key}"):
            st.session_state.active_portal_module = key
            if key == "custody":
                st.session_state.active_tab = "records"
            st.rerun()
        if is_soon:
            st.markdown(f'<div class="sb-program-meta">{t["coming_soon"]} — {t["in_prep"]}</div>', unsafe_allow_html=True)

    st.divider()
    with st.container(border=True):
        st.markdown(f'<div class="sb-settings-title">{t["settings_title"]}</div>', unsafe_allow_html=True)
        lang_choice = st.radio(t["lang_label"], ["العربية", "English"], index=0 if st.session_state.system_lang == "العربية" else 1, horizontal=True)
        if lang_choice != st.session_state.system_lang:
            st.session_state.system_lang = lang_choice
            st.session_state.project_currency = normalize_project_currency(st.session_state.project_currency, lang_choice)
            st.rerun()

        theme_options = [t["theme_light"], t["theme_dark"]]
        cur_th_idx = 0 if st.session_state.system_theme == "Light" else 1
        theme_selected = st.radio(t["theme_label"], theme_options, index=cur_th_idx, horizontal=True)
        new_theme = "Light" if theme_selected == t["theme_light"] else "Dark"
        if new_theme != st.session_state.system_theme:
            st.session_state.system_theme = new_theme; st.rerun()

        currency_opts = currency_options_for_lang(st.session_state.system_lang)
        current_currency = normalize_project_currency(st.session_state.project_currency, st.session_state.system_lang)
        st.session_state.project_currency = current_currency
        cur_idx = currency_opts.index(current_currency) if current_currency in currency_opts else 0
        selected_currency = st.selectbox(t["currency_label"], currency_opts, index=cur_idx)
        if selected_currency != st.session_state.project_currency:
            st.session_state.project_currency = selected_currency
            st.rerun()

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

        user_query = st.text_input(t["assistant_placeholder"], key="assistant_text_in", label_visibility="collapsed")
        send_assistant = st.button(t["assistant_send"], use_container_width=True, key="assistant_send_btn")
        if send_assistant and str(user_query or "").strip():
            st.session_state.chat_messages.append({"role": "user", "content": user_query.strip()})
            with st.spinner(t["assistant_spinner"]):
                try:
                    ans = ask_project_assistant(
                        user_query=user_query.strip(),
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

        st.markdown("---")
        st.caption(t["calc_title"])
        calc_expr = st.text_input(t["calc_expr"], value="", key="quick_calc_in")
        if st.button(t["calc_btn"], use_container_width=True, key="sidebar_calc_btn"):
            try:
                clean_expr = re.sub(r'[^0-9\+\-\*\/\.\(\)\s]', '', calc_expr)
                if clean_expr.strip():
                    res = eval(clean_expr)
                    st.success(f"{t['calc_res']} **{res:,.2f}**")
            except Exception:
                st.error(t["calc_err"])

if st.session_state.active_portal_module == "client":
    render_client_invoices_tab()
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

if st.session_state.active_portal_module == "subcontractor":
    from subcontractor_module import render_subcontractor_interface
    render_subcontractor_interface(selected_proj, current_user_data, api_key)
    st.stop()

if st.session_state.active_portal_module == "executive":
    # ─── 1. استدعاء البيانات المجمعة الموسعة ───
    exec_data = get_project_executive_summary(selected_proj) or {}

    cash_in = float(exec_data.get("total_cash_in", 0.0) or 0.0)
    cash_out = float(exec_data.get("total_cash_out", 0.0) or 0.0)
    net_flow = float(exec_data.get("net_cash_flow", 0.0) or 0.0)

    sub_paid = float(exec_data.get("subcontractors_paid", 0.0) or 0.0)
    mat_paid = float(exec_data.get("material_suppliers_paid", 0.0) or 0.0)
    site_exp = float(exec_data.get("general_site_expenses", 0.0) or 0.0)

    client_retention = float(exec_data.get("client_retention_receivable", 0.0) or 0.0)
    sub_retention = float(exec_data.get("subcontractors_retention", 0.0) or 0.0)

    adv_received = float(exec_data.get("advance_payment_received", 0.0) or 0.0)
    adv_recovered = float(exec_data.get("advance_payment_recovered", 0.0) or 0.0)
    adv_balance = float(exec_data.get("advance_payment_balance", 0.0) or 0.0)

    pending_ipc = float(exec_data.get("client_pending_approval", 0.0) or 0.0)
    sub_due = float(exec_data.get("subcontractors_balance_due", 0.0) or 0.0)

    forecast_in = float(exec_data.get("short_term_forecast_inflow", 0.0) or 0.0)
    forecast_out = float(exec_data.get("short_term_forecast_outflow", 0.0) or 0.0)
    forecast_net = float(exec_data.get("short_term_forecast_net", 0.0) or 0.0)

    issue_date_val = datetime.date.today().strftime("%Y-%m-%d")
    proj_html = html.escape(str(selected_proj or ""))
    curr_html = html.escape(str(st.session_state.project_currency))
    title_html = html.escape(str(t.get("prog_exec", "")))
    print_label = html.escape(str(t.get("print_report", "طباعة التقرير")))
    issue_label = html.escape(str(t.get("issue_date", "تاريخ الإصدار")))
    retention_gap = client_retention - sub_retention

    # ─── 2. ضبط المؤشرات البصرية ودلالات الألوان ───
    if net_flow > 0:
        net_color = "#10B981"
        status_text = t["exec_status_surplus"]
    elif net_flow < 0:
        net_color = "#EF4444"
        status_text = t["exec_status_deficit"]
    else:
        net_color = "#38BDF8"
        status_text = t["exec_status_balanced"]

    coverage_ratio = (cash_in / cash_out * 100) if cash_out > 0 else 0.0

    st.markdown("""
    <style>
    .exec-print-header { display: none !important; visibility: hidden !important; height: 0 !important; overflow: hidden !important; margin: 0 !important; padding: 0 !important; border: none !important; }
    @media print {
        @page { size: A3 landscape; margin: 10mm 12mm; }
        html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main, .block-container {
            background: #FFFFFF !important; color: #2C3E50 !important;
            overflow: visible !important; height: auto !important; max-width: 100% !important;
            padding: 0 !important; margin: 0 !important;
        }
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"],
        [data-testid="stStatusWidget"],
        [data-testid="stBottomBlockContainer"],
        footer, #MainMenu, .stDeployButton, .stAppToolbar,
        .no-print, .footer-container,
        [data-testid="stExpander"],
        [data-testid="stSelectbox"],
        [data-testid="stIFrame"],
        [data-testid="stInfo"],
        [data-testid="stAlert"],
        [data-testid="stDivider"],
        .stButton, [data-testid="stButton"] {
            display: none !important; visibility: hidden !important; height: 0 !important; width: 0 !important;
            overflow: hidden !important;
        }
        body * { visibility: hidden !important; }
        .exec-print-header, .exec-print-header *,
        .print-keep, .print-keep *,
        .kpi-card, .kpi-card *,
        .print-chart-block, .print-chart-block *,
        [data-testid="stPlotlyChart"], [data-testid="stPlotlyChart"] *,
        .js-plotly-plot, .js-plotly-plot *, .plot-container, .plot-container *, .svg-container, .svg-container * {
            visibility: visible !important;
        }
        [data-testid="stAppViewContainer"] { margin-left: 0 !important; }
        section[data-testid="stSidebar"] { display: none !important; width: 0 !important; min-width: 0 !important; }
        .exec-print-header {
            display: block !important;
            visibility: visible !important;
            height: auto !important;
            overflow: visible !important;
            margin-bottom: 10px !important;
            border-bottom: 3px solid #0284C7 !important;
            padding-bottom: 8px !important;
            page-break-after: avoid !important;
        }
        .kpi-card {
            background: #E3F4FB !important; border: 1px solid #B7D7EA !important;
            page-break-inside: avoid !important; break-inside: avoid !important;
        }
        .print-keep, .print-chart-block,
        .js-plotly-plot, .plot-container, .svg-container,
        [data-testid="stPlotlyChart"], [data-testid="stHorizontalBlock"] {
            page-break-inside: avoid !important; break-inside: avoid-page !important;
            overflow: visible !important;
        }
        [data-testid="stPlotlyChart"], .js-plotly-plot, .plot-container, .svg-container {
            max-height: none !important; height: auto !important;
        }
        h2, h3, h4 { margin: 4px 0 6px 0 !important; page-break-after: avoid !important; }
        * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
    }
    </style>
    """, unsafe_allow_html=True)

    # ─── 3. شريط العنوان وأمر الطباعة ───
    col_title, col_print = st.columns([3.2, 1])
    with col_title:
        st.markdown(
            f'<div class="section-banner no-print">📊 {title_html} — {proj_html}</div>',
            unsafe_allow_html=True,
        )
    with col_print:
        st.components.v1.html(
            f"""
            <button onclick="window.parent.print()" style="background: linear-gradient(135deg, #0A2540 0%, #005C8A 100%); color:white; padding:11px 16px; border:1px solid #0369A1; border-radius:12px; cursor:pointer; font-weight:800; font-size:13px; width:100%;">
                🖨️ {print_label}
            </button>
            """,
            height=50,
        )

    # ─── 4. ترويسة التقرير الرسمية للطباعة (تظهر في الطباعة فقط) ───
    st.markdown(f"""
    <div class="exec-print-header">
        <h3 style="margin:0;">{html.escape(t["exec_print_company"])}</h3>
        <h2 style="margin:6px 0 8px 0;">{html.escape(t["exec_print_title"])}</h2>
        <p style="margin:0;font-weight:700;">{html.escape(t["exec_print_project"])}: {proj_html}</p>
        <p style="margin:4px 0 0 0;">{issue_label}: {issue_date_val}</p>
    </div>
    """, unsafe_allow_html=True)

    # ─── 5. شريط مؤشرات الرقابة والسيولة الشامل (6 بطاقات رئيسية) ───
    st.markdown(f"""
    <div class="print-keep" style="display:flex;gap:15px;margin-bottom:16px;flex-wrap:wrap;">
        <div class="kpi-card">
            <h5>{html.escape(t["exec_kpi_in_title"])}</h5>
            <h3>{cash_in:,.2f} {curr_html}</h3>
            <p style="margin:8px 0 0 0;font-size:12px;opacity:.8;">{html.escape(t["exec_kpi_in_sub"])}</p>
        </div>
        <div class="kpi-card">
            <h5>{html.escape(t["exec_kpi_out_title"])}</h5>
            <h3>{cash_out:,.2f} {curr_html}</h3>
            <p style="margin:8px 0 0 0;font-size:12px;opacity:.8;">{html.escape(t["exec_kpi_out_sub"])}</p>
        </div>
        <div class="kpi-card">
            <h5>{html.escape(t["exec_kpi_net_title"])}</h5>
            <h3 style="color:{net_color} !important;">{net_flow:,.2f} {curr_html}</h3>
            <p style="margin:8px 0 0 0;font-size:12px;opacity:.8;">{html.escape(t["exec_kpi_net_sub"])} · {html.escape(t["exec_coverage"])} {coverage_ratio:.1f}%</p>
        </div>
    </div>
    <div class="print-keep" style="display:flex;gap:15px;margin-bottom:24px;flex-wrap:wrap;">
        <div class="kpi-card">
            <h5>{html.escape(t["exec_kpi_pending_title"])}</h5>
            <h3>{pending_ipc:,.2f} {curr_html}</h3>
            <p style="margin:8px 0 0 0;font-size:12px;opacity:.8;">{html.escape(t["exec_kpi_pending_sub"])}</p>
        </div>
        <div class="kpi-card">
            <h5>{html.escape(t["exec_kpi_ret_title"])}</h5>
            <h3>{client_retention:,.2f} {curr_html}</h3>
            <p style="margin:8px 0 0 0;font-size:12px;opacity:.8;">{html.escape(t["exec_kpi_ret_sub"])}</p>
        </div>
        <div class="kpi-card">
            <h5>{html.escape(t["exec_kpi_adv_title"])}</h5>
            <h3>{adv_balance:,.2f} {curr_html}</h3>
            <p style="margin:8px 0 0 0;font-size:12px;opacity:.8;">{html.escape(t["exec_kpi_adv_sub"])}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ─── 6. لوحة تقييم الالتزامات والضمانات الإنشائية (Exposure & Retentions) ───
    st.markdown(f"""
    <div class="print-keep" style="border:1px solid #E2E8F0;border-radius:12px;padding:18px 20px;margin-bottom:22px;background:rgba(255,255,255,0.35);">
        <h4 style="margin:0 0 10px 0;">🏗️ {html.escape(t["exec_exposure_title"])}</h4>
        <p style="margin:0 0 14px 0;font-size:18px;font-weight:800;color:{net_color};">{html.escape(status_text)}</p>
        <p style="margin:0 0 8px 0;"><b>💰 {html.escape(t["exec_advance_cycle"])}:</b></p>
        <p style="margin:0 0 4px 18px;">• {html.escape(t["exec_adv_received"])}: <b>{adv_received:,.2f} {curr_html}</b></p>
        <p style="margin:0 0 4px 18px;">• {html.escape(t["exec_adv_recovered"])}: <b>{adv_recovered:,.2f} {curr_html}</b></p>
        <p style="margin:0 0 12px 18px;">• {html.escape(t["exec_adv_remaining"])}: <b>{adv_balance:,.2f} {curr_html}</b></p>
        <p style="margin:0 0 8px 0;"><b>🔒 {html.escape(t["exec_ret_section"])}:</b></p>
        <p style="margin:0 0 4px 18px;">• {html.escape(t["exec_ret_client"])}: <b>{client_retention:,.2f} {curr_html}</b></p>
        <p style="margin:0 0 4px 18px;">• {html.escape(t["exec_ret_sub"])}: <b>{sub_retention:,.2f} {curr_html}</b></p>
        <p style="margin:0 0 12px 18px;">• {html.escape(t["exec_ret_gap"])}: <b>{retention_gap:,.2f} {curr_html}</b></p>
        <p style="margin:0 0 8px 0;"><b>📦 {html.escape(t["exec_outflow_section"])}:</b></p>
        <p style="margin:0 0 4px 18px;">• {html.escape(t["exec_paid_sub"])}: <b>{sub_paid:,.2f} {curr_html}</b></p>
        <p style="margin:0 0 4px 18px;">• {html.escape(t["exec_paid_mat"])}: <b>{mat_paid:,.2f} {curr_html}</b></p>
        <p style="margin:0 0 0 18px;">• {html.escape(t["exec_paid_site"])}: <b>{site_exp:,.2f} {curr_html}</b></p>
        <p style="margin:10px 0 0 0;font-size:12px;opacity:.85;">{html.escape(t["exec_sub_due"])}: <b>{sub_due:,.2f} {curr_html}</b></p>
    </div>
    """, unsafe_allow_html=True)

    # ─── 7. الرسوم البيانية: هيكل التكاليف + توقعات السيولة القادمة ───
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.markdown('<div class="print-chart-block">', unsafe_allow_html=True)
        st.markdown(f"### 🍩 {t['exec_chart_expense']}")
        expense_labels = [t["exec_lbl_subs"], t["exec_lbl_mat"], t["exec_lbl_site"]]
        expense_values = [sub_paid, mat_paid, site_exp]
        if sum(expense_values) > 0:
            fig_donut = px.pie(
                values=expense_values,
                names=expense_labels,
                hole=0.45,
                color_discrete_sequence=["#DC2626", "#F59E0B", "#3B82F6"],
            )
            fig_donut.update_layout(height=320, margin=dict(t=20, b=20, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info(t["exec_no_expenses"])
        st.markdown("</div>", unsafe_allow_html=True)

    with col_chart2:
        st.markdown('<div class="print-chart-block">', unsafe_allow_html=True)
        st.markdown(f"### 📈 {t['exec_chart_forecast']}")
        fig_forecast = go.Figure(data=[
            go.Bar(name=t["exec_bar_in"], x=[t["exec_horizon"]], y=[forecast_in], marker_color="#0284C7", text=[f"{forecast_in:,.0f}"], textposition="auto"),
            go.Bar(name=t["exec_bar_out"], x=[t["exec_horizon"]], y=[forecast_out], marker_color="#EF4444", text=[f"{forecast_out:,.0f}"], textposition="auto"),
            go.Bar(name=t["exec_bar_net"], x=[t["exec_horizon"]], y=[forecast_net], marker_color="#10B981" if forecast_net >= 0 else "#DC2626", text=[f"{forecast_net:,.0f}"], textposition="auto"),
        ])
        fig_forecast.update_layout(barmode="group", height=320, margin=dict(t=20, b=20, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_forecast, use_container_width=True, config={"displayModeBar": False})
        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

project_invoices = [item for item in st.session_state.invoices_data if item.get("project") == selected_proj]
active_project_invoices = [item for item in project_invoices if not item.get("delete", False)]

total_in = sum(item["amount"] for item in active_project_invoices if item["doc_type"] == "وارد")
total_out = sum(item["amount"] for item in active_project_invoices if item["doc_type"] == "منصرف")
balance = total_in - total_out
burn_rate = (total_out / total_in * 100) if total_in > 0 else 0

# ألسنة التبويبات المجمعة جهة اليمين
if can_access_system_policies:
    t_cols = st.columns([1.6, 2.2, 1.8, 4.4])
else:
    t_cols = st.columns([1.8, 2.4, 5.8])

with t_cols[0]:
    st.markdown('<span class="folder-tab-anchor"></span>', unsafe_allow_html=True)
    if st.button(t["tab_records"], use_container_width=True, type="primary" if st.session_state.active_tab == "records" else "secondary", key="folder_tab_records"):
        st.session_state.active_tab = "records"
        st.rerun()

with t_cols[1]:
    if st.button(t["tab_custody_analytics"], use_container_width=True, type="primary" if st.session_state.active_tab == "analytics" else "secondary", key="folder_tab_analytics"):
        st.session_state.active_tab = "analytics"
        st.rerun()

if can_access_system_policies:
    with t_cols[2]:
        if st.button(t["tab_memory"], use_container_width=True, type="primary" if st.session_state.active_tab == "memory" else "secondary", key="folder_tab_memory"):
            st.session_state.active_tab = "memory"
            st.rerun()

if st.session_state.active_tab == "records":
    apply_pending_sync_results()
    st.markdown(f"""
    <div style='display: flex; gap: 15px; margin-bottom: 30px;'>
        <div class="kpi-card"><h5>{t["metric_in"]}</h5><h3>{total_in:,.2f} {st.session_state.project_currency}</h3></div>
        <div class="kpi-card"><h5>{t["metric_out"]}</h5><h3>{total_out:,.2f} {st.session_state.project_currency}</h3></div>
        <div class="kpi-card"><h5>{t["metric_bal"]}</h5><h3>{balance:,.2f} {st.session_state.project_currency}</h3></div>
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

            with st.container():
                if is_rtl:
                    kind_options = [
                        "🔴 منصرف (فواتير وإيصالات صرف)",
                        "🟢 وارد (سندات قبض وتمويل)",
                    ]
                    kind_label = "نوع الحركة المالية:"
                    file_label = "اسحب المستندات وأفلتها هنا أو انقر للاختيار (PDF أو صور):"
                    file_help = "يدعم السحب والإفلات، التصفح المباشر، وملفات الـ PDF والصور المتعددة حتى 200MB"
                    paste_hint = "يمكنك أيضاً الضغط على Ctrl+V للصق صورة من الحافظة، أو سحب الملف وإفلاته مباشرة."
                else:
                    kind_options = [
                        f"{t['out_opt']} ({t['out_opt_sub']})",
                        f"{t['in_opt']} ({t['in_opt_sub']})",
                    ]
                    kind_label = f"{t['doc_type_prompt']}:"
                    file_label = t["choose_files"]
                    file_help = "Drag and drop, browse, and paste images. PDF and images up to 200MB."
                    paste_hint = "You can also press Ctrl+V to paste an image, or drag a file onto the box."

                col_kind, col_upload, col_action = st.columns([1.2, 2.8, 1.2], gap="medium")

                with col_kind:
                    doc_kind_selected = st.selectbox(
                        kind_label,
                        kind_options,
                        index=0 if st.session_state.upload_doc_kind == "out" else 1,
                        key="styled_doc_kind_select" if is_rtl else "styled_doc_kind_select_en",
                    )
                    st.session_state.upload_doc_kind = "out" if doc_kind_selected == kind_options[0] else "in"
                    is_inbound = (st.session_state.upload_doc_kind == "in")
                    st.markdown(f'<div class="upload-paste-hint">{paste_hint}</div>', unsafe_allow_html=True)

                with col_upload:
                    st.markdown('<span class="invoice-drop-anchor"></span>', unsafe_allow_html=True)
                    main_files = st.file_uploader(
                        file_label,
                        type=["jpg", "png", "jpeg", "pdf"],
                        accept_multiple_files=True,
                        key="unified_file_uploader",
                        help=file_help,
                    )

                with col_action:
                    start_trigger = st.button(
                        "🚀 " + t["start_process"],
                        type="primary",
                        use_container_width=True,
                        key="btn_start_extract_proc",
                    )

                st.html(
                    """
                    <div id="invoice-paste-hook"></div>
                    <script>
                    (function () {
                      const root = document.documentElement;
                      if (root.dataset.invoicePasteBound === "1") return;
                      root.dataset.invoicePasteBound = "1";
                      document.addEventListener("paste", function (event) {
                        const active = document.activeElement;
                        const tag = active && active.tagName;
                        if (tag === "INPUT" || tag === "TEXTAREA" || (active && active.isContentEditable)) {
                          if (!active || active.type !== "file") return;
                        }
                        const items = (event.clipboardData && event.clipboardData.items) || [];
                        const images = [];
                        for (let i = 0; i < items.length; i++) {
                          if (items[i].type && items[i].type.indexOf("image/") === 0) {
                            const file = items[i].getAsFile();
                            if (file) images.push(file);
                          }
                        }
                        if (!images.length) return;
                        const anchor = document.querySelector(".invoice-drop-anchor");
                        const column = anchor && anchor.closest('[data-testid="stColumn"]');
                        const input = (column && column.querySelector('input[type="file"]'))
                          || document.querySelector('[data-testid="stFileUploaderDropzone"] input[type="file"]');
                        if (!input || typeof DataTransfer === "undefined") return;
                        event.preventDefault();
                        const transfer = new DataTransfer();
                        if (input.multiple && input.files) {
                          for (let i = 0; i < input.files.length; i++) transfer.items.add(input.files[i]);
                        }
                        images.forEach(function (file, index) {
                          const ext = (file.type.split("/")[1] || "png").replace("jpeg", "jpg");
                          const name = (file.name && file.name !== "image.png")
                            ? file.name
                            : ("clipboard-" + Date.now() + "-" + index + "." + ext);
                          transfer.items.add(new File([file], name, { type: file.type || "image/png" }));
                        });
                        input.files = transfer.files;
                        input.dispatchEvent(new Event("change", { bubbles: true }));
                      });
                    })();
                    </script>
                    """,
                    unsafe_allow_javascript=True,
                )

                if start_trigger:
                    if not api_key:
                        st.error(t["api_disc"])
                    elif not main_files:
                        st.warning(t["files_first"])
                    else:
                        with st.spinner(t["process_spinner"]):
                            st.session_state.invoice_queue = []
                            for file in main_files:
                                file_bytes = file.read()
                                if file.name.lower().endswith(".pdf"):
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
                                        st.session_state.invoice_queue.append({"image": img, "name": f"{file.name} - ص{i+1}"})
                                    doc.close()
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
                        st.session_state.pending_invoice = analyze_invoice_with_gemini(current_item["image"], prompt, api_key, current_project=selected_proj, module_type="custody")
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
                    amount = st.number_input(f"{t['col_amount']} ({st.session_state.project_currency})", value=float(data.get("amount", 0.0)))
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
                        ⚠️ تنبيه تكرار: المستند رقم ({clean_inv_no}) بمبلغ ({amount:,.2f} {st.session_state.project_currency}) مسجل مسبقاً في الحركة رقم ({duplicate_found[0]}).
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
                                "id": str(uuid.uuid4()),
                                "module_type": "custody",
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
        desc_info = f"({target_inv['description']} - {target_inv['amount']:,.2f} {st.session_state.project_currency})" if target_inv else ""
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
        background: var(--bg-card, #FFFFFF); border: 1px solid #D6E4EF; border-{ 'right' if is_rtl else 'left' }: 4px solid #0284C7;
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
        text-align: {align_css}; border-bottom: 2px solid #0284C7;
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
        .print-only-header {{ display: block !important; margin-bottom: 10px !important; border-bottom: 3px solid #0284C7; padding-bottom: 8px; page-break-after: avoid !important; }}
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
        <button onclick="window.parent.print()" style="background: linear-gradient(135deg, #0A2540 0%, #005C8A 100%); color:white; padding:11px 16px; border:1px solid #0369A1; border-radius:12px; cursor:pointer; font-weight:800; font-size:13px; width:100%;">
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
        <div class="kpi-card"><h5>{t["metric_in"]}</h5><h3>{a_total_in:,.2f} {st.session_state.project_currency}</h3></div>
        <div class="kpi-card"><h5>{t["metric_out"]}</h5><h3>{a_total_out:,.2f} {st.session_state.project_currency}</h3></div>
        <div class="kpi-card"><h5>{t["metric_bal"]}</h5><h3>{a_balance:,.2f} {st.session_state.project_currency}</h3></div>
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
            cost_body = f"يمثل بند <b>({top_cat})</b> أعلى معدل استنزاف نقدي في نطاق التحليل بإجمالي <b>{top_cat_amt:,.2f} {st.session_state.project_currency}</b> وبنسبة <b>{top_cat_pct:.1f}%</b> من إجمالي المنصرف."
            cost_rec = "مراجعة أوامر التوريد ومطابقة المستخلصات الدورية للبند للتحقق من كفاءة التسعير والكميات."
            cash_body = f"تبلغ نسبة السداد النقدي المباشر <b>{cash_pct:.1f}%</b> بإجمالي <b>{cash_amt:,.2f} {st.session_state.project_currency}</b>."
            cash_rec = "الاعتماد المستمر على الشيكات والتحويلات البنكية الموثقة لإحكام الرقابة وتأكيد التسليم المباشر للموردين والمقاولين."
        else:
            cost_body = f"The item <b>({top_cat})</b> is the highest cash drain in this scope, totaling <b>{top_cat_amt:,.2f} {st.session_state.project_currency}</b> ({top_cat_pct:.1f}% of expenses)."
            cost_rec = "Review supply orders and periodic certificates for this item to verify pricing and quantity efficiency."
            cash_body = f"Direct cash payments represent <b>{cash_pct:.1f}%</b>, totaling <b>{cash_amt:,.2f} {st.session_state.project_currency}</b>."
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
# ─── تبويب سياسات وضوابط النظام (التصميم المؤسسي الموحد - Super Admin) ───
# ═════════════════════════════════════════════════════════════════════════
elif st.session_state.active_tab == "memory" and (user_role == "Super Admin"):
    _mem_title = html.escape(str(t["tab_memory"]))
    _mem_proj = html.escape(str(selected_proj))
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700;800&display=swap');
    .memory-policies-root, .memory-policies-root *,
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root),
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root) * {{
        font-family: 'IBM Plex Sans Arabic', sans-serif !important;
    }}
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root) {{
        direction: rtl !important;
        text-align: right !important;
    }}
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root) button[kind="primary"] {{
        background: linear-gradient(135deg, #0A2540 0%, #005C8A 100%) !important;
        border: 1px solid #0369A1 !important;
        color: #FFFFFF !important;
        font-family: 'IBM Plex Sans Arabic', sans-serif !important;
        font-weight: 700 !important;
    }}
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root) button[kind="secondary"] {{
        background: #FFFFFF !important;
        border: 1px solid #0A2540 !important;
        color: #0A2540 !important;
        font-family: 'IBM Plex Sans Arabic', sans-serif !important;
        font-weight: 700 !important;
    }}
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root) [data-testid="stTextInput"] input,
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root) [data-testid="stTextArea"] textarea,
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root) [data-baseweb="select"],
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root) [data-baseweb="input"] {{
        border: 1px solid #0369A1 !important;
        font-family: 'IBM Plex Sans Arabic', sans-serif !important;
        direction: rtl !important;
        text-align: right !important;
    }}
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root) [data-testid="stTextInput"] input:focus,
    .stApp [data-testid="stVerticalBlock"]:has(.memory-policies-root) [data-testid="stTextArea"] textarea:focus {{
        border-color: #0284C7 !important;
        box-shadow: 0 0 0 1px #0284C7 !important;
    }}
    .memory-kpi-strip {{
        display: flex; gap: 15px; margin-bottom: 24px;
        direction: rtl; font-family: 'IBM Plex Sans Arabic', sans-serif;
    }}
    .memory-kpi-strip .kpi-card small {{
        display: block; margin-top: 6px; font-size: 12px; font-weight: 600;
        color: var(--text-muted, #64748B);
    }}
    </style>
    <div class="memory-policies-root section-banner">
        ⚙️ {_mem_title} — {_mem_proj}
    </div>
    """, unsafe_allow_html=True)

    # ─── 1. شريط المؤشرات الإحصائية لذاكرة النظام ───
    approved_ds = load_approved_dataset()
    count_custody = len([d for d in approved_ds if d.get("module_type", "custody") == "custody"])
    count_sub = len([d for d in approved_ds if d.get("module_type") == "subcontractor"])
    count_client = len([d for d in approved_ds if d.get("module_type") == "client"])
    total_samples = len(approved_ds)

    st.markdown(f"""
    <div class="memory-kpi-strip">
        <div class="kpi-card">
            <h5>إجمالي الذاكرة المعرفية</h5>
            <h3>{total_samples}</h3>
            <small>عينة استرشادية معتمدة</small>
        </div>
        <div class="kpi-card">
            <h5>فواتير وعهد الموقع</h5>
            <h3>{count_custody}</h3>
            <small>نماذج صرف وتدقيق</small>
        </div>
        <div class="kpi-card">
            <h5>مقاولو الباطن</h5>
            <h3>{count_sub}</h3>
            <small>حصر ومستخلصات جارية</small>
        </div>
        <div class="kpi-card">
            <h5>مستخلصات العميل</h5>
            <h3>{count_client}</h3>
            <small>مطابقة كميات واعتمادات</small>
        </div>
    </div>
    """, unsafe_allow_html=True)

    t_tab1, t_tab2, t_tab3 = st.tabs([
        "1️⃣ ضوابط وتوجيهات التدقيق",
        "2️⃣ مستودع العينات المعتمدة",
        "3️⃣ التوجيه الذكي وقاموس المصطلحات"
    ])

    curr_cfg = st.session_state.tuning_config

    # ─── القسم الأول: ضوابط وتوجيهات التدقيق ───
    with t_tab1:
        st.subheader("🏢 تخصيص سياسات التدقيق المحاسبي للمشاريع")

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            c_name_val = st.text_input("اسم المنشأة / الشركة المعتمدة:", value=curr_cfg.get("company_name", "شركة اليسر للمقاولات"))
        with col_c2:
            c_id_val = st.text_input("معرّف المنشأة في النظام:", value=curr_cfg.get("company_id", "alyoser_contracting"))

        module_choice = st.radio(
            "اختر الوحدة لضبط سياسات التدقيق والاستخراج الخاصة بها:",
            ["فواتير ومصروفات العهد", "مستخلصات مقاولي الباطن", "مستخلصات العميل والمقايسة"],
            horizontal=True
        )

        schemas = curr_cfg.get("schemas", {})
        if not isinstance(schemas, dict):
            schemas = {}

        if module_choice == "فواتير ومصروفات العهد":
            curr_inst = curr_cfg.get("inst_custody", "أنت مراجع مالي معتمد. مهمتك استخراج ومطابقة بيانات إيصالات وفواتير العهد والمصروفات بدقة ومطابقة التفقيط.")
            curr_schema = schemas.get("custody", {
                "invoice_no": "رقم المستند", "invoice_date": "YYYY-MM-DD",
                "amount": 0.0, "vat": 0.0, "description": "البيان واسم المستفيد",
                "category": "موردين / مواد / مقاولين / عمالة / نثريات",
                "payment_method": "نقدي / شيك / تحويل"
            })
            inst_key = "inst_custody"
            schema_key = "custody"

        elif module_choice == "مستخلصات مقاولي الباطن":
            curr_inst = curr_cfg.get("inst_subcontractor", "أنت مهندس ومراجع عقود مقاولي باطن. مهمتك مراجعة حصر الأعمال الحالية، نسب الإنجاز، استقطاع الدفعة المقدمة ومحتجز ضمان الأعمال.")
            curr_schema = schemas.get("subcontractor", {
                "subcontractor_name": "اسم مقاول الباطن", "ipc_no": "رقم المستخلص الجاري",
                "current_work_value": 0.0, "retention_deduction": 0.0,
                "advance_recovery": 0.0, "net_payable": 0.0, "statement_period": "فترة الأعمال"
            })
            inst_key = "inst_subcontractor"
            schema_key = "subcontractor"

        else:
            curr_inst = curr_cfg.get("inst_client", "أنت خبير إدارة عقود ومستخلصات مالك. مهمتك تدقيق بنود الحصر ومطابقتها بجدول الكميات المعتمد (BOQ)، واحتساب المحتجزات والضريبة بدقة.")
            curr_schema = schemas.get("client", {
                "client_name": "اسم المالك / جهة الإسناد", "invoice_no": "رقم مستخلص العميل",
                "work_executed_amount": 0.0, "retention_amount": 0.0,
                "advance_payment_deduction": 0.0, "vat_amount": 0.0,
                "net_payable": 0.0, "approval_status": "معتمد / قيد المراجعة"
            })
            inst_key = "inst_client"
            schema_key = "client"

        st.markdown(f"**التوجيه المحاسبي المعتمد لوحدة ({module_choice}):**")
        updated_inst = st.text_area("نص التوجيه للنظام أثناء المعالجة:", value=curr_inst, height=100, key=f"inst_area_{schema_key}")

        st.markdown(f"**هيكل الحقول الإلزامي المستخرج لوحدة ({module_choice}):**")
        updated_schema_str = st.text_area(
            "هيكل الحقول (JSON Schema):",
            value=json.dumps(curr_schema, ensure_ascii=False, indent=2),
            height=160,
            key=f"schema_area_{schema_key}"
        )

        if st.button("💾 حفظ سياسات وتوجيهات الوحدة", type="primary", key=f"save_btn_{schema_key}", use_container_width=True):
            try:
                parsed_schema = json.loads(updated_schema_str)
                curr_cfg["company_name"] = c_name_val
                curr_cfg["company_id"] = c_id_val
                curr_cfg[inst_key] = updated_inst
                if "schemas" not in curr_cfg:
                    curr_cfg["schemas"] = {}
                curr_cfg["schemas"][schema_key] = parsed_schema

                save_tuning_config(curr_cfg)
                st.session_state.tuning_config = curr_cfg
                st.success(f"✅ تم حفظ السياسات المعتمدة لوحدة ({module_choice}) بنجاح!")
            except Exception as e:
                st.error(f"خطأ في صيغة JSON: {e}")

    # ─── القسم الثاني: مستودع العينات المعتمدة ───
    with t_tab2:
        st.subheader("📚 مستودع العينات والقيود المعتمدة (Ground Truth Dataset)")
        curr_curr = st.session_state.get("project_currency", "ج.م")

        # التأكد من وجود معرّف ونوع الوحدة لكل عينة مسجلة مسبقاً
        updated_ds_ids = False
        for item in approved_ds:
            if "id" not in item:
                item["id"] = str(uuid.uuid4())
                updated_ds_ids = True
            if "module_type" not in item:
                item["module_type"] = "custody"
                updated_ds_ids = True
        if updated_ds_ids:
            save_approved_dataset(approved_ds)
            st.session_state.approved_dataset = approved_ds

        col_f1, col_f2 = st.columns([1.5, 2])
        with col_f1:
            filter_unit = st.selectbox(
                "تصفية العينات حسب الوحدة:",
                ["الكل", "فواتير ومصروفات العهد", "مستخلصات مقاولي الباطن", "مستخلصات العميل"],
                key="ds_filter_unit_enhanced"
            )
        with col_f2:
            search_query = st.text_input("🔍 بحث في المستندات أو البيانات:", placeholder="رقم المستند، البيان، اسم الجهة...", key="ds_search_in")

        filtered_ds = approved_ds
        if filter_unit == "فواتير ومصروفات العهد":
            filtered_ds = [d for d in approved_ds if d.get("module_type", "custody") == "custody"]
        elif filter_unit == "مستخلصات مقاولي الباطن":
            filtered_ds = [d for d in approved_ds if d.get("module_type") == "subcontractor"]
        elif filter_unit == "مستخلصات العميل":
            filtered_ds = [d for d in approved_ds if d.get("module_type") == "client"]

        if search_query.strip():
            q = search_query.strip().lower()
            filtered_ds = [
                d for d in filtered_ds
                if q in str(d.get("input_doc", "")).lower()
                or q in str(d.get("ground_truth", {})).lower()
            ]

        st.markdown(f"إجمالي العينات المطابقة: **{len(filtered_ds)}** من أصل **{len(approved_ds)}** عينة موثقة")

        if filtered_ds:
            for idx, item in enumerate(filtered_ds):
                gt = item.get("ground_truth", {})
                sample_id = item.get("id", str(idx))
                unit_label = {
                    "custody": "🧾 فواتير وعهد",
                    "subcontractor": "🏗️ مقاولو باطن",
                    "client": "📑 مستخلصات عميل"
                }.get(item.get("module_type", "custody"), "وثيقة")

                doc_title = item.get("input_doc", "مستند بدون اسم")
                sample_date = item.get("timestamp", "")[:10]
                amount_val = float(gt.get("amount", gt.get("net_payable", gt.get("current_work_value", 0.0))))

                with st.expander(f"{unit_label} | {doc_title} — {amount_val:,.2f} {curr_curr} ({sample_date})", expanded=False):
                    c_det1, c_det2 = st.columns([3, 1])
                    with c_det1:
                        st.json(gt)
                    with c_det2:
                        st.markdown(f"**معرّف السجل:**\n\n{(sample_id or '')[:8]}...", unsafe_allow_html=True)
                        st.markdown(f"المصدر: {item.get('source', 'نظام الاعتماد')}")
                        if st.button("🗑️ حذف هذه العينة", key=f"del_sample_{sample_id}", type="secondary", use_container_width=True):
                            approved_ds = [d for d in approved_ds if d.get("id") != sample_id]
                            save_approved_dataset(approved_ds)
                            st.session_state.approved_dataset = approved_ds
                            st.toast("تم حذف العينة بنجاح!", icon="✅")
                            time.sleep(0.4)
                            st.rerun()

            st.divider()
            col_clr1, _ = st.columns([2, 4])
            with col_clr1:
                if st.button("🗑️ مسح نتائج التصفية الحالية فقط", key="clr_filtered_btn", use_container_width=True):
                    filtered_ids = {d.get("id") for d in filtered_ds}
                    approved_ds = [d for d in approved_ds if d.get("id") not in filtered_ids]
                    save_approved_dataset(approved_ds)
                    st.session_state.approved_dataset = approved_ds
                    st.toast("تم مسح العينات المحددة بنجاح!", icon="🧹")
                    time.sleep(0.4)
                    st.rerun()
        else:
            st.info("لا توجد عينات معتمدة مطابقة لشروط التصفية والبحث الحالية.")

    # ─── القسم الثالث: التوجيه الذكي وقاموس المصطلحات ───
    with t_tab3:
        st.subheader("📖 قاموس المصطلحات، الموردين، والمقاولين المعتمد")
        st.markdown("يستخدم هذا القاموس لتوجيه النظام لمطابقة الأسماء والتصنيفات بدقة عبر كافة مستندات المشروع:")

        current_dict_text = st.text_area(
            "قواعد المطابقة والتصنيف المعتمدة:",
            value=st.session_state.system_dictionary,
            height=200,
            key="sys_dict_editor"
        )

        if st.button("💾 حفظ وتعميم القاموس", type="primary", use_container_width=True):
            st.session_state.system_dictionary = current_dict_text
            local_ok, cloud_ok = save_system_dictionary(current_dict_text)
            if local_ok:
                st.success("✅ تم حفظ القاموس الموحد وتعميمه على كافة وحدات النظام بنجاح!")
            else:
                st.error("تعذر حفظ القاموس محلياً، يرجى التحقق من أذونات الكتابة.")

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