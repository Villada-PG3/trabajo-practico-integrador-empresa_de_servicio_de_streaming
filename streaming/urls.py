from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('mi-lista/', views.mi_lista_view, name='mi_lista'),
    path('mi-lista/toggle/<int:titulo_id>/', views.toggle_mi_lista_view, name='toggle_mi_lista'),
    path('perfiles/', views.perfiles_view, name='perfiles'),
    path('perfiles/crear/', views.crear_perfil_view, name='crear_perfil'),
    path('perfiles/<int:perfil_id>/configurar/', views.configurar_perfil_view, name='configurar_perfil'),
    path('perfiles/<int:perfil_id>/desactivar/', views.desactivar_perfil_view, name='desactivar_perfil'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('reporte-ventas/', views.reporte_ventas_view, name='reporte_ventas'),
    path('registro/', views.registro_view, name='registro'),
    path('planes/', views.seleccionar_plan_view, name='seleccionar_plan'),
]
