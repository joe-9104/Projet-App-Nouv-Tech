from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.middleware.csrf import get_token
from django.utils.crypto import get_random_string
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    GoogleLoginSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)


User = get_user_model()


def user_payload(user):
    return UserSerializer(user).data


class CsrfView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({'csrfToken': get_token(request)})


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.save()
        login(request, user)
        return Response({'user': user_payload(user)}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': 'Invalid credentials.'}, status=status.HTTP_400_BAD_REQUEST)
        email = serializer.validated_data['email'].strip().lower()
        password = serializer.validated_data['password']
        user = User.objects.filter(email__iexact=email).first()
        authenticated = authenticate(request, username=user.username, password=password) if user else None
        if authenticated is None or not authenticated.is_active:
            return Response({'error': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, authenticated)
        return Response({'user': user_payload(authenticated)})


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({'detail': 'Logged out.'})


class MeView(APIView):
    def get(self, request):
        return Response({'user': user_payload(request.user)})


class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': 'Invalid Google credential.'}, status=status.HTTP_400_BAD_REQUEST)
        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        if not client_id:
            return Response({'error': 'Google OAuth is not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            identity = id_token.verify_oauth2_token(
                serializer.validated_data['credential'],
                google_requests.Request(),
                client_id,
            )
        except Exception:
            return Response({'error': 'Invalid or expired Google credential.'}, status=status.HTTP_401_UNAUTHORIZED)

        email = identity.get('email')
        email_verified = identity.get('email_verified') is True
        if not email or not email_verified:
            return Response({'error': 'A verified Google email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        email = email.strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            if not user.is_active:
                return Response({'error': 'Account is disabled.'}, status=status.HTTP_403_FORBIDDEN)
        else:
            username = email
            suffix = 1
            while User.objects.filter(username=username).exists():
                username = f'{email}_{suffix}'
                suffix += 1
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=identity.get('given_name', ''),
                last_name=identity.get('family_name', ''),
                password=get_random_string(64),
            )

        login(request, user)
        return Response({'user': user_payload(user)})
