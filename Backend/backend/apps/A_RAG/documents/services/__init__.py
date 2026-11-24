import re
from django.core.exceptions import ValidationError
from django.db import transaction
from ..models import Document, FigurePassageAssociation


class DocumentLifecycleService:
    """
    Service for managing Document state transitions.
    """

    ALLOWED_TRANSITIONS = {
        Document.Status.PENDING: [Document.Status.PROCESSING, Document.Status.ERROR],
        Document.Status.PROCESSING: [Document.Status.READY, Document.Status.ERROR],
        Document.Status.READY: [],  # Terminal state for current scope
        Document.Status.ERROR: [Document.Status.PROCESSING],  # Allow retry from error
    }

    @classmethod
    def transition_to(cls, document, next_status):
        """
        Transitions a document to a new status if the transition is allowed.
        """
        current_status = document.status

        if next_status not in cls.ALLOWED_TRANSITIONS.get(current_status, []):
            raise ValidationError(
                f"Invalid transition from {current_status} to {next_status}."
            )

        document.status = next_status
        document.save()
        return document


class FigurePassageAssociationService:
    """Creates deterministic associations between extracted figures and text blocks."""

    def __init__(self, extracted_document):
        self.extracted_document = extracted_document

    @staticmethod
    def _distance_to_bbox(text_bbox, figure_bbox):
        if not isinstance(text_bbox, list) or not isinstance(figure_bbox, list):
            return None
        if len(text_bbox) < 4 or len(figure_bbox) < 4:
            return None
        tx1, ty1, tx2, ty2 = text_bbox[:4]
        fx1, fy1, fx2, fy2 = figure_bbox[:4]
        dx = max(fx1 - tx2, tx1 - fx2, 0)
        dy = max(fy1 - ty2, ty1 - fy2, 0)
        return (dx * dx + dy * dy) ** 0.5

    @staticmethod
    def _explicit_reference(text, caption):
        if not text:
            return False
        patterns = [r'\bfigure\s*(?:n[°o]?\s*)?[#:]?\s*(\d+)']
        text_lower = text.lower()
        if caption:
            caption_numbers = re.findall(r'\d+', caption)
            if caption_numbers:
                patterns.extend(re.escape(str(number)) for number in caption_numbers)
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def associate_all(self, structured_data=None):
        """Rebuilds associations for this extraction; block IDs are stable per page/index."""
        with transaction.atomic():
            FigurePassageAssociation.objects.filter(extracted_document=self.extracted_document).delete()
            created = []
            pages = structured_data.get('pages', []) if structured_data else self.extracted_document.normalized_content.get('pages', [])

            for figure in self.extracted_document.figures.select_related('extracted_document').all():
                page_index = figure.page_index
                text_blocks = []
                if page_index < len(pages):
                    page = pages[page_index]
                    for block in page.get('blocks', []):
                        block_type = str(block.get('type', '')).lower()
                        if block_type not in ('text', 'paragraph', 'title', 'subtitle', 'caption'):
                            continue
                        block_id = block.get('block_id')
                        if not block_id:
                            source_index = block.get('index', block.get('source_index'))
                            block_id = f"blk_{page_index}_{source_index}" if source_index is not None else None
                        if block_id:
                            text_blocks.append((block_id, block))

                for passage_block_id, block in text_blocks:
                    text = str(block.get('content') or '')
                    confidence = None
                    reasons = []

                    if self._explicit_reference(text, figure.caption):
                        confidence = FigurePassageAssociation.Confidence.HIGH
                        reasons.append('explicit_figure_reference')

                    distance = self._distance_to_bbox(block.get('bbox'), figure.bbox)
                    if confidence is None and distance is not None:
                        if distance == 0:
                            confidence = FigurePassageAssociation.Confidence.MEDIUM
                            reasons.append('bounding_box_overlap')
                        elif distance <= 80:
                            confidence = FigurePassageAssociation.Confidence.MEDIUM
                            reasons.append('spatial_proximity')

                    if figure.caption and text:
                        caption_words = {word.lower() for word in re.findall(r'[A-Za-zÀ-ÿ]{5,}', figure.caption)}
                        text_words = {word.lower() for word in re.findall(r'[A-Za-zÀ-ÿ]{5,}', text)}
                        overlap = caption_words & text_words
                        if overlap and confidence is None:
                            confidence = FigurePassageAssociation.Confidence.MEDIUM
                            reasons.append('caption_text_overlap')

                    if confidence is None:
                        continue

                    association, _ = FigurePassageAssociation.objects.update_or_create(
                        figure=figure,
                        passage_block_id=passage_block_id,
                        defaults={
                            'extracted_document': self.extracted_document,
                            'page_index': page_index,
                            'confidence': confidence,
                            'provenance': {
                                'method': 'deterministic_structure_v1',
                                'reasons': reasons,
                                'source_block_id': block_id,
                                'figure_block_id': figure.source_block_id,
                            },
                        }
                    )
                    created.append(association)
            return created
