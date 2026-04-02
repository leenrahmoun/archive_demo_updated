from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


def user_has_active_account(user) -> bool:
    return bool(user and getattr(user, "is_active", False))


class ActiveAccountJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if not user_has_active_account(user):
            raise AuthenticationFailed(_("User is inactive"), code="user_inactive")

        return user
