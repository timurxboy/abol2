from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.main.views import ImageViewSet, ImageMediaView

router = DefaultRouter()
router.register(r'images', ImageViewSet)

urlpatterns = [
    path('images/media/', ImageMediaView.as_view(), name='image-media')
]

urlpatterns += router.urls
