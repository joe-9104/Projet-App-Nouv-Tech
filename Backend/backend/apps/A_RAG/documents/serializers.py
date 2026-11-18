from rest_framework import serializers
from .models import Document

class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

class DocumentResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'original_filename', 'status', 'created_at']
