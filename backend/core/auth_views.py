from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed as DRFAuthenticationFailed
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.models import AuditAction
from core.services.audit_log_service import log_user_security_event, resolve_user_from_refresh_token


User = get_user_model()


class AuditedTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        username = attrs.get(self.username_field)
        request = self.context.get("request")

        try:
            data = super().validate(attrs)
        except DRFAuthenticationFailed as exc:
            matched_user = User.objects.filter(**{self.username_field: username}).first()
            if matched_user is not None:
                log_user_security_event(
                    user=matched_user,
                    action=AuditAction.LOGIN_FAILED,
                    request=request,
                    message="Failed login attempt.",
                    reason=str(exc.detail),
                )
            raise

        log_user_security_event(
            user=self.user,
            action=AuditAction.LOGIN,
            request=request,
            message="Successful login.",
        )
        return data


class AuditedTokenObtainPairView(TokenObtainPairView):
    serializer_class = AuditedTokenObtainPairSerializer


class AuditedTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        refresh_token = request.data.get("refresh")

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            user = resolve_user_from_refresh_token(refresh_token)
            if user is not None:
                log_user_security_event(
                    user=user,
                    action=AuditAction.REFRESH_FAILED,
                    request=request,
                    message="Refresh token was rejected.",
                    reason=str(exc),
                )
            raise InvalidToken(exc.args[0]) from exc
        except DRFAuthenticationFailed as exc:
            user = resolve_user_from_refresh_token(refresh_token)
            if user is not None:
                log_user_security_event(
                    user=user,
                    action=AuditAction.REFRESH_FAILED,
                    request=request,
                    message="Refresh denied for inactive account.",
                    reason=str(exc.detail),
                )
            raise

        return Response(serializer.validated_data, status=status.HTTP_200_OK)
