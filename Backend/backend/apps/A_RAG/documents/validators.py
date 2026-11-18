import os
from django.core.exceptions import ValidationError

# Configurable limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB default

def validate_pdf_file(file):
    """
    Validates that a file is a valid PDF.
    """
    # 1. Check extension
    filename = file.name
    if not filename.lower().endswith('.pdf'):
        raise ValidationError("The file must have a .pdf extension.")

    # 2. Check if file is empty
    if file.size == 0:
        raise ValidationError("The file is empty.")

    # 3. Check file size
    if file.size > MAX_FILE_SIZE:
        raise ValidationError(f"The file size exceeds the maximum limit of {MAX_FILE_SIZE // (1024 * 1024)} MB.")

    # 4. Check PDF signature (magic bytes)
    # Read the first 4 bytes to check for %PDF-
    try:
        # Reset file pointer to start
        file.seek(0)
        header = file.read(4)
        if header != b'%PDF':
            raise ValidationError("The file content is not a valid PDF.")
        # Reset file pointer back to start for future reading
        file.seek(0)
    except Exception as e:
        if isinstance(e, ValidationError):
            raise e
        raise ValidationError(f"Could not read file content: {str(e)}")
