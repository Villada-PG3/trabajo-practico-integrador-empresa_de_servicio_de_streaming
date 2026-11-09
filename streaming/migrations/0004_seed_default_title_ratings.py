from decimal import Decimal

from django.db import migrations


def seed_default_title_ratings(apps, schema_editor):
    Calificacion = apps.get_model('streaming', 'Calificacion')
    Perfil = apps.get_model('streaming', 'Perfil')
    PerfilTitulo = apps.get_model('streaming', 'PerfilTitulo')
    Titulo = apps.get_model('streaming', 'Titulo')
    database = schema_editor.connection.alias

    calificacion_inicial, _ = Calificacion.objects.using(database).get_or_create(
        estrellas=Decimal('2.5'),
        defaults={
            'nombre': '2.5 estrellas',
            'porcentaje_gusto': 50,
        },
    )
    PerfilTitulo.objects.using(database).filter(
        calificacion__isnull=True,
    ).update(calificacion_id=calificacion_inicial.pk)

    titulo_ids = Titulo.objects.using(database).values_list('pk', flat=True)
    for perfil_id in Perfil.objects.using(database).values_list(
        'pk', flat=True,
    ).iterator():
        existentes = set(
            PerfilTitulo.objects.using(database)
            .filter(perfil_id=perfil_id)
            .values_list('titulo_id', flat=True)
        )
        lote = []
        for titulo_id in titulo_ids.iterator():
            if titulo_id in existentes:
                continue
            lote.append(PerfilTitulo(
                perfil_id=perfil_id,
                titulo_id=titulo_id,
                calificacion_id=calificacion_inicial.pk,
            ))
            if len(lote) == 500:
                PerfilTitulo.objects.using(database).bulk_create(
                    lote,
                    batch_size=500,
                )
                lote = []
        if lote:
            PerfilTitulo.objects.using(database).bulk_create(
                lote,
                batch_size=500,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('streaming', '0003_remove_perfiltitulo_puntuacion_estrellas_and_more'),
    ]

    operations = [
        migrations.RunPython(
            seed_default_title_ratings,
            migrations.RunPython.noop,
        ),
    ]
