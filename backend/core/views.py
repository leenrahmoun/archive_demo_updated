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
from django.utils.dateparse import parse_date, parse_datetime


class StandardListPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def get_document_detail_queryset_for_user(user):
    queryset = Document.objects.filter(is_deleted=False)
    if user.role == UserRole.READER:
        return queryset.filter(status=DocumentStatus.APPROVED)
    if user.role == UserRole.AUDITOR:
        return queryset.filter(status__in=[DocumentStatus.PENDING, DocumentStatus.APPROVED])
    if user.role == UserRole.DATA_ENTRY:
        return queryset.filter(created_by=user)
    return queryset


class DossierListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [DossierPermission]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    queryset = Dossier.objects.all().order_by("-created_at", "-id")
    pagination_class = StandardListPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["file_number", "full_name", "national_id"]
    ordering_fields = ["file_number", "full_name", "created_at"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.role == UserRole.DATA_ENTRY:
            queryset = queryset.filter(created_by=user)

        query_params = self.request.query_params

        governorate = query_params.get("governorate")
        if governorate and governorate.isdigit():
            queryset = queryset.filter(governorate_id=int(governorate))

        created_by = query_params.get("created_by")
        if created_by and created_by.isdigit():
            queryset = queryset.filter(created_by_id=int(created_by))

        is_deleted = query_params.get("is_deleted")
        if is_deleted is not None:
            lowered = is_deleted.lower()
            if lowered in {"true", "1"}:
                queryset = queryset.filter(is_archived=True)
            elif lowered in {"false", "0"}:
                queryset = queryset.filter(is_archived=False)

        return queryset

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
        user = self.request.user
        queryset = Dossier.objects.all()
        if user.role == UserRole.DATA_ENTRY:
            return queryset.filter(created_by=user)
        return queryset


class DocumentListAPIView(generics.ListCreateAPIView):
    permission_classes = [DocumentPermission]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DocumentCreateSerializer
        return DocumentSummarySerializer

    pagination_class = StandardListPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["doc_number", "doc_name", "file_path"]
    ordering_fields = ["status", "created_at", "reviewed_at"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        user = self.request.user
        queryset = Document.objects.filter(is_deleted=False).order_by("-created_at", "-id")
        if user.role == UserRole.READER:
            queryset = queryset.filter(status=DocumentStatus.APPROVED)
        elif user.role == UserRole.AUDITOR:
            # Auditor sees only documents from their assigned data_entry users
            # Statuses: pending, rejected, approved (draft excluded)
            queryset = queryset.filter(
                created_by__assigned_auditor=user,
                status__in=[
                    DocumentStatus.PENDING,
                    DocumentStatus.REJECTED,
                    DocumentStatus.APPROVED,
                ],
            )
        elif user.role == UserRole.DATA_ENTRY:
            queryset = queryset.filter(created_by=user)

        query_params = self.request.query_params

        status_param = query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        doc_type = query_params.get("doc_type")
        if doc_type and doc_type.isdigit():
            queryset = queryset.filter(doc_type_id=int(doc_type))

        dossier = query_params.get("dossier")
        if dossier and dossier.isdigit():
            queryset = queryset.filter(dossier_id=int(dossier))

        created_by = query_params.get("created_by")
        if created_by and created_by.isdigit():
            queryset = queryset.filter(created_by_id=int(created_by))

        reviewed_by = query_params.get("reviewed_by")
        if reviewed_by and reviewed_by.isdigit():
            queryset = queryset.filter(reviewed_by_id=int(reviewed_by))
        elif reviewed_by == "null":
            queryset = queryset.filter(reviewed_by__isnull=True)

        is_deleted = query_params.get("is_deleted")
        if is_deleted is not None:
            lowered = is_deleted.lower()
            if lowered in {"true", "1"}:
                queryset = Document.objects.filter(is_deleted=True).order_by("-created_at", "-id")
                if user.role == UserRole.READER:
                    queryset = queryset.filter(status=DocumentStatus.APPROVED)
                elif user.role == UserRole.AUDITOR:
                    # Auditor scoped visibility for deleted documents too
                    queryset = queryset.filter(
                        created_by__assigned_auditor=user,
                        status__in=[
                            DocumentStatus.PENDING,
                            DocumentStatus.REJECTED,
                            DocumentStatus.APPROVED,
                        ],
                    )
                elif user.role == UserRole.DATA_ENTRY:
                    queryset = queryset.filter(created_by=user)
            elif lowered in {"false", "0"}:
                queryset = queryset.filter(is_deleted=False)

        return queryset


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
    queryset = DocumentType.objects.filter(is_active=True).order_by("group_name", "display_order", "id")


class AuditLogPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


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
        document = generics.get_object_or_404(Document, pk=pk, is_deleted=False)
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
        document = generics.get_object_or_404(Document, pk=pk, is_deleted=False)
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
        queryset = AuditLog.objects.select_related("user").order_by("-created_at", "-id")

        action = self.request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)

        actor = self.request.query_params.get("actor")
        if actor:
            if actor.isdigit():
                queryset = queryset.filter(user_id=int(actor))
            else:
                queryset = queryset.filter(user__username=actor)

        table_name = self.request.query_params.get("table_name")
        model = self.request.query_params.get("model")
        if table_name:
            queryset = queryset.filter(entity_type=table_name)
        if model:
            queryset = queryset.filter(entity_type=model)

        object_id = self.request.query_params.get("object_id")
        if object_id and object_id.isdigit():
            queryset = queryset.filter(entity_id=int(object_id))

        date_from = self.request.query_params.get("date_from")
        if date_from:
            parsed = parse_datetime(date_from)
            if parsed is None:
                parsed_date = parse_date(date_from)
                if parsed_date is not None:
                    queryset = queryset.filter(created_at__date__gte=parsed_date)
            else:
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
                queryset = queryset.filter(created_at__gte=parsed)

        date_to = self.request.query_params.get("date_to")
        if date_to:
            parsed = parse_datetime(date_to)
            if parsed is None:
                parsed_date = parse_date(date_to)
                if parsed_date is not None:
                    queryset = queryset.filter(created_at__date__lte=parsed_date)
            else:
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
                queryset = queryset.filter(created_at__lte=parsed)

        return queryset


class AuditLogRetrieveAPIView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, AuditLogPermission]
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.select_related("user").all()


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
        queryset = User.objects.all().order_by("-date_joined", "-id")

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
    queryset = User.objects.all()


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
        user = self.request.user
        # Admin sees all pending documents
        if user.role == UserRole.ADMIN:
            return Document.objects.filter(
                is_deleted=False,
                status=DocumentStatus.PENDING,
            ).select_related("dossier", "doc_type", "created_by").order_by("-created_at", "-id")
        # Auditor sees only pending documents from assigned data_entry users
        if user.role == UserRole.AUDITOR:
            return Document.objects.filter(
                is_deleted=False,
                created_by__assigned_auditor=user,
                status=DocumentStatus.PENDING,
            ).select_related("dossier", "doc_type", "created_by").order_by("-created_at", "-id")
        # Other roles see nothing
        return Document.objects.none()
