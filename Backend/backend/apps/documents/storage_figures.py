import os
import base64
import uuid
import logging
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

class FigureStorageService:
    """
    Handles the private storage of extracted figures.
    """

    def save_figure(self, base64_data: str, mime_type: str, filename_hint: str = None) -> str:
        """
        Decodes Base64 image data and saves it to private storage.
        Returns the private storage path.
        """
        try:
            # 1. Handle Data URI prefix (e.g., "data:image/jpeg;base64,")
            if "," in base64_data:
                header, base64_data = base64_data.split(",", 1)
                # Optional: validate mime_type from header

            # 2. Decode
            binary_data = base64.b64decode(base64_data)

            # 3. Generate safe filename
            ext = self._get_extension_from_mime(mime_type)
            filename = f"fig_{uuid.uuid4().hex}{ext}"

            # Use a private directory not exposed via MEDIA_URL
            # In a real setup, this would be a specific storage backend.
            # For now, we use default_storage with a 'private_figures' prefix.
            path = os.path.join('private_figures', filename)

            # 4. Save
            with default_storage.open(path, 'wb') as f:
                f.write(binary_data)

            return path

        except Exception as e:
            logger.exception(f"Failed to save figure: {e}")
            raise IOError(f"Could not store figure: {e}")

    def _get_extension_from_mime(self, mime_type: str) -> str:
        mapping = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
        }
        return mapping.get(mime_type, '.bin')
