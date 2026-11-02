from rest_framework import serializers

from .models import Branding


class BrandingSerializer(serializers.Serializer):
    display_name = serializers.CharField()
    tagline = serializers.CharField(allow_blank=True)
    primary_color = serializers.CharField()
    accent_color = serializers.CharField()
    logo_url = serializers.CharField(allow_null=True)
    login_image_url = serializers.CharField(allow_null=True)


class BrandingUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branding
        fields = ["display_name", "tagline", "primary_color", "accent_color"]

    def validate_primary_color(self, value):
        return value.upper()

    def validate_accent_color(self, value):
        return value.upper()


class BrandingImageSerializer(serializers.Serializer):
    file = serializers.FileField()
