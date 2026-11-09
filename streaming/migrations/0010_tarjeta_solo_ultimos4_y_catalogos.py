import re

from django.core.validators import RegexValidator
from django.db import migrations, models


def preparar_tarjetas_y_catalogos(apps, schema_editor):
    MarcaTarjeta = apps.get_model('streaming', 'MarcaTarjeta')
    MetodoPago = apps.get_model('streaming', 'MetodoPago')
    Tarjeta = apps.get_model('streaming', 'Tarjeta')
    database = schema_editor.connection.alias

    for tarjeta in Tarjeta.objects.using(database).iterator():
        ultimos4 = re.sub(r'\D', '', tarjeta.numero)[-4:]
        Tarjeta.objects.using(database).filter(pk=tarjeta.pk).update(
            numero=ultimos4,
        )

    for nombre, numero_asignado in (
        ('Visa', 4),
        ('Mastercard', 5),
        ('American Express', 3),
        ('Discover', 6),
        ('Diners Club', 3),
        ('Maestro', 5),
    ):
        MarcaTarjeta.objects.using(database).get_or_create(
            nombre=nombre,
            defaults={
                'numero_asignado': numero_asignado,
                'descripcion': 'Marca disponible para tarjetas demo.',
            },
        )

    for nombre in ('Débito', 'Crédito'):
        MetodoPago.objects.using(database).get_or_create(
            nombre=nombre,
            defaults={'descripcion': 'Método disponible para tarjetas demo.'},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('streaming', '0009_cobro_cambio_plan_cobro_fecha_hora_creacion_and_more'),
    ]

    operations = [
        migrations.RunPython(
            preparar_tarjetas_y_catalogos,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='tarjeta',
            name='numero',
            field=models.CharField(
                max_length=4,
                validators=[
                    RegexValidator(
                        r'^[0-9]{4}$',
                        'La tarjeta debe guardar solo 4 dígitos.',
                    ),
                ],
            ),
        ),
    ]
