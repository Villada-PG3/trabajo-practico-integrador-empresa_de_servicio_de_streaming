from decimal import Decimal

from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError


def remove_seeded_default_title_ratings(apps, schema_editor):
    PerfilTitulo = apps.get_model('streaming', 'PerfilTitulo')
    database = schema_editor.connection.alias
    calificaciones_iniciales = PerfilTitulo.objects.using(database).filter(
        calificacion__estrellas=Decimal('2.5'),
    )
    calificaciones_en_mi_lista = calificaciones_iniciales.filter(
        porver__isnull=False,
    )

    calificaciones_en_mi_lista.update(calificacion=None)
    calificaciones_iniciales.filter(porver__isnull=True).delete()


def restore_seeded_default_title_ratings(apps, schema_editor):
    raise IrreversibleError(
        'No se pueden restaurar las calificaciones predeterminadas eliminadas.',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('streaming', '0005_perfiltitulo_unique_perfil_titulo'),
    ]

    operations = [
        migrations.RunPython(
            remove_seeded_default_title_ratings,
            restore_seeded_default_title_ratings,
        ),
    ]
