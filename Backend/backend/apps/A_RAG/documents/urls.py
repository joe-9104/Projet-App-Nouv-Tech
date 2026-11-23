from django.urls import path
from .views import DocumentUploadView, DocumentViewSet

urlpatterns = [
    path('upload/', DocumentUploadView.as_view(), name='document-upload'),
    path('', DocumentViewSet.as_view({'get': 'list'}), name='document-list'),
    path('<uuid:pk>/', DocumentViewSet.as_view({'get': 'retrieve'}), name='document-detail'),
]
