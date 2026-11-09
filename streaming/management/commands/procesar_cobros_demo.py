import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from streaming.billing import procesar_cobros_demo


class Command(BaseCommand):
    help = (
        'Procesa cobros de demostración. Usa --watch para mantener un worker '
        'activo y aprobar cobros 5 segundos después.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--watch',
            action='store_true',
            help='Repite el procesamiento cada segundo.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'El worker de cobros demo solo puede ejecutarse '
                'con DEBUG activado.'
            )

        while True:
            resultado = procesar_cobros_demo()
            if resultado['creados'] or resultado['aprobados']:
                self.stdout.write(
                    f"Cobros creados: {resultado['creados']}; "
                    f"aprobados: {resultado['aprobados']}."
                )
            if not options['watch']:
                break
            time.sleep(1)
