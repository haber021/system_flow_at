from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.views.decorators.cache import cache_control

# Optimized media serving with cache headers
@cache_control(max_age=86400, public=True)  # Cache for 24 hours
def serve_media(request, path):
    """Serve media files with optimized caching headers"""
    return serve(request, path, document_root=settings.MEDIA_ROOT)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('attendance.urls')),
]

# Serve media files in development with optimized caching
if settings.DEBUG:
    urlpatterns += [
        path('media/<path:path>', serve_media, name='media'),
    ]
