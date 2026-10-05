from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('reporte-ventas/', views.reporte_ventas_view, name='reporte_ventas')
]