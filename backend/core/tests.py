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
        self.assertEqual(response.data[0]["slug"], "appointment")


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
        self.admin = User.objects.create_user(username="admin_audit", password="pass12345", role=UserRole.ADMIN)
        self.auditor = User.objects.create_user(username="auditor_audit", password="pass12345", role=UserRole.AUDITOR)
        self.data_entry = User.objects.create_user(username="entry_audit", password="pass12345", role=UserRole.DATA_ENTRY)
        self.reader = User.objects.create_user(username="reader_audit", password="pass12345", role=UserRole.READER)

        self.log1 = AuditLog.objects.create(
            user=self.admin,
            action=AuditAction.CREATE,
            entity_type="dossier",
            entity_id=10,
            new_values={"status": "created"},
        )
        self.log2 = AuditLog.objects.create(
            user=self.auditor,
            action=AuditAction.APPROVE,
            entity_type="document",
            entity_id=20,
            old_values={"status": "pending"},
            new_values={"status": "approved"},
        )
        self.log3 = AuditLog.objects.create(
            user=self.admin,
            action=AuditAction.REJECT,
            entity_type="document",
            entity_id=21,
            old_values={"status": "pending"},
            new_values={"status": "rejected"},
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

    def test_audit_logs_filters(self):
        self.client.force_authenticate(user=self.admin)

        by_action = self.client.get("/api/audit-logs/?action=approve")
        self.assertEqual(by_action.status_code, status.HTTP_200_OK)
        self.assertEqual(by_action.data["count"], 1)

        by_actor = self.client.get(f"/api/audit-logs/?actor={self.auditor.id}")
        self.assertEqual(by_actor.status_code, status.HTTP_200_OK)
        self.assertEqual(by_actor.data["count"], 1)

        by_model = self.client.get("/api/audit-logs/?model=document")
        self.assertEqual(by_model.status_code, status.HTTP_200_OK)
        self.assertEqual(by_model.data["count"], 2)

        by_table_name = self.client.get("/api/audit-logs/?table_name=dossier")
        self.assertEqual(by_table_name.status_code, status.HTTP_200_OK)
        self.assertEqual(by_table_name.data["count"], 1)

        by_object_id = self.client.get("/api/audit-logs/?object_id=20")
        self.assertEqual(by_object_id.status_code, status.HTTP_200_OK)
        self.assertEqual(by_object_id.data["count"], 1)

        today_str = timezone.now().date().isoformat()
        by_date = self.client.get(f"/api/audit-logs/?date_from={today_str}")
        self.assertEqual(by_date.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(by_date.data["count"], 1)

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
        self.auditor = User.objects.create_user(username="d_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()
        self.g1 = Governorate.objects.create(name="Damascus", is_active=True)
        self.g2 = Governorate.objects.create(name="Homs", is_active=True)

        self.d1 = Dossier.objects.create(
            file_number="DOS-003",
            full_name="Ali Hassan",
            national_id="N-003",
            personal_id="P-003",
            governorate=self.g1,
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.admin,
            is_archived=False,
        )
        self.d2 = Dossier.objects.create(
            file_number="DOS-001",
            full_name="Maya Saad",
            national_id="N-001",
            personal_id="P-001",
            governorate=self.g2,
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.data_entry,
            is_archived=True,
        )
        self.d3 = Dossier.objects.create(
            file_number="DOS-002",
            full_name="Omar Khaled",
            national_id="N-002",
            personal_id="P-002",
            governorate=self.g1,
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.admin,
            is_archived=False,
        )

        now = timezone.now()
        Dossier.objects.filter(pk=self.d1.pk).update(created_at=now - timedelta(days=2))
        Dossier.objects.filter(pk=self.d2.pk).update(created_at=now - timedelta(days=1))
        Dossier.objects.filter(pk=self.d3.pk).update(created_at=now)

        self.client.force_authenticate(user=self.admin)

    def test_data_entry_sees_only_own_dossiers(self):
        self.client.force_authenticate(user=self.data_entry)
        response = self.client.get("/api/dossiers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.d2.id)

    def test_auditor_sees_only_assigned_data_entry_dossiers(self):
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get("/api/dossiers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.d2.id)

    def test_dossier_list_is_paginated_and_default_order_newest_first(self):
        response = self.client.get("/api/dossiers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["results"][0]["id"], self.d3.id)

    def test_dossier_search_fields(self):
        by_file_number = self.client.get("/api/dossiers/?search=DOS-001")
        self.assertEqual(by_file_number.status_code, status.HTTP_200_OK)
        self.assertEqual(by_file_number.data["count"], 1)
        self.assertEqual(by_file_number.data["results"][0]["id"], self.d2.id)

        by_name = self.client.get("/api/dossiers/?search=Ali")
        self.assertEqual(by_name.status_code, status.HTTP_200_OK)
        self.assertEqual(by_name.data["count"], 1)
        self.assertEqual(by_name.data["results"][0]["id"], self.d1.id)

        by_national_id = self.client.get("/api/dossiers/?search=N-002")
        self.assertEqual(by_national_id.status_code, status.HTTP_200_OK)
        self.assertEqual(by_national_id.data["count"], 1)
        self.assertEqual(by_national_id.data["results"][0]["id"], self.d3.id)

    def test_dossier_filters(self):
        by_governorate = self.client.get(f"/api/dossiers/?governorate={self.g1.id}")
        self.assertEqual(by_governorate.status_code, status.HTTP_200_OK)
        self.assertEqual(by_governorate.data["count"], 2)

        by_creator = self.client.get(f"/api/dossiers/?created_by={self.data_entry.id}")
        self.assertEqual(by_creator.status_code, status.HTTP_200_OK)
        self.assertEqual(by_creator.data["count"], 1)
        self.assertEqual(by_creator.data["results"][0]["id"], self.d2.id)

        archived_only = self.client.get("/api/dossiers/?is_deleted=true")
        self.assertEqual(archived_only.status_code, status.HTTP_200_OK)
        self.assertEqual(archived_only.data["count"], 1)
        self.assertEqual(archived_only.data["results"][0]["id"], self.d2.id)

    def test_dossier_ordering_and_pagination(self):
        ordered = self.client.get("/api/dossiers/?ordering=file_number")
        self.assertEqual(ordered.status_code, status.HTTP_200_OK)
        self.assertEqual([item["file_number"] for item in ordered.data["results"]], ["DOS-001", "DOS-002", "DOS-003"])

        paged = self.client.get("/api/dossiers/?page_size=2")
        self.assertEqual(paged.status_code, status.HTTP_200_OK)
        self.assertEqual(len(paged.data["results"]), 2)
        self.assertEqual(paged.data["count"], 3)


class DocumentListQueryApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="q_admin", password="pass12345", role=UserRole.ADMIN)
        self.data_entry = User.objects.create_user(username="q_entry", password="pass12345", role=UserRole.DATA_ENTRY)
        self.auditor = User.objects.create_user(username="q_auditor", password="pass12345", role=UserRole.AUDITOR)
        self.reader = User.objects.create_user(username="q_reader", password="pass12345", role=UserRole.READER)

        self.doc_type_1 = DocumentType.objects.create(name="Type 1", slug="type-1", group_name="core", display_order=1, is_active=True)
        self.doc_type_2 = DocumentType.objects.create(name="Type 2", slug="type-2", group_name="core", display_order=2, is_active=True)

        self.dossier_1 = Dossier.objects.create(
            file_number="QD-001",
            full_name="Doc User 1",
            national_id="Q-N1",
            personal_id="Q-P1",
            room_number="1",
            column_number="1",
            shelf_number="1",
            created_by=self.admin,
        )
        self.dossier_2 = Dossier.objects.create(
            file_number="QD-002",
            full_name="Doc User 2",
            national_id="Q-N2",
            personal_id="Q-P2",
            room_number="2",
            column_number="2",
            shelf_number="2",
            created_by=self.data_entry,
        )

        self.doc_approved = Document.objects.create(
            dossier=self.dossier_1,
            doc_type=self.doc_type_1,
            doc_number="DOC-APP",
            doc_name="Approved Letter",
            file_path="archive/q-doc-approved.pdf",
            file_size_kb=120,
            mime_type="application/pdf",
            status=DocumentStatus.APPROVED,
            created_by=self.data_entry,
            reviewed_by=self.auditor,
            reviewed_at=timezone.now() - timedelta(hours=1),
        )
        self.doc_pending = Document.objects.create(
            dossier=self.dossier_1,
            doc_type=self.doc_type_2,
            doc_number="DOC-PEN",
            doc_name="Pending Letter",
            file_path="archive/q-doc-pending.pdf",
            file_size_kb=121,
            mime_type="application/pdf",
            status=DocumentStatus.PENDING,
            created_by=self.admin,
        )
        self.doc_draft = Document.objects.create(
            dossier=self.dossier_2,
            doc_type=self.doc_type_1,
            doc_number="DOC-DRF",
            doc_name="Draft Form",
            file_path="archive/q-doc-draft.pdf",
            file_size_kb=122,
            mime_type="application/pdf",
            status=DocumentStatus.DRAFT,
            created_by=self.data_entry,
        )
        self.doc_rejected_deleted = Document.objects.create(
            dossier=self.dossier_2,
            doc_type=self.doc_type_2,
            doc_number="DOC-REJ",
            doc_name="Rejected Memo",
            file_path="archive/q-doc-rejected.pdf",
            file_size_kb=123,
            mime_type="application/pdf",
            status=DocumentStatus.REJECTED,
            created_by=self.admin,
            is_deleted=True,
        )

        now = timezone.now()
        Document.objects.filter(pk=self.doc_approved.pk).update(created_at=now - timedelta(days=3))
        Document.objects.filter(pk=self.doc_pending.pk).update(created_at=now - timedelta(days=2))
        Document.objects.filter(pk=self.doc_draft.pk).update(created_at=now - timedelta(days=1))
        Document.objects.filter(pk=self.doc_rejected_deleted.pk).update(created_at=now)

    def test_data_entry_sees_only_own_documents(self):
        self.client.force_authenticate(user=self.data_entry)
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        ids = {item["id"] for item in response.data["results"]}
        self.assertEqual(ids, {self.doc_draft.id, self.doc_approved.id})

    def test_document_role_visibility_remains_unchanged(self):
        """Verify role-based document visibility with auditor scope via assigned_auditor linkage."""
        # Set up assigned_auditor linkage so auditor can see documents from data_entry
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        self.client.force_authenticate(user=self.reader)
        reader_response = self.client.get("/api/documents/")
        self.assertEqual(reader_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reader_response.data["count"], 1)
        self.assertEqual(reader_response.data["results"][0]["id"], self.doc_approved.id)

        self.client.force_authenticate(user=self.auditor)
        auditor_response = self.client.get("/api/documents/")
        self.assertEqual(auditor_response.status_code, status.HTTP_200_OK)
        # Auditor sees documents from assigned data_entry with statuses: pending, rejected, approved (draft excluded)
        # doc_approved (created_by=data_entry) and doc_rejected_deleted (is_deleted=True) - only doc_approved visible
        self.assertEqual(auditor_response.data["count"], 1)
        self.assertEqual(auditor_response.data["results"][0]["id"], self.doc_approved.id)

        self.client.force_authenticate(user=self.admin)
        admin_response = self.client.get("/api/documents/")
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_response.data["count"], 3)

    def test_document_search_filters_ordering_and_pagination(self):
        self.client.force_authenticate(user=self.admin)

        by_search = self.client.get("/api/documents/?search=Pending")
        self.assertEqual(by_search.status_code, status.HTTP_200_OK)
        self.assertEqual(by_search.data["count"], 1)
        self.assertEqual(by_search.data["results"][0]["id"], self.doc_pending.id)

        by_status = self.client.get("/api/documents/?status=approved")
        self.assertEqual(by_status.status_code, status.HTTP_200_OK)
        self.assertEqual(by_status.data["count"], 1)
        self.assertEqual(by_status.data["results"][0]["id"], self.doc_approved.id)

        by_doc_type = self.client.get(f"/api/documents/?doc_type={self.doc_type_1.id}")
        self.assertEqual(by_doc_type.status_code, status.HTTP_200_OK)
        self.assertEqual(by_doc_type.data["count"], 2)

        by_dossier = self.client.get(f"/api/documents/?dossier={self.dossier_1.id}")
        self.assertEqual(by_dossier.status_code, status.HTTP_200_OK)
        self.assertEqual(by_dossier.data["count"], 2)

        by_creator = self.client.get(f"/api/documents/?created_by={self.admin.id}")
        self.assertEqual(by_creator.status_code, status.HTTP_200_OK)
        self.assertEqual(by_creator.data["count"], 1)
        self.assertEqual(by_creator.data["results"][0]["id"], self.doc_pending.id)

        by_reviewer = self.client.get(f"/api/documents/?reviewed_by={self.auditor.id}")
        self.assertEqual(by_reviewer.status_code, status.HTTP_200_OK)
        self.assertEqual(by_reviewer.data["count"], 1)
        self.assertEqual(by_reviewer.data["results"][0]["id"], self.doc_approved.id)

        include_deleted = self.client.get("/api/documents/?is_deleted=true")
        self.assertEqual(include_deleted.status_code, status.HTTP_200_OK)
        self.assertEqual(include_deleted.data["count"], 1)
        self.assertEqual(include_deleted.data["results"][0]["id"], self.doc_rejected_deleted.id)

        ordered = self.client.get("/api/documents/?ordering=status")
        self.assertEqual(ordered.status_code, status.HTTP_200_OK)
        self.assertEqual([item["status"] for item in ordered.data["results"]], ["approved", "draft", "pending"])

        paged = self.client.get("/api/documents/?page_size=2")
        self.assertEqual(paged.status_code, status.HTTP_200_OK)
        self.assertEqual(paged.data["count"], 3)
        self.assertEqual(len(paged.data["results"]), 2)


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
        self.assertIn("status", res.data)

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
        self.assertGreaterEqual(count, 59)
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
        self.assertGreaterEqual(len(response.data), 59)


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

        self.client.force_authenticate(user=self.admin)

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

    def test_no_assigned_auditor_is_not_flagged(self):
        """Document without assigned auditor should have is_approved_by_admin=False."""
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

        # Check serializer field - no assigned auditor means not in scope
        from core.serializers import DocumentSummarySerializer
        serializer = DocumentSummarySerializer(doc)
        self.assertFalse(serializer.data["is_approved_by_admin"])

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

    def test_deleted_documents_also_follow_auditor_scope(self):
        """Auditor sees deleted documents only from their assigned data_entry users."""
        # Link data_entry to auditor
        self.data_entry.assigned_auditor = self.auditor
        self.data_entry.save()

        # Create deleted document from assigned data_entry
        doc_deleted = Document.objects.create(
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
        doc_other_deleted = Document.objects.create(
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

        # Should see only 1 deleted document (from assigned data_entry)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], doc_deleted.id)


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
