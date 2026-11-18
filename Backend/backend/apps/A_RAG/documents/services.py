from django.core.exceptions import ValidationError
from .models import Document

class DocumentLifecycleService:
    """
    Service for managing Document state transitions.
    """

    # Define allowed transitions: {current_status: [allowed_next_statuses]}
    ALLOWED_TRANSITIONS = {
        Document.Status.PENDING: [Document.Status.PROCESSING, Document.Status.ERROR],
        Document.Status.PROCESSING: [Document.Status.READY, Document.Status.ERROR],
        Document.Status.READY: [], # Terminal state for current scope
        Document.Status.ERROR: [Document.Status.PROCESSING], # Allow retry from error
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
