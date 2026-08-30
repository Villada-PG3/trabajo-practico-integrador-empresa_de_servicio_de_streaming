from django.db import models
from django.conf import settings

class MarcaTarjeta(models.Model):
    nombre = models.CharField(max_length=100)
    numero_asignado = models.IntegerField()
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre


class MetodoPago(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre


class Tarjeta(models.Model):
    numero = models.CharField(max_length=30)
    nombre_titular = models.CharField(max_length=150)
    fecha_vencimiento = models.DateField()
    marca_tarjeta = models.ForeignKey(MarcaTarjeta, on_delete=models.PROTECT, related_name='tarjetas')
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT, related_name='tarjetas')
    habilitado = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.marca_tarjeta} **** {self.numero[-4:]}'
    """
    # Es muy posible que esto no se deberia guardar, en cuyo caso:
    # ultimos 4 nums para reconocerla
    numero = models.CharField(max_length=4)
    marca_tarjeta = models.ForeignKey(MarcaTarjeta, on_delete=models.PROTECT, related_name='tarjetas')
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT, related_name='tarjetas')
    habilitado = models.BooleanField(default=True)
    """


class Plan(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    cantidad_pantallas_simultaneas = models.IntegerField()

    def __str__(self):
        return self.nombre


class PlanCalidad(models.Model):
    # Soluciona la n:m entre Plan y Calidad (streaming)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='plan_calidades')
    calidad = models.ForeignKey('streaming.Calidad', on_delete=models.CASCADE, related_name='plan_calidades')

    class Meta:
        verbose_name = 'Calidad del plan'
        verbose_name_plural = 'Calidades del plan'

    def __str__(self):
        return f'{self.plan} - {self.calidad}'


class Precio(models.Model):
    precio = models.FloatField()
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(blank=True, null=True)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='precios')

    def __str__(self):
        return f'{self.plan} - {self.precio}'


class Suscripcion(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='suscripciones')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='suscripciones')
    fecha_inscripcion = models.DateField()
    fecha_vigencia = models.DateField(blank=True, null=True)
    fecha_cancelacion = models.DateField(blank=True, null=True)
    habilitado = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.usuario} - {self.plan}'


class EstadoCobro(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre


class Cobro(models.Model):
    num_factura = models.IntegerField()
    suscripcion = models.ForeignKey(Suscripcion, on_delete=models.PROTECT, related_name='cobros')
    fecha_cobro = models.DateField()
    estado_cobro = models.ForeignKey(EstadoCobro, on_delete=models.PROTECT, related_name='cobros')
    # se copia de la suscripcion al momento del cobro, para dejar historial
    tarjeta = models.ForeignKey(Tarjeta, on_delete=models.PROTECT, related_name='cobros')
    numero_autorizacion = models.CharField(max_length=100, blank=True, null=True)
    monto = models.FloatField()

    def __str__(self):
        return f'Factura {self.num_factura} - {self.suscripcion}'