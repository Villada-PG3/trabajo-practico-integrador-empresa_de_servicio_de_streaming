from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect
from django.utils import timezone

from .billing import suscripcion_activa
from .models import Registro, Suscripcion, Usuario

VENTANA_ACTIVIDAD = timedelta(minutes=1)
RUTA_BLOQUEO_DISPOSITIVOS = '/dispositivos-bloqueados/'
CLAVE_ADMISION_DISPOSITIVO_PENDIENTE = 'admision_dispositivo_pendiente'
RUTAS_SIN_CONTROL = {
    RUTA_BLOQUEO_DISPOSITIVOS,
    '/logout/',
}


def _actividad_reciente():
    ahora = timezone.localtime()
    limite = ahora - VENTANA_ACTIVIDAD
    hora_limite = limite.time().replace(tzinfo=None)
    return (
        Q(ultima_conexion_fecha__gt=limite.date())
        | Q(
            ultima_conexion_fecha=limite.date(),
            ultima_conexion_hora__gte=hora_limite,
        )
    )


def _suscripcion_con_limite(usuario):
    suscripciones = (
        Suscripcion.objects.filter(usuario=usuario, habilitado=True)
        .select_related('plan')
        .order_by('-fecha_inscripcion', '-pk')
    )
    return next(
        (suscripcion for suscripcion in suscripciones if suscripcion_activa(suscripcion)),
        None,
    )


class LimiteDispositivosSimultaneosMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            not request.user.is_authenticated
            or request.path_info in RUTAS_SIN_CONTROL
        ):
            return self.get_response(request)

        session_key = request.session.session_key
        if not session_key:
            request.session.save()
            session_key = request.session.session_key

        ahora = timezone.localtime()
        registro = Registro.objects.filter(
            usuario=request.user,
            token_disp=session_key,
        ).first()
        registro_activo = bool(
            registro
            and registro.estado
            and not request.session.get(CLAVE_ADMISION_DISPOSITIVO_PENDIENTE)
            and Registro.objects.filter(pk=registro.pk)
            .filter(_actividad_reciente())
            .exists()
        )

        if not registro_activo:
            with transaction.atomic():
                Usuario.objects.select_for_update().get(pk=request.user.pk)
                suscripcion = _suscripcion_con_limite(request.user)
                if suscripcion is not None:
                    dispositivos_activos = (
                        Registro.objects.filter(
                            usuario=request.user,
                            estado=True,
                        )
                        .filter(_actividad_reciente())
                        .exclude(token_disp=session_key)
                        .values('token_disp')
                        .distinct()
                        .count()
                    )
                    limite = max(suscripcion.plan.cantidad_pantallas_simultaneas, 0)
                    if dispositivos_activos >= limite:
                        if registro is not None:
                            Registro.objects.filter(pk=registro.pk).update(
                                estado=False,
                            )
                        return redirect('dispositivos_bloqueados')

        valores_registro = {
            'os': request.META.get('HTTP_USER_AGENT', 'Navegador')[:100],
            'ultima_conexion_fecha': ahora.date(),
            'ultima_conexion_hora': ahora.time().replace(tzinfo=None),
            'estado': True,
        }
        Registro.objects.update_or_create(
            usuario=request.user,
            token_disp=session_key,
            defaults=valores_registro,
        )
        request.session.pop(CLAVE_ADMISION_DISPOSITIVO_PENDIENTE, None)
        return self.get_response(request)
