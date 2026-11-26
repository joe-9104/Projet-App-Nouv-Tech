from django.core.exceptions import ValidationError
from rest_framework import permissions, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404

from .models import Document, DocumentFigure
from .serializers import DocumentResponseSerializer, DocumentUploadSerializer
from .models import ExtractedDocument
from .rag_indexing import DocumentIndexingService, DocumentSearchService, IndexingError, build_visual_assets
from .validators import validate_pdf_file


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class DocumentUploadView(APIView):
    """
    DOC-01: Endpoint to import a PDF file and create a Document record.
    """
    permission_classes = [permissions.IsAuthenticated]

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
            owner=request.user
        )

        response_serializer = DocumentResponseSerializer(document)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DocumentFileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, document_id):
        document = Document.objects.filter(id=document_id, owner=request.user).first()
        if not document:
            raise Http404
        return FileResponse(
            bytes(document.file_data),
            content_type='application/pdf',
            as_attachment=True,
            filename=document.original_filename,
        )


class DocumentFigureAssetView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, document_id, asset_id):
        figure = DocumentFigure.objects.select_related(
            'extracted_document__document'
        ).filter(
            id=asset_id,
            extracted_document__document_id=document_id,
            extracted_document__document__owner=request.user,
        ).first()
        if not figure or not default_storage.exists(figure.storage_path):
            raise Http404

        file = default_storage.open(figure.storage_path, 'rb')
        response = FileResponse(file, content_type=figure.mime_type)
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class DocumentSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        document_id = request.data.get('document_id')
        query = request.data.get('query')
        page_range = request.data.get('page_range')
        top_k = request.data.get('top_k', 5)

        if not document_id or not isinstance(query, str) or not query.strip():
            return Response({'error': 'document_id and query are required.'}, status=status.HTTP_400_BAD_REQUEST)

        document = Document.objects.filter(id=document_id, owner=request.user).first()
        if not document:
            raise Http404

        try:
            top_k = int(top_k)
        except (TypeError, ValueError):
            return Response({'error': 'top_k must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
        top_k = max(1, min(top_k, 20))

        if page_range is not None:
            if not isinstance(page_range, dict):
                return Response({'error': 'page_range must contain start and end.'}, status=status.HTTP_400_BAD_REQUEST)
            start, end = page_range.get('start'), page_range.get('end')
            if start is not None:
                try:
                    start = int(start)
                except (TypeError, ValueError):
                    return Response({'error': 'page_range start must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
            if end is not None:
                try:
                    end = int(end)
                except (TypeError, ValueError):
                    return Response({'error': 'page_range end must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
            if start is not None and end is not None and start > end:
                return Response({'error': 'page_range start must not exceed end.'}, status=status.HTTP_400_BAD_REQUEST)
            page_range = {'start': start, 'end': end}

        try:
            outcome = DocumentSearchService().search(document, query.strip(), page_range, top_k)
        except IndexingError:
            return Response({'error': 'The document search service is unavailable.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        results = []
        for chunk in outcome['results']:
            results.append({
                'chunk_id': chunk.id,
                'text': chunk.text,
                'relevance_score': round(float(chunk.relevance_score), 4),
                'source': {
                    'page_start': chunk.page_start,
                    'page_end': chunk.page_end,
                    'section_title': chunk.section_title,
                    'block_ids': chunk.block_ids,
                },
                'visual_assets': build_visual_assets(chunk),
            })

        response = {'document_id': str(document_id), 'results': results}
        if outcome['status'] != 'ok':
            response['status'] = outcome['status']
        return Response(response)


class DocumentIndexView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, document_id):
        document = Document.objects.filter(id=document_id, owner=request.user).first()
        if not document:
            raise Http404
        extracted = ExtractedDocument.objects.filter(document=document).first()
        if not extracted:
            return Response({'error': 'Document is not extracted yet.'}, status=status.HTTP_409_CONFLICT)
        try:
            generation, count = DocumentIndexingService().index_document(extracted)
        except IndexingError:
            return Response({'error': 'Indexing failed; no previous index was replaced.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'document_id': str(document.id), 'generation': generation, 'chunk_count': count})


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
