import io
from django.db import transaction
from django.http import HttpResponse
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from PIL import Image as PILImage
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.main.models import Image, ImageVariant
from apps.main.serializers import ImageGetSerializer, ImageCreateSerializer, ImageUpdateSerializer, ImageMediaGetSerializer
from apps.main.services.rabbitmq.send import send_message


class ImageViewSet(viewsets.ModelViewSet):
    queryset = Image.objects.all()

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ImageGetSerializer
        elif self.action in ['create']:
            return ImageCreateSerializer
        elif self.action in ['update']:
            return ImageUpdateSerializer

    def retrieve(self, request, pk=None, *args, **kwargs):
        cache_key = f"image_{pk}"
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)

        try:
            image = self.get_object()
            serializer = self.get_serializer(image)
            data = serializer.data
            cache.set(cache_key, data, timeout=3600)  # Кэшируем на 1 час
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(data={'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def list(self, request, *args, **kwargs):
        cache_key = "images_list"
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        cache.set(cache_key, data, timeout=3600)  # Кэшируем на 1 час
        return Response(data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        name = serializer.validated_data.get('name')
        tag = serializer.validated_data.get('tag')
        image_file = serializer.validated_data.get('image')

        with transaction.atomic():
            try:
                image_obj = Image.objects.create(name=name, tag=tag)

                image_path = f'{image_obj.id}_original'
                original_image_bytes = io.BytesIO(image_file.read())
                cache.set(image_path, original_image_bytes.getvalue())

                with PILImage.open(image_file) as img:
                    original_resolution = f"{img.width}x{img.height}"

                ImageVariant.objects.create(
                    image=image_obj,
                    resolution=original_resolution,
                    file_path=image_path,
                    size=image_file.size,
                    format=image_file.content_type.split('/')[-1]
                )

                for resolution, size in [('100x100', (100, 100)), ('500x500', (500, 500)), ('1000x1000', (1000, 1000))]:
                    pil_image = PILImage.open(image_file)
                    pil_image = pil_image.convert("L")
                    pil_image.thumbnail(size)

                    variant_path = f'{image_obj.id}_{resolution}'
                    variant_bytes = io.BytesIO()
                    pil_image.save(variant_bytes, format="JPEG")
                    cache.set(variant_path, variant_bytes.getvalue())

                    ImageVariant.objects.create(
                        image=image_obj,
                        resolution=resolution,
                        file_path=variant_path,
                        size=variant_bytes.tell(),
                        format="JPEG"
                    )

                # Очистка кэша после создания нового изображения
                cache.delete("images_list")

                # Отправка сообщения о создании в Брокер (RabbitMQ)
                send_message('create', {
                    'id': image_obj.id,
                    'name': image_obj.name,
                    'tag': image_obj.tag
                })

                return Response(data={'message': 'Created'}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response(data={'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None, *args, **kwargs):
        image_obj = self.get_object()
        serializer = self.get_serializer(image_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        name = serializer.validated_data.get('name')
        tag = serializer.validated_data.get('tag')

        with transaction.atomic():
            try:
                image_obj.name = name or image_obj.name
                image_obj.tag = tag or image_obj.tag
                image_obj.save()

                # Очистка кэша для обновленного объекта
                cache.delete(f"image_{pk}")
                cache.delete("images_list")

                # Отправка сообщения о создании в Брокер (RabbitMQ)
                send_message('update', {
                    'id': image_obj.id,
                    'name': image_obj.name,
                    'tag': image_obj.tag
                })

                return Response(serializer.data, status=status.HTTP_200_OK)
            except Exception as e:
                return Response(data={'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None, *args, **kwargs):
        image_obj = self.get_object()

        with transaction.atomic():
            try:
                image_obj.variants.all().delete()
                image_obj.delete()

                cache.delete(f"{image_obj.id}_original")  # Оригинальное изображение
                for resolution in ['100x100', '500x500', '1000x1000']:
                    cache.delete(f"{image_obj.id}_{resolution}")  # Варианты изображений

                cache.delete("images_list")  # Удаляем общий кэш для списка изображений

                # Отправка сообщения о создании в Брокер (RabbitMQ)
                send_message('delete', {
                    'id': image_obj.id,
                    'name': image_obj.name,
                    'tag': image_obj.tag
                })

                return Response(data={'message': 'Deleted'}, status=status.HTTP_204_NO_CONTENT)
            except Exception as e:
                return Response(data={'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ImageMediaView(APIView):
    @extend_schema(parameters=[ImageMediaGetSerializer])
    def get(self, request, pk=None, *args, **kwargs):
        filter_serializer = ImageMediaGetSerializer(data=self.request.GET)
        filter_serializer.is_valid(raise_exception=True)

        file_path = filter_serializer.validated_data.get('file_path')
        try:
            # Получаем изображение из кэша
            image_data = cache.get(file_path)
            if image_data is None:
                return Response(data={'message': 'Image not found'}, status=status.HTTP_404_NOT_FOUND)

            # Определяем тип содержимого изображения
            image = PILImage.open(io.BytesIO(image_data))
            image_format = image.format.lower()  # Получаем формат изображения в нижнем регистре

            # Устанавливаем соответствующий content_type
            content_type = f'image/{image_format}' if image_format in ['jpeg', 'png', 'gif', 'bmp', 'tiff'] else 'application/octet-stream'

            # Создаем HTTP-ответ с изображением
            response = HttpResponse(image_data, content_type=content_type)
            response['Content-Disposition'] = f'inline; filename="{file_path.split("/")[-1]}"'
            return response

        except Exception as e:
            return Response(data={'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
