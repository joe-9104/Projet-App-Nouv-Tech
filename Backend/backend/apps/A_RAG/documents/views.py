from rest_framework import viewsets
from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from .models import Document
from .serializers import DocumentResponseSerializer

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class DocumentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing documents.
    Ensures strict ownership filtering and standard DRF functionality.
    """
    serializer_class = DocumentResponseSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Strict ownership filtering: users only see their own documents
        user = self.request.user
        return Document.objects.filter(owner=user).order_by('-created_at')

    def retrieve(self, request, *args, **kwargs):
        # Override retrieve to ensure 404 if the document doesn't belong to the user
        # get_queryset already filters by owner, so if it's not found, 404 is naturally returned.
        return super().retrieve(request, *args, **kwargs)
