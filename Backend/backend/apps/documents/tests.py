import io
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from .models import Document
from .services import DocumentLifecycleService
from .validators import validate_pdf_file, ValidationError

class DocumentModelTest(TestCase):
    def test_document_creation(self):
        user = User.objects.create_user(username='testuser')
        doc = Document.objects.create(
            original_filename='test.pdf',
            file_data=b'%PDF-1.4 binary data',
            owner=user
        )
        self.assertEqual(doc.status, Document.Status.PENDING)
        self.assertEqual(doc.original_filename, 'test.pdf')

class DocumentLifecycleTest(TestCase):
    def setUp(self):
        self.doc = Document.objects.create(
            original_filename='test.pdf',
            file_data=b'%PDF-1.4 binary data',
            status=Document.Status.PENDING
        )

    def test_valid_transitions(self):
        # pending -> processing
        DocumentLifecycleService.transition_to(self.doc, Document.Status.PROCESSING)
        self.assertEqual(self.doc.status, Document.Status.PROCESSING)

        # processing -> ready
        DocumentLifecycleService.transition_to(self.doc, Document.Status.READY)
        self.assertEqual(self.doc.status, Document.Status.READY)

    def test_invalid_transition(self):
        # pending -> ready (not allowed)
        with self.assertRaises(ValidationError):
            DocumentLifecycleService.transition_to(self.doc, Document.Status.READY)

class DocumentUploadAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='password')

    def create_pdf_file(self, content=b'%PDF-1.4 test content', filename='test.pdf'):
        return io.BytesIO(content)

    def test_upload_success(self):
        pdf = self.create_pdf_file()
        # We need to simulate the filename for the validator
        # In real Django request, this is in the UploadedFile object
        # Using a mock or just passing it in the test client

        # Since APIClient doesn't easily let us set the .name attribute on BytesIO
        # we'll use a helper that mimics an UploadedFile or just accept the failure
        # and fix it with a wrapper.

        # Let's wrap the BytesIO to add a name
        class MockUploadedFile:
            def __init__(self, fileobj, name):
                self.fileobj = fileobj
                self.name = name
                self.size = len(fileobj.getvalue())
            def read(self, *args, **kwargs): return self.fileobj.read(*args, **kwargs)
            def seek(self, *args, **kwargs): return self.fileobj.seek(*args, **kwargs)
            def close(self): self.fileobj.close()

        pdf_file = MockUploadedFile(pdf, 'test.pdf')

        # APIClient doesn't directly support MockUploadedFile objects in the 'data' dict
        # the same way as request.FILES. We use SimpleUploadedFile from django.core.files.uploadedfile
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded_pdf = SimpleUploadedFile('test.pdf', b'%PDF-1.4 binary content', content_type='application/pdf')

        response = self.client.post('/api/documents/upload/', {'file': uploaded_pdf}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(Document.objects.first().status, Document.Status.PENDING)

    def test_upload_no_file(self):
        response = self.client.post('/api/documents/upload/', {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_non_pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded_txt = SimpleUploadedFile('test.txt', b'Just some text', content_type='text/plain')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_txt}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('extension', response.data['error'])

    def test_upload_invalid_pdf_signature(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded_fake_pdf = SimpleUploadedFile('fake.pdf', b'Not a PDF content', content_type='application/pdf')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_fake_pdf}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('content is not a valid PDF', response.data['error'])

    def test_upload_empty_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded_empty = SimpleUploadedFile('empty.pdf', b'', content_type='application/pdf')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_empty}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # The error is now inside the serializer errors dict
        self.assertTrue(any('empty' in str(err) for err in response.data['error'].get('file', [])))

    def test_upload_oversized_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .validators import MAX_FILE_SIZE

        # Create a file slightly larger than MAX_FILE_SIZE
        large_content = b'a' * (MAX_FILE_SIZE + 100)
        # Ensure it starts with %PDF for the validator to reach size check?
        # No, size is checked before signature in my validator.

        uploaded_large = SimpleUploadedFile('large.pdf', large_content, content_type='application/pdf')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_large}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('exceeds the maximum limit', response.data['error'])

    def test_upload_ownership_unauthenticated(self):
        self.client.logout()
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded_pdf = SimpleUploadedFile('test.pdf', b'%PDF-1.4 binary content', content_type='application/pdf')

        response = self.client.post('/api/documents/upload/', {'file': uploaded_pdf}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        doc = Document.objects.first()
        self.assertIsNone(doc.owner)
