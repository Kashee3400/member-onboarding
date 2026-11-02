from rest_framework import serializers

from .models import Document, DocumentType


class DocumentSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_document_type_display", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "document_type",
            "label",
            "content_type",
            "size_bytes",
            "uploaded_by_name",
            "created_at",
        ]


class DocumentUploadSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=DocumentType.choices)
    file = serializers.FileField()


class SignatureUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class SignatureStatusSerializer(serializers.Serializer):
    has_signature = serializers.BooleanField()
