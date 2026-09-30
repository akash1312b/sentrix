from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User
from .serializers import RegisterSerializer, UserSerializer

__all__ = [
    "RegisterView", "MeView", "LoginView", "RefreshView",
]


class RegisterView(generics.CreateAPIView):
    """Sign up a new shop owner. Creates the User + their first Shop
    + an 'owner' Membership in a single transaction."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    """Return the logged-in user's profile with their shop memberships,
    so the frontend can build a shop switcher without extra calls."""

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class LoginView(TokenObtainPairView):
    """Thin wrapper kept so accounts.urls doesn't need to import
    rest_framework_simplejwt directly — keeps the dependency contained."""
    pass


class RefreshView(TokenRefreshView):
    pass
