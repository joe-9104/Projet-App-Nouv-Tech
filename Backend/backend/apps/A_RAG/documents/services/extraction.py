import logging
from django.db import transaction
from django.core.files.storage import default_storage
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

            # 4. Prepare figure files and metadata without removing a previous extraction
            figures_metadata = self._extract_figures(structured_data, document)

            # 5. Persist results atomically; only remove replaced private files after commit
            old_paths = list(ExtractedDocument.objects.filter(document=document).values_list('normalized_content', flat=True))
            replaced_paths = []
            try:
                with transaction.atomic():
                    ext_doc, _ = ExtractedDocument.objects.update_or_create(
                        document=document,
                        defaults={
                            "extraction_metadata": {
                                "engine": "MinerU",
                                "version": "4.0.12",
                                "schema_version": self.normalizer.SCHEMA_VERSION,
                            },
                            "normalized_content": normalized_content,
                        }
                    )

                    previous_figures = list(ext_doc.figures.all())
                    previous_paths = {figure.storage_path for figure in previous_figures}
                    current_references = set()

                    for fig in figures_metadata:
                        reference_id = fig.pop('reference_id')
                        current_references.add(reference_id)
                        DocumentFigure.objects.update_or_create(
                            extracted_document=ext_doc,
                            reference_id=reference_id,
                            defaults=fig,
                        )

                    removed_figures = ext_doc.figures.exclude(reference_id__in=current_references)
                    removed_paths = set(removed_figures.values_list('storage_path', flat=True))
                    removed_figures.delete()

                    from . import FigurePassageAssociationService
                    FigurePassageAssociationService(ext_doc).associate_all(normalized_content)

                replaced_paths = list(previous_paths - {fig['storage_path'] for fig in figures_metadata})
                for path in replaced_paths:
                    if default_storage.exists(path):
                        default_storage.delete(path)

            except Exception:
                for fig in figures_metadata:
                    path = fig.get('storage_path')
                    if path and default_storage.exists(path):
                        default_storage.delete(path)
                raise

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

                        source_index = block.get('index')
                        source_block_id = str(source_index if source_index is not None else f"image_{page_idx}_{len(figs)}")
                        reference_id = f"img_{document.id.hex}_{page_idx}_{source_block_id}"
                        figs.append({
                            "reference_id": reference_id,
                            "page_index": page_idx,
                            "storage_path": path,
                            "mime_type": mime_type,
                            "caption": block.get('caption'),
                            "bbox": block.get('bbox'),
                            "dimensions": block.get('dimensions'),
                            "metadata": block.get('metadata', {}) if isinstance(block.get('metadata'), dict) else {},
                            "source_block_id": source_block_id,
                            "source_block_ids": [source_block_id],
                        })
                    except Exception as e:
                        logger.warning(f"Failed to process figure in page {page_idx}: {e}")

        return figs
