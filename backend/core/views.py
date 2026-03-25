from rest_framework import filters, generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from core.models import AuditLog, Document, DocumentType, Dossier, Governorate, UserRole
from core.permissions import AuditLogPermission, DocumentPermission, DossierPermission, DocumentWorkflowPermission
from core.serializers import (
    AuditLogSerializer,
    DocumentCreateSerializer,
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


class DossierListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [DossierPermission]
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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
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
            queryset = queryset.filter(status="approved")
        elif user.role == UserRole.AUDITOR:
            queryset = queryset.filter(status__in=["pending", "approved"])
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
                    queryset = queryset.filter(status="approved")
                elif user.role == UserRole.AUDITOR:
                    queryset = queryset.filter(status__in=["pending", "approved"])
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
        user = self.request.user
        queryset = Document.objects.filter(is_deleted=False)
        if user.role == UserRole.READER:
            return queryset.filter(status="approved")
        if user.role == UserRole.AUDITOR:
            return queryset.filter(status__in=["pending", "approved"])
        if user.role == UserRole.DATA_ENTRY:
            return queryset.filter(created_by=user)
        return queryset


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
