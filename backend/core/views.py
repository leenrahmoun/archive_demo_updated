from datetime import timedelta
from pathlib import Path

from django.core.files.storage import default_storage
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404
from rest_framework import filters, generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from core.access import (
    annotate_audit_log_human_fields,
    apply_audit_log_filters,
    apply_audit_log_search,
    apply_document_advanced_filters,
    apply_dossier_advanced_filters,
    get_audit_log_visibility_queryset,
    get_deleted_document_visibility_queryset,
    get_deleted_document_detail_queryset_for_user,
    get_document_queryset_for_user,
    get_document_detail_queryset_for_user,
    get_document_restore_scope_queryset_for_user,
    get_document_soft_delete_scope_queryset_for_user,
    get_document_submit_scope_queryset_for_user,
    get_document_review_scope_queryset_for_user,
    get_dossier_visibility_queryset,
    get_review_queue_queryset_for_user,
)
from core.models import AuditAction, AuditLog, Document, DocumentStatus, DocumentType, Dossier, Governorate, User, UserRole
from core.permissions import (
    AdminOnlyPermission,
    AuditLogPermission,
    DeletedDocumentPermission,
    DocumentPermission,
    DossierPermission,
    DocumentWorkflowPermission,
)
from core.serializers import (
    AdminDashboardAdminReviewActivitySerializer,
    AdminDashboardAuditEventSerializer,
    AdminDashboardAuditorPerformanceSerializer,
    AdminDashboardDataEntryPerformanceSerializer,
    AdminDashboardRecentDocumentSerializer,
    AuditLogSerializer,
    DocumentCreateSerializer,
    DocumentReplaceFileSerializer,
    DocumentRejectSerializer,
    DocumentSummarySerializer,
    DocumentTypeManagementSerializer,
    DocumentTypeLookupSerializer,
    DocumentUpdateSerializer,
    DossierCreateSerializer,
    DossierDetailSerializer,
    DossierListSerializer,
    GovernorateLookupSerializer,
    LogoutSerializer,
    MeSerializer,
    UserManagementSerializer,
    get_user_display_name,
    normalize_document_type_name,
)
from core.services.audit_log_service import create_audit_log, log_document_workflow_access_denied, log_user_security_event
from core.services.document_workflow_service import (
    WorkflowError,
    approve_document,
    reject_document,
    restore_document,
    soft_delete_document,
    submit_document,
)
from core.user_visibility import exclude_emergency_only_audit_logs, get_operational_user_queryset


class StandardListPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


DOCUMENT_TYPE_ADMIN_ORDERING = ("name", "id")
RECENT_DASHBOARD_ITEMS_LIMIT = 5
RECENT_DASHBOARD_WINDOW_DAYS = 7
DASHBOARD_CHART_WINDOW_DAYS = 7
DASHBOARD_TOP_ITEMS_LIMIT = 5


def apply_document_type_admin_name_search(queryset, raw_search_value):
    normalized_search = normalize_document_type_name(raw_search_value)
    if not normalized_search:
        return queryset

    matching_ids = [
        document_type_id
        for document_type_id, name in queryset.values_list("id", "name")
        if normalized_search in normalize_document_type_name(name)
    ]
    if not matching_ids:
        return queryset.none()

    return queryset.filter(id__in=matching_ids)


def get_latest_dashboard_timestamp(*values):
    present_values = [value for value in values if value is not None]
    if not present_values:
        return None
    return max(present_values)


def build_dashboard_daily_count_series(*, start_date, window_days, count_by_date):
    items = []
    for offset in range(window_days):
        current_date = start_date + timedelta(days=offset)
        items.append(
            {
                "date": current_date.isoformat(),
                "label": current_date.strftime("%d/%m"),
                "value": count_by_date.get(current_date, 0),
            }
        )
    return items


def build_dashboard_daily_review_series(*, start_date, window_days, approved_by_date, rejected_by_date):
    items = []
    for offset in range(window_days):
        current_date = start_date + timedelta(days=offset)
        approved_value = approved_by_date.get(current_date, 0)
        rejected_value = rejected_by_date.get(current_date, 0)
        items.append(
            {
                "date": current_date.isoformat(),
                "label": current_date.strftime("%d/%m"),
                "approved_value": approved_value,
                "rejected_value": rejected_value,
                "total_value": approved_value + rejected_value,
            }
        )
    return items


class DossierListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [DossierPermission]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    queryset = Dossier.objects.all().order_by("-created_at", "-id")
    pagination_class = StandardListPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["file_number", "full_name", "created_at"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        queryset = get_dossier_visibility_queryset(self.request.user).select_related("governorate", "created_by")
        return apply_dossier_advanced_filters(queryset, self.request.query_params, self.request.user)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DossierCreateSerializer
        return DossierListSerializer

    def _get_create_payload(self, request):
        content_type = request.content_type or ""
        if not content_type.startswith("multipart/"):
            return request.data

        payload = {}
        first_document = {}

        for key in request.POST.keys():
            value = request.POST.get(key)
            if key.startswith("first_document."):
                first_document[key.split(".", 1)[1]] = value
            else:
                payload[key] = value

        uploaded_file = request.FILES.get("first_document.file")
        if uploaded_file is not None:
            first_document["file"] = uploaded_file

        if first_document:
            payload["first_document"] = first_document

        return payload

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=self._get_create_payload(request))
        serializer.is_valid(raise_exception=True)
        dossier = serializer.save()
        output = DossierDetailSerializer(dossier, context=self.get_serializer_context())
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)


class DossierRetrieveAPIView(generics.RetrieveAPIView):
    permission_classes = [DossierPermission]
    serializer_class = DossierDetailSerializer

    def get_queryset(self):
        return get_dossier_visibility_queryset(self.request.user)


class DocumentListAPIView(generics.ListCreateAPIView):
    permission_classes = [DocumentPermission]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DocumentCreateSerializer
        return DocumentSummarySerializer

    pagination_class = StandardListPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["status", "created_at", "reviewed_at"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        queryset = get_document_queryset_for_user(self.request.user).select_related(
            "dossier",
            "doc_type",
            "created_by",
            "reviewed_by",
        )
        return apply_document_advanced_filters(queryset, self.request.query_params, self.request.user)


class DeletedDocumentListAPIView(generics.ListAPIView):
    permission_classes = [DeletedDocumentPermission]
    serializer_class = DocumentSummarySerializer
    pagination_class = StandardListPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["status", "created_at", "reviewed_at", "deleted_at"]
    ordering = ["-deleted_at", "-id"]

    def get_queryset(self):
        queryset = get_deleted_document_visibility_queryset(self.request.user).select_related(
            "dossier",
            "doc_type",
            "created_by",
            "reviewed_by",
            "deleted_by",
        )
        return apply_document_advanced_filters(queryset, self.request.query_params, self.request.user, deleted_state=True)


class DocumentRetrieveAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [DocumentPermission]

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return DocumentUpdateSerializer
        return DocumentSummarySerializer

    def get_queryset(self):
        include_deleted = str(self.request.query_params.get("include_deleted", "")).lower() in {"1", "true", "yes"}
        if self.request.method == "GET" and include_deleted:
            return get_deleted_document_detail_queryset_for_user(self.request.user).select_related(
                "dossier",
                "doc_type",
                "created_by",
                "reviewed_by",
                "deleted_by",
            )
        return get_document_detail_queryset_for_user(self.request.user).select_related(
            "dossier",
            "doc_type",
            "created_by",
            "reviewed_by",
            "deleted_by",
        )


class DocumentFileAccessAPIView(APIView):
    permission_classes = [DocumentPermission]

    def get(self, request, pk, *args, **kwargs):
        document = generics.get_object_or_404(
            get_document_detail_queryset_for_user(request.user).select_related("created_by"),
            pk=pk,
        )

        try:
            file_handle = default_storage.open(document.file_path, "rb")
        except FileNotFoundError as exc:
            raise Http404("Document file not found.") from exc

        filename = Path(document.file_path).name or f"document-{document.id}.pdf"
        return FileResponse(
            file_handle,
            content_type=document.mime_type or Document.PDF_MIME_TYPE,
            filename=filename,
        )


class DocumentReplaceFileAPIView(APIView):
    permission_classes = [IsAuthenticated, DocumentPermission]
    parser_classes = [FormParser, MultiPartParser]

    def post(self, request, pk, *args, **kwargs):
        if request.user.role != UserRole.DATA_ENTRY:
            return Response(
                {"detail": "You do not have permission to replace document files."},
                status=status.HTTP_403_FORBIDDEN,
            )

        document = generics.get_object_or_404(
            Document.objects.filter(created_by=request.user, is_deleted=False),
            pk=pk,
        )
        serializer = DocumentReplaceFileSerializer(
            instance=document,
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        document = serializer.save()
        return Response(DocumentSummarySerializer(document).data, status=status.HTTP_200_OK)


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(MeSerializer(request.user).data, status=status.HTTP_200_OK)


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_user_security_event(
            user=request.user,
            action=AuditAction.LOGOUT,
            request=request,
            message="Successful logout.",
        )
        return Response({"detail": "Logout successful."}, status=status.HTTP_200_OK)


class GovernorateListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GovernorateLookupSerializer
    queryset = Governorate.objects.filter(is_active=True).order_by("name")


class DocumentTypeListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DocumentTypeLookupSerializer

    def get_queryset(self):
        return DocumentType.objects.filter(is_active=True).order_by("group_name", "display_order", "name", "id")


class AdminDocumentTypeListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, AdminOnlyPermission]
    serializer_class = DocumentTypeManagementSerializer
    pagination_class = StandardListPagination

    def get_queryset(self):
        queryset = DocumentType.objects.annotate(usage_count=Count("documents", distinct=True))

        search_value = (self.request.query_params.get("search") or "").strip()
        queryset = apply_document_type_admin_name_search(queryset, search_value)

        status_value = (self.request.query_params.get("status") or "").strip().lower()
        if not status_value:
            is_active = self.request.query_params.get("is_active")
            if is_active is not None:
                lowered = is_active.lower()
                if lowered in {"true", "1"}:
                    status_value = "active"
                elif lowered in {"false", "0"}:
                    status_value = "inactive"

        if status_value == "active":
            queryset = queryset.filter(is_active=True)
        elif status_value == "inactive":
            queryset = queryset.filter(is_active=False)

        return queryset.order_by(*DOCUMENT_TYPE_ADMIN_ORDERING)


class AdminDocumentTypeRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, AdminOnlyPermission]
    serializer_class = DocumentTypeManagementSerializer
    queryset = DocumentType.objects.annotate(usage_count=Count("documents", distinct=True)).all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.documents.exists():
            return Response(
                {"detail": "لا يمكن حذف نوع الوثيقة لأنه مستخدم في وثائق موجودة. يمكنك تعطيله بدلًا من ذلك."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        create_audit_log(
            user=request.user,
            action=AuditAction.DELETE,
            entity_type="document_type",
            entity_id=instance.id,
            old_values={"name": instance.name, "is_active": instance.is_active},
            new_values={"name": instance.name, "message": "تم حذف نوع الوثيقة."},
        )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated, AdminOnlyPermission]

    def get(self, request, *args, **kwargs):
        user = request.user
        recent_cutoff = timezone.now() - timedelta(days=RECENT_DASHBOARD_WINDOW_DAYS)
        chart_start_date = timezone.localdate() - timedelta(days=DASHBOARD_CHART_WINDOW_DAYS - 1)
        operational_users = get_operational_user_queryset()

        visible_dossiers = get_dossier_visibility_queryset(user)
        visible_documents = get_document_visibility_queryset(user)
        visible_audit_logs = annotate_audit_log_human_fields(
            exclude_emergency_only_audit_logs(get_audit_log_visibility_queryset(user))
        )

        summary = visible_documents.aggregate(
            total_active_documents=Count("id"),
            draft_documents=Count("id", filter=Q(status=DocumentStatus.DRAFT)),
            pending_documents=Count("id", filter=Q(status=DocumentStatus.PENDING)),
            rejected_documents=Count("id", filter=Q(status=DocumentStatus.REJECTED)),
            approved_documents=Count("id", filter=Q(status=DocumentStatus.APPROVED)),
        )
        summary["total_dossiers"] = visible_dossiers.count()
        summary["soft_deleted_documents"] = Document.objects.filter(is_deleted=True).count()
        summary["total_active_users"] = operational_users.filter(is_active=True).count()

        workflow = {
            "pending_review_documents": summary["pending_documents"],
            "rejected_waiting_correction_documents": summary["rejected_documents"],
            "approved_documents": summary["approved_documents"],
            "recently_created_documents": visible_documents.filter(created_at__gte=recent_cutoff).count(),
            "recent_window_days": RECENT_DASHBOARD_WINDOW_DAYS,
        }

        user_activity = operational_users.aggregate(
            total_data_entry_users=Count("id", filter=Q(role=UserRole.DATA_ENTRY)),
            total_auditors=Count("id", filter=Q(role=UserRole.AUDITOR)),
            total_readers=Count("id", filter=Q(role=UserRole.READER)),
            total_active_users=Count("id", filter=Q(is_active=True)),
            data_entry_users_without_assigned_auditor=Count(
                "id",
                filter=Q(role=UserRole.DATA_ENTRY, assigned_auditor__isnull=True),
            ),
        )
        user_activity["auditors_with_zero_assigned_data_entry_users"] = (
            operational_users.filter(role=UserRole.AUDITOR)
            .annotate(
                assigned_data_entry_users_count=Count(
                    "assigned_data_entries",
                    filter=Q(assigned_data_entries__role=UserRole.DATA_ENTRY),
                    distinct=True,
                )
            )
            .filter(assigned_data_entry_users_count=0)
            .count()
        )

        data_entry_users = list(
            operational_users.filter(role=UserRole.DATA_ENTRY)
            .select_related("assigned_auditor")
            .order_by("first_name", "last_name", "username", "id")
        )

        data_entry_dossier_stats = {
            item["created_by_id"]: item
            for item in Dossier.objects.values("created_by_id").annotate(
                dossiers_created_count=Count("id"),
                last_dossier_created_at=Max("created_at"),
            )
        }
        data_entry_document_stats = {
            item["created_by_id"]: item
            for item in Document.objects.values("created_by_id").annotate(
                documents_created_count=Count("id"),
                draft_documents_count=Count(
                    "id",
                    filter=Q(is_deleted=False, status=DocumentStatus.DRAFT),
                ),
                pending_documents_count=Count(
                    "id",
                    filter=Q(is_deleted=False, status=DocumentStatus.PENDING),
                ),
                rejected_documents_count=Count(
                    "id",
                    filter=Q(is_deleted=False, status=DocumentStatus.REJECTED),
                ),
                approved_documents_count=Count(
                    "id",
                    filter=Q(is_deleted=False, status=DocumentStatus.APPROVED),
                ),
                last_document_created_at=Max("created_at"),
            )
        }
        data_entry_log_stats = {
            item["user_id"]: item
            for item in AuditLog.objects.filter(user__role=UserRole.DATA_ENTRY, user__is_superuser=False)
            .values("user_id")
            .annotate(
                submissions_count=Count(
                    "id",
                    filter=Q(action=AuditAction.SUBMIT, entity_type="document"),
                ),
                last_audit_log_at=Max("created_at"),
            )
        }

        data_entry_performance_rows = []
        for data_entry_user in data_entry_users:
            dossier_stats = data_entry_dossier_stats.get(data_entry_user.id, {})
            document_stats = data_entry_document_stats.get(data_entry_user.id, {})
            log_stats = data_entry_log_stats.get(data_entry_user.id, {})
            data_entry_performance_rows.append(
                {
                    "user_id": data_entry_user.id,
                    "username": data_entry_user.username,
                    "display_name": get_user_display_name(data_entry_user),
                    "assigned_auditor_name": (
                        get_user_display_name(data_entry_user.assigned_auditor)
                        if data_entry_user.assigned_auditor
                        else None
                    ),
                    "dossiers_created_count": dossier_stats.get("dossiers_created_count", 0),
                    "documents_created_count": document_stats.get("documents_created_count", 0),
                    "draft_documents_count": document_stats.get("draft_documents_count", 0),
                    "pending_documents_count": document_stats.get("pending_documents_count", 0),
                    "rejected_documents_count": document_stats.get("rejected_documents_count", 0),
                    "approved_documents_count": document_stats.get("approved_documents_count", 0),
                    "submissions_count": log_stats.get("submissions_count", 0),
                    "last_activity_at": get_latest_dashboard_timestamp(
                        log_stats.get("last_audit_log_at"),
                        document_stats.get("last_document_created_at"),
                        dossier_stats.get("last_dossier_created_at"),
                    ),
                }
            )

        data_entry_performance_rows.sort(
            key=lambda item: (
                -item["documents_created_count"],
                -item["dossiers_created_count"],
                -item["submissions_count"],
                item["display_name"],
                item["user_id"],
            )
        )

        auditors = list(
            operational_users.filter(role=UserRole.AUDITOR).order_by("first_name", "last_name", "username", "id")
        )
        assigned_data_entry_stats = {
            item["assigned_auditor_id"]: item["assigned_data_entry_count"]
            for item in operational_users.filter(role=UserRole.DATA_ENTRY, assigned_auditor__isnull=False)
            .values("assigned_auditor_id")
            .annotate(assigned_data_entry_count=Count("id"))
        }
        auditor_scope_stats = {
            item["created_by__assigned_auditor_id"]: item
            for item in Document.objects.filter(
                is_deleted=False,
                created_by__role=UserRole.DATA_ENTRY,
                created_by__assigned_auditor__isnull=False,
            )
            .values("created_by__assigned_auditor_id")
            .annotate(
                pending_documents_in_scope=Count(
                    "id",
                    filter=Q(status=DocumentStatus.PENDING),
                ),
                rejected_documents_in_scope=Count(
                    "id",
                    filter=Q(status=DocumentStatus.REJECTED),
                ),
                last_scoped_document_activity_at=Max("updated_at"),
            )
        }
        auditor_review_log_stats = {
            item["user_id"]: item
            for item in AuditLog.objects.filter(
                user__role=UserRole.AUDITOR,
                user__is_superuser=False,
                entity_type="document",
            )
            .values("user_id")
            .annotate(
                reviewed_documents_count=Count(
                    "id",
                    filter=Q(action__in=[AuditAction.APPROVE, AuditAction.REJECT]),
                ),
                approved_by_auditor_count=Count("id", filter=Q(action=AuditAction.APPROVE)),
                rejected_by_auditor_count=Count("id", filter=Q(action=AuditAction.REJECT)),
                last_audit_log_at=Max("created_at"),
            )
        }
        auditor_reviewed_document_stats = {
            item["reviewed_by_id"]: item
            for item in Document.objects.filter(reviewed_by__role=UserRole.AUDITOR)
            .values("reviewed_by_id")
            .annotate(last_reviewed_at=Max("reviewed_at"))
        }

        auditor_performance_rows = []
        for auditor in auditors:
            scope_stats = auditor_scope_stats.get(auditor.id, {})
            review_log_stats = auditor_review_log_stats.get(auditor.id, {})
            reviewed_document_stats = auditor_reviewed_document_stats.get(auditor.id, {})
            auditor_performance_rows.append(
                {
                    "user_id": auditor.id,
                    "username": auditor.username,
                    "display_name": get_user_display_name(auditor),
                    "assigned_data_entry_count": assigned_data_entry_stats.get(auditor.id, 0),
                    "pending_documents_in_scope": scope_stats.get("pending_documents_in_scope", 0),
                    "rejected_documents_in_scope": scope_stats.get("rejected_documents_in_scope", 0),
                    "reviewed_documents_count": review_log_stats.get("reviewed_documents_count", 0),
                    "approved_by_auditor_count": review_log_stats.get("approved_by_auditor_count", 0),
                    "rejected_by_auditor_count": review_log_stats.get("rejected_by_auditor_count", 0),
                    "last_activity_at": get_latest_dashboard_timestamp(
                        review_log_stats.get("last_audit_log_at"),
                        reviewed_document_stats.get("last_reviewed_at"),
                        scope_stats.get("last_scoped_document_activity_at"),
                    ),
                }
            )

        auditor_performance_rows.sort(
            key=lambda item: (
                -(item["pending_documents_in_scope"] + item["rejected_documents_in_scope"]),
                -item["reviewed_documents_count"],
                item["display_name"],
                item["user_id"],
            )
        )

        admin_review_activity = AdminDashboardAdminReviewActivitySerializer(
            AuditLog.objects.filter(
                user__role=UserRole.ADMIN,
                entity_type="document",
                action__in=[AuditAction.APPROVE, AuditAction.REJECT],
            ).aggregate(
                approved_by_admin_count=Count("id", filter=Q(action=AuditAction.APPROVE)),
                rejected_by_admin_count=Count("id", filter=Q(action=AuditAction.REJECT)),
                latest_admin_review_at=Max("created_at"),
            )
        ).data

        documents_by_status_items = [
            {"key": "draft", "label": "المسودات", "value": summary["draft_documents"], "tone": "neutral"},
            {"key": "pending", "label": "قيد المراجعة", "value": summary["pending_documents"], "tone": "warning"},
            {"key": "rejected", "label": "المرفوضة", "value": summary["rejected_documents"], "tone": "danger"},
            {"key": "approved", "label": "المعتمدة", "value": summary["approved_documents"], "tone": "success"},
        ]
        documents_created_counts_by_date = {
            item["day"]: item["value"]
            for item in visible_documents.filter(created_at__date__gte=chart_start_date)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(value=Count("id"))
        }
        review_decision_counts = (
            AuditLog.objects.filter(
                entity_type="document",
                action__in=[AuditAction.APPROVE, AuditAction.REJECT],
                created_at__date__gte=chart_start_date,
            )
            .annotate(day=TruncDate("created_at"))
            .values("day", "action")
            .annotate(value=Count("id"))
        )
        approvals_by_date = {}
        rejections_by_date = {}
        for item in review_decision_counts:
            if item["action"] == AuditAction.APPROVE:
                approvals_by_date[item["day"]] = item["value"]
            elif item["action"] == AuditAction.REJECT:
                rejections_by_date[item["day"]] = item["value"]

        top_data_entry_by_created_documents = [
            {
                "user_id": item["user_id"],
                "label": item["display_name"],
                "username": item["username"],
                "assigned_auditor_name": item["assigned_auditor_name"],
                "value": item["documents_created_count"],
                "documents_created_count": item["documents_created_count"],
                "dossiers_created_count": item["dossiers_created_count"],
                "submissions_count": item["submissions_count"],
            }
            for item in data_entry_performance_rows[:DASHBOARD_TOP_ITEMS_LIMIT]
        ]
        top_data_entry_by_review_backlog = [
            {
                "user_id": item["user_id"],
                "label": item["display_name"],
                "username": item["username"],
                "assigned_auditor_name": item["assigned_auditor_name"],
                "pending_documents_count": item["pending_documents_count"],
                "rejected_documents_count": item["rejected_documents_count"],
                "draft_documents_count": item["draft_documents_count"],
                "value": item["pending_documents_count"] + item["rejected_documents_count"],
            }
            for item in sorted(
                data_entry_performance_rows,
                key=lambda row: (
                    -(row["pending_documents_count"] + row["rejected_documents_count"]),
                    -row["draft_documents_count"],
                    row["display_name"],
                    row["user_id"],
                ),
            )[:DASHBOARD_TOP_ITEMS_LIMIT]
        ]
        top_auditors_by_review_workload = [
            {
                "user_id": item["user_id"],
                "label": item["display_name"],
                "username": item["username"],
                "assigned_data_entry_count": item["assigned_data_entry_count"],
                "pending_documents_in_scope": item["pending_documents_in_scope"],
                "rejected_documents_in_scope": item["rejected_documents_in_scope"],
                "reviewed_documents_count": item["reviewed_documents_count"],
                "approved_by_auditor_count": item["approved_by_auditor_count"],
                "rejected_by_auditor_count": item["rejected_by_auditor_count"],
                "value": item["pending_documents_in_scope"] + item["rejected_documents_in_scope"],
            }
            for item in auditor_performance_rows[:DASHBOARD_TOP_ITEMS_LIMIT]
        ]

        charts = {
            "documents_by_status": {
                "chart_type": "donut",
                "total": summary["total_active_documents"],
                "items": documents_by_status_items,
            },
            "documents_created_over_time": {
                "chart_type": "bar",
                "window_days": DASHBOARD_CHART_WINDOW_DAYS,
                "items": build_dashboard_daily_count_series(
                    start_date=chart_start_date,
                    window_days=DASHBOARD_CHART_WINDOW_DAYS,
                    count_by_date=documents_created_counts_by_date,
                ),
            },
            "approvals_rejections_over_time": {
                "chart_type": "grouped_bar",
                "window_days": DASHBOARD_CHART_WINDOW_DAYS,
                "items": build_dashboard_daily_review_series(
                    start_date=chart_start_date,
                    window_days=DASHBOARD_CHART_WINDOW_DAYS,
                    approved_by_date=approvals_by_date,
                    rejected_by_date=rejections_by_date,
                ),
            },
            "top_data_entry_by_created_documents": {
                "chart_type": "ranked_bar",
                "items": top_data_entry_by_created_documents,
            },
            "top_data_entry_by_review_backlog": {
                "chart_type": "stacked_bar",
                "items": top_data_entry_by_review_backlog,
            },
            "top_auditors_by_review_workload": {
                "chart_type": "stacked_bar",
                "items": top_auditors_by_review_workload,
            },
        }

        recent_documents_queryset = visible_documents.select_related("dossier", "doc_type", "created_by", "reviewed_by")
        recent_activity = {
            "latest_pending_documents": AdminDashboardRecentDocumentSerializer(
                recent_documents_queryset.filter(status=DocumentStatus.PENDING).order_by("-submitted_at", "-created_at", "-id")[
                    :RECENT_DASHBOARD_ITEMS_LIMIT
                ],
                many=True,
            ).data,
            "latest_rejected_documents": AdminDashboardRecentDocumentSerializer(
                recent_documents_queryset.filter(status=DocumentStatus.REJECTED).order_by("-reviewed_at", "-updated_at", "-id")[
                    :RECENT_DASHBOARD_ITEMS_LIMIT
                ],
                many=True,
            ).data,
            "latest_approved_documents": AdminDashboardRecentDocumentSerializer(
                recent_documents_queryset.filter(status=DocumentStatus.APPROVED).order_by("-reviewed_at", "-updated_at", "-id")[
                    :RECENT_DASHBOARD_ITEMS_LIMIT
                ],
                many=True,
            ).data,
            "latest_audit_log_events": AdminDashboardAuditEventSerializer(
                visible_audit_logs.order_by("-created_at", "-id")[:RECENT_DASHBOARD_ITEMS_LIMIT],
                many=True,
            ).data,
        }

        return Response(
            {
                "summary": summary,
                "workflow": workflow,
                "user_activity": user_activity,
                "employee_tracking": {
                    "data_entry_performance": AdminDashboardDataEntryPerformanceSerializer(
                        data_entry_performance_rows,
                        many=True,
                    ).data,
                    "auditor_performance": AdminDashboardAuditorPerformanceSerializer(
                        auditor_performance_rows,
                        many=True,
                    ).data,
                    "admin_review_activity": admin_review_activity,
                },
                "charts": charts,
                "recent_activity": recent_activity,
            },
            status=status.HTTP_200_OK,
        )


class AuditLogPagination(PageNumberPagination):
    page_size = 20


def get_scoped_workflow_document_or_404(*, request, pk, queryset, workflow_action):
    document = queryset.filter(pk=pk).first()
    if document is not None:
        return document

    existing_document = Document.objects.filter(pk=pk).first()
    if existing_document is not None:
        log_document_workflow_access_denied(
            user=request.user,
            workflow_action=workflow_action,
            request=request,
            document=existing_document,
            reason="Document is outside the permitted workflow scope.",
        )

    raise Http404


class DocumentSubmitAPIView(APIView):
    permission_classes = [IsAuthenticated, DocumentWorkflowPermission]
    workflow_action = "submit"

    def post(self, request, pk, *args, **kwargs):
        document = get_scoped_workflow_document_or_404(
            request=request,
            pk=pk,
            queryset=get_document_submit_scope_queryset_for_user(request.user).select_related("created_by"),
            workflow_action=self.workflow_action,
        )
        try:
            document = submit_document(actor=request.user, document=document)
        except WorkflowError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DocumentSummarySerializer(document).data, status=status.HTTP_200_OK)


class DocumentApproveAPIView(APIView):
    permission_classes = [IsAuthenticated, DocumentWorkflowPermission]
    workflow_action = "approve"

    def post(self, request, pk, *args, **kwargs):
        document = get_scoped_workflow_document_or_404(
            request=request,
            pk=pk,
            queryset=get_document_review_scope_queryset_for_user(request.user).select_related("created_by"),
            workflow_action=self.workflow_action,
        )
        try:
            document = approve_document(actor=request.user, document=document)
        except WorkflowError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DocumentSummarySerializer(document).data, status=status.HTTP_200_OK)


class DocumentRejectAPIView(APIView):
    permission_classes = [IsAuthenticated, DocumentWorkflowPermission]
    workflow_action = "reject"

    def post(self, request, pk, *args, **kwargs):
        serializer = DocumentRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = get_scoped_workflow_document_or_404(
            request=request,
            pk=pk,
            queryset=get_document_review_scope_queryset_for_user(request.user).select_related("created_by"),
            workflow_action=self.workflow_action,
        )
        try:
            document = reject_document(
                actor=request.user,
                document=document,
                rejection_reason=serializer.validated_data["rejection_reason"],
            )
        except WorkflowError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DocumentSummarySerializer(document).data, status=status.HTTP_200_OK)


class DocumentSoftDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated, DocumentWorkflowPermission]
    workflow_action = "soft_delete"

    def post(self, request, pk, *args, **kwargs):
        document = get_scoped_workflow_document_or_404(
            request=request,
            pk=pk,
            queryset=get_document_soft_delete_scope_queryset_for_user(request.user).select_related("created_by"),
            workflow_action=self.workflow_action,
        )
        try:
            document = soft_delete_document(actor=request.user, document=document)
        except WorkflowError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DocumentSummarySerializer(document).data, status=status.HTTP_200_OK)


class DocumentRestoreAPIView(APIView):
    permission_classes = [IsAuthenticated, DocumentWorkflowPermission]
    workflow_action = "restore"

    def post(self, request, pk, *args, **kwargs):
        document = get_scoped_workflow_document_or_404(
            request=request,
            pk=pk,
            queryset=get_document_restore_scope_queryset_for_user(request.user),
            workflow_action=self.workflow_action,
        )
        try:
            document = restore_document(actor=request.user, document=document)
        except WorkflowError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DocumentSummarySerializer(document).data, status=status.HTTP_200_OK)


class AuditLogListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, AuditLogPermission]
    serializer_class = AuditLogSerializer
    pagination_class = AuditLogPagination

    def get_queryset(self):
        queryset = exclude_emergency_only_audit_logs(get_audit_log_visibility_queryset(self.request.user))
        queryset = apply_audit_log_filters(queryset, self.request.query_params)
        queryset = annotate_audit_log_human_fields(queryset)
        queryset = apply_audit_log_search(queryset, self.request.query_params)
        return queryset.order_by("-created_at", "-id")


class AuditLogRetrieveAPIView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, AuditLogPermission]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        return annotate_audit_log_human_fields(
            exclude_emergency_only_audit_logs(get_audit_log_visibility_queryset(self.request.user))
        )


class UserManagementListCreateAPIView(generics.ListCreateAPIView):
    """Admin-only endpoint for listing and creating users."""
    permission_classes = [IsAuthenticated, AdminOnlyPermission]
    serializer_class = UserManagementSerializer
    pagination_class = StandardListPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering_fields = ["username", "role", "date_joined"]
    ordering = ["-date_joined"]

    def get_queryset(self):
        queryset = get_operational_user_queryset().select_related("assigned_auditor").order_by("-date_joined", "-id")

        role = self.request.query_params.get("role")
        if role:
            queryset = queryset.filter(role=role)

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            lowered = is_active.lower()
            if lowered in {"true", "1"}:
                queryset = queryset.filter(is_active=True)
            elif lowered in {"false", "0"}:
                queryset = queryset.filter(is_active=False)

        assigned_auditor = self.request.query_params.get("assigned_auditor")
        if assigned_auditor:
            if assigned_auditor.isdigit():
                queryset = queryset.filter(assigned_auditor_id=int(assigned_auditor))
            elif assigned_auditor == "null":
                queryset = queryset.filter(assigned_auditor__isnull=True)

        return queryset


class UserManagementRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Admin-only endpoint for retrieving, updating and deleting users."""
    permission_classes = [IsAuthenticated, AdminOnlyPermission]
    serializer_class = UserManagementSerializer
    queryset = get_operational_user_queryset().select_related("assigned_auditor")


class AuditorReviewQueueAPIView(generics.ListAPIView):
    """Auditor and Admin endpoint for pending documents."""
    permission_classes = [IsAuthenticated, DocumentPermission]
    serializer_class = DocumentSummarySerializer
    pagination_class = StandardListPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["doc_number", "doc_name", "dossier__file_number"]
    ordering_fields = ["created_at", "dossier__file_number"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            get_review_queue_queryset_for_user(self.request.user)
            .select_related("dossier", "doc_type", "created_by")
            .order_by("-created_at", "-id")
        )
