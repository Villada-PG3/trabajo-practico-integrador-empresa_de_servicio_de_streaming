from django.urls import path
from . import views

urlpatterns = [
    path('', views.pagina_inicial_view, name='pagina_inicial'),
    path('inicio/', views.home, name='home'),
    path('categorias/', views.categorias_view, name='categorias'),
    path('buscar/', views.buscar_titulos_view, name='buscar_titulos'),
    path('mi-lista/', views.mi_lista_view, name='mi_lista'),
    path(
        'titulos/<int:titulo_id>/reproducir/',
        views.reproducir_titulo_view,
        name='reproducir_titulo',
    ),
    path(
        'titulos/<int:titulo_id>/contenidos/<int:contenido_id>/reproducir/',
        views.reproducir_titulo_view,
        name='reproducir_contenido',
    ),
    path(
        'titulos/<int:titulo_id>/reproducir/<int:video_id>/',
        views.reproducir_video_view,
        name='reproducir_video',
    ),
    path(
        'titulos/<int:titulo_id>/reproducir/<int:video_id>/subtitulos/<int:subtitulo_id>.vtt',
        views.servir_subtitulo_view,
        name='servir_subtitulo',
    ),
    path(
        'titulos/<int:titulo_id>/reproducir/<int:video_id>/subtitulos/<int:subtitulo_id>.vtt',
        views.servir_subtitulo_view,
        name='servir_subtitulo',
    ),
    path('mi-lista/toggle/<int:titulo_id>/', views.toggle_mi_lista_view, name='toggle_mi_lista'),
    path('titulos/<int:titulo_id>/calificar/', views.calificar_titulo_view, name='calificar_titulo'),
    path('perfiles/', views.perfiles_view, name='perfiles'),
    path('cuenta/', views.cuenta_view, name='cuenta'),
    path('cuenta/sesiones/cerrar-otras/', views.cerrar_otras_sesiones_view, name='cerrar_otras_sesiones'),
    path(
        'cuenta/suscripcion/cancelar/',
        views.cancelar_suscripcion_view,
        name='cancelar_suscripcion',
    ),
    path('cuenta/editar/<slug:campo>/', views.editar_dato_cuenta_view, name='editar_dato_cuenta'),
    path('perfiles/crear/', views.crear_perfil_view, name='crear_perfil'),
    path('perfiles/<int:perfil_id>/configurar/', views.configurar_perfil_view, name='configurar_perfil'),
    path('perfiles/<int:perfil_id>/desactivar/', views.desactivar_perfil_view, name='desactivar_perfil'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path(
        'dispositivos-bloqueados/',
        views.dispositivos_bloqueados_view,
        name='dispositivos_bloqueados',
    ),
    path(
        'dispositivos/actividad/',
        views.heartbeat_dispositivo_view,
        name='heartbeat_dispositivo',
    ),
    path('reporte-ventas/', views.reporte_ventas_view, name='reporte_ventas'),
    path('registro/', views.registro_view, name='registro'),
    path('planes/', views.seleccionar_plan_view, name='seleccionar_plan'),
    path('planes/<int:plan_id>/pago/', views.pagar_suscripcion_view, name='pagar_suscripcion'),
    path('planes/<int:plan_id>/cambio/', views.pagar_cambio_plan_view, name='pagar_cambio_plan'),
    path('ver/<int:contenido_id>/', views.reproductor, name='reproductor'),
]
