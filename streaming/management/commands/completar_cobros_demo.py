from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from streaming.models import (
    Cobro,
    EstadoCobro,
    MarcaTarjeta,
    MetodoPago,
    Plan,
    Precio,
    Suscripcion,
    Tarjeta,
    Usuario,
)


class Command(BaseCommand):
    help = 'Registra cobros y tarjetas ficticios para todas las cuentas de desarrollo.'

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'Esta carga solo puede ejecutarse con DEBUG activado; '
                'nunca crea cobros ficticios en producción.'
            )

        hoy = timezone.localdate()
        plan_demo, _ = Plan.objects.get_or_create(
            nombre='Plan Demo Basico',
            defaults={
                'descripcion': 'Plan de prueba, no representa una oferta real.',
                'cantidad_pantallas_simultaneas': 1,
            },
        )
        precio_demo, _ = Precio.objects.get_or_create(
            plan=plan_demo,
            fecha_inicio=hoy,
            defaults={'precio': 4.99},
        )
        estado_cobro, _ = EstadoCobro.objects.get_or_create(
            nombre='Aprobado',
            defaults={'descripcion': 'Estado ficticio para una prueba local.'},
        )
        marca_demo, _ = MarcaTarjeta.objects.get_or_create(
            nombre='Tarjeta Demo',
            defaults={
                'numero_asignado': 0,
                'descripcion': 'Marca ficticia; no usar para pagos.',
            },
        )
        metodo_demo, _ = MetodoPago.objects.get_or_create(
            nombre='Pago de prueba',
            defaults={'descripcion': 'Método ficticio para datos locales.'},
        )

        cuentas_completadas = 0
        suscripciones_creadas = 0
        cobros_creados = 0
        for usuario in Usuario.objects.order_by('pk').iterator():
            suscripcion = (
                Suscripcion.objects.filter(usuario=usuario)
                .order_by('-fecha_inscripcion', '-pk')
                .first()
            )
            if suscripcion is None:
                suscripcion = Suscripcion.objects.create(
                    usuario=usuario,
                    plan=plan_demo,
                    fecha_inscripcion=hoy,
                    fecha_vigencia=hoy,
                    habilitado=True,
                )
                suscripciones_creadas += 1

            nombre_titular = f'DEMO - {usuario.username}'[:150]
            tarjeta = suscripcion.tarjeta
            if tarjeta is None:
                ultimo_cobro = suscripcion.cobros.order_by(
                    '-fecha_cobro',
                    '-pk',
                ).first()
                tarjeta = ultimo_cobro.tarjeta if ultimo_cobro else None
            if tarjeta is None:
                tarjeta = Tarjeta.objects.create(
                    numero='0000',
                    nombre_titular=nombre_titular,
                    fecha_vencimiento=date(hoy.year + 2, hoy.month, 1),
                    marca_tarjeta=marca_demo,
                    metodo_pago=metodo_demo,
                    habilitado=True,
                )
            if suscripcion.tarjeta_id != tarjeta.pk:
                suscripcion.tarjeta = tarjeta
                suscripcion.save(update_fields=['tarjeta'])
            if suscripcion.cobros.exists():
                cuentas_completadas += 1
                continue
            precio_actual = (
                Precio.objects.filter(
                    plan=suscripcion.plan,
                    fecha_inicio__lte=hoy,
                )
                .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy))
                .order_by('-fecha_inicio', '-pk')
                .first()
            )
            monto = (
                precio_actual.precio
                if precio_actual is not None
                else precio_demo.precio
            )
            Cobro.objects.create(
                num_factura=900000000 + usuario.pk,
                suscripcion=suscripcion,
                fecha_cobro=hoy,
                estado_cobro=estado_cobro,
                tarjeta=tarjeta,
                numero_autorizacion=f'DEMO-AUTH-{usuario.pk}',
                monto=monto,
            )
            cobros_creados += 1
            cuentas_completadas += 1

        self.stdout.write(self.style.SUCCESS(
            f'Cuentas con cobro registrado: {cuentas_completadas}. '
            f'Suscripciones demo creadas: {suscripciones_creadas}. '
            f'Cobros demo creados: {cobros_creados}.'
        ))
        self.stdout.write(
            'Todos los cobros y tarjetas creados por este comando son ficticios '
            'y están marcados como demo.'
        )
