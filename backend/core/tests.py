import tempfile
from datetime import timedelta
from pathlib import Path
import shutil
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from core.models import AuditAction, AuditLog, Document, DocumentStatus, DocumentType, Dossier, Governorate, User, UserRole


class TemporaryMediaRootMixin:
    def setUp(self):
        uploads_root = Path(__file__).resolve().parents[1] / "uploads"
        uploads_root.mkdir(parents=True, exist_ok=True)
        self._temp_media_root = uploads_root / f"test-media-{uuid4().hex}"
        self._temp_media_root.mkdir(parents=True, exist_ok=True)
        self._media_override = override_settings(MEDIA_ROOT=str(self._temp_media_root))
        self._media_override.enable()
        super().setUp()

    def tearDown(self):
        self._media_override.disable()
        shutil.rmtree(self._temp_media_root, ignore_errors=True)
        super().tearDown()

    def make_uploaded_pdf(self, name="document.pdf", size_kb=120, content_type="application/pdf"):
        header = b"%PDF-1.4\n"
        payload_size = max((size_kb * 1024) - len(header), 0)
        content = header + (b"0" * payload_size)
        return SimpleUploadedFile(name, content, content_type=content_type)

    def assertStoredFileExists(self, file_path):
        self.assertTrue((Path(settings.MEDIA_ROOT) / file_path).exists())

    def write_stored_pdf(self, file_path, size_kb=120):
        full_path = Path(settings.MEDIA_ROOT) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        header = b"%PDF-1.4\n"
        payload_size = max((size_kb * 1024) - len(header), 0)
        full_path.write_bytes(header + (b"0" * payload_size))


class DossierApiTests(TemporaryMediaRootMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="entry",
            password="pass12345",
            role=UserRole.DATA_ENTRY,
        )
        self.client.force_authenticate(user=self.user)
        self.doc_type = DocumentType.objects.create(
            name="قرار تعيين",
            slug="appointment",
            group_name="group",
            display_order=1,
            is_active=True,
        )

    def _payload(self, **overrides):
        payload = {
            "file_number": "DOS-001",
            "full_name": "Test User",
            "national_id": "NAT-001",
            "personal_id": "PER-001",
            "room_number": "R1",
            "column_number": "C1",
            "shelf_number": "S1",
            "first_document.doc_type_id": str(self.doc_type.id),
            "first_document.doc_number": "DOC-001",
            "first_document.doc_name": "First doc",
            "first_document.notes": "ok",
            "first_document.file": self.make_uploaded_pdf(name="appointment_1.pdf", size_kb=120),
        }
        payload.update(overrides)
        return payload

    def test_create_dossier_with_first_document_success(self):
        response = self.client.post("/api/dossiers/", self._payload(), format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Dossier.objects.count(), 1)
        self.assertEqual(Document.objects.count(), 1)
        self.assertIn("documents", response.data)
        self.assertEqual(len(response.data["documents"]), 1)
        dossier = Dossier.objects.get()
        document = Document.objects.get()
        self.assertEqual(response.data["documents"][0]["id"], document.id)
        self.assertEqual(response.data["documents"][0]["status"], DocumentStatus.DRAFT)
        self.assertTrue(document.file_path.startswith(f"uploads/dossier_{dossier.id}/"))
        self.assertEqual(document.file_size_kb, 120)
        self.assertEqual(document.mime_type, "application/pdf")
        self.assertStoredFileExists(document.file_path)

    def test_create_dossier_rejects_missing_first_document(self):
        payload = self._payload()
        for key in list(payload.keys()):
            if key.startswith("first_document."):
                payload.pop(key)
        response = self.client.post("/api/dossiers/", payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Dossier.objects.count(), 0)
        self.assertEqual(Document.objects.count(), 0)
        self.assertIn("first_document", response.data)

    def test_create_dossier_rolls_back_when_document_creation_fails(self):
        with patch(
            "core.services.dossier_service.Document.save",
            side_effect=ValidationError({"doc_number": ["Save failed."]}),
        ):
            response = self.client.post("/api/dossiers/", self._payload(), format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Dossier.objects.count(), 0)
        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(list(Path(settings.MEDIA_ROOT).rglob("*.pdf")), [])

    def test_create_dossier_rejects_non_pdf(self):
        payload = self._payload(
            **{
                "first_document.doc_name": "Bad mime",
                "first_document.file": self.make_uploaded_pdf(
                    name="appointment_3.jpg",
                    size_kb=200,
                    content_type="image/jpeg",
                ),
            }
        )
        response = self.client.post("/api/dossiers/", payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Dossier.objects.count(), 0)
        self.assertEqual(Document.objects.count(), 0)
        self.assertIn("first_document", response.data)

    def test_create_dossier_rejects_inactive_first_document_type(self):
        self.doc_type.is_active = False
        self.doc_type.save(update_fields=["is_active", "updated_at"])

        response = self.client.post("/api/dossiers/", self._payload(), format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["first_document"]["doc_type_id"][0], "نوع الوثيقة غير نشط حاليًا ولا يمكن اختياره.")


class AuthAndLookupApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin1",
            password="pass12345",
            role=UserRole.ADMIN,
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
        )
        self.client.force_authenticate(user=self.user)

        Governorate.objects.create(name="Damascus", is_active=True)
        Governorate.objects.create(name="Inactive Gov", is_active=False)
        DocumentType.objects.create(name="قرار تعيين", slug="appointment", group_name="core", display_order=1, is_active=True)
        DocumentType.objects.create(name="Inactive", slug="inactive", group_name="core", display_order=2, is_active=False)

    def test_auth_me_returns_profile(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], self.user.username)
        self.assertEqual(response.data["role"], UserRole.ADMIN)
        self.assertEqual(response.data["email"], "admin@example.com")

    def test_auth_logout_blacklists_refresh_token(self):
        refresh = RefreshToken.for_user(self.user)
        response = self.client.post("/api/auth/logout/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        outstanding = OutstandingToken.objects.get(token=str(refresh))
        self.assertTrue(BlacklistedToken.objects.filter(token=outstanding).exists())

    def test_governorates_lookup_requires_auth_and_returns_active_only(self):
        self.client.force_authenticate(user=None)
        unauthorized = self.client.get("/api/governorates/")
        self.assertEqual(unauthorized.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/governorates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Damascus")

    def test_document_types_lookup_returns_active_only(self):
        response = self.client.get("/api/document-types/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "قرار تعيين")
        self.assertEqual(set(response.data[0].keys()), {"id", "name"})


class AdminDocumentTypeManagementApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="types_admin", password="pass12345", role=UserRole.ADMIN)
        self.reader = User.objects.create_user(username="types_reader", password="pass12345", role=UserRole.READER)
        self.data_entry = User.objects.create_user(username="types_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.client.force_authenticate(user=self.admin)

        self.active_type = DocumentType.objects.create(
            name="قرار تعيين",
            slug="appointment-decision",
            group_name="core",
            display_order=1,
            is_active=True,
        )
        self.unused_type = DocumentType.objects.create(
            name="بيان خدمة",
            slug="service-statement",
            group_name="core",
            display_order=2,
            is_active=True,
        )
        self.used_type = DocumentType.objects.create(
            name="نسخة عقد",
            slug="contract-copy",
            group_name="core",
            display_order=3,
            is_active=True,
        )
        self.dossier = Dossier.objects.create(
            file_number="TYPE-001",
            full_name="Document Type Owner",
            national_id="TYPE-N-001",
            personal_id="TYPE-P-001",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry,
        )
        self.document = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.used_type,
            doc_number="TYPE-DOC-001",
            doc_name="Linked document",
            file_path="archive/type-linked.pdf",
            file_size_kb=120,
            mime_type="application/pdf",
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
        )

    def test_admin_can_create_document_type(self):
        response = self.client.post(
            "/api/admin/document-types/",
            {"name": "تعهد خطي", "is_active": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "تعهد خطي")
        self.assertTrue(response.data["is_active"])
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.CREATE,
                entity_type="document_type",
                entity_id=response.data["id"],
            ).exists()
        )

    def test_admin_can_list_document_types_with_usage_counts(self):
        response = self.client.get("/api/admin/document-types/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertGreaterEqual(response.data["count"], 3)
        returned_ids = [item["id"] for item in response.data["results"]]
        self.assertIn(self.active_type.id, returned_ids)
        used_entry = next(item for item in response.data["results"] if item["id"] == self.used_type.id)
        self.assertEqual(set(used_entry.keys()), {"id", "name", "is_active", "usage_count"})
        self.assertEqual(used_entry["usage_count"], 1)

    def test_admin_list_search_uses_normalized_arabic_name_contains(self):
        response = self.client.get("/api/admin/document-types/?search=  نسخه  ")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.used_type.id)

    def test_admin_list_can_filter_by_status(self):
        self.used_type.is_active = False
        self.used_type.save(update_fields=["is_active", "updated_at"])

        inactive_response = self.client.get("/api/admin/document-types/?status=inactive")
        active_response = self.client.get("/api/admin/document-types/?status=active")

        self.assertEqual(inactive_response.status_code, status.HTTP_200_OK)
        self.assertEqual({item["id"] for item in inactive_response.data["results"]}, {self.used_type.id})
        active_ids = {item["id"] for item in active_response.data["results"]}
        self.assertIn(self.active_type.id, active_ids)
        self.assertIn(self.unused_type.id, active_ids)
        self.assertNotIn(self.used_type.id, active_ids)

    def test_admin_rejects_duplicate_document_type_name_after_normalization(self):
        response = self.client.post(
            "/api/admin/document-types/",
            {"name": "  قرار   تعيين  ", "is_active": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["name"][0], "يوجد نوع وثيقة بالاسم نفسه بالفعل.")

    def test_admin_can_edit_document_type(self):
        response = self.client.put(
            f"/api/admin/document-types/{self.active_type.id}/",
            {"name": "قرار تعيين محدث", "is_active": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.active_type.refresh_from_db()
        self.assertEqual(self.active_type.name, "قرار تعيين محدث")
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.UPDATE,
                entity_type="document_type",
                entity_id=self.active_type.id,
            ).exists()
        )

    def test_used_document_type_can_be_renamed(self):
        response = self.client.put(
            f"/api/admin/document-types/{self.used_type.id}/",
            {"name": "نسخة عقد محدثة", "is_active": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.used_type.refresh_from_db()
        self.assertEqual(self.used_type.name, "نسخة عقد محدثة")

    def test_admin_can_delete_unused_document_type(self):
        response = self.client.delete(f"/api/admin/document-types/{self.unused_type.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DocumentType.objects.filter(id=self.unused_type.id).exists())
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.DELETE,
                entity_type="document_type",
                entity_id=self.unused_type.id,
            ).exists()
        )

    def test_used_document_type_cannot_be_hard_deleted(self):
        response = self.client.delete(f"/api/admin/document-types/{self.used_type.id}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "لا يمكن حذف نوع الوثيقة لأنه مستخدم في وثائق موجودة. يمكنك تعطيله بدلًا من ذلك.",
        )
        self.assertTrue(DocumentType.objects.filter(id=self.used_type.id).exists())

    def test_used_document_type_can_be_deactivated(self):
        response = self.client.patch(
            f"/api/admin/document-types/{self.used_type.id}/",
            {"is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.used_type.refresh_from_db()
        self.assertFalse(self.used_type.is_active)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.UPDATE,
                entity_type="document_type",
                entity_id=self.used_type.id,
            ).exists()
        )

    def test_inactive_document_type_not_shown_in_active_lookup(self):
        self.used_type.is_active = False
        self.used_type.save(update_fields=["is_active", "updated_at"])

        response = self.client.get("/api/document-types/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [item["id"] for item in response.data]
        self.assertIn(self.active_type.id, returned_ids)
        self.assertNotIn(self.used_type.id, returned_ids)
        self.assertEqual(set(response.data[0].keys()), {"id", "name"})

    def test_old_documents_still_show_inactive_document_type_name(self):
        self.used_type.name = "نسخة عقد محفوظة"
        self.used_type.is_active = False
        self.used_type.save(update_fields=["name", "is_active", "updated_at"])

        response = self.client.get(f"/api/documents/{self.document.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["doc_type"], self.used_type.id)
        self.assertEqual(response.data["doc_type_name"], "نسخة عقد محفوظة")

    def test_non_admin_cannot_manage_document_types(self):
        self.client.force_authenticate(user=self.reader)

        list_response = self.client.get("/api/admin/document-types/")
        create_response = self.client.post("/api/admin/document-types/", {"name": "ممنوع"}, format="json")

        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)


class AdminDashboardApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="dashboard_admin",
            password="pass12345",
            role=UserRole.ADMIN,
            first_name="مدير",
            last_name="النظام",
        )
        self.reader = User.objects.create_user(
            username="dashboard_reader",
            password="pass12345",
            role=UserRole.READER,
            is_active=False,
        )
        self.auditor_one = User.objects.create_user(
            username="auditor_one",
            password="pass12345",
            role=UserRole.AUDITOR,
            first_name="أحمد",
            last_name="علي",
        )
        self.auditor_two = User.objects.create_user(
            username="auditor_two",
            password="pass12345",
            role=UserRole.AUDITOR,
            first_name="سارة",
            last_name="ناصر",
        )
        self.data_entry_one = User.objects.create_user(
            username="entry_one",
            password="pass12345",
            role=UserRole.DATA_ENTRY,
        )
        self.data_entry_two = User.objects.create_user(
            username="entry_two",
            password="pass12345",
            role=UserRole.DATA_ENTRY,
        )
        self.data_entry_three = User.objects.create_user(
            username="entry_three",
            password="pass12345",
            role=UserRole.DATA_ENTRY,
        )
        self.data_entry_one.assigned_auditor = self.auditor_one
        self.data_entry_one.save()
        self.data_entry_three.assigned_auditor = self.auditor_one
        self.data_entry_three.save()

        self.client.force_authenticate(user=self.admin)

        self.doc_type = DocumentType.objects.create(
            name="قرار إداري",
            slug="dashboard-doc-type",
            group_name="dashboard",
            display_order=1,
            is_active=True,
        )

        self.dossier_one = Dossier.objects.create(
            file_number="DASH-001",
            full_name="أضبارة أولى",
            national_id="DASH-N-001",
            personal_id="DASH-P-001",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry_one,
        )
        self.dossier_two = Dossier.objects.create(
            file_number="DASH-002",
            full_name="أضبارة ثانية",
            national_id="DASH-N-002",
            personal_id="DASH-P-002",
            room_number="1",
            column_number="2",
            shelf_number="1",
            created_by=self.data_entry_two,
        )
        self.dossier_three = Dossier.objects.create(
            file_number="DASH-003",
            full_name="أضبارة ثالثة",
            national_id="DASH-N-003",
            personal_id="DASH-P-003",
            room_number="2",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry_three,
        )

        now = timezone.now()
        self.now = now
        self.draft_document = self._create_document(
            dossier=self.dossier_one,
            creator=self.data_entry_one,
            number="DASH-DR-1",
            name="مسودة واردة",
            status=DocumentStatus.DRAFT,
            created_at=now - timedelta(days=2),
        )
        self.pending_document_older = self._create_document(
            dossier=self.dossier_one,
            creator=self.data_entry_one,
            number="DASH-PN-1",
            name="قيد المراجعة الأقدم",
            status=DocumentStatus.PENDING,
            created_at=now - timedelta(days=3),
            submitted_at=now - timedelta(days=1),
        )
        self.pending_document_latest = self._create_document(
            dossier=self.dossier_three,
            creator=self.data_entry_three,
            number="DASH-PN-2",
            name="قيد المراجعة الأحدث",
            status=DocumentStatus.PENDING,
            created_at=now - timedelta(hours=8),
            submitted_at=now - timedelta(hours=2),
        )
        self.rejected_document = self._create_document(
            dossier=self.dossier_one,
            creator=self.data_entry_one,
            number="DASH-RJ-1",
            name="مرفوضة بانتظار التصحيح",
            status=DocumentStatus.REJECTED,
            created_at=now - timedelta(days=4),
            reviewed_by=self.auditor_one,
            reviewed_at=now - timedelta(days=2),
            rejection_reason="بيانات ناقصة",
        )
        self.approved_document_recent = self._create_document(
            dossier=self.dossier_one,
            creator=self.data_entry_one,
            number="DASH-AP-1",
            name="معتمدة حديثًا",
            status=DocumentStatus.APPROVED,
            created_at=now - timedelta(days=1),
            reviewed_by=self.auditor_one,
            reviewed_at=now - timedelta(hours=3),
        )
        self.approved_document_mid = self._create_document(
            dossier=self.dossier_three,
            creator=self.data_entry_three,
            number="DASH-AP-2",
            name="معتمدة قبل يومين",
            status=DocumentStatus.APPROVED,
            created_at=now - timedelta(days=2),
            reviewed_by=self.auditor_one,
            reviewed_at=now - timedelta(days=1, hours=5),
        )
        self.approved_document_old = self._create_document(
            dossier=self.dossier_two,
            creator=self.data_entry_two,
            number="DASH-AP-3",
            name="معتمدة قديمة",
            status=DocumentStatus.APPROVED,
            created_at=now - timedelta(days=10),
            reviewed_by=self.admin,
            reviewed_at=now - timedelta(days=9),
        )
        self.soft_deleted_document = self._create_document(
            dossier=self.dossier_two,
            creator=self.data_entry_two,
            number="DASH-DEL-1",
            name="محذوفة منطقيًا",
            status=DocumentStatus.PENDING,
            created_at=now - timedelta(hours=12),
            submitted_at=now - timedelta(hours=10),
            is_deleted=True,
            deleted_at=now - timedelta(hours=9),
            deleted_by=self.admin,
        )

        self.audit_log_oldest = self._create_audit_log(
            action=AuditAction.CREATE,
            entity_id=self.draft_document.id,
            actor=self.admin,
            created_at=now - timedelta(days=4),
            old_values=None,
            new_values={"doc_number": self.draft_document.doc_number, "status": DocumentStatus.DRAFT},
        )
        self.audit_log_middle = self._create_audit_log(
            action=AuditAction.REJECT,
            entity_id=self.rejected_document.id,
            actor=self.auditor_one,
            created_at=now - timedelta(days=2, hours=1),
            old_values={"status": DocumentStatus.PENDING},
            new_values={"status": DocumentStatus.REJECTED, "rejection_reason": "بيانات ناقصة"},
        )
        self.audit_log_latest = self._create_audit_log(
            action=AuditAction.APPROVE,
            entity_id=self.approved_document_recent.id,
            actor=self.admin,
            created_at=now - timedelta(hours=1),
            old_values={"status": DocumentStatus.PENDING},
            new_values={"status": DocumentStatus.APPROVED},
        )
        self.audit_log_submit_pending_older = self._create_audit_log(
            action=AuditAction.SUBMIT,
            entity_id=self.pending_document_older.id,
            actor=self.data_entry_one,
            created_at=now - timedelta(days=1),
            old_values={"status": DocumentStatus.DRAFT},
            new_values={"status": DocumentStatus.PENDING},
        )
        self.audit_log_submit_approved_recent = self._create_audit_log(
            action=AuditAction.SUBMIT,
            entity_id=self.approved_document_recent.id,
            actor=self.data_entry_one,
            created_at=now - timedelta(hours=20),
            old_values={"status": DocumentStatus.DRAFT},
            new_values={"status": DocumentStatus.PENDING},
        )
        self.audit_log_submit_approved_mid = self._create_audit_log(
            action=AuditAction.SUBMIT,
            entity_id=self.approved_document_mid.id,
            actor=self.data_entry_three,
            created_at=now - timedelta(days=1, hours=8),
            old_values={"status": DocumentStatus.DRAFT},
            new_values={"status": DocumentStatus.PENDING},
        )
        self.audit_log_submit_pending_latest = self._create_audit_log(
            action=AuditAction.SUBMIT,
            entity_id=self.pending_document_latest.id,
            actor=self.data_entry_three,
            created_at=now - timedelta(hours=2),
            old_values={"status": DocumentStatus.DRAFT},
            new_values={"status": DocumentStatus.PENDING},
        )
        self.audit_log_approve_mid = self._create_audit_log(
            action=AuditAction.APPROVE,
            entity_id=self.approved_document_mid.id,
            actor=self.auditor_one,
            created_at=now - timedelta(days=1, hours=5),
            old_values={"status": DocumentStatus.PENDING},
            new_values={"status": DocumentStatus.APPROVED},
        )
        self.audit_log_approve_recent_auditor = self._create_audit_log(
            action=AuditAction.APPROVE,
            entity_id=self.approved_document_recent.id,
            actor=self.auditor_one,
            created_at=now - timedelta(hours=3),
            old_values={"status": DocumentStatus.PENDING},
            new_values={"status": DocumentStatus.APPROVED},
        )
        self.audit_log_admin_reject = self._create_audit_log(
            action=AuditAction.REJECT,
            entity_id=self.rejected_document.id,
            actor=self.admin,
            created_at=now - timedelta(hours=4),
            old_values={"status": DocumentStatus.PENDING},
            new_values={"status": DocumentStatus.REJECTED, "rejection_reason": "Ù…Ø±Ø§Ø¬Ø¹Ø© Ø¥Ø¯Ø§Ø±ÙŠØ©"},
        )

    def _create_document(
        self,
        *,
        dossier,
        creator,
        number,
        name,
        status,
        created_at,
        submitted_at=None,
        reviewed_by=None,
        reviewed_at=None,
        rejection_reason=None,
        is_deleted=False,
        deleted_at=None,
        deleted_by=None,
    ):
        document = Document.objects.create(
            dossier=dossier,
            doc_type=self.doc_type,
            doc_number=number,
            doc_name=name,
            file_path=f"archive/dashboard/{number}.pdf",
            file_size_kb=120,
            mime_type="application/pdf",
            status=status,
            created_by=creator,
            reviewed_by=reviewed_by,
            rejection_reason=rejection_reason,
            is_deleted=is_deleted,
            deleted_at=deleted_at,
            deleted_by=deleted_by,
        )
        Document.objects.filter(pk=document.pk).update(
            created_at=created_at,
            updated_at=created_at,
            submitted_at=submitted_at,
            reviewed_at=reviewed_at,
            deleted_at=deleted_at,
        )
        document.refresh_from_db()
        return document

    def _create_audit_log(self, *, action, entity_id, actor, created_at, old_values, new_values):
        audit_log = AuditLog.objects.create(
            user=actor,
            action=action,
            entity_type="document",
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
        )
        AuditLog.objects.filter(pk=audit_log.pk).update(created_at=created_at)
        audit_log.refresh_from_db()
        return audit_log

    def test_admin_can_access_dashboard(self):
        response = self.client.get("/api/admin/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("summary", response.data)
        self.assertIn("workflow", response.data)
        self.assertIn("user_activity", response.data)
        self.assertIn("employee_tracking", response.data)
        self.assertIn("charts", response.data)
        self.assertIn("recent_activity", response.data)

    def test_non_admin_cannot_access_dashboard(self):
        self.client.force_authenticate(user=self.data_entry_one)

        response = self.client.get("/api/admin/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_counts_and_payload_structure_are_correct(self):
        response = self.client.get("/api/admin/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["summary"],
            {
                "total_active_documents": 7,
                "draft_documents": 1,
                "pending_documents": 2,
                "rejected_documents": 1,
                "approved_documents": 3,
                "total_dossiers": 3,
                "soft_deleted_documents": 1,
                "total_active_users": 6,
            },
        )
        self.assertEqual(
            response.data["workflow"],
            {
                "pending_review_documents": 2,
                "rejected_waiting_correction_documents": 1,
                "approved_documents": 3,
                "recently_created_documents": 6,
                "recent_window_days": 7,
            },
        )
        self.assertEqual(
            response.data["user_activity"],
            {
                "total_data_entry_users": 3,
                "total_auditors": 2,
                "total_readers": 1,
                "total_active_users": 6,
                "data_entry_users_without_assigned_auditor": 1,
                "auditors_with_zero_assigned_data_entry_users": 1,
            },
        )
        self.assertEqual(
            set(response.data["employee_tracking"].keys()),
            {"data_entry_performance", "auditor_performance", "admin_review_activity"},
        )
        self.assertEqual(
            set(response.data["charts"].keys()),
            {
                "documents_by_status",
                "documents_created_over_time",
                "approvals_rejections_over_time",
                "top_data_entry_by_created_documents",
                "top_data_entry_by_review_backlog",
                "top_auditors_by_review_workload",
            },
        )
        self.assertEqual(
            set(response.data["recent_activity"].keys()),
            {
                "latest_pending_documents",
                "latest_rejected_documents",
                "latest_approved_documents",
                "latest_audit_log_events",
            },
        )

    def test_dashboard_data_entry_productivity_counts_are_correct(self):
        response = self.client.get("/api/admin/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        performance_by_username = {
            item["username"]: item for item in response.data["employee_tracking"]["data_entry_performance"]
        }
        self.assertEqual(performance_by_username["entry_one"]["documents_created_count"], 4)
        self.assertEqual(performance_by_username["entry_one"]["dossiers_created_count"], 1)
        self.assertEqual(performance_by_username["entry_one"]["draft_documents_count"], 1)
        self.assertEqual(performance_by_username["entry_one"]["pending_documents_count"], 1)
        self.assertEqual(performance_by_username["entry_one"]["rejected_documents_count"], 1)
        self.assertEqual(performance_by_username["entry_one"]["approved_documents_count"], 1)
        self.assertEqual(performance_by_username["entry_one"]["submissions_count"], 2)
        self.assertEqual(performance_by_username["entry_two"]["documents_created_count"], 2)
        self.assertEqual(performance_by_username["entry_two"]["approved_documents_count"], 1)
        self.assertEqual(performance_by_username["entry_two"]["submissions_count"], 0)
        self.assertIsNone(performance_by_username["entry_two"]["assigned_auditor_name"])
        self.assertEqual(performance_by_username["entry_three"]["documents_created_count"], 2)
        self.assertEqual(performance_by_username["entry_three"]["pending_documents_count"], 1)
        self.assertEqual(performance_by_username["entry_three"]["approved_documents_count"], 1)
        self.assertEqual(performance_by_username["entry_three"]["submissions_count"], 2)
        self.assertIsNotNone(performance_by_username["entry_one"]["last_activity_at"])

    def test_dashboard_auditor_productivity_counts_are_correct(self):
        response = self.client.get("/api/admin/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        performance_by_username = {
            item["username"]: item for item in response.data["employee_tracking"]["auditor_performance"]
        }

        self.assertEqual(performance_by_username["auditor_one"]["assigned_data_entry_count"], 2)
        self.assertEqual(performance_by_username["auditor_one"]["pending_documents_in_scope"], 2)
        self.assertEqual(performance_by_username["auditor_one"]["rejected_documents_in_scope"], 1)
        self.assertEqual(performance_by_username["auditor_one"]["reviewed_documents_count"], 3)
        self.assertEqual(performance_by_username["auditor_one"]["approved_by_auditor_count"], 2)
        self.assertEqual(performance_by_username["auditor_one"]["rejected_by_auditor_count"], 1)
        self.assertIsNotNone(performance_by_username["auditor_one"]["last_activity_at"])
        self.assertEqual(performance_by_username["auditor_two"]["assigned_data_entry_count"], 0)
        self.assertEqual(performance_by_username["auditor_two"]["pending_documents_in_scope"], 0)
        self.assertEqual(performance_by_username["auditor_two"]["rejected_documents_in_scope"], 0)
        self.assertEqual(performance_by_username["auditor_two"]["reviewed_documents_count"], 0)
        self.assertIsNone(performance_by_username["auditor_two"]["last_activity_at"])

    def test_dashboard_admin_review_metrics_are_correct(self):
        response = self.client.get("/api/admin/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        admin_review_activity = response.data["employee_tracking"]["admin_review_activity"]
        self.assertEqual(admin_review_activity["approved_by_admin_count"], 1)
        self.assertEqual(admin_review_activity["rejected_by_admin_count"], 1)
        self.assertIsNotNone(admin_review_activity["latest_admin_review_at"])

    def test_dashboard_chart_data_is_correct(self):
        response = self.client.get("/api/admin/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        status_chart = response.data["charts"]["documents_by_status"]
        self.assertEqual(status_chart["chart_type"], "donut")
        self.assertEqual(status_chart["total"], 7)
        self.assertEqual(
            {item["key"]: item["value"] for item in status_chart["items"]},
            {"draft": 1, "pending": 2, "rejected": 1, "approved": 3},
        )

        created_over_time = {
            item["date"]: item["value"] for item in response.data["charts"]["documents_created_over_time"]["items"]
        }
        chart_start_date = (self.now - timedelta(days=6)).date()
        expected_created_counts = {}
        for document in [
            self.draft_document,
            self.pending_document_older,
            self.pending_document_latest,
            self.rejected_document,
            self.approved_document_recent,
            self.approved_document_mid,
        ]:
            if document.created_at.date() < chart_start_date:
                continue
            key = document.created_at.date().isoformat()
            expected_created_counts[key] = expected_created_counts.get(key, 0) + 1
        for date_key, count in expected_created_counts.items():
            self.assertEqual(created_over_time[date_key], count)

        review_over_time = {
            item["date"]: item for item in response.data["charts"]["approvals_rejections_over_time"]["items"]
        }
        expected_approvals = {}
        expected_rejections = {}
        for audit_log in [
            self.audit_log_latest,
            self.audit_log_approve_recent_auditor,
            self.audit_log_approve_mid,
        ]:
            key = audit_log.created_at.date().isoformat()
            expected_approvals[key] = expected_approvals.get(key, 0) + 1
        for audit_log in [
            self.audit_log_middle,
            self.audit_log_admin_reject,
        ]:
            key = audit_log.created_at.date().isoformat()
            expected_rejections[key] = expected_rejections.get(key, 0) + 1
        for date_key, count in expected_approvals.items():
            self.assertEqual(review_over_time[date_key]["approved_value"], count)
        for date_key, count in expected_rejections.items():
            self.assertEqual(review_over_time[date_key]["rejected_value"], count)

        self.assertEqual(
            response.data["charts"]["top_data_entry_by_created_documents"]["items"][0]["username"],
            "entry_one",
        )
        self.assertEqual(
            response.data["charts"]["top_data_entry_by_created_documents"]["items"][0]["documents_created_count"],
            4,
        )
        self.assertEqual(
            response.data["charts"]["top_auditors_by_review_workload"]["items"][0]["username"],
            "auditor_one",
        )
        self.assertEqual(
            response.data["charts"]["top_auditors_by_review_workload"]["items"][0]["pending_documents_in_scope"],
            2,
        )

    def test_dashboard_recent_lists_return_expected_scoped_data(self):
        response = self.client.get("/api/admin/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        pending_ids = [item["id"] for item in response.data["recent_activity"]["latest_pending_documents"]]
        rejected_ids = [item["id"] for item in response.data["recent_activity"]["latest_rejected_documents"]]
        approved_ids = [item["id"] for item in response.data["recent_activity"]["latest_approved_documents"]]
        audit_event_ids = [item["id"] for item in response.data["recent_activity"]["latest_audit_log_events"]]

        self.assertEqual(pending_ids, [self.pending_document_latest.id, self.pending_document_older.id])
        self.assertEqual(rejected_ids, [self.rejected_document.id])
        self.assertEqual(
            approved_ids,
            [
                self.approved_document_recent.id,
                self.approved_document_mid.id,
                self.approved_document_old.id,
            ],
        )
        self.assertEqual(
            audit_event_ids,
            [
                self.audit_log_latest.id,
                self.audit_log_submit_pending_latest.id,
                self.audit_log_approve_recent_auditor.id,
                self.audit_log_admin_reject.id,
                self.audit_log_submit_approved_recent.id,
            ],
        )
        self.assertNotIn(self.soft_deleted_document.id, pending_ids)


class AdminDashboardEmptyStateApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="empty_dashboard_admin",
            password="pass12345",
            role=UserRole.ADMIN,
        )
        self.client.force_authenticate(user=self.admin)

    def test_dashboard_handles_empty_state_without_users_documents_or_activity(self):
        response = self.client.get("/api/admin/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["summary"],
            {
                "total_active_documents": 0,
                "draft_documents": 0,
                "pending_documents": 0,
                "rejected_documents": 0,
                "approved_documents": 0,
                "total_dossiers": 0,
                "soft_deleted_documents": 0,
                "total_active_users": 1,
            },
        )
        self.assertEqual(response.data["employee_tracking"]["data_entry_performance"], [])
        self.assertEqual(response.data["employee_tracking"]["auditor_performance"], [])
        self.assertEqual(
            response.data["employee_tracking"]["admin_review_activity"],
            {
                "approved_by_admin_count": 0,
                "rejected_by_admin_count": 0,
                "latest_admin_review_at": None,
            },
        )
        self.assertEqual(response.data["recent_activity"]["latest_pending_documents"], [])
        self.assertEqual(response.data["recent_activity"]["latest_rejected_documents"], [])
        self.assertEqual(response.data["recent_activity"]["latest_approved_documents"], [])
        self.assertEqual(response.data["recent_activity"]["latest_audit_log_events"], [])


class DocumentWorkflowApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass12345", role=UserRole.ADMIN)
        self.data_entry = User.objects.create_user(username="entry2", password="pass12345", role=UserRole.DATA_ENTRY)
        self.auditor = User.objects.create_user(username="auditor", password="pass12345", role=UserRole.AUDITOR)
        self.other_auditor = User.objects.create_user(username="auditor_other", password="pass12345", role=UserRole.AUDITOR)
        self.reader = User.objects.create_user(username="reader", password="pass12345", role=UserRole.READER)
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        self.doc_type = DocumentType.objects.create(
            name="قرار",
            slug="qarar",
            group_name="core",
            display_order=1,
            is_active=True,
        )
        self.dossier = Dossier.objects.create(
            file_number="D-100",
            full_name="Workflow User",
            national_id="N-100",
            personal_id="P-100",
            room_number="1",
            column_number="2",
            shelf_number="3",
            created_by=self.data_entry,
        )
        self.document = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="DOC-100",
            doc_name="Workflow doc",
            file_path="archive/doc-100.pdf",
            file_size_kb=150,
            mime_type="application/pdf",
            status=DocumentStatus.DRAFT,
            created_by=self.data_entry,
        )

    def test_submit_transition_success_for_data_entry(self):
        self.client.force_authenticate(user=self.data_entry)
        response = self.client.post(f"/api/documents/{self.document.id}/submit/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, DocumentStatus.PENDING)
        self.assertIsNotNone(self.document.submitted_at)
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.SUBMIT, entity_id=self.document.id).exists())

    def test_approve_transition_success_for_auditor(self):
        self.document.status = DocumentStatus.PENDING
        self.document.save(update_fields=["status", "updated_at"])
        self.client.force_authenticate(user=self.auditor)
        response = self.client.post(f"/api/documents/{self.document.id}/approve/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, DocumentStatus.APPROVED)
        self.assertEqual(self.document.reviewed_by_id, self.auditor.id)
        audit_log = AuditLog.objects.get(action=AuditAction.APPROVE, entity_id=self.document.id)
        self.assertEqual(audit_log.old_values["status"], DocumentStatus.PENDING)
        self.assertIsNone(audit_log.old_values["reviewed_at"])
        self.assertEqual(audit_log.new_values["status"], DocumentStatus.APPROVED)
        self.assertEqual(audit_log.new_values["reviewed_by"], self.auditor.id)
        self.assertIsInstance(audit_log.new_values["reviewed_at"], str)

    def test_reject_requires_rejection_reason(self):
        self.document.status = DocumentStatus.PENDING
        self.document.save(update_fields=["status", "updated_at"])
        self.client.force_authenticate(user=self.auditor)
        response = self.client.post(f"/api/documents/{self.document.id}/reject/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_transition_success(self):
        self.document.status = DocumentStatus.PENDING
        self.document.save(update_fields=["status", "updated_at"])
        self.client.force_authenticate(user=self.auditor)
        response = self.client.post(
            f"/api/documents/{self.document.id}/reject/",
            {"rejection_reason": "Mismatch in document number"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, DocumentStatus.REJECTED)
        self.assertEqual(self.document.rejection_reason, "Mismatch in document number")
        audit_log = AuditLog.objects.get(action=AuditAction.REJECT, entity_id=self.document.id)
        self.assertEqual(audit_log.old_values["status"], DocumentStatus.PENDING)
        self.assertIsNone(audit_log.old_values["reviewed_at"])
        self.assertEqual(audit_log.new_values["status"], DocumentStatus.REJECTED)
        self.assertEqual(audit_log.new_values["reviewed_by"], self.auditor.id)
        self.assertEqual(audit_log.new_values["rejection_reason"], "Mismatch in document number")
        self.assertIsInstance(audit_log.new_values["reviewed_at"], str)

    def test_invalid_transition_approved_cannot_be_submitted(self):
        self.document.status = DocumentStatus.APPROVED
        self.document.save(update_fields=["status", "updated_at"])
        self.client.force_authenticate(user=self.data_entry)
        response = self.client.post(f"/api/documents/{self.document.id}/submit/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_soft_delete_marks_without_physical_removal(self):
        self.client.force_authenticate(user=self.data_entry)
        response = self.client.post(f"/api/documents/{self.document.id}/soft-delete/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.document.refresh_from_db()
        self.assertTrue(self.document.is_deleted)
        self.assertEqual(self.document.deleted_by_id, self.data_entry.id)
        self.assertTrue(Document.objects.filter(id=self.document.id).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.DELETE, entity_id=self.document.id).exists())

    def test_permissions_reader_cannot_call_workflow_actions(self):
        self.client.force_authenticate(user=self.reader)
        response = self.client.post(f"/api/documents/{self.document.id}/submit/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_resubmit_rejected_document_returns_to_pending(self):
        """Rejected document can be resubmitted by data_entry; it returns to pending."""
        self.document.status = DocumentStatus.REJECTED
        self.document.rejection_reason = "Wrong number"
        self.document.save(update_fields=["status", "rejection_reason", "updated_at"])

        self.client.force_authenticate(user=self.data_entry)
        response = self.client.post(f"/api/documents/{self.document.id}/submit/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, DocumentStatus.PENDING)
        self.assertIsNone(self.document.rejection_reason)
        self.assertIsNotNone(self.document.submitted_at)
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.SUBMIT, entity_id=self.document.id).exists())

    def test_submit_pending_document_still_blocked(self):
        """A pending document cannot be submitted again — existing guard must remain intact."""
        self.document.status = DocumentStatus.PENDING
        self.document.save(update_fields=["status", "updated_at"])

        self.client.force_authenticate(user=self.data_entry)
        response = self.client.post(f"/api/documents/{self.document.id}/submit/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_auditor_cannot_review_document_outside_assignment(self):
        self.document.status = DocumentStatus.PENDING
        self.document.save(update_fields=["status", "updated_at"])

        self.client.force_authenticate(user=self.other_auditor)
        response = self.client.post(f"/api/documents/{self.document.id}/approve/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_submit_requires_assigned_auditor_for_data_entry(self):
        self.data_entry.assigned_auditor = None
        self.data_entry.save()

        self.client.force_authenticate(user=self.data_entry)
        response = self.client.post(f"/api/documents/{self.document.id}/submit/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "Data entry users must be assigned to an auditor before submitting documents.",
        )


class AuditLogApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_audit",
            password="pass12345",
            role=UserRole.ADMIN,
            first_name="System",
            last_name="Admin",
        )
        self.auditor = User.objects.create_user(
            username="auditor_audit",
            password="pass12345",
            role=UserRole.AUDITOR,
            first_name="Audit",
            last_name="Reviewer",
        )
        self.data_entry = User.objects.create_user(
            username="entry_audit",
            password="pass12345",
            role=UserRole.DATA_ENTRY,
            first_name="Data",
            last_name="Entry",
        )
        self.reader = User.objects.create_user(username="reader_audit", password="pass12345", role=UserRole.READER)
        self.doc_type = DocumentType.objects.create(
            name="Audit Test Type",
            slug="audit-test-type",
            group_name="audit",
            display_order=1,
            is_active=True,
        )
        self.dossier = Dossier.objects.create(
            file_number="AUD-100",
            full_name="Audit Dossier",
            national_id="AUD-N-100",
            personal_id="AUD-P-100",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry,
        )
        self.document = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AUD-DOC-1",
            doc_name="Family Statement",
            file_path="archive/audit-family-statement.pdf",
            file_size_kb=120,
            mime_type="application/pdf",
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            reviewed_by=self.auditor,
        )

        self.log1 = AuditLog.objects.create(
            user=self.admin,
            action=AuditAction.CREATE,
            entity_type="dossier",
            entity_id=self.dossier.id,
            new_values={"status": "created", "message": "Created audit dossier"},
        )
        self.log2 = AuditLog.objects.create(
            user=self.auditor,
            action=AuditAction.APPROVE,
            entity_type="document",
            entity_id=self.document.id,
            old_values={"status": "pending"},
            new_values={"status": "approved", "message": "Approved family statement"},
        )
        self.log3 = AuditLog.objects.create(
            user=self.admin,
            action=AuditAction.UPDATE,
            entity_type="user",
            entity_id=self.data_entry.id,
            old_values={"role": "data_entry"},
            new_values={"role": "data_entry", "message": "Updated user profile"},
        )

        now = timezone.now()
        AuditLog.objects.filter(pk=self.log1.pk).update(created_at=now - timedelta(days=2))
        AuditLog.objects.filter(pk=self.log2.pk).update(created_at=now - timedelta(days=1))
        AuditLog.objects.filter(pk=self.log3.pk).update(created_at=now)

    def test_audit_logs_list_allowed_for_admin_only(self):
        self.client.force_authenticate(user=self.admin)
        admin_response = self.client.get("/api/audit-logs/")
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.auditor)
        denied_auditor = self.client.get("/api/audit-logs/")
        self.assertEqual(denied_auditor.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.data_entry)
        denied_data_entry = self.client.get("/api/audit-logs/")
        self.assertEqual(denied_data_entry.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.reader)
        denied_reader = self.client.get("/api/audit-logs/")
        self.assertEqual(denied_reader.status_code, status.HTTP_403_FORBIDDEN)

    def test_audit_logs_list_order_and_pagination_shape(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/audit-logs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 3)
        # newest first
        self.assertEqual(response.data["results"][0]["id"], self.log3.id)
        approve_row = next(item for item in response.data["results"] if item["id"] == self.log2.id)
        self.assertEqual(approve_row["actor"]["display_name"], "Audit Reviewer")
        self.assertIn("Family Statement", approve_row["entity_display"])
        self.assertIn("Approved family statement", approve_row["change_summary"])

    def test_audit_logs_useful_search_filters(self):
        self.client.force_authenticate(user=self.admin)

        by_username = self.client.get("/api/audit-logs/?search=auditor_audit")
        self.assertEqual(by_username.status_code, status.HTTP_200_OK)
        self.assertEqual(by_username.data["count"], 1)
        self.assertEqual(by_username.data["results"][0]["id"], self.log2.id)

        by_display_name = self.client.get("/api/audit-logs/?search=Audit Reviewer")
        self.assertEqual(by_display_name.status_code, status.HTTP_200_OK)
        self.assertEqual(by_display_name.data["count"], 1)
        self.assertEqual(by_display_name.data["results"][0]["id"], self.log2.id)

        by_action_code = self.client.get("/api/audit-logs/?search=approve")
        self.assertEqual(by_action_code.status_code, status.HTTP_200_OK)
        self.assertEqual(by_action_code.data["count"], 1)
        self.assertEqual(by_action_code.data["results"][0]["id"], self.log2.id)

        by_action_label = self.client.get("/api/audit-logs/?search=موافقة")
        self.assertEqual(by_action_label.status_code, status.HTTP_200_OK)
        self.assertEqual(by_action_label.data["count"], 1)
        self.assertEqual(by_action_label.data["results"][0]["id"], self.log2.id)

        by_action_filter = self.client.get("/api/audit-logs/?action=approve")
        self.assertEqual(by_action_filter.status_code, status.HTTP_200_OK)
        self.assertEqual(by_action_filter.data["count"], 1)
        self.assertEqual(by_action_filter.data["results"][0]["id"], self.log2.id)

        by_entity_title = self.client.get("/api/audit-logs/?search=Family Statement")
        self.assertEqual(by_entity_title.status_code, status.HTTP_200_OK)
        self.assertEqual(by_entity_title.data["count"], 1)
        self.assertEqual(by_entity_title.data["results"][0]["id"], self.log2.id)

        by_summary = self.client.get("/api/audit-logs/?search=Approved family statement")
        self.assertEqual(by_summary.status_code, status.HTTP_200_OK)
        self.assertEqual(by_summary.data["count"], 1)
        self.assertEqual(by_summary.data["results"][0]["id"], self.log2.id)

        today_str = timezone.now().date().isoformat()
        by_date = self.client.get(f"/api/audit-logs/?date_from={today_str}")
        self.assertEqual(by_date.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(by_date.data["count"], 1)

    def test_removed_technical_filters_do_not_affect_results(self):
        self.client.force_authenticate(user=self.admin)

        baseline = self.client.get("/api/audit-logs/?action=approve")
        ignored_filters = self.client.get(
            "/api/audit-logs/?action=approve&entity_type=user&entity_id=999&model=user&table_name=user&object_id=999"
        )
        self.assertEqual(ignored_filters.status_code, status.HTTP_200_OK)
        self.assertEqual(ignored_filters.data["count"], baseline.data["count"])
        self.assertEqual(ignored_filters.data["results"][0]["id"], baseline.data["results"][0]["id"])

    def test_audit_logs_default_pagination_stays_stable(self):
        self.client.force_authenticate(user=self.admin)
        for index in range(25):
            AuditLog.objects.create(
                user=self.admin,
                action=AuditAction.UPDATE,
                entity_type="user",
                entity_id=self.admin.id,
                new_values={"message": f"bulk update {index}"},
            )

        first_page = self.client.get("/api/audit-logs/?page_size=5")
        self.assertEqual(first_page.status_code, status.HTTP_200_OK)
        self.assertEqual(first_page.data["count"], 28)
        self.assertEqual(len(first_page.data["results"]), 20)
        self.assertIsNotNone(first_page.data["next"])

        second_page = self.client.get("/api/audit-logs/?page=2&page_size=5")
        self.assertEqual(second_page.status_code, status.HTTP_200_OK)
        self.assertEqual(len(second_page.data["results"]), 8)

    def test_audit_log_detail(self):
        """Audit log detail is admin-only per approved policy (Req 6)."""
        # Admin can access
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f"/api/audit-logs/{self.log2.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.log2.id)
        self.assertEqual(response.data["actor"]["id"], self.auditor.id)

        # Auditor is denied (audit logs are admin-only)
        self.client.force_authenticate(user=self.auditor)
        denied = self.client.get(f"/api/audit-logs/{self.log2.id}/")
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)


class DossierListQueryApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="d_admin", password="pass12345", role=UserRole.ADMIN)
        self.data_entry = User.objects.create_user(username="d_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.other_data_entry = User.objects.create_user(username="d_entry_other", password="pass12345", role=UserRole.DATA_ENTRY)
        self.auditor = User.objects.create_user(username="d_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.other_auditor = User.objects.create_user(username="d_auditor_other", password="pass12345", role=UserRole.AUDITOR)
        self.reader = User.objects.create_user(username="d_reader", password="pass12345", role=UserRole.READER)

        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self.other_data_entry.assigned_auditor = self.other_auditor
        self.other_data_entry.save()

        self.g1 = Governorate.objects.create(name="Damascus", is_active=True)
        self.g2 = Governorate.objects.create(name="Homs", is_active=True)
        self.doc_type = DocumentType.objects.create(
            name="Dossier Query Doc",
            slug="dossier-query-doc",
            group_name="query",
            display_order=1,
            is_active=True,
        )

        self.assigned_pending_dossier = Dossier.objects.create(
            file_number="DOS-A-PENDING",
            full_name="Assigned Pending Dossier",
            national_id="DOS-N-001",
            personal_id="DOS-P-001",
            governorate=self.g1,
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry,
        )
        self.assigned_approved_archived_dossier = Dossier.objects.create(
            file_number="DOS-A-APPROVED",
            full_name="Assigned Approved Dossier",
            national_id="DOS-N-002",
            personal_id="DOS-P-002",
            governorate=self.g2,
            room_number="2",
            column_number="2",
            shelf_number="2",
            created_by=self.data_entry,
            is_archived=True,
        )
        self.assigned_draft_only_dossier = Dossier.objects.create(
            file_number="DOS-A-DRAFT",
            full_name="Assigned Draft Dossier",
            national_id="DOS-N-003",
            personal_id="DOS-P-003",
            governorate=self.g1,
            room_number="3",
            column_number="3",
            shelf_number="3",
            created_by=self.data_entry,
        )
        self.other_approved_dossier = Dossier.objects.create(
            file_number="DOS-O-APPROVED",
            full_name="Other Approved Dossier",
            national_id="DOS-N-004",
            personal_id="DOS-P-004",
            governorate=self.g2,
            room_number="4",
            column_number="4",
            shelf_number="4",
            created_by=self.other_data_entry,
        )
        self.admin_pending_dossier = Dossier.objects.create(
            file_number="DOS-ADMIN-PENDING",
            full_name="Admin Pending Dossier",
            national_id="DOS-N-005",
            personal_id="DOS-P-005",
            governorate=self.g1,
            room_number="5",
            column_number="5",
            shelf_number="5",
            created_by=self.admin,
        )

        Document.objects.create(
            dossier=self.assigned_pending_dossier,
            doc_type=self.doc_type,
            doc_number="DOS-DOC-PENDING",
            doc_name="Assigned Pending Doc",
            file_path="archive/dos-pending.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.data_entry,
        )
        Document.objects.create(
            dossier=self.assigned_approved_archived_dossier,
            doc_type=self.doc_type,
            doc_number="DOS-DOC-APPROVED",
            doc_name="Assigned Approved Doc",
            file_path="archive/dos-approved.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
        )
        Document.objects.create(
            dossier=self.assigned_draft_only_dossier,
            doc_type=self.doc_type,
            doc_number="DOS-DOC-DRAFT",
            doc_name="Assigned Draft Doc",
            file_path="archive/dos-draft.pdf",
            file_size_kb=100,
            status=DocumentStatus.DRAFT,
            created_by=self.data_entry,
        )
        Document.objects.create(
            dossier=self.other_approved_dossier,
            doc_type=self.doc_type,
            doc_number="DOS-DOC-OTHER",
            doc_name="Other Approved Doc",
            file_path="archive/dos-other.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.other_data_entry,
        )
        Document.objects.create(
            dossier=self.admin_pending_dossier,
            doc_type=self.doc_type,
            doc_number="DOS-DOC-ADMIN",
            doc_name="Admin Pending Doc",
            file_path="archive/dos-admin.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.admin,
        )

        now = timezone.now()
        Dossier.objects.filter(pk=self.assigned_pending_dossier.pk).update(created_at=now - timedelta(days=4))
        Dossier.objects.filter(pk=self.assigned_approved_archived_dossier.pk).update(created_at=now - timedelta(days=3))
        Dossier.objects.filter(pk=self.assigned_draft_only_dossier.pk).update(created_at=now - timedelta(days=2))
        Dossier.objects.filter(pk=self.other_approved_dossier.pk).update(created_at=now - timedelta(days=1))
        Dossier.objects.filter(pk=self.admin_pending_dossier.pk).update(created_at=now)

    def test_dossier_visibility_for_admin_data_entry_auditor_and_reader(self):
        self.client.force_authenticate(user=self.admin)
        admin_response = self.client.get("/api/dossiers/")
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_response.data["count"], 5)

        self.client.force_authenticate(user=self.data_entry)
        data_entry_response = self.client.get("/api/dossiers/")
        self.assertEqual(data_entry_response.status_code, status.HTTP_200_OK)
        self.assertEqual(data_entry_response.data["count"], 3)
        self.assertEqual(
            {item["id"] for item in data_entry_response.data["results"]},
            {
                self.assigned_pending_dossier.id,
                self.assigned_approved_archived_dossier.id,
                self.assigned_draft_only_dossier.id,
            },
        )

        self.client.force_authenticate(user=self.auditor)
        auditor_response = self.client.get("/api/dossiers/")
        self.assertEqual(auditor_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in auditor_response.data["results"]},
            {
                self.assigned_pending_dossier.id,
                self.assigned_approved_archived_dossier.id,
            },
        )

        self.client.force_authenticate(user=self.reader)
        reader_response = self.client.get("/api/dossiers/")
        self.assertEqual(reader_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in reader_response.data["results"]},
            {
                self.assigned_approved_archived_dossier.id,
                self.other_approved_dossier.id,
            },
        )

    def test_dossier_text_search_does_not_leak_scope(self):
        self.client.force_authenticate(user=self.auditor)
        outside_scope = self.client.get(f"/api/dossiers/?search={self.other_approved_dossier.file_number}")
        self.assertEqual(outside_scope.status_code, status.HTTP_200_OK)
        self.assertEqual(outside_scope.data["count"], 0)

        draft_only = self.client.get(f"/api/dossiers/?search={self.assigned_draft_only_dossier.file_number}")
        self.assertEqual(draft_only.status_code, status.HTTP_200_OK)
        self.assertEqual(draft_only.data["count"], 0)

        self.client.force_authenticate(user=self.reader)
        pending_scope = self.client.get(f"/api/dossiers/?search={self.assigned_pending_dossier.file_number}")
        self.assertEqual(pending_scope.status_code, status.HTTP_200_OK)
        self.assertEqual(pending_scope.data["count"], 0)

    def test_dossier_combined_filters_stay_within_visibility_scope(self):
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get(f"/api/dossiers/?search=Approved&governorate={self.g2.id}&is_deleted=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.assigned_approved_archived_dossier.id)

    def test_empty_dossier_filters_are_ignored_safely(self):
        self.client.force_authenticate(user=self.admin)
        baseline = self.client.get("/api/dossiers/")
        with_empty_values = self.client.get("/api/dossiers/?search=&governorate=&is_deleted=&created_by=")
        self.assertEqual(with_empty_values.status_code, status.HTTP_200_OK)
        self.assertEqual(with_empty_values.data["count"], baseline.data["count"])

    def test_dossier_ordering_and_pagination_remain_consistent(self):
        self.client.force_authenticate(user=self.admin)
        ordered = self.client.get("/api/dossiers/?ordering=file_number")
        self.assertEqual(ordered.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["file_number"] for item in ordered.data["results"]],
            [
                "DOS-A-APPROVED",
                "DOS-A-DRAFT",
                "DOS-A-PENDING",
                "DOS-ADMIN-PENDING",
                "DOS-O-APPROVED",
            ],
        )

        paged = self.client.get("/api/dossiers/?page_size=2")
        self.assertEqual(paged.status_code, status.HTTP_200_OK)
        self.assertEqual(paged.data["count"], 5)
        self.assertEqual(len(paged.data["results"]), 2)


class DocumentListQueryApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="q_admin", password="pass12345", role=UserRole.ADMIN)
        self.data_entry = User.objects.create_user(username="q_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.other_data_entry = User.objects.create_user(username="q_entry_other", password="pass12345", role=UserRole.DATA_ENTRY)
        self.auditor = User.objects.create_user(username="q_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.other_auditor = User.objects.create_user(username="q_auditor_other", password="pass12345", role=UserRole.AUDITOR)
        self.reader = User.objects.create_user(username="q_reader", password="pass12345", role=UserRole.READER)

        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self.other_data_entry.assigned_auditor = self.other_auditor
        self.other_data_entry.save()

        self.doc_type_1 = DocumentType.objects.create(name="Type 1", slug="type-1", group_name="core", display_order=1, is_active=True)
        self.doc_type_2 = DocumentType.objects.create(name="Type 2", slug="type-2", group_name="core", display_order=2, is_active=True)

        self.entry_dossier = Dossier.objects.create(
            file_number="QD-ENTRY",
            full_name="Entry Dossier",
            national_id="Q-N1",
            personal_id="Q-P1",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry,
        )
        self.other_entry_dossier = Dossier.objects.create(
            file_number="QD-OTHER",
            full_name="Other Entry Dossier",
            national_id="Q-N2",
            personal_id="Q-P2",
            room_number="2",
            column_number="2",
            shelf_number="2",
            created_by=self.other_data_entry,
        )
        self.admin_dossier = Dossier.objects.create(
            file_number="QD-ADMIN",
            full_name="Admin Dossier",
            national_id="Q-N3",
            personal_id="Q-P3",
            room_number="3",
            column_number="3",
            shelf_number="3",
            created_by=self.admin,
        )
        self.numeric_entry_dossier = Dossier.objects.create(
            file_number="10045",
            full_name="Numeric Entry Dossier",
            national_id="Q-N4",
            personal_id="Q-P4",
            room_number="4",
            column_number="4",
            shelf_number="4",
            created_by=self.data_entry,
        )
        self.numeric_other_dossier = Dossier.objects.create(
            file_number="20077",
            full_name="Numeric Other Dossier",
            national_id="Q-N5",
            personal_id="Q-P5",
            room_number="5",
            column_number="5",
            shelf_number="5",
            created_by=self.other_data_entry,
        )

        self.entry_approved = Document.objects.create(
            dossier=self.entry_dossier,
            doc_type=self.doc_type_1,
            doc_number="ENTRY-APP",
            doc_name="Entry Approved",
            file_path="archive/entry-approved.pdf",
            file_size_kb=120,
            mime_type="application/pdf",
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            reviewed_by=self.auditor,
            reviewed_at=timezone.now() - timedelta(hours=1),
        )
        self.entry_pending = Document.objects.create(
            dossier=self.entry_dossier,
            doc_type=self.doc_type_2,
            doc_number="ENTRY-PEN",
            doc_name="Entry Pending",
            file_path="archive/entry-pending.pdf",
            file_size_kb=121,
            mime_type="application/pdf",
            status=DocumentStatus.PENDING,
            created_by=self.data_entry,
        )
        self.entry_rejected = Document.objects.create(
            dossier=self.entry_dossier,
            doc_type=self.doc_type_2,
            doc_number="ENTRY-REJ",
            doc_name="Entry Rejected",
            file_path="archive/entry-rejected.pdf",
            file_size_kb=122,
            mime_type="application/pdf",
            status=DocumentStatus.REJECTED,
            rejection_reason="Needs fixes",
            created_by=self.data_entry,
        )
        self.entry_draft = Document.objects.create(
            dossier=self.entry_dossier,
            doc_type=self.doc_type_1,
            doc_number="ENTRY-DRF",
            doc_name="Entry Draft",
            file_path="archive/entry-draft.pdf",
            file_size_kb=123,
            mime_type="application/pdf",
            status=DocumentStatus.DRAFT,
            created_by=self.data_entry,
        )
        self.other_entry_approved = Document.objects.create(
            dossier=self.other_entry_dossier,
            doc_type=self.doc_type_2,
            doc_number="OTHER-APP",
            doc_name="Other Approved",
            file_path="archive/other-approved.pdf",
            file_size_kb=124,
            mime_type="application/pdf",
            status=DocumentStatus.APPROVED,
            created_by=self.other_data_entry,
            reviewed_by=self.other_auditor,
        )
        self.admin_pending = Document.objects.create(
            dossier=self.admin_dossier,
            doc_type=self.doc_type_1,
            doc_number="ADMIN-PEN",
            doc_name="Admin Pending",
            file_path="archive/admin-pending.pdf",
            file_size_kb=125,
            mime_type="application/pdf",
            status=DocumentStatus.PENDING,
            created_by=self.admin,
        )
        self.numeric_entry_pending = Document.objects.create(
            dossier=self.numeric_entry_dossier,
            doc_type=self.doc_type_1,
            doc_number="ENTRY-NUM",
            doc_name="Entry Numeric Dossier",
            file_path="archive/entry-numeric.pdf",
            file_size_kb=127,
            mime_type="application/pdf",
            status=DocumentStatus.PENDING,
            created_by=self.data_entry,
        )
        self.numeric_other_pending = Document.objects.create(
            dossier=self.numeric_other_dossier,
            doc_type=self.doc_type_2,
            doc_number="OTHER-NUM",
            doc_name="Other Numeric Dossier",
            file_path="archive/other-numeric.pdf",
            file_size_kb=128,
            mime_type="application/pdf",
            status=DocumentStatus.PENDING,
            created_by=self.other_data_entry,
        )
        self.deleted_entry_approved = Document.objects.create(
            dossier=self.entry_dossier,
            doc_type=self.doc_type_1,
            doc_number="ENTRY-DEL",
            doc_name="Deleted Approved",
            file_path="archive/entry-deleted.pdf",
            file_size_kb=126,
            mime_type="application/pdf",
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            is_deleted=True,
        )

        now = timezone.now()
        Document.objects.filter(pk=self.entry_approved.pk).update(created_at=now - timedelta(days=6))
        Document.objects.filter(pk=self.entry_pending.pk).update(created_at=now - timedelta(days=5))
        Document.objects.filter(pk=self.entry_rejected.pk).update(created_at=now - timedelta(days=4))
        Document.objects.filter(pk=self.entry_draft.pk).update(created_at=now - timedelta(days=3))
        Document.objects.filter(pk=self.other_entry_approved.pk).update(created_at=now - timedelta(days=2))
        Document.objects.filter(pk=self.admin_pending.pk).update(created_at=now - timedelta(days=1))
        Document.objects.filter(pk=self.numeric_entry_pending.pk).update(created_at=now - timedelta(hours=12))
        Document.objects.filter(pk=self.numeric_other_pending.pk).update(created_at=now - timedelta(hours=6))
        Document.objects.filter(pk=self.deleted_entry_approved.pk).update(created_at=now)

    def test_document_visibility_for_admin_data_entry_auditor_and_reader(self):
        self.client.force_authenticate(user=self.admin)
        admin_response = self.client.get("/api/documents/")
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in admin_response.data["results"]},
            {
                self.entry_approved.id,
                self.entry_pending.id,
                self.entry_rejected.id,
                self.entry_draft.id,
                self.other_entry_approved.id,
                self.admin_pending.id,
                self.numeric_entry_pending.id,
                self.numeric_other_pending.id,
            },
        )

        self.client.force_authenticate(user=self.data_entry)
        data_entry_response = self.client.get("/api/documents/")
        self.assertEqual(data_entry_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in data_entry_response.data["results"]},
            {
                self.entry_approved.id,
                self.entry_pending.id,
                self.entry_rejected.id,
                self.entry_draft.id,
                self.numeric_entry_pending.id,
            },
        )

        self.client.force_authenticate(user=self.auditor)
        auditor_response = self.client.get("/api/documents/")
        self.assertEqual(auditor_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in auditor_response.data["results"]},
            {
                self.entry_approved.id,
                self.entry_pending.id,
                self.entry_rejected.id,
                self.numeric_entry_pending.id,
            },
        )

        self.client.force_authenticate(user=self.reader)
        reader_response = self.client.get("/api/documents/")
        self.assertEqual(reader_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in reader_response.data["results"]},
            {self.entry_approved.id, self.other_entry_approved.id},
        )

    def test_document_text_search_does_not_leak_scope(self):
        self.client.force_authenticate(user=self.auditor)
        outside_scope = self.client.get(f"/api/documents/?search={self.other_entry_approved.doc_number}")
        self.assertEqual(outside_scope.status_code, status.HTTP_200_OK)
        self.assertEqual(outside_scope.data["count"], 0)

        hidden_draft = self.client.get(f"/api/documents/?search={self.entry_draft.doc_number}")
        self.assertEqual(hidden_draft.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden_draft.data["count"], 0)

    def test_document_search_by_dossier_number_respects_scope(self):
        self.client.force_authenticate(user=self.admin)
        admin_response = self.client.get(f"/api/documents/?search={self.entry_dossier.file_number}")
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_response.data["count"], 4)

        self.client.force_authenticate(user=self.auditor)
        auditor_response = self.client.get(f"/api/documents/?search={self.entry_dossier.file_number}")
        self.assertEqual(auditor_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in auditor_response.data["results"]},
            {
                self.entry_approved.id,
                self.entry_pending.id,
                self.entry_rejected.id,
            },
        )

        self.client.force_authenticate(user=self.reader)
        reader_response = self.client.get(f"/api/documents/?search={self.entry_dossier.file_number}")
        self.assertEqual(reader_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reader_response.data["count"], 1)
        self.assertEqual(reader_response.data["results"][0]["id"], self.entry_approved.id)

    def test_document_dossier_filter_by_file_number_respects_scope(self):
        self.client.force_authenticate(user=self.auditor)
        visible_response = self.client.get(f"/api/documents/?dossier={self.entry_dossier.file_number}")
        self.assertEqual(visible_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in visible_response.data["results"]},
            {
                self.entry_approved.id,
                self.entry_pending.id,
                self.entry_rejected.id,
            },
        )

        hidden_response = self.client.get(f"/api/documents/?dossier={self.other_entry_dossier.file_number}")
        self.assertEqual(hidden_response.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden_response.data["count"], 0)

    def test_document_dossier_filter_by_numeric_file_number_respects_scope(self):
        self.client.force_authenticate(user=self.admin)
        general_search_response = self.client.get(f"/api/documents/?search={self.numeric_entry_dossier.file_number}")
        self.assertEqual(general_search_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in general_search_response.data["results"]},
            {self.numeric_entry_pending.id},
        )

        dedicated_filter_response = self.client.get(f"/api/documents/?dossier={self.numeric_entry_dossier.file_number}")
        self.assertEqual(dedicated_filter_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in dedicated_filter_response.data["results"]},
            {self.numeric_entry_pending.id},
        )

        self.client.force_authenticate(user=self.auditor)
        scoped_response = self.client.get(f"/api/documents/?dossier={self.numeric_other_dossier.file_number}")
        self.assertEqual(scoped_response.status_code, status.HTTP_200_OK)
        self.assertEqual(scoped_response.data["count"], 0)

        nonexistent_response = self.client.get("/api/documents/?dossier=999999")
        self.assertEqual(nonexistent_response.status_code, status.HTTP_200_OK)
        self.assertEqual(nonexistent_response.data["count"], 0)

    def test_document_number_search_still_works_after_dossier_search_fix(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f"/api/documents/?search={self.entry_pending.doc_number}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in response.data["results"]},
            {self.entry_pending.id},
        )

    def test_document_status_filter_is_role_safe(self):
        self.client.force_authenticate(user=self.auditor)
        auditor_draft = self.client.get("/api/documents/?status=draft")
        self.assertEqual(auditor_draft.status_code, status.HTTP_200_OK)
        self.assertEqual(auditor_draft.data["count"], 0)

        self.client.force_authenticate(user=self.reader)
        reader_pending = self.client.get("/api/documents/?status=pending")
        self.assertEqual(reader_pending.status_code, status.HTTP_200_OK)
        self.assertEqual(reader_pending.data["count"], 0)

        reader_approved = self.client.get("/api/documents/?status=approved")
        self.assertEqual(reader_approved.status_code, status.HTTP_200_OK)
        self.assertEqual(reader_approved.data["count"], 2)

    def test_document_combined_filters_stay_within_scope(self):
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get(
            f"/api/documents/?status=approved&doc_type={self.doc_type_1.id}&created_by={self.data_entry.username}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.entry_approved.id)

    def test_empty_document_filters_are_ignored_safely(self):
        self.client.force_authenticate(user=self.admin)
        baseline = self.client.get("/api/documents/")
        with_empty_values = self.client.get(
            "/api/documents/?search=&status=&doc_type=&dossier=&created_by=&reviewed_by=&is_deleted="
        )
        self.assertEqual(with_empty_values.status_code, status.HTTP_200_OK)
        self.assertEqual(with_empty_values.data["count"], baseline.data["count"])

    def test_document_ordering_and_pagination_remain_consistent(self):
        self.client.force_authenticate(user=self.admin)
        ordered = self.client.get("/api/documents/?ordering=created_at")
        self.assertEqual(ordered.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in ordered.data["results"]],
            [
                self.entry_approved.id,
                self.entry_pending.id,
                self.entry_rejected.id,
                self.entry_draft.id,
                self.other_entry_approved.id,
                self.admin_pending.id,
                self.numeric_entry_pending.id,
                self.numeric_other_pending.id,
            ],
        )

        paged = self.client.get("/api/documents/?page_size=2")
        self.assertEqual(paged.status_code, status.HTTP_200_OK)
        self.assertEqual(paged.data["count"], 8)
        self.assertEqual(len(paged.data["results"]), 2)

    def test_deleted_documents_never_expand_search_scope(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/documents/?is_deleted=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)


class DocumentCreateUpdateApiTests(TemporaryMediaRootMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="cu_admin", password="pass12345", role=UserRole.ADMIN)
        self.data_entry = User.objects.create_user(username="cu_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.auditor = User.objects.create_user(username="cu_auditor", password="pass12345", role=UserRole.AUDITOR)

        self.client.force_authenticate(user=self.data_entry)

        self.doc_type_1 = DocumentType.objects.create(name="Type A", slug="type-a", group_name="core", display_order=1, is_active=True)
        self.dossier_1 = Dossier.objects.create(
            file_number="DOS-CU-001",
            full_name="User",
            national_id="N-CU-1",
            personal_id="P-CU-1",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry,
        )
        self.dossier_archived = Dossier.objects.create(
            file_number="DOS-CU-002",
            full_name="Archived",
            national_id="N-CU-2",
            personal_id="P-CU-2",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry,
            is_archived=True,
        )

    def create_document_with_stored_file(self, *, status_value, created_by=None, dossier=None, rejection_reason=None):
        created_by = created_by or self.data_entry
        dossier = dossier or self.dossier_1
        relative_path = f"uploads/dossier_{dossier.id}/{uuid4().hex}.pdf"
        self.write_stored_pdf(relative_path)
        return Document.objects.create(
            dossier=dossier,
            doc_type=self.doc_type_1,
            doc_number=f"DOC-{uuid4().hex[:8]}",
            doc_name="Stored Document",
            file_path=relative_path,
            file_size_kb=120,
            mime_type="application/pdf",
            status=status_value,
            rejection_reason=rejection_reason,
            created_by=created_by,
        )

    def test_create_document_success(self):
        payload = {
            "dossier": str(self.dossier_1.id),
            "doc_type": str(self.doc_type_1.id),
            "doc_number": "NEW-DOC-1",
            "doc_name": "New Document",
            "file": self.make_uploaded_pdf(name="new_doc1.pdf", size_kb=200),
        }
        res = self.client.post("/api/documents/", payload, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        doc = Document.objects.get(doc_number="NEW-DOC-1")
        self.assertEqual(doc.status, DocumentStatus.DRAFT)
        self.assertTrue(doc.file_path.startswith(f"uploads/dossier_{self.dossier_1.id}/"))
        self.assertEqual(doc.file_size_kb, 200)
        self.assertEqual(doc.mime_type, "application/pdf")
        self.assertStoredFileExists(doc.file_path)
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.CREATE, entity_id=doc.id).exists())

    def test_create_document_on_archived_dossier_fails(self):
        payload = {
            "dossier": str(self.dossier_archived.id),
            "doc_type": str(self.doc_type_1.id),
            "doc_number": "NEW-DOC-2",
            "doc_name": "New Document",
            "file": self.make_uploaded_pdf(name="new_doc2.pdf", size_kb=200),
        }
        res = self.client.post("/api/documents/", payload, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dossier", res.data)

    def test_create_document_with_inactive_type_fails(self):
        self.doc_type_1.is_active = False
        self.doc_type_1.save(update_fields=["is_active", "updated_at"])

        payload = {
            "dossier": str(self.dossier_1.id),
            "doc_type": str(self.doc_type_1.id),
            "doc_number": "NEW-DOC-INACTIVE",
            "doc_name": "Inactive Type Document",
            "file": self.make_uploaded_pdf(name="inactive_type.pdf", size_kb=200),
        }
        res = self.client.post("/api/documents/", payload, format="multipart")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["doc_type"][0], "نوع الوثيقة غير نشط حاليًا ولا يمكن اختياره.")

    def test_data_entry_cannot_create_document_on_others_dossier(self):
        other_user = User.objects.create_user(username="create_other_owner", password="pass12345", role=UserRole.DATA_ENTRY)
        other_dossier = Dossier.objects.create(
            file_number="DOS-CU-003",
            full_name="Other Owner",
            national_id="N-CU-3",
            personal_id="P-CU-3",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=other_user,
        )

        payload = {
            "dossier": str(other_dossier.id),
            "doc_type": str(self.doc_type_1.id),
            "doc_number": "NEW-DOC-OTHER",
            "doc_name": "Other Dossier Document",
            "file": self.make_uploaded_pdf(name="new_doc_other.pdf", size_kb=200),
        }
        res = self.client.post("/api/documents/", payload, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dossier", res.data)

    def test_update_draft_document_success(self):
        doc = Document.objects.create(
            dossier=self.dossier_1,
            doc_type=self.doc_type_1,
            doc_number="EXISTING",
            doc_name="Draft Doc",
            file_path="archive/draft1.pdf",
            file_size_kb=150,
            status=DocumentStatus.DRAFT,
            created_by=self.data_entry
        )
        payload = {
            "doc_type": self.doc_type_1.id,
            "doc_number": "UPDATED-DOC",
            "doc_name": "Updated Name",
            "file_path": "archive/updated.pdf",
            "file_size_kb": 300,
            "mime_type": "application/pdf"
        }
        res = self.client.put(f"/api/documents/{doc.id}/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        doc.refresh_from_db()
        self.assertEqual(doc.doc_number, "UPDATED-DOC")
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.UPDATE, entity_id=doc.id).exists())

    def test_update_pending_document_fails(self):
        doc = Document.objects.create(
            dossier=self.dossier_1,
            doc_type=self.doc_type_1,
            doc_number="PENDING-DOC",
            doc_name="Pending Doc",
            file_path="archive/pending.pdf",
            file_size_kb=150,
            status=DocumentStatus.PENDING,
            created_by=self.data_entry
        )
        payload = {
            "doc_type": self.doc_type_1.id,
            "doc_number": "UPDATED-DOC",
            "doc_name": "Updated Name",
            "file_path": "archive/updated.pdf",
            "file_size_kb": 300,
            "mime_type": "application/pdf"
        }
        res = self.client.put(f"/api/documents/{doc.id}/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_document_keeps_existing_inactive_type(self):
        self.doc_type_1.is_active = False
        self.doc_type_1.save(update_fields=["is_active", "updated_at"])
        doc = Document.objects.create(
            dossier=self.dossier_1,
            doc_type=self.doc_type_1,
            doc_number="INACTIVE-KEEP",
            doc_name="Inactive Keep",
            file_path="archive/inactive-keep.pdf",
            file_size_kb=150,
            status=DocumentStatus.DRAFT,
            created_by=self.data_entry,
        )

        payload = {
            "doc_type": self.doc_type_1.id,
            "doc_number": "INACTIVE-KEEP-UPDATED",
            "doc_name": "Inactive Keep Updated",
            "file_path": "archive/inactive-keep.pdf",
            "file_size_kb": 150,
            "mime_type": "application/pdf",
            "notes": "",
        }
        res = self.client.put(f"/api/documents/{doc.id}/", payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        doc.refresh_from_db()
        self.assertEqual(doc.doc_type_id, self.doc_type_1.id)

    def test_update_document_cannot_switch_to_different_inactive_type(self):
        other_inactive_type = DocumentType.objects.create(
            name="Type B",
            slug="type-b",
            group_name="core",
            display_order=2,
            is_active=False,
        )
        doc = Document.objects.create(
            dossier=self.dossier_1,
            doc_type=self.doc_type_1,
            doc_number="INACTIVE-SWITCH",
            doc_name="Inactive Switch",
            file_path="archive/inactive-switch.pdf",
            file_size_kb=150,
            status=DocumentStatus.DRAFT,
            created_by=self.data_entry,
        )

        payload = {
            "doc_type": other_inactive_type.id,
            "doc_number": "INACTIVE-SWITCH",
            "doc_name": "Inactive Switch",
            "file_path": "archive/inactive-switch.pdf",
            "file_size_kb": 150,
            "mime_type": "application/pdf",
            "notes": "",
        }
        res = self.client.put(f"/api/documents/{doc.id}/", payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["doc_type"][0], "نوع الوثيقة غير نشط حاليًا ولا يمكن اختياره.")

    def test_data_entry_cannot_delete_others_document(self):
        """Data entry cannot soft-delete documents created by other users (Req 3 isolation)."""
        other_user = User.objects.create_user(username="other_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        other_doc = Document.objects.create(
            dossier=self.dossier_1,
            doc_type=self.doc_type_1,
            doc_number="OTHER-DOC",
            doc_name="Other User Doc",
            file_path="archive/other.pdf",
            file_size_kb=150,
            status=DocumentStatus.DRAFT,
            created_by=other_user,
        )

        # Attempt to delete as the original data_entry (not the owner)
        self.client.force_authenticate(user=self.data_entry)
        res = self.client.post(f"/api/documents/{other_doc.id}/soft-delete/", {}, format="json")
        # Should get 403 or 404 (permission denied or not found due to queryset filtering)
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])
        # Verify document still exists
        self.assertTrue(Document.objects.filter(id=other_doc.id, is_deleted=False).exists())

    def test_data_entry_cannot_update_others_document(self):
        """Data entry cannot update documents created by other users (Req 3 isolation)."""
        other_user = User.objects.create_user(username="other_entry2", password="pass12345", role=UserRole.DATA_ENTRY)
        other_doc = Document.objects.create(
            dossier=self.dossier_1,
            doc_type=self.doc_type_1,
            doc_number="OTHER-DOC-2",
            doc_name="Other User Doc 2",
            file_path="archive/other2.pdf",
            file_size_kb=150,
            status=DocumentStatus.DRAFT,
            created_by=other_user,
        )

        payload = {
            "doc_type": self.doc_type_1.id,
            "doc_number": "HIJACKED-DOC",
            "doc_name": "Hijacked Name",
            "file_path": "archive/hijacked.pdf",
            "file_size_kb": 300,
            "mime_type": "application/pdf"
        }

        # Attempt to update as the original data_entry (not the owner)
        self.client.force_authenticate(user=self.data_entry)
        res = self.client.put(f"/api/documents/{other_doc.id}/", payload, format="json")
        # Should get 403 or 404 (permission denied or not found due to queryset filtering)
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])
        # Verify document was not modified
        other_doc.refresh_from_db()
        self.assertEqual(other_doc.doc_number, "OTHER-DOC-2")

    def test_replace_own_draft_file_succeeds(self):
        document = self.create_document_with_stored_file(status_value=DocumentStatus.DRAFT)
        old_updated_at = document.updated_at
        old_file_path = document.file_path

        response = self.client.post(
            f"/api/documents/{document.id}/replace-file/",
            {"file": self.make_uploaded_pdf(name="replacement-draft.pdf", size_kb=220)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        document.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.DRAFT)
        self.assertNotEqual(document.file_path, old_file_path)
        self.assertEqual(document.file_size_kb, 220)
        self.assertEqual(document.mime_type, "application/pdf")
        self.assertGreater(document.updated_at, old_updated_at)
        self.assertStoredFileExists(document.file_path)

    def test_replace_own_rejected_file_succeeds(self):
        document = self.create_document_with_stored_file(
            status_value=DocumentStatus.REJECTED,
            rejection_reason="Initial rejection reason",
        )
        old_file_path = document.file_path

        response = self.client.post(
            f"/api/documents/{document.id}/replace-file/",
            {"file": self.make_uploaded_pdf(name="replacement-rejected.pdf", size_kb=240)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        document.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.REJECTED)
        self.assertEqual(document.rejection_reason, "Initial rejection reason")
        self.assertNotEqual(document.file_path, old_file_path)
        self.assertEqual(document.file_size_kb, 240)
        self.assertStoredFileExists(document.file_path)

    def test_replace_pending_file_fails(self):
        document = self.create_document_with_stored_file(status_value=DocumentStatus.PENDING)
        old_file_path = document.file_path

        response = self.client.post(
            f"/api/documents/{document.id}/replace-file/",
            {"file": self.make_uploaded_pdf(name="replacement-pending.pdf", size_kb=220)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "Document file can only be replaced when status is draft or rejected.")
        document.refresh_from_db()
        self.assertEqual(document.file_path, old_file_path)
        self.assertStoredFileExists(old_file_path)

    def test_replace_approved_file_fails(self):
        document = self.create_document_with_stored_file(status_value=DocumentStatus.APPROVED)
        old_file_path = document.file_path

        response = self.client.post(
            f"/api/documents/{document.id}/replace-file/",
            {"file": self.make_uploaded_pdf(name="replacement-approved.pdf", size_kb=220)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "Document file can only be replaced when status is draft or rejected.")
        document.refresh_from_db()
        self.assertEqual(document.file_path, old_file_path)
        self.assertStoredFileExists(old_file_path)

    def test_replace_other_users_file_fails(self):
        other_user = User.objects.create_user(username="replace_other", password="pass12345", role=UserRole.DATA_ENTRY)
        document = self.create_document_with_stored_file(
            status_value=DocumentStatus.DRAFT,
            created_by=other_user,
        )

        response = self.client.post(
            f"/api/documents/{document.id}/replace-file/",
            {"file": self.make_uploaded_pdf(name="replacement-other.pdf", size_kb=220)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_replace_non_pdf_fails(self):
        document = self.create_document_with_stored_file(status_value=DocumentStatus.DRAFT)
        old_file_path = document.file_path

        response = self.client.post(
            f"/api/documents/{document.id}/replace-file/",
            {
                "file": self.make_uploaded_pdf(
                    name="replacement.txt",
                    size_kb=220,
                    content_type="text/plain",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)
        document.refresh_from_db()
        self.assertEqual(document.file_path, old_file_path)
        self.assertStoredFileExists(old_file_path)

    def test_replace_file_creates_audit_log_and_removes_old_file(self):
        document = self.create_document_with_stored_file(status_value=DocumentStatus.DRAFT)
        old_file_path = document.file_path
        old_full_path = Path(settings.MEDIA_ROOT) / old_file_path

        response = self.client.post(
            f"/api/documents/{document.id}/replace-file/",
            {"file": self.make_uploaded_pdf(name="replacement-audit.pdf", size_kb=260)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        document.refresh_from_db()
        audit_log = AuditLog.objects.get(action=AuditAction.REPLACE_FILE, entity_id=document.id)
        self.assertEqual(audit_log.old_values["file_path"], old_file_path)
        self.assertEqual(audit_log.old_values["status"], DocumentStatus.DRAFT)
        self.assertEqual(audit_log.new_values["file_path"], document.file_path)
        self.assertEqual(audit_log.new_values["file_size_kb"], 260)
        self.assertEqual(audit_log.new_values["status"], DocumentStatus.DRAFT)
        self.assertFalse(old_full_path.exists())
        self.assertStoredFileExists(document.file_path)


class DocumentFileAccessApiTests(TemporaryMediaRootMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="file_admin", password="pass12345", role=UserRole.ADMIN)
        self.data_entry = User.objects.create_user(username="file_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.other_data_entry = User.objects.create_user(
            username="file_entry_other",
            password="pass12345",
            role=UserRole.DATA_ENTRY,
        )
        self.auditor = User.objects.create_user(username="file_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.other_auditor = User.objects.create_user(username="file_auditor_other", password="pass12345", role=UserRole.AUDITOR)
        self.reader = User.objects.create_user(username="file_reader", password="pass12345", role=UserRole.READER)

        self.doc_type = DocumentType.objects.create(
            name="File Access Type",
            slug="file-access-type",
            group_name="core",
            display_order=1,
            is_active=True,
        )

        self.dossier = Dossier.objects.create(
            file_number="DOS-FILE-001",
            full_name="File Access User",
            national_id="N-FILE-001",
            personal_id="P-FILE-001",
            room_number="1",
            column_number="2",
            shelf_number="3",
            created_by=self.data_entry,
        )
        self.other_dossier = Dossier.objects.create(
            file_number="DOS-FILE-002",
            full_name="Other File User",
            national_id="N-FILE-002",
            personal_id="P-FILE-002",
            room_number="4",
            column_number="5",
            shelf_number="6",
            created_by=self.other_data_entry,
        )

    def create_document_with_file(self, *, created_by, dossier, status_value, name):
        relative_path = f"uploads/dossier_{dossier.id}/{name}.pdf"
        self.write_stored_pdf(relative_path)
        return Document.objects.create(
            dossier=dossier,
            doc_type=self.doc_type,
            doc_number=f"DOC-{name.upper()}",
            doc_name=f"Document {name}",
            file_path=relative_path,
            file_size_kb=120,
            mime_type="application/pdf",
            status=status_value,
            created_by=created_by,
        )

    def test_data_entry_can_access_own_document_file(self):
        document = self.create_document_with_file(
            created_by=self.data_entry,
            dossier=self.dossier,
            status_value=DocumentStatus.DRAFT,
            name="owner-access",
        )

        self.client.force_authenticate(user=self.data_entry)
        response = self.client.get(f"/api/documents/{document.id}/file/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        first_chunk = next(response.streaming_content)
        self.assertTrue(first_chunk.startswith(b"%PDF"))

    def test_data_entry_cannot_access_other_users_document_file(self):
        document = self.create_document_with_file(
            created_by=self.other_data_entry,
            dossier=self.other_dossier,
            status_value=DocumentStatus.APPROVED,
            name="other-owner",
        )

        self.client.force_authenticate(user=self.data_entry)
        response = self.client.get(f"/api/documents/{document.id}/file/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_reader_can_access_only_approved_document_file(self):
        approved_document = self.create_document_with_file(
            created_by=self.data_entry,
            dossier=self.dossier,
            status_value=DocumentStatus.APPROVED,
            name="reader-approved",
        )
        pending_document = self.create_document_with_file(
            created_by=self.data_entry,
            dossier=self.dossier,
            status_value=DocumentStatus.PENDING,
            name="reader-pending",
        )

        self.client.force_authenticate(user=self.reader)

        approved_response = self.client.get(f"/api/documents/{approved_document.id}/file/")
        self.assertEqual(approved_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approved_response["Content-Type"], "application/pdf")

        pending_response = self.client.get(f"/api/documents/{pending_document.id}/file/")
        self.assertEqual(pending_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_auditor_can_access_scoped_pending_rejected_and_approved_document_files(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        documents = [
            self.create_document_with_file(
                created_by=self.data_entry,
                dossier=self.dossier,
                status_value=DocumentStatus.PENDING,
                name="auditor-pending",
            ),
            self.create_document_with_file(
                created_by=self.data_entry,
                dossier=self.dossier,
                status_value=DocumentStatus.REJECTED,
                name="auditor-rejected",
            ),
            self.create_document_with_file(
                created_by=self.data_entry,
                dossier=self.dossier,
                status_value=DocumentStatus.APPROVED,
                name="auditor-approved",
            ),
        ]

        self.client.force_authenticate(user=self.auditor)
        for document in documents:
            response = self.client.get(f"/api/documents/{document.id}/file/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response["Content-Type"], "application/pdf")

    def test_auditor_cannot_access_scoped_draft_document_file(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        draft_document = self.create_document_with_file(
            created_by=self.data_entry,
            dossier=self.dossier,
            status_value=DocumentStatus.DRAFT,
            name="auditor-draft",
        )

        self.client.force_authenticate(user=self.auditor)
        response = self.client.get(f"/api/documents/{draft_document.id}/file/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_auditor_cannot_access_document_file_outside_assignment(self):
        self.other_data_entry.assigned_auditor = self.other_auditor
        self.other_data_entry.save()
        document = self.create_document_with_file(
            created_by=self.other_data_entry,
            dossier=self.other_dossier,
            status_value=DocumentStatus.PENDING,
            name="auditor-outside",
        )

        self.client.force_authenticate(user=self.auditor)
        response = self.client.get(f"/api/documents/{document.id}/file/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_physical_file_returns_404(self):
        document = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="DOC-MISSING",
            doc_name="Missing File",
            file_path=f"uploads/dossier_{self.dossier.id}/missing-file.pdf",
            file_size_kb=120,
            mime_type="application/pdf",
            status=DocumentStatus.DRAFT,
            created_by=self.data_entry,
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f"/api/documents/{document.id}/file/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class UserAssignedAuditorLinkageTests(APITestCase):
    """
    Step b: Verify data_entry ↔ assigned_auditor linkage model behavior.
    Tests model field, validation, and minimal serializer exposure.
    """

    def setUp(self):
        self.admin = User.objects.create_user(username="link_admin", password="pass12345", role=UserRole.ADMIN)
        self.auditor = User.objects.create_user(username="link_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.auditor2 = User.objects.create_user(username="link_auditor2", password="pass12345", role=UserRole.AUDITOR)
        self.data_entry = User.objects.create_user(username="link_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.reader = User.objects.create_user(username="link_reader", password="pass12345", role=UserRole.READER)

    def test_data_entry_can_have_assigned_auditor(self):
        """Data entry user can be linked to an auditor."""
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.full_clean()
        self.data_entry.save()
        self.data_entry.refresh_from_db()
        self.assertEqual(self.data_entry.assigned_auditor_id, self.auditor.id)

    def test_data_entry_cannot_be_assigned_to_non_auditor(self):
        self.data_entry.assigned_auditor = self.admin
        with self.assertRaises(ValidationError) as ctx:
            self.data_entry.full_clean()
        self.assertIn("assigned_auditor", ctx.exception.message_dict)

    def test_auditor_cannot_have_assigned_auditor(self):
        """Auditor user cannot have an assigned auditor (validation error)."""
        self.auditor.assigned_auditor = self.auditor2
        with self.assertRaises(ValidationError) as ctx:
            self.auditor.full_clean()
        self.assertIn("assigned_auditor", ctx.exception.message_dict)

    def test_admin_cannot_have_assigned_auditor(self):
        """Admin user cannot have an assigned auditor (validation error)."""
        self.admin.assigned_auditor = self.auditor
        with self.assertRaises(ValidationError) as ctx:
            self.admin.full_clean()
        self.assertIn("assigned_auditor", ctx.exception.message_dict)

    def test_reader_cannot_have_assigned_auditor(self):
        """Reader user cannot have an assigned auditor (validation error)."""
        self.reader.assigned_auditor = self.auditor
        with self.assertRaises(ValidationError) as ctx:
            self.reader.full_clean()
        self.assertIn("assigned_auditor", ctx.exception.message_dict)

    def test_data_entry_can_clear_assigned_auditor(self):
        """Data entry user can have assigned_auditor set to null."""
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self.data_entry.assigned_auditor = None
        self.data_entry.full_clean()
        self.data_entry.save()
        self.data_entry.refresh_from_db()
        self.assertIsNone(self.data_entry.assigned_auditor_id)

    def test_auditor_reverse_relation_shows_assigned_data_entries(self):
        """Auditor can see their assigned data entries via reverse relation."""
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        assigned_ids = list(self.auditor.assigned_data_entries.values_list("id", flat=True))
        self.assertIn(self.data_entry.id, assigned_ids)

    def test_me_serializer_includes_assigned_auditor_id(self):
        """MeSerializer exposes assigned_auditor_id for data_entry users."""
        from core.serializers import MeSerializer
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        serializer = MeSerializer(self.data_entry)
        self.assertEqual(serializer.data["assigned_auditor_id"], self.auditor.id)

    def test_me_serializer_assigned_auditor_id_null_when_not_set(self):
        """MeSerializer returns null for assigned_auditor_id when not set."""
        from core.serializers import MeSerializer
        serializer = MeSerializer(self.data_entry)
        self.assertIsNone(serializer.data["assigned_auditor_id"])

    def test_me_serializer_only_accepts_auditor_ids(self):
        """MeSerializer validation only accepts auditor user IDs."""
        from core.serializers import MeSerializer
        # Attempt to assign a non-auditor (admin) as assigned_auditor
        data = {"assigned_auditor_id": self.admin.id}
        serializer = MeSerializer(self.data_entry, data=data, partial=True)
        # Should fail validation because queryset is limited to auditors
        self.assertFalse(serializer.is_valid())
        self.assertIn("assigned_auditor_id", serializer.errors)


class SeedLookupsCommandTests(APITestCase):
    """Tests for the seed_lookups management command."""

    def _run_seed(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command("seed_lookups", stdout=out)
        return out.getvalue()

    def test_seed_creates_governorates(self):
        output = self._run_seed()
        count = Governorate.objects.filter(is_active=True).count()
        self.assertGreaterEqual(count, 14)
        self.assertIn("Governorates", output)

    def test_seed_creates_document_types(self):
        output = self._run_seed()
        count = DocumentType.objects.filter(is_active=True).count()
        self.assertEqual(count, 59)
        self.assertIn("Document types", output)

    def test_seed_is_idempotent_for_governorates(self):
        self._run_seed()
        count_after_first = Governorate.objects.count()
        self._run_seed()
        count_after_second = Governorate.objects.count()
        self.assertEqual(count_after_first, count_after_second)

    def test_seed_is_idempotent_for_document_types(self):
        self._run_seed()
        count_after_first = DocumentType.objects.count()
        self._run_seed()
        count_after_second = DocumentType.objects.count()
        self.assertEqual(count_after_first, count_after_second)

    def test_seeded_governorates_visible_via_api(self):
        self._run_seed()
        admin = User.objects.create_user(username="seed_admin", password="pass12345", role=UserRole.ADMIN)
        self.client.force_authenticate(user=admin)
        response = self.client.get("/api/governorates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 14)

    def test_seeded_document_types_visible_via_api(self):
        self._run_seed()
        admin = User.objects.create_user(username="seed_admin2", password="pass12345", role=UserRole.ADMIN)
        self.client.force_authenticate(user=admin)
        response = self.client.get("/api/document-types/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 59)

    def test_seed_keeps_existing_custom_document_types_active(self):
        extra_type = DocumentType.objects.create(
            name="نوع مخصص",
            slug="custom-type",
            group_name="custom",
            display_order=999,
            is_active=True,
        )

        self._run_seed()
        extra_type.refresh_from_db()

        self.assertTrue(extra_type.is_active)

    def obsolete_document_types_api_hides_inactive_entries(self):
        active_type = DocumentType.objects.create(
            name="نوع نشط",
            slug="active-type",
            group_name="custom",
            display_order=999,
            is_active=True,
        )
        inactive_type = DocumentType.objects.create(
            name="نوع غير نشط",
            slug="inactive-type",
            group_name="custom",
            display_order=1000,
            is_active=False,
        )
        admin = User.objects.create_user(username="seed_admin3", password="pass12345", role=UserRole.ADMIN)
        self.client.force_authenticate(user=admin)

        response = self.client.get("/api/document-types/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [item["id"] for item in response.data]
        returned_names = [item["name"] for item in response.data]
        self.assertIn(active_type.id, returned_ids)
        self.assertNotIn(inactive_type.id, returned_ids)
        self.assertIn("عقد", returned_names)
        self.assertNotIn("نوع غير نشط", returned_names)

    def obsolete_document_types_api_uses_approved_arabic_display_names(self):
        approved_type = DocumentType.objects.create(
            name="Contract",
            slug="contract",
            group_name="junk",
            display_order=999,
            is_active=True,
        )
        admin = User.objects.create_user(username="seed_admin4", password="pass12345", role=UserRole.ADMIN)
        self.client.force_authenticate(user=admin)

        response = self.client.get("/api/document-types/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contract_entry = next((item for item in response.data if item["id"] == approved_type.id), None)
        self.assertIsNotNone(contract_entry)
        self.assertEqual(contract_entry["name"], "عقد")
class SeededDocumentTypeLookupApiTests(APITestCase):
    def test_document_types_api_hides_inactive_entries_cleanly(self):
        active_type = DocumentType.objects.create(
            name="نوع نشط فعلي",
            slug="active-real",
            group_name="custom",
            display_order=1001,
            is_active=True,
        )
        inactive_type = DocumentType.objects.create(
            name="نوع مخفي",
            slug="inactive-hidden",
            group_name="custom",
            display_order=1002,
            is_active=False,
        )
        admin = User.objects.create_user(username="seed_admin_visible", password="pass12345", role=UserRole.ADMIN)
        self.client.force_authenticate(user=admin)

        response = self.client.get("/api/document-types/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [item["id"] for item in response.data]
        returned_names = [item["name"] for item in response.data]
        self.assertIn(active_type.id, returned_ids)
        self.assertNotIn(inactive_type.id, returned_ids)
        self.assertIn("نوع نشط فعلي", returned_names)
        self.assertNotIn("نوع مخفي", returned_names)

    def test_document_types_api_uses_database_display_names(self):
        custom_type = DocumentType.objects.create(
            name="اسم من قاعدة البيانات",
            slug="db-display-name",
            group_name="custom",
            display_order=1003,
            is_active=True,
        )
        admin = User.objects.create_user(username="seed_admin_db_name", password="pass12345", role=UserRole.ADMIN)
        self.client.force_authenticate(user=admin)

        response = self.client.get("/api/document-types/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        custom_entry = next((item for item in response.data if item["id"] == custom_type.id), None)
        self.assertIsNotNone(custom_entry)
        self.assertEqual(custom_entry["name"], "اسم من قاعدة البيانات")
        self.assertEqual(set(custom_entry.keys()), {"id", "name"})


class DossierDetailDocumentVisibilityTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="vis_admin", password="pass12345", role=UserRole.ADMIN)
        self.data_entry = User.objects.create_user(username="vis_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.other_data_entry = User.objects.create_user(username="vis_entry_other", password="pass12345", role=UserRole.DATA_ENTRY)
        self.auditor = User.objects.create_user(username="vis_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.other_auditor = User.objects.create_user(username="vis_auditor_other", password="pass12345", role=UserRole.AUDITOR)
        self.reader = User.objects.create_user(username="vis_reader", password="pass12345", role=UserRole.READER)
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self.other_data_entry.assigned_auditor = self.other_auditor
        self.other_data_entry.save()

        self.doc_type = DocumentType.objects.create(
            name="Type V",
            slug="type-v",
            group_name="core",
            display_order=1,
            is_active=True,
        )
        self.dossier = Dossier.objects.create(
            file_number="VIS-001",
            full_name="Visibility Test",
            national_id="VIS-N1",
            personal_id="VIS-P1",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry,
        )
        self.other_dossier = Dossier.objects.create(
            file_number="VIS-002",
            full_name="Other Visibility Test",
            national_id="VIS-N2",
            personal_id="VIS-P2",
            room_number="2",
            column_number="2",
            shelf_number="2",
            created_by=self.other_data_entry,
        )

        def _doc(number, stat, deleted=False):
            return Document.objects.create(
                dossier=self.dossier,
                doc_type=self.doc_type,
                doc_number=number,
                doc_name=f"Doc {number}",
                file_path=f"archive/vis/{number}.pdf",
                file_size_kb=100,
                mime_type="application/pdf",
                status=stat,
                is_deleted=deleted,
                created_by=self.data_entry,
            )

        self.doc_draft = _doc("VIS-DRF", DocumentStatus.DRAFT)
        self.doc_pending = _doc("VIS-PEN", DocumentStatus.PENDING)
        self.doc_approved = _doc("VIS-APP", DocumentStatus.APPROVED)
        self.doc_rejected = _doc("VIS-REJ", DocumentStatus.REJECTED)
        self.doc_deleted = _doc("VIS-DEL", DocumentStatus.APPROVED, deleted=True)

        self.url = f"/api/dossiers/{self.dossier.id}/"
        self.other_url = f"/api/dossiers/{self.other_dossier.id}/"

    def _ids(self, response):
        return {doc["id"] for doc in response.data["documents"]}

    # ── reader ──────────────────────────────────────────────────────────────
    def test_reader_sees_only_approved(self):
        self.client.force_authenticate(user=self.reader)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = self._ids(response)
        self.assertIn(self.doc_approved.id, ids)
        self.assertNotIn(self.doc_draft.id, ids)
        self.assertNotIn(self.doc_pending.id, ids)
        self.assertNotIn(self.doc_rejected.id, ids)
        self.assertNotIn(self.doc_deleted.id, ids)
        self.assertEqual(len(ids), 1)

    # ── auditor ─────────────────────────────────────────────────────────────
    def test_auditor_sees_scoped_pending_rejected_and_approved(self):
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = self._ids(response)
        self.assertIn(self.doc_pending.id, ids)
        self.assertIn(self.doc_approved.id, ids)
        self.assertIn(self.doc_rejected.id, ids)
        self.assertNotIn(self.doc_draft.id, ids)
        self.assertNotIn(self.doc_deleted.id, ids)
        self.assertEqual(len(ids), 3)

    def test_auditor_gets_404_for_unassigned_dossier(self):
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get(self.other_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── admin ────────────────────────────────────────────────────────────────
    def test_admin_sees_all_non_deleted(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = self._ids(response)
        self.assertIn(self.doc_draft.id, ids)
        self.assertIn(self.doc_pending.id, ids)
        self.assertIn(self.doc_approved.id, ids)
        self.assertIn(self.doc_rejected.id, ids)
        self.assertNotIn(self.doc_deleted.id, ids)
        self.assertEqual(len(ids), 4)

    # ── data_entry ───────────────────────────────────────────────────────────
    def test_data_entry_gets_404_for_others_dossier(self):
        self.client.force_authenticate(user=self.data_entry)
        response = self.client.get(self.other_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminUserManagementApiTests(APITestCase):
    """
    Step c: Admin-only user management endpoint tests.
    Verify CRUD operations and assigned_auditor assignment work correctly.
    """

    def setUp(self):
        self.admin = User.objects.create_user(username="um_admin", password="pass12345", role=UserRole.ADMIN)
        self.auditor = User.objects.create_user(username="um_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.auditor2 = User.objects.create_user(username="um_auditor2", password="pass12345", role=UserRole.AUDITOR)
        self.data_entry = User.objects.create_user(username="um_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.reader = User.objects.create_user(username="um_reader", password="pass12345", role=UserRole.READER)
        self.doc_type = DocumentType.objects.create(
            name="User Management Doc",
            slug="user-management-doc",
            group_name="user-management",
            display_order=1,
            is_active=True,
        )

        self.client.force_authenticate(user=self.admin)

    def _build_user_update_payload(self, user, **overrides):
        payload = {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
        }
        if user.role == UserRole.DATA_ENTRY and user.assigned_auditor_id:
            payload["assigned_auditor_id"] = user.assigned_auditor_id
        payload.update(overrides)
        if payload.get("role") != UserRole.DATA_ENTRY:
            payload["assigned_auditor_id"] = None
        return payload

    def _create_owned_document(self, status, *, is_deleted=False):
        if not hasattr(self, "dossier"):
            self.dossier = Dossier.objects.create(
                file_number="UM-001",
                full_name="User Management Dossier",
                national_id="UMNAT001",
                personal_id="UMPER001",
                room_number="101",
                column_number="A",
                shelf_number="1",
                created_by=self.data_entry,
            )
        next_index = Document.objects.count() + 1
        return Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number=f"UM-DOC-{next_index}",
            doc_name=f"User Management Document {next_index}",
            file_path=f"archive/user-management-{next_index}.pdf",
            file_size_kb=120,
            mime_type="application/pdf",
            status=status,
            rejection_reason="سبب رفض تجريبي" if status == DocumentStatus.REJECTED else None,
            created_by=self.data_entry,
            is_deleted=is_deleted,
        )

    def test_admin_can_list_users(self):
        """Admin can list all users via /api/users/."""
        response = self.client.get("/api/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 5)  # all users created in setUp

    def test_user_management_response_includes_human_readable_assignment_fields(self):
        self.auditor.first_name = "Audit"
        self.auditor.last_name = "Owner"
        self.auditor.save()
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        response = self.client.get(f"/api/users/{self.data_entry.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["assigned_auditor_id"], self.auditor.id)
        self.assertEqual(response.data["assigned_auditor_username"], self.auditor.username)
        self.assertEqual(response.data["assigned_auditor"]["id"], self.auditor.id)
        self.assertEqual(response.data["assigned_auditor"]["username"], self.auditor.username)
        self.assertEqual(response.data["assigned_auditor"]["full_name"], "Audit Owner")

    def test_non_admin_cannot_list_users(self):
        """Non-admin users are denied access to user list."""
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get("/api/users/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_user(self):
        """Admin can create new users via POST /api/users/."""
        payload = {
            "username": "new_reader",
            "password": "newpass123",
            "first_name": "New",
            "last_name": "Reader",
            "email": "new@example.com",
            "role": UserRole.READER,
            "is_active": True,
        }
        response = self.client.post("/api/users/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["username"], "new_reader")
        self.assertEqual(response.data["role"], UserRole.READER)

    def test_admin_cannot_create_data_entry_without_assigned_auditor(self):
        payload = {
            "username": "entry_without_auditor",
            "password": "newpass123",
            "first_name": "No",
            "last_name": "Auditor",
            "email": "noauditor@example.com",
            "role": UserRole.DATA_ENTRY,
            "is_active": True,
        }
        response = self.client.post("/api/users/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assigned_auditor_id", response.data)

    def test_admin_can_create_data_entry_with_assigned_auditor(self):
        """Admin can create data_entry user with assigned_auditor."""
        self.auditor.first_name = "Scope"
        self.auditor.last_name = "Reviewer"
        self.auditor.save()

        payload = {
            "username": "new_entry_with_auditor",
            "password": "newpass123",
            "first_name": "New",
            "last_name": "Entry",
            "email": "new2@example.com",
            "role": UserRole.DATA_ENTRY,
            "is_active": True,
            "assigned_auditor_id": self.auditor.id,
        }
        response = self.client.post("/api/users/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["assigned_auditor_id"], self.auditor.id)
        self.assertEqual(response.data["assigned_auditor_username"], self.auditor.username)
        self.assertEqual(response.data["assigned_auditor"]["full_name"], "Scope Reviewer")

    def test_admin_cannot_assign_non_auditor_as_assigned_auditor(self):
        payload = {
            "username": "entry_with_reader_assignment",
            "password": "newpass123",
            "role": UserRole.DATA_ENTRY,
            "is_active": True,
            "assigned_auditor_id": self.reader.id,
        }
        response = self.client.post("/api/users/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assigned_auditor_id", response.data)

    def test_admin_cannot_create_non_data_entry_with_assigned_auditor(self):
        """Admin cannot assign auditor to non-data_entry user."""
        payload = {
            "username": "new_reader_with_auditor",
            "password": "newpass123",
            "first_name": "New",
            "last_name": "Reader",
            "email": "new3@example.com",
            "role": UserRole.READER,
            "is_active": True,
            "assigned_auditor_id": self.auditor.id,
        }
        response = self.client.post("/api/users/", payload, format="json")
        # Should succeed but assigned_auditor_id should be ignored or cause validation error
        # Based on serializer validation, it should be cleared
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["assigned_auditor_id"])

    def test_admin_can_update_user_role(self):
        """Admin can update user role via PUT /api/users/{id}/."""
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        payload = {
            "username": self.data_entry.username,
            "first_name": "Updated",
            "last_name": "Name",
            "email": self.data_entry.email,
            "role": UserRole.AUDITOR,  # Change role
            "is_active": True,
        }
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], UserRole.AUDITOR)
        self.assertIsNone(response.data["assigned_auditor_id"])
        self.data_entry.refresh_from_db()
        self.assertIsNone(self.data_entry.assigned_auditor)

    def test_changing_data_entry_with_draft_document_fails(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self._create_owned_document(DocumentStatus.DRAFT)

        payload = self._build_user_update_payload(self.data_entry, role=UserRole.READER)
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["role"][0],
            "لا يمكن تغيير دور هذا المستخدم لأنه يملك وثائق غير منتهية (مسودة / مرفوضة / قيد المراجعة).",
        )

    def test_changing_data_entry_with_rejected_document_fails(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self._create_owned_document(DocumentStatus.REJECTED)

        payload = self._build_user_update_payload(self.data_entry, role=UserRole.READER)
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["role"][0],
            "لا يمكن تغيير دور هذا المستخدم لأنه يملك وثائق غير منتهية (مسودة / مرفوضة / قيد المراجعة).",
        )

    def test_changing_data_entry_with_pending_document_fails(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self._create_owned_document(DocumentStatus.PENDING)

        payload = self._build_user_update_payload(self.data_entry, role=UserRole.READER)
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["role"][0],
            "لا يمكن تغيير دور هذا المستخدم لأنه يملك وثائق غير منتهية (مسودة / مرفوضة / قيد المراجعة).",
        )

    def test_changing_data_entry_with_only_approved_documents_succeeds(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self._create_owned_document(DocumentStatus.APPROVED)

        payload = self._build_user_update_payload(self.data_entry, role=UserRole.READER)
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], UserRole.READER)
        self.assertIsNone(response.data["assigned_auditor_id"])

    def test_changing_auditor_with_assigned_data_entry_users_fails(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        payload = self._build_user_update_payload(self.auditor, role=UserRole.READER)
        response = self.client.put(f"/api/users/{self.auditor.id}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["role"][0],
            "لا يمكن تغيير دور هذا المدقق لأنه ما زال مرتبطًا بمدخلي بيانات.",
        )

    def test_changing_auditor_with_no_assigned_data_entry_users_succeeds(self):
        payload = self._build_user_update_payload(self.auditor2, role=UserRole.READER)
        response = self.client.put(f"/api/users/{self.auditor2.id}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], UserRole.READER)

    def test_admin_can_assign_auditor_to_data_entry(self):
        """Admin can assign auditor to existing data_entry user."""
        payload = {
            "username": self.data_entry.username,
            "first_name": self.data_entry.first_name,
            "last_name": self.data_entry.last_name,
            "email": self.data_entry.email,
            "role": UserRole.DATA_ENTRY,
            "is_active": True,
            "assigned_auditor_id": self.auditor.id,
        }
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["assigned_auditor_id"], self.auditor.id)

    def test_admin_can_change_assigned_auditor_for_existing_data_entry(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        payload = {
            "username": self.data_entry.username,
            "first_name": self.data_entry.first_name,
            "last_name": self.data_entry.last_name,
            "email": self.data_entry.email,
            "role": UserRole.DATA_ENTRY,
            "is_active": True,
            "assigned_auditor_id": self.auditor2.id,
        }
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["assigned_auditor_id"], self.auditor2.id)
        self.assertEqual(response.data["assigned_auditor_username"], self.auditor2.username)
        self.data_entry.refresh_from_db()
        self.assertEqual(self.data_entry.assigned_auditor_id, self.auditor2.id)

    def test_admin_cannot_remove_assigned_auditor_from_data_entry(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        payload = {
            "username": self.data_entry.username,
            "first_name": self.data_entry.first_name,
            "last_name": self.data_entry.last_name,
            "email": self.data_entry.email,
            "role": UserRole.DATA_ENTRY,
            "is_active": True,
            "assigned_auditor_id": None,
        }
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assigned_auditor_id", response.data)

    def test_admin_can_filter_users_by_role(self):
        """Admin can filter users by role query parameter."""
        response = self.client.get(f"/api/users/?role={UserRole.AUDITOR}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)  # um_auditor, um_auditor2

    def test_admin_can_filter_users_by_assigned_auditor(self):
        """Admin can filter users by assigned_auditor query parameter."""
        # Assign an auditor first
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        response = self.client.get(f"/api/users/?assigned_auditor={self.auditor.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.data_entry.id)

    def test_admin_can_search_users(self):
        """Admin can search users by username, first_name, last_name, email."""
        response = self.client.get("/api/users/?search=um_entry")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["username"], "um_entry")

    def test_admin_can_delete_user(self):
        """Admin can delete user via DELETE /api/users/{id}/."""
        response = self.client.delete(f"/api/users/{self.data_entry.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=self.data_entry.id).exists())

    def test_non_admin_cannot_create_user(self):
        """Non-admin users cannot create users."""
        self.client.force_authenticate(user=self.auditor)
        payload = {
            "username": "hacker",
            "password": "hack123",
            "role": UserRole.ADMIN,
        }
        response = self.client.post("/api/users/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_update_user(self):
        """Non-admin users cannot update users."""
        self.client.force_authenticate(user=self.reader)
        payload = {
            "username": self.data_entry.username,
            "first_name": "Hacked",
            "last_name": "Name",
            "email": self.data_entry.email,
            "role": UserRole.DATA_ENTRY,
            "is_active": True,
        }
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_optionally_change_password_on_edit(self):
        payload = {
            "username": self.reader.username,
            "first_name": self.reader.first_name,
            "last_name": self.reader.last_name,
            "email": self.reader.email,
            "role": self.reader.role,
            "is_active": self.reader.is_active,
            "password": "new-reader-pass-123",
        }
        response = self.client.put(f"/api/users/{self.reader.id}/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.check_password("new-reader-pass-123"))

    def test_updating_user_without_changing_role_still_succeeds(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self._create_owned_document(DocumentStatus.DRAFT)

        payload = self._build_user_update_payload(
            self.data_entry,
            first_name="Updated",
            role=UserRole.DATA_ENTRY,
            assigned_auditor_id=self.auditor.id,
        )
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], UserRole.DATA_ENTRY)
        self.assertEqual(response.data["assigned_auditor_id"], self.auditor.id)
        self.assertEqual(response.data["full_name"], "Updated")

    def test_role_change_failure_message_is_returned_from_api(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self._create_owned_document(DocumentStatus.PENDING)

        payload = self._build_user_update_payload(self.data_entry, role=UserRole.ADMIN)
        response = self.client.put(f"/api/users/{self.data_entry.id}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)
        self.assertEqual(
            response.data["role"][0],
            "لا يمكن تغيير دور هذا المستخدم لأنه يملك وثائق غير منتهية (مسودة / مرفوضة / قيد المراجعة).",
        )

    def test_password_is_write_only(self):
        """Password field is write-only and not returned in response."""
        payload = {
            "username": "password_test",
            "password": "secret123",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "role": UserRole.READER,
            "is_active": True,
        }
        response = self.client.post("/api/users/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data)


class AdminApprovalIndicatorTests(APITestCase):
    """
    Step d: Verify admin approval indicator for documents in auditor scope.
    Tests the is_approved_by_admin field behavior.
    """

    def setUp(self):
        self.admin = User.objects.create_user(username="ap_admin", password="pass12345", role=UserRole.ADMIN)
        self.auditor = User.objects.create_user(username="ap_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.auditor2 = User.objects.create_user(username="ap_auditor2", password="pass12345", role=UserRole.AUDITOR)
        self.data_entry = User.objects.create_user(username="ap_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.reader = User.objects.create_user(username="ap_reader", password="pass12345", role=UserRole.READER)

        # Set up document type and dossier
        self.doc_type = DocumentType.objects.create(
            name="Test Doc",
            slug="test-doc",
            group_name="test",
            display_order=1,
            is_active=True,
        )
        self.dossier = Dossier.objects.create(
            file_number="AP-001",
            full_name="Test Dossier",
            national_id="12345678901",
            personal_id="PID001",
            room_number="101",
            column_number="A",
            shelf_number="1",
            created_by=self.data_entry,
        )

    def test_approved_by_assigned_auditor_is_not_flagged(self):
        """Document approved by assigned auditor should NOT have is_approved_by_admin=True."""
        # Link data_entry to auditor
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        # Create document and approve by the assigned auditor
        doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AP-001",
            doc_name="Test Doc 1",
            file_path="archive/test1.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            reviewed_by=self.auditor,  # Approved by assigned auditor
        )

        # Check serializer field
        from core.serializers import DocumentSummarySerializer
        serializer = DocumentSummarySerializer(doc)
        self.assertFalse(serializer.data["is_approved_by_admin"])
        self.assertEqual(serializer.data["reviewed_by_role"], UserRole.AUDITOR)
        self.assertEqual(serializer.data["reviewed_by_name"], self.auditor.username)
        self.assertEqual(serializer.data["status_display_label"], "معتمدة")

    def test_approved_by_admin_is_flagged_for_auditor_scope(self):
        """Document approved by admin should have is_approved_by_admin=True when data_entry has assigned auditor."""
        # Link data_entry to auditor
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        # Create document and approve by admin (not the assigned auditor)
        doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AP-002",
            doc_name="Test Doc 2",
            file_path="archive/test2.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            reviewed_by=self.admin,  # Approved by admin, not assigned auditor
        )

        # Check serializer field
        from core.serializers import DocumentSummarySerializer
        serializer = DocumentSummarySerializer(doc)
        self.assertTrue(serializer.data["is_approved_by_admin"])
        self.assertEqual(serializer.data["reviewed_by_role"], UserRole.ADMIN)
        self.assertEqual(serializer.data["reviewed_by_name"], self.admin.username)
        self.assertEqual(serializer.data["status_display_label"], "معتمدة من المدير")

    def test_approved_by_other_auditor_is_not_flagged(self):
        """Document approved by different auditor (not admin) should NOT have is_approved_by_admin=True."""
        # Link data_entry to auditor1
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        # Create document and approve by auditor2 (not the assigned auditor, not admin)
        doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AP-003",
            doc_name="Test Doc 3",
            file_path="archive/test3.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            reviewed_by=self.auditor2,  # Approved by different auditor (not admin)
        )

        # Check serializer field - only admin approval should be flagged
        from core.serializers import DocumentSummarySerializer
        serializer = DocumentSummarySerializer(doc)
        self.assertFalse(serializer.data["is_approved_by_admin"])
        self.assertEqual(serializer.data["status_display_label"], "معتمدة")

    def test_non_approved_document_is_not_flagged(self):
        """Non-approved documents should have is_approved_by_admin=False."""
        # Link data_entry to auditor
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        # Create pending document
        doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AP-004",
            doc_name="Test Doc 4",
            file_path="archive/test4.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.data_entry,
        )

        # Check serializer field
        from core.serializers import DocumentSummarySerializer
        serializer = DocumentSummarySerializer(doc)
        self.assertFalse(serializer.data["is_approved_by_admin"])
        self.assertEqual(serializer.data["status_display_label"], "قيد المراجعة")

    def test_no_assigned_auditor_still_shows_admin_approval(self):
        """Admin approval should be indicated even when no auditor assignment exists."""
        # data_entry has NO assigned auditor

        # Create document and approve by admin
        doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AP-005",
            doc_name="Test Doc 5",
            file_path="archive/test5.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            reviewed_by=self.admin,
        )

        # Check serializer field - approval origin depends on reviewer role only
        from core.serializers import DocumentSummarySerializer
        serializer = DocumentSummarySerializer(doc)
        self.assertTrue(serializer.data["is_approved_by_admin"])
        self.assertEqual(serializer.data["status_display_label"], "معتمدة من المدير")

    def test_rejected_by_admin_is_flagged_and_uses_manager_status_text(self):
        doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AP-005-REJ",
            doc_name="Rejected by Admin",
            file_path="archive/test5-rej.pdf",
            file_size_kb=100,
            status=DocumentStatus.REJECTED,
            created_by=self.data_entry,
            reviewed_by=self.admin,
            rejection_reason="Missing signature",
        )

        from core.serializers import DocumentSummarySerializer

        serializer = DocumentSummarySerializer(doc)
        self.assertTrue(serializer.data["is_rejected_by_admin"])
        self.assertEqual(serializer.data["status_display_label"], "مرفوضة من المدير")

    def test_rejected_by_auditor_keeps_normal_status_text(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AP-005-REJ-AUD",
            doc_name="Rejected by Auditor",
            file_path="archive/test5-rej-aud.pdf",
            file_size_kb=100,
            status=DocumentStatus.REJECTED,
            created_by=self.data_entry,
            reviewed_by=self.auditor,
            rejection_reason="Missing stamp",
        )

        from core.serializers import DocumentSummarySerializer

        serializer = DocumentSummarySerializer(doc)
        self.assertFalse(serializer.data["is_rejected_by_admin"])
        self.assertEqual(serializer.data["status_display_label"], "مرفوضة")

    def test_api_includes_indicator_for_auditor(self):
        """API response includes is_approved_by_admin field when auditor views documents."""
        # Link data_entry to auditor
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        # Create admin-approved document
        doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AP-006",
            doc_name="Test Doc 6",
            file_path="archive/test6.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            reviewed_by=self.admin,
        )

        # Auditor views document list
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Find our document in results
        doc_data = next((d for d in response.data["results"] if d["id"] == doc.id), None)
        self.assertIsNotNone(doc_data)
        self.assertIn("is_approved_by_admin", doc_data)
        self.assertTrue(doc_data["is_approved_by_admin"])
        self.assertEqual(doc_data["reviewed_by_role"], UserRole.ADMIN)
        self.assertEqual(doc_data["reviewed_by_name"], self.admin.username)
        self.assertEqual(doc_data["status_display_label"], "معتمدة من المدير")

    def test_document_detail_api_includes_reviewer_name_and_role_for_approved_document(self):
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AP-006-DETAIL",
            doc_name="Test Doc Detail",
            file_path="archive/test6-detail.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            reviewed_by=self.auditor,
        )

        self.client.force_authenticate(user=self.auditor)
        response = self.client.get(f"/api/documents/{doc.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["reviewed_by_role"], UserRole.AUDITOR)
        self.assertEqual(response.data["reviewed_by_name"], self.auditor.username)
        self.assertFalse(response.data["is_approved_by_admin"])
        self.assertEqual(response.data["status_display_label"], "معتمدة")

    def test_api_includes_indicator_for_reader(self):
        """API response includes is_approved_by_admin field when reader views documents."""
        # Link data_entry to auditor
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        # Create admin-approved document
        doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AP-007",
            doc_name="Test Doc 7",
            file_path="archive/test7.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            reviewed_by=self.admin,
        )

        # Reader views document list (readers see approved documents)
        self.client.force_authenticate(user=self.reader)
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Find our document in results
        doc_data = next((d for d in response.data["results"] if d["id"] == doc.id), None)
        self.assertIsNotNone(doc_data)
        self.assertIn("is_approved_by_admin", doc_data)
        self.assertEqual(doc_data["status_display_label"], "معتمدة من المدير")


class AuditorScopedDocumentVisibilityTests(APITestCase):
    """
    Step e1: Auditor scoped document visibility for document listing.
    Tests that auditor sees only documents from their assigned data_entry users
    with statuses: pending, rejected, approved (draft excluded).
    """

    def setUp(self):
        self.admin = User.objects.create_user(username="aud_vis_admin", password="pass12345", role=UserRole.ADMIN)
        self.auditor = User.objects.create_user(username="aud_vis_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.auditor2 = User.objects.create_user(username="aud_vis_auditor2", password="pass12345", role=UserRole.AUDITOR)
        self.data_entry = User.objects.create_user(username="aud_vis_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.data_entry2 = User.objects.create_user(username="aud_vis_entry2", password="pass12345", role=UserRole.DATA_ENTRY)
        self.reader = User.objects.create_user(username="aud_vis_reader", password="pass12345", role=UserRole.READER)

        # Set up document type and dossier
        self.doc_type = DocumentType.objects.create(
            name="Test Doc",
            slug="test-doc",
            group_name="test",
            display_order=1,
            is_active=True,
        )
        self.dossier = Dossier.objects.create(
            file_number="AUD-VIS-001",
            full_name="Test Dossier",
            national_id="12345678901",
            personal_id="PID001",
            room_number="101",
            column_number="A",
            shelf_number="1",
            created_by=self.data_entry,
        )

    def test_auditor_sees_only_assigned_data_entry_documents(self):
        """Auditor sees only documents from data_entry users assigned to them."""
        # Link data_entry to auditor
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        # data_entry2 is NOT assigned to auditor
        self.data_entry2.assigned_auditor = self.auditor2
        self.data_entry2.save()

        # Create document from assigned data_entry (should be visible)
        doc_assigned = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AV-001",
            doc_name="Assigned Doc",
            file_path="archive/av1.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.data_entry,
        )

        # Create document from non-assigned data_entry (should NOT be visible)
        doc_other = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AV-002",
            doc_name="Other Doc",
            file_path="archive/av2.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.data_entry2,
        )

        # Auditor views document list
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should see only 1 document (the one from assigned data_entry)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], doc_assigned.id)

    def test_auditor_sees_pending_rejected_approved_not_draft(self):
        """Auditor sees pending, rejected, approved but NOT draft documents."""
        # Link data_entry to auditor
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        # Create documents in different statuses
        doc_draft = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AV-DRAFT",
            doc_name="Draft Doc",
            file_path="archive/draft.pdf",
            file_size_kb=100,
            status=DocumentStatus.DRAFT,
            created_by=self.data_entry,
        )
        doc_pending = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AV-PENDING",
            doc_name="Pending Doc",
            file_path="archive/pending.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.data_entry,
        )
        doc_rejected = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AV-REJECTED",
            doc_name="Rejected Doc",
            file_path="archive/rejected.pdf",
            file_size_kb=100,
            status=DocumentStatus.REJECTED,
            created_by=self.data_entry,
        )
        doc_approved = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AV-APPROVED",
            doc_name="Approved Doc",
            file_path="archive/approved.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
        )

        # Auditor views document list
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should see 3 documents (pending, rejected, approved) but not draft
        self.assertEqual(response.data["count"], 3)
        visible_ids = {d["id"] for d in response.data["results"]}
        self.assertIn(doc_pending.id, visible_ids)
        self.assertIn(doc_rejected.id, visible_ids)
        self.assertIn(doc_approved.id, visible_ids)
        self.assertNotIn(doc_draft.id, visible_ids)

    def test_auditor_sees_no_documents_without_assignment(self):
        """Auditor sees no documents if no data_entry users are assigned to them."""
        # data_entry has NO assigned auditor
        self.data_entry.assigned_auditor = None
        self.data_entry.save()

        # Create document
        Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AV-NO-ASSIGN",
            doc_name="No Assign Doc",
            file_path="archive/noassign.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.data_entry,
        )

        # Auditor views document list
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should see 0 documents (no assigned data_entry users)
        self.assertEqual(response.data["count"], 0)

    def test_deleted_documents_do_not_appear_in_auditor_search_scope(self):
        """Deleted documents stay outside the auditor search/list visibility scope."""
        # Link data_entry to auditor
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        # Create deleted document from assigned data_entry
        Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AV-DEL",
            doc_name="Deleted Doc",
            file_path="archive/deleted.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            is_deleted=True,
        )

        # Create deleted document from other data_entry (not assigned to this auditor)
        self.data_entry2.assigned_auditor = self.auditor2
        self.data_entry2.save()
        Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="AV-DEL-OTHER",
            doc_name="Other Deleted Doc",
            file_path="archive/deleted_other.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry2,
            is_deleted=True,
        )

        # Auditor views deleted document list
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get("/api/documents/?is_deleted=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Deleted documents are outside the search visibility scope entirely.
        self.assertEqual(response.data["count"], 0)


class ScopedReviewQueueApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="rq_admin", password="pass12345", role=UserRole.ADMIN)
        self.auditor = User.objects.create_user(username="rq_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.other_auditor = User.objects.create_user(username="rq_auditor_other", password="pass12345", role=UserRole.AUDITOR)
        self.data_entry = User.objects.create_user(username="rq_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.other_data_entry = User.objects.create_user(username="rq_entry_other", password="pass12345", role=UserRole.DATA_ENTRY)
        self.reader = User.objects.create_user(username="rq_reader", password="pass12345", role=UserRole.READER)

        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self.other_data_entry.assigned_auditor = self.other_auditor
        self.other_data_entry.save()

        self.doc_type = DocumentType.objects.create(
            name="Review Queue Doc",
            slug="review-queue-doc",
            group_name="review",
            display_order=1,
            is_active=True,
        )
        self.dossier = Dossier.objects.create(
            file_number="RQ-001",
            full_name="Review Queue User",
            national_id="RQ-N1",
            personal_id="RQ-P1",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry,
        )
        self.other_dossier = Dossier.objects.create(
            file_number="RQ-002",
            full_name="Review Queue User 2",
            national_id="RQ-N2",
            personal_id="RQ-P2",
            room_number="2",
            column_number="2",
            shelf_number="2",
            created_by=self.other_data_entry,
        )

        self.assigned_pending = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="RQ-PENDING-1",
            doc_name="Assigned Pending",
            file_path="archive/rq-pending-1.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.data_entry,
        )
        self.assigned_approved = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="RQ-APPROVED-1",
            doc_name="Assigned Approved",
            file_path="archive/rq-approved-1.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
        )
        self.other_pending = Document.objects.create(
            dossier=self.other_dossier,
            doc_type=self.doc_type,
            doc_number="RQ-PENDING-2",
            doc_name="Other Pending",
            file_path="archive/rq-pending-2.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.other_data_entry,
        )

    def test_assigned_auditor_sees_only_their_pending_queue(self):
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get("/api/auditor/review-queue/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.assigned_pending.id)

    def test_other_auditor_cannot_see_unrelated_queue_items(self):
        self.client.force_authenticate(user=self.other_auditor)
        response = self.client.get("/api/auditor/review-queue/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.other_pending.id)

    def test_admin_sees_all_pending_queue_items(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/auditor/review-queue/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertEqual(ids, {self.assigned_pending.id, self.other_pending.id})


class DocumentDetailScopeApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="dd_admin", password="pass12345", role=UserRole.ADMIN)
        self.auditor = User.objects.create_user(username="dd_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.other_auditor = User.objects.create_user(username="dd_auditor_other", password="pass12345", role=UserRole.AUDITOR)
        self.data_entry = User.objects.create_user(username="dd_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.other_data_entry = User.objects.create_user(username="dd_entry_other", password="pass12345", role=UserRole.DATA_ENTRY)

        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self.other_data_entry.assigned_auditor = self.other_auditor
        self.other_data_entry.save()

        self.doc_type = DocumentType.objects.create(
            name="Detail Scope Doc",
            slug="detail-scope-doc",
            group_name="detail",
            display_order=1,
            is_active=True,
        )
        self.dossier = Dossier.objects.create(
            file_number="DD-001",
            full_name="Detail Scope User",
            national_id="DD-N1",
            personal_id="DD-P1",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry,
        )
        self.other_dossier = Dossier.objects.create(
            file_number="DD-002",
            full_name="Other Detail Scope User",
            national_id="DD-N2",
            personal_id="DD-P2",
            room_number="2",
            column_number="2",
            shelf_number="2",
            created_by=self.other_data_entry,
        )

        self.pending_doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="DD-PENDING",
            doc_name="Pending Detail",
            file_path="archive/dd-pending.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.data_entry,
        )
        self.rejected_doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="DD-REJECTED",
            doc_name="Rejected Detail",
            file_path="archive/dd-rejected.pdf",
            file_size_kb=100,
            status=DocumentStatus.REJECTED,
            rejection_reason="Needs correction",
            created_by=self.data_entry,
        )
        self.approved_doc = Document.objects.create(
            dossier=self.dossier,
            doc_type=self.doc_type,
            doc_number="DD-APPROVED",
            doc_name="Approved Detail",
            file_path="archive/dd-approved.pdf",
            file_size_kb=100,
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
        )
        self.outside_doc = Document.objects.create(
            dossier=self.other_dossier,
            doc_type=self.doc_type,
            doc_number="DD-OUTSIDE",
            doc_name="Outside Scope",
            file_path="archive/dd-outside.pdf",
            file_size_kb=100,
            status=DocumentStatus.PENDING,
            created_by=self.other_data_entry,
        )

    def test_auditor_can_open_scoped_pending_rejected_and_approved_documents(self):
        self.client.force_authenticate(user=self.auditor)
        for document in [self.pending_doc, self.rejected_doc, self.approved_doc]:
            response = self.client.get(f"/api/documents/{document.id}/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["id"], document.id)

    def test_auditor_cannot_access_document_outside_assignment(self):
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get(f"/api/documents/{self.outside_doc.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
