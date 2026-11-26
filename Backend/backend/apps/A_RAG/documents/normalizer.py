import logging
from typing import Dict, Any, List, Optional
from .models import Document, ExtractedDocument

logger = logging.getLogger(__name__)

class DocumentNormalizer:
    """
    Transforms MinerU raw output into the internal stable schema.
    Schema Version: 1.0
    """
    SCHEMA_VERSION = "1.0"

    def normalize(self, middle_data: Dict[str, Any], structured_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes MinerU outputs.
        We primarily use middle_data for structure and style,
        and structured_data for simplified text and figure metadata.
        """
        # Metadata extraction
        metadata = middle_data.get('metadata', {})
        document_metadata = metadata.get('document', {}) if isinstance(metadata, dict) else {}
        authors = document_metadata.get('authors', []) if isinstance(document_metadata, dict) else []
        languages = document_metadata.get('languages', []) if isinstance(document_metadata, dict) else []
        producer = metadata.get('producer') if isinstance(metadata, dict) else None

        normalized = {
            "schema_version": self.SCHEMA_VERSION,
            "metadata": {
                "title": metadata.get('title') if isinstance(metadata, dict) else None,
                "author": authors[0] if authors else (metadata.get('author') if isinstance(metadata, dict) else None),
                "language": languages[0] if languages else (metadata.get('language') if isinstance(metadata, dict) else None),
                "page_count": document_metadata.get('page_count') if isinstance(document_metadata, dict) else metadata.get('page_count'),
                "producer": producer,
            },
            "pages": []
        }

        # Process pages from middle_data (more detailed)
        pages_data = middle_data.get('pages', [])
        for page in pages_data:
            page_idx = page.get('page_idx')

            normalized_page = {
                "page_index": page_idx,
                "dimensions": page.get('dimensions'), # Store source dimensions
                "blocks": []
            }

            blocks = page.get('blocks', [])
            for block in blocks:
                normalized_block = self._normalize_block(block, page_idx)
                normalized_page["blocks"].append(normalized_block)

            normalized["pages"].append(normalized_page)

        return normalized

    def _normalize_block(self, block: Dict[str, Any], page_idx: int) -> Dict[str, Any]:
        """
        Normalizes a single block.
        """
        block_type = block.get('type', 'unknown')

        # Preserve basic structure
        source_index = block.get('index')
        normalized_block = {
            "block_id": f"blk_{page_idx}_{source_index}" if source_index is not None else None,
            "source_index": source_index,
            "type": block_type,
            "bbox": block.get('bbox'), # Source coordinates
            "level": block.get('level'),
            "content": block.get('content'),
        }

        # If content is complex (segments), we keep it as is to preserve styles
        # but we ensure it's a serializable format.

        return normalized_block
