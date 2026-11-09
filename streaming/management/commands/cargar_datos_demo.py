from datetime import date, time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from streaming.models import (
    Calidad,
    CalidadIdiomaContenido,
    Calificacion,
    Categoria,
    Cobro,
    Contenido,
    Elenco,
    EstadoCobro,
    Idioma,
    IdiomaContenido,
    IdiomaTitulo,
    Imagen,
    MarcaTarjeta,
    MetodoPago,
    Pais,
    Perfil,
    PerfilContenido,
    PerfilTitulo,
    Plan,
    PlanCalidad,
    Precio,
    Porver,
    Registro,
    Rol,
    RolElenco,
    Subtitulo,
    Suscripcion,
    Tarjeta,
    TipoPerfil,
    TipoTitulo,
    Titulo,
    TituloCategoria,
    TituloRolElenco,
)

Usuario = get_user_model()

TRADUCCIONES_TITULOS_INGLES = {
    'La ruta de prueba': (
        'Test Route',
        'A fictional movie created to test the streaming platform.',
    ),
    'Misterios de muestra': (
        'Sample Mysteries',
        'A fictional mystery series created to test the streaming platform.',
    ),
    'Horizonte de cobre': (
        'Copper Horizon',
        'A journey across a distant landscape puts courage and loyalty to the test.',
    ),
    'Código lunar': (
        'Lunar Code',
        'A hidden message on the Moon leads a team into a race against time.',
    ),
    'Estación Boreal': (
        'Boreal Station',
        'A remote research station uncovers a mystery beneath the northern lights.',
    ),
    'Archivo del viento': (
        'The Wind Archive',
        'An archivist discovers that forgotten records can change the present.',
    ),
    'El último faro': (
        'The Last Lighthouse',
        'A lighthouse keeper follows a signal that should not exist.',
    ),
    'Niebla roja': (
        'Red Fog',
        'A town is hidden by a strange fog as its residents search for answers.',
    ),
    'Guardia nocturna': (
        'Night Watch',
        'A night-shift team investigates a series of unexplained events.',
    ),
    'Planeta oculto': (
        'Hidden Planet',
        'Explorers document a world that does not appear on any star chart.',
    ),
    'Habitación 404': (
        'Room 404',
        'Guests at an old hotel discover that one room changes every night.',
    ),
}


class Command(BaseCommand):
    help = 'Carga datos ficticios de demostración sin borrar ni duplicar los existentes.'

    @transaction.atomic
    def handle(self, *args, **options):
        hoy = timezone.localdate()
        pais, _ = Pais.objects.get_or_create(nombre='Argentina')
        pais_origen, _ = Pais.objects.get_or_create(nombre='Estados Unidos')
        espanol, _ = Idioma.objects.get_or_create(
            nombre='Español',
            defaults={'descripcion': 'Idioma de demostración'},
        )
        ingles, _ = Idioma.objects.get_or_create(
            nombre='Inglés',
            defaults={'descripcion': 'Idioma de demostración'},
        )

        tipo_pelicula, _ = TipoTitulo.objects.get_or_create(
            nombre='Película',
            defaults={'descripcion': 'Largometraje'},
        )
        tipo_serie, _ = TipoTitulo.objects.get_or_create(
            nombre='Serie',
            defaults={'descripcion': 'Serie episódica'},
        )
        edades_minimas = {
            'ATP': 0,
            '+7': 7,
            '+10': 10,
            '+13': 13,
            '+16': 16,
            '+18': 18,
        }
        descripciones_categorias = {
            'Acción': 'Historias de acción',
            'Aventura': 'Historias de aventura',
            'Ciencia ficción': 'Historias de ciencia ficción',
            'Drama': 'Historias dramáticas',
            'Misterio': 'Historias de misterio',
            'Animación': 'Historias animadas',
            'Comedia': 'Historias de comedia',
            'Crimen': 'Historias de crimen',
            'Documental': 'Historias documentales',
            'Familia': 'Historias para toda la familia',
            'Fantasía': 'Historias de fantasía',
            'Música': 'Historias relacionadas con la música',
            'Romance': 'Historias románticas',
            'Suspenso': 'Historias de suspenso',
            'Terror': 'Historias de terror',
        }
        categoria_por_nombre = {}
        for nombre, descripcion in descripciones_categorias.items():
            categoria, _ = Categoria.objects.get_or_create(
                nombre=nombre,
                defaults={'descripcion': descripcion},
            )
            if not categoria.descripcion:
                categoria.descripcion = descripcion
                categoria.save(update_fields=['descripcion'])
            categoria_por_nombre[nombre] = categoria
        actor, _ = Rol.objects.get_or_create(
            nombre='Actor',
            defaults={'descripcion': 'Interpreta un personaje'},
        )
        director, _ = Rol.objects.get_or_create(
            nombre='Director',
            defaults={'descripcion': 'Dirige la producción'},
        )
        elenco, _ = Elenco.objects.get_or_create(
            nombre='Alex',
            apellido='Demo',
            defaults={
                'pais': pais,
                'fecha_nacimiento': date(1990, 1, 1),
                'descripcion': 'Persona ficticia para datos de prueba.',
            },
        )
        rol_actor, _ = RolElenco.objects.get_or_create(rol=actor, elenco=elenco)
        rol_director, _ = RolElenco.objects.get_or_create(rol=director, elenco=elenco)
        calidad_hd, _ = Calidad.objects.get_or_create(
            nombre='HD',
            defaults={'descripcion': 'Alta definición de prueba'},
        )
        calidad_full_hd, _ = Calidad.objects.get_or_create(
            nombre='Full HD',
            defaults={'descripcion': 'Full HD de prueba'},
        )
        calificacion, _ = Calificacion.objects.get_or_create(
            nombre='Apta para todo público',
            defaults={'porcentaje_gusto': 92.0},
        )

        pelicula, _ = Titulo.objects.get_or_create(
            nombre_original='La ruta de prueba',
            defaults={
                'descripcion_original': 'Película ficticia para probar la plataforma.',
                'tipo_titulo': tipo_pelicula,
                'pais': pais,
                'fecha_estreno': date(2024, 5, 3),
                'edad_minima': edades_minimas['ATP'],
            },
        )
        serie, _ = Titulo.objects.get_or_create(
            nombre_original='Misterios de muestra',
            defaults={
                'descripcion_original': 'Serie ficticia para probar la plataforma.',
                'tipo_titulo': tipo_serie,
                'pais': pais_origen,
                'fecha_estreno': date(2023, 9, 15),
                'edad_minima': edades_minimas['+13'],
            },
        )
        titulos_demo = [
            (pelicula, ('Drama', 'Aventura', 'Acción'), 'ATP', 0),
            (serie, ('Drama', 'Misterio'), '+13', 2),
        ]
        titulos_adicionales = [
            (
                'Horizonte de cobre',
                tipo_pelicula,
                pais,
                date(2022, 4, 8),
                ('Acción', 'Aventura'),
                '+13',
                0,
            ),
            (
                'Código lunar',
                tipo_pelicula,
                pais_origen,
                date(2025, 2, 14),
                ('Ciencia ficción', 'Acción'),
                '+10',
                0,
            ),
            (
                'Estación Boreal',
                tipo_serie,
                pais,
                date(2021, 11, 5),
                ('Ciencia ficción', 'Misterio'),
                '+10',
                3,
            ),
            (
                'Archivo del viento',
                tipo_serie,
                pais_origen,
                date(2024, 7, 19),
                ('Drama', 'Misterio'),
                '+13',
                2,
            ),
            (
                'El último faro',
                tipo_serie,
                pais,
                date(2026, 8, 3),
                ('Drama', 'Misterio'),
                '+10',
                2,
            ),
            (
                'Niebla roja',
                tipo_pelicula,
                pais_origen,
                date(2026, 10, 10),
                ('Drama', 'Acción'),
                '+16',
                0,
            ),
            ('Ciudad de ceniza', tipo_pelicula, pais_origen, date(2022, 2, 11),
             ('Acción', 'Crimen'), '+16', 0),
            ('El mapa de las estrellas', tipo_pelicula, pais, date(2023, 5, 19),
             ('Ciencia ficción', 'Aventura'), '+10', 0),
            ('Domingo de verano', tipo_pelicula, pais, date(2021, 12, 3),
             ('Romance', 'Comedia'), 'ATP', 0),
            ('Ritmo de barrio', tipo_pelicula, pais_origen, date(2020, 7, 24),
             ('Drama', 'Música'), 'ATP', 0),
            ('El jardín secreto', tipo_pelicula, pais, date(2024, 3, 8),
             ('Fantasía', 'Aventura'), '+7', 0),
            ('La última jugada', tipo_pelicula, pais_origen, date(2022, 9, 16),
             ('Acción', 'Drama'), '+10', 0),
            ('Voces del puerto', tipo_pelicula, pais, date(2021, 4, 30),
             ('Drama', 'Misterio'), '+13', 0),
            ('Plan de escape', tipo_pelicula, pais_origen, date(2023, 11, 17),
             ('Acción', 'Suspenso'), '+16', 0),
            ('Risas en órbita', tipo_pelicula, pais, date(2025, 1, 10),
             ('Comedia', 'Ciencia ficción'), '+7', 0),
            ('Crónicas del bosque', tipo_pelicula, pais_origen, date(2020, 6, 12),
             ('Aventura', 'Fantasía'), '+10', 0),
            ('El testigo silencioso', tipo_pelicula, pais, date(2022, 8, 5),
             ('Misterio', 'Suspenso'), '+13', 0),
            ('Pequeños gigantes', tipo_pelicula, pais_origen, date(2024, 7, 12),
             ('Familia', 'Comedia'), 'ATP', 0),
            ('Código de medianoche', tipo_pelicula, pais, date(2025, 10, 3),
             ('Crimen', 'Suspenso'), '+16', 0),
            ('Viaje a las nubes', tipo_pelicula, pais_origen, date(2021, 1, 22),
             ('Animación', 'Aventura'), 'ATP', 0),
            ('Sombras del pasado', tipo_pelicula, pais, date(2023, 10, 27),
             ('Terror', 'Misterio'), '+16', 0),
            ('El sabor del tiempo', tipo_pelicula, pais_origen, date(2024, 2, 9),
             ('Romance', 'Drama'), '+13', 0),
            ('Turno de noche', tipo_serie, pais, date(2022, 6, 10),
             ('Crimen', 'Drama'), '+16', 3),
            ('Las voces del río', tipo_serie, pais_origen, date(2023, 4, 14),
             ('Drama', 'Misterio'), '+13', 2),
            ('Pequeños exploradores', tipo_serie, pais, date(2021, 8, 20),
             ('Familia', 'Aventura'), 'ATP', 2),
            ('Planeta azul', tipo_serie, pais_origen, date(2020, 3, 6),
             ('Documental', 'Aventura'), 'ATP', 3),
            ('Reino de cristal', tipo_serie, pais, date(2024, 9, 13),
             ('Fantasía', 'Drama'), '+10', 4),
            ('Club del misterio', tipo_serie, pais_origen, date(2022, 1, 28),
             ('Misterio', 'Comedia'), '+10', 2),
            ('Barrio central', tipo_serie, pais, date(2023, 7, 7),
             ('Comedia', 'Familia'), '+7', 3),
            ('Frontera cero', tipo_serie, pais_origen, date(2025, 6, 6),
             ('Acción', 'Ciencia ficción'), '+16', 2),
            ('Ecos de la montaña', tipo_serie, pais, date(2021, 2, 19),
             ('Documental', 'Drama'), '+7', 2),
            ('Navegantes del alba', tipo_pelicula, pais, date(2022, 3, 18),
             ('Aventura', 'Fantasía'), '+7', 0),
            ('La fórmula perdida', tipo_pelicula, pais_origen, date(2024, 6, 21),
             ('Misterio', 'Crimen'), '+13', 0),
            ('Fuego en la frontera', tipo_pelicula, pais, date(2023, 8, 11),
             ('Acción', 'Suspenso'), '+16', 0),
            ('El club de los domingos', tipo_pelicula, pais_origen, date(2021, 5, 7),
             ('Comedia', 'Familia'), 'ATP', 0),
            ('Memoria de Marte', tipo_pelicula, pais, date(2025, 4, 4),
             ('Ciencia ficción', 'Drama'), '+10', 0),
            ('Cartas al invierno', tipo_pelicula, pais_origen, date(2020, 9, 25),
             ('Romance', 'Drama'), 'ATP', 0),
            ('Operación Quimera', tipo_pelicula, pais, date(2024, 11, 15),
             ('Acción', 'Ciencia ficción'), '+16', 0),
            ('El museo de sombras', tipo_pelicula, pais_origen, date(2022, 10, 28),
             ('Terror', 'Misterio'), '+16', 0),
            ('Caminos cruzados', tipo_pelicula, pais, date(2023, 2, 17),
             ('Drama', 'Romance'), '+13', 0),
            ('Pequeña gran misión', tipo_pelicula, pais_origen, date(2025, 7, 4),
             ('Animación', 'Familia'), '+7', 0),
            ('El ritmo invisible', tipo_pelicula, pais, date(2021, 10, 1),
             ('Música', 'Drama'), '+10', 0),
            ('Río profundo', tipo_pelicula, pais_origen, date(2024, 1, 26),
             ('Documental', 'Misterio'), '+13', 0),
            ('Los archivos de octubre', tipo_serie, pais, date(2024, 10, 4),
             ('Crimen', 'Misterio'), '+16', 3),
            ('Casa de papel azul', tipo_serie, pais_origen, date(2022, 4, 22),
             ('Drama', 'Familia'), '+13', 2),
            ('Pequeños inventores', tipo_serie, pais, date(2023, 1, 13),
             ('Ciencia ficción', 'Familia'), '+7', 3),
            ('El sabor del barrio', tipo_serie, pais_origen, date(2021, 9, 3),
             ('Comedia', 'Romance'), 'ATP', 2),
            ('Guardia nocturna', tipo_serie, pais, date(2025, 3, 28),
             ('Acción', 'Suspenso'), '+16', 4),
            ('Planeta oculto', tipo_serie, pais_origen, date(2020, 11, 20),
             ('Documental', 'Fantasía'), '+10', 3),
            ('Amigos del faro', tipo_serie, pais, date(2024, 5, 24),
             ('Aventura', 'Familia'), '+7', 2),
            ('Vidas paralelas', tipo_serie, pais_origen, date(2023, 12, 8),
             ('Drama', 'Ciencia ficción'), '+13', 4),
            ('Noche sin retorno', tipo_pelicula, pais_origen, date(2026, 9, 18),
             ('Crimen', 'Suspenso'), '+18', 0),
            ('Habitación 404', tipo_serie, pais, date(2026, 6, 12),
             ('Terror', 'Misterio'), '+18', 2),
        ]
        banner_assets = {
            'La ruta de prueba': 'demo/banners/ruta.svg',
            'Misterios de muestra': 'demo/banners/misterios.svg',
            'Horizonte de cobre': 'demo/banners/horizonte.svg',
            'Código lunar': 'demo/banners/codigo-lunar.svg',
            'Estación Boreal': 'demo/banners/boreal.svg',
            'Archivo del viento': 'demo/banners/archivo.svg',
            'El último faro': 'demo/banners/faro.svg',
            'Niebla roja': 'demo/banners/niebla.svg',
        }
        for nombre, tipo, origen, estreno, categorias_titulo, edad, temporadas in titulos_adicionales:
            titulo, _ = Titulo.objects.get_or_create(
                nombre_original=nombre,
                defaults={
                    'descripcion_original': 'Título ficticio para probar la plataforma.',
                    'tipo_titulo': tipo,
                    'pais': origen,
                    'fecha_estreno': estreno,
                    'edad_minima': edades_minimas[edad],
                },
            )
            titulos_demo.append((titulo, categorias_titulo, edad, temporadas))

        contenido_principal = None
        for indice, (titulo, nombres_categoria, edad, temporadas) in enumerate(titulos_demo, start=1):
            edad_minima = edades_minimas[edad]
            if titulo.edad_minima != edad_minima:
                titulo.edad_minima = edad_minima
                titulo.save(update_fields=['edad_minima'])
            categorias_titulo = [
                categoria_por_nombre[nombre]
                for nombre in nombres_categoria
            ]
            for categoria in categorias_titulo:
                TituloCategoria.objects.get_or_create(titulo=titulo, categoria=categoria)
            TituloRolElenco.objects.get_or_create(titulo=titulo, rol_elenco=rol_actor)
            TituloRolElenco.objects.get_or_create(titulo=titulo, rol_elenco=rol_director)
            idioma_titulo_espanol = IdiomaTitulo.objects.filter(
                titulo=titulo,
                idioma=espanol,
            ).order_by('pk').first()
            if idioma_titulo_espanol is None:
                idioma_titulo_espanol = IdiomaTitulo(
                    titulo=titulo,
                    idioma=espanol,
                )
            idioma_titulo_espanol.nombre = titulo.nombre_original
            idioma_titulo_espanol.descripcion = titulo.descripcion_original or ''
            imagen_banner = banner_assets.get(titulo.nombre_original)
            if imagen_banner and idioma_titulo_espanol.imagen.name != imagen_banner:
                idioma_titulo_espanol.imagen = imagen_banner
            idioma_titulo_espanol.save()
            traduccion_titulo = TRADUCCIONES_TITULOS_INGLES.get(
                titulo.nombre_original,
            )
            if traduccion_titulo:
                IdiomaTitulo.objects.update_or_create(
                    titulo=titulo,
                    idioma=ingles,
                    defaults={
                        'nombre': traduccion_titulo[0],
                        'descripcion': traduccion_titulo[1],
                    },
                )

            contenido, _ = Contenido.objects.get_or_create(
                nombre=f'{titulo.nombre_original} - contenido principal',
                defaults={
                    'descripcion': 'Contenido ficticio de demostración.',
                    'seccion': 1,
                    'orden': indice,
                    'duracion_segundos': 3600,
                    'titulo': titulo,
                },
            )
            if not contenido.duracion_segundos:
                contenido.duracion_segundos = 3600
                contenido.save(update_fields=['duracion_segundos'])
            if titulo == pelicula:
                contenido_principal = contenido
            idioma_contenido, _ = IdiomaContenido.objects.get_or_create(
                idioma=espanol,
                contenido=contenido,
            )
            campos_idioma_contenido = []
            if not idioma_contenido.nombre:
                idioma_contenido.nombre = contenido.nombre
                campos_idioma_contenido.append('nombre')
            if not idioma_contenido.descripcion:
                idioma_contenido.descripcion = contenido.descripcion or ''
                campos_idioma_contenido.append('descripcion')
            if campos_idioma_contenido:
                idioma_contenido.save(update_fields=campos_idioma_contenido)
            if traduccion_titulo:
                IdiomaContenido.objects.update_or_create(
                    idioma=ingles,
                    contenido=contenido,
                    defaults={
                        'nombre': f'{traduccion_titulo[0]} - Main Feature',
                        'descripcion': (
                            f'Main demonstration content for '
                            f'{traduccion_titulo[0]}.'
                        ),
                    },
                )
            for calidad in (calidad_hd, calidad_full_hd):
                CalidadIdiomaContenido.objects.get_or_create(
                    idioma_contenido=idioma_contenido,
                    calidad=calidad,
                    defaults={'archivo_legacy': b'archivo de video ficticio'},
                )
            Subtitulo.objects.get_or_create(
                contenido=contenido,
                idioma=espanol,
                defaults={
                    'archivo_vtt': (
                        b'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n'
                        b'Subtitulos ficticios de demostracion.\n'
                    ),
                },
            )
            for temporada in range(1, temporadas + 1):
                for episodio in range(1, 3):
                    episodio_demo, _ = Contenido.objects.get_or_create(
                        nombre=f'{titulo.nombre_original} - T{temporada:02}E{episodio:02}',
                        defaults={
                            'descripcion': f'Episodio ficticio {episodio} de la temporada {temporada}.',
                            'seccion': temporada,
                            'orden': episodio,
                            'duracion_segundos': 2700,
                            'titulo': titulo,
                        },
                    )
                    if not episodio_demo.duracion_segundos:
                        episodio_demo.duracion_segundos = 2700
                        episodio_demo.save(update_fields=['duracion_segundos'])
                    if traduccion_titulo:
                        IdiomaContenido.objects.update_or_create(
                            idioma=ingles,
                            contenido=episodio_demo,
                            defaults={
                                'nombre': (
                                    f'Season {temporada}, Episode {episodio} - '
                                    f'{traduccion_titulo[0]}'
                                ),
                                'descripcion': (
                                    f'Episode {episodio} of season {temporada} '
                                    f'of {traduccion_titulo[0]}.'
                                ),
                            },
                        )
                    if titulo == serie:
                        idioma_episodio_espanol, _ = (
                            IdiomaContenido.objects.get_or_create(
                                idioma=espanol,
                                contenido=episodio_demo,
                            )
                        )
                        video_episodio, _ = (
                            CalidadIdiomaContenido.objects.get_or_create(
                                idioma_contenido=idioma_episodio_espanol,
                                calidad=calidad_hd,
                                defaults={
                                    'archivo_legacy': b'',
                                    'archivo': 'videos/hd.mp4',
                                },
                            )
                        )
                        if not video_episodio.archivo:
                            video_episodio.archivo = 'videos/hd.mp4'
                            video_episodio.save(update_fields=['archivo'])

        plan_basico, _ = Plan.objects.get_or_create(
            nombre='Plan Demo Basico',
            defaults={
                'descripcion': 'Plan de prueba, no representa una oferta real.',
                'cantidad_pantallas_simultaneas': 1,
            },
        )
        plan_familiar, _ = Plan.objects.get_or_create(
            nombre='Plan Demo Familiar',
            defaults={
                'descripcion': 'Plan de prueba, no representa una oferta real.',
                'cantidad_pantallas_simultaneas': 4,
            },
        )
        for plan, calidad in (
            (plan_basico, calidad_hd),
            (plan_familiar, calidad_hd),
            (plan_familiar, calidad_full_hd),
        ):
            PlanCalidad.objects.get_or_create(plan=plan, calidad=calidad)
        precio_basico, _ = Precio.objects.get_or_create(
            plan=plan_basico,
            fecha_inicio=hoy,
            defaults={'precio': 4.99},
        )
        Precio.objects.get_or_create(
            plan=plan_familiar,
            fecha_inicio=hoy,
            defaults={'precio': 8.99},
        )

        usuario, creado = Usuario.objects.get_or_create(
            username='demo@ejemplo.test',
            defaults={
                'email': 'demo@ejemplo.test',
                'first_name': 'Cuenta',
                'last_name': 'Demo',
                'pais': pais,
                'idioma': espanol,
                'is_active': True,
            },
        )
        if creado:
            usuario.set_password('DemoStreaming2026!')
            usuario.save(update_fields=['password'])

        suscripcion, _ = Suscripcion.objects.get_or_create(
            usuario=usuario,
            plan=plan_basico,
            fecha_inscripcion=hoy,
            defaults={'fecha_vigencia': hoy, 'habilitado': True},
        )
        estado_cobro, _ = EstadoCobro.objects.get_or_create(
            nombre='Aprobado',
            defaults={'descripcion': 'Estado ficticio para una prueba local.'},
        )
        marca, _ = MarcaTarjeta.objects.get_or_create(
            nombre='Tarjeta Demo',
            defaults={
                'numero_asignado': 0,
                'descripcion': 'Marca ficticia; no usar para pagos.',
            },
        )
        metodo_pago, _ = MetodoPago.objects.get_or_create(
            nombre='Pago de prueba',
            defaults={'descripcion': 'Método ficticio para datos locales.'},
        )
        tarjeta, _ = Tarjeta.objects.get_or_create(
            numero='0000',
            nombre_titular='USUARIO DE PRUEBA',
            defaults={
                'fecha_vencimiento': date(hoy.year + 2, hoy.month, 1),
                'marca_tarjeta': marca,
                'metodo_pago': metodo_pago,
                'habilitado': True,
            },
        )
        if suscripcion.tarjeta_id != tarjeta.pk:
            suscripcion.tarjeta = tarjeta
            suscripcion.save(update_fields=['tarjeta'])
        Cobro.objects.get_or_create(
            num_factura=990001,
            defaults={
                'suscripcion': suscripcion,
                'fecha_cobro': hoy,
                'estado_cobro': estado_cobro,
                'tarjeta': tarjeta,
                'numero_autorizacion': 'DEMO-AUTH-001',
                'monto': precio_basico.precio,
            },
        )

        tipo_perfil, _ = TipoPerfil.objects.get_or_create(
            nombre='Perfil Demo',
            defaults={'edad_max': 100},
        )
        imagen_avatar, _ = Imagen.objects.get_or_create(
            nombre='Avatar Dorado',
            defaults={
                'imagen': 'demo/perfiles/avatar-dorado.svg',
            },
        )
        if imagen_avatar.imagen.name != 'demo/perfiles/avatar-dorado.svg':
            imagen_avatar.imagen = 'demo/perfiles/avatar-dorado.svg'
            imagen_avatar.save(update_fields=['imagen'])
        perfil, _ = Perfil.objects.get_or_create(
            nombre='Perfil Demo',
            usuario=usuario,
            defaults={
                'imagen': imagen_avatar,
                'tipo_perfil': tipo_perfil,
            },
        )
        if perfil.imagen_id != imagen_avatar.pk:
            perfil.imagen = imagen_avatar
            perfil.save(update_fields=['imagen'])
        perfil_titulo, _ = PerfilTitulo.objects.get_or_create(
            perfil=perfil,
            titulo=pelicula,
            defaults={'calificacion': calificacion},
        )
        Porver.objects.get_or_create(
            perfil_titulo=perfil_titulo,
            fecha_agregado=hoy,
            defaults={'fecha_eliminado': None},
        )
        PerfilContenido.objects.update_or_create(
            perfil=perfil,
            contenido=contenido_principal,
            defaults={
                'segundos_vistos': 600,
                'ultima_visualizacion': timezone.now(),
            },
        )
        Registro.objects.get_or_create(
            token_disp='demo-dispositivo-001',
            defaults={
                'os': 'Navegador de prueba',
                'ultima_conexion_fecha': hoy,
                'ultima_conexion_hora': time(12, 0),
                'estado': True,
                'usuario': usuario,
            },
        )

        self.stdout.write(self.style.SUCCESS(
            'Datos de demostración cargados. No se borraron registros existentes.'
        ))
        self.stdout.write('Cuenta de prueba: demo@ejemplo.test')
        if creado:
            self.stdout.write('Contraseña local de prueba: DemoStreaming2026!')
        else:
            self.stdout.write('La cuenta demo ya existía; su contraseña no se modificó.')
