from django.urls import path

from core.views import (
    AuditLogListAPIView,
    AuditLogRetrieveAPIView,
    DocumentApproveAPIView,
    DocumentListAPIView,
    DocumentRejectAPIView,
    DocumentRetrieveAPIView,
    DocumentSoftDeleteAPIView,
    DocumentSubmitAPIView,
    DocumentTypeListAPIView,
    DossierListCreateAPIView,
    DossierRetrieveAPIView,
    GovernorateListAPIView,
    LogoutAPIView,
    MeAPIView,
)

urlpatterns = [
    path("auth/me/", MeAPIView.as_view(), name="auth-me"),
    path("auth/logout/", LogoutAPIView.as_view(), name="auth-logout"),
    path("audit-logs/", AuditLogListAPIView.as_view(), name="audit-log-list"),
    path("audit-logs/<int:pk>/", AuditLogRetrieveAPIView.as_view(), name="audit-log-detail"),
    path("dossiers/", DossierListCreateAPIView.as_view(), name="dossier-list-create"),
    path("dossiers/<int:pk>/", DossierRetrieveAPIView.as_view(), name="dossier-detail"),
    path("documents/", DocumentListAPIView.as_view(), name="document-list"),
    path("documents/<int:pk>/", DocumentRetrieveAPIView.as_view(), name="document-detail"),
    path("documents/<int:pk>/submit/", DocumentSubmitAPIView.as_view(), name="document-submit"),
    path("documents/<int:pk>/approve/", DocumentApproveAPIView.as_view(), name="document-approve"),
    path("documents/<int:pk>/reject/", DocumentRejectAPIView.as_view(), name="document-reject"),
    path("documents/<int:pk>/soft-delete/", DocumentSoftDeleteAPIView.as_view(), name="document-soft-delete"),
    path("governorates/", GovernorateListAPIView.as_view(), name="governorate-list"),
    path("document-types/", DocumentTypeListAPIView.as_view(), name="document-type-list"),
]

