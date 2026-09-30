import streamlit as st
import pandas as pd
import json
import os
import uuid
import html
import tempfile
from datetime import datetime, timezone
import numpy as np

try:
    import gspread
    from google.oauth2.service_account import Credentials
    G_CLOUD_AVAILABLE = True
except ImportError:
    G_CLOUD_AVAILABLE = False

# ثوابت مسارات الملفات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_BOQ_FILE = os.path.join(BASE_DIR, "client_boq_local.json")
SUPPORTING_DOCS_FILE = os.path.join(BASE_DIR, "client_supporting_docs_local.json")
CLIENT_INVOICE_HEADERS_FILE = os.path.join(BASE_DIR, "client_invoices_headers_local.json")
CLIENT_INVOICE_ITEMS_FILE = os.path.join(BASE_DIR, "client_invoices_items_local.json")
PROJECTS_FILE = os.path.join(BASE_DIR, "projects.json")
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "coral-idiom-265509-184c07e5e6c0.json")

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

API_KEY_FILE = os.path.join(BASE_DIR, "api_key.txt")
CLIENT_SPREADSHEET_NAME = "Client_Invoices_Master"
CLIENT_BOQ_WORKSHEET = "Client_BOQ"
CLIENT_SPREADSHEET_ID = "1UmTGZ_KKfyQnF4Qs0cbTb2kQlcZkvArLq_ctiE1NVFE"

CLIENT_BOQ_HEADERS = [
    "boq_item_id",
    "project_id",
    "item_no",
    "description",
    "unit",
    "contract_qty",
    "contract_rate",
    "contract_amount",
]

CLIENT_IPC_HEADERS_WORKSHEET = "Client_IPC_Headers"
CLIENT_IPC_ITEMS_WORKSHEET = "Client_IPC_Items"

CLIENT_IPC_HEADER_SHEET_COLS = [
    "ipc_id",
    "project_id",
    "project_name",
    "ipc_number",
    "contract_wo_number",
    "billing_period",
    "period_from",
    "period_to",
    "issue_date",
    "submission_date",
    "currency",
    "retention_rate",
    "advance_deduction",
    "other_deductions",
    "vat_rate",
    "total_current_works",
    "total_cumulative_works",
    "retention_amount",
    "net_before_vat",
    "vat_amount",
    "net_payable",
    "gross_amount",
    "deductions",
    "net_amount",
    "approval_status",
    "payment_status",
    "status",
    "client_name",
    "contractor_name",
    "created_at",
    "created_by",
]

CLIENT_IPC_ITEM_SHEET_COLS = [
    "ipc_id",
    "project_id",
    "boq_item_id",
    "item_no",
    "description",
    "unit",
    "contract_qty",
    "contract_rate",
    "previous_qty",
    "current_qty",
    "cumulative_qty",
    "current_amount",
    "cumulative_amount",
    "is_overrun",
]

SUPPORTING_DOCUMENT_TYPES = (
    "QC Request",
    "Inspection Request",
    "Approved Measurement",
    "Other Supporting Document",
)

IPC_APPROVED_STATUSES = {"Approved", "معتمد", "Paid", "مدفوع", "معتمد ومسدد"}
APPROVAL_STATUS_OPTIONS = ("Draft", "Submitted", "Approved", "Returned")
PAYMENT_STATUS_OPTIONS = ("Not Paid", "Partially Paid", "Paid")
INVOICE_CURRENCIES = ("SAR", "EGP", "USD")


def _ui_currency():
    val = st.session_state.get("project_currency")
    if val is None or str(val).strip() == "":
        return "ج.م"
    return str(val).strip()
INVOICE_ITEM_DISPLAY_COLS = [
    "boq_item_id",
    "item_no",
    "description",
    "unit",
    "contract_qty",
    "contract_rate",
    "previous_qty",
    "current_qty",
    "cumulative_qty",
    "current_amount",
    "cumulative_amount",
    "is_overrun",
]

SUPPORTING_DOCUMENT_FIELDS = [
    "id",
    "ipc_id",
    "project_id",
    "document_type",
    "file_name",
    "upload_date",
    "uploaded_by",
    "file_reference",
    "extracted_boq_item_id",
    "extracted_description",
    "extracted_qty",
    "extracted_unit",
    "approval_status",
    "ai_confidence",
    "user_confirmed",
    "source_document_id",
]


def load_json(file_path, default_empty=list):
    """تحميل آمن لملفات JSON"""
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"خطأ في قراءة {file_path}: {e}")
    return default_empty()


def save_json(file_path, data):
    """حفظ JSON كتابة ذرية: ملف مؤقت في نفس المجلد ثم os.replace."""
    tmp_path = None
    try:
        directory = os.path.dirname(os.path.abspath(file_path)) or os.getcwd()
        os.makedirs(directory, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".tmp_json_",
            suffix=".json",
            delete=False,
        ) as tmp:
            tmp_path = tmp.name
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, file_path)
        tmp_path = None
        return True
    except Exception as e:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        st.error(f"خطأ في حفظ {file_path}: {e}")
        return False


def _current_uploader_name():
    return str(st.session_state.get("current_user") or "system")


def create_supporting_document_entry(
    project_id,
    document_type,
    file_name,
    file_reference,
    ipc_id=None,
    uploaded_by=None,
):
    """يبني سجل وثيقة داعمة بالشكل المعتمد للمستخلصات (بدون استخراج AI حالياً)."""
    dtype = document_type if document_type in SUPPORTING_DOCUMENT_TYPES else "Other Supporting Document"
    return {
        "id": f"DOC-{uuid.uuid4().hex[:12]}",
        "ipc_id": ipc_id,
        "project_id": "" if project_id is None else str(project_id),
        "document_type": dtype,
        "file_name": file_name or "",
        "upload_date": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": uploaded_by or _current_uploader_name(),
        "file_reference": file_reference or "local",
        "extracted_boq_item_id": None,
        "extracted_description": None,
        "extracted_qty": None,
        "extracted_unit": None,
        "approval_status": None,
        "ai_confidence": None,
        "user_confirmed": False,
        "source_document_id": None,
    }


def load_supporting_documents(project_id=None):
    """تحميل آمن لأرشيف الوثائق الداعمة مع إمكانية التصفية بالمشروع."""
    rows = load_json(SUPPORTING_DOCS_FILE, default_empty=list)
    if not isinstance(rows, list):
        rows = []
    if project_id is None or project_id == "":
        return rows
    pid = str(project_id)
    return [r for r in rows if isinstance(r, dict) and str(r.get("project_id", "")) == pid]


def save_supporting_document(doc_record):
    """يلحق سجلاً واحداً بـ client_supporting_docs_local.json بعد تطبيع الحقول."""
    if not isinstance(doc_record, dict):
        return False, "سجل الوثيقة غير صالح."
    project_id = doc_record.get("project_id")
    if not project_id:
        return False, "project_id مطلوب لحفظ الوثيقة الداعمة."
    normalized = create_supporting_document_entry(
        project_id=project_id,
        document_type=doc_record.get("document_type") or "Other Supporting Document",
        file_name=doc_record.get("file_name", ""),
        file_reference=doc_record.get("file_reference") or "local",
        ipc_id=doc_record.get("ipc_id"),
        uploaded_by=doc_record.get("uploaded_by"),
    )
    if doc_record.get("id"):
        normalized["id"] = str(doc_record["id"])
    if doc_record.get("upload_date"):
        normalized["upload_date"] = str(doc_record["upload_date"])
    for key in (
        "extracted_boq_item_id",
        "extracted_description",
        "extracted_qty",
        "extracted_unit",
        "approval_status",
        "ai_confidence",
        "source_document_id",
    ):
        if key in doc_record:
            normalized[key] = doc_record.get(key)
    if "user_confirmed" in doc_record:
        normalized["user_confirmed"] = bool(doc_record.get("user_confirmed"))

    rows = load_supporting_documents()
    replaced = False
    for i, existing in enumerate(rows):
        if isinstance(existing, dict) and existing.get("id") == normalized["id"]:
            rows[i] = normalized
            replaced = True
            break
    if not replaced:
        rows.append(normalized)
    if save_json(SUPPORTING_DOCS_FILE, rows):
        return True, normalized
    return False, "تعذر حفظ أرشيف الوثائق الداعمة."


def ensure_supporting_docs_store():
    if not os.path.exists(SUPPORTING_DOCS_FILE):
        save_json(SUPPORTING_DOCS_FILE, [])


def _build_project_options(projects_data):
    """يدعم قائمة أسماء نصية أو قائمة كائنات {id, name}."""
    options = {}
    if not isinstance(projects_data, list):
        return options
    for i, p in enumerate(projects_data):
        if isinstance(p, str) and p.strip():
            options[p.strip()] = p.strip()
        elif isinstance(p, dict):
            pid = p.get("id") or p.get("project_id") or p.get("name") or f"P{i+1}"
            name = p.get("name") or p.get("project_name") or f"Project {pid}"
            options[str(name)] = str(pid)
    return options


AMOUNT_ABS_TOLERANCE = 0.50
AMOUNT_REL_TOLERANCE = 0.001


def _to_numeric_series(series):
    """تحويل رقمي آمن للخلايا الفارغة والنصوص والمسافات."""
    cleaned = series.astype(str).str.replace(",", "", regex=False).str.strip()
    cleaned = cleaned.replace({"": np.nan, "nan": np.nan, "None": np.nan, "-": np.nan})
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def apply_boq_amount_checks(df):
    """يتحقق من القيمة مع سماحية فروقات التقريب المستخرجة من PDF."""
    work = df.copy()
    work["contract_qty"] = _to_numeric_series(work["contract_qty"]).round(4)
    work["contract_rate"] = _to_numeric_series(work["contract_rate"]).round(4)
    work["contract_amount"] = _to_numeric_series(work["contract_amount"]).round(2)
    work["calculated_amount"] = (work["contract_qty"] * work["contract_rate"]).round(2)
    zero_amount = work["contract_amount"].abs() < 0.0001
    work.loc[zero_amount, "contract_amount"] = work.loc[zero_amount, "calculated_amount"]
    work["amount_diff"] = (work["contract_amount"] - work["calculated_amount"]).abs().round(2)
    rel = work["amount_diff"] / work["calculated_amount"].abs().replace(0, np.nan)
    rel = rel.fillna(0.0)
    work["is_valid"] = (work["amount_diff"] <= AMOUNT_ABS_TOLERANCE) | (rel <= AMOUNT_REL_TOLERANCE)
    return work


def _rewind_upload(uploaded_file):
    seek_fn = getattr(uploaded_file, "seek", None)
    if callable(seek_fn):
        try:
            seek_fn(0)
        except Exception:
            pass


def load_client_api_key():
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    return key
        except Exception:
            pass
    return os.environ.get("GOOGLE_API_KEY") or st.session_state.get("api_key") or ""


def finalize_boq_dataframe(df, project_id):
    expected_cols = ["item_no", "description", "unit", "contract_qty", "contract_rate", "contract_amount"]
    work = df.copy()
    for col in expected_cols:
        if col not in work.columns:
            work[col] = None

    work["item_no"] = work["item_no"].apply(lambda v: "" if pd.isna(v) else str(v).strip())
    empty_mask = work["item_no"] == ""
    work.loc[empty_mask, "item_no"] = [str(i + 1) for i in range(int(empty_mask.sum()))]

    work["project_id"] = project_id
    work["boq_item_id"] = work.apply(
        lambda row: f"BOQ-{project_id}-{str(row['item_no']).strip()}",
        axis=1
    )
    work = apply_boq_amount_checks(work)
    display_cols = [
        "boq_item_id", "project_id", "item_no", "description", "unit",
        "contract_qty", "contract_rate", "contract_amount", "calculated_amount", "amount_diff", "is_valid"
    ]
    return work[display_cols].copy()


def extract_boq_from_pdf(uploaded_file, project_id):
    api_key = load_client_api_key()
    if not GENAI_AVAILABLE:
        return None, "مكتبة google.generativeai غير مثبتة."
    if not api_key:
        return None, "مفتاح Google AI API غير متوفر. أضفه في api_key.txt."
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.5-flash-lite")
        _rewind_upload(uploaded_file)
        file_bytes = uploaded_file.getvalue()
        _rewind_upload(uploaded_file)
        file_mime = getattr(uploaded_file, "type", None) or "application/pdf"
        prompt = """
أنت مهندس مكتب فني خبير في جداول الكميات (BOQ).
استخرج كل بنود المقايسة من ملف PDF بدقة بصيغة JSON فقط:
{
  "boq_items": [
    {
      "item_no": "رقم البند",
      "description": "توصيف الأعمال كاملاً",
      "unit": "الوحدة",
      "contract_qty": 0.0,
      "contract_rate": 0.0,
      "contract_amount": 0.0
    }
  ]
}
لا تضف أي نص خارج JSON.
"""
        response = model.generate_content([
            {"mime_type": file_mime, "data": file_bytes},
            prompt
        ])
        txt = (response.text or "").strip()
        if txt.startswith("```json"):
            txt = txt[7:-3].strip()
        elif txt.startswith("```"):
            txt = txt[3:-3].strip()
        data = json.loads(txt)
        items = data.get("boq_items") if isinstance(data, dict) else data
        if not items:
            return None, "لم يتم العثور على بنود مقايسة داخل ملف PDF."
        raw_df = pd.DataFrame(items)
        return finalize_boq_dataframe(raw_df, project_id), None
    except Exception as e:
        return None, f"تعذر استخراج بنود المقايسة من PDF: {e}"


def get_gspread_client():
    if not G_CLOUD_AVAILABLE:
        return None, "مكتبات gspread/google.oauth2 غير مثبتة."
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        return None, f"ملف الاعتماد غير موجود: {SERVICE_ACCOUNT_FILE}"
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        return gspread.authorize(creds), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def open_client_invoices_spreadsheet(gs_client):
    try:
        return gs_client.open(CLIENT_SPREADSHEET_NAME), None
    except Exception:
        try:
            return gs_client.open_by_key(CLIENT_SPREADSHEET_ID), None
        except Exception as e:
            return None, f"تعذر فتح الشيت {CLIENT_SPREADSHEET_NAME}: {e}"


def setup_named_worksheet(sh, title, headers):
    """يفتح ورقة بالعنوان المحدد فقط، أو ينشئها، دون الرجوع إلى sheet1."""
    try:
        try:
            ws = sh.worksheet(title)
        except Exception:
            ws = sh.add_worksheet(
                title=title,
                rows="4000",
                cols=str(max(len(headers) + 2, 16))
            )
        if not ws or getattr(ws, "title", "") != title:
            return None, f"تعذر فتح صفحة {title} دون الرجوع إلى ورقة أخرى."
        vals = ws.get_all_values()
        if not vals:
            ws.insert_row(headers, 1)
        elif vals[0] != headers:
            ws.update("A1", [headers])
        return ws, None
    except Exception as e:
        return None, str(e)


def setup_client_boq_worksheet(sh):
    return setup_named_worksheet(sh, CLIENT_BOQ_WORKSHEET, CLIENT_BOQ_HEADERS)


def _cell_for_sheet(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return value


def _record_to_sheet_row(record, columns):
    return [_cell_for_sheet(record.get(col, "")) for col in columns]


def _merge_sheet_rows(existing_vals, columns, local_records, project_id=None, drop_ipc_ids=None):
    """يبقي صفوف المشاريع الأخرى ويستبدل صفوف المشروع/المستخلصات المحلية حسب ipc_id."""
    kept = [columns]
    pid = None if project_id is None or project_id == "" else str(project_id)
    drop_ids = {str(x) for x in (drop_ipc_ids or [])}
    if existing_vals and len(existing_vals) > 1:
        col_headers = existing_vals[0]
        try:
            pid_idx = col_headers.index("project_id")
        except ValueError:
            pid_idx = 1 if len(col_headers) > 1 else 0
        try:
            ipc_idx = col_headers.index("ipc_id")
        except ValueError:
            ipc_idx = 0
        for row in existing_vals[1:]:
            row_pid = row[pid_idx] if len(row) > pid_idx else ""
            row_ipc = row[ipc_idx] if len(row) > ipc_idx else ""
            if pid is not None and str(row_pid) == pid:
                continue
            if str(row_ipc) in drop_ids:
                continue
            padded = list(row) + [""] * (len(columns) - len(row))
            kept.append(padded[:len(columns)])
    for rec in local_records:
        kept.append(_record_to_sheet_row(rec, columns))
    return kept


def _write_sheet_matrix(ws, matrix):
    """يكتب المصفوفة من A1 دون مسح الورقة مسبقاً، ثم يزيل الصفوف الزائدة فقط."""
    ws.update("A1", matrix, value_input_option="USER_ENTERED")
    extra_start = len(matrix) + 1
    try:
        ws.batch_clear([f"A{extra_start}:ZZ10000"])
    except Exception:
        pass


def sync_client_invoices_to_cloud(project_id=None):
    """يزامن رؤوس وبنود المستخلصات المحلية إلى Google Sheets ويحدث حالة التزامن محلياً."""
    ensure_invoice_stores()
    all_local_headers = load_invoice_headers()

    if project_id:
        target_headers = [h for h in all_local_headers if str(h.get("project_id", "")) == str(project_id)]
        item_rows = load_invoice_items(project_id=project_id)
    else:
        target_headers = list(all_local_headers)
        item_rows = load_invoice_items()

    target_headers = [normalize_invoice_header(h) for h in target_headers if isinstance(h, dict)]
    item_rows = [r for r in item_rows if isinstance(r, dict)]

    if not target_headers and not item_rows:
        return False, "لا توجد مستخلصات محفوظة محلياً للمزامنة. احفظ مستخلصاً أولاً."

    gs_client, auth_err = get_gspread_client()
    if not gs_client:
        return False, f"فشل الاتصال بخدمة جوجل: {auth_err}"

    sh, open_err = open_client_invoices_spreadsheet(gs_client)
    if not sh:
        return False, f"فشل فتح جدول المستخلصات: {open_err}"

    ws_headers, h_err = setup_named_worksheet(sh, CLIENT_IPC_HEADERS_WORKSHEET, CLIENT_IPC_HEADER_SHEET_COLS)
    if not ws_headers:
        return False, f"فشل تجهيز ورقة الرؤوس: {h_err}"

    ws_items, i_err = setup_named_worksheet(sh, CLIENT_IPC_ITEMS_WORKSHEET, CLIENT_IPC_ITEM_SHEET_COLS)
    if not ws_items:
        return False, f"فشل تجهيز ورقة البنود: {i_err}"

    try:
        drop_ids = {str(r.get("ipc_id", "")) for r in target_headers if r.get("ipc_id")}

        header_matrix = _merge_sheet_rows(
            ws_headers.get_all_values(),
            CLIENT_IPC_HEADER_SHEET_COLS,
            target_headers,
            project_id=project_id,
            drop_ipc_ids=drop_ids,
        )
        item_matrix = _merge_sheet_rows(
            ws_items.get_all_values(),
            CLIENT_IPC_ITEM_SHEET_COLS,
            item_rows,
            project_id=project_id,
            drop_ipc_ids=drop_ids,
        )

        if not header_matrix or not isinstance(header_matrix, list):
            return False, "فشل إعداد مصفوفة الرؤوس للمزامنة."
        if not item_matrix or not isinstance(item_matrix, list):
            return False, "فشل إعداد مصفوفة البنود للمزامنة."

        _write_sheet_matrix(ws_headers, header_matrix)
        _write_sheet_matrix(ws_items, item_matrix)

        sync_timestamp = datetime.now(timezone.utc).isoformat()
        synced_ipc_ids = {h.get("ipc_id") for h in target_headers if h.get("ipc_id")}

        for h in all_local_headers:
            if h.get("ipc_id") in synced_ipc_ids:
                h["is_synced"] = True
                h["synced_at"] = sync_timestamp

        if not save_json(CLIENT_INVOICE_HEADERS_FILE, all_local_headers):
            return False, (
                "تمت الكتابة إلى Google Sheets لكن تعذر تحديث حالة التزامن محلياً في "
                "client_invoices_headers_local.json."
            )

        scope = f"المشروع {project_id}" if project_id else "كل المشاريع"
        return True, (
            f"تمت مزامنة {len(target_headers)} مستخلص و {len(item_rows)} بند ({scope}) بنجاح. "
            f"توقيت المزامنة: {sync_timestamp}"
        )
    except Exception as e:
        return False, f"فشل مزامنة المستخلصات: {type(e).__name__}: {str(e)}"


def _open_existing_worksheet(sh, title):
    try:
        ws = sh.worksheet(title)
        if not ws or getattr(ws, "title", "") != title:
            return None, f"تعذر فتح صفحة {title} دون الرجوع إلى ورقة أخرى."
        return ws, None
    except Exception as e:
        return None, f"الورقة {title} غير موجودة: {e}"


def _sheet_values_to_records(vals):
    if not vals or len(vals) < 2:
        return []
    headers = [str(h).strip() for h in vals[0]]
    records = []
    for row in vals[1:]:
        rec = {}
        has_value = False
        for i, col in enumerate(headers):
            if not col:
                continue
            val = row[i] if i < len(row) else ""
            rec[col] = val
            if str(val).strip() != "":
                has_value = True
        if has_value and str(rec.get("ipc_id") or "").strip():
            records.append(rec)
    return records


def _coerce_pulled_header(rec, pull_ts):
    h = normalize_invoice_header(rec)
    h["is_synced"] = True
    recorded = str(rec.get("synced_at") or h.get("synced_at") or "").strip()
    h["synced_at"] = recorded or pull_ts
    try:
        h["ipc_number"] = int(h.get("ipc_number") or rec.get("ipc_number") or 0)
    except (TypeError, ValueError):
        h["ipc_number"] = rec.get("ipc_number") or h.get("ipc_number") or 0
    return h


def _coerce_pulled_item(rec):
    out = dict(rec)
    for key in (
        "contract_qty", "contract_rate", "previous_qty", "current_qty",
        "cumulative_qty", "current_amount", "cumulative_amount",
    ):
        out[key] = _safe_money(out.get(key))
    flag = str(out.get("is_overrun", "")).strip().upper()
    out["is_overrun"] = flag in ("TRUE", "1", "YES", "T", "نعم")
    return out


def pull_client_invoices_from_cloud(project_id=None):
    """يسحب مستخلصات Google Sheets ويدمجها محلياً مع الإبقاء على المسودات غير المزامنة."""
    ensure_invoice_stores()
    gs_client, auth_err = get_gspread_client()
    if not gs_client:
        return False, f"فشل الاتصال بخدمة جوجل: {auth_err}"

    sh, open_err = open_client_invoices_spreadsheet(gs_client)
    if not sh:
        return False, f"فشل فتح جدول المستخلصات: {open_err}"

    ws_headers, h_err = _open_existing_worksheet(sh, CLIENT_IPC_HEADERS_WORKSHEET)
    if not ws_headers:
        return False, h_err
    ws_items, i_err = _open_existing_worksheet(sh, CLIENT_IPC_ITEMS_WORKSHEET)
    if not ws_items:
        return False, i_err

    try:
        cloud_headers_raw = _sheet_values_to_records(ws_headers.get_all_values())
        cloud_items_raw = _sheet_values_to_records(ws_items.get_all_values())
        if project_id:
            pid = str(project_id)
            cloud_headers_raw = [h for h in cloud_headers_raw if str(h.get("project_id", "")) == pid]
            cloud_ids_scope = {str(h.get("ipc_id", "")) for h in cloud_headers_raw if h.get("ipc_id")}
            cloud_items_raw = [
                it for it in cloud_items_raw
                if str(it.get("project_id", "")) == pid or str(it.get("ipc_id", "")) in cloud_ids_scope
            ]

        pull_ts = datetime.now(timezone.utc).isoformat()
        cloud_headers = [_coerce_pulled_header(h, pull_ts) for h in cloud_headers_raw]
        cloud_items = [_coerce_pulled_item(it) for it in cloud_items_raw]
        cloud_by_id = {str(h.get("ipc_id")): h for h in cloud_headers if h.get("ipc_id")}
        cloud_item_ids = {str(it.get("ipc_id")) for it in cloud_items if it.get("ipc_id")}

        local_headers = load_invoice_headers()
        local_items = load_invoice_items()
        if not isinstance(local_headers, list):
            local_headers = []
        if not isinstance(local_items, list):
            local_items = []

        merged_headers = []
        seen_ids = set()
        for loc in local_headers:
            if not isinstance(loc, dict):
                continue
            ipc = str(loc.get("ipc_id", ""))
            if project_id and str(loc.get("project_id", "")) != str(project_id):
                merged_headers.append(loc)
                if ipc:
                    seen_ids.add(ipc)
                continue
            if ipc and ipc in cloud_by_id:
                merged_headers.append(cloud_by_id[ipc])
                seen_ids.add(ipc)
            else:
                merged_headers.append(loc)
                if ipc:
                    seen_ids.add(ipc)
        for ipc, rec in cloud_by_id.items():
            if ipc not in seen_ids:
                merged_headers.append(rec)
                seen_ids.add(ipc)

        merged_items = []
        for loc in local_items:
            if not isinstance(loc, dict):
                continue
            ipc = str(loc.get("ipc_id", ""))
            if project_id and str(loc.get("project_id", "")) != str(project_id) and ipc not in cloud_by_id:
                merged_items.append(loc)
                continue
            if ipc in cloud_by_id or ipc in cloud_item_ids:
                continue
            merged_items.append(loc)
        merged_items.extend(cloud_items)

        if not save_json(CLIENT_INVOICE_HEADERS_FILE, merged_headers):
            return False, "تعذر حفظ الرؤوس المدمجة محلياً."
        if not save_json(CLIENT_INVOICE_ITEMS_FILE, merged_items):
            return False, "تم حفظ الرؤوس وتعذر حفظ البنود المدمجة محلياً."

        scope = f"المشروع {project_id}" if project_id else "كل المشاريع"
        return True, (
            f"تم استيراد وتحديث {len(cloud_headers)} مستخلص و {len(cloud_items)} بند من السحابة ({scope}). "
            f"الإجمالي المحلي: {len(merged_headers)} مستخلص."
        )
    except Exception as e:
        return False, f"فشل الاستيراد من السحابة: {type(e).__name__}: {str(e)}"


def sync_boq_to_cloud(project_id):
    """يزامن بنود المقايسة المحلية إلى ورقة Client_BOQ داخل Client_Invoices_Master."""
    local_rows = load_json(CLIENT_BOQ_FILE)
    if not isinstance(local_rows, list):
        local_rows = []
    project_rows = [r for r in local_rows if str(r.get("project_id", "")) == str(project_id)]
    if not project_rows:
        return False, "لا توجد بنود محفوظة محلياً لهذا المشروع. احفظ الجدول أولاً ثم حاول المزامنة."

    gs_client, auth_err = get_gspread_client()
    if not gs_client:
        return False, auth_err

    sh, open_err = open_client_invoices_spreadsheet(gs_client)
    if not sh:
        return False, open_err

    ws, ws_err = setup_client_boq_worksheet(sh)
    if not ws:
        return False, ws_err

    try:
        existing_vals = ws.get_all_values()
        kept_rows = [CLIENT_BOQ_HEADERS]
        if existing_vals and len(existing_vals) > 1:
            headers = existing_vals[0]
            try:
                pid_idx = headers.index("project_id")
            except ValueError:
                pid_idx = 1 if len(headers) > 1 else 0
            for row in existing_vals[1:]:
                row_pid = row[pid_idx] if len(row) > pid_idx else ""
                if str(row_pid) != str(project_id):
                    padded = list(row) + [""] * (len(CLIENT_BOQ_HEADERS) - len(row))
                    kept_rows.append(padded[:len(CLIENT_BOQ_HEADERS)])

        for rec in project_rows:
            kept_rows.append([
                rec.get("boq_item_id", ""),
                rec.get("project_id", project_id),
                rec.get("item_no", ""),
                rec.get("description", ""),
                rec.get("unit", ""),
                rec.get("contract_qty", 0),
                rec.get("contract_rate", 0),
                rec.get("contract_amount", 0),
            ])

        ws.clear()
        ws.update("A1", kept_rows, value_input_option="USER_ENTERED")
        return True, f"تمت مزامنة {len(project_rows)} بند إلى {CLIENT_SPREADSHEET_NAME} / {CLIENT_BOQ_WORKSHEET}."
    except Exception as e:
        return False, f"فشل المزامنة السحابية: {type(e).__name__}: {e}"


def ensure_invoice_stores():
    for path in (CLIENT_INVOICE_HEADERS_FILE, CLIENT_INVOICE_ITEMS_FILE):
        if not os.path.exists(path):
            save_json(path, [])


def load_invoice_headers(project_id=None):
    ensure_invoice_stores()
    rows = load_json(CLIENT_INVOICE_HEADERS_FILE, default_empty=list)
    if not isinstance(rows, list):
        rows = []
    if project_id is None or project_id == "":
        return rows
    pid = str(project_id)
    return [r for r in rows if isinstance(r, dict) and str(r.get("project_id", "")) == pid]


def load_invoice_items(ipc_id=None, project_id=None):
    ensure_invoice_stores()
    rows = load_json(CLIENT_INVOICE_ITEMS_FILE, default_empty=list)
    if not isinstance(rows, list):
        rows = []
    if ipc_id:
        rows = [r for r in rows if isinstance(r, dict) and str(r.get("ipc_id", "")) == str(ipc_id)]
    if project_id is not None and project_id != "":
        rows = [r for r in rows if isinstance(r, dict) and str(r.get("project_id", "")) == str(project_id)]
    return rows


def next_ipc_number(project_id):
    headers = load_invoice_headers(project_id)
    if not headers:
        return 1
    numbers = []
    for rec in headers:
        try:
            numbers.append(int(rec.get("ipc_number", 0) or 0))
        except (TypeError, ValueError):
            numbers.append(0)
    return max(numbers) + 1 if numbers else len(headers) + 1


def _ipc_sort_key(header):
    try:
        num = int(header.get("ipc_number", 0) or 0)
    except (TypeError, ValueError):
        num = 0
    return (num, str(header.get("issue_date") or ""), str(header.get("ipc_id") or ""))


def _safe_money(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _esc(value):
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _esc_num(value, digits=2):
    return html.escape(f"{_safe_money(value):,.{digits}f}", quote=True)


def normalize_invoice_header(header):
    """يوحّد حقول السجل للمستخلصات القديمة والجديدة دون إعادة حساب البنود."""
    h = dict(header or {})
    approval = str(h.get("approval_status") or h.get("status") or "Draft").strip()
    approval_map = {"معتمد": "Approved", "مسودة": "Draft", "مقدم": "Submitted", "مرتجع": "Returned"}
    approval = approval_map.get(approval, approval)
    if approval not in APPROVAL_STATUS_OPTIONS:
        approval = "Draft" if approval not in IPC_APPROVED_STATUSES else "Approved"
    payment = str(h.get("payment_status") or "Not Paid").strip()
    payment_map = {"غير مدفوع": "Not Paid", "مدفوع جزئياً": "Partially Paid", "مدفوع": "Paid"}
    payment = payment_map.get(payment, payment)
    if payment not in PAYMENT_STATUS_OPTIONS:
        payment = "Not Paid"
    period_from = str(h.get("period_from") or "")
    period_to = str(h.get("period_to") or "")
    billing = h.get("billing_period") or (
        f"{period_from} → {period_to}" if period_from or period_to else ""
    ).strip(" →")
    gross = _safe_money(h.get("gross_amount"), _safe_money(h.get("total_current_works")))
    deductions = h.get("deductions")
    if deductions in (None, ""):
        deductions = (
            _safe_money(h.get("retention_amount"))
            + _safe_money(h.get("advance_deduction"))
            + _safe_money(h.get("other_deductions"))
        )
    deductions = round(_safe_money(deductions), 2)
    vat_amount = _safe_money(h.get("vat_amount"))
    net_amount = _safe_money(h.get("net_amount"), _safe_money(h.get("net_payable")))
    submission = h.get("submission_date") or h.get("issue_date") or ""
    h.update({
        "project_name": h.get("project_name") or h.get("project_id") or "",
        "billing_period": billing,
        "submission_date": submission,
        "gross_amount": round(gross, 2),
        "deductions": deductions,
        "vat_amount": round(vat_amount, 2),
        "net_amount": round(net_amount, 2),
        "approval_status": approval,
        "payment_status": payment,
        "client_name": h.get("client_name") or "",
        "contractor_name": h.get("contractor_name") or "",
        "currency": h.get("currency") or _ui_currency(),
        "is_synced": bool(h.get("is_synced")),
        "synced_at": h.get("synced_at") or "",
    })
    return h


def invoice_is_synced(header):
    val = (header or {}).get("is_synced")
    if val is True:
        return True
    if val in (1, "1", "true", "True", "TRUE", "yes"):
        return True
    return False


def format_synced_at(header):
    if not invoice_is_synced(header):
        return "-"
    ts = str((header or {}).get("synced_at") or "").strip()
    if not ts:
        return "-"
    try:
        raw = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


def invoice_sync_status_label(header):
    return "☁️ متزامن" if invoice_is_synced(header) else "💻 محلي فقط"


def snapshot_line_items_dataframe(ipc_id):
    """لقطة البنود المحفوظة فقط — بلا إعادة ربط أو حساب من مقايسة اليوم."""
    rows = load_invoice_items(ipc_id=ipc_id)
    records = []
    for rec in rows:
        if not isinstance(rec, dict):
            continue
        contract_qty = _safe_money(rec.get("contract_qty"))
        cumulative_qty = _safe_money(rec.get("cumulative_qty"))
        records.append({
            "item_no": rec.get("item_no", ""),
            "description": rec.get("description", ""),
            "unit": rec.get("unit", ""),
            "contract_qty": contract_qty,
            "previous_qty": _safe_money(rec.get("previous_qty")),
            "current_qty": _safe_money(rec.get("current_qty")),
            "cumulative_qty": cumulative_qty,
            "remaining_qty": round(contract_qty - cumulative_qty, 4),
            "contract_rate": _safe_money(rec.get("contract_rate")),
            "current_amount": _safe_money(rec.get("current_amount")),
        })
    cols = [
        "item_no", "description", "unit", "contract_qty", "previous_qty",
        "current_qty", "cumulative_qty", "remaining_qty", "contract_rate", "current_amount",
    ]
    if not records:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(records)[cols]


def update_invoice_header_fields(ipc_id, **fields):
    headers = load_invoice_headers()
    found = False
    for i, rec in enumerate(headers):
        if str(rec.get("ipc_id", "")) == str(ipc_id):
            rec.update(fields)
            if "approval_status" in fields:
                rec["status"] = fields["approval_status"]
            headers[i] = rec
            found = True
            break
    if not found:
        return False, "المستخلص غير موجود في السجل."
    if save_json(CLIENT_INVOICE_HEADERS_FILE, headers):
        return True, None
    return False, "تعذر حفظ حالة المستخلص."


def build_ipc_print_html(header, items_df):
    h = normalize_invoice_header(header)
    currency = _esc(h.get("currency") or _ui_currency())
    project = _esc(h.get("project_name") or h.get("project_id") or "—")
    contract_no = _esc(h.get("contract_wo_number") or "—")
    client = _esc(h.get("client_name") or "—")
    contractor = _esc(h.get("contractor_name") or "—")
    ipc_id = _esc(h.get("ipc_id") or "—")
    period = _esc(h.get("billing_period") or "—")
    issue = _esc(h.get("submission_date") or h.get("issue_date") or "—")
    gross = _esc_num(h.get("gross_amount"), 2)
    deductions = _esc_num(h.get("deductions"), 2)
    vat_amount = _esc_num(h.get("vat_amount"), 2)
    net_amount = _esc_num(h.get("net_amount"), 2)
    rows_html = ""
    if items_df is None or items_df.empty:
        rows_html = '<tr><td colspan="9" style="text-align:center;padding:12px;">لا توجد بنود محفوظة لهذه اللقطة</td></tr>'
    else:
        for _, row in items_df.iterrows():
            rows_html += (
                "<tr>"
                f"<td>{_esc(row.get('item_no', ''))}</td>"
                f"<td class='desc'>{_esc(row.get('description', ''))}</td>"
                f"<td>{_esc(row.get('unit', ''))}</td>"
                f"<td class='num'>{_esc_num(row.get('contract_qty'), 4)}</td>"
                f"<td class='num'>{_esc_num(row.get('previous_qty'), 4)}</td>"
                f"<td class='num'>{_esc_num(row.get('current_qty'), 4)}</td>"
                f"<td class='num'>{_esc_num(row.get('cumulative_qty'), 4)}</td>"
                f"<td class='num'>{_esc_num(row.get('contract_rate'), 2)}</td>"
                f"<td class='num'>{_esc_num(row.get('current_amount'), 2)}</td>"
                "</tr>"
            )
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"/>
<title>IPC {ipc_id}</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm; }}
  body {{ font-family: "Segoe UI", Tahoma, Arial, sans-serif; color: #111827; margin: 0; background: #fff; }}
  .sheet {{ padding: 12px 16px; }}
  .top {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #0f766e; padding-bottom: 10px; margin-bottom: 12px; }}
  h1 {{ margin: 0; font-size: 20px; color: #0f766e; }}
  .meta {{ font-size: 12px; line-height: 1.6; }}
  table.items {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  table.items th {{ background: #0f766e; color: #fff; padding: 6px; border: 1px solid #0f766e; }}
  table.items td {{ border: 1px solid #d1d5db; padding: 5px 6px; vertical-align: top; }}
  td.num {{ text-align: left; font-variant-numeric: tabular-nums; direction: ltr; }}
  td.desc {{ text-align: right; }}
  .finance {{ margin-top: 14px; width: 360px; margin-right: auto; border: 1px solid #0f766e; }}
  .finance td {{ padding: 6px 10px; font-size: 12px; border-bottom: 1px solid #e5e7eb; }}
  .finance tr:last-child td {{ background: #ecfdf5; font-weight: 700; border-bottom: none; }}
  .signs {{ display: flex; justify-content: space-between; margin-top: 28px; gap: 16px; }}
  .sign {{ flex: 1; border-top: 1px solid #9ca3af; padding-top: 8px; font-size: 12px; text-align: center; min-height: 70px; }}
  .print-bar {{ margin-bottom: 10px; }}
  .print-bar button {{ background: #0f766e; color: #fff; border: 0; padding: 8px 14px; border-radius: 6px; cursor: pointer; }}
  @media print {{
    .print-bar {{ display: none !important; }}
    body {{ background: #fff; }}
  }}
</style>
</head>
<body>
<div class="sheet">
  <div class="print-bar"><button onclick="window.print()">طباعة المستخلص المعتمد</button></div>
  <div class="top">
    <div>
      <h1>مستخلص أعمال دوري معتمد</h1>
      <div class="meta">المشروع: {project}<br/>رقم العقد / أمر العمل: {contract_no}</div>
    </div>
    <div class="meta">
      رقم المستخلص: <b>{ipc_id}</b><br/>
      الفترة: {period}<br/>
      التاريخ: {issue}<br/>
      العميل: {client}<br/>
      المقاول: {contractor}
    </div>
  </div>
  <table class="items">
    <thead>
      <tr>
        <th>رقم البند</th><th>التوصيف</th><th>الوحدة</th>
        <th>كمية العقد</th><th>سابق</th><th>حالي</th><th>تراكمي</th>
        <th>الفئة</th><th>قيمة الحالي</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  <table class="finance">
    <tr><td>إجمالي الأعمال الحالية</td><td class="num">{gross} {currency}</td></tr>
    <tr><td>إجمالي الخصومات</td><td class="num">{deductions} {currency}</td></tr>
    <tr><td>ضريبة القيمة المضافة</td><td class="num">{vat_amount} {currency}</td></tr>
    <tr><td>صافي المستحق</td><td class="num">{net_amount} {currency}</td></tr>
  </table>
  <div class="signs">
    <div class="sign">إعداد<br/>الاسم: ........................<br/>التاريخ: ........ / ........ / ............</div>
    <div class="sign">مراجعة<br/>الاسم: ........................<br/>التاريخ: ........ / ........ / ............</div>
    <div class="sign">اعتماد<br/>الاسم: ........................<br/>التاريخ: ........ / ........ / ............</div>
  </div>
</div>
</body>
</html>"""


def latest_approved_previous_qty_map(project_id):
    """previous_qty من أحدث مستخلص approval_status == Approved فقط (بدون Draft/Returned)."""
    headers = []
    for h in load_invoice_headers(project_id):
        if not isinstance(h, dict):
            continue
        norm = normalize_invoice_header(h)
        if str(norm.get("approval_status", "")).strip() == "Approved":
            headers.append(h)
    if not headers:
        return {}
    latest = max(headers, key=_ipc_sort_key)
    qty_map = {}
    for item in load_invoice_items(ipc_id=latest.get("ipc_id"), project_id=project_id):
        bid = str(item.get("boq_item_id", ""))
        if not bid:
            continue
        prev = item.get("cumulative_qty", item.get("previous_qty", 0))
        try:
            qty_map[bid] = float(prev or 0)
        except (TypeError, ValueError):
            qty_map[bid] = 0.0
    return qty_map


def load_project_boq_items(project_id):
    rows = load_json(CLIENT_BOQ_FILE, default_empty=list)
    if not isinstance(rows, list):
        rows = []
    pid = str(project_id)
    return [r for r in rows if isinstance(r, dict) and str(r.get("project_id", "")) == pid]


def apply_invoice_item_calcs(df):
    work = df.copy()
    for col in ("contract_qty", "contract_rate", "previous_qty", "current_qty"):
        if col not in work.columns:
            work[col] = 0.0
        work[col] = _to_numeric_series(work[col])
    work["current_qty"] = work["current_qty"].clip(lower=0)
    work["cumulative_qty"] = (work["previous_qty"] + work["current_qty"]).round(4)
    work["current_amount"] = (work["current_qty"] * work["contract_rate"]).round(2)
    work["cumulative_amount"] = (work["cumulative_qty"] * work["contract_rate"]).round(2)
    work["is_overrun"] = work["cumulative_qty"] > work["contract_qty"]
    cols = [c for c in INVOICE_ITEM_DISPLAY_COLS if c in work.columns]
    return work[cols].copy()


def build_invoice_items_dataframe(project_id):
    boq_rows = load_project_boq_items(project_id)
    if not boq_rows:
        return pd.DataFrame(columns=INVOICE_ITEM_DISPLAY_COLS)
    prev_map = latest_approved_previous_qty_map(project_id)
    records = []
    for row in boq_rows:
        bid = str(row.get("boq_item_id", ""))
        rate = float(row.get("contract_rate") or 0)
        cqty = float(row.get("contract_qty") or 0)
        prev = float(prev_map.get(bid, 0.0) or 0.0)
        records.append({
            "boq_item_id": bid,
            "item_no": row.get("item_no", ""),
            "description": row.get("description", ""),
            "unit": row.get("unit", ""),
            "contract_qty": cqty,
            "contract_rate": rate,
            "previous_qty": prev,
            "current_qty": 0.0,
        })
    return apply_invoice_item_calcs(pd.DataFrame(records))


def compute_invoice_financials(items_df, retention_rate, advance_deduction, other_deductions, vat_rate):
    if items_df is None or items_df.empty:
        total_current = 0.0
        total_cumulative = 0.0
    else:
        live = apply_invoice_item_calcs(items_df)
        total_current = float(live["current_amount"].sum())
        total_cumulative = float(live["cumulative_amount"].sum())
    retention_amount = round(total_current * (float(retention_rate or 0) / 100.0), 2)
    net_before_vat = round(
        total_current - retention_amount - float(advance_deduction or 0) - float(other_deductions or 0),
        2
    )
    vat_amount = round(net_before_vat * (float(vat_rate or 0) / 100.0), 2)
    net_payable = round(net_before_vat + vat_amount, 2)
    return {
        "total_current_works": round(total_current, 2),
        "total_cumulative_works": round(total_cumulative, 2),
        "retention_amount": retention_amount,
        "net_before_vat": net_before_vat,
        "vat_amount": vat_amount,
        "net_payable": net_payable,
    }


def save_progress_invoice(header_record, item_records):
    headers = load_invoice_headers()
    items = load_invoice_items()
    ipc_id = header_record.get("ipc_id")
    headers = [h for h in headers if str(h.get("ipc_id", "")) != str(ipc_id)]
    items = [r for r in items if str(r.get("ipc_id", "")) != str(ipc_id)]
    headers.append(header_record)
    items.extend(item_records)
    ok_h = save_json(CLIENT_INVOICE_HEADERS_FILE, headers)
    ok_i = save_json(CLIENT_INVOICE_ITEMS_FILE, items)
    if ok_h and ok_i:
        return True, None
    return False, "تعذر حفظ ملفات المستخلص محلياً."


def _reset_invoice_form_state():
    st.session_state.ipc_items_df = None
    st.session_state.ipc_bound_project_id = None
    st.session_state.ipc_editor_nonce = st.session_state.get("ipc_editor_nonce", 0) + 1
    for key in (
        "ipc_contract_wo",
        "ipc_period_from",
        "ipc_period_to",
        "ipc_issue_date",
        "ipc_currency",
        "ipc_retention_rate",
        "ipc_advance_deduction",
        "ipc_other_deductions",
        "ipc_vat_rate",
        "ipc_num_display",
        "ipc_id_display",
    ):
        if key in st.session_state:
            del st.session_state[key]


def render_boq_subtab(selected_project_id):
    project_docs = load_supporting_documents(selected_project_id)
    all_docs = load_supporting_documents()
    with st.expander("أرشيف الوثائق الداعمة", expanded=False):
        st.caption("وثائق المشروع المرتبطة بجداول الكميات والمستخلصات.")
        c1, c2, c3 = st.columns(3)
        c1.metric("وثائق هذا المشروع", len(project_docs))
        c2.metric("إجمالي الأرشيف", len(all_docs))
        c3.metric("حقول السجل المعتمدة", len(SUPPORTING_DOCUMENT_FIELDS))
        st.info("يمكن إرفاق طلبات الفحص والقياس المعتمد والوثائق الداعمة الأخرى.")

    if "boq_df" not in st.session_state:
        st.session_state.boq_df = None
    if "last_uploaded" not in st.session_state:
        st.session_state.last_uploaded = None
    if "boq_bound_project_id" not in st.session_state:
        st.session_state.boq_bound_project_id = None
    if "boq_editor_nonce" not in st.session_state:
        st.session_state.boq_editor_nonce = 0

    if st.session_state.boq_bound_project_id not in (None, selected_project_id):
        st.session_state.boq_df = None
        st.session_state.last_uploaded = None
        st.session_state.boq_editor_nonce += 1

    uploaded_file = st.file_uploader(
        "رفع ملف جدول الكميات (Excel / CSV / PDF)",
        type=["xlsx", "xls", "csv", "pdf"],
        key="boq_uploader"
    )
    st.caption("ملف PDF يُقرأ تلقائياً لاستخراج البنود (رقم البند، التوصيف، الوحدة، الكمية، السعر، القيمة). راجع الجدول ثم احفظ.")

    if uploaded_file is not None:
        try:
            _rewind_upload(uploaded_file)
            file_name = (uploaded_file.name or "").lower()

            if st.session_state.last_uploaded != uploaded_file.name:
                if file_name.endswith(".pdf"):
                    with st.spinner("جاري قراءة ملف PDF واستخراج بنود المقايسة..."):
                        df, pdf_err = extract_boq_from_pdf(uploaded_file, selected_project_id)
                    if pdf_err:
                        st.session_state.last_uploaded = uploaded_file.name
                        st.session_state.boq_df = None
                        st.error(pdf_err)
                        return
                else:
                    if file_name.endswith(".csv"):
                        df = pd.read_csv(uploaded_file)
                    else:
                        df = pd.read_excel(uploaded_file)
                    df = finalize_boq_dataframe(df, selected_project_id)

                st.session_state.boq_df = df.copy()
                st.session_state.last_uploaded = uploaded_file.name
                st.session_state.boq_bound_project_id = selected_project_id
                if file_name.endswith(".pdf"):
                    st.success(f"تم استخراج {len(df)} بند من ملف PDF. راجع الجدول ثم احفظ.")

        except Exception as e:
            st.error(f"حدث خطأ أثناء معالجة الملف: {str(e)}")
            return

    if st.session_state.boq_df is not None:
        st.markdown("#### مراجعة وتعديل بيانات جدول الكميات")
        st.caption(
            "فروقات حتى 0.50 أو 0.1٪ تُقبل تلقائياً. عمود amount_diff يوضح الفرق. "
            "يمكنك تسوية القيمة على الكمية × السعر، أو اعتماد الفروقات يدوياً."
        )

        st.markdown('<div class="client-rtl">', unsafe_allow_html=True)
        edited_df = st.data_editor(
            st.session_state.boq_df,
            use_container_width=True,
            disabled=["boq_item_id", "project_id", "calculated_amount", "amount_diff", "is_valid"],
            key=f"boq_data_editor_{st.session_state.boq_editor_nonce}"
        )
        st.markdown("</div>", unsafe_allow_html=True)

        manual_override = st.checkbox(
            "اعتماد يدوي: حفظ القيم كما هي حتى مع وجود فروقات أكبر من السماحية",
            key="boq_manual_override"
        )

        col_fix, col_save, col_sync = st.columns(3)
        with col_fix:
            fix_clicked = st.button("تسوية القيمة = الكمية × السعر", use_container_width=True)
        with col_save:
            save_clicked = st.button("💾 اعتماد وحفظ جدول الكميات", type="primary", use_container_width=True)
        with col_sync:
            sync_clicked = st.button("☁️ مزامنة مع السحابة", use_container_width=True)

        if fix_clicked:
            fixed = apply_boq_amount_checks(edited_df)
            fixed["contract_amount"] = fixed["calculated_amount"]
            st.session_state.boq_df = apply_boq_amount_checks(fixed)
            st.session_state.boq_editor_nonce += 1
            st.rerun()

        if save_clicked:
            checked = apply_boq_amount_checks(edited_df)
            invalid_count = int((~checked["is_valid"]).sum())

            if invalid_count > 0 and not manual_override:
                st.error(
                    f"لا يمكن الحفظ. يوجد {invalid_count} بند بفرق أكبر من 0.50 "
                    "بين القيمة والقيمة المحسوبة. صحّح الجدول، أو استخدم تسوية القيمة، أو فعّل الاعتماد اليدوي."
                )
            else:
                save_df = checked.drop(columns=["calculated_amount", "amount_diff", "is_valid"], errors="ignore")
                existing_data = load_json(CLIENT_BOQ_FILE)
                existing_df = pd.DataFrame(existing_data) if existing_data else pd.DataFrame(columns=save_df.columns)

                if not existing_df.empty and "project_id" in existing_df.columns:
                    existing_df = existing_df[existing_df["project_id"] != selected_project_id]
                    final_df = pd.concat([existing_df, save_df], ignore_index=True)
                else:
                    final_df = save_df

                records = json.loads(final_df.to_json(orient="records", force_ascii=False))
                if save_json(CLIENT_BOQ_FILE, records):
                    ensure_supporting_docs_store()
                    if invalid_count > 0 and manual_override:
                        st.success(
                            f"تم الحفظ باعتماد يدوي لـ {invalid_count} بند. البيانات جاهزة لإنشاء المستخلصات."
                        )
                    else:
                        st.success("تم حفظ جدول الكميات بنجاح. أصبحت البيانات جاهزة لإنشاء المستخلصات.")
                    st.session_state.boq_df = None
                    st.session_state.last_uploaded = None
                    st.session_state.boq_bound_project_id = None
                    st.session_state.boq_manual_override = False
                    st.rerun()

        if sync_clicked:
            ok, msg = sync_boq_to_cloud(selected_project_id)
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")
    else:
        st.caption("يمكنك مزامنة آخر مقايسة محفوظة محلياً لهذا المشروع دون إعادة رفع الملف.")
        if st.button("☁️ مزامنة مع السحابة", key="btn_sync_boq_saved_only"):
            ok, msg = sync_boq_to_cloud(selected_project_id)
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")


def render_new_progress_invoice_subtab(selected_project_id, selected_project_name):
    ensure_invoice_stores()
    if "ipc_items_df" not in st.session_state:
        st.session_state.ipc_items_df = None
    if "ipc_bound_project_id" not in st.session_state:
        st.session_state.ipc_bound_project_id = None
    if "ipc_editor_nonce" not in st.session_state:
        st.session_state.ipc_editor_nonce = 0
    if "ipc_save_flash" not in st.session_state:
        st.session_state.ipc_save_flash = None

    if st.session_state.ipc_bound_project_id not in (None, selected_project_id):
        st.session_state.ipc_items_df = None
        st.session_state.ipc_bound_project_id = None
        st.session_state.ipc_editor_nonce += 1

    if st.session_state.ipc_save_flash:
        st.success(st.session_state.ipc_save_flash)
        st.session_state.ipc_save_flash = None

    ipc_no = next_ipc_number(selected_project_id)
    ipc_id_preview = f"CL-IPC-{selected_project_id}-{ipc_no:03d}"

    st.markdown("#### بيانات رأس المستخلص")

    h1, h2, h3 = st.columns(3)
    with h1:
        st.text_input("رقم المستخلص (تلقائي)", value=str(ipc_no), disabled=True, key="ipc_num_display")
    with h2:
        st.text_input("معرف المستخلص", value=ipc_id_preview, disabled=True, key="ipc_id_display")
    with h3:
        contract_wo = st.text_input("رقم العقد / أمر العمل", value="", key="ipc_contract_wo")

    d1, d2, d3, d4 = st.columns(4)
    with d1:
        period_from = st.date_input("فترة العمل من", key="ipc_period_from")
    with d2:
        period_to = st.date_input("فترة العمل إلى", key="ipc_period_to")
    with d3:
        issue_date = st.date_input("تاريخ الإصدار", key="ipc_issue_date")
    with d4:
        currency = _ui_currency()
        st.text_input("العملة", value=currency, disabled=True, key="ipc_currency_display")

    r1, r2, r3, r4 = st.columns(4)
    with r1:
        retention_rate = st.number_input("نسبة الاحتجاز %", min_value=0.0, max_value=100.0, value=5.0, step=0.1, key="ipc_retention_rate")
    with r2:
        advance_deduction = st.number_input("خصم الدفعة المقدمة", min_value=0.0, value=0.0, step=100.0, key="ipc_advance_deduction")
    with r3:
        other_deductions = st.number_input("خصومات / غرامات أخرى", min_value=0.0, value=0.0, step=100.0, key="ipc_other_deductions")
    with r4:
        vat_rate = st.number_input("ضريبة القيمة المضافة %", min_value=0.0, max_value=100.0, value=15.0, step=0.1, key="ipc_vat_rate")

    boq_rows = load_project_boq_items(selected_project_id)
    if not boq_rows:
        st.warning("لا توجد مقايسة معتمدة لهذا المشروع. ارفع جدول الكميات واحفظه من تبويب جدول الكميات التعاقدي أولاً.")
        return

    if st.session_state.ipc_items_df is None or st.session_state.ipc_bound_project_id != selected_project_id:
        st.session_state.ipc_items_df = build_invoice_items_dataframe(selected_project_id)
        st.session_state.ipc_bound_project_id = selected_project_id

    st.markdown("#### بنود التقييم")
    st.caption("الكمية الحالية فقط قابلة للتعديل. الكمية السابقة تُجلب من آخر مستخلص معتمد، وتكون صفراً للمستخلص الأول.")

    st.markdown('<div class="client-rtl">', unsafe_allow_html=True)
    edited_items = st.data_editor(
        st.session_state.ipc_items_df,
        use_container_width=True,
        disabled=[c for c in INVOICE_ITEM_DISPLAY_COLS if c != "current_qty"],
        key=f"ipc_items_editor_{st.session_state.ipc_editor_nonce}",
        column_config={
            "current_qty": st.column_config.NumberColumn("current_qty", min_value=0.0, step=0.01, format="%.4f"),
            "is_overrun": st.column_config.CheckboxColumn("is_overrun", disabled=True),
        }
    )
    st.markdown("</div>", unsafe_allow_html=True)
    live_items = apply_invoice_item_calcs(edited_items)
    prev_qty = _to_numeric_series(st.session_state.ipc_items_df["current_qty"])
    new_qty = _to_numeric_series(live_items["current_qty"])
    if not prev_qty.reset_index(drop=True).equals(new_qty.reset_index(drop=True)):
        st.session_state.ipc_items_df = live_items
        st.session_state.ipc_editor_nonce += 1
        st.rerun()

    overrun_count = int(live_items["is_overrun"].sum()) if not live_items.empty else 0
    if overrun_count:
        st.warning(f"يوجد {overrun_count} بند تتجاوز فيه الكمية التراكمية الكمية التعاقدية.")

    money = compute_invoice_financials(
        live_items, retention_rate, advance_deduction, other_deductions, vat_rate
    )

    st.markdown("#### ملخص مالي وخصومات")
    m1, m2, m3 = st.columns(3)
    m1.metric("إجمالي الأعمال الحالية", f"{money['total_current_works']:,.2f} {currency}")
    m2.metric("إجمالي الأعمال التراكمية", f"{money['total_cumulative_works']:,.2f} {currency}")
    m3.metric("قيمة الاحتجاز", f"{money['retention_amount']:,.2f} {currency}")
    m4, m5, m6 = st.columns(3)
    m4.metric("الصافي قبل الضريبة", f"{money['net_before_vat']:,.2f} {currency}")
    m5.metric("قيمة الضريبة", f"{money['vat_amount']:,.2f} {currency}")
    m6.metric("صافي المستحق", f"{money['net_payable']:,.2f} {currency}")

    if st.button("💾 اعتماد وحفظ المستخلص الدوري", type="primary", use_container_width=True, key="btn_save_progress_ipc"):
        if period_from and period_to and period_from > period_to:
            st.error("تاريخ نهاية فترة العمل يجب ألا يسبق تاريخ البداية.")
            return
        if float(live_items["current_qty"].sum()) <= 0:
            st.error("أدخل كمية حالية لبند واحد على الأقل قبل الحفظ.")
            return

        ipc_id = f"CL-IPC-{selected_project_id}-{ipc_no:03d}"
        header = {
            "ipc_id": ipc_id,
            "project_id": selected_project_id,
            "project_name": selected_project_name,
            "ipc_number": ipc_no,
            "contract_wo_number": (contract_wo or "").strip(),
            "period_from": period_from.isoformat() if period_from else "",
            "period_to": period_to.isoformat() if period_to else "",
            "issue_date": issue_date.isoformat() if issue_date else "",
            "currency": currency,
            "retention_rate": float(retention_rate),
            "advance_deduction": float(advance_deduction),
            "other_deductions": float(other_deductions),
            "vat_rate": float(vat_rate),
            "total_current_works": money["total_current_works"],
            "total_cumulative_works": money["total_cumulative_works"],
            "retention_amount": money["retention_amount"],
            "net_before_vat": money["net_before_vat"],
            "vat_amount": money["vat_amount"],
            "net_payable": money["net_payable"],
            "gross_amount": money["total_current_works"],
            "deductions": round(
                float(money["retention_amount"]) + float(advance_deduction) + float(other_deductions), 2
            ),
            "net_amount": money["net_payable"],
            "billing_period": f"{period_from.isoformat() if period_from else ''} → {period_to.isoformat() if period_to else ''}".strip(" →"),
            "submission_date": issue_date.isoformat() if issue_date else "",
            "approval_status": "Approved",
            "payment_status": "Not Paid",
            "status": "Approved",
            "client_name": "",
            "contractor_name": "",
            "is_synced": False,
            "synced_at": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": _current_uploader_name(),
        }
        item_records = []
        for rec in json.loads(live_items.to_json(orient="records", force_ascii=False)):
            item_records.append({
                "ipc_id": ipc_id,
                "project_id": selected_project_id,
                "boq_item_id": rec.get("boq_item_id", ""),
                "item_no": rec.get("item_no", ""),
                "description": rec.get("description", ""),
                "unit": rec.get("unit", ""),
                "contract_qty": rec.get("contract_qty", 0),
                "contract_rate": rec.get("contract_rate", 0),
                "previous_qty": rec.get("previous_qty", 0),
                "current_qty": rec.get("current_qty", 0),
                "cumulative_qty": rec.get("cumulative_qty", 0),
                "current_amount": rec.get("current_amount", 0),
                "cumulative_amount": rec.get("cumulative_amount", 0),
                "is_overrun": bool(rec.get("is_overrun", False)),
            })
        ok, err = save_progress_invoice(header, item_records)
        if not ok:
            st.error(err)
            return
        st.session_state.ipc_save_flash = (
            f"تم اعتماد وحفظ المستخلص {ipc_id} — صافي المستحق {money['net_payable']:,.2f} {currency}."
        )
        _reset_invoice_form_state()
        st.rerun()


def render_invoice_register_subtab(selected_project_id, selected_project_name):
    ensure_invoice_stores()
    if "ipc_register_flash" not in st.session_state:
        st.session_state.ipc_register_flash = None
    if st.session_state.ipc_register_flash:
        st.success(st.session_state.ipc_register_flash)
        st.session_state.ipc_register_flash = None

    raw_headers = load_invoice_headers()
    normalized = [normalize_invoice_header(h) for h in raw_headers if isinstance(h, dict)]

    st.markdown("#### سجل المستخلصات")
    col_push, col_pull = st.columns(2)
    with col_push:
        if st.button("☁️ مزامنة المستخلصات مع السحابة", use_container_width=True, key="btn_sync_ipcs_cloud"):
            with st.spinner("جاري مزامنة رؤوس وبنود المستخلصات مع Google Sheets..."):
                ok, msg = sync_client_invoices_to_cloud(selected_project_id)
            if ok:
                st.session_state.ipc_register_flash = msg
                st.rerun()
            else:
                st.error(msg)
    with col_pull:
        if st.button("📥 استيراد وتحديث من السحابة", use_container_width=True, key="btn_pull_ipcs_cloud"):
            with st.spinner("جاري سحب المستخلصات من Google Sheets ودمجها محلياً..."):
                ok, msg = pull_client_invoices_from_cloud(selected_project_id)
            if ok:
                st.session_state.ipc_register_flash = msg
                st.rerun()
            else:
                st.error(msg)

    f1, f2, f3, f4 = st.columns([2, 1.4, 1.4, 1.2])
    with f1:
        search_ipc = st.text_input("بحث برقم المستخلص", value="", key="reg_search_ipc")
    with f2:
        approval_filter = st.selectbox(
            "حالة الاعتماد",
            ["الكل"] + list(APPROVAL_STATUS_OPTIONS),
            key="reg_filter_approval"
        )
    with f3:
        payment_filter = st.selectbox(
            "حالة السداد",
            ["الكل"] + list(PAYMENT_STATUS_OPTIONS),
            key="reg_filter_payment"
        )
    with f4:
        only_current = st.checkbox("المشروع النشط فقط", value=True, key="reg_filter_project")

    filtered = []
    needle = (search_ipc or "").strip().lower()
    for rec in normalized:
        if only_current and str(rec.get("project_id", "")) != str(selected_project_id):
            continue
        if needle:
            blob = f"{rec.get('ipc_id', '')} {rec.get('ipc_number', '')}".lower()
            if needle not in blob:
                continue
        if approval_filter != "الكل" and rec.get("approval_status") != approval_filter:
            continue
        if payment_filter != "الكل" and rec.get("payment_status") != payment_filter:
            continue
        filtered.append(rec)

    if not filtered:
        st.info("لا توجد مستخلصات مطابقة لعوامل التصفية.")
        return

    table_rows = []
    for rec in sorted(filtered, key=_ipc_sort_key, reverse=True):
        table_rows.append({
            "ipc_id": rec.get("ipc_id", ""),
            "project_name": rec.get("project_name", ""),
            "billing_period": rec.get("billing_period", ""),
            "submission_date": rec.get("submission_date", ""),
            "gross_amount": rec.get("gross_amount", 0),
            "deductions": rec.get("deductions", 0),
            "vat_amount": rec.get("vat_amount", 0),
            "net_amount": rec.get("net_amount", 0),
            "approval_status": rec.get("approval_status", ""),
            "payment_status": rec.get("payment_status", ""),
            "حالة المزامنة": invoice_sync_status_label(rec),
            "تاريخ المزامنة": format_synced_at(rec),
        })
    st.markdown('<div class="client-rtl">', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    options = [r["ipc_id"] for r in table_rows]
    selected_ipc = st.selectbox("فتح مستخلص للعرض التفصيلي", options, key="reg_open_ipc")
    header = next((r for r in filtered if r.get("ipc_id") == selected_ipc), None)
    if not header:
        return

    items_df = snapshot_line_items_dataframe(selected_ipc)
    currency = header.get("currency") or _ui_currency()

    st.markdown("#### تفاصيل المستخلص (لقطة تاريخية محفوظة)")
    st.caption("البنود معروضة كما حُفظت وقت الاعتماد. لا يُعاد ربطها بمقايسة المشروع الحالية.")

    st.markdown("**أ) بيانات المستخلص**")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("رقم المستخلص", header.get("ipc_id", "—"))
    a2.metric("المشروع", str(header.get("project_name") or selected_project_name))
    a3.metric("فترة العمل", header.get("billing_period") or "—")
    a4.metric("تاريخ التقديم", str(header.get("submission_date") or "—"))
    s1, s2, s3, s4 = st.columns(4)
    s1.write(f"العقد / أمر العمل: `{header.get('contract_wo_number') or '—'}`")
    s2.write(f"حالة الاعتماد: **{header.get('approval_status')}**")
    s3.write(f"حالة السداد: **{header.get('payment_status')}**")
    if invoice_is_synced(header):
        s4.metric("حالة المزامنة السحابية", "متزامن", format_synced_at(header))
    else:
        s4.metric("حالة المزامنة السحابية", "غير متزامن")

    st.markdown("**ب) مؤشرات الكميات والقيمة**")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("إجمالي الأعمال", f"{header.get('gross_amount', 0):,.2f} {currency}")
    b2.metric("إجمالي الخصومات", f"{header.get('deductions', 0):,.2f} {currency}")
    b3.metric("الضريبة", f"{header.get('vat_amount', 0):,.2f} {currency}")
    b4.metric("صافي المستحق", f"{header.get('net_amount', 0):,.2f} {currency}")

    st.markdown("**ج) تفصيل البنود**")
    st.markdown('<div class="client-rtl">', unsafe_allow_html=True)
    st.dataframe(items_df, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("**تحديث الحالة**")
    u1, u2, u3 = st.columns([1.4, 1.4, 1])
    with u1:
        new_approval = st.selectbox(
            "حالة الاعتماد",
            list(APPROVAL_STATUS_OPTIONS),
            index=list(APPROVAL_STATUS_OPTIONS).index(header.get("approval_status"))
            if header.get("approval_status") in APPROVAL_STATUS_OPTIONS else 2,
            key=f"reg_edit_approval_{selected_ipc}"
        )
    with u2:
        new_payment = st.selectbox(
            "حالة السداد",
            list(PAYMENT_STATUS_OPTIONS),
            index=list(PAYMENT_STATUS_OPTIONS).index(header.get("payment_status"))
            if header.get("payment_status") in PAYMENT_STATUS_OPTIONS else 0,
            key=f"reg_edit_payment_{selected_ipc}"
        )
    with u3:
        st.write("")
        st.write("")
        if st.button("حفظ الحالة", type="primary", use_container_width=True, key=f"reg_save_status_{selected_ipc}"):
            ok, err = update_invoice_header_fields(
                selected_ipc,
                approval_status=new_approval,
                payment_status=new_payment,
            )
            if ok:
                st.session_state.ipc_register_flash = f"تم تحديث حالة {selected_ipc}."
                st.rerun()
            else:
                st.error(err)

    if st.button("🖨️ عرض نسخة الطباعة المعتمدة", use_container_width=True, key=f"reg_print_{selected_ipc}"):
        st.session_state.ipc_print_id = selected_ipc

    if st.session_state.get("ipc_print_id") == selected_ipc:
        st.markdown("##### نسخة الطباعة المعتمدة")
        print_html = build_ipc_print_html(header, items_df)
        st.components.v1.html(print_html, height=920, scrolling=True)


def render_client_invoices_tab():
    st.markdown("""
    <style>
    .section-banner {
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
    }
    div[data-testid="stMarkdownContainer"]:has(.section-banner) {
        width: fit-content !important;
        max-width: 100% !important;
    }
    .client-rtl, .client-rtl * {
        direction: rtl !important;
        unicode-bidi: isolate;
    }
    [data-testid="stDataFrame"], [data-testid="stDataEditor"],
    [data-testid="stTextInput"], [data-testid="stNumberInput"],
    [data-testid="stDateInput"], [data-testid="stSelectbox"] {
        direction: rtl;
    }
    [data-testid="InputInstructions"], kbd {
        display: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    projects_data = load_json(PROJECTS_FILE)
    if not projects_data:
        st.warning("لم يتم العثور على مشاريع مسجلة. يرجى إضافة مشروع أولاً.")
        return

    project_options = _build_project_options(projects_data)
    if not project_options:
        st.warning("لم يتم العثور على مشاريع مسجلة. يرجى إضافة مشروع أولاً.")
        return

    option_names = list(project_options.keys())
    selected_project_name = st.selectbox("اختر المشروع:", option_names, key="boq_proj_select")
    selected_project_id = project_options[selected_project_name]
    ensure_supporting_docs_store()
    ensure_invoice_stores()

    st.markdown(
        f'<div class="section-banner">📑 مستخلصات العميل — {html.escape(str(selected_project_name or ""))}</div>',
        unsafe_allow_html=True,
    )

    tab_boq, tab_new_ipc, tab_register = st.tabs([
        "📋 جدول الكميات التعاقدي",
        "➕ إعداد مستخلص جاري جديد",
        "📑 سجل ومتابعة المستخلصات",
    ])
    with tab_boq:
        render_boq_subtab(selected_project_id)
    with tab_new_ipc:
        render_new_progress_invoice_subtab(selected_project_id, selected_project_name)
    with tab_register:
        render_invoice_register_subtab(selected_project_id, selected_project_name)

