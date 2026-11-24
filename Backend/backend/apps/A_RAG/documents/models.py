import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings

class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        READY = 'ready', 'Ready'
        ERROR = 'error', 'Error'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_filename = models.CharField(max_length=255)
    file_data = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='documents'
    )

    def __str__(self):
        return f"{self.original_filename} ({self.status})"


class ExtractedDocument(models.Model):
    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name='extracted_version'
    )
    extraction_metadata = models.JSONField(
        help_text="Metadata about the extraction engine, version, and processing time"
    )
    normalized_content = models.JSONField(
        help_text="The core structured data: pages, blocks, and styles"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Extracted version of {self.document.original_filename}"


class DocumentFigure(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_id = models.CharField(max_length=255, null=True, blank=True)
    extracted_document = models.ForeignKey(
        ExtractedDocument,
        on_delete=models.CASCADE,
        related_name='figures'
    )
    page_index = models.IntegerField()
    storage_path = models.CharField(max_length=512)
    mime_type = models.CharField(max_length=100)
    caption = models.TextField(null=True, blank=True)
    bbox = models.JSONField(null=True, blank=True)
    dimensions = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    source_block_id = models.CharField(max_length=255)
    source_block_ids = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['extracted_document', 'reference_id'], name='unique_figure_reference_per_extraction'),
        ]
        indexes = [models.Index(fields=['extracted_document', 'page_index'], name='figure_extraction_page_idx')]

    def __str__(self):
        return f"Figure in {self.extracted_document.document.original_filename} page {self.page_index}"


class FigurePassageAssociation(models.Model):
    class Confidence(models.TextChoices):
        HIGH = 'high', 'High'
        MEDIUM = 'medium', 'Medium'
        LOW = 'low', 'Low'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    figure = models.ForeignKey(DocumentFigure, on_delete=models.CASCADE, related_name='passage_associations')
    extracted_document = models.ForeignKey(ExtractedDocument, on_delete=models.CASCADE, related_name='figure_associations')
    passage_block_id = models.CharField(max_length=255)
    page_index = models.IntegerField()
    confidence = models.CharField(max_length=10, choices=Confidence.choices)
    provenance = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['figure', 'passage_block_id'], name='unique_figure_passage'),
        ]
        indexes = [models.Index(fields=['extracted_document', 'passage_block_id'], name='association_passage_idx')]

    def clean(self):
        super().clean()
        if self.figure.extracted_document_id != self.extracted_document_id:
            raise ValidationError({'figure': 'Figure and passage must belong to the same extraction.'})

    def save(self, *args, **kwargs):
        if self.figure.extracted_document_id != self.extracted_document_id:
            raise ValueError('Figure and passage must belong to the same extraction.')
        super().save(*args, **kwargs)
