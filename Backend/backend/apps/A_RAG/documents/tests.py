import io
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import Document, DocumentFigure, ExtractedDocument
from .normalizer import DocumentNormalizer
from .services import DocumentLifecycleService
from .services.extraction import ExtractionService
from .storage_figures import FigureStorageService
from .validators import MAX_FILE_SIZE, ValidationError


# ==============================================================================
# DOC-01: Modèle, Cycle de vie et Import PDF
# ==============================================================================

class DocumentModelTest(TestCase):
    """
    Vérification de la création du modèle Document et des valeurs par défaut.
    """
    def test_document_creation(self):
        user = User.objects.create_user(username='testuser')
        doc = Document.objects.create(
            original_filename='test.pdf',
            file_data=b'%PDF-1.4 binary data',
            owner=user
        )
        self.assertEqual(doc.status, Document.Status.PENDING)
        self.assertEqual(doc.original_filename, 'test.pdf')
        self.assertEqual(str(doc), 'test.pdf (pending)')


class DocumentLifecycleTest(TestCase):
    """
    Vérification des transitions de la machine d'états DocumentLifecycleService.
    """
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
        # pending -> ready (interdit, doit passer par processing)
        with self.assertRaises(ValidationError):
            DocumentLifecycleService.transition_to(self.doc, Document.Status.READY)

    def test_error_and_retry_transitions(self):
        # pending -> error
        DocumentLifecycleService.transition_to(self.doc, Document.Status.ERROR)
        self.assertEqual(self.doc.status, Document.Status.ERROR)

        # error -> processing (retry allowed)
        DocumentLifecycleService.transition_to(self.doc, Document.Status.PROCESSING)
        self.assertEqual(self.doc.status, Document.Status.PROCESSING)


class DocumentUploadAPITest(TestCase):
    """
    Vérification de l'endpoint d'import DOC-01: /api/documents/upload/.
    """
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='password')

    def test_upload_success(self):
        uploaded_pdf = SimpleUploadedFile('test.pdf', b'%PDF-1.4 binary content', content_type='application/pdf')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_pdf}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(Document.objects.first().status, Document.Status.PENDING)

    def test_upload_no_file(self):
        response = self.client.post('/api/documents/upload/', {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_non_pdf(self):
        uploaded_txt = SimpleUploadedFile('test.txt', b'Just some text', content_type='text/plain')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_txt}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('extension', response.data['error'])

    def test_upload_invalid_pdf_signature(self):
        uploaded_fake_pdf = SimpleUploadedFile('fake.pdf', b'Not a PDF content', content_type='application/pdf')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_fake_pdf}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('content is not a valid PDF', response.data['error'])

    def test_upload_empty_file(self):
        uploaded_empty = SimpleUploadedFile('empty.pdf', b'', content_type='application/pdf')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_empty}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(any('empty' in str(err) for err in response.data['error'].get('file', [])))

    def test_upload_oversized_file(self):
        large_content = b'a' * (MAX_FILE_SIZE + 100)
        uploaded_large = SimpleUploadedFile('large.pdf', large_content, content_type='application/pdf')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_large}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('exceeds the maximum limit', response.data['error'])

    def test_upload_ownership_unauthenticated(self):
        self.client.logout()
        uploaded_pdf = SimpleUploadedFile('test.pdf', b'%PDF-1.4 binary content', content_type='application/pdf')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_pdf}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        doc = Document.objects.first()
        self.assertIsNone(doc.owner)

    def test_upload_ownership_authenticated(self):
        self.client.force_authenticate(user=self.user)
        uploaded_pdf = SimpleUploadedFile('auth_test.pdf', b'%PDF-1.4 binary content', content_type='application/pdf')
        response = self.client.post('/api/documents/upload/', {'file': uploaded_pdf}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        doc = Document.objects.get(id=response.data['id'])
        self.assertEqual(doc.owner, self.user)


# ==============================================================================
# DOC-02: Extraction, Normalisation et Stockage des Figures
# ==============================================================================

class DocumentNormalizerTest(TestCase):
    """
    Vérification de la normalisation des sorties de MinerU vers le schéma interne stable 1.0.
    """
    def setUp(self):
        self.normalizer = DocumentNormalizer()

    def test_normalize_schema_and_blocks(self):
        middle_data = {
            "metadata": {
                "title": "Document de Test",
                "author": "Auteur Test",
                "language": "fr",
                "page_count": 1,
                "producer": "PyPDF"
            },
            "pages": [
                {
                    "page_idx": 0,
                    "dimensions": [595.0, 842.0],
                    "blocks": [
                        {
                            "index": 0,
                            "type": "title",
                            "bbox": [50, 50, 500, 80],
                            "level": 1,
                            "content": "Chapitre 1 : Introduction"
                        },
                        {
                            "index": 1,
                            "type": "text",
                            "bbox": [50, 90, 500, 200],
                            "level": 0,
                            "content": "Contenu du premier paragraphe."
                        }
                    ]
                }
            ]
        }
        structured_data = {"pages": []}

        normalized = self.normalizer.normalize(middle_data, structured_data)

        self.assertEqual(normalized["schema_version"], "1.0")
        self.assertEqual(normalized["metadata"]["title"], "Document de Test")
        self.assertEqual(normalized["metadata"]["author"], "Auteur Test")
        self.assertEqual(len(normalized["pages"]), 1)

        page0 = normalized["pages"][0]
        self.assertEqual(page0["page_index"], 0)
        self.assertEqual(page0["dimensions"], [595.0, 842.0])
        self.assertEqual(len(page0["blocks"]), 2)

        block0 = page0["blocks"][0]
        self.assertEqual(block0["source_index"], 0)
        self.assertEqual(block0["type"], "title")
        self.assertEqual(block0["level"], 1)
        self.assertEqual(block0["bbox"], [50, 50, 500, 80])
        self.assertEqual(block0["content"], "Chapitre 1 : Introduction")


class FigureStorageServiceTest(TestCase):
    """
    Vérification du décodage Base64 et du stockage privé des figures.
    """
    def setUp(self):
        self.service = FigureStorageService()
        self.created_paths = []
        import os
        os.makedirs(default_storage.path('private_figures'), exist_ok=True)

    def tearDown(self):
        for path in self.created_paths:
            if default_storage.exists(path):
                default_storage.delete(path)

    def test_save_figure_png_with_data_uri(self):
        # 1x1 transparent PNG in base64
        base64_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        path = self.service.save_figure(base64_png, "image/png")
        self.created_paths.append(path)

        self.assertTrue(path.startswith("private_figures"))
        self.assertTrue(path.endswith(".png"))
        self.assertTrue(default_storage.exists(path))

    def test_mime_type_extension_mapping(self):
        self.assertEqual(self.service._get_extension_from_mime('image/jpeg'), '.jpg')
        self.assertEqual(self.service._get_extension_from_mime('image/png'), '.png')
        self.assertEqual(self.service._get_extension_from_mime('image/gif'), '.gif')
        self.assertEqual(self.service._get_extension_from_mime('image/webp'), '.webp')
        self.assertEqual(self.service._get_extension_from_mime('application/octet-stream'), '.bin')


class ExtractionServiceTest(TestCase):
    """
    Vérification de l'orchestration du service d'extraction (sans appel externe réel).
    """
    def setUp(self):
        self.user = User.objects.create_user(username='raguser', password='password')
        self.doc = Document.objects.create(
            original_filename='cours_rag.pdf',
            file_data=b'%PDF-1.4 simulated pdf data',
            status=Document.Status.PENDING,
            owner=self.user
        )

    def test_process_document_success(self):
        mock_middle = {
            "metadata": {"title": "Cours RAG", "page_count": 1},
            "pages": [
                {
                    "page_idx": 0,
                    "dimensions": [500, 700],
                    "blocks": [{"index": 0, "type": "text", "content": "RAG concept"}]
                }
            ]
        }
        mock_structured = {
            "pages": [
                {
                    "blocks": [
                        {
                            "type": "image",
                            "image_source": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                            "caption": "Schéma RAG",
                            "bbox": [10, 20, 200, 150],
                            "index": 1
                        }
                    ]
                }
            ]
        }

        service = ExtractionService()
        with patch.object(service.adapter, 'extract', return_value=(mock_middle, mock_structured)), \
             patch.object(service.figure_storage, 'save_figure', return_value="private_figures/fig_mock.png"):

            ext_doc = service.process_document(self.doc.id)

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, Document.Status.READY)
        self.assertEqual(ext_doc.document, self.doc)
        self.assertEqual(ext_doc.extraction_metadata["engine"], "MinerU")
        self.assertEqual(ext_doc.figures.count(), 1)

        figure = ext_doc.figures.first()
        self.assertEqual(figure.storage_path, "private_figures/fig_mock.png")
        self.assertEqual(figure.caption, "Schéma RAG")

    def test_process_document_failure_transitions_to_error(self):
        service = ExtractionService()
        with patch.object(service.adapter, 'extract', side_effect=RuntimeError("MinerU processing failure")):
            with self.assertRaises(RuntimeError):
                service.process_document(self.doc.id)

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, Document.Status.ERROR)


# ==============================================================================
# DOC-03: Liste des documents et de leur état
# ==============================================================================

class DocumentListAPITest(TestCase):
    """
    Tests de la liste documentaire (DOC-03 Section A) :
    1. Récupération par un utilisateur authentifié.
    2. Isolation stricte des documents entre utilisateurs.
    3. Conformité exacte des métadonnées avec le contrat d'API.
    4. Exposition correcte des 4 états (pending, processing, ready, error).
    5. Tri chronologique décroissant (du plus récent au plus ancien).
    6. Pagination fonctionnelle.
    """
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='user_alice', password='password123')
        self.other_user = User.objects.create_user(username='user_bob', password='password123')
        self.client.force_authenticate(user=self.user)

    def test_authenticated_user_can_list_own_documents(self):
        """Cas 1 : Un utilisateur authentifié peut récupérer sa liste de documents."""
        Document.objects.create(
            original_filename='doc1.pdf',
            file_data=b'%PDF-1.4 data1',
            status=Document.Status.READY,
            owner=self.user
        )
        Document.objects.create(
            original_filename='doc2.pdf',
            file_data=b'%PDF-1.4 data2',
            status=Document.Status.PENDING,
            owner=self.user
        )

        response = self.client.get('/api/documents/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['results']), 2)

    def test_list_contains_only_documents_belonging_to_authenticated_user(self):
        """Cas 2 : La liste contient uniquement les documents appartenant à cet utilisateur."""
        # Documents pour Alice
        alice_doc1 = Document.objects.create(
            original_filename='alice_notes.pdf',
            file_data=b'%PDF-1.4 data',
            status=Document.Status.READY,
            owner=self.user
        )
        alice_doc2 = Document.objects.create(
            original_filename='alice_exam.pdf',
            file_data=b'%PDF-1.4 data',
            status=Document.Status.PENDING,
            owner=self.user
        )
        # Documents pour Bob
        bob_doc1 = Document.objects.create(
            original_filename='bob_confidential.pdf',
            file_data=b'%PDF-1.4 secret',
            status=Document.Status.READY,
            owner=self.other_user
        )
        bob_doc2 = Document.objects.create(
            original_filename='bob_grades.pdf',
            file_data=b'%PDF-1.4 grades',
            status=Document.Status.PROCESSING,
            owner=self.other_user
        )

        # Alice consulte ses documents
        response_alice = self.client.get('/api/documents/')
        self.assertEqual(response_alice.status_code, status.HTTP_200_OK)
        alice_ids = [item['id'] for item in response_alice.data['results']]
        self.assertEqual(len(alice_ids), 2)
        self.assertIn(str(alice_doc1.id), alice_ids)
        self.assertIn(str(alice_doc2.id), alice_ids)
        self.assertNotIn(str(bob_doc1.id), alice_ids)
        self.assertNotIn(str(bob_doc2.id), alice_ids)

        # Bob consulte ses documents
        self.client.force_authenticate(user=self.other_user)
        response_bob = self.client.get('/api/documents/')
        self.assertEqual(response_bob.status_code, status.HTTP_200_OK)
        bob_ids = [item['id'] for item in response_bob.data['results']]
        self.assertEqual(len(bob_ids), 2)
        self.assertIn(str(bob_doc1.id), bob_ids)
        self.assertIn(str(bob_doc2.id), bob_ids)
        self.assertNotIn(str(alice_doc1.id), bob_ids)
        self.assertNotIn(str(alice_doc2.id), bob_ids)

    def test_response_exposes_exact_metadata_per_api_contract(self):
        """Cas 3 : La réponse expose exactement les métadonnées prévues par le contrat API."""
        doc = Document.objects.create(
            original_filename='contract_check.pdf',
            file_data=b'%PDF-1.4 binary data',
            status=Document.Status.READY,
            owner=self.user
        )

        response = self.client.get('/api/documents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

        item = response.data['results'][0]
        expected_fields = {'id', 'original_filename', 'status', 'created_at', 'updated_at'}
        self.assertEqual(set(item.keys()), expected_fields)

        # Validation des types et formats
        self.assertEqual(uuid.UUID(item['id']), doc.id)
        self.assertEqual(item['original_filename'], 'contract_check.pdf')
        self.assertEqual(item['status'], 'ready')
        self.assertIsInstance(item['created_at'], str)
        self.assertIsInstance(item['updated_at'], str)

        # Vérification qu'aucune donnée technique ou d'isolation n'est divulguée
        self.assertNotIn('file_data', item)
        self.assertNotIn('owner', item)
        self.assertNotIn('owner_id', item)
        self.assertNotIn('extracted_version', item)

    def test_all_four_states_properly_exposed(self):
        """Cas 4 : Les quatre états (pending, processing, ready, error) sont correctement exposés."""
        doc_pending = Document.objects.create(
            original_filename='doc_pending.pdf',
            file_data=b'%PDF-1.4 p',
            status=Document.Status.PENDING,
            owner=self.user
        )
        doc_processing = Document.objects.create(
            original_filename='doc_processing.pdf',
            file_data=b'%PDF-1.4 pr',
            status=Document.Status.PROCESSING,
            owner=self.user
        )
        doc_ready = Document.objects.create(
            original_filename='doc_ready.pdf',
            file_data=b'%PDF-1.4 r',
            status=Document.Status.READY,
            owner=self.user
        )
        doc_error = Document.objects.create(
            original_filename='doc_error.pdf',
            file_data=b'%PDF-1.4 e',
            status=Document.Status.ERROR,
            owner=self.user
        )

        response = self.client.get('/api/documents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 4)

        status_by_id = {item['id']: item['status'] for item in response.data['results']}
        self.assertEqual(status_by_id[str(doc_pending.id)], 'pending')
        self.assertEqual(status_by_id[str(doc_processing.id)], 'processing')
        self.assertEqual(status_by_id[str(doc_ready.id)], 'ready')
        self.assertEqual(status_by_id[str(doc_error.id)], 'error')

        # Ensemble exact des 4 états
        exposed_statuses = set(status_by_id.values())
        self.assertEqual(exposed_statuses, {'pending', 'processing', 'ready', 'error'})

    def test_documents_ordered_from_newest_to_oldest(self):
        """Cas 5 : Les documents sont triés du plus récent au plus ancien."""
        now = timezone.now()
        doc1 = Document.objects.create(
            original_filename='oldest.pdf',
            file_data=b'%PDF-1.4 1',
            status=Document.Status.READY,
            owner=self.user
        )
        doc2 = Document.objects.create(
            original_filename='middle.pdf',
            file_data=b'%PDF-1.4 2',
            status=Document.Status.READY,
            owner=self.user
        )
        doc3 = Document.objects.create(
            original_filename='newest.pdf',
            file_data=b'%PDF-1.4 3',
            status=Document.Status.READY,
            owner=self.user
        )

        # Forcer des dates de création distinctes pour un test déterministe
        Document.objects.filter(pk=doc1.pk).update(created_at=now - timedelta(days=2))
        Document.objects.filter(pk=doc2.pk).update(created_at=now - timedelta(days=1))
        Document.objects.filter(pk=doc3.pk).update(created_at=now)

        response = self.client.get('/api/documents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results_ids = [item['id'] for item in response.data['results']]
        expected_ids = [str(doc3.id), str(doc2.id), str(doc1.id)]
        self.assertEqual(results_ids, expected_ids)

    def test_pagination_works_as_expected(self):
        """Cas 6 : La pagination fonctionne si elle est activée."""
        # Création de 15 documents pour tester la pagination (page_size = 10 par défaut)
        base_time = timezone.now()
        for i in range(15):
            doc = Document.objects.create(
                original_filename=f'page_doc_{i:02d}.pdf',
                file_data=b'%PDF-1.4 test',
                status=Document.Status.READY,
                owner=self.user
            )
            Document.objects.filter(pk=doc.pk).update(created_at=base_time + timedelta(minutes=i))

        # Page 1
        response_page1 = self.client.get('/api/documents/')
        self.assertEqual(response_page1.status_code, status.HTTP_200_OK)
        self.assertEqual(response_page1.data['count'], 15)
        self.assertEqual(len(response_page1.data['results']), 10)
        self.assertIsNotNone(response_page1.data['next'])
        self.assertIsNone(response_page1.data['previous'])

        # Page 2
        response_page2 = self.client.get('/api/documents/?page=2')
        self.assertEqual(response_page2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_page2.data['results']), 5)
        self.assertIsNone(response_page2.data['next'])
        self.assertIsNotNone(response_page2.data['previous'])

        # Page size personnalisée (?page_size=5)
        response_custom_size = self.client.get('/api/documents/?page_size=5')
        self.assertEqual(response_custom_size.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_custom_size.data['results']), 5)

        # Taille maximale plafonnée à max_page_size (100)
        response_max_size = self.client.get('/api/documents/?page_size=200')
        self.assertEqual(response_max_size.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_max_size.data['results']), 15)

    def test_empty_list_for_user_with_no_documents(self):
        """Un utilisateur sans document reçoit une liste vide avec un count de 0."""
        response = self.client.get('/api/documents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['results'], [])


class DocumentDetailAPITest(TestCase):
    """
    Tests de la consultation individuelle (DOC-03 Section B) :
    7. Le propriétaire peut consulter individuellement son document.
    8. Un utilisateur ne peut pas consulter un document appartenant à autrui.
    9. Un document inexistant renvoie une réponse HTTP 404.
    10. Un document appartenant à autrui renvoie également une réponse HTTP 404 neutre.
    """
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='user_alice', password='password123')
        self.other_user = User.objects.create_user(username='user_bob', password='password123')
        self.client.force_authenticate(user=self.user)

        self.alice_doc = Document.objects.create(
            original_filename='alice_report.pdf',
            file_data=b'%PDF-1.4 alice private data',
            status=Document.Status.READY,
            owner=self.user
        )
        self.bob_doc = Document.objects.create(
            original_filename='bob_confidential.pdf',
            file_data=b'%PDF-1.4 bob private data',
            status=Document.Status.READY,
            owner=self.other_user
        )

    def test_owner_can_consult_own_document_individually(self):
        """Cas 7 : Le propriétaire peut consulter individuellement son document."""
        response = self.client.get(f'/api/documents/{self.alice_doc.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(self.alice_doc.id))
        self.assertEqual(response.data['original_filename'], 'alice_report.pdf')
        self.assertEqual(response.data['status'], 'ready')
        self.assertEqual(set(response.data.keys()), {'id', 'original_filename', 'status', 'created_at', 'updated_at'})

    def test_user_cannot_consult_document_belonging_to_another_user(self):
        """Cas 8 : Un utilisateur ne peut pas consulter un document appartenant à un autre utilisateur."""
        response = self.client.get(f'/api/documents/{self.bob_doc.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_document_returns_404(self):
        """Cas 9 : Un document inexistant renvoie une réponse HTTP 404."""
        nonexistent_id = uuid.uuid4()
        response = self.client.get(f'/api/documents/{nonexistent_id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_user_document_returns_same_404_as_nonexistent(self):
        """Cas 10 : Un document appartenant à un autre utilisateur renvoie également HTTP 404 (réponse neutre)."""
        nonexistent_id = uuid.uuid4()
        response_nonexistent = self.client.get(f'/api/documents/{nonexistent_id}/')
        response_other_user = self.client.get(f'/api/documents/{self.bob_doc.id}/')

        # Les deux requêtes doivent retourner HTTP 404
        self.assertEqual(response_nonexistent.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response_other_user.status_code, status.HTTP_404_NOT_FOUND)

        # La réponse ne doit pas confirmer l'existence du document d'autrui
        self.assertEqual(response_nonexistent.data, response_other_user.data)

    def test_invalid_uuid_returns_404(self):
        """Un identifiant non conforme au format UUID renvoie un 404 au niveau du routage."""
        response = self.client.get('/api/documents/invalid-uuid-string/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DocumentSecurityAndAuthTest(TestCase):
    """
    Tests de sécurité et d'authentification (DOC-03 Section C) :
    11. Accès non authentifié bloqué (HTTP 401 ou 403 selon la configuration).
    12. Absence totale de fuite d'informations sensibles (tracebacks, chemins, PDF brut, MinerU, base64, autrui).
    13. Isolation des documents orphelins (owner=None).
    14. Protection en lecture seule (rejet des méthodes d'écriture).
    """
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='user_alice', password='password123')
        self.doc_error = Document.objects.create(
            original_filename='failing_document.pdf',
            file_data=b'%PDF-1.4 raw binary confidential content /var/log/private',
            status=Document.Status.ERROR,
            owner=self.user
        )

    def test_unauthenticated_cannot_access_list(self):
        """Cas 11a : Un utilisateur non authentifié ne peut pas accéder à la liste (HTTP 401/403)."""
        self.client.logout()
        response = self.client.get('/api/documents/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_unauthenticated_cannot_access_detail(self):
        """Cas 11b : Un utilisateur non authentifié ne peut pas accéder au détail d'un document (HTTP 401/403)."""
        self.client.logout()
        response = self.client.get(f'/api/documents/{self.doc_error.id}/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_no_sensitive_technical_information_exposed(self):
        """
        Cas 12 : Aucune information technique sensible n'est exposée, y compris à l'état error.
        Vérification de l'absence de :
        - Tracebacks Python
        - Chemins physiques du serveur
        - Contenu brut du PDF
        - JSON MinerU / Extraction
        - Données Base64
        - Données utilisateur sensibles
        """
        # Création d'une version extraite et de figures associées contenant des données techniques
        ext_doc = ExtractedDocument.objects.create(
            document=self.doc_error,
            extraction_metadata={
                "engine": "MinerU",
                "version": "4.0.12",
                "server_path": "C:\\inetpub\\wwwroot\\backend\\mineru.py",
                "internal_trace": "Traceback (most recent call last): File mineru.py line 42",
            },
            normalized_content={
                "schema_version": "1.0",
                "pages": [{"page_index": 0, "blocks": [{"type": "text", "content": "secret document text"}]}]
            }
        )
        DocumentFigure.objects.create(
            extracted_document=ext_doc,
            page_index=0,
            storage_path="private_figures/fig_internal_storage.png",
            mime_type="image/png",
            caption="Internal Figure with data:image/png;base64,iVBORw0KGgoAAAANS",
            source_block_id="blk_001"
        )

        self.client.force_authenticate(user=self.user)

        # 1. Vérification sur le endpoint de détail
        response_detail = self.client.get(f'/api/documents/{self.doc_error.id}/')
        self.assertEqual(response_detail.status_code, status.HTTP_200_OK)
        detail_payload = str(response_detail.data)

        # 2. Vérification sur le endpoint de liste
        response_list = self.client.get('/api/documents/')
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        list_payload = str(response_list.data)

        # Liste des motifs interdits dans les charges utiles de sortie
        sensitive_patterns = [
            # Tracebacks et erreurs Python
            "Traceback", "File \"", "line 42", "internal_trace",
            # Chemins physiques serveur
            "C:\\inetpub", "/var/log", "private_figures",
            # Contenu brut du PDF
            "raw binary confidential content", "%PDF",
            # JSON interne MinerU
            "extraction_metadata", "normalized_content", "schema_version", "MinerU",
            # Données Base64
            "data:image", "base64", "iVBORw0KGgo",
            # Données sensibles d'authentification
            "password", "pbkdf2", "argon2"
        ]

        for pattern in sensitive_patterns:
            self.assertNotIn(pattern, detail_payload, f"Fuite d'information sensible détectée dans le détail: {pattern}")
            self.assertNotIn(pattern, list_payload, f"Fuite d'information sensible détectée dans la liste: {pattern}")

    def test_unowned_document_cannot_be_accessed_or_listed(self):
        """
        Cas 13 : Un document sans propriétaire (owner=None) ne peut être ni listé
        ni consulté individuellement par un utilisateur authentifié.
        """
        unowned_doc = Document.objects.create(
            original_filename='orphan_document.pdf',
            file_data=b'%PDF-1.4 orphan content',
            status=Document.Status.READY,
            owner=None
        )

        self.client.force_authenticate(user=self.user)

        # 1. Non présent dans la liste
        response_list = self.client.get('/api/documents/')
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        returned_ids = [item['id'] for item in response_list.data['results']]
        self.assertNotIn(str(unowned_doc.id), returned_ids)

        # 2. Non consultable en détail (404)
        response_detail = self.client.get(f'/api/documents/{unowned_doc.id}/')
        self.assertEqual(response_detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_only_methods_enforced(self):
        """
        Cas 14 : DOC-03 est strictement en lecture seule. Les requêtes POST, PUT, PATCH, DELETE
        sont rejetées avec HTTP 405 Method Not Allowed.
        """
        self.client.force_authenticate(user=self.user)

        # POST sur la collection /api/documents/
        response_post = self.client.post('/api/documents/', {'original_filename': 'malicious.pdf'})
        self.assertEqual(response_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # PUT sur le document individuel
        response_put = self.client.put(f'/api/documents/{self.doc_error.id}/', {'status': 'ready'})
        self.assertEqual(response_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # PATCH sur le document individuel
        response_patch = self.client.patch(f'/api/documents/{self.doc_error.id}/', {'status': 'ready'})
        self.assertEqual(response_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # DELETE sur le document individuel
        response_delete = self.client.delete(f'/api/documents/{self.doc_error.id}/')
        self.assertEqual(response_delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
