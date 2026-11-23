import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from ..models import Document, ExtractedDocument, DocumentFigure
from . import DocumentLifecycleService
from ..adapter_mineru import MinerUAdapter
from ..normalizer import DocumentNormalizer
from ..storage_figures import FigureStorageService

logger = logging.getLogger(__name__)

class ExtractionService:
    """
    Orchestrates the extraction, normalization and persistence of a Document.
    """

    def __init__(self):
        self.adapter = MinerUAdapter()
        self.normalizer = DocumentNormalizer()
        self.figure_storage = FigureStorageService()

    def process_document(self, document_id):
        """
        Processes a document from pending -> ready.
        """
        try:
            document = Document.objects.get(id=document_id)

            # 1. Transition to processing
            DocumentLifecycleService.transition_to(document, Document.Status.PROCESSING)

            # 2. Extract using MinerU
            middle_data, structured_data = self.adapter.extract(document)

            # 3. Normalize content
            normalized_content = self.normalizer.normalize(middle_data, structured_data)

            # 4. Extract and store figures
            # We use structured_data as a source for figures as per observations
            figures_metadata = self._extract_figures(structured_data, document)

            # 5. Persist results
            with transaction.atomic():
                ext_doc = ExtractedDocument.objects.create(
                    document=document,
                    extraction_metadata={
                        "engine": "MinerU",
                        "version": "4.0.12", # Should be dynamic in production
                        "schema_version": self.normalizer.SCHEMA_VERSION,
                    },
                    normalized_content=normalized_content
                )

                for fig in figures_metadata:
                    DocumentFigure.objects.create(
                        extracted_document=ext_doc,
                        **fig
                    )

            # 6. Transition to ready
            DocumentLifecycleService.transition_to(document, Document.Status.READY)
            return ext_doc

        except Exception as e:
            logger.exception(f"Extraction failed for document {document_id}: {e}")
            try:
                # Transition to error if we have the document object
                if 'document' in locals():
                    DocumentLifecycleService.transition_to(document, Document.Status.ERROR)
            except Exception:
                pass
            raise e

    def _extract_figures(self, structured_data, document):
        """
        Processes images from structured_data and stores them.
        """
        figs = []
        pages = structured_data.get('pages', [])

        for page_idx, page in enumerate(pages):
            # Note: Structured data blocks for images vary.
            # This is a simplified loop based on provided context.
            for block in page.get('blocks', []):
                if block.get('type') == 'image':
                    image_source = block.get('image_source')
                    if not image_source:
                        continue

                    try:
                        # Figure storage handles Base64 decoding and private path
                        # Determine mime type from source or default
                        mime_type = 'image/jpeg' # Default, should be parsed from Data URI
                        if 'image/png' in image_source: mime_type = 'image/png'
                        elif 'image/gif' in image_source: mime_type = 'image/gif'
                        elif 'image/webp' in image_source: mime_type = 'image/webp'

                        path = self.figure_storage.save_figure(
                            image_source,
                            mime_type
                        )

                        figs.append({
                            "page_index": page_idx,
                            "storage_path": path,
                            "mime_type": mime_type,
                            "caption": block.get('caption'),
                            "bbox": block.get('bbox'),
                            "source_block_id": str(block.get('index', 'unknown'))
                        })
                    except Exception as e:
                        logger.warning(f"Failed to process figure in page {page_idx}: {e}")

        return figs
