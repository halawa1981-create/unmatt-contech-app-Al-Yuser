"""محرك تجميع البيانات والرقابة المالية التنفيذية الموسع."""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_INVOICES_FILE = os.path.join(BASE_DIR, "invoices_local.json")
SUBCONTRACTS_FILE = os.path.join(BASE_DIR, "subcontracts_local.json")
IPC_LOCAL_FILE = os.path.join(BASE_DIR, "ipc_local.json")
CLIENT_INVOICES_HEADERS_FILE = os.path.join(BASE_DIR, "client_invoices_headers_local.json")
CLIENT_INVOICES_FILE = os.path.join(BASE_DIR, "client_invoices_local.json")

SUB_CERTIFIED = {"approved", "معتمد", "paid", "مدفوع"}
SUB_PAID = {"paid", "مدفوع"}
CLIENT_EXECUTED = {"approved", "معتمد", "paid", "مدفوع"}
CLIENT_PAID = {"paid", "مدفوع"}
CLIENT_PARTIAL = {"partially paid", "مدفوع جزئياً"}
CLIENT_PENDING = {
    "draft", "مسودة", "submitted", "مقدم", "under review", "قيد المراجعة",
    "تحت المراجعة", "قيد التدقيق", "قيد الاعتماد", "pending", "returned", "مرتجع",
}


def _safe_load_json(file_path):
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            return [data]
        return []
    except Exception:
        return []


def _to_float(val, default=0.0):
    """تحويل آمن للأرقام وتجريد الفواصل العشرية والنصوص الفارغة."""
    try:
        if val is None or val == "":
            return float(default)
        cleaned = str(val).replace(",", "").strip()
        return float(cleaned)
    except Exception:
        return float(default)


def is_material_or_supplier_category(category_name: str) -> bool:
    """التحقق الدقيق من تصنيف الموردين والمواد لتفادي أخطاء الإدخال اليدوي."""
    cat = str(category_name or "").strip().lower()
    keywords = ["مورد", "موردين", "مواد", "خامات", "تشطيبات", "حديد", "خرسانة", "supplier", "material"]
    return any(k in cat for k in keywords)


def _txt(val):
    if val is None:
        return ""
    return str(val).strip()


def _norm(val):
    return _txt(val).lower()


def _matches_project(rec, project_name):
    target = _txt(project_name)
    if not target:
        return False
    for key in ("project_name", "project", "project_id"):
        if _txt(rec.get(key)) == target:
            return True
    return False


def _is_deleted(rec):
    flag = rec.get("delete", False)
    if isinstance(flag, bool):
        return flag
    return _txt(flag).lower() in ("true", "1", "yes", "نعم")


def _contract_value(rec):
    terms = rec.get("commercial_terms") if isinstance(rec.get("commercial_terms"), dict) else {}
    for key in ("total_including_vat", "total_amount", "contract_amount", "contract_value"):
        if key in terms and terms.get(key) not in (None, ""):
            return _to_float(terms.get(key))
        if key in rec and rec.get(key) not in (None, ""):
            return _to_float(rec.get(key))
    return 0.0


def get_project_executive_summary(project_name: str) -> dict:
    """
    محرك تجميع البيانات والرقابة المالية التنفيذية الموسع للمشروع:
    - التدفقات المباشرة (Cash In / Out)
    - الدفعة المقدمة واستهلاكها
    - المحتجزات (لدى المالك / لصالح الباطن)
    - المستخلصات تحت المراجعة والاعتماد
    - التزامات وفواتير الموردين المحسنة
    """
    empty = {
        "project_name": _txt(project_name),
        "total_cash_in": 0.0,
        "total_cash_out": 0.0,
        "net_cash_flow": 0.0,
        "financial_health_status": "Neutral",
        "subcontractors_paid": 0.0,
        "custody_expenses": 0.0,
        "material_suppliers_paid": 0.0,
        "general_site_expenses": 0.0,
        "subcontracts_total_value": 0.0,
        "subcontractors_approved_work": 0.0,
        "subcontractors_balance_due": 0.0,
        "subcontractors_retention": 0.0,
        "client_total_executed": 0.0,
        "client_uncollected_balance": 0.0,
        "client_retention_receivable": 0.0,
        "client_pending_approval": 0.0,
        "advance_payment_received": 0.0,
        "advance_payment_recovered": 0.0,
        "advance_payment_balance": 0.0,
        "short_term_forecast_inflow": 0.0,
        "short_term_forecast_outflow": 0.0,
        "short_term_forecast_net": 0.0,
        "branches": {
            "custody": {"custody_in": 0.0, "custody_out": 0.0},
            "subcontractors": {"subcontractor_cash_out": 0.0},
            "client": {"client_cash_in": 0.0},
        },
    }
    try:
        target_proj = _txt(project_name)

        invoices_data = _safe_load_json(LOCAL_INVOICES_FILE)
        active_invoices = [
            inv for inv in invoices_data
            if _matches_project(inv, target_proj) and not _is_deleted(inv)
        ]

        total_custody_funding = 0.0
        custody_expenses = 0.0
        material_suppliers_paid = 0.0
        for inv in active_invoices:
            doc_type = _txt(inv.get("doc_type"))
            category = _txt(inv.get("category"))
            amount = _to_float(inv.get("amount", 0.0))
            if doc_type in ("وارد", "Inbound", "inbound"):
                total_custody_funding += amount
            else:
                custody_expenses += amount
                if is_material_or_supplier_category(category):
                    material_suppliers_paid += amount

        subcontracts = _safe_load_json(SUBCONTRACTS_FILE)
        proj_subcontracts = [s for s in subcontracts if _matches_project(s, target_proj)]
        total_subcontracts_value = sum(_contract_value(s) for s in proj_subcontracts)

        ipcs_data = _safe_load_json(IPC_LOCAL_FILE)
        proj_ipcs = [ipc for ipc in ipcs_data if _matches_project(ipc, target_proj)]

        subcontractors_approved_work = 0.0
        subcontractors_paid = 0.0
        subcontractors_retention = 0.0
        for ipc in proj_ipcs:
            status = _norm(ipc.get("status") or ipc.get("approval_status"))
            work_val = _to_float(
                ipc.get("current_gross_amount", ipc.get("current_work_value", ipc.get("total_amount", 0.0)))
            )
            net_val = _to_float(ipc.get("net_ipc_amount", ipc.get("net_payable", ipc.get("paid_amount", ipc.get("amount", 0.0)))))
            ret_val = _to_float(ipc.get("retention_amount", ipc.get("retention_deduction", 0.0)))
            if status in SUB_CERTIFIED:
                subcontractors_approved_work += work_val if work_val else net_val
                subcontractors_retention += ret_val
            if status in SUB_PAID:
                paid_val = _to_float(ipc.get("paid_amount", net_val))
                subcontractors_paid += paid_val if paid_val else net_val

        subcontractors_balance_due = max(0.0, subcontractors_approved_work - subcontractors_paid)

        client_headers = _safe_load_json(CLIENT_INVOICES_HEADERS_FILE)
        if not client_headers:
            client_headers = _safe_load_json(CLIENT_INVOICES_FILE)
        proj_client_invoices = [ci for ci in client_headers if _matches_project(ci, target_proj)]

        client_total_executed = 0.0
        client_cash_in = 0.0
        client_retention_receivable = 0.0
        client_pending_approval = 0.0
        advance_payment_received = 0.0
        advance_payment_recovered = 0.0

        for ci in proj_client_invoices:
            approval = _norm(ci.get("approval_status") or ci.get("status"))
            payment = _norm(ci.get("payment_status"))
            net_payable = _to_float(ci.get("net_payable", ci.get("net_amount", ci.get("invoice_amount", 0.0))))
            collected = _to_float(ci.get("collected_amount", ci.get("paid_amount", 0.0)))
            ret_amt = _to_float(ci.get("retention_amount", 0.0))
            exec_amt = _to_float(ci.get("work_executed_amount", ci.get("gross_amount", ci.get("total_current_works", net_payable))))
            adv_deduct = _to_float(ci.get("advance_deduction", ci.get("advance_payment_deduction", 0.0)))
            desc = _txt(ci.get("description", ""))
            title = _txt(ci.get("invoice_title", ""))
            inv_type = _norm(ci.get("invoice_type"))
            is_adv_inv = (
                "مقدمة" in desc
                or "دفعة مقدمة" in title
                or inv_type in ("advance", "دفعة مقدمة")
            )

            advance_payment_recovered += adv_deduct
            if is_adv_inv:
                advance_payment_received += net_payable

            if approval in CLIENT_EXECUTED or payment in CLIENT_PAID:
                client_total_executed += exec_amt
                client_retention_receivable += ret_amt

            if payment in CLIENT_PAID:
                client_cash_in += collected if collected > 0 else net_payable
            elif payment in CLIENT_PARTIAL:
                client_cash_in += collected
            elif is_adv_inv and collected > 0:
                client_cash_in += collected

            if approval in CLIENT_PENDING:
                client_pending_approval += max(0.0, net_payable - collected)

        advance_payment_balance = max(0.0, advance_payment_received - advance_payment_recovered)
        client_uncollected_balance = max(0.0, client_total_executed - client_cash_in - client_retention_receivable)

        total_cash_in = client_cash_in
        total_cash_out = subcontractors_paid + custody_expenses
        net_cash_flow = total_cash_in - total_cash_out
        if net_cash_flow > 0:
            health_status = "Surplus"
        elif net_cash_flow < 0:
            health_status = "Deficit"
        else:
            health_status = "Neutral"

        general_site_expenses = max(0.0, custody_expenses - material_suppliers_paid)
        short_in = client_pending_approval
        short_out = subcontractors_balance_due

        return {
            "project_name": target_proj,
            "total_cash_in": round(total_cash_in, 2),
            "total_cash_out": round(total_cash_out, 2),
            "net_cash_flow": round(net_cash_flow, 2),
            "financial_health_status": health_status,
            "subcontractors_paid": round(subcontractors_paid, 2),
            "custody_expenses": round(custody_expenses, 2),
            "material_suppliers_paid": round(material_suppliers_paid, 2),
            "general_site_expenses": round(general_site_expenses, 2),
            "subcontracts_total_value": round(total_subcontracts_value, 2),
            "subcontractors_approved_work": round(subcontractors_approved_work, 2),
            "subcontractors_balance_due": round(subcontractors_balance_due, 2),
            "subcontractors_retention": round(subcontractors_retention, 2),
            "client_total_executed": round(client_total_executed, 2),
            "client_uncollected_balance": round(client_uncollected_balance, 2),
            "client_retention_receivable": round(client_retention_receivable, 2),
            "client_pending_approval": round(client_pending_approval, 2),
            "advance_payment_received": round(advance_payment_received, 2),
            "advance_payment_recovered": round(advance_payment_recovered, 2),
            "advance_payment_balance": round(advance_payment_balance, 2),
            "short_term_forecast_inflow": round(short_in, 2),
            "short_term_forecast_outflow": round(short_out, 2),
            "short_term_forecast_net": round(short_in - short_out, 2),
            "custody_funding": round(total_custody_funding, 2),
            "branches": {
                "custody": {
                    "custody_in": round(total_custody_funding, 2),
                    "custody_out": round(custody_expenses, 2),
                },
                "subcontractors": {
                    "subcontractor_cash_out": round(subcontractors_paid, 2),
                },
                "client": {
                    "client_cash_in": round(client_cash_in, 2),
                },
            },
        }
    except Exception:
        return empty


def get_project_executive_summary_safe(project_name: str) -> dict:
    try:
        return get_project_executive_summary(project_name)
    except Exception:
        return get_project_executive_summary("")
