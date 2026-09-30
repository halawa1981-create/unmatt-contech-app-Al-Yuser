import streamlit as st
import pandas as pd
import json
import os
import io
import html
import datetime
import uuid
import re
import google.generativeai as genai

# ─── مكتبات الربط السحابي (Google Sheets & Drive) ───
try:
    import gspread
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    G_CLOUD_AVAILABLE = True
except ImportError:
    G_CLOUD_AVAILABLE = False

# ─── إدارة المسارات وقواعد البيانات المحلية ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTRACTORS_FILE = os.path.join(BASE_DIR, "contractors_local.json")
SUBCONTRACTS_FILE = os.path.join(BASE_DIR, "subcontracts_local.json")
BOQ_FILE = os.path.join(BASE_DIR, "boq_local.json")
IPC_FILE = os.path.join(BASE_DIR, "ipc_local.json")
IPC_AUDIT_FILE = os.path.join(BASE_DIR, "ipc_audit_trail.json")
ATTACHMENTS_DIR = os.path.join(BASE_DIR, "subcontract_attachments")
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "coral-idiom-265509-184c07e5e6c0.json")

os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

# معرفات الربط السحابي المركزية
SPREADSHEET_ID = "1UmTGZ_KKfyQnF4Qs0cbTb2kQlcZkvArLq_ctiE1NVFE"
DRIVE_FOLDER_ID = "12EROsINe-PstiDGhRqnQTAuW5GXxab9e"

# معرفات المجلدات الفرعية على Google Drive (هيكل المشروع المعتمد)
DRIVE_SUB_FOLDERS = {
    "contracts": "1UhZsc5J8Jz2Tf0j0U_7Ttfg9zjEfhUW8",      # Contracts_PDF
    "submissions": "17VU1v6H9YoyqRUEadco8sejnUbhsNrQM",    # Contractor_Submissions
    "certified": "1YZxrQQZbrxdlgb60t35I7pvBUre5pNlr",      # Certified_IPCs
    "boq": "1NJ3hm8sfpJYHQR5MIU9xWsUUEBusuMCi"              # BOQ_Sheets
}

# ─── الترويسات العربية الرسمية المعتمدة للشيتات ───
SUBCONTRACTS_HEADERS_AR = [
    "كود العقد", "رقم العقد", "مرجع طلب الشراء", "اسم المشروع",
    "تاريخ التعاقد", "تاريخ الإنجاز المطلوب", "اسم المقاول", "كود المقاول",
    "رقم الهاتف", "العملة", "إجمالي الأعمال التعاقدية", "ضريبة القيمة المضافة",
    "الإجمالي شامل الضريبة", "نسبة ضمان الأعمال %", "الدفعة المقدمة", "نسبة استرداد الدفعة %",
    "حالة العقد", "تاريخ الإنشاء", "رابط ملف العقد"
]

BOQ_HEADERS_AR = [
    "معرف البند", "كود العقد", "م", "كود البند",
    "توصيف الأعمال", "الوحدة", "الكمية التعاقدية", "فئة السعر", "الإجمالي"
]

SUBCONTRACTS_LINE_ITEMS_HEADERS = [
    "كود العقد", "رقم العقد", "اسم المشروع", "اسم المقاول", "رابط ملف العقد",
    "معرف البند", "م", "كود البند", "توصيف الأعمال", "الوحدة",
    "الكمية التعاقدية", "فئة السعر", "الإجمالي"
]

IPCS_HEADERS_AR = [
    "معرف المستخلص", "رقم المستخلص", "كود العقد", "رقم العقد",
    "اسم المقاول", "اسم المشروع", "تاريخ التقديم", "فترة الاستخلاص", "مصدر الإدخال",
    "إجمالي الأعمال الحالية", "استرداد الدفعة المقدمة", "ضمان الأعمال",
    "استقطاعات أخرى", "الصافي قبل الضريبة", "ضريبة القيمة المضافة",
    "صافي المستخلص المستحق", "حالة الاعتماد", "تاريخ الحفظ والاعتماد",
    "رابط مطالبة المقاول", "رابط المستخلص المعتمد"
]

IPC_ITEMS_HEADERS_AR = [
    "معرف المستخلص", "رقم المستخلص", "معرف البند", "توصيف الأعمال",
    "الوحدة", "الكمية التعاقدية", "الكمية السابقة", "الكمية الحالية", "الكمية التراكمية",
    "الكمية المتبقية", "فئة السعر", "القيمة الحالية", "القيمة التراكمية", "القيمة المتبقية"
]

IPCS_LINE_ITEMS_HEADERS = [
    "معرف المستخلص", "رقم المستخلص", "كود العقد", "رقم العقد",
    "اسم المقاول", "اسم المشروع", "رابط مطالبة المقاول",
    "معرف البند", "توصيف الأعمال", "الوحدة",
    "الكمية التعاقدية", "الكمية السابقة", "الكمية الحالية", "الكمية التراكمية",
    "الكمية المتبقية", "فئة السعر", "القيمة الحالية", "القيمة التراكمية", "القيمة المتبقية"
]

# ─── دوال الاتصال السحابي الآمنة (Fail-safe) ───
_LAST_GCLOUD_ERROR = ""

def get_gcloud_clients():
    global _LAST_GCLOUD_ERROR
    _LAST_GCLOUD_ERROR = ""
    if not G_CLOUD_AVAILABLE or not os.path.exists(SERVICE_ACCOUNT_FILE):
        _LAST_GCLOUD_ERROR = "المكتبات السحابية غير متوفرة أو ملف الاعتماد مفقود."
        return None, None
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        gs_client = gspread.authorize(creds)
        drive_service = build("drive", "v3", credentials=creds)
        return gs_client, drive_service
    except Exception as e:
        _LAST_GCLOUD_ERROR = f"{type(e).__name__}: {e}"
        return None, None

def push_drive_notice(kind, msg):
    st.session_state["contract_drive_flash"] = {"kind": kind, "msg": msg}
    if kind == "error":
        st.error(msg)
    elif kind == "warning":
        st.warning(msg)
    else:
        st.success(msg)

def guess_upload_mime(file_name):
    lower = str(file_name or "").lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    return "application/octet-stream"

def rewind_uploaded_file(uploaded_file):
    if uploaded_file is None:
        return
    seek_fn = getattr(uploaded_file, "seek", None)
    if callable(seek_fn):
        try:
            seek_fn(0)
        except Exception:
            pass

def persist_bytes_to_attachments(file_bytes, file_name, name_prefix):
    if not file_bytes:
        return ""
    if isinstance(file_bytes, memoryview):
        file_bytes = file_bytes.tobytes()
    raw_name = safe_str(file_name) or "contract.bin"
    safe_name = re.sub(r"[^\w.\-]+", "_", raw_name)
    dest = os.path.join(ATTACHMENTS_DIR, f"{name_prefix}_{uuid.uuid4().hex[:8]}_{safe_name}")
    with open(dest, "wb") as f:
        f.write(file_bytes)
    return dest

def persist_uploaded_file(uploaded_file, name_prefix):
    if uploaded_file is None:
        return ""
    rewind_uploaded_file(uploaded_file)
    raw_name = safe_str(getattr(uploaded_file, "name", "attachment.bin")) or "attachment.bin"
    payload = uploaded_file.getvalue()
    rewind_uploaded_file(uploaded_file)
    return persist_bytes_to_attachments(payload, raw_name, name_prefix)

def is_http_link(val):
    return str(val or "").strip().lower().startswith("http")

def save_and_upload_to_drive(uploaded_file, folder_id, name_prefix):
    """يحفظ المرفق محلياً باسم مؤقت ثم يرفعه فوراً ويعيد (المسار المحلي, webViewLink)."""
    return persist_and_upload_file(uploaded_file, name_prefix, folder_id)

def resolve_drive_link(existing_link, local_path, folder_id, drive_name=""):
    if is_http_link(existing_link):
        return existing_link
    path_to_upload = local_path if local_path and os.path.exists(local_path) else ""
    if not path_to_upload and existing_link and os.path.exists(str(existing_link)):
        path_to_upload = existing_link
    if not path_to_upload:
        return existing_link or ""
    name = drive_name or os.path.basename(path_to_upload)
    drive_link, _ = upload_file_to_drive(path_to_upload, name, folder_id)
    return drive_link or ""

def _coerce_file_bytes(file_source):
    if file_source is None:
        return None, "لا يوجد محتوى للرفع."
    if isinstance(file_source, memoryview):
        return file_source.tobytes(), None
    if isinstance(file_source, (bytes, bytearray)):
        return bytes(file_source), None
    if isinstance(file_source, str) and os.path.exists(file_source):
        with open(file_source, "rb") as fh:
            fh.seek(0)
            return fh.read(), None
    rewind_uploaded_file(file_source)
    if hasattr(file_source, "getvalue"):
        payload = file_source.getvalue()
        rewind_uploaded_file(file_source)
        return bytes(payload) if not isinstance(payload, bytes) else payload, None
    if hasattr(file_source, "read"):
        rewind_uploaded_file(file_source)
        payload = file_source.read()
        rewind_uploaded_file(file_source)
        if isinstance(payload, memoryview):
            payload = payload.tobytes()
        return bytes(payload) if payload is not None else None, None
    return None, "نوع مصدر الملف غير مدعوم للرفع."

def upload_file_to_drive(file_source, file_name=None, folder_id=DRIVE_FOLDER_ID):
    """يقبل بايتات أو ستريم أو مسار محلي، ينسخه إلى ATTACHMENTS_DIR ثم يرفعه إلى folder_id."""
    if not G_CLOUD_AVAILABLE:
        return None, "مكتبات gspread/googleapiclient غير مثبتة على السيرفر."
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        return None, f"ملف الاعتماد غير موجود ({SERVICE_ACCOUNT_FILE})."
    if not folder_id:
        return None, "معرف مجلد Drive فارغ."

    raw_bytes, coerce_err = _coerce_file_bytes(file_source)
    if not raw_bytes:
        return None, coerce_err or "تعذر قراءة بايتات الملف."

    display_name = file_name or getattr(file_source, "name", None) or "upload.bin"
    if isinstance(file_source, str) and os.path.exists(file_source) and not file_name:
        display_name = os.path.basename(file_source)
    local_copy = persist_bytes_to_attachments(raw_bytes, display_name, "drv")
    if not local_copy or not os.path.exists(local_copy):
        return None, "فشل إنشاء نسخة محلية مؤقتة داخل subcontract_attachments."

    try:
        _, drive_service = get_gcloud_clients()
        if not drive_service:
            detail = f" السبب: {_LAST_GCLOUD_ERROR}" if _LAST_GCLOUD_ERROR else ""
            return None, f"تعذر إنشاء عميل Drive.{detail}"
        file_metadata = {
            "name": os.path.basename(local_copy),
            "parents": [folder_id]
        }
        media = MediaFileUpload(local_copy, mimetype=guess_upload_mime(display_name), resumable=True)
        uploaded = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink, name",
            supportsAllDrives=True
        ).execute()
        file_id = uploaded.get("id")
        drive_link = uploaded.get("webViewLink") or (f"https://drive.google.com/file/d/{file_id}/view" if file_id else "")
        if drive_link:
            return drive_link, None
        return None, "اكتملت عملية الإنشاء دون إرجاع webViewLink أو معرف ملف."
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

def get_or_create_drive_subfolder(folder_name, parent_id=DRIVE_FOLDER_ID):
    _, drive_service = get_gcloud_clients()
    if not drive_service or not folder_name or not parent_id:
        return None
    try:
        query = (
            f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed = false"
        )
        found = drive_service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
            pageSize=5,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute().get("files") or []
        if found:
            return found[0].get("id")
        created = drive_service.files().create(
            body={
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id]
            },
            fields="id",
            supportsAllDrives=True
        ).execute()
        return created.get("id")
    except Exception:
        return None

def resolve_archive_folder(kind):
    """يرجع معرف المجلد الفرعي المعتمد من DRIVE_SUB_FOLDERS فقط."""
    key_map = {
        "contracts": "contracts",
        "submissions": "submissions",
        "certified": "certified",
        "boq": "boq",
        "ipcs": "submissions"
    }
    key = key_map.get(kind, kind)
    return DRIVE_SUB_FOLDERS.get(key) or DRIVE_FOLDER_ID

def persist_and_upload_file(uploaded_file, name_prefix, folder_id):
    rewind_uploaded_file(uploaded_file)
    local_path = persist_uploaded_file(uploaded_file, name_prefix)
    rewind_uploaded_file(uploaded_file)
    if not local_path:
        return "", ""
    drive_link, _ = upload_file_to_drive(local_path, os.path.basename(local_path), folder_id)
    return local_path, drive_link or ""

def sheet_hyperlink(url, label="فتح الملف"):
    if not is_http_link(url):
        return url or ""
    safe_url = str(url).replace('"', '""')
    safe_label = str(label).replace('"', '""')
    return f'=HYPERLINK("{safe_url}","{safe_label}")'

def setup_worksheet_safe(sh, title, headers):
    """يفتح الصفحة بالمسمى المحدد فقط عبر worksheet(title) ولا يرجع أبداً إلى sheet1."""
    try:
        try:
            ws = sh.worksheet(title)
        except Exception:
            ws = sh.add_worksheet(title=title, rows="1000", cols=str(max(len(headers) + 2, 26)))

        if not ws or getattr(ws, "title", "") != title:
            return None

        vals = ws.get_all_values()
        if not vals:
            ws.insert_row(headers, 1)
        elif vals[0] != headers:
            ws.update("A1", [headers])
        return ws
    except Exception:
        return None

def sync_contract_to_cloud(contract_dict, boq_list):
    gs_client, _ = get_gcloud_clients()
    if not gs_client:
        return False, "بيانات الاعتماد السحابية غير متوفرة."
    try:
        sh = gs_client.open_by_key(SPREADSHEET_ID)
        ws_contracts = setup_worksheet_safe(sh, "Subcontracts_Master", SUBCONTRACTS_HEADERS_AR)
        if not ws_contracts or ws_contracts.title != "Subcontracts_Master":
            return False, "تعذر فتح صفحة Subcontracts_Master."

        c_no = safe_str(contract_dict.get("contract_number")) or contract_dict.get("subcontract_id")
        local_doc = contract_dict.get("local_document_file") or ""
        drive_link = resolve_drive_link(
            contract_dict.get("document_file") or contract_dict.get("drive_contract_link") or "",
            local_doc,
            DRIVE_SUB_FOLDERS["contracts"],
            f"{c_no}_{os.path.basename(local_doc)}" if local_doc else ""
        )
        contract_dict["document_file"] = drive_link or ""
        contract_dict["drive_contract_link"] = drive_link or ""
        contract_link_cell = sheet_hyperlink(drive_link, "رابط ملف العقد")

        vnd = contract_dict.get("vendor", {})
        comm = contract_dict.get("commercial_terms", {})

        contract_row = [
            contract_dict.get("subcontract_id"),
            contract_dict.get("contract_number"),
            contract_dict.get("mr_pr_reference"),
            contract_dict.get("project_name"),
            contract_dict.get("contract_date"),
            contract_dict.get("delivery_date"),
            vnd.get("vendor_name"),
            vnd.get("vendor_id"),
            vnd.get("mobile_no"),
            comm.get("currency", "SAR"),
            safe_float(comm.get("total_amount")),
            safe_float(comm.get("total_vat")),
            safe_float(comm.get("total_including_vat")),
            safe_float(comm.get("retention_pct")),
            safe_float(comm.get("adv_payment_amt")),
            safe_float(comm.get("adv_recovery_pct")),
            contract_dict.get("status", "Active"),
            contract_dict.get("created_at"),
            contract_link_cell
        ]
        ws_contracts.append_row(contract_row, value_input_option="USER_ENTERED")

        ws_boq = setup_worksheet_safe(sh, "Subcontract_BOQ_Master", SUBCONTRACTS_LINE_ITEMS_HEADERS)
        if not ws_boq or ws_boq.title != "Subcontract_BOQ_Master":
            return False, "تعذر فتح صفحة Subcontract_BOQ_Master."
        boq_rows = []
        for itm in boq_list:
            boq_rows.append([
                contract_dict.get("subcontract_id"),
                contract_dict.get("contract_number"),
                contract_dict.get("project_name"),
                vnd.get("vendor_name"),
                contract_link_cell,
                itm.get("boq_item_id"),
                itm.get("sr_no"),
                itm.get("item_code"),
                itm.get("description"),
                itm.get("unit"),
                safe_float(itm.get("contract_qty")),
                safe_float(itm.get("unit_price")),
                safe_float(itm.get("total_amount"))
            ])
        if boq_rows:
            ws_boq.append_rows(boq_rows, value_input_option="USER_ENTERED")

        return True, "تمت المزامنة السحابية بنجاح."
    except Exception as e:
        return False, f"فشل ترحيل العقد للسحاب: {str(e)}"

def sync_ipc_to_cloud(ipc_dict):
    gs_client, _ = get_gcloud_clients()
    if not gs_client:
        return False, "بيانات الاعتماد السحابية غير متوفرة."
    try:
        sh = gs_client.open_by_key(SPREADSHEET_ID)
        ws_ipcs = setup_worksheet_safe(sh, "IPCs_Master", IPCS_HEADERS_AR)
        if not ws_ipcs or ws_ipcs.title != "IPCs_Master":
            return False, "تعذر فتح صفحة IPCs_Master."

        ipc_key = safe_str(ipc_dict.get("ipc_number")) or ipc_dict.get("ipc_id")
        claim_local = ipc_dict.get("local_contractor_claim_file") or ""
        claim_link = resolve_drive_link(
            ipc_dict.get("drive_submission_link") or ipc_dict.get("contractor_claim_file") or "",
            claim_local,
            DRIVE_SUB_FOLDERS["submissions"],
            f"{ipc_key}_claim_{os.path.basename(claim_local)}" if claim_local else ""
        )
        ipc_dict["drive_submission_link"] = claim_link or ""
        if is_http_link(claim_link):
            ipc_dict["contractor_claim_file"] = claim_link
        claim_link_cell = sheet_hyperlink(claim_link, "رابط مطالبة المقاول")

        certified_links = []
        existing_certified = ipc_dict.get("drive_certified_link") or ""
        if is_http_link(existing_certified):
            certified_links.extend([p.strip() for p in existing_certified.split("|") if p.strip() and is_http_link(p.strip())])
        certified_candidates = []
        if ipc_dict.get("certified_file"):
            certified_candidates.append(ipc_dict.get("certified_file"))
        for p in ipc_dict.get("local_support_files") or ipc_dict.get("support_files") or []:
            certified_candidates.append(p)
        seen = set(certified_links)
        for idx, c_path in enumerate(certified_candidates):
            if is_http_link(c_path):
                if c_path not in seen:
                    certified_links.append(c_path)
                    seen.add(c_path)
                continue
            if c_path and os.path.exists(c_path):
                uploaded_certified, _ = upload_file_to_drive(
                    c_path,
                    f"{ipc_key}_certified_{idx+1}_{os.path.basename(c_path)}",
                    DRIVE_SUB_FOLDERS["certified"]
                )
                if uploaded_certified and uploaded_certified not in seen:
                    certified_links.append(uploaded_certified)
                    seen.add(uploaded_certified)
        ipc_dict["drive_certified_link"] = " | ".join(certified_links)
        certified_link_cell = sheet_hyperlink(certified_links[0] if certified_links else "", "رابط المستخلص المعتمد")
        if len(certified_links) > 1:
            certified_link_cell = " | ".join([sheet_hyperlink(u, "مرفق معتمد") for u in certified_links])

        ipc_row = [
            ipc_dict.get("ipc_id"),
            ipc_dict.get("ipc_number"),
            ipc_dict.get("subcontract_id"),
            ipc_dict.get("contract_number"),
            ipc_dict.get("contractor_name"),
            ipc_dict.get("project_name"),
            ipc_dict.get("ipc_date"),
            ipc_dict.get("billing_period"),
            ipc_dict.get("source"),
            safe_float(ipc_dict.get("current_gross_amount")),
            safe_float(ipc_dict.get("advance_recovery")),
            safe_float(ipc_dict.get("retention_amount")),
            safe_float(ipc_dict.get("other_deductions_total")),
            safe_float(ipc_dict.get("subtotal_before_vat")),
            safe_float(ipc_dict.get("vat_amount")),
            safe_float(ipc_dict.get("net_ipc_amount")),
            ipc_dict.get("status", "Draft"),
            ipc_dict.get("created_at"),
            claim_link_cell,
            certified_link_cell
        ]
        ws_ipcs.append_row(ipc_row, value_input_option="USER_ENTERED")

        ws_ipc_items = setup_worksheet_safe(sh, "IPC_Items_Detail", IPCS_LINE_ITEMS_HEADERS)
        if not ws_ipc_items or ws_ipc_items.title != "IPC_Items_Detail":
            return False, "تعذر فتح صفحة IPC_Items_Detail."
        detail_rows = []
        for itm in ipc_dict.get("items", []):
            detail_rows.append([
                ipc_dict.get("ipc_id"),
                ipc_dict.get("ipc_number"),
                ipc_dict.get("subcontract_id"),
                ipc_dict.get("contract_number"),
                ipc_dict.get("contractor_name"),
                ipc_dict.get("project_name"),
                claim_link_cell,
                itm.get("boq_item_id"),
                itm.get("description"),
                itm.get("unit"),
                safe_float(itm.get("contract_qty")),
                safe_float(itm.get("prev_qty")),
                safe_float(itm.get("current_qty")),
                safe_float(itm.get("cum_qty")),
                safe_float(itm.get("remaining_qty")),
                safe_float(itm.get("unit_price")),
                safe_float(itm.get("current_amt")),
                safe_float(itm.get("cum_amt")),
                safe_float(itm.get("remaining_amt"))
            ])
        if detail_rows:
            ws_ipc_items.append_rows(detail_rows, value_input_option="USER_ENTERED")

        return True, "تمت مزامنة المستخلص بنجاح مع Google Sheets."
    except Exception as e:
        return False, f"فشل ترحيل المستخلص للسحاب: {str(e)}"

# ─── دوال التنظيف والحماية الحسابية ───
def safe_str(val):
    if val is None:
        return ""
    return str(val).strip()

def safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        clean_val = str(val).replace(",", "").replace("(", "-").replace(")", "").strip()
        return float(clean_val)
    except (ValueError, TypeError):
        return default

def number_to_words_ar(num, currency="SAR"):
    curr_map = {
        "SAR": "ريال سعودي",
        "EGP": "جنيه مصري",
        "AED": "درهم إماراتي",
        "USD": "دولار أمريكي"
    }
    curr_label = curr_map.get(currency, currency)
    units = ["", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة"]
    teens = ["عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"]
    tens = ["", "عشرة", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
    hundreds = ["", "مائة", "مائتان", "ثلاثمائة", "أربعمائة", "خمسمائة", "ستمائة", "سبعمائة", "ثمانمائة", "تسعمائة"]
    
    n = int(round(num))
    if n == 0:
        return f"صفر {curr_label} فقط لا غير"
    if n < 0:
        return f"سالب {number_to_words_ar(abs(n), currency)}"
    
    parts = []
    billions = n // 1000000000
    millions = (n % 1000000000) // 1000000
    thousands = (n % 1000000) // 1000
    remainder = n % 1000

    def convert_block(val):
        res = []
        h = val // 100
        t = (val % 100) // 10
        u = val % 10
        if h > 0:
            res.append(hundreds[h])
        if t == 1:
            res.append(teens[u])
        else:
            if u > 0:
                res.append(units[u])
            if t > 0:
                res.append(tens[t])
        return " و ".join(res)

    if billions > 0:
        parts.append(convert_block(billions) + " مليار")
    if millions > 0:
        parts.append(convert_block(millions) + " مليون")
    if thousands > 0:
        parts.append(convert_block(thousands) + " ألف")
    if remainder > 0:
        parts.append(convert_block(remainder))

    text = " و ".join(parts)
    return f"{text} {curr_label} فقط لا غير"

def load_json_data(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []
    return []

def save_json_data(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception:
        return False

def get_contract_consumption_metrics(subcontract_id, contract_total_val, ipc_history):
    consumed_val = 0.0
    for ipc in ipc_history:
        if ipc.get("subcontract_id") == subcontract_id and is_certified_ipc_status(ipc.get("status")):
            consumed_val += safe_float(ipc.get("current_gross_amount", ipc.get("subtotal_current", 0.0)))
    
    remaining_val = contract_total_val - consumed_val
    progress_pct = (consumed_val / contract_total_val * 100.0) if contract_total_val > 0 else 0.0
    return consumed_val, remaining_val, progress_pct

def get_previous_accumulated_qty(subcontract_id, boq_item_id, item_desc, ipc_history):
    total_prev = 0.0
    for old_ipc in ipc_history:
        if old_ipc.get("subcontract_id") == subcontract_id and is_certified_ipc_status(old_ipc.get("status")):
            for past_itm in old_ipc.get("items", []):
                id_match = (boq_item_id and past_itm.get("boq_item_id") == boq_item_id)
                desc_match = (safe_str(past_itm.get("description")).lower() == safe_str(item_desc).lower())
                if id_match or desc_match:
                    total_prev += safe_float(past_itm.get("current_qty", 0.0))
    return total_prev

def canonical_ipc_status(status):
    mapping = {
        "Draft": "Draft", "مسودة": "Draft",
        "Submitted": "Submitted", "مقدم": "Submitted",
        "Under Review": "Under Review", "قيد المراجعة": "Under Review",
        "Returned": "Returned", "مرتجع": "Returned",
        "Approved": "Approved", "معتمد": "Approved",
        "Paid": "Paid", "مدفوع": "Paid"
    }
    return mapping.get(safe_str(status), safe_str(status) or "Draft")

def is_certified_ipc_status(status):
    return canonical_ipc_status(status) in ("Approved", "Paid")

def to_excel_download_button(df, filename, button_label, key):
    if df is None or getattr(df, "empty", True):
        st.caption("لا توجد بيانات للتصدير حالياً.")
        return
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Export"[:31])
    st.download_button(
        label=button_label,
        data=buffer.getvalue(),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key
    )

def append_ipc_audit(ipc_id, action, user, field_changed="", old_value="", new_value="", reason=""):
    trail = load_json_data(IPC_AUDIT_FILE)
    trail.append({
        "audit_id": f"AUD-{uuid.uuid4().hex[:10]}",
        "ipc_id": ipc_id or "",
        "action": action,
        "field_changed": field_changed or "",
        "old_value": "" if old_value is None else str(old_value),
        "new_value": "" if new_value is None else str(new_value),
        "user": user or "User",
        "timestamp": str(datetime.datetime.now()),
        "reason": reason or ""
    })
    save_json_data(IPC_AUDIT_FILE, trail)

def append_status_history(ipc_rec, status, user, comment=""):
    hist = list(ipc_rec.get("status_history") or [])
    hist.append({
        "status": status,
        "user": user or "User",
        "timestamp": str(datetime.datetime.now()),
        "comment": comment or ""
    })
    ipc_rec["status_history"] = hist

def enrich_ipc_item_qty_fields(item):
    c_qty = safe_float(item.get("contract_qty"))
    p_qty = safe_float(item.get("prev_qty"))
    certified = safe_float(item.get("current_qty"))
    if item.get("submitted_qty") is None:
        item["submitted_qty"] = certified
    submitted = safe_float(item.get("submitted_qty"))
    qty_diff = round(submitted - certified, 6)
    item["qty_difference"] = qty_diff
    if abs(qty_diff) > 0.0001:
        item["difference_reason"] = item.get("difference_reason") or "فروقات اعتماد عن الكمية المقدمة من المقاول"
    else:
        item["difference_reason"] = item.get("difference_reason") or ""
    cum_qty = p_qty + certified
    item["cum_qty"] = cum_qty
    item["remaining_qty"] = c_qty - cum_qty
    item["completion_pct"] = round((cum_qty / c_qty * 100.0), 4) if c_qty > 0 else 0.0
    item["qty_overrun"] = cum_qty > (c_qty + 0.0001)
    return item

def collect_quantity_overruns(contracts, boq_items, ipc_history):
    flags = []
    for c in contracts:
        sc_id = c.get("subcontract_id")
        for b_item in [b for b in boq_items if b.get("subcontract_id") == sc_id]:
            certified_cum = get_previous_accumulated_qty(sc_id, b_item.get("boq_item_id"), b_item.get("description"), ipc_history)
            c_qty = safe_float(b_item.get("contract_qty"))
            if certified_cum > c_qty + 0.0001:
                flags.append({
                    "رقم العقد": c.get("contract_number"),
                    "المقاول": c.get("vendor", {}).get("vendor_name"),
                    "البند": b_item.get("description"),
                    "الكمية التعاقدية": c_qty,
                    "الكمية المعتمدة التراكمية": certified_cum,
                    "التجاوز": round(certified_cum - c_qty, 4),
                    "العلم": "تجاوز كمية"
                })
    return flags

# ─── محرك استخراج وتفريغ المستخلص عبر Gemini بالموديل المستقر ───
def extract_and_match_ipc_via_gemini(uploaded_file, contract_obj, contract_items, api_key):
    if not api_key:
        return None, "مفتاح Google AI API غير متوفر."
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.5-flash-lite")
        rewind_uploaded_file(uploaded_file)
        file_bytes = uploaded_file.getvalue()
        rewind_uploaded_file(uploaded_file)
        file_mime = uploaded_file.type or "application/pdf"
        
        contract_boq_summary = []
        for itm in contract_items:
            contract_boq_summary.append({
                "boq_item_id": itm.get("boq_item_id"),
                "description": itm.get("description"),
                "contract_price": itm.get("unit_price"),
                "unit": itm.get("unit"),
                "contract_qty": itm.get("contract_qty")
            })

        prompt = f"""
        أنت مهندس مكتب فني ومراجع حسابات كميات وتدقيق عقود خبير جداً.
        أمامك صورة أو ملف مستخلص/فاتورة ضريبية مرفوعة من مقاول باطن.
        
        بيانات العقد المعتمد في النظام:
        - رقم العقد: {contract_obj.get('contract_number')}
        - اسم المقاول: {contract_obj.get('vendor', {}).get('vendor_name')}
        - بنود المقايسة التعاقدية الرسمية المعتمدة وأسعارها:
        {json.dumps(contract_boq_summary, ensure_ascii=False)}

        المطلوب بدقة شديدة:
        1. استخرج رقم الفاتورة/المستخلص، وتاريخه، وفترة الاستخلاص (مثال: شهر 05 / 2023 أو May 2023).
        2. طابق كل بند في الفاتورة المرفوعة مع البند المقابل له في العقد المعتمد أعلاه.
        3. قواعد تسعير وحساب هندسية حاسمة:
           - سعر الوحدة التعاقدي المعتمد في العقد (Contract Price) هو الأصل الصارم ولا يجوز تغييره.
           - إذا نزل المقاول في الفاتورة مبلغاً جزئياً (مثل 18 يوماً من أصل شهر مقطوع بسعر 18,200)، فاحسب الكمية المنفذة المستحقة كنسبة = المبلغ المطالب به مقسوماً على فئة سعر العقد (مثال: 10,920 / 18,200 = 0.60 شهر).
           - إذا كانت الفئة المدونة في الفاتورة تختلف عن فئة العقد ولم يكن المبلغ ناتج نسبة زمنية، دوّن تنبيهاً صريحاً (price_discrepancy: true).
        
        أخرج النتيجة بصيغة JSON فقط:
        {{
          "ipc_number": "رقم المستخلص أو الفاتورة",
          "ipc_date": "YYYY-MM-DD",
          "billing_period": "فترة الفاتورة",
          "matched_items": [
            {{
              "boq_item_id": "معرف البند المطابق من العقد",
              "contract_description": "توصيف البند في العقد",
              "invoice_raw_description": "النص المكتوب في الفاتورة",
              "unit": "الوحدة التعاقدية",
              "contract_unit_price": 0.0,
              "contract_qty": 0.0,
              "invoice_unit_price": 0.0,
              "executed_qty": 0.0,
              "claimed_amount": 0.0,
              "price_discrepancy": false,
              "discrepancy_note": "ملاحظة تدقيقية إن وجدت"
            }}
          ]
        }}
        """
        response = model.generate_content([
            {"mime_type": file_mime, "data": file_bytes},
            prompt
        ])
        txt = response.text.strip()
        if txt.startswith("```json"):
            txt = txt[7:-3].strip()
        elif txt.startswith("```"):
            txt = txt[3:-3].strip()
        data = json.loads(txt)
        return data, None
    except Exception as e:
        return None, f"تعذر استخراج بيانات المستخلص وتدقيقها: {str(e)}"

def extract_contract_via_gemini(uploaded_file, api_key):
    if not api_key:
        return None, "مفتاح Google AI API غير متوفر."
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.5-flash-lite")
        rewind_uploaded_file(uploaded_file)
        file_bytes = uploaded_file.getvalue()
        rewind_uploaded_file(uploaded_file)
        file_mime = uploaded_file.type or "application/pdf"
        
        prompt = """
        أنت مهندس عقود ومكتب فني خبير. استخرج بيانات أمر الشراء أو العقد بدقة بصيغة JSON فقط:
        {
          "contract_number": "رقم أمر الشراء PO أو رقم العقد",
          "mr_pr_reference": "طلب الشراء PR أو طلب المواد MR",
          "contract_date": "YYYY-MM-DD",
          "delivery_date": "YYYY-MM-DD",
          "buyer_name": "مسؤول التعاقد أو المشتري",
          "buyer_contact": "رقم اتصال مسؤول التعاقد",
          "vendor": {
            "vendor_name": "اسم شركة المقاول أو المورد",
            "vendor_id": "كود المورد إن وجد",
            "contact_name": "الشخص المسؤول لدى المقاول",
            "mobile_no": "رقم الهاتف أو الجوال",
            "email": "البريد الإلكتروني",
            "address": "العنوان والمقر"
          },
          "commercial_terms": {
            "currency": "SAR أو EGP أو AED أو USD",
            "payment_term": "شروط السداد",
            "payment_method": "طريقة الدفع",
            "adv_payment_amt": 0.0,
            "adv_recovery_pct": 0.0,
            "retention_pct": 0.0,
            "vat_pct": 15.0,
            "special_terms": "الشروط والملاحظات الخاصة كاملة"
          },
          "boq_items": [
            {
              "sr_no": 1,
              "item_code": "كود البند",
              "description": "توصيف البند بالكامل",
              "unit": "الوحدة",
              "contract_qty": 0.0,
              "unit_price": 0.0,
              "vat_amount": 0.0,
              "total_amount": 0.0
            }
          ]
        }
        """
        response = model.generate_content([
            {"mime_type": file_mime, "data": file_bytes},
            prompt
        ])
        txt = response.text.strip()
        if txt.startswith("```json"):
            txt = txt[7:-3].strip()
        elif txt.startswith("```"):
            txt = txt[3:-3].strip()
        return json.loads(txt), None
    except Exception as e:
        return None, f"تعذر استخراج بيانات العقد: {str(e)}"

def format_special_terms_as_numbered_list(terms_text):
    if not terms_text or not str(terms_text).strip():
        return "<p style='margin:0; color:#64748b;'>تطبق الشروط والمواصفات القياسية للمشروع.</p>"
    text = str(terms_text).strip()
    parts = re.split(r'(?:\r?\n|;|\b(?=\d+[\.\-\)]))', text)
    clean_parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
    if not clean_parts:
        clean_parts = [text]

    html_list = "<div class='rtl-strict' style='direction:rtl !important; text-align:right !important; font-family:Cairo, sans-serif; unicode-bidi:isolate;'><ol style='margin: 6px 0; padding-right: 24px; padding-left: 0; color:#1e293b; line-height: 1.7;'>"
    for part in clean_parts:
        cleaned_item = re.sub(r'^\d+[\.\-\)]\s*', '', part)
        html_list += f"<li style='margin-bottom: 6px; font-size:12.5px; direction:rtl; text-align:right;'>{html.escape(cleaned_item)}</li>"
    html_list += "</ol></div>"
    return html_list

def render_printable_contract_html(data, items, selected_proj):
    c_num = safe_str(data.get("contract_number"))
    pr_num = safe_str(data.get("mr_pr_reference"))
    c_date = safe_str(data.get("contract_date"))
    d_date = safe_str(data.get("delivery_date"))
    buyer = safe_str(data.get("buyer_name"))
    b_phone = safe_str(data.get("buyer_contact"))
    
    v_name = safe_str(data.get("vendor_name"))
    v_id = safe_str(data.get("vendor_id"))
    v_contact = safe_str(data.get("contact_name"))
    v_phone = safe_str(data.get("mobile_no"))

    curr = safe_str(data.get("currency"))
    p_term = safe_str(data.get("payment_term"))
    p_method = safe_str(data.get("payment_method"))
    adv = safe_float(data.get("adv_payment_amt"))
    ret = safe_float(data.get("retention_pct"))
    vat_p = safe_float(data.get("vat_pct", 15.0))
    spec = safe_str(data.get("special_terms"))

    subtotal = sum(safe_float(i.get("contract_qty")) * safe_float(i.get("unit_price")) for i in items)
    vat_total = subtotal * (vat_p / 100.0)
    grand_total = subtotal + vat_total
    tafeet = number_to_words_ar(grand_total, curr)

    items_html = ""
    for itm in items:
        q = safe_float(itm.get("contract_qty"))
        p = safe_float(itm.get("unit_price"))
        tot = q * p
        items_html += f"""
        <tr>
            <td style="text-align:center; padding:6px; border:1px solid #cbd5e1;">{itm.get('sr_no', '')}</td>
            <td style="text-align:center; padding:6px; border:1px solid #cbd5e1;">{safe_str(itm.get('item_code'))}</td>
            <td style="text-align:right; padding:6px; border:1px solid #cbd5e1;">{safe_str(itm.get('description'))}</td>
            <td style="text-align:center; padding:6px; border:1px solid #cbd5e1;">{safe_str(itm.get('unit'))}</td>
            <td style="text-align:center; padding:6px; border:1px solid #cbd5e1;">{q:,.2f}</td>
            <td style="text-align:center; padding:6px; border:1px solid #cbd5e1;">{p:,.2f}</td>
            <td style="text-align:center; padding:6px; border:1px solid #cbd5e1; font-weight:bold;">{tot:,.2f}</td>
        </tr>
        """

    terms_formatted_html = format_special_terms_as_numbered_list(spec)

    html = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, Tahoma, sans-serif; margin: 0; padding: 10px; color: #0F172A; background: #ffffff; }}
        .contract-box {{ background: #ffffff; border: 2px solid #0F2545; border-radius: 8px; padding: 24px; }}
        .print-btn-bar {{ display: flex; justify-content: flex-end; margin-bottom: 15px; }}
        .btn-print {{ background-color: #0284c7; color: #ffffff; border: none; padding: 8px 18px; font-size: 14px; font-weight: bold; border-radius: 6px; cursor: pointer; }}
        @media print {{ body {{ background: #ffffff; padding: 0; }} .print-btn-bar {{ display: none; }} .contract-box {{ border: none; padding: 0; }} }}
    </style>
    </head>
    <body>
        <div class="print-btn-bar">
            <button class="btn-print" onclick="window.print();">طباعة أمر الشراء / العقد</button>
        </div>
        <div class="contract-box">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom: 2px solid #0F2545; padding-bottom: 12px; margin-bottom: 15px;">
                <div>
                    <h2 style="margin:0; color:#0F2545;">شركة اليُسر للمقاولات</h2>
                    <p style="margin:3px 0 0 0; color:#475569; font-size:14px;">أمر شراء / عقد مقاولة باطن • المشروع: <b>{selected_proj}</b></p>
                </div>
                <div style="text-align:left; direction:ltr;">
                    <h3 style="margin:0; color:#0284c7;">PO: {c_num}</h3>
                    <p style="margin:2px 0 0 0; font-size:13px; color:#475569;">PR Ref: {pr_num}</p>
                    <p style="margin:0; font-size:12px; color:#475569;">Date: {c_date}</p>
                </div>
            </div>

            <table style="width:100%; border-collapse:collapse; margin-bottom:15px; font-size:13px;">
                <tr style="background:#f8fafc;">
                    <th colspan="2" style="border:1px solid #cbd5e1; padding:6px; text-align:right; color:#0F2545;">بيانات الطرف الأول (المشتري / الإدارة)</th>
                    <th colspan="2" style="border:1px solid #cbd5e1; padding:6px; text-align:right; color:#0F2545;">بيانات الطرف الثاني (المقاول / المورد)</th>
                </tr>
                <tr>
                    <td style="border:1px solid #cbd5e1; padding:6px; width:18%;"><b>مسؤول التعاقد:</b></td>
                    <td style="border:1px solid #cbd5e1; padding:6px; width:32%;">{buyer}</td>
                    <td style="border:1px solid #cbd5e1; padding:6px; width:18%;"><b>اسم المقاول:</b></td>
                    <td style="border:1px solid #cbd5e1; padding:6px; width:32%;">{v_name}</td>
                </tr>
                <tr>
                    <td style="border:1px solid #cbd5e1; padding:6px;"><b>هاتف الاتصال:</b></td>
                    <td style="border:1px solid #cbd5e1; padding:6px;">{b_phone}</td>
                    <td style="border:1px solid #cbd5e1; padding:6px;"><b>كود المقاول:</b></td>
                    <td style="border:1px solid #cbd5e1; padding:6px;">{v_id}</td>
                </tr>
                <tr>
                    <td style="border:1px solid #cbd5e1; padding:6px;"><b>تاريخ الإنجاز:</b></td>
                    <td style="border:1px solid #cbd5e1; padding:6px;">{d_date}</td>
                    <td style="border:1px solid #cbd5e1; padding:6px;"><b>المسؤول / الهاتف:</b></td>
                    <td style="border:1px solid #cbd5e1; padding:6px;">{v_contact} - {v_phone}</td>
                </tr>
            </table>

            <table style="width:100%; border-collapse:collapse; margin-bottom:15px; font-size:12px;">
                <thead>
                    <tr style="background:#0F2545; color:#ffffff;">
                        <th style="border:1px solid #0F2545; padding:6px; width:6%;">م</th>
                        <th style="border:1px solid #0F2545; padding:6px; width:16%;">كود البند</th>
                        <th style="border:1px solid #0F2545; padding:6px; width:40%;">توصيف الأعمال</th>
                        <th style="border:1px solid #0F2545; padding:6px; width:10%;">الوحدة</th>
                        <th style="border:1px solid #0F2545; padding:6px; width:12%;">الكمية</th>
                        <th style="border:1px solid #0F2545; padding:6px; width:12%;">السعر</th>
                        <th style="border:1px solid #0F2545; padding:6px; width:14%;">الإجمالي</th>
                    </tr>
                </thead>
                <tbody>
                    {items_html}
                </tbody>
            </table>

            <div style="display:flex; justify-content:space-between; margin-bottom:15px; font-size:13px;">
                <div style="width:58%; background:#f8fafc; border:1px solid #cbd5e1; padding:12px; border-radius:6px;">
                    <b style="color:#0F2545;">الشروط والأحكام الخاصة بالتعاقد:</b>
                    <div style="margin-top:4px; font-size:12px; color:#475569;">
                        - شروط السداد: <b>{p_term}</b> | طريقة الدفع: <b>{p_method}</b><br>
                        - نسبة ضمان الأعمال: <b>{ret}%</b> | الدفعة المقدمة: <b>{adv:,.2f} {curr}</b><br>
                        - ضريبة القيمة المضافة: <b>{vat_p}%</b>
                    </div>
                    <div style="margin-top:8px; border-top:1px dashed #cbd5e1; padding-top:6px;">
                        <b style="font-size:12px; color:#0F2545;">المحددات والبنود الخاصة:</b>
                        {terms_formatted_html}
                    </div>
                </div>
                <div style="width:38%; background:#f8fafc; border:1px solid #cbd5e1; padding:12px; border-radius:6px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                        <span>إجمالي الأعمال:</span><b>{subtotal:,.2f} {curr}</b>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                        <span>ضريبة القيمة المضافة ({vat_p}%):</span><b>{vat_total:,.2f} {curr}</b>
                    </div>
                    <div style="display:flex; justify-content:space-between; border-top:1px solid #cbd5e1; padding-top:4px; font-size:14px; color:#0F2545; font-weight:bold;">
                        <span>الإجمالي الصافي:</span><b>{grand_total:,.2f} {curr}</b>
                    </div>
                    <div style="font-size:11px; margin-top:6px; color:#475569;">فقط وقدره: {tafeet}</div>
                </div>
            </div>

            <div style="display:flex; justify-content:space-between; margin-top:35px; padding-top:15px; border-top:1px dashed #94a3b8; font-size:13px;">
                <div style="text-align:center; width:30%;">
                    <b>إعداد ومراجعة (المكتب الفني)</b><br><br><br>
                    التوقيع: ...........................
                </div>
                <div style="text-align:center; width:30%;">
                    <b>الرقابة المالية والمشروع</b><br><br><br>
                    التوقيع: ...........................
                </div>
                <div style="text-align:center; width:30%;">
                    <b>اعتماد مقاول الباطن</b><br><br><br>
                    الختم والتوقيع: ...........................
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html

def render_printable_ipc_sheet_html(ipc_header, items, totals, c_curr):
    rows_html = ""
    for itm in items:
        rows_html += f"""
        <tr>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8;">{itm.get('sr_no')}</td>
            <td style="text-align:right; padding:6px; border:1px solid #94a3b8;">{itm.get('description')}</td>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8;">{itm.get('unit')}</td>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8;">{itm.get('contract_qty'):,.2f}</td>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8;">{itm.get('prev_qty'):,.4f}</td>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8; font-weight:bold; background:#fffbeb;">{itm.get('current_qty'):,.4f}</td>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8;">{itm.get('cum_qty'):,.4f}</td>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8;">{itm.get('remaining_qty'):,.4f}</td>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8;">{itm.get('unit_price'):,.2f}</td>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8; font-weight:bold; background:#fffbeb;">{itm.get('current_amt'):,.2f}</td>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8;">{itm.get('cum_amt'):,.4f}</td>
            <td style="text-align:center; padding:6px; border:1px solid #94a3b8;">{itm.get('remaining_amt'):,.4f}</td>
        </tr>
        """

    tafeet_current = number_to_words_ar(totals['net_ipc_amount'], c_curr)

    deductions_rows = ""
    for od in totals.get("other_deductions_list", []):
        deductions_rows += f"""
        <div style="display:flex; justify-content:space-between; margin-bottom:2px; color:#b91c1c;">
            <span>(-) {od.get('description')} ({od.get('reference', '')}):</span>
            <b>({safe_float(od.get('amount')):,.2f}) {c_curr}</b>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
    <meta charset="utf-8">
    <style>
        @page {{ size: A4 landscape; margin: 8mm; }}
        body {{
            font-family: Arial, Tahoma, sans-serif;
            margin: 0; padding: 10px; color: #0F172A; background: #ffffff;
            font-feature-settings: "tnum"; font-variant-numeric: tabular-nums;
        }}
        .print-container {{ width: 100%; }}
        .header-table {{ width: 100%; border-collapse: collapse; margin-bottom: 8px; }}
        .header-table td {{ padding: 4px 8px; font-size: 13px; }}
        .sheet-table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 12px; }}
        .sheet-table th {{
            background-color: #0F2545; color: #ffffff; padding: 8px 4px;
            border: 1px solid #0F2545; text-align: center; font-size: 12px;
        }}
        .row-subtotal {{ background-color: #ffedd5; font-weight: bold; border-top: 2px solid #ea580c; font-size: 13px; }}
        .signatures {{ display: flex; justify-content: space-between; margin-top: 35px; padding-top: 15px; border-top: 1px dashed #94a3b8; font-size: 13px; text-align: center; }}
        .sig-box {{ width: 23%; }}
        .btn-print {{ background: #0284c7; color: #fff; padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; margin-bottom: 12px; }}
        @media print {{ .no-print {{ display: none; }} body {{ padding: 0; }} }}
    </style>
    </head>
    <body>
        <div class="no-print" style="text-align:left;">
            <button class="btn-print" onclick="window.print();">طباعة المستخلص المعتمد (A4 Landscape)</button>
        </div>
        <div class="print-container">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; border-bottom:2px solid #0F2545; padding-bottom:6px;">
                <div>
                    <h2 style="margin:0; color:#0F2545; font-size:19px;">شركة اليُسر للهندسة والمقاولات</h2>
                    <p style="margin:2px 0 0 0; color:#475569; font-size:12px;">مستخلص ختامي وصافي أعمال مقاولي الباطن (Net IPC Summary)</p>
                </div>
                <div style="text-align:left; direction:ltr;">
                    <span style="font-size:15px; font-weight:bold; color:#0284c7;">{ipc_header.get('ipc_number')}</span>
                </div>
            </div>
            
            <table class="header-table" style="border: 1px solid #cbd5e1; background: #f8fafc;">
                <tr>
                    <td style="width:15%;"><b>المشروع:</b></td>
                    <td style="width:35%;">{ipc_header.get('project_name')}</td>
                    <td style="width:15%;"><b>رقم المستخلص:</b></td>
                    <td style="width:35%; font-weight:bold; color:#0F2545;">{ipc_header.get('ipc_number')}</td>
                </tr>
                <tr>
                    <td><b>مقاول الباطن:</b></td>
                    <td>{ipc_header.get('contractor_name')}</td>
                    <td><b>تاريخ التقديم:</b></td>
                    <td>{ipc_header.get('ipc_date')}</td>
                </tr>
                <tr>
                    <td><b>رقم العقد:</b></td>
                    <td>{ipc_header.get('contract_number')}</td>
                    <td><b>فترة الاستخلاص:</b></td>
                    <td>{ipc_header.get('billing_period', '-')} ({ipc_header.get('source', 'مقدم من المقاول')})</td>
                </tr>
            </table>

            <table class="sheet-table">
                <thead>
                    <tr>
                        <th style="width:3%;">م</th>
                        <th style="width:23%;">توصيف الأعمال</th>
                        <th style="width:4%;">الوحدة</th>
                        <th style="width:7%;">الكمية التعاقدية</th>
                        <th style="width:7%;">الكمية السابقة</th>
                        <th style="width:7%; background:#eab308; color:#0F2545;">الكمية الحالية</th>
                        <th style="width:7%;">الكمية التراكمية</th>
                        <th style="width:7%;">الكمية المتبقية</th>
                        <th style="width:7%;">فئة السعر</th>
                        <th style="width:10%; background:#eab308; color:#0F2545;">القيمة الحالية</th>
                        <th style="width:9%;">القيمة التراكمية</th>
                        <th style="width:9%;">القيمة المتبقية</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                    <tr class="row-subtotal">
                        <td colspan="9" style="text-align:center; padding:8px; border:1px solid #ea580c;">إجمالي الأعمال المنفذة (Gross Amounts)</td>
                        <td style="text-align:center; padding:8px; border:1px solid #ea580c; background:#fed7aa; color:#9a3412;">{totals['current_gross_amount']:,.2f}</td>
                        <td style="text-align:center; padding:8px; border:1px solid #ea580c;">{totals['cumulative_gross_amount']:,.2f}</td>
                        <td style="text-align:center; padding:8px; border:1px solid #ea580c;">{totals['remaining_gross_amount']:,.2f}</td>
                    </tr>
                </tbody>
            </table>

            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-top:10px;">
                <div style="width:52%; font-size:12px; color:#475569; padding:12px; border:1px solid #cbd5e1; border-radius:6px; background:#fafafa;">
                    <b>الشروط التجارية والاستقطاعات المعتمدة:</b><br>
                    - نسبة استرداد الدفعة المقدمة: {totals['adv_pct']}%<br>
                    - نسبة استقطاع ضمان الأعمال: {totals['ret_pct']}%<br>
                    - نسبة ضريبة القيمة المضافة: {totals['vat_pct']}%<br>
                    <div style="margin-top:6px; border-top:1px dashed #cbd5e1; padding-top:6px;">
                        <b>تفاصيل الاستقطاعات الأخرى:</b>
                        {deductions_rows if deductions_rows else '<div>لا توجد استقطاعات إضافية مسجلة.</div>'}
                    </div>
                </div>

                <div style="width:44%; background:#f8fafc; border:1px solid #cbd5e1; padding:12px; border-radius:6px; font-size:13px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                        <span>إجمالي الأعمال الحالية:</span>
                        <b>{totals['current_gross_amount']:,.2f} {c_curr}</b>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-bottom:5px; color:#b91c1c;">
                        <span>(-) استرداد الدفعة المقدمة:</span>
                        <b>({totals['adv_recovery']:,.2f}) {c_curr}</b>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-bottom:5px; color:#b91c1c;">
                        <span>(-) ضمان الأعمال:</span>
                        <b>({totals['retention_amount']:,.2f}) {c_curr}</b>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-bottom:5px; color:#b91c1c;">
                        <span>(-) استقطاعات أخرى:</span>
                        <b>({totals['other_deductions_total']:,.2f}) {c_curr}</b>
                    </div>
                    <div style="display:flex; justify-content:space-between; border-top:1px solid #cbd5e1; padding-top:6px; font-weight:bold; color:#0F2545;">
                        <span>الوعاء الخاضع للضريبة:</span>
                        <b>{totals['subtotal_before_vat']:,.2f} {c_curr}</b>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-top:6px; color:#0284c7; font-weight:bold;">
                        <span>(+) ضريبة القيمة المضافة ({totals['vat_pct']}%):</span>
                        <b>{totals['vat_amount']:,.2f} {c_curr}</b>
                    </div>
                    <div style="display:flex; justify-content:space-between; border-top:2px solid #0F2545; padding-top:8px; margin-top:6px; font-size:15px; color:#15803d; font-weight:bold;">
                        <span>صافي المستخلص المستحق للصرف:</span>
                        <b>{totals['net_ipc_amount']:,.2f} {c_curr}</b>
                    </div>
                </div>
            </div>

            <div style="background:#f8fafc; border:1px solid #cbd5e1; border-radius:6px; padding:8px 14px; margin-top:10px; font-size:13px;">
                <b>صافي المستخلص كتابةً:</b> 
                <span style="color:#0F2545; font-weight:bold;">{tafeet_current}</span>
            </div>

            <div class="signatures">
                <div class="sig-box"><b>حساب الكميات</b><br><br><br>التوقيع: ...........................</div>
                <div class="sig-box"><b>مسؤول السلامة</b><br><br><br>التوقيع: ...........................</div>
                <div class="sig-box"><b>مدير التنفيذ</b><br><br><br>التوقيع: ...........................</div>
                <div class="sig-box"><b>مدير المشروع</b><br><br><br>التوقيع: ...........................</div>
            </div>
        </div>
    </body>
    </html>
    """
    return html

# ─── الواجهة الرئيسية ───
def render_subcontractor_interface(selected_proj, current_user_data, api_key):
    is_rtl = True
    dir_align = "right"
    dir_style = "rtl"

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
    
    .stApp, div[data-testid="stMarkdownContainer"] p, div[data-testid="stMarkdownContainer"] span, 
    .stTextInput label, .stDateInput label, .stSelectbox label, .stNumberInput label, .stTextArea label,
    button, div[data-testid="stDataFrame"] {{
        font-family: 'Cairo', Arial, sans-serif !important;
        font-feature-settings: "tnum";
        font-variant-numeric: tabular-nums;
    }}

    div[data-testid="stFileUploaderDropzone"] {{
        direction: rtl !important;
        text-align: center !important;
    }}

    .alyosser-header {{
        background: linear-gradient(135deg, #0F2545 0%, #162F56 60%, #1E3A8A 100%);
        border-radius: 12px;
        padding: 18px 24px;
        margin-bottom: 20px;
        color: #FFFFFF;
        text-align: {dir_align};
        direction: {dir_style};
        box-shadow: 0 4px 14px rgba(15, 37, 69, 0.12);
        border-top: 4px solid #EAB308;
    }}

    .subcontract-section {{
        text-align: {dir_align};
        direction: {dir_style};
        font-size: 15px;
        font-weight: 800;
        color: #0F2545;
        margin: 16px 0 8px 0;
        border-bottom: 2px solid #CBD5E1;
        padding-bottom: 5px;
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .subcontract-section::before {{
        content: "";
        display: inline-block;
        width: 4px;
        height: 18px;
        background: #EAB308;
        border-radius: 2px;
    }}

    .stTextInput label, .stDateInput label, .stSelectbox label, .stNumberInput label, .stTextArea label {{
        color: #0F172A !important;
        font-weight: 700 !important;
        font-size: 13.5px !important;
    }}

    div[data-testid="stDataFrame"] {{
        border: 1px solid #94A3B8 !important;
        border-radius: 6px !important;
    }}
    div[data-testid="stDataFrame"] * {{
        color: #0F172A !important;
        font-weight: 600 !important;
    }}

    button[kind="primary"] {{
        background: linear-gradient(135deg, #0F2545 0%, #0284C7 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: 700 !important;
    }}

    .glass-card {{
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 14px;
        box-shadow: 0 2px 8px rgba(15, 37, 69, 0.05);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    .glass-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(15, 37, 69, 0.1);
    }}

    .metric-bubble {{
        background: linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 100%);
        border: 1px solid #BFDBFE;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.03);
    }}

    .discrepancy-box {{
        background-color: #FEF2F2;
        border-right: 4px solid #EF4444;
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 15px;
        direction: rtl;
        text-align: right;
    }}

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
        background: #1E293B !important;
        color: #FFFFFF !important;
        border: none !important;
        border-right: 4px solid #E8B423 !important;
        direction: rtl !important;
        text-align: right !important;
    }}
    div[data-testid="stMarkdownContainer"]:has(.section-banner) {{
        width: fit-content !important;
        max-width: 100% !important;
    }}
    .kpi-chip-grid {{
        display: grid;
        grid-template-columns: repeat(4, minmax(140px, 1fr));
        gap: 10px;
        direction: rtl;
        margin: 0 0 14px 0;
    }}
    .kpi-chip {{
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-right: 4px solid #E8B423;
        border-radius: 8px;
        padding: 10px 12px;
        text-align: right;
        direction: rtl;
        unicode-bidi: isolate;
    }}
    .kpi-chip-label {{
        font-size: 12px;
        color: #64748B;
        font-weight: 700;
        margin: 0;
    }}
    .kpi-chip-value {{
        font-size: 14px;
        color: #1E293B;
        font-weight: 800;
        margin: 4px 0 0 0;
        word-break: break-word;
    }}
    .rtl-strict, .rtl-strict * {{
        direction: rtl !important;
        text-align: right !important;
        unicode-bidi: isolate;
    }}
    [data-testid="InputInstructions"],
    [data-testid="stElementToolbar"],
    kbd {{
        display: none !important;
    }}
    </style>
    <div class="section-banner">🏗️ مستخلصات مقاولي الباطن والموردين — {html.escape(str(selected_proj or ""))}</div>
    """, unsafe_allow_html=True)

    contractors_data = load_json_data(CONTRACTORS_FILE)
    contracts_data = load_json_data(SUBCONTRACTS_FILE)
    boq_data = load_json_data(BOQ_FILE)
    ipc_data = load_json_data(IPC_FILE)

    flash = st.session_state.pop("contract_drive_flash", None)
    if flash:
        kind = flash.get("kind")
        msg = flash.get("msg", "")
        if kind == "error":
            st.error(msg)
        elif kind == "warning":
            st.warning(msg)
        else:
            st.success(msg)

    current_proj_contracts = [c for c in contracts_data if c.get("project_name") == selected_proj]

    tab_contracts, tab_new_contract, tab_ipc, tab_control = st.tabs([
        "سجل العقود المعتمدة", 
        "توثيق عقد جديد",
        "مستخلصات مقاولي الباطن",
        "لوحة الرقابة وسجل التدقيق"
    ])

    # ── 1. سجل العقود المعتمدة ──
    with tab_contracts:
        if not current_proj_contracts:
            st.info("لا توجد عقود معتمدة مسجلة لهذا المشروع حالياً.")
        else:
            summary_table = []
            for c in current_proj_contracts:
                vnd = c.get("vendor", {})
                comm = c.get("commercial_terms", {})
                c_id = c.get("subcontract_id")
                c_val = safe_float(comm.get('total_including_vat', 0))
                c_curr_label = comm.get('currency', 'SAR')

                consumed_amt, remaining_amt, prog_pct = get_contract_consumption_metrics(c_id, c_val, ipc_data)

                if prog_pct > 100.0:
                    status_badge = f"🚨 تجاوز ({prog_pct:.1f}%)"
                elif prog_pct >= 90.0:
                    status_badge = f"⚠️ قارب على النفاد ({prog_pct:.1f}%)"
                else:
                    status_badge = f"نشط ({prog_pct:.1f}%)"

                summary_table.append({
                    "كود العقد": c_id,
                    "رقم العقد": c.get("contract_number"),
                    "المقاول": vnd.get("vendor_name"),
                    "قيمة العقد الأصلية": f"{c_val:,.2f} {c_curr_label}",
                    "المنفذ المعتمد (المستهلك)": f"{consumed_amt:,.2f} {c_curr_label}",
                    "المتبقي من العقد": f"{remaining_amt:,.2f} {c_curr_label}",
                    "نسبة الاستهلاك": f"{prog_pct:.1f}%",
                    "حالة الرقابة": status_badge
                })
            
            st.dataframe(pd.DataFrame(summary_table), use_container_width=True, hide_index=True)
            contract_export_rows = []
            for c in current_proj_contracts:
                vnd = c.get("vendor", {})
                comm = c.get("commercial_terms", {})
                c_id = c.get("subcontract_id")
                c_val = safe_float(comm.get("total_including_vat", 0))
                consumed_amt, remaining_amt, prog_pct = get_contract_consumption_metrics(c_id, c_val, ipc_data)
                contract_export_rows.append({
                    "كود العقد": c_id,
                    "رقم العقد": c.get("contract_number"),
                    "المقاول": vnd.get("vendor_name"),
                    "قيمة العقد الأصلية": c_val,
                    "المنفذ المعتمد": consumed_amt,
                    "المتبقي من العقد": remaining_amt,
                    "نسبة الاستهلاك %": round(prog_pct, 2),
                    "العملة": comm.get("currency", "SAR"),
                    "حالة العقد": c.get("status", "Active"),
                    "رابط ملف العقد": c.get("document_file") or c.get("drive_contract_link") or ""
                })
            to_excel_download_button(
                pd.DataFrame(contract_export_rows),
                f"subcontracts_{selected_proj}.xlsx",
                "⬇️ تصدير سجل العقود Excel",
                "btn_xlsx_contracts_register"
            )

            st.markdown("---")
            st.markdown("##### 📄 استعراض وثيقة أمر الشراء / العقد والتحكم المالي الحي")
            contract_options = {c["contract_number"]: c for c in current_proj_contracts}
            selected_c_no = st.selectbox("اختر العقد للمعاينة أو الطباعة ومتابعة الاستهلاك:", list(contract_options.keys()), key="sel_contract_overview")

            if selected_c_no:
                sel_c = contract_options[selected_c_no]
                sc_id = sel_c.get("subcontract_id")
                vnd = sel_c.get("vendor", {})
                comm = sel_c.get("commercial_terms", {})
                c_val = safe_float(comm.get('total_including_vat', 0))
                c_curr_label = comm.get('currency', 'SAR')
                c_items = [b for b in boq_data if b.get("subcontract_id") == sc_id]

                live_consumed, live_remaining, live_pct = get_contract_consumption_metrics(sc_id, c_val, ipc_data)

                with st.expander(f"ملف العقد ومتابعة الاستهلاك: {selected_c_no} — {vnd.get('vendor_name')}", expanded=True):
                    mb1, mb2, mb3, mb4 = st.columns(4)
                    with mb1:
                        st.markdown(f"""
                        <div class="metric-bubble">
                            <span style="font-size:12px; color:#64748b; font-weight:700;">إجمالي العقد الصافي</span>
                            <h3 style="margin:4px 0 0 0; color:#0F2545; font-size:19px; font-weight:900;">{c_val:,.2f} <span style="font-size:12px;">{c_curr_label}</span></h3>
                        </div>
                        """, unsafe_allow_html=True)
                    with mb2:
                        st.markdown(f"""
                        <div class="metric-bubble">
                            <span style="font-size:12px; color:#0284c7; font-weight:700;">المنفذ بالمستخلصات</span>
                            <h3 style="margin:4px 0 0 0; color:#0284c7; font-size:19px; font-weight:900;">{live_consumed:,.2f} <span style="font-size:12px;">{c_curr_label}</span></h3>
                            <span style="font-size:11px; color:#15803d; font-weight:bold;">↑ {live_pct:.1f}% مستهلك</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with mb3:
                        rem_color = "#15803d" if live_remaining >= 0 else "#b91c1c"
                        st.markdown(f"""
                        <div class="metric-bubble">
                            <span style="font-size:12px; color:#64748b; font-weight:700;">المتبقي المالي المتاح</span>
                            <h3 style="margin:4px 0 0 0; color:{rem_color}; font-size:19px; font-weight:900;">{live_remaining:,.2f} <span style="font-size:12px;">{c_curr_label}</span></h3>
                        </div>
                        """, unsafe_allow_html=True)
                    with mb4:
                        st.markdown(f"""
                        <div class="metric-bubble">
                            <span style="font-size:12px; color:#64748b; font-weight:700;">حالة التعاقد</span>
                            <h3 style="margin:4px 0 0 0; color:#0F2545; font-size:19px; font-weight:900;">{sel_c.get('status', 'Active')}</h3>
                        </div>
                        """, unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)
                    clamped_progress = min(max(live_pct / 100.0, 0.0), 1.0)
                    st.progress(clamped_progress, text=f"مؤشر استهلاك العقد المالي: {live_pct:.1f}%")

                    if live_pct > 100.0:
                        st.error(f"🚨 تنبيه رقابي: العقد تجاوز القيمة التعاقدية المعتمدة بمبلغ ({abs(live_remaining):,.2f} {c_curr_label})! يلزم إصدار أمر تغيير.")
                    elif live_pct >= 90.0:
                        st.warning(f"⚠️ تنبيه اقتراب: العقد استهلك أكثر من 90% من مخصصاته المالية.")

                    po_no = html.escape(str(sel_c.get("contract_number") or "—"))
                    c_date = html.escape(str(sel_c.get("contract_date") or "—"))
                    p_term = html.escape(str(comm.get("payment_term") or "—"))
                    p_method = html.escape(str(comm.get("payment_method") or "—"))
                    vat_lbl = html.escape(str(comm.get("vat_pct", 15)))
                    st.markdown(f"""
                    <div class="kpi-chip-grid">
                        <div class="kpi-chip"><p class="kpi-chip-label">رقم أمر الشراء</p><p class="kpi-chip-value">{po_no}</p></div>
                        <div class="kpi-chip"><p class="kpi-chip-label">تاريخ التعاقد</p><p class="kpi-chip-value">{c_date}</p></div>
                        <div class="kpi-chip"><p class="kpi-chip-label">شروط السداد</p><p class="kpi-chip-value">{p_term} — {p_method}</p></div>
                        <div class="kpi-chip"><p class="kpi-chip-label">نسبة الضريبة</p><p class="kpi-chip-value">{vat_lbl}%</p></div>
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown(f"""
                    <div class="glass-card rtl-strict" style="direction:rtl; text-align:right;">
                        <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap: 12px; font-size: 13px;">
                            <div><b>اسم المقاول:</b> <span style="color:#0F2545;">{html.escape(str(vnd.get('vendor_name') or ""))}</span></div>
                            <div><b>كود المقاول:</b> {html.escape(str(vnd.get('vendor_id') or ""))}</div>
                            <div><b>الشخص المسؤول:</b> {html.escape(str(vnd.get('contact_name') or ""))}</div>
                            <div><b>رقم الهاتف:</b> <span style="direction:ltr; display:inline-block; unicode-bidi:isolate;">{html.escape(str(vnd.get('mobile_no') or ""))}</span></div>
                            <div><b>مرجع طلب الشراء:</b> {html.escape(str(sel_c.get('mr_pr_reference') or ""))}</div>
                            <div><b>تاريخ الإنجاز المطلوب:</b> {html.escape(str(sel_c.get('delivery_date') or ""))}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown("**الشروط والأحكام التعاقدية:**")
                    st.markdown(f"""
                    <div class="glass-card rtl-strict">
                        {format_special_terms_as_numbered_list(comm.get("special_terms", ""))}
                    </div>
                    """, unsafe_allow_html=True)

                    if c_items:
                        st.markdown('<div class="rtl-strict">', unsafe_allow_html=True)
                        st.markdown("**جدول الكميات وبنود الأعمال التعاقدية:**")
                        df_boq = pd.DataFrame(c_items).drop(columns=["subcontract_id", "boq_item_id"], errors="ignore")
                        st.dataframe(df_boq, use_container_width=True, hide_index=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown("---")
                    c_act1, c_act2 = st.columns([1.5, 3])
                    with c_act1:
                        if st.button("🖨️ فتح وثيقة أمر الشراء / العقد للطباعة", type="primary", key=f"btn_print_view_{sc_id}"):
                            st.session_state[f"show_print_{sc_id}"] = not st.session_state.get(f"show_print_{sc_id}", False)

                    with c_act2:
                        with st.expander("إدارة بنود وتعديلات العقد"):
                            st.caption("تحذير: حذف العقد سيقوم بحذف جميع بنوده ومستخلصاته المرتبطة نهائياً.")
                            if st.button("🗑️ حذف هذا العقد نهائياً من النظام", type="secondary", key=f"btn_del_contract_{sc_id}"):
                                contracts_data = [x for x in contracts_data if x.get("subcontract_id") != sc_id]
                                boq_data = [x for x in boq_data if x.get("subcontract_id") != sc_id]
                                ipc_data = [x for x in ipc_data if x.get("subcontract_id") != sc_id]
                                save_json_data(SUBCONTRACTS_FILE, contracts_data)
                                save_json_data(BOQ_FILE, boq_data)
                                save_json_data(IPC_FILE, ipc_data)
                                st.success("تم حذف العقد وجميع سجلاته المرتبطة بنجاح.")
                                st.rerun()

                    if st.session_state.get(f"show_print_{sc_id}", False):
                        contract_print_data = {
                            "contract_number": sel_c.get("contract_number"),
                            "mr_pr_reference": sel_c.get("mr_pr_reference"),
                            "contract_date": sel_c.get("contract_date"),
                            "delivery_date": sel_c.get("delivery_date"),
                            "buyer_name": sel_c.get("buyer_name"),
                            "buyer_contact": sel_c.get("buyer_contact"),
                            "vendor_name": vnd.get("vendor_name"),
                            "vendor_id": vnd.get("vendor_id"),
                            "contact_name": vnd.get("contact_name"),
                            "mobile_no": vnd.get("mobile_no"),
                            "address": vnd.get("address"),
                            "currency": comm.get("currency"),
                            "payment_term": comm.get("payment_term"),
                            "payment_method": comm.get("payment_method"),
                            "adv_payment_amt": comm.get("adv_payment_amt"),
                            "adv_recovery_pct": comm.get("adv_recovery_pct"),
                            "retention_pct": comm.get("retention_pct"),
                            "vat_pct": comm.get("vat_pct", 15.0),
                            "special_terms": comm.get("special_terms")
                        }
                        preview_html = render_printable_contract_html(contract_print_data, c_items, selected_proj)
                        st.components.v1.html(preview_html, height=720, scrolling=True)

    # ── 2. توثيق عقد جديد ──
    with tab_new_contract:
        if "contract_form_state" not in st.session_state:
            st.session_state.contract_form_state = {
                "contract_number": "",
                "mr_pr_reference": "",
                "contract_date": datetime.date.today(),
                "delivery_date": datetime.date.today() + datetime.timedelta(days=365),
                "buyer_name": current_user_data.get("name", "") if current_user_data else "",
                "buyer_contact": "",
                "vendor_name": "",
                "vendor_id": "",
                "contact_name": "",
                "mobile_no": "",
                "email": "",
                "address": "",
                "currency": "SAR",
                "payment_term": "30 Days IPC",
                "payment_method": "Bank TRANSFER",
                "adv_payment_amt": 0.0,
                "adv_recovery_pct": 0.0,
                "retention_pct": 0.0,
                "vat_pct": 15.0,
                "special_terms": "",
                "boq_items": []
            }

        form_state = st.session_state.contract_form_state

        with st.expander("وثيقة أمر الشراء / العقد الأصلية", expanded=True):
            uploaded_doc = st.file_uploader("ملف العقد", type=["pdf", "png", "jpg", "jpeg"], key="ocr_contract_uploader")
            if uploaded_doc is not None:
                rewind_uploaded_file(uploaded_doc)
                st.session_state["raw_contract_file_bytes"] = uploaded_doc.getvalue()
                st.session_state["raw_contract_file_name"] = uploaded_doc.name
                rewind_uploaded_file(uploaded_doc)
                st.success(f"📄 الملف جاهز للإيداع السحابي: {uploaded_doc.name}")
            elif st.session_state.get("raw_contract_file_bytes"):
                cached_name = st.session_state.get("raw_contract_file_name", "ملف العقد")
                st.success(f"📄 الملف جاهز للإيداع السحابي: {cached_name}")
            if uploaded_doc is not None:
                if st.button("استخراج بيانات العقد", type="secondary", key="btn_ext_contract"):
                    with st.spinner("جاري قراءة واستخراج كافة بيانات العقد والمقاول والبنود..."):
                        extracted_data, err = extract_contract_via_gemini(uploaded_doc, api_key)
                        if err:
                            st.error(err)
                        elif extracted_data:
                            form_state["contract_number"] = safe_str(extracted_data.get("contract_number"))
                            form_state["mr_pr_reference"] = safe_str(extracted_data.get("mr_pr_reference"))
                            form_state["buyer_name"] = safe_str(extracted_data.get("buyer_name"))
                            form_state["buyer_contact"] = safe_str(extracted_data.get("buyer_contact"))
                            
                            if extracted_data.get("contract_date"):
                                try:
                                    form_state["contract_date"] = datetime.datetime.strptime(str(extracted_data["contract_date"])[:10], "%Y-%m-%d").date()
                                except Exception:
                                    pass
                            if extracted_data.get("delivery_date"):
                                try:
                                    form_state["delivery_date"] = datetime.datetime.strptime(str(extracted_data["delivery_date"])[:10], "%Y-%m-%d").date()
                                except Exception:
                                    pass

                            vnd_ex = extracted_data.get("vendor", {})
                            form_state["vendor_name"] = safe_str(vnd_ex.get("vendor_name"))
                            form_state["vendor_id"] = safe_str(vnd_ex.get("vendor_id"))
                            form_state["contact_name"] = safe_str(vnd_ex.get("contact_name"))
                            form_state["mobile_no"] = safe_str(vnd_ex.get("mobile_no"))
                            form_state["email"] = safe_str(vnd_ex.get("email"))
                            form_state["address"] = safe_str(vnd_ex.get("address"))
                            
                            comm_ex = extracted_data.get("commercial_terms", {})
                            if safe_str(comm_ex.get("currency")) in ["SAR", "EGP", "AED", "USD"]:
                                form_state["currency"] = safe_str(comm_ex.get("currency"))
                            form_state["payment_term"] = safe_str(comm_ex.get("payment_term")) or "30 Days IPC"
                            form_state["payment_method"] = safe_str(comm_ex.get("payment_method")) or "Bank TRANSFER"
                            form_state["adv_payment_amt"] = safe_float(comm_ex.get("adv_payment_amt"), 0.0)
                            form_state["adv_recovery_pct"] = safe_float(comm_ex.get("adv_recovery_pct"), 0.0)
                            form_state["retention_pct"] = safe_float(comm_ex.get("retention_pct"), 0.0)
                            form_state["vat_pct"] = safe_float(comm_ex.get("vat_pct"), 15.0)
                            form_state["special_terms"] = safe_str(comm_ex.get("special_terms"))
                            
                            items_raw = extracted_data.get("boq_items", [])
                            sanitized_items = []
                            for idx, itm in enumerate(items_raw):
                                q = safe_float(itm.get("contract_qty"))
                                p = safe_float(itm.get("unit_price"))
                                v = safe_float(itm.get("vat_amount"))
                                tot = (q * p) + v
                                sanitized_items.append({
                                    "sr_no": idx + 1,
                                    "item_code": safe_str(itm.get("item_code")) or f"ITEM-{idx+1}",
                                    "description": safe_str(itm.get("description")),
                                    "unit": safe_str(itm.get("unit")) or "EA",
                                    "contract_qty": q,
                                    "unit_price": p,
                                    "vat_amount": v,
                                    "total_amount": tot
                                })
                            form_state["boq_items"] = sanitized_items

                            st.session_state["c_in_num"] = form_state["contract_number"]
                            st.session_state["c_in_pr"] = form_state["mr_pr_reference"]
                            st.session_state["c_in_date"] = form_state["contract_date"]
                            st.session_state["c_in_buyer"] = form_state["buyer_name"]
                            st.session_state["c_in_bcontact"] = form_state["buyer_contact"]
                            st.session_state["c_in_deliv"] = form_state["delivery_date"]
                            st.session_state["c_in_vname"] = form_state["vendor_name"]
                            st.session_state["c_in_vid"] = form_state["vendor_id"]
                            st.session_state["c_in_vcontact"] = form_state["contact_name"]
                            st.session_state["c_in_vphone"] = form_state["mobile_no"]
                            st.session_state["c_in_vmail"] = form_state["email"]
                            st.session_state["c_in_vaddr"] = form_state["address"]
                            st.session_state["c_in_curr"] = form_state["currency"]
                            st.session_state["c_in_pterm"] = form_state["payment_term"]
                            st.session_state["c_in_pmeth"] = form_state["payment_method"]
                            st.session_state["c_in_ret"] = form_state["retention_pct"]
                            st.session_state["c_in_adv"] = form_state["adv_payment_amt"]
                            st.session_state["c_in_adv_pct"] = form_state["adv_recovery_pct"]
                            st.session_state["c_in_vat"] = form_state["vat_pct"]
                            st.session_state["c_in_spec"] = form_state["special_terms"]

                            st.success("تم استخراج وتعبئة كافة البيانات بنجاح.")
                            st.rerun()

        st.markdown('<div class="subcontract-section">1. بيانات الوثيقة التعاقدية والمشروع</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        contract_number = c1.text_input("رقم العقد *", value=form_state["contract_number"], key="c_in_num")
        form_state["contract_number"] = contract_number
        mr_pr_reference = c2.text_input("مرجع طلب الشراء", value=form_state["mr_pr_reference"], key="c_in_pr")
        form_state["mr_pr_reference"] = mr_pr_reference
        contract_date = c3.date_input("تاريخ العقد", value=form_state["contract_date"], key="c_in_date")
        form_state["contract_date"] = contract_date

        c4, c5, c6 = st.columns(3)
        buyer_name = c4.text_input("مسؤول التعاقد", value=form_state["buyer_name"], key="c_in_buyer")
        form_state["buyer_name"] = buyer_name
        buyer_contact = c5.text_input("رقم الاتصال", value=form_state["buyer_contact"], key="c_in_bcontact")
        form_state["buyer_contact"] = buyer_contact
        delivery_date = c6.date_input("تاريخ الإنجاز", value=form_state["delivery_date"], key="c_in_deliv")
        form_state["delivery_date"] = delivery_date

        st.markdown('<div class="subcontract-section">2. بيانات الطرف الثاني (المقاول)</div>', unsafe_allow_html=True)
        v1, v2, v3 = st.columns(3)
        vendor_name = v1.text_input("اسم المقاول *", value=form_state["vendor_name"], key="c_in_vname")
        form_state["vendor_name"] = vendor_name
        vendor_id = v2.text_input("كود المقاول", value=form_state["vendor_id"], key="c_in_vid")
        form_state["vendor_id"] = vendor_id
        contact_name = v3.text_input("الشخص المسؤول", value=form_state["contact_name"], key="c_in_vcontact")
        form_state["contact_name"] = contact_name

        v4, v5, v6 = st.columns(3)
        mobile_no = v4.text_input("رقم الهاتف", value=form_state["mobile_no"], key="c_in_vphone")
        form_state["mobile_no"] = mobile_no
        email = v5.text_input("البريد الإلكتروني", value=form_state["email"], key="c_in_vmail")
        form_state["email"] = email
        address = v6.text_input("العنوان", value=form_state["address"], key="c_in_vaddr")
        form_state["address"] = address

        st.markdown('<div class="subcontract-section">3. الشروط المالية والتعاقدية</div>', unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        currency_list = ["SAR", "EGP", "AED", "USD"]
        curr_idx = currency_list.index(form_state["currency"]) if form_state["currency"] in currency_list else 0
        currency = m1.selectbox("العملة", currency_list, index=curr_idx, key="c_in_curr")
        form_state["currency"] = currency

        terms_list = ["30 Days IPC", "60 Days IPC", "Advance", "Milestone", "Immediate"]
        term_idx = terms_list.index(form_state["payment_term"]) if form_state["payment_term"] in terms_list else 0
        payment_term = m2.selectbox("شروط السداد", terms_list, index=term_idx, key="c_in_pterm")
        form_state["payment_term"] = payment_term

        methods_list = ["Bank TRANSFER", "Cheque", "Cash"]
        method_idx = methods_list.index(form_state["payment_method"]) if form_state["payment_method"] in methods_list else 0
        payment_method = m3.selectbox("طريقة الدفع", methods_list, index=method_idx, key="c_in_pmeth")
        form_state["payment_method"] = payment_method

        retention_pct = m4.number_input("ضمان الأعمال %", min_value=0.0, max_value=100.0, value=safe_float(form_state["retention_pct"], 0.0), step=0.5, key="c_in_ret")
        form_state["retention_pct"] = retention_pct

        m5, m6, m7, m8 = st.columns(4)
        adv_payment_amt = m5.number_input(f"الدفعة المقدمة ({currency})", min_value=0.0, value=safe_float(form_state["adv_payment_amt"], 0.0), step=5000.0, key="c_in_adv")
        form_state["adv_payment_amt"] = adv_payment_amt
        adv_recovery_pct = m6.number_input("نسبة استرداد الدفعة المقدمة %", min_value=0.0, max_value=100.0, value=safe_float(form_state.get("adv_recovery_pct", 0.0)), step=1.0, key="c_in_adv_pct")
        form_state["adv_recovery_pct"] = adv_recovery_pct
        vat_pct = m7.number_input("ضريبة القيمة المضافة %", min_value=0.0, max_value=100.0, value=safe_float(form_state["vat_pct"], 15.0), step=1.0, key="c_in_vat")
        form_state["vat_pct"] = vat_pct
        special_terms = m8.text_input("شروط خاصة", value=form_state["special_terms"], key="c_in_spec")
        form_state["special_terms"] = special_terms

        st.markdown('<div class="subcontract-section">4. جدول بنود الأعمال التعاقدية</div>', unsafe_allow_html=True)

        with st.expander("إضافة بند تعاقدي يدوياً"):
            r1, r2, r3, r4, r5, r6, r7, r8 = st.columns([0.6, 1.2, 2.4, 0.8, 1.0, 1.0, 1.0, 1.2])
            in_sr = r1.number_input("م", min_value=1, value=len(form_state["boq_items"]) + 1, key="c_b_sr")
            in_code = r2.text_input("كود البند", value=f"04010101_{in_sr:03d}", key="c_b_code")
            in_desc = r3.text_input("توصيف البند", key="c_b_desc")
            in_unit = r4.text_input("الوحدة", value="EA", key="c_b_unit")
            in_qty = r5.number_input("الكمية التعاقدية", min_value=0.0, step=1.0, key="c_b_qty")
            in_price = r6.number_input(f"السعر ({currency})", min_value=0.0, step=10.0, key="c_b_price")
            in_vat_item = r7.number_input(f"الضريبة ({currency})", min_value=0.0, step=5.0, key="c_b_vat")
            
            in_item_total = (in_qty * in_price) + in_vat_item
            r8.metric("الإجمالي الصافي", f"{in_item_total:,.2f}")

            if st.button("إدراج البند في الجدول", use_container_width=False, key="btn_add_boq_item"):
                if in_desc.strip():
                    form_state["boq_items"].append({
                        "sr_no": int(in_sr),
                        "item_code": safe_str(in_code),
                        "description": safe_str(in_desc),
                        "unit": safe_str(in_unit) or "EA",
                        "contract_qty": safe_float(in_qty),
                        "unit_price": safe_float(in_price),
                        "vat_amount": safe_float(in_vat_item),
                        "total_amount": safe_float(in_item_total)
                    })
                    st.rerun()

        subtotal_base = 0.0
        total_items_vat = 0.0
        if form_state["boq_items"]:
            for item in form_state["boq_items"]:
                q_val = safe_float(item.get("contract_qty"))
                p_val = safe_float(item.get("unit_price"))
                v_val = safe_float(item.get("vat_amount", 0.0))
                expected_tot = round((q_val * p_val) + v_val, 2)
                item["total_amount"] = expected_tot
                subtotal_base += (q_val * p_val)
                total_items_vat += v_val

            df_table = pd.DataFrame(form_state["boq_items"])
            df_table = df_table.rename(columns={
                "sr_no": "م",
                "item_code": "كود البند",
                "description": "توصيف الأعمال",
                "unit": "الوحدة",
                "contract_qty": "الكمية التعاقدية",
                "unit_price": f"فئة السعر ({currency})",
                "vat_amount": f"الضريبة ({currency})",
                "total_amount": f"الإجمالي الصافي ({currency})"
            })
            st.dataframe(df_table, use_container_width=True, hide_index=True)

            if st.button("إفراغ جدول المقايسة", use_container_width=False, key="btn_clear_boq"):
                form_state["boq_items"] = []
                st.rerun()

        final_vat = total_items_vat if total_items_vat > 0 else (subtotal_base * (vat_pct / 100.0))
        net_contract_value = subtotal_base + final_vat

        st.markdown(f"""
        <div style="background:#F8FAFC; border:1px solid #CBD5E1; border-radius:8px; padding:16px; margin:16px 0; direction:rtl; text-align:right;">
            <div style="display:flex; justify-content:space-between; margin-bottom:6px; font-weight:700; color:#0F172A;">
                <span>إجمالي الأعمال التعاقدية:</span><span>{subtotal_base:,.2f} {currency}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:6px; font-weight:700; color:#0284c7;">
                <span>ضريبة القيمة المضافة:</span><span>{final_vat:,.2f} {currency}</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:18px; font-weight:900; color:#0F2545; border-top:2px solid #0F2545; padding-top:8px;">
                <span>الإجمالي الصافي شامل الضريبة:</span><span>{net_contract_value:,.2f} {currency}</span>
            </div>
            <div style="margin-top:8px; font-size:14px; font-style:italic; color:#475569;">
                <b>فقط وقدره:</b> {number_to_words_ar(net_contract_value, currency)}
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_a1, col_a2 = st.columns([1.5, 3])
        if col_a1.button("اعتماد وحفظ العقد ومزامنته سحابياً", type="primary", key="btn_save_contract_rec"):
            clean_c_no = safe_str(contract_number)
            clean_v_name = safe_str(vendor_name)

            if not clean_c_no or not clean_v_name:
                st.error("رقم العقد واسم المقاول حقول إلزامية.")
            elif not form_state["boq_items"]:
                st.error("جدول بنود الأعمال فارغ.")
            else:
                clean_proj_code = "".join([c for c in selected_proj if c.isalnum()]).upper()[:6]
                sc_id = f"SC-{clean_proj_code}-{clean_c_no}-{str(uuid.uuid4())[:6]}"
                clean_v_id = safe_str(vendor_id) or f"VND-{clean_c_no}"

                saved_contract_path = ""
                contract_drive_link = ""
                upload_source = None
                upload_name = "contract.pdf"
                if uploaded_doc is not None:
                    rewind_uploaded_file(uploaded_doc)
                    st.session_state["raw_contract_file_bytes"] = uploaded_doc.getvalue()
                    st.session_state["raw_contract_file_name"] = uploaded_doc.name
                    rewind_uploaded_file(uploaded_doc)
                    upload_source = uploaded_doc
                    upload_name = uploaded_doc.name
                elif st.session_state.get("raw_contract_file_bytes"):
                    upload_source = st.session_state.get("raw_contract_file_bytes")
                    upload_name = st.session_state.get("raw_contract_file_name") or "contract.pdf"

                if upload_source is not None:
                    saved_contract_path = persist_bytes_to_attachments(
                        st.session_state.get("raw_contract_file_bytes") or _coerce_file_bytes(upload_source)[0],
                        upload_name,
                        f"tmp_{sc_id}"
                    )
                    contract_drive_link, drive_err = upload_file_to_drive(
                        upload_source,
                        upload_name,
                        DRIVE_SUB_FOLDERS["contracts"]
                    )
                    if contract_drive_link:
                        push_drive_notice("success", f"✅ تم إيداع ملف العقد في Google Drive: {contract_drive_link}")
                    else:
                        push_drive_notice("error", f"❌ تعذر رفع العقد إلى Google Drive: {drive_err}")
                else:
                    push_drive_notice("warning", "⚠️ تنبيه: لم يتم العثور على ملف مرفوع لإيداعه في الدرايف.")

                new_contract = {
                    "subcontract_id": sc_id,
                    "contract_number": clean_c_no,
                    "mr_pr_reference": safe_str(mr_pr_reference),
                    "project_name": selected_proj,
                    "contract_date": str(contract_date),
                    "delivery_date": str(delivery_date),
                    "buyer_name": safe_str(buyer_name),
                    "buyer_contact": safe_str(buyer_contact),
                    "vendor": {
                        "vendor_id": clean_v_id,
                        "vendor_name": clean_v_name,
                        "contact_name": safe_str(contact_name),
                        "address": safe_str(address),
                        "mobile_no": safe_str(mobile_no),
                        "email": safe_str(email)
                    },
                    "commercial_terms": {
                        "payment_term": safe_str(payment_term),
                        "payment_method": safe_str(payment_method),
                        "adv_payment_amt": safe_float(adv_payment_amt, 0.0),
                        "adv_recovery_pct": safe_float(adv_recovery_pct, 0.0),
                        "retention_pct": safe_float(retention_pct, 0.0),
                        "vat_pct": safe_float(vat_pct),
                        "currency": currency,
                        "total_amount": float(subtotal_base),
                        "total_vat": float(final_vat),
                        "total_including_vat": float(net_contract_value),
                        "amount_in_words": number_to_words_ar(net_contract_value, currency),
                        "special_terms": safe_str(special_terms)
                    },
                    "local_document_file": saved_contract_path,
                    "document_file": contract_drive_link,
                    "drive_contract_link": contract_drive_link,
                    "status": "Active",
                    "created_at": str(datetime.datetime.now()),
                    "created_by": current_user_data.get("name", "User") if current_user_data else "User"
                }

                contracts_data.append(new_contract)
                save_json_data(SUBCONTRACTS_FILE, contracts_data)

                saved_boq_items = []
                for idx, itm in enumerate(form_state["boq_items"]):
                    itm_copy = dict(itm)
                    itm_copy["boq_item_id"] = f"{sc_id}_BOQ_{idx+1}_{str(uuid.uuid4())[:4]}"
                    itm_copy["subcontract_id"] = sc_id
                    boq_data.append(itm_copy)
                    saved_boq_items.append(itm_copy)
                save_json_data(BOQ_FILE, boq_data)

                with st.spinner("جاري حفظ العقد ومزامنته سحابياً مع Google Sheets..."):
                    sync_contract_to_cloud(new_contract, saved_boq_items)
                    save_json_data(SUBCONTRACTS_FILE, contracts_data)

                contract_widget_keys = [
                    "c_in_num", "c_in_pr", "c_in_date", "c_in_buyer", "c_in_bcontact", "c_in_deliv",
                    "c_in_vname", "c_in_vid", "c_in_vcontact", "c_in_vphone", "c_in_vmail", "c_in_vaddr",
                    "c_in_curr", "c_in_pterm", "c_in_pmeth", "c_in_ret", "c_in_adv", "c_in_adv_pct", "c_in_vat", "c_in_spec",
                    "c_b_sr", "c_b_code", "c_b_desc", "c_b_unit", "c_b_qty", "c_b_price", "c_b_vat"
                ]
                for k in contract_widget_keys:
                    st.session_state.pop(k, None)

                st.session_state.contract_form_state = {
                    "contract_number": "",
                    "mr_pr_reference": "",
                    "contract_date": datetime.date.today(),
                    "delivery_date": datetime.date.today() + datetime.timedelta(days=365),
                    "buyer_name": current_user_data.get("name", "") if current_user_data else "",
                    "buyer_contact": "",
                    "vendor_name": "",
                    "vendor_id": "",
                    "contact_name": "",
                    "mobile_no": "",
                    "email": "",
                    "address": "",
                    "currency": currency,
                    "payment_term": "30 Days IPC",
                    "payment_method": "Bank TRANSFER",
                    "adv_payment_amt": 0.0,
                    "adv_recovery_pct": 0.0,
                    "retention_pct": 0.0,
                    "vat_pct": 15.0,
                    "special_terms": "",
                    "boq_items": []
                }
                if contract_drive_link:
                    st.session_state.pop("raw_contract_file_bytes", None)
                    st.session_state.pop("raw_contract_file_name", None)
                st.success(f"تم اعتماد العقد محلياً وترحيل بياناته سحابياً بالترويسات العربية المنسقة برقم: {clean_c_no}")
                st.rerun()

    # ── 3. مستخلصات مقاولي الباطن ──
    with tab_ipc:
        st.markdown('<div class="subcontract-section">سجل وإصدار المستخلصات</div>', unsafe_allow_html=True)
        
        ipc_action_sub = st.radio(
            "اختر العملية",
            ["سجل المستخلصات", "➕ إنشاء مستخلص جديد"], 
            horizontal=True,
            label_visibility="collapsed",
            key="ipc_main_radio"
        )

        if ipc_action_sub == "سجل المستخلصات":
            current_proj_ipcs = [i for i in ipc_data if i.get("project_name") == selected_proj]
            if not current_proj_ipcs:
                st.info("لا توجد مستخلصات مسجلة لهذا المشروع بعد.")
            else:
                ipc_display_rows = []
                for ip in current_proj_ipcs:
                    ipc_display_rows.append({
                        "رقم المستخلص": ip.get("ipc_number"),
                        "كود العقد": ip.get("subcontract_id"),
                        "رقم العقد": ip.get("contract_number"),
                        "المقاول": ip.get("contractor_name"),
                        "تاريخ المستخلص": ip.get("ipc_date"),
                        "فترة الاستخلاص": ip.get("billing_period", "-"),
                        "المصدر": ip.get("source", "مقدم من المقاول"),
                        "إجمالي الأعمال": f"{ip.get('current_gross_amount', ip.get('subtotal_current', 0)):,.2f}",
                        "الاستقطاعات": f"{ip.get('other_deductions_total', 0) + ip.get('advance_recovery', 0) + ip.get('retention_amount', 0):,.2f}",
                        "الضريبة": f"{ip.get('vat_amount', 0):,.2f}",
                        "صافي المستخلص": f"{ip.get('net_ipc_amount', ip.get('net_payable', 0)):,.2f} {ip.get('currency', 'SAR')}",
                        "الحالة": ip.get("status", "Draft")
                    })
                st.dataframe(pd.DataFrame(ipc_display_rows), use_container_width=True, hide_index=True)
                ipc_export_rows = []
                for ip in current_proj_ipcs:
                    ipc_export_rows.append({
                        "معرف المستخلص": ip.get("ipc_id"),
                        "رقم المستخلص": ip.get("ipc_number"),
                        "كود العقد": ip.get("subcontract_id"),
                        "رقم العقد": ip.get("contract_number"),
                        "المقاول": ip.get("contractor_name"),
                        "تاريخ المستخلص": ip.get("ipc_date"),
                        "فترة الاستخلاص": ip.get("billing_period", ""),
                        "المصدر": ip.get("source", ""),
                        "إجمالي الأعمال الحالية": safe_float(ip.get("current_gross_amount", ip.get("subtotal_current", 0))),
                        "استرداد الدفعة المقدمة": safe_float(ip.get("advance_recovery")),
                        "ضمان الأعمال": safe_float(ip.get("retention_amount")),
                        "استقطاعات أخرى": safe_float(ip.get("other_deductions_total")),
                        "الصافي قبل الضريبة": safe_float(ip.get("subtotal_before_vat")),
                        "ضريبة القيمة المضافة": safe_float(ip.get("vat_amount")),
                        "صافي المستخلص": safe_float(ip.get("net_ipc_amount", ip.get("net_payable", 0))),
                        "العملة": ip.get("currency", "SAR"),
                        "الحالة": canonical_ipc_status(ip.get("status", "Draft")),
                        "رابط مطالبة المقاول": ip.get("drive_submission_link") or ip.get("contractor_claim_file") or "",
                        "رابط المستخلص المعتمد": ip.get("drive_certified_link") or ip.get("certified_file") or ""
                    })
                to_excel_download_button(
                    pd.DataFrame(ipc_export_rows),
                    f"ipcs_{selected_proj}.xlsx",
                    "⬇️ تصدير سجل المستخلصات Excel",
                    "btn_xlsx_ipc_register"
                )

                st.markdown("---")
                st.markdown("##### 🔍 استعراض وطباعة تفاصيل مستخلص محفوظ")
                saved_ipc_options = {f"{ip.get('ipc_number')} — أمر شراء: {ip.get('contract_number')} ({ip.get('ipc_date')}) [{ip.get('status', 'Draft')}]": ip for ip in current_proj_ipcs}
                chosen_saved_ipc_label = st.selectbox("اختر مستخلصاً لفتح بياناته وجدول كمياته ومعاينته للطباعة:", list(saved_ipc_options.keys()), key="sel_open_saved_ipc")

                if chosen_saved_ipc_label:
                    selected_saved_ipc = saved_ipc_options[chosen_saved_ipc_label]
                    saved_items = selected_saved_ipc.get("items", [])
                    ipc_rec_id = selected_saved_ipc.get("ipc_id")
                    c_curr_saved = selected_saved_ipc.get("currency", "SAR")

                    with st.expander(f"ملف المستخلص: {selected_saved_ipc.get('ipc_number')} — الحالة: {selected_saved_ipc.get('status')}", expanded=True):
                        st.markdown(f"""
                        <div class="glass-card" style="direction:rtl; text-align:right;">
                            <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap: 10px; font-size: 13px;">
                                <div><b>المشروع:</b> {selected_saved_ipc.get('project_name')}</div>
                                <div><b>المقاول:</b> {selected_saved_ipc.get('contractor_name')}</div>
                                <div><b>رقم العقد:</b> <code>{selected_saved_ipc.get('contract_number')}</code></div>
                                <div><b>تاريخ التقديم:</b> {selected_saved_ipc.get('ipc_date')}</div>
                                <div><b>فترة الاستخلاص:</b> {selected_saved_ipc.get('billing_period', '-')}</div>
                                <div><b>مصدر الإدخال:</b> {selected_saved_ipc.get('source', 'مقدم من المقاول')}</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                        sm1, sm2, sm3 = st.columns(3)
                        sm1.metric("إجمالي الأعمال المنفذة", f"{selected_saved_ipc.get('current_gross_amount', 0):,.2f} {c_curr_saved}")
                        sm2.metric("مجموع الاستقطاعات", f"{selected_saved_ipc.get('other_deductions_total', 0) + selected_saved_ipc.get('advance_recovery', 0) + selected_saved_ipc.get('retention_amount', 0):,.2f} {c_curr_saved}", delta_color="inverse")
                        sm3.metric("صافي المستخلص النهائي", f"{selected_saved_ipc.get('net_ipc_amount', selected_saved_ipc.get('net_payable', 0)):,.2f} {c_curr_saved}")

                        if saved_items:
                            st.markdown('<div class="rtl-strict">', unsafe_allow_html=True)
                            st.markdown("**جدول الكميات والتوزيع المالي:**")
                            st.dataframe(pd.DataFrame(saved_items), use_container_width=True, hide_index=True)
                            st.markdown("</div>", unsafe_allow_html=True)

                        st.markdown("---")
                        col_p1, col_p2 = st.columns([1.5, 3])
                        with col_p1:
                            if st.button("🖨️ فتح شيت المستخلص للطباعة (A4 Landscape)", key=f"btn_print_saved_{ipc_rec_id}"):
                                st.session_state[f"show_saved_ipc_print_{ipc_rec_id}"] = not st.session_state.get(f"show_saved_ipc_print_{ipc_rec_id}", False)

                        if st.session_state.get(f"show_saved_ipc_print_{ipc_rec_id}", False):
                            hdr_d = {
                                "project_name": selected_saved_ipc.get("project_name"),
                                "contractor_name": selected_saved_ipc.get("contractor_name"),
                                "contract_number": selected_saved_ipc.get("contract_number"),
                                "ipc_number": selected_saved_ipc.get("ipc_number"),
                                "ipc_date": str(selected_saved_ipc.get("ipc_date")),
                                "billing_period": selected_saved_ipc.get("billing_period"),
                                "source": selected_saved_ipc.get("source")
                            }
                            tot_d = {
                                "current_gross_amount": safe_float(selected_saved_ipc.get("current_gross_amount")),
                                "cumulative_gross_amount": safe_float(selected_saved_ipc.get("cumulative_gross_amount")),
                                "remaining_gross_amount": safe_float(selected_saved_ipc.get("remaining_gross_amount")),
                                "adv_pct": safe_float(selected_saved_ipc.get("commercial_terms_snapshot", {}).get("adv_recovery_pct")),
                                "adv_recovery": safe_float(selected_saved_ipc.get("advance_recovery")),
                                "ret_pct": safe_float(selected_saved_ipc.get("commercial_terms_snapshot", {}).get("retention_pct")),
                                "retention_amount": safe_float(selected_saved_ipc.get("retention_amount")),
                                "other_deductions_total": safe_float(selected_saved_ipc.get("other_deductions_total")),
                                "other_deductions_list": selected_saved_ipc.get("other_deductions_items", []),
                                "subtotal_before_vat": safe_float(selected_saved_ipc.get("subtotal_before_vat")),
                                "vat_pct": safe_float(selected_saved_ipc.get("commercial_terms_snapshot", {}).get("vat_pct", 15.0)),
                                "vat_amount": safe_float(selected_saved_ipc.get("vat_amount")),
                                "net_ipc_amount": safe_float(selected_saved_ipc.get("net_ipc_amount", selected_saved_ipc.get("net_payable", 0)))
                            }
                            ipc_print_html = render_printable_ipc_sheet_html(hdr_d, saved_items, tot_d, c_curr_saved)
                            st.components.v1.html(ipc_print_html, height=800, scrolling=True)

                        st.markdown("---")
                        st.markdown("**دورة مراجعة واعتماد المستخلص**")
                        ipc_canon = canonical_ipc_status(selected_saved_ipc.get("status"))
                        reviewer = current_user_data.get("name", "Owner") if current_user_data else "Owner"
                        st.caption(f"الحالة الحالية: `{ipc_canon}`")
                        hist_rows = selected_saved_ipc.get("status_history") or []
                        if hist_rows:
                            st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)

                        def _apply_ipc_status(new_status, comment="", extra=None, do_sync=False):
                            for rec in ipc_data:
                                if rec.get("ipc_id") == ipc_rec_id:
                                    old_st = rec.get("status")
                                    rec["status"] = new_status
                                    if extra:
                                        rec.update(extra)
                                    append_status_history(rec, new_status, reviewer, comment)
                                    append_ipc_audit(ipc_rec_id, "Status Transitions", reviewer, "status", old_st, new_status, comment)
                                    if do_sync:
                                        sync_ipc_to_cloud(rec)
                                    break
                            save_json_data(IPC_FILE, ipc_data)
                            st.rerun()

                        if ipc_canon == "Draft":
                            wf1, wf2 = st.columns(2)
                            if wf1.button("إرسال للمراجعة (Submitted)", key=f"btn_submit_{ipc_rec_id}"):
                                _apply_ipc_status("Submitted", "تم الإرسال من المسودة")
                            if wf2.button("✅ اعتماد المستخلص النهائي ومزامنته سحابياً", type="primary", key=f"btn_approve_draft_{ipc_rec_id}"):
                                _apply_ipc_status(
                                    "Approved",
                                    "اعتماد مباشر من المسودة",
                                    {"approved_at": str(datetime.datetime.now()), "approved_by": reviewer},
                                    do_sync=True
                                )

                        elif ipc_canon in ("Submitted", "Under Review"):
                            return_reason = st.text_area("سبب الإرجاع للتصحيح", key=f"txt_return_reason_{ipc_rec_id}")
                            wf1, wf2, wf3 = st.columns(3)
                            if ipc_canon == "Submitted" and wf1.button("بدء المراجعة (Under Review)", key=f"btn_review_{ipc_rec_id}"):
                                _apply_ipc_status("Under Review", "بدء المراجعة")
                            if wf2.button("اعتماد (Approved)", type="primary", key=f"btn_approve_rev_{ipc_rec_id}"):
                                _apply_ipc_status(
                                    "Approved",
                                    "اعتماد بعد المراجعة",
                                    {"approved_at": str(datetime.datetime.now()), "approved_by": reviewer},
                                    do_sync=True
                                )
                            if wf3.button("إرجاع للتصحيح (Returned)", key=f"btn_return_{ipc_rec_id}"):
                                if not safe_str(return_reason):
                                    st.error("سبب الإرجاع إلزامي.")
                                else:
                                    _apply_ipc_status(
                                        "Returned",
                                        return_reason,
                                        {
                                            "return_reason": safe_str(return_reason),
                                            "returned_by": reviewer,
                                            "returned_at": str(datetime.datetime.now())
                                        }
                                    )

                        elif ipc_canon == "Returned":
                            st.warning(f"مرتجع للتصحيح — {selected_saved_ipc.get('return_reason', '')} / بواسطة {selected_saved_ipc.get('returned_by', '-')}")
                            if st.button("إعادة الإرسال بعد التصحيح (Submitted)", key=f"btn_resubmit_{ipc_rec_id}"):
                                _apply_ipc_status("Submitted", "إعادة إرسال بعد التصحيح")

                        elif ipc_canon == "Approved":
                            st.info("المستخلص معتمد ومقفول عن التعديل القياسي.")
                            if st.button("تأشير كمدفوع (Paid)", key=f"btn_paid_{ipc_rec_id}"):
                                _apply_ipc_status("Paid", "تم التأشير بالسداد")

                        elif ipc_canon == "Paid":
                            st.success("هذا المستخلص مدفوع.")

                st.markdown("---")
                with st.expander("إدارة المستخلصات"):
                    if chosen_saved_ipc_label:
                        target_del_ipc = saved_ipc_options[chosen_saved_ipc_label]
                        del_ipc_id = target_del_ipc.get("ipc_id")
                        if st.button(f"🗑️ حذف المستخلص {target_del_ipc.get('ipc_number')} وإعادة ضبط التراكميات", type="secondary", key=f"btn_del_ipc_{del_ipc_id}"):
                            ipc_data = [x for x in ipc_data if x.get("ipc_id") != del_ipc_id]
                            save_json_data(IPC_FILE, ipc_data)
                            st.success(f"تم حذف المستخلص {target_del_ipc.get('ipc_number')} بنجاح وإعادة ضبط التراكميات المالية.")
                            st.rerun()

        elif ipc_action_sub == "➕ إنشاء مستخلص جديد":
            if not current_proj_contracts:
                st.warning("يجب تسجيل عقد معتمد أولاً لإصدار مستخلص.")
            else:
                c_choices = {f"{c['contract_number']} — {c.get('vendor', {}).get('vendor_name')}": c for c in current_proj_contracts}
                selected_c_label = st.selectbox("اختر العقد المعتمد لإصدار المستخلص:", list(c_choices.keys()), key="ipc_contract_select")
                target_contract = c_choices[selected_c_label]
                target_sc_id = target_contract["subcontract_id"]
                target_comm = target_contract.get("commercial_terms", {})
                target_vendor = target_contract.get("vendor", {})
                c_curr = target_comm.get("currency", "SAR")
                c_total_val = safe_float(target_comm.get('total_including_vat', 0))

                contract_adv_val = safe_float(target_comm.get("adv_payment_amt"), 0.0)
                contract_adv_pct = safe_float(target_comm.get("adv_recovery_pct"), 0.0) if contract_adv_val > 0 else 0.0
                contract_ret_pct = safe_float(target_comm.get("retention_pct"), 0.0)
                contract_vat_pct = safe_float(target_comm.get("vat_pct"), 15.0)

                contract_boq_items = [b for b in boq_data if b.get("subcontract_id") == target_sc_id]

                st.markdown(f"""
                <div class="glass-card rtl-strict" style="direction:rtl; text-align:right;">
                    <div class="kpi-chip-grid" style="margin-bottom:12px;">
                        <div class="kpi-chip"><p class="kpi-chip-label">رقم أمر الشراء</p><p class="kpi-chip-value">{html.escape(str(target_contract.get('contract_number') or ''))}</p></div>
                        <div class="kpi-chip"><p class="kpi-chip-label">تاريخ التعاقد</p><p class="kpi-chip-value">{html.escape(str(target_contract.get('contract_date') or ''))}</p></div>
                        <div class="kpi-chip"><p class="kpi-chip-label">شروط السداد</p><p class="kpi-chip-value">{html.escape(str(target_comm.get('payment_term') or ''))}</p></div>
                        <div class="kpi-chip"><p class="kpi-chip-label">نسبة الضريبة</p><p class="kpi-chip-value">{html.escape(str(target_comm.get('vat_pct', 15)))}%</p></div>
                    </div>
                    <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap: 10px; font-size: 13px;">
                        <div><b>المقاول:</b> {html.escape(str(target_vendor.get('vendor_name') or ''))}</div>
                        <div><b>قيمة العقد الشاملة:</b> <b style="color:#0284c7;">{c_total_val:,.2f} {html.escape(str(c_curr))}</b></div>
                        <div><b>تاريخ نهاية العقد:</b> {html.escape(str(target_contract.get('delivery_date') or ''))}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # دالة لإنشاء وتحميل بنود المقايسة مع الكميات السابقة بدقة تامة
                def load_base_boq_items():
                    b_items = []
                    for idx, b_item in enumerate(contract_boq_items):
                        u_p = safe_float(b_item.get("unit_price"))
                        c_q = safe_float(b_item.get("contract_qty"))
                        accumulated_prev_q = get_previous_accumulated_qty(target_sc_id, b_item.get("boq_item_id"), b_item.get("description"), ipc_data)
                        b_items.append({
                            "sr_no": idx + 1,
                            "boq_item_id": b_item.get("boq_item_id"),
                            "description": b_item.get("description"),
                            "unit": b_item.get("unit", "EA"),
                            "contract_qty": c_q,
                            "prev_qty": accumulated_prev_q,
                            "submitted_qty": 0.0,
                            "current_qty": 0.0,
                            "qty_difference": 0.0,
                            "difference_reason": "",
                            "completion_pct": 0.0,
                            "unit_price": u_p
                        })
                    return b_items

                if ("ipc_form_state" not in st.session_state 
                    or st.session_state.get("active_sc_id") != target_sc_id 
                    or not st.session_state.ipc_form_state.get("items")):
                    
                    st.session_state.active_sc_id = target_sc_id
                    st.session_state.ipc_form_state = {
                        "ipc_number": f"IPC-{len([i for i in ipc_data if i.get('subcontract_id') == target_sc_id]) + 1:03d}",
                        "billing_period": f"شهر {datetime.date.today().strftime('%m / %Y')}",
                        "submission_date": datetime.date.today(),
                        "source": "مقدم من المقاول",
                        "vat_pct": contract_vat_pct,
                        "adv_pct": contract_adv_pct,
                        "ret_pct": contract_ret_pct,
                        "items": load_base_boq_items(),
                        "other_deductions": [],
                        "ocr_version": 0
                    }

                ipc_state = st.session_state.ipc_form_state

                # التأكد دائماً من أن قائمة البنود غير فارغة عند اختيار العقد
                if not ipc_state.get("items"):
                    ipc_state["items"] = load_base_boq_items()

                st.markdown('<div class="subcontract-section">1. بيانات ترويسة المستخلص</div>', unsafe_allow_html=True)
                
                v_num = ipc_state.get("ocr_version", 0)
                ip_c1, ip_c2, ip_c3, ip_c4 = st.columns(4)
                ipc_state["ipc_number"] = ip_c1.text_input("رقم المستخلص *", value=ipc_state.get("ipc_number", ""), key=f"inp_ipc_no_v{v_num}")
                ipc_state["billing_period"] = ip_c2.text_input("فترة الاستخلاص *", value=ipc_state.get("billing_period", ""), key=f"inp_ipc_per_v{v_num}")
                ipc_state["submission_date"] = ip_c3.date_input("تاريخ التقديم", value=ipc_state.get("submission_date", datetime.date.today()), key=f"inp_ipc_dt_v{v_num}")
                
                source_options = ["مقدم من المقاول", "كميات متفق عليها"]
                curr_src_idx = source_options.index(ipc_state.get("source")) if ipc_state.get("source") in source_options else 0
                selected_source = ip_c4.selectbox("مصدر الإدخال", source_options, index=curr_src_idx, key="ipc_hdr_source")
                ipc_state["source"] = selected_source

                uploaded_contractor_ipc = None
                uploaded_support_docs = []

                # إرفاق شيت المقاول واستخراج البيانات آلياً فقط عند اختيار "مقدم من المقاول"
                if selected_source == "مقدم من المقاول":
                    st.markdown("""
                    <div style="background:#EFF6FF; border:1px solid #BFDBFE; border-radius:8px; padding:12px; margin:10px 0;">
                        <b>إرفاق فاتورة / شيت المستخلص المقدم من المقاول:</b>
                    </div>
                    """, unsafe_allow_html=True)
                    col_file, col_btn = st.columns([3, 1])
                    uploaded_contractor_ipc = col_file.file_uploader("ملف المستخلص المقدم من المقاول", type=["pdf", "png", "jpg", "jpeg"], key="ipc_contractor_sheet_uploader")
                    
                    if uploaded_contractor_ipc is not None:
                        rewind_uploaded_file(uploaded_contractor_ipc)
                        if col_btn.button("🤖 استخراج وتفريغ الكميات", type="secondary", key="btn_extract_contractor_sheet"):
                            with st.spinner("جاري قراءة وثيقة المقاول وتدقيق ومطابقة البنود والكميات..."):
                                ext_ipc, err_ipc = extract_and_match_ipc_via_gemini(uploaded_contractor_ipc, target_contract, contract_boq_items, api_key)
                                if err_ipc:
                                    st.error(err_ipc)
                                elif ext_ipc:
                                    if ext_ipc.get("ipc_number"):
                                        ipc_state["ipc_number"] = safe_str(ext_ipc.get("ipc_number"))
                                    if ext_ipc.get("billing_period"):
                                        ipc_state["billing_period"] = safe_str(ext_ipc.get("billing_period"))
                                    if ext_ipc.get("ipc_date"):
                                        try:
                                            ipc_state["submission_date"] = datetime.datetime.strptime(str(ext_ipc["ipc_date"])[:10], "%Y-%m-%d").date()
                                        except Exception:
                                            pass

                                    discrepancies = []
                                    matched_list = ext_ipc.get("matched_items", [])
                                    
                                    for base_row in ipc_state["items"]:
                                        m_itm = next((m for m in matched_list if m.get("boq_item_id") == base_row.get("boq_item_id")), None)
                                        if not m_itm:
                                            m_itm = next((m for m in matched_list if safe_str(m.get("contract_description")).lower() in safe_str(base_row.get("description")).lower()), None)
                                        
                                        if m_itm:
                                            c_price = base_row["unit_price"]
                                            claimed_amt = safe_float(m_itm.get("claimed_amount"))
                                            exec_qty = safe_float(m_itm.get("executed_qty"))

                                            if c_price > 0 and claimed_amt > 0 and exec_qty == 1.0 and abs((exec_qty * c_price) - claimed_amt) > 0.01:
                                                calculated_qty = round(claimed_amt / c_price, 4)
                                                discrepancies.append(f"تم تدقيق البند '{base_row['description']}': الفاتورة تطالب بمبلغ {claimed_amt:,.2f} بينما سعر الوحدة التعاقدي هو {c_price:,.2f}. تم ضبط الكمية الحالية المنفذة إلى ({calculated_qty}).")
                                                exec_qty = calculated_qty

                                            base_row["submitted_qty"] = exec_qty
                                            base_row["current_qty"] = exec_qty
                                            base_row["qty_difference"] = 0.0
                                            base_row["difference_reason"] = ""

                                    ipc_state["discrepancies"] = discrepancies
                                    ipc_state["ocr_version"] = ipc_state.get("ocr_version", 0) + 1
                                    st.success("✅ تم تفريغ بيانات الترويسة والكميات بنجاح! يمكنك مراجعة وتعديل أي كمية يدوياً في الجدول أدناه.")
                                    st.rerun()

                with st.expander("📎 إرفاق المستندات الداعمة للفاتورة (Supporting Documents)"):
                    st.caption("ارفع المستندات الداعمة مثل: شيتات الحصر الهندسي، محاضر استلام الأعمال (RFI)، أو نتائج الاختبارات:")
                    uploaded_support_docs = st.file_uploader("مستندات الدعم", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True, key="ipc_support_docs_uploader")
                    if uploaded_support_docs:
                        for _sdoc in uploaded_support_docs:
                            rewind_uploaded_file(_sdoc)
                        st.success(f"تم إدراج عدد ({len(uploaded_support_docs)}) مستند دعم وسيتم ربطها بسجل المستخلص.")

                st.markdown('<div class="subcontract-section">2. إدارة وحساب كميات وقيم بنود المستخلص</div>', unsafe_allow_html=True)
                st.info("💡 **الكمية المعتمدة (Certified)** هي أساس الحساب المالي. الكمية المقدمة من المقاول تُحفظ للمقارنة ولا تدخل في الإجمالي أو الضريبة أو الصافي.")

                editor_rows = []
                for itm in ipc_state["items"]:
                    submitted_q = safe_float(itm.get("submitted_qty", itm.get("current_qty")))
                    editor_rows.append({
                        "م": itm.get("sr_no"),
                        "boq_item_id": itm.get("boq_item_id"),
                        "توصيف الأعمال": itm.get("description"),
                        "الوحدة": itm.get("unit"),
                        "الكمية التعاقدية": safe_float(itm.get("contract_qty")),
                        "الكمية السابقة": safe_float(itm.get("prev_qty")),
                        "الكمية المقدمة": submitted_q,
                        "الكمية المعتمدة": safe_float(itm.get("current_qty")),
                        "فئة السعر": safe_float(itm.get("unit_price")),
                        "سبب الفروقات": itm.get("difference_reason") or ""
                    })

                df_for_editor = pd.DataFrame(editor_rows)
                editor_key = f"ipc_qty_editor_v{ipc_state.get('ocr_version', 0)}"
                
                edited_df = st.data_editor(
                    df_for_editor,
                    column_config={
                        "م": st.column_config.NumberColumn("م", disabled=True, width="small"),
                        "boq_item_id": None,
                        "توصيف الأعمال": st.column_config.TextColumn("توصيف الأعمال", disabled=True, width="large"),
                        "الوحدة": st.column_config.TextColumn("الوحدة", disabled=True, width="small"),
                        "الكمية التعاقدية": st.column_config.NumberColumn("الكمية التعاقدية", format="%.2f", disabled=True),
                        "الكمية السابقة": st.column_config.NumberColumn("الكمية السابقة", format="%.4f", disabled=True),
                        "الكمية المقدمة": st.column_config.NumberColumn("الكمية المقدمة (Submitted)", format="%.4f", disabled=True),
                        "الكمية المعتمدة": st.column_config.NumberColumn("الكمية المعتمدة (Certified — انقر للتعديل)", format="%.4f", required=True, disabled=False),
                        "فئة السعر": st.column_config.NumberColumn(f"فئة السعر ({c_curr})", format="%.2f", disabled=True),
                        "سبب الفروقات": st.column_config.TextColumn("سبب الفروقات", disabled=False)
                    },
                    use_container_width=True,
                    hide_index=True,
                    key=editor_key
                )

                calculated_items = []
                sheet_rows = []
                total_previous_certified_amount = 0.0
                total_current_gross_amount = 0.0
                total_cumulative_gross_amount = 0.0
                total_remaining_amount = 0.0

                for idx, row in edited_df.iterrows():
                    rate = safe_float(row["فئة السعر"])
                    c_qty = safe_float(row["الكمية التعاقدية"])
                    p_qty = safe_float(row["الكمية السابقة"])
                    submitted_qty = safe_float(row["الكمية المقدمة"])
                    cur_qty = safe_float(row["الكمية المعتمدة"])
                    reason_txt = safe_str(row.get("سبب الفروقات", ""))

                    cum_qty = p_qty + cur_qty
                    rem_qty = c_qty - cum_qty

                    prev_amt = p_qty * rate
                    cur_amt = cur_qty * rate
                    cum_amt = cum_qty * rate
                    rem_amt = rem_qty * rate

                    total_previous_certified_amount += prev_amt
                    total_current_gross_amount += cur_amt
                    total_cumulative_gross_amount += cum_amt
                    total_remaining_amount += rem_amt

                    qty_item = enrich_ipc_item_qty_fields({
                        "sr_no": int(row["م"]),
                        "boq_item_id": row["boq_item_id"],
                        "description": row["توصيف الأعمال"],
                        "unit": row["الوحدة"],
                        "contract_qty": c_qty,
                        "prev_qty": p_qty,
                        "submitted_qty": submitted_qty,
                        "current_qty": cur_qty,
                        "difference_reason": reason_txt,
                        "unit_price": rate,
                        "prev_amt": prev_amt,
                        "current_amt": cur_amt,
                        "cum_amt": cum_amt,
                        "remaining_amt": rem_amt
                    })
                    calculated_items.append(qty_item)

                    sheet_rows.append({
                        "م": row["م"],
                        "توصيف الأعمال": row["توصيف الأعمال"],
                        "الوحدة": row["الوحدة"],
                        "الكمية التعاقدية": f"{c_qty:,.2f}",
                        "الكمية السابقة": f"{p_qty:,.4f}",
                        "الكمية المقدمة": f"{submitted_qty:,.4f}",
                        "الكمية المعتمدة": f"{cur_qty:,.4f}",
                        "فرق الكميات": f"{qty_item.get('qty_difference', 0):,.4f}",
                        "نسبة الإنجاز %": f"{qty_item.get('completion_pct', 0):,.2f}",
                        "تجاوز كمية": "تجاوز كمية" if qty_item.get("qty_overrun") else "",
                        "الكمية التراكمية": f"{qty_item.get('cum_qty', cum_qty):,.4f}",
                        "الكمية المتبقية": f"{qty_item.get('remaining_qty', rem_qty):,.4f}",
                        "فئة السعر": f"{rate:,.2f}",
                        "القيمة الحالية": f"{cur_amt:,.2f}",
                        "القيمة التراكمية": f"{cum_amt:,.2f}",
                        "القيمة المتبقية": f"{rem_amt:,.2f}"
                    })

                ipc_state["items"] = calculated_items
                st.markdown('<div class="rtl-strict">', unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(sheet_rows), use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)
                if any(itm.get("qty_overrun") for itm in calculated_items):
                    st.error("تجاوز كمية: توجد بنود تجاوزت الكمية التعاقدية بالتراكمي المعتمد.")

                st.markdown('<div class="subcontract-section">3. الاستقطاعات والخصومات الأخرى</div>', unsafe_allow_html=True)
                with st.expander("➕ إضافة استقطاع آخر (غرامات / تلفيات / خصومات موقع)", expanded=False):
                    od_c1, od_c2, od_c3, od_c4 = st.columns([2, 1.2, 1.8, 1])
                    new_od_desc = od_c1.text_input("توصيف الخصم", key="in_od_desc")
                    new_od_amt = od_c2.number_input(f"قيمة الخصم ({c_curr})", min_value=0.0, step=100.0, key="in_od_amt")
                    new_od_ref = od_c3.text_input("السبب / رقم المرجع", key="in_od_ref")
                    
                    if od_c4.button("إدراج الخصم", key="btn_add_other_ded"):
                        if new_od_desc.strip() and new_od_amt > 0:
                            ipc_state["other_deductions"].append({
                                "id": str(uuid.uuid4())[:6],
                                "description": new_od_desc.strip(),
                                "amount": safe_float(new_od_amt),
                                "reference": new_od_ref.strip()
                            })
                            st.rerun()

                total_other_deductions = 0.0
                if ipc_state.get("other_deductions"):
                    st.markdown("**قائمة الاستقطاعات الأخرى المسجلة:**")
                    od_display_list = []
                    for idx_od, od_item in enumerate(ipc_state["other_deductions"]):
                        total_other_deductions += safe_float(od_item["amount"])
                        od_display_list.append({
                            "م": idx_od + 1,
                            "التوصيف": od_item["description"],
                            "القيمة": f"{safe_float(od_item['amount']):,.2f} {c_curr}",
                            "السبب / المرجع": od_item["reference"]
                        })
                    st.dataframe(pd.DataFrame(od_display_list), use_container_width=True, hide_index=True)
                    if st.button("إفراغ الاستقطاعات الأخرى", key="btn_clear_other_ded"):
                        ipc_state["other_deductions"] = []
                        st.rerun()

                st.markdown('<div class="subcontract-section">4. الهيكل المالي وصافي المستخلص</div>', unsafe_allow_html=True)
                
                c_adv_pct = safe_float(ipc_state.get("adv_pct", contract_adv_pct))
                c_ret_pct = safe_float(ipc_state.get("ret_pct", contract_ret_pct))
                c_vat_pct = safe_float(ipc_state.get("vat_pct", contract_vat_pct))

                advance_recovery = total_current_gross_amount * (c_adv_pct / 100.0)
                retention_amount = total_current_gross_amount * (c_ret_pct / 100.0)
                
                subtotal_before_vat = total_current_gross_amount - advance_recovery - retention_amount - total_other_deductions
                vat_amount = subtotal_before_vat * (c_vat_pct / 100.0)
                net_ipc_amount = subtotal_before_vat + vat_amount

                is_negative_net = net_ipc_amount < 0
                if is_negative_net:
                    st.error(f"🚨 تحذير مالي حرج: مجموع الاستقطاعات ({advance_recovery + retention_amount + total_other_deductions:,.2f}) تجاوز قيمة الأعمال، مما جعل الصافي سالباً ({net_ipc_amount:,.2f} {c_curr})!")

                r_c1, r_c2, r_c3 = st.columns(3)
                r_c1.metric("إجمالي الأعمال المنفذة", f"{total_current_gross_amount:,.2f} {c_curr}")
                r_c2.metric("مجموع الاستقطاعات", f"{advance_recovery + retention_amount + total_other_deductions:,.2f} {c_curr}", delta=f"-{(advance_recovery + retention_amount + total_other_deductions):,.2f}", delta_color="inverse")
                r_c3.metric("الصافي قبل الضريبة", f"{subtotal_before_vat:,.2f} {c_curr}")

                r_c4, r_c5 = st.columns([1.5, 2])
                r_c4.metric(f"ضريبة القيمة المضافة ({c_vat_pct}%)", f"{vat_amount:,.2f} {c_curr}")
                r_c5.metric("صافي المستخلص النهائي", f"{net_ipc_amount:,.2f} {c_curr}", delta="المبلغ المستحق للصرف", delta_color="normal" if not is_negative_net else "inverse")

                st.info(f"**صافي المستخلص المستحق للصرف كتابةً:** {number_to_words_ar(net_ipc_amount, c_curr)}")

                totals_dict = {
                    "current_gross_amount": total_current_gross_amount,
                    "cumulative_gross_amount": total_cumulative_gross_amount,
                    "remaining_gross_amount": total_remaining_amount,
                    "adv_pct": c_adv_pct,
                    "adv_recovery": advance_recovery,
                    "ret_pct": c_ret_pct,
                    "retention_amount": retention_amount,
                    "other_deductions_total": total_other_deductions,
                    "other_deductions_list": ipc_state.get("other_deductions", []),
                    "subtotal_before_vat": subtotal_before_vat,
                    "vat_pct": c_vat_pct,
                    "vat_amount": vat_amount,
                    "net_ipc_amount": net_ipc_amount
                }

                c_btn1, c_btn2, c_btn3 = st.columns([1.5, 1.8, 1.8])
                show_ipc_preview = c_btn1.button("معاينة وطباعة شيت المستخلص", key="btn_preview_ipc")
                save_draft_btn = c_btn2.button("💾 حفظ كمسودة", type="secondary", use_container_width=True, key="btn_save_ipc_draft")
                save_approve_btn = c_btn3.button("اعتماد وحفظ المستخلص ومزامنته سحابياً", type="primary", use_container_width=True, key="btn_save_ipc_final")

                if show_ipc_preview:
                    if not safe_str(ipc_state["ipc_number"]):
                        st.warning("يرجى إدخال رقم المستخلص لعرض شيت الطباعة المعتمد.")
                    elif not calculated_items:
                        st.warning("لا توجد بنود محملة في المستخلص للمعاينة.")
                    else:
                        header_dict = {
                            "project_name": target_contract.get("project_name"),
                            "contractor_name": target_vendor.get("vendor_name"),
                            "contract_number": target_contract.get("contract_number"),
                            "ipc_number": ipc_state["ipc_number"],
                            "ipc_date": str(ipc_state["submission_date"]),
                            "billing_period": ipc_state.get("billing_period"),
                            "source": ipc_state.get("source")
                        }
                        ipc_html = render_printable_ipc_sheet_html(header_dict, calculated_items, totals_dict, c_curr)
                        st.markdown("---")
                        st.components.v1.html(ipc_html, height=800, scrolling=True)

                if save_draft_btn or save_approve_btn:
                    if not safe_str(ipc_state["ipc_number"]):
                        st.error("يرجى إدخال رقم المستخلص كحقل إلزامي.")
                    elif is_negative_net and save_approve_btn:
                        st.error("لا يمكن اعتماد مستخلص بصافي سالب. يرجى تصحيح الاستقطاعات.")
                    else:
                        status_val = "Draft" if save_draft_btn else "Approved"
                        actor_name = current_user_data.get("name", "User") if current_user_data else "User"
                        ipc_id = f"IPC-{target_sc_id}-{str(uuid.uuid4())[:6]}"
                        saved_claim_path = ""
                        claim_drive_link = ""
                        saved_support_paths = []
                        support_drive_links = []
                        if uploaded_contractor_ipc is not None:
                            rewind_uploaded_file(uploaded_contractor_ipc)
                            saved_claim_path = persist_uploaded_file(uploaded_contractor_ipc, f"tmp_{ipc_id}_claim")
                            rewind_uploaded_file(uploaded_contractor_ipc)
                            claim_drive_link, _ = upload_file_to_drive(
                                uploaded_contractor_ipc,
                                getattr(uploaded_contractor_ipc, "name", "contractor_claim.pdf"),
                                DRIVE_SUB_FOLDERS["submissions"]
                            )
                        if uploaded_support_docs:
                            for i, sdoc in enumerate(uploaded_support_docs):
                                rewind_uploaded_file(sdoc)
                                spath = persist_uploaded_file(sdoc, f"tmp_{ipc_id}_support_{i+1}")
                                rewind_uploaded_file(sdoc)
                                if spath:
                                    saved_support_paths.append(spath)
                                slink, _ = upload_file_to_drive(
                                    sdoc,
                                    getattr(sdoc, "name", f"support_{i+1}.pdf"),
                                    DRIVE_SUB_FOLDERS["certified"]
                                )
                                if slink:
                                    support_drive_links.append(slink)
                        new_ipc_record = {
                            "ipc_id": ipc_id,
                            "ipc_number": safe_str(ipc_state["ipc_number"]),
                            "subcontract_id": target_sc_id,
                            "contract_number": target_contract.get("contract_number"),
                            "contractor_name": target_vendor.get("vendor_name"),
                            "contractor_id": target_vendor.get("vendor_id"),
                            "project_name": selected_proj,
                            "project_id": selected_proj,
                            "ipc_date": str(ipc_state["submission_date"]),
                            "billing_period": safe_str(ipc_state.get("billing_period")),
                            "source": safe_str(ipc_state.get("source")),
                            "currency": c_curr,
                            "commercial_terms_snapshot": {
                                "adv_recovery_pct": c_adv_pct,
                                "retention_pct": c_ret_pct,
                                "vat_pct": c_vat_pct
                            },
                            "current_gross_amount": float(total_current_gross_amount),
                            "cumulative_gross_amount": float(total_cumulative_gross_amount),
                            "remaining_gross_amount": float(total_remaining_amount),
                            "advance_recovery": float(advance_recovery),
                            "retention_amount": float(retention_amount),
                            "other_deductions_total": float(total_other_deductions),
                            "other_deductions_items": ipc_state.get("other_deductions", []),
                            "subtotal_before_vat": float(subtotal_before_vat),
                            "vat_amount": float(vat_amount),
                            "net_ipc_amount": float(net_ipc_amount),
                            "status": status_val,
                            "status_history": [{
                                "status": status_val,
                                "user": current_user_data.get("name", "User") if current_user_data else "User",
                                "timestamp": str(datetime.datetime.now()),
                                "comment": "IPC Creation"
                            }],
                            "created_at": str(datetime.datetime.now()),
                            "created_by": current_user_data.get("name", "User") if current_user_data else "User",
                            "items": calculated_items,
                            "local_contractor_claim_file": saved_claim_path,
                            "contractor_claim_file": claim_drive_link or saved_claim_path,
                            "local_support_files": saved_support_paths,
                            "support_files": support_drive_links or saved_support_paths,
                            "certified_file": " | ".join(support_drive_links),
                            "drive_submission_link": claim_drive_link,
                            "drive_certified_link": " | ".join(support_drive_links)
                        }

                        ipc_data.append(new_ipc_record)
                        save_json_data(IPC_FILE, ipc_data)
                        creator_name = current_user_data.get("name", "User") if current_user_data else "User"
                        append_ipc_audit(ipc_id, "IPC Creation", creator_name, "status", "", status_val)
                        for itm in calculated_items:
                            if abs(safe_float(itm.get("qty_difference"))) > 0.0001:
                                append_ipc_audit(
                                    ipc_id, "Quantity Overrides", creator_name,
                                    f"current_qty:{itm.get('boq_item_id')}",
                                    itm.get("submitted_qty"), itm.get("current_qty"),
                                    itm.get("difference_reason") or ""
                                )
                        if ipc_state.get("other_deductions"):
                            append_ipc_audit(
                                ipc_id, "Deductions Updated", creator_name,
                                "other_deductions", "[]",
                                json.dumps(ipc_state.get("other_deductions"), ensure_ascii=False)
                            )

                        if status_val == "Approved":
                            with st.spinner("جاري ترحيل المستخلص ومزامنته سحابياً مع Google Sheets..."):
                                sync_ipc_to_cloud(new_ipc_record)
                                save_json_data(IPC_FILE, ipc_data)

                        ipc_widget_keys = [
                            f"inp_ipc_no_v{v_num}", f"inp_ipc_per_v{v_num}", f"inp_ipc_dt_v{v_num}", "ipc_hdr_source",
                            editor_key, "in_od_desc", "in_od_amt", "in_od_ref",
                            "ipc_contractor_sheet_uploader", "ipc_support_docs_uploader"
                        ]
                        for k in ipc_widget_keys:
                            st.session_state.pop(k, None)

                        st.session_state.ipc_form_state = {
                            "ipc_number": "",
                            "billing_period": "",
                            "submission_date": datetime.date.today(),
                            "source": "مقدم من المقاول",
                            "items": load_base_boq_items(),
                            "other_deductions": [],
                            "ocr_version": 0
                        }

                        if status_val == "Draft":
                            st.success("✅ تم حفظ المستخلص كمسودة محلياً بنجاح.")
                        else:
                            st.success("✅ تم اعتماد وحفظ المستخلص وترحيل بياناته سحابياً بنجاح.")
                        st.rerun()

    # ── 4. لوحة الرقابة وسجل التدقيق ──
    with tab_control:
        st.markdown('<div class="subcontract-section">لوحة الرقابة المالية والتحكم بالكميات</div>', unsafe_allow_html=True)
        actor_name = current_user_data.get("name", "User") if current_user_data else "User"

        contractor_rows = []
        vendor_map = {}
        for c in current_proj_contracts:
            vname = c.get("vendor", {}).get("vendor_name") or "غير محدد"
            c_val = safe_float(c.get("commercial_terms", {}).get("total_including_vat", 0))
            consumed, remaining, pct = get_contract_consumption_metrics(c.get("subcontract_id"), c_val, ipc_data)
            bucket = vendor_map.setdefault(vname, {"قيمة العقود": 0.0, "المعتمد حتى تاريخه": 0.0})
            bucket["قيمة العقود"] += c_val
            bucket["المعتمد حتى تاريخه"] += consumed
        for vname, vals in vendor_map.items():
            contractor_rows.append({
                "المقاول": vname,
                "إجمالي قيمة العقود": vals["قيمة العقود"],
                "المعتمد حتى تاريخه": vals["المعتمد حتى تاريخه"],
                "المتبقي": vals["قيمة العقود"] - vals["المعتمد حتى تاريخه"]
            })
        if contractor_rows:
            st.markdown("**مستوى المقاول: قيمة العقود مقابل المعتمد**")
            st.dataframe(pd.DataFrame(contractor_rows), use_container_width=True, hide_index=True)
        else:
            st.info("لا توجد بيانات مقاولين لعرض مؤشرات الرقابة بعد.")

        contract_ctrl_rows = []
        for c in current_proj_contracts:
            sc_id = c.get("subcontract_id")
            c_val = safe_float(c.get("commercial_terms", {}).get("total_including_vat", 0))
            consumed, remaining, pct = get_contract_consumption_metrics(sc_id, c_val, ipc_data)
            contract_ctrl_rows.append({
                "رقم العقد": c.get("contract_number"),
                "المقاول": c.get("vendor", {}).get("vendor_name"),
                "قيمة العقد": c_val,
                "المنفذ من المستخلصات المعتمدة والمدفوعة": consumed,
                "المتبقي": remaining,
                "نسبة التنفيذ %": round(pct, 2)
            })
        if contract_ctrl_rows:
            st.markdown("**مستوى العقد: الكميات/القيم المنفذة من المستخلصات المعتمدة والمدفوعة فقط**")
            st.dataframe(pd.DataFrame(contract_ctrl_rows), use_container_width=True, hide_index=True)

        overrun_rows = collect_quantity_overruns(current_proj_contracts, boq_data, ipc_data)
        st.markdown("**علم تجاوز الكمية**")
        if overrun_rows:
            st.error("يوجد بنود تجاوزت الكمية التعاقدية بالتراكمي المعتمد.")
            st.dataframe(pd.DataFrame(overrun_rows), use_container_width=True, hide_index=True)
        else:
            st.success("لا يوجد تجاوز كمية على بنود العقود المعتمدة حالياً.")

        st.markdown("---")
        st.markdown('<div class="subcontract-section">سجل التدقيق غير القابل للتعديل</div>', unsafe_allow_html=True)
        audit_trail = load_json_data(IPC_AUDIT_FILE)
        if not audit_trail:
            st.info("سجل التدقيق فارغ حتى تنفيذ إجراء رقابي (إنشاء / تعديل كمية / انتقال حالة / استقطاعات).")
        else:
            audit_sorted = sorted(audit_trail, key=lambda x: str(x.get("timestamp", "")), reverse=True)
            audit_df = pd.DataFrame(audit_sorted)
            st.dataframe(audit_df, use_container_width=True, hide_index=True)
            to_excel_download_button(
                audit_df,
                f"ipc_audit_trail_{selected_proj}.xlsx",
                "⬇️ تصدير سجل التدقيق Excel",
                "btn_xlsx_audit_trail"
            )