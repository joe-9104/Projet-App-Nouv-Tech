from django.urls import path
from .views import DocumentUploadView, DocumentViewSet, DocumentFigureAssetView

urlpatterns = [
    path('upload/', DocumentUploadView.as_view(), name='document-upload'),
    path('', DocumentViewSet.as_view({'get': 'list'}), name='document-list'),
    path('<uuid:document_id>/assets/<uuid:asset_id>', DocumentFigureAssetView.as_view(), name='document-figure-asset'),
    path('<uuid:pk>/', DocumentViewSet.as_view({'get': 'retrieve'}), name='document-detail'),
]
