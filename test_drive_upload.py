import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "coral-idiom-265509-184c07e5e6c0.json")
DRIVE_PARENT_FOLDER_ID = "12EROsINe-PstiDGhRqnQTAuW5GXxab9e"

def test_upload():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"❌ خطأ: ملف الاعتماد غير موجود: {SERVICE_ACCOUNT_FILE}")
        return

    try:
        scopes = ["https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        drive_service = build("drive", "v3", credentials=creds)

        # إنشاء بايتات PDF تجريبية في الذاكرة
        dummy_content = b"%PDF-1.4 ... Test PDF Content for Google Drive Upload ..."
        file_stream = io.BytesIO(dummy_content)
        file_stream.seek(0)

        file_metadata = {
            "name": "Test_Contract_Upload.pdf",
            "parents": [DRIVE_PARENT_FOLDER_ID]
        }
        
        media = MediaIoBaseUpload(file_stream, mimetype="application/pdf", resumable=True)
        uploaded = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
            supportsAllDrives=True
        ).execute()

        print("✅ تم الرفع بنجاح إلى Google Drive!")
        print(f"معرف الملف: {uploaded.get('id')}")
        print(f"رابط المعاينة: {uploaded.get('webViewLink')}")

    except Exception as e:
        print(f"❌ فشل الرفع: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    test_upload()