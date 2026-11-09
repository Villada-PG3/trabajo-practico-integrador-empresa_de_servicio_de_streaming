from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('reporte-ventas/', views.reporte_ventas_view, name='reporte_ventas'),
    path('registro/', views.registro_view, name='registro'),
    path('seleccionar-plan/', views.seleccionar_plan, name='seleccionar_plan'),
    path('pago/', views.pago_view, name='pago'),
    path('seleccionar-perfil/', views.seleccionar_perfil_view, name='seleccionar_perfil'),
    path('crear-perfil/', views.crear_perfil_view, name='crear_perfil'),
    path('titulo/<int:pk>/', views.detalle_contenido, name='detalle_contenido'),
]
