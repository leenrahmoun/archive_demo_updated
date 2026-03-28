from pathlib import Path

from django.core.files.storage import default_storage
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
    get_document_detail_queryset_for_user,
    get_document_visibility_queryset,
    get_document_review_scope_queryset_for_user,
    get_dossier_visibility_queryset,
    get_review_queue_queryset_for_user,
)
from core.document_type_catalog import get_approved_document_type_entries, get_approved_document_type_slugs
from core.models import AuditLog, Document, DocumentStatus, DocumentType, Dossier, Governorate, User, UserRole
from core.permissions import AdminOnlyPermission, AuditLogPermission, DocumentPermission, DossierPermission, DocumentWorkflowPermission
from core.serializers import (
    AuditLogSerializer,
    DocumentCreateSerializer,
    DocumentReplaceFileSerializer,
    DocumentRejectSerializer,
    DocumentSummarySerializer,
    DocumentTypeLookupSerializer,
    DocumentUpdateSerializer,
    DossierCreateSerializer,
    DossierDetailSerializer,
    DossierListSerializer,
    GovernorateLookupSerializer,
    LogoutSerializer,
    MeSerializer,
    UserManagementSerializer,
)
from core.services.document_workflow_service import (
    WorkflowError,
    approve_document,
    reject_document,
    soft_delete_document,
    submit_document,
)


class StandardListPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


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
        queryset = get_document_visibility_queryset(self.request.user).select_related(
            "dossier",
            "doc_type",
            "created_by",
            "reviewed_by",
        )
        return apply_document_advanced_filters(queryset, self.request.query_params, self.request.user)


class DocumentRetrieveAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [DocumentPermission]

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return DocumentUpdateSerializer
        return DocumentSummarySerializer

    def get_queryset(self):
        return get_document_detail_queryset_for_user(self.request.user)


class DocumentFileAccessAPIView(APIView):
    permission_classes = [DocumentPermission]

    def get(self, request, pk, *args, **kwargs):
        document = generics.get_object_or_404(get_document_detail_queryset_for_user(request.user), pk=pk)

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
        return Response({"detail": "Logout successful."}, status=status.HTTP_200_OK)


class GovernorateListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GovernorateLookupSerializer
    queryset = Governorate.objects.filter(is_active=True).order_by("name")


class DocumentTypeListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DocumentTypeLookupSerializer

    def get_queryset(self):
        return DocumentType.objects.filter(
            is_active=True,
            slug__in=get_approved_document_type_slugs(),
        )

    def list(self, request, *args, **kwargs):
        approved_entries = get_approved_document_type_entries()
        document_types_by_slug = {
            document_type.slug: document_type
            for document_type in self.get_queryset()
        }
        payload = []

        for entry in approved_entries:
            document_type = document_types_by_slug.get(entry["slug"])
            if document_type is None:
                continue
            payload.append(
                {
                    "id": document_type.id,
                    "name": entry["name"],
                    "slug": entry["slug"],
                    "group_name": entry["group"],
                    "display_order": entry["order"],
                }
            )

        return Response(payload, status=status.HTTP_200_OK)


class AuditLogPagination(PageNumberPagination):
    page_size = 20


class DocumentSubmitAPIView(APIView):
    permission_classes = [IsAuthenticated, DocumentWorkflowPermission]
    workflow_action = "submit"

    def post(self, request, pk, *args, **kwargs):
        qs = Document.objects.filter(is_deleted=False)
        if request.user.role == UserRole.DATA_ENTRY:
            qs = qs.filter(created_by=request.user)
        document = generics.get_object_or_404(qs, pk=pk)
        try:
            document = submit_document(actor=request.user, document=document)
        except WorkflowError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DocumentSummarySerializer(document).data, status=status.HTTP_200_OK)


class DocumentApproveAPIView(APIView):
    permission_classes = [IsAuthenticated, DocumentWorkflowPermission]
    workflow_action = "approve"

    def post(self, request, pk, *args, **kwargs):
        document = generics.get_object_or_404(get_document_review_scope_queryset_for_user(request.user), pk=pk)
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
        document = generics.get_object_or_404(get_document_review_scope_queryset_for_user(request.user), pk=pk)
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
        qs = Document.objects.filter(is_deleted=False)
        if request.user.role == UserRole.DATA_ENTRY:
            qs = qs.filter(created_by=request.user)
        document = generics.get_object_or_404(qs, pk=pk)
        try:
            document = soft_delete_document(actor=request.user, document=document)
        except WorkflowError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DocumentSummarySerializer(document).data, status=status.HTTP_200_OK)


class AuditLogListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, AuditLogPermission]
    serializer_class = AuditLogSerializer
    pagination_class = AuditLogPagination

    def get_queryset(self):
        queryset = get_audit_log_visibility_queryset(self.request.user)
        queryset = apply_audit_log_filters(queryset, self.request.query_params)
        queryset = annotate_audit_log_human_fields(queryset)
        queryset = apply_audit_log_search(queryset, self.request.query_params)
        return queryset.order_by("-created_at", "-id")


class AuditLogRetrieveAPIView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, AuditLogPermission]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        return annotate_audit_log_human_fields(get_audit_log_visibility_queryset(self.request.user))


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
        queryset = User.objects.select_related("assigned_auditor").all().order_by("-date_joined", "-id")

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
    queryset = User.objects.select_related("assigned_auditor").all()


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
