from django.db import models


class Image(models.Model):
    name = models.CharField(max_length=255)
    tag = models.CharField(max_length=255)
    upload_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ImageVariant(models.Model):
    image = models.ForeignKey(Image, related_name="variants", on_delete=models.CASCADE)
    resolution = models.CharField(max_length=50)
    file_path = models.CharField(max_length=255)
    size = models.PositiveIntegerField(blank=True, null=True)
    format = models.CharField(max_length=10, blank=True)

    def __str__(self):
        return f"{self.image.name} - {self.resolution}"
