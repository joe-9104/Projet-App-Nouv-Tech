from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import DocumentUploadSerializer, DocumentResponseSerializer
from .models import Document
from .validators import validate_pdf_file
from django.core.exceptions import ValidationError

class DocumentUploadView(APIView):
    """
    Endpoint to import a PDF file and create a Document record.
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
        # Reset pointer to read all content
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
