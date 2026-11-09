import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('streaming', '0010_tarjeta_solo_ultimos4_y_catalogos'),
    ]

    operations = [
        migrations.RenameField(
            model_name='calidadidiomacontenido',
            old_name='archivo',
            new_name='archivo_legacy',
        ),
        migrations.AddField(
            model_name='calidadidiomacontenido',
            name='archivo',
            field=models.FileField(
                blank=True,
                upload_to='videos/',
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=['mp4'],
                    ),
                ],
                verbose_name='Archivo MP4',
            ),
        ),
    ]
