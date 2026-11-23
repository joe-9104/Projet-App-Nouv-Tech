from django.core.exceptions import ValidationError
from rest_framework import permissions, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document
from .serializers import DocumentResponseSerializer, DocumentUploadSerializer
from .validators import validate_pdf_file


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class DocumentUploadView(APIView):
    """
    DOC-01: Endpoint to import a PDF file and create a Document record.
    """
    def post(self, request, *args, **kwargs):
        # Check if 'file' is present in request.FILES first
        if 'file' not in request.FILES:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = DocumentUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = request.FILES.get('file')

        try:
            # Validate PDF content and size
            validate_pdf_file(uploaded_file)
        except ValidationError as e:
            # Handle both single string and list of messages
            if hasattr(e, 'message') and e.message:
                message = e.message
            elif hasattr(e, 'messages') and e.messages:
                message = e.messages[0]
            else:
                message = str(e)
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        # Store file as binary in DB
        uploaded_file.seek(0)
        file_content = uploaded_file.read()

        document = Document.objects.create(
            original_filename=uploaded_file.name,
            file_data=file_content,
            status=Document.Status.PENDING,
            owner=request.user if request.user.is_authenticated else None
        )

        response_serializer = DocumentResponseSerializer(document)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DocumentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    DOC-03: Read-only ViewSet for listing and retrieving documents.

    The authenticated user consults their own documents and their processing status.
    Ownership is strictly derived from the authentication context (request.user),
    never from a client-supplied identifier.

    - List: GET /api/documents/
    - Detail: GET /api/documents/<document_id>/
    """
    serializer_class = DocumentResponseSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Strict ownership filtering: users only see their own documents.
        Unauthenticated requests yield an empty queryset.
        Documents are ordered from newest to oldest.
        """
        user = self.request.user
        if not user or not user.is_authenticated:
            return Document.objects.none()
        return Document.objects.filter(owner=user).order_by('-created_at', '-id')

    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve a single document owned by the authenticated user.
        get_object() uses get_queryset(), so accessing a document owned by
        another user or a nonexistent document raises a neutral HTTP 404
        without leaking resource existence.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
