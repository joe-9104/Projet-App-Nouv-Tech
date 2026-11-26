from django.urls import path

from .views import RegisterView, LoginView, LogoutView, MeView, GoogleLoginView, CsrfView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('google/', GoogleLoginView.as_view(), name='auth-google'),
    path('csrf/', CsrfView.as_view(), name='auth-csrf'),
]
