from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

def no_cache_serve(request, path, document_root=None, show_indexes=False):
    response = serve(request, path, document_root=document_root, show_indexes=show_indexes)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('pages.urls')),
    path('academics/', include('academics.urls')),
    # 強制支援靜態資源服務（透過反向代理或 Tunnel 訪問能即時更新，防止瀏覽器或 Cloudflare 快取舊圖片）
    re_path(r'^static/(?P<path>.*)$', no_cache_serve, {'document_root': settings.BASE_DIR / 'html'}),
    re_path(r'^media/(?P<path>.*)$', no_cache_serve, {'document_root': settings.MEDIA_ROOT}),
]
