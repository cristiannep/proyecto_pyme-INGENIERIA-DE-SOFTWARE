from django.urls import path
from core import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('productos/', views.productos_lista, name='productos_lista'),
    path('productos/nuevo/', views.producto_crear, name='producto_crear'),
]