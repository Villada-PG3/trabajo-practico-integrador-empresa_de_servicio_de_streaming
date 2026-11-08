from django.urls import path
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
    path("perfil/<int:perfil_id>/catalogo/", views.catalogo, name="catalogo"),
    path("perfil/<int:perfil_id>/mi-lista/<int:titulo_id>/", views.toggle_mi_lista, name="toggle_mi_lista"),
]
