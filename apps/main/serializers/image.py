from rest_framework import serializers
from apps.main.models import Image, ImageVariant


class ImageVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageVariant
        fields = ['resolution', 'file_path', 'size', 'format']


class ImageGetSerializer(serializers.ModelSerializer):
    variants = ImageVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Image
        fields = ['id', 'name', 'tag', 'upload_date', 'variants']


class ImageCreateSerializer(serializers.ModelSerializer):
    image = serializers.ImageField()

    class Meta:
        model = Image
        fields = ['name', 'tag', 'image']


class ImageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = ['name', 'tag']


class ImageMediaGetSerializer(serializers.Serializer):
    file_path = serializers.CharField(required=True)
