from django.urls import path
from .views import DocumentUploadView, DocumentViewSet, DocumentFigureAssetView, DocumentSearchView, DocumentIndexView, DocumentFileView

urlpatterns = [
    path('upload/', DocumentUploadView.as_view(), name='document-upload'),
    path('search/', DocumentSearchView.as_view(), name='document-search'),
    path('', DocumentViewSet.as_view({'get': 'list'}), name='document-list'),
    path('<uuid:document_id>/file/', DocumentFileView.as_view(), name='document-file'),
    path('<uuid:document_id>/assets/<uuid:asset_id>', DocumentFigureAssetView.as_view(), name='document-figure-asset'),
    path('<uuid:document_id>/index/', DocumentIndexView.as_view(), name='document-index'),
    path('<uuid:pk>/', DocumentViewSet.as_view({'get': 'retrieve'}), name='document-detail'),
]
