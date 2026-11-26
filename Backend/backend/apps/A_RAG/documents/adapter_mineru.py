import os
import json
import tempfile
import logging
from typing import Tuple, Optional, Dict, Any
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .models import Document

logger = logging.getLogger(__name__)

class MinerUAdapter:
    """
    Adapter to interface with the MinerU extraction engine.
    Handles file preparation and raw output retrieval.
    """

    def __init__(self):
        try:
            from mineru.parser import parse
            self.parse = parse
        except ImportError:
            self.parse = None
            logger.error("MinerU (mineru.parser) not installed. Extraction will fail.")

    def extract(self, document: Document) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Extracts content from a Document.
        Returns a tuple of (middle_data, structured_data).
        """
        if not self.parse:
            raise ImportError("MinerU is not installed in the current environment.")

        # 1. Save binary data to a temporary file for MinerU to process
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(document.file_data)
            tmp_path = tmp.name

        try:
            # 2. Call MinerU parser
            # tier="standard" as per experiments
            result = self.parse(tmp_path, tier="standard")

            # 3. Retrieve outputs
            middle_data = result.to_json()
            if isinstance(middle_data, str):
                middle_data = json.loads(middle_data)
            structured_data = result.structured_content()
            if isinstance(structured_data, str):
                structured_data = json.loads(structured_data)

            return middle_data, structured_data
        except Exception as e:
            logger.exception(f"MinerU extraction failed for document {document.id}: {e}")
            raise e
        finally:
            # 4. Cleanup temporary file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
