
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from stations.views import StationViewSet, ContainerViewSet, ActivityLogViewSet

router = DefaultRouter()
router.register(r'stations', StationViewSet, basename='station')
router.register(r'containers', ContainerViewSet, basename='container')
router.register(r'logs', ActivityLogViewSet, basename='activitylog')
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/auth/token/', obtain_auth_token, name='api_token_auth'),
    path('api/auth/', include('rest_framework.urls')),
]
