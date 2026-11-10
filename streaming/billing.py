import calendar
import re
import secrets
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from .models import (
    CambioPlan,
    Cobro,
    EstadoCobro,
    MarcaTarjeta,
    MetodoPago,
    Precio,
    Suscripcion,
    Tarjeta,
)


def calcular_proximo_cobro(fecha_vigencia):
    if fecha_vigencia is None:
        return None

    mes_siguiente = fecha_vigencia.year * 12 + fecha_vigencia.month
    anio, mes = divmod(mes_siguiente, 12)
    mes += 1
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(fecha_vigencia.day, ultimo_dia))


def suscripcion_activa(suscripcion, hoy=None):
    if not suscripcion.habilitado:
        return False
    if suscripcion.fecha_cancelacion is None:
        return True

    hoy = hoy or timezone.localdate()
    return hoy < suscripcion.fecha_cancelacion


def fecha_inicio_suscripcion(usuario, hoy=None):
    hoy = hoy or timezone.localdate()
    anterior = (
        Suscripcion.objects.filter(usuario=usuario)
        .order_by('-fecha_inscripcion', '-pk')
        .first()
    )
    if (
        anterior
        and suscripcion_activa(anterior, hoy)
        and anterior.fecha_vigencia
    ):
        return anterior.fecha_vigencia
    return hoy


def normalizar_numero_tarjeta(numero):
    if not numero:
        return ''
    numero = str(numero).strip()
    if not re.fullmatch(r'[0-9][0-9 -]*[0-9]', numero):
        return ''
    return numero.replace(' ', '').replace('-', '')


def numero_tarjeta_valido(numero_targeta):
    if not numero_targeta.isascii() or not numero_targeta.isdigit() or not 12 <= len(numero_targeta) <= 19:
        return False

    suma = 0
    for posicion, digito in enumerate(reversed(numero_targeta)):
        valor = int(digito)
        if posicion % 2:
            valor *= 2
            if valor > 9:
                valor -= 9
        suma += valor
    return suma % 10 == 0


def generar_numero_autorizacion_demo():
    return f'DEMO-AUTH-{secrets.token_hex(6).upper()}'


def guardar_tarjeta_demo(
    nombre_titular,
    numero_tarjeta,
    marca_tarjeta,
    metodo_pago,
    hoy=None,
):
    numero_tarjeta = normalizar_numero_tarjeta(numero_tarjeta)
    if not numero_tarjeta_valido(numero_tarjeta):
        raise ValueError('No se puede guardar una tarjeta que no supera Luhn.')

    hoy = hoy or timezone.localdate()
    return Tarjeta.objects.create(
        numero=numero_tarjeta[-4:],
        nombre_titular=nombre_titular[:150],
        fecha_vencimiento=date(hoy.year + 10, hoy.month, 1),
        marca_tarjeta=marca_tarjeta,
        metodo_pago=metodo_pago,
        habilitado=True,
    )


@transaction.atomic
def procesar_cobros_demo(ahora=None):
    if not settings.DEBUG:
        raise CommandError(
            'El procesamiento simulado de cobros solo puede ejecutarse '
            'con DEBUG activado.'
        )

    ahora = ahora or timezone.now()
    hoy = timezone.localdate(ahora)
    por_aprobar, _ = EstadoCobro.objects.get_or_create(
        nombre='Por aprobar',
        defaults={'descripcion': 'Cobro demo en proceso de aprobación.'},
    )
    aprobado, _ = EstadoCobro.objects.get_or_create(
        nombre='Aprobado',
        defaults={'descripcion': 'Cobro demo aprobado automáticamente.'},
    )

    aprobados = 0
    cancelados = 0
    cobros_pendientes = list(
        Cobro.objects.select_for_update()
        .filter(
            estado_cobro=por_aprobar,
            fecha_hora_creacion__lte=ahora - timedelta(seconds=5),
        )
        .select_related('suscripcion', 'cambio_plan')
        .order_by('fecha_hora_creacion', 'pk')
    )
    for cobro in cobros_pendientes:
        suscripcion = Suscripcion.objects.select_for_update().get(
            pk=cobro.suscripcion_id,
        )
        if (
            suscripcion.fecha_cancelacion is not None
            and cobro.fecha_cobro >= suscripcion.fecha_cancelacion
        ):
            cancelado, _ = EstadoCobro.objects.get_or_create(
                nombre='Cancelado',
                defaults={'descripcion': 'Suscripción cancelada antes de la renovación.'},
            )
            cobro.estado_cobro = cancelado
            cobro.save(update_fields=['estado_cobro'])
            if (
                cobro.cambio_plan_id
                and cobro.cambio_plan.estado == CambioPlan.ESTADO_PENDIENTE
            ):
                cobro.cambio_plan.estado = CambioPlan.ESTADO_CANCELADO
                cobro.cambio_plan.save(update_fields=['estado'])
            continue

        cobro.estado_cobro = aprobado
        cobro.numero_autorizacion = generar_numero_autorizacion_demo()
        cobro.save(update_fields=['estado_cobro', 'numero_autorizacion'])
        suscripcion.fecha_vigencia = cobro.fecha_cobro
        if (
            cobro.cambio_plan_id
            and cobro.cambio_plan.estado == CambioPlan.ESTADO_PENDIENTE
        ):
            suscripcion.plan = cobro.cambio_plan.plan
            cobro.cambio_plan.estado = CambioPlan.ESTADO_APLICADO
            cobro.cambio_plan.save(update_fields=['estado'])
        suscripcion.save(update_fields=['plan', 'fecha_vigencia'])
        aprobados += 1

    creados = 0
    suscripciones = (
        Suscripcion.objects.select_for_update()
        .filter(habilitado=True, fecha_vigencia__isnull=False)
        .select_related('plan', 'tarjeta')
        .order_by('pk')
    )
    for suscripcion in suscripciones:
        if (
            suscripcion.fecha_cancelacion is not None
            and hoy >= suscripcion.fecha_cancelacion
        ):
            suscripcion.habilitado = False
            suscripcion.save(update_fields=['habilitado'])
            suscripcion.cambios_programados.filter(
                estado=CambioPlan.ESTADO_PENDIENTE,
            ).update(estado=CambioPlan.ESTADO_CANCELADO)
            cancelados += 1
            continue

        fecha_cobro = calcular_proximo_cobro(suscripcion.fecha_vigencia)
        if fecha_cobro is None or fecha_cobro > hoy:
            continue
        if (
            suscripcion.fecha_cancelacion is not None
            and (
                fecha_cobro > suscripcion.fecha_cancelacion
                or hoy > suscripcion.fecha_cancelacion
            )
        ):
            continue
        if Cobro.objects.filter(
            suscripcion=suscripcion,
            fecha_cobro=fecha_cobro,
        ).exists():
            continue
        if suscripcion.tarjeta_id is None or not suscripcion.tarjeta.habilitado:
            continue

        cambio_plan = (
            suscripcion.cambios_programados.filter(
                estado=CambioPlan.ESTADO_PENDIENTE,
                fecha_aplicacion__lte=fecha_cobro,
            )
            .select_related('plan')
            .first()
        )
        plan_cobrado = cambio_plan.plan if cambio_plan else suscripcion.plan
        precio = (
            Precio.objects.filter(
                plan=plan_cobrado,
                fecha_inicio__lte=fecha_cobro,
            )
            .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_cobro))
            .order_by('-fecha_inicio', '-pk')
            .first()
        )
        if precio is None:
            continue

        numero_factura = (
            Cobro.objects.aggregate(ultimo=Max('num_factura'))['ultimo'] or 0
        ) + 1
        Cobro.objects.create(
            num_factura=numero_factura,
            suscripcion=suscripcion,
            fecha_cobro=fecha_cobro,
            estado_cobro=por_aprobar,
            tarjeta=suscripcion.tarjeta,
            numero_autorizacion='',
            monto=precio.precio,
            fecha_hora_creacion=ahora,
            cambio_plan=cambio_plan,
        )
        creados += 1

    return {
        'creados': creados,
        'aprobados': aprobados,
        'suscripciones_canceladas': cancelados,
    }
