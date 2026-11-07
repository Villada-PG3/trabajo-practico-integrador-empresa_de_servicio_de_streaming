from django.db import migrations


def ensure_profile_active_column(apps, schema_editor):
    Perfil = apps.get_model('streaming', 'Perfil')
    table_name = Perfil._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor,
                table_name,
            )
        }

    if 'activo' not in columns:
        schema_editor.add_field(Perfil, Perfil._meta.get_field('activo'))


class Migration(migrations.Migration):

    dependencies = [
        ('streaming', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            ensure_profile_active_column,
            migrations.RunPython.noop,
        ),
    ]
