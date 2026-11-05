import calendar, random, string
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max, Q
from streaming.models import Suscripcion, Cobro, Precio, EstadoCobro

def dia_de_cobro(base, anio, mes):
    # Si el dia de renovacion del mes pasado esta en el proximo mes,
    # renovar ese dia, si no esta renovar el ultimo dia del mes
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(base.day, ultimo))

def obt_precio_actual(suscripcion, cobro_mes):
    precios = Precio.objects.filter(plan=suscripcion.plan, fecha_inicio__lte=cobro_mes).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=cobro_mes))
    actual = Precio()
    for p in precios:
        if p.fecha_inicio > actual.fecha_inicio : 
            actual = p
    return actual
    
class Command(BaseCommand):
    help = "Genera los cobros mensuales pendientes"

    def add_arguments(self, parser):
        parser.add_argument("--fecha", help="Simular otra fecha (YYYY-MM-DD)")

    def handle(self, *args, **opts):
        if opts["fecha"]:
            hoy = date.fromisoformat(opts["fecha"])  
        else: 
            hoy = date.today()
        pagado = EstadoCobro.objects.get_or_create(nombre="Pagado")[0]
        creados = 0

        for suscripcion in Suscripcion.objects.filter(habilitado=True).select_related("plan", "usuario"):
            # Cancelacion de suscripcion
            if suscripcion.fecha_cancelacion:
                if suscripcion.fecha_vigencia and hoy > suscripcion.fecha_vigencia:
                    suscripcion.habilitado = False
                    suscripcion.save()
                    suscripcion.usuario.is_active = False
                    suscripcion.usuario.save()
                continue

            dia_cobro = dia_de_cobro(suscripcion.fecha_inscripcion, hoy.year, hoy.month)
            # query que devuelve los cobros de este mes de la suscripcion actual
            temp1 = Cobro.objects.filter(suscripcion=suscripcion, fecha_cobro__year=hoy.year,
                fecha_cobro__month=hoy.month)
            
            # si todavia no paso el mes anterior no renovar y si existe ya un cobro este mes saltear
            if dia_cobro > hoy and temp1.exists():
                continue
            # esto hace que el primer mes sea gratis pero depende de las reglas de negocio
            """
            if cobro_mes <= suscripcion.fecha_inscripcion:
                
                continue
            """
            
            precio_suscripcion = obt_precio_actual(suscripcion, dia_cobro)
            
            if not precio_suscripcion:
                print(f"Sin precio vigente para {suscripcion.plan}")
                continue
            
            # Esto hace una 'transaccion', lo que significa que si hay algun error se cancela toda la operacion para
            # evitar datos rotos en la DB
            with transaction.atomic():
                Cobro.objects.create(
                    suscripcion=suscripcion, 
                    fecha_cobro=dia_cobro,
                    estado_cobro=pagado, 
                    tarjeta=suscripcion.tarjeta,
                    # simula con random un numero de autorizacion de pago
                    numero_autorizacion="".join(random.choices(string.ascii_uppercase + string.digits, k=15)), 
                    monto=precio_suscripcion.precio)
                suscripcion.fecha_vigencia = dia_cobro + timedelta(days=31)
                suscripcion.save()
                
                creados += 1

        print(f"{creados} cobros generados para {hoy}")