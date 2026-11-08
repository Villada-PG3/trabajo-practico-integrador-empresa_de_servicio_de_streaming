from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Categoria,
    Calificacion,
    Contenido,
    Elenco,
    Imagen,
    Idioma,
    IdiomaContenido,
    IdiomaTitulo,
    Pais,
    Perfil,
    PerfilContenido,
    PerfilTitulo,
    Plan,
    Precio,
    Porver,
    Rol,
    RolElenco,
    Suscripcion,
    TipoPerfil,
    TipoTitulo,
    Titulo,
    TituloCategoria,
    TituloRolElenco,
    Usuario,
)


class FlujoCuentaTests(TestCase):
    def setUp(self):
        self.pais = Pais.objects.create(nombre='Argentina')
        self.idioma = Idioma.objects.create(nombre='Español')

    def datos_usuario(self, email='persona@example.com', password='UnaClave-larga-2026!'):
        return {
            'email': email,
            'password': password,
            'pais': self.pais.pk,
            'idioma': self.idioma.pk,
        }

    def test_ruta_raiz_para_visitantes_lleva_a_inicio(self):
        response = self.client.get('/')

        self.assertRedirects(response, reverse('home'))
        self.assertEqual(reverse('home'), '/inicio/')

    def test_ruta_raiz_con_sesion_lleva_a_perfiles(self):
        usuario = Usuario.objects.create_user(
            username='persona@example.com',
            email='persona@example.com',
            password='UnaClave-larga-2026!',
        )
        self.client.force_login(usuario)

        response = self.client.get('/', follow=False)

        self.assertRedirects(
            response,
            reverse('perfiles'),
            fetch_redirect_response=False,
        )

    @override_settings(DEBUG=False)
    def test_ruta_inexistente_muestra_not_found_y_vuelve_a_la_raiz(self):
        response = self.client.get('/no-existe/')

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'NotFound', status_code=404)
        self.assertContains(response, '¿Te perdiste?', status_code=404)
        self.assertContains(response, 'Volver a inicio', status_code=404)
        self.assertContains(
            response,
            f'href="{reverse("pagina_inicial")}"',
            status_code=404,
        )
        self.assertContains(response, 'https://picsum.photos/1920/1080', status_code=404)

    def test_registro_crea_usuario_y_redirige_a_crear_perfil(self):
        response = self.client.post(reverse('registro'), self.datos_usuario())

        self.assertRedirects(response, reverse('crear_perfil'))
        usuario = Usuario.objects.get(username='persona@example.com')
        self.assertEqual(usuario.email, 'persona@example.com')
        self.assertEqual(usuario.pais, self.pais)
        self.assertEqual(usuario.idioma, self.idioma)
        self.assertTrue(usuario.check_password('UnaClave-larga-2026!'))
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_registro_permite_omitir_pais_e_idioma(self):
        response = self.client.post(reverse('registro'), {
            'email': 'sin-preferencias@example.com',
            'password': 'UnaClave-larga-2026!',
        })

        self.assertRedirects(response, reverse('crear_perfil'))
        usuario = Usuario.objects.get(username='sin-preferencias@example.com')
        self.assertIsNone(usuario.pais)
        self.assertIsNone(usuario.idioma)

    def test_registro_rechaza_correo_duplicado_y_clave_debil(self):
        self.client.post(reverse('registro'), self.datos_usuario())
        self.client.logout()
        response = self.client.post(reverse('registro'), self.datos_usuario())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ya existe una cuenta asociada a este correo.')
        self.assertEqual(Usuario.objects.count(), 1)

    def test_registro_rechaza_clave_debil(self):
        response = self.client.post(
            reverse('registro'),
            self.datos_usuario(password='password'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Usuario.objects.count(), 0)

    def test_inicio_de_sesion_con_suscripcion_y_sin_perfiles_va_a_crear_perfil(self):
        usuario = Usuario.objects.create_user(
            username='persona@example.com',
            email='persona@example.com',
            password='UnaClave-larga-2026!',
            pais=self.pais,
            idioma=self.idioma,
        )
        plan = Plan.objects.create(nombre='Básico', cantidad_pantallas_simultaneas=1)
        Suscripcion.objects.create(
            usuario=usuario,
            plan=plan,
            fecha_inscripcion=timezone.localdate(),
        )

        response = self.client.post(reverse('login'), {
            'email': usuario.email,
            'password': 'UnaClave-larga-2026!',
            'remember_me': '1',
        })

        self.assertRedirects(response, reverse('crear_perfil'))
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)

    def test_inicio_de_sesion_sin_plan_y_sin_perfiles_va_a_crear_perfil(self):
        Usuario.objects.create_user(
            username='persona@example.com',
            email='persona@example.com',
            password='UnaClave-larga-2026!',
            pais=self.pais,
            idioma=self.idioma,
        )

        response = self.client.post(reverse('login'), {
            'email': 'persona@example.com',
            'password': 'UnaClave-larga-2026!',
        })

        self.assertRedirects(response, reverse('crear_perfil'))

    def test_seleccionar_plan_guarda_suscripcion_en_base_de_datos(self):
        usuario = Usuario.objects.create_user(
            username='persona@example.com',
            email='persona@example.com',
            password='UnaClave-larga-2026!',
            pais=self.pais,
            idioma=self.idioma,
        )
        plan = Plan.objects.create(nombre='Estándar', cantidad_pantallas_simultaneas=2)
        Precio.objects.create(
            plan=plan,
            precio=12.5,
            fecha_inicio=timezone.localdate(),
        )
        self.client.force_login(usuario)

        response = self.client.post(reverse('seleccionar_plan'), {'plan': plan.pk})

        self.assertRedirects(response, reverse('home'))
        suscripcion = Suscripcion.objects.get(usuario=usuario)
        self.assertEqual(suscripcion.plan, plan)
        self.assertEqual(suscripcion.fecha_inscripcion, timezone.localdate())


class ReporteVentasTests(TestCase):
    def test_reporte_usa_datos_de_suscripciones_y_precios(self):
        pais = Pais.objects.create(nombre='Argentina')
        idioma = Idioma.objects.create(nombre='Español')
        usuario = Usuario.objects.create_user(
            username='persona@example.com',
            email='persona@example.com',
            password='UnaClave-larga-2026!',
            pais=pais,
            idioma=idioma,
        )
        plan = Plan.objects.create(nombre='Básico', cantidad_pantallas_simultaneas=1)
        Suscripcion.objects.create(
            usuario=usuario,
            plan=plan,
            fecha_inscripcion=timezone.localdate(),
        )
        Precio.objects.create(
            plan=plan,
            precio=9.99,
            fecha_inicio=timezone.localdate(),
        )

        response = self.client.get(reverse('reporte_ventas'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['labels_miembros_json'], ['Básico'])
        self.assertEqual(response.context['data_miembros_json'], [1])
        self.assertEqual(response.context['datasets_precios_json'][0]['data'], [9.99])
        self.assertFalse(response.context['es_demostracion'])
        self.assertEqual(response.context['total_miembros'], 1)

    def test_reporte_vacio_muestra_datos_demo_y_enlace_de_estadisticas(self):
        usuario = Usuario.objects.create_user(
            username='estadisticas@example.com',
            email='estadisticas@example.com',
            password='UnaClave-larga-2026!',
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse('reporte_ventas'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['es_demostracion'])
        self.assertEqual(response.context['total_miembros'], 268)
        self.assertEqual(response.context['cantidad_planes'], 3)
        self.assertEqual(len(response.context['fechas_precio_labels_json']), 6)
        self.assertEqual(len(response.context['datasets_precios_json']), 3)
        self.assertContains(response, 'Datos de demostración')
        self.assertContains(response, 'Estadísticas')
        self.assertContains(response, f'href="{reverse("reporte_ventas")}"')

    def test_reporte_muestra_error_para_rango_invertido(self):
        response = self.client.get(reverse('reporte_ventas'), {
            'fecha_inicio': '2026-10-20',
            'fecha_fin': '2026-10-19',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'La fecha inicial no puede ser posterior a la fecha final.')
        self.assertEqual(response.context['data_miembros_json'], [])
        self.assertFalse(response.context['es_demostracion'])


class HomeCarouselesTests(TestCase):
    def setUp(self):
        self.pais = Pais.objects.create(nombre='Argentina')
        self.idioma = Idioma.objects.create(nombre='Español')
        self.pelicula = TipoTitulo.objects.create(nombre='Película')
        self.serie = TipoTitulo.objects.create(nombre='Serie')
        self.accion = Categoria.objects.create(nombre='Acción')

    def autenticar_con_perfil(self, usuario, edad_max=100):
        self.client.force_login(usuario)
        tipo_perfil, _ = TipoPerfil.objects.get_or_create(
            nombre=f'Perfil hasta {edad_max}',
            defaults={'edad_max': edad_max},
        )
        perfil = Perfil.objects.create(
            nombre='Perfil de prueba',
            imagen=Imagen.objects.get(nombre='Avatar Azul'),
            tipo_perfil=tipo_perfil,
            usuario=usuario,
        )
        session = self.client.session
        session['perfil_activo_id'] = perfil.pk
        session.save()
        return perfil

    def crear_titulo(self, nombre, tipo, con_contenido, categoria=None, edad_minima=None):
        titulo = Titulo.objects.create(
            nombre_original=nombre,
            tipo_titulo=tipo,
            pais=self.pais,
            edad_minima=0 if edad_minima is None else edad_minima,
        )
        if categoria:
            TituloCategoria.objects.create(titulo=titulo, categoria=categoria)
        if con_contenido:
            Contenido.objects.create(
                nombre=f'{nombre} - contenido',
                seccion=1,
                orden=1,
                duracion_segundos=1000,
                titulo=titulo,
            )
        return titulo

    def agregar_imagen_titulo(self, titulo, nombre, archivo):
        return IdiomaTitulo.objects.create(
            nombre=nombre,
            titulo=titulo,
            idioma=self.idioma,
            imagen=archivo,
        )

    def test_home_separa_carouseles_y_omite_titulos_sin_contenido(self):
        pelicula = self.crear_titulo(
            'Película de acción',
            self.pelicula,
            con_contenido=True,
            categoria=self.accion,
        )
        self.agregar_imagen_titulo(
            pelicula,
            'Póster de prueba',
            'demo/posters/pelicula.svg',
        )
        serie = self.crear_titulo('Serie disponible', self.serie, con_contenido=True)
        sin_contenido = self.crear_titulo(
            'Título incompleto',
            self.pelicula,
            con_contenido=False,
            categoria=self.accion,
        )
        usuario = Usuario.objects.create_user(
            username='catalogo@example.com',
            email='catalogo@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        carruseles = {
            carrusel['etiqueta']: carrusel['titulos']
            for carrusel in response.context['carruseles']
        }
        self.assertEqual(
            [titulo.pk for titulo in carruseles['Películas']],
            [pelicula.pk],
        )
        self.assertEqual(carruseles['Películas'][0].duracion_formateada, '17 min')
        self.assertContains(response, '|</span> 17 min')
        self.assertEqual(
            [titulo.pk for titulo in carruseles['Series']],
            [serie.pk],
        )
        self.assertEqual(
            [titulo.pk for titulo in carruseles['Acción']],
            [pelicula.pk],
        )
        self.assertContains(response, 'src="/media/demo/posters/pelicula.svg"')
        for titulos in carruseles.values():
            self.assertNotIn(sin_contenido.pk, [titulo.pk for titulo in titulos])
            self.assertTrue(all(titulo.contenidos.exists() for titulo in titulos))

    def test_home_usa_nombre_y_descripcion_del_idioma_del_usuario_con_fallbacks(self):
        ingles = Idioma.objects.create(nombre='Inglés')
        titulo_localizado = self.crear_titulo(
            'Nombre original',
            self.pelicula,
            con_contenido=True,
        )
        titulo_localizado.descripcion_original = 'Descripción original'
        titulo_localizado.fecha_estreno = date(2026, 1, 1)
        titulo_localizado.save(update_fields=['descripcion_original', 'fecha_estreno'])
        self.agregar_imagen_titulo(
            titulo_localizado,
            'Nombre localizado',
            'demo/localizado.svg',
        )
        IdiomaTitulo.objects.filter(titulo=titulo_localizado).update(idioma=ingles)

        titulo_parcial = self.crear_titulo(
            'Nombre original alternativo',
            self.pelicula,
            con_contenido=True,
        )
        titulo_parcial.fecha_estreno = date(2026, 1, 2)
        titulo_parcial.save(update_fields=['fecha_estreno'])
        IdiomaTitulo.objects.create(
            titulo=titulo_parcial,
            idioma=ingles,
            nombre='',
            descripcion='Descripción localizada',
            imagen='demo/parcial.svg',
        )
        usuario = Usuario.objects.create_user(
            username='localizacion@example.com',
            email='localizacion@example.com',
            password='UnaClave-larga-2026!',
            idioma=ingles,
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'))

        self.assertContains(respuesta, 'Nombre localizado')
        self.assertContains(respuesta, 'Descripción original')
        self.assertContains(respuesta, 'Nombre original alternativo')
        self.assertContains(respuesta, 'Descripción localizada')
        self.assertNotContains(respuesta, 'Nombre original</h1>')

    def test_idioma_contenido_puede_tener_imagen_de_episodio(self):
        titulo = self.crear_titulo('Serie con episodio', self.serie, con_contenido=True)
        contenido = titulo.contenidos.get()
        idioma_contenido = IdiomaContenido.objects.create(
            contenido=contenido,
            idioma=self.idioma,
            imagen='demo/episodios/episodio.svg',
        )

        self.assertEqual(
            idioma_contenido.imagen.url,
            '/media/demo/episodios/episodio.svg',
        )

    def test_carouseles_limitan_a_treinta_titulos_por_categoria(self):
        usuario = Usuario.objects.create_user(
            username='limite@example.com',
            email='limite@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)
        for indice in range(35):
            self.crear_titulo(
                f'Película de acción {indice:02}',
                self.pelicula,
                con_contenido=True,
                categoria=self.accion,
            )

        respuesta = self.client.get(reverse('home'))

        carruseles = {
            carrusel['etiqueta']: carrusel['titulos']
            for carrusel in respuesta.context['carruseles']
        }
        self.assertEqual(len(carruseles['Películas']), 30)
        self.assertEqual(len(carruseles['Acción']), 30)

    def test_inicio_muestra_los_primeros_treinta_titulos_de_mi_lista_solo_en_inicio(self):
        usuario = Usuario.objects.create_user(
            username='mi-lista-home@example.com',
            email='mi-lista-home@example.com',
            password='UnaClave-larga-2026!',
        )
        perfil = self.autenticar_con_perfil(usuario)
        titulos = [
            self.crear_titulo(
                f'Título guardado {indice:02}',
                self.pelicula,
                con_contenido=True,
            )
            for indice in range(32)
        ]
        for titulo in titulos:
            perfil_titulo = PerfilTitulo.objects.create(perfil=perfil, titulo=titulo)
            Porver.objects.create(
                perfil_titulo=perfil_titulo,
                fecha_agregado=date(2026, 1, 1),
            )

        respuesta_inicio = self.client.get(reverse('home'))
        carruseles_inicio = respuesta_inicio.context['carruseles']
        mi_lista = carruseles_inicio[0]

        self.assertEqual(mi_lista['etiqueta'], 'Mi Lista')
        self.assertTrue(mi_lista['es_mi_lista'])
        self.assertEqual(
            [titulo.pk for titulo in mi_lista['titulos']],
            [titulo.pk for titulo in titulos[:30]],
        )
        self.assertContains(respuesta_inicio, 'id="carousel-title-1">Mi Lista</h2>')
        self.assertContains(
            respuesta_inicio,
            'Quitar de Mi Lista: Título guardado 00',
        )

        for tipo in ('series', 'peliculas'):
            respuesta_filtrada = self.client.get(reverse('home'), {'tipo': tipo})
            etiquetas = [
                carrusel['etiqueta']
                for carrusel in respuesta_filtrada.context['carruseles']
            ]
            self.assertNotIn('Mi Lista', etiquetas)
            self.assertNotIn('Series', etiquetas)
            self.assertNotIn('Películas', etiquetas)

    def test_inicio_ordena_carruseles_por_reproducciones_lista_tipos_y_categorias(self):
        usuario = Usuario.objects.create_user(
            username='orden-carruseles@example.com',
            email='orden-carruseles@example.com',
            password='UnaClave-larga-2026!',
        )
        perfil = self.autenticar_con_perfil(usuario)
        zoologia = Categoria.objects.create(nombre='Zoología')
        aventura = Categoria.objects.create(nombre='Aventura')
        pelicula_reproducida = self.crear_titulo(
            'Película reproducida',
            self.pelicula,
            con_contenido=True,
            categoria=zoologia,
        )
        serie = self.crear_titulo(
            'Serie de aventura',
            self.serie,
            con_contenido=True,
            categoria=aventura,
        )
        perfil_titulo = PerfilTitulo.objects.create(
            perfil=perfil,
            titulo=pelicula_reproducida,
        )
        Porver.objects.create(
            perfil_titulo=perfil_titulo,
            fecha_agregado=date(2026, 1, 1),
        )
        PerfilContenido.objects.create(
            perfil=perfil,
            contenido=pelicula_reproducida.contenidos.get(),
            segundos_vistos=100,
            ultima_visualizacion=timezone.now(),
        )

        respuesta = self.client.get(reverse('home'))

        self.assertEqual(
            [carrusel['etiqueta'] for carrusel in respuesta.context['carruseles']],
            [
                'Más reproducidos',
                'Mi Lista',
                'Series',
                'Películas',
                'Aventura',
                'Zoología',
            ],
        )

    def test_pagina_categorias_muestra_categorias_alfabeticamente_y_filtra_inicio(self):
        zoologia = Categoria.objects.create(nombre='Zoología')
        aventura = Categoria.objects.create(nombre='Aventura')
        pelicula = self.crear_titulo(
            'Película de aventura',
            self.pelicula,
            con_contenido=True,
            categoria=aventura,
        )
        pelicula.fecha_estreno = date(2024, 1, 1)
        pelicula.save(update_fields=['fecha_estreno'])
        pelicula_reciente = self.crear_titulo(
            'Estreno de aventura',
            self.pelicula,
            con_contenido=True,
            categoria=aventura,
        )
        pelicula_reciente.fecha_estreno = date(2026, 1, 1)
        pelicula_reciente.save(update_fields=['fecha_estreno'])
        titulo_otra_categoria = self.crear_titulo(
            'Título zoológico',
            self.serie,
            con_contenido=True,
            categoria=zoologia,
        )
        titulo_otra_categoria.fecha_estreno = date(2026, 2, 1)
        titulo_otra_categoria.save(update_fields=['fecha_estreno'])
        for titulo in (pelicula, pelicula_reciente, titulo_otra_categoria):
            self.agregar_imagen_titulo(
                titulo,
                f'Banner {titulo.nombre_original}',
                f'demo/banners/{titulo.pk}.svg',
            )
        self.crear_titulo(
            'Serie zoológica sin banner',
            self.serie,
            con_contenido=True,
            categoria=zoologia,
        )
        usuario = Usuario.objects.create_user(
            username='categorias-home@example.com',
            email='categorias-home@example.com',
            password='UnaClave-larga-2026!',
        )
        perfil = self.autenticar_con_perfil(usuario)
        titulos_en_lista = (pelicula, pelicula_reciente, titulo_otra_categoria)
        for titulo in titulos_en_lista:
            perfil_titulo = PerfilTitulo.objects.create(perfil=perfil, titulo=titulo)
            Porver.objects.create(
                perfil_titulo=perfil_titulo,
                fecha_agregado=date(2026, 1, 2),
            )

        respuesta_categorias = self.client.get(reverse('categorias'))

        self.assertEqual(respuesta_categorias.status_code, 200)
        self.assertEqual(
            list(respuesta_categorias.context['categorias']),
            [aventura, zoologia],
        )
        self.assertContains(respuesta_categorias, 'Descubre tu próxima historia')
        respuesta_filtrada = self.client.get(
            reverse('home'),
            {'categoria': aventura.pk},
        )
        self.assertRegex(
            respuesta_filtrada.content.decode(),
            rf'<a class="nav-link active"\s+href="{reverse("categorias")}">Categorías</a>',
        )
        self.assertRegex(
            respuesta_filtrada.content.decode(),
            rf'<a class="nav-link"\s+href="{reverse("home")}">Inicio</a>',
        )
        self.assertContains(respuesta_filtrada, 'Catálogo de: Aventura')
        etiquetas = [
            carrusel['etiqueta']
            for carrusel in respuesta_filtrada.context['carruseles']
        ]
        self.assertNotIn('Aventura', etiquetas)
        self.assertEqual(
            [titulo.pk for titulo in respuesta_filtrada.context['carruseles'][0]['titulos']],
            [pelicula_reciente.pk, pelicula.pk],
        )
        carruseles_filtrados = {
            carrusel['etiqueta']: carrusel['titulos']
            for carrusel in respuesta_filtrada.context['carruseles']
        }
        self.assertEqual(
            [titulo.pk for titulo in carruseles_filtrados['Mi Lista']],
            [pelicula_reciente.pk, pelicula.pk],
        )
        self.assertEqual(
            [banner['titulo'].pk for banner in respuesta_filtrada.context['banners']],
            [pelicula_reciente.pk, pelicula.pk],
        )

    def test_nav_filtra_inicio_por_tipo_y_inicio_quita_el_filtro(self):
        serie_categoria = Categoria.objects.create(nombre='Misterio')
        pelicula = self.crear_titulo(
            'Película para filtrar',
            self.pelicula,
            con_contenido=True,
            categoria=self.accion,
        )
        serie = self.crear_titulo(
            'Serie para filtrar',
            self.serie,
            con_contenido=True,
            categoria=serie_categoria,
        )
        usuario = Usuario.objects.create_user(
            username='filtros@example.com',
            email='filtros@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta_series = self.client.get(reverse('home'), {'tipo': 'series'})
        carruseles_series = respuesta_series.context['carruseles']
        titulos_series = [
            titulo
            for carrusel in carruseles_series
            for titulo in carrusel['titulos']
        ]
        etiquetas_series = [carrusel['etiqueta'] for carrusel in carruseles_series]

        self.assertTrue(titulos_series)
        self.assertTrue(all(titulo.pk == serie.pk for titulo in titulos_series))
        self.assertIn('Misterio', etiquetas_series)
        self.assertNotIn('Películas', etiquetas_series)
        self.assertNotIn('Series', etiquetas_series)
        self.assertNotIn('Acción', etiquetas_series)
        self.assertContains(respuesta_series, '?tipo=peliculas')
        self.assertEqual(respuesta_series.context['filtro_tipo'], 'series')

        respuesta_peliculas = self.client.get(reverse('home'), {'tipo': 'peliculas'})
        carruseles_peliculas = respuesta_peliculas.context['carruseles']
        titulos_peliculas = [
            titulo
            for carrusel in carruseles_peliculas
            for titulo in carrusel['titulos']
        ]
        etiquetas_peliculas = [
            carrusel['etiqueta'] for carrusel in carruseles_peliculas
        ]

        self.assertTrue(titulos_peliculas)
        self.assertTrue(all(titulo.pk == pelicula.pk for titulo in titulos_peliculas))
        self.assertIn('Acción', etiquetas_peliculas)
        self.assertNotIn('Series', etiquetas_peliculas)
        self.assertNotIn('Películas', etiquetas_peliculas)
        self.assertNotIn('Misterio', etiquetas_peliculas)

        respuesta_inicio = self.client.get(reverse('home'))
        etiquetas_inicio = [
            carrusel['etiqueta'] for carrusel in respuesta_inicio.context['carruseles']
        ]

        self.assertIn('Películas', etiquetas_inicio)
        self.assertIn('Series', etiquetas_inicio)
        self.assertEqual(respuesta_inicio.context['filtro_tipo'], '')

    def test_perfil_de_17_anos_solo_ve_titulos_hasta_17_en_catalogo_y_banner(self):
        permitidos = [
            self.crear_titulo('Clasificación 16', self.pelicula, True, edad_minima=16),
            self.crear_titulo('Clasificación 17', self.serie, True, edad_minima=17),
        ]
        restringidos = self.crear_titulo(
            'Clasificación 18',
            self.pelicula,
            True,
            edad_minima=18,
        )
        sin_clasificacion = Titulo.objects.create(
            nombre_original='Sin clasificación',
            tipo_titulo=self.pelicula,
            pais=self.pais,
            edad_minima=None,
        )
        for indice, titulo in enumerate((*permitidos, restringidos, sin_clasificacion)):
            titulo.fecha_estreno = date(2026, 1, indice + 1)
            titulo.save(update_fields=['fecha_estreno'])
            self.agregar_imagen_titulo(
                titulo,
                f'Banner {titulo.nombre_original}',
                f'demo/banners/{indice}.svg',
            )
        usuario = Usuario.objects.create_user(
            username='diecisiete@example.com',
            email='diecisiete@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario, edad_max=17)

        respuesta = self.client.get(reverse('home'))

        titulos_carruseles = {
            titulo.pk
            for carrusel in respuesta.context['carruseles']
            for titulo in carrusel['titulos']
        }
        titulos_banner = {
            banner['titulo'].pk for banner in respuesta.context['banners']
        }
        self.assertEqual(titulos_carruseles, {titulo.pk for titulo in permitidos})
        self.assertEqual(titulos_banner, {titulo.pk for titulo in permitidos})
        self.assertNotIn(restringidos.pk, titulos_carruseles)
        self.assertNotIn(sin_clasificacion.pk, titulos_carruseles)

    def test_boton_de_home_agrega_y_quita_titulo_de_mi_lista(self):
        titulo = self.crear_titulo(
            'Título para guardar',
            self.pelicula,
            con_contenido=True,
        )
        titulo.fecha_estreno = date(2026, 5, 1)
        titulo.save(update_fields=['fecha_estreno'])
        self.agregar_imagen_titulo(titulo, 'Banner para guardar', 'demo/banner.svg')
        usuario = Usuario.objects.create_user(
            username='mi-lista-home@example.com',
            email='mi-lista-home@example.com',
            password='UnaClave-larga-2026!',
        )
        perfil = self.autenticar_con_perfil(usuario)
        url_toggle = reverse('toggle_mi_lista', args=[titulo.pk])

        respuesta_home = self.client.get(reverse('home'))
        respuesta_agregar = self.client.post(url_toggle, {
            'next': '/?tipo=peliculas',
        })
        respuesta_guardado = self.client.get(reverse('home'))
        respuesta_quitar = self.client.post(url_toggle, {
            'next': '/?tipo=peliculas',
        })

        self.assertContains(respuesta_home, 'Agregar a Mi Lista: Banner para guardar')
        self.assertEqual(respuesta_agregar.status_code, 302)
        self.assertEqual(respuesta_agregar.url, '/?tipo=peliculas')
        self.assertContains(respuesta_guardado, 'Quitar de Mi Lista: Banner para guardar')
        self.assertEqual(respuesta_quitar.url, '/?tipo=peliculas')
        self.assertEqual(
            Porver.objects.filter(
                perfil_titulo__perfil=perfil,
                perfil_titulo__titulo=titulo,
                fecha_eliminado__isnull=True,
            ).count(),
            0,
        )
        self.assertEqual(
            Porver.objects.filter(
                perfil_titulo__perfil=perfil,
                perfil_titulo__titulo=titulo,
            ).count(),
            1,
        )

    def test_boton_de_mi_lista_acepta_peticion_ajax_y_devuelve_estado(self):
        titulo = self.crear_titulo(
            'Título con respuesta JSON',
            self.pelicula,
            con_contenido=True,
        )
        usuario = Usuario.objects.create_user(
            username='mi-lista-ajax@example.com',
            email='mi-lista-ajax@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.post(
            reverse('toggle_mi_lista', args=[titulo.pk]),
            {'next': reverse('home')},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['titulo_id'], titulo.pk)
        self.assertTrue(respuesta.json()['en_mi_lista'])

    def test_tarjeta_muestra_boton_de_detalles_y_ficha_de_calificacion(self):
        titulo = self.crear_titulo(
            'Historia para calificar',
            self.pelicula,
            con_contenido=True,
        )
        titulo.descripcion_original = 'Una historia para probar la ficha.'
        titulo.save(update_fields=['descripcion_original'])
        self.agregar_imagen_titulo(
            titulo,
            'Imagen de la historia',
            'demo/banners/historia.svg',
        )
        usuario = Usuario.objects.create_user(
            username='ficha-titulo@example.com',
            email='ficha-titulo@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'))

        self.assertContains(respuesta, 'data-title-details-open')
        self.assertContains(respuesta, 'bi bi-list')
        self.assertContains(respuesta, 'role="dialog" aria-modal="true"')
        self.assertContains(respuesta, 'Imagen de la historia')
        self.assertContains(respuesta, 'Una historia para probar la ficha.')
        self.assertContains(
            respuesta,
            reverse('calificar_titulo', args=[titulo.pk]),
        )
        self.assertContains(respuesta, 'data-title-rating-star="5"')
        self.assertContains(respuesta, 'data-title-rating="2.5"')
        self.assertContains(respuesta, 'Promedio de 3 de 5 estrellas')

    def test_puntuacion_de_titulo_se_guarda_en_incrementos_de_media_estrella(self):
        titulo = self.crear_titulo(
            'Título puntuado',
            self.pelicula,
            con_contenido=True,
        )
        usuario = Usuario.objects.create_user(
            username='puntuacion-titulo@example.com',
            email='puntuacion-titulo@example.com',
            password='UnaClave-larga-2026!',
        )
        perfil = self.autenticar_con_perfil(usuario)
        url = reverse('calificar_titulo', args=[titulo.pk])

        respuesta = self.client.post(
            url,
            {'puntuacion': '3.5'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['puntuacion'], '3.5')
        perfil_titulo = PerfilTitulo.objects.get(perfil=perfil, titulo=titulo)
        self.assertEqual(perfil_titulo.calificacion.estrellas, Decimal('3.5'))
        self.assertEqual(perfil_titulo.calificacion.porcentaje_gusto, 70)

        for puntuacion in ('0', '5.5', '2.3', 'invalida'):
            with self.subTest(puntuacion=puntuacion):
                respuesta_invalida = self.client.post(
                    url,
                    {'puntuacion': puntuacion},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                    HTTP_ACCEPT='application/json',
                )
                self.assertEqual(respuesta_invalida.status_code, 400)
        perfil_titulo.refresh_from_db()
        self.assertEqual(perfil_titulo.calificacion.estrellas, Decimal('3.5'))
        respuesta_inicio = self.client.get(reverse('home'))
        self.assertContains(respuesta_inicio, 'data-title-rating="3.5"')

        cliente_reiniciado = self.client_class()
        cliente_reiniciado.force_login(usuario)
        session = cliente_reiniciado.session
        session['perfil_activo_id'] = perfil.pk
        session.save()
        respuesta_reinicio = cliente_reiniciado.get(reverse('home'))
        self.assertContains(respuesta_reinicio, 'data-title-rating="3.5"')

    def test_promedio_publico_redondea_estrellas_y_se_muestra_junto_al_nombre(self):
        redondea_arriba = self.crear_titulo(
            'Promedio tres y medio',
            self.pelicula,
            con_contenido=True,
        )
        redondea_abajo = self.crear_titulo(
            'Promedio tres y cuarto',
            self.pelicula,
            con_contenido=True,
        )
        usuario = Usuario.objects.create_user(
            username='promedios-estrellas@example.com',
            email='promedios-estrellas@example.com',
            password='UnaClave-larga-2026!',
        )
        perfil_uno = self.autenticar_con_perfil(usuario)
        calificacion_tres = Calificacion.objects.create(
            nombre='3 estrellas',
            porcentaje_gusto=60,
            estrellas=Decimal('3'),
        )
        calificacion_tres_y_media = Calificacion.objects.create(
            nombre='3.5 estrellas',
            porcentaje_gusto=70,
            estrellas=Decimal('3.5'),
        )
        calificacion_cuatro = Calificacion.objects.create(
            nombre='4 estrellas',
            porcentaje_gusto=80,
            estrellas=Decimal('4'),
        )
        for titulo in (redondea_arriba, redondea_abajo):
            PerfilTitulo.objects.create(
                perfil=perfil_uno,
                titulo=titulo,
                calificacion=calificacion_tres,
            )

        perfil_dos = Perfil.objects.create(
            nombre='Segundo perfil',
            imagen=perfil_uno.imagen,
            tipo_perfil=perfil_uno.tipo_perfil,
            usuario=usuario,
        )
        PerfilTitulo.objects.create(
            perfil=perfil_dos,
            titulo=redondea_arriba,
            calificacion=calificacion_cuatro,
        )
        PerfilTitulo.objects.create(
            perfil=perfil_dos,
            titulo=redondea_abajo,
            calificacion=calificacion_tres_y_media,
        )
        session = self.client.session
        session['perfil_activo_id'] = perfil_dos.pk
        session.save()

        respuesta = self.client.get(reverse('home'))

        titulos = {
            titulo.pk: titulo
            for carrusel in respuesta.context['carruseles']
            for titulo in carrusel['titulos']
        }
        self.assertEqual(
            titulos[redondea_arriba.pk].estrellas_promedio_redondeado,
            4,
        )
        self.assertEqual(
            titulos[redondea_abajo.pk].estrellas_promedio_redondeado,
            3,
        )
        self.assertContains(respuesta, 'Promedio de 4 de 5 estrellas')
        self.assertContains(respuesta, 'Promedio de 3 de 5 estrellas')

    def test_boton_mi_lista_rechaza_titulo_fuera_de_la_edad_del_perfil(self):
        titulo = self.crear_titulo(
            'Solo adultos',
            self.pelicula,
            con_contenido=True,
            edad_minima=18,
        )
        usuario = Usuario.objects.create_user(
            username='perfil-menor@example.com',
            email='perfil-menor@example.com',
            password='UnaClave-larga-2026!',
        )
        perfil = self.autenticar_con_perfil(usuario, edad_max=17)

        respuesta = self.client.post(
            reverse('toggle_mi_lista', args=[titulo.pk]),
            {'next': reverse('home')},
        )

        self.assertRedirects(respuesta, reverse('home'))
        self.assertFalse(
            PerfilTitulo.objects.filter(perfil=perfil, titulo=titulo).exists()
        )

    def test_busqueda_coincide_con_nombre_mostrado_y_respeta_edad(self):
        ingles = Idioma.objects.create(nombre='Inglés')
        localizado = self.crear_titulo(
            'Original no visible',
            self.pelicula,
            con_contenido=True,
        )
        IdiomaTitulo.objects.create(
            titulo=localizado,
            idioma=ingles,
            nombre='The Northern Lights',
            descripcion='',
        )
        sin_traduccion = self.crear_titulo(
            'Northern Stories',
            self.serie,
            con_contenido=True,
        )
        edad_restringida = self.crear_titulo(
            'Northern Adults',
            self.pelicula,
            con_contenido=True,
            edad_minima=18,
        )
        usuario = Usuario.objects.create_user(
            username='busqueda@example.com',
            email='busqueda@example.com',
            password='UnaClave-larga-2026!',
            idioma=ingles,
        )
        perfil = self.autenticar_con_perfil(usuario, edad_max=17)
        PerfilTitulo.objects.create(perfil=perfil, titulo=localizado)
        Porver.objects.create(
            perfil_titulo=PerfilTitulo.objects.get(perfil=perfil, titulo=localizado),
            fecha_agregado=date(2026, 1, 1),
        )

        respuesta = self.client.get(reverse('buscar_titulos'), {'q': 'northern'})

        self.assertEqual(respuesta.status_code, 200)
        resultados = respuesta.json()['resultados']
        self.assertEqual(
            [(resultado['nombre'], resultado['tipo']) for resultado in resultados],
            [('Northern Stories', 'Serie'), ('The Northern Lights', 'Película')],
        )
        self.assertNotIn(
            'Original no visible',
            [resultado['nombre'] for resultado in resultados],
        )
        self.assertNotIn(
            edad_restringida.pk,
            [resultado['id'] for resultado in resultados],
        )
        self.assertEqual(
            next(r['url'] for r in resultados if r['id'] == localizado.pk),
            f'{reverse("home")}?titulo={localizado.pk}',
        )
        resultado_guardado = next(r for r in resultados if r['id'] == localizado.pk)
        resultado_disponible = next(r for r in resultados if r['id'] == sin_traduccion.pk)
        self.assertTrue(resultado_guardado['en_mi_lista'])
        self.assertFalse(resultado_disponible['en_mi_lista'])
        self.assertEqual(resultado_disponible['puntuacion_perfil'], '2.5')
        self.assertEqual(
            resultado_disponible['rating_url'],
            reverse('calificar_titulo', args=[sin_traduccion.pk]),
        )
        self.assertIn('descripcion', resultado_disponible)
        self.assertEqual(
            resultado_disponible['toggle_url'],
            reverse('toggle_mi_lista', args=[sin_traduccion.pk]),
        )
        self.assertTrue(sin_traduccion.pk in [resultado['id'] for resultado in resultados])

    def test_busqueda_requiere_perfil_activo(self):
        usuario = Usuario.objects.create_user(
            username='busqueda-sin-perfil@example.com',
            email='busqueda-sin-perfil@example.com',
            password='UnaClave-larga-2026!',
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse('buscar_titulos'), {'q': 'test'})

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('error', respuesta.json())

    def test_busqueda_sin_idioma_respeta_el_fallback_del_nombre_mostrado(self):
        primero = Idioma.objects.create(nombre='A idioma')
        segundo = Idioma.objects.create(nombre='B idioma')
        titulo = self.crear_titulo(
            'Nombre original visible',
            self.pelicula,
            con_contenido=True,
        )
        IdiomaTitulo.objects.create(
            titulo=titulo,
            idioma=primero,
            nombre='',
            descripcion='Descripción disponible',
        )
        IdiomaTitulo.objects.create(
            titulo=titulo,
            idioma=segundo,
            nombre='Nombre traducido no visible',
            descripcion='',
        )
        usuario = Usuario.objects.create_user(
            username='busqueda-sin-idioma@example.com',
            email='busqueda-sin-idioma@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta_traducido = self.client.get(
            reverse('buscar_titulos'),
            {'q': 'traducido'},
        )
        respuesta_original = self.client.get(
            reverse('buscar_titulos'),
            {'q': 'original visible'},
        )

        self.assertEqual(respuesta_traducido.json()['resultados'], [])
        self.assertEqual(
            [resultado['nombre'] for resultado in respuesta_original.json()['resultados']],
            ['Nombre original visible'],
        )

    def test_busqueda_devuelve_todos_los_resultados_en_orden_alfabetico(self):
        usuario = Usuario.objects.create_user(
            username='busqueda-completa@example.com',
            email='busqueda-completa@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)
        nombres = [f'Coincidencia {indice:02}' for indice in range(12)]
        for nombre in reversed(nombres):
            self.crear_titulo(nombre, self.pelicula, con_contenido=True)

        respuesta = self.client.get(reverse('buscar_titulos'), {'q': 'coincidencia'})

        self.assertEqual(
            [resultado['nombre'] for resultado in respuesta.json()['resultados']],
            nombres,
        )

    def test_home_filtra_por_titulo_seleccionado_desde_busqueda(self):
        resultado = self.crear_titulo(
            'Resultado específico',
            self.pelicula,
            con_contenido=True,
        )
        otro = self.crear_titulo('Otro resultado', self.serie, con_contenido=True)
        usuario = Usuario.objects.create_user(
            username='click-busqueda@example.com',
            email='click-busqueda@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'), {'titulo': resultado.pk})

        titulos = {
            titulo.pk
            for carrusel in respuesta.context['carruseles']
            for titulo in carrusel['titulos']
        }
        self.assertEqual(titulos, {resultado.pk})
        self.assertNotIn(otro.pk, titulos)

    def test_inicio_autenticado_sin_perfil_activo_no_muestra_titulos(self):
        usuario = Usuario.objects.create_user(
            username='sin-perfil-activo@example.com',
            email='sin-perfil-activo@example.com',
            password='UnaClave-larga-2026!',
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse('home'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['carruseles'], [])
        self.assertEqual(respuesta.context['banners'], [])

    def test_categoria_del_carrusel_va_primero_y_restantes_alfabeticamente(self):
        misterio = Categoria.objects.create(nombre='Misterio')
        aventura = Categoria.objects.create(nombre='Aventura')
        suspenso = Categoria.objects.create(nombre='Suspenso')
        titulo = self.crear_titulo(
            'Misterio entre montañas',
            self.pelicula,
            con_contenido=True,
            edad_minima=13,
        )
        for categoria in (suspenso, misterio, aventura):
            TituloCategoria.objects.create(titulo=titulo, categoria=categoria)
        usuario = Usuario.objects.create_user(
            username='categorias@example.com',
            email='categorias@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'))

        carruseles = {
            carrusel['etiqueta']: carrusel['titulos']
            for carrusel in respuesta.context['carruseles']
        }
        self.assertEqual(
            [categoria.nombre for categoria in carruseles['Misterio'][0].categorias_ordenadas],
            ['Misterio', 'Aventura', 'Suspenso'],
        )
        self.assertEqual(carruseles['Misterio'][0].clasificacion_edad, '+13')
        self.assertEqual(
            [categoria.nombre for categoria in carruseles['Películas'][0].categorias_ordenadas],
            ['Aventura', 'Misterio', 'Suspenso'],
        )
        self.assertEqual(carruseles['Películas'][0].clasificacion_edad, '+13')
        self.assertNotIn('+13', carruseles)
        self.assertNotIn('+7', carruseles)
        html = respuesta.content.decode()
        self.assertLess(html.index('title-card-type'), html.index('Clasificación:'))
        self.assertLess(html.index('Clasificación:'), html.index('title-card-categories'))

    def test_series_muestran_temporadas_con_secciones_que_tienen_contenido(self):
        serie = self.crear_titulo('Serie por temporadas', self.serie, con_contenido=True)
        categoria = Categoria.objects.create(nombre='Misterio')
        TituloCategoria.objects.create(titulo=serie, categoria=categoria)
        for seccion in (1, 1, 2, 0):
            Contenido.objects.create(
                nombre=f'Temporada {seccion} - episodio {serie.contenidos.count()}',
                seccion=seccion,
                orden=1,
                duracion_segundos=1000,
                titulo=serie,
            )
        usuario = Usuario.objects.create_user(
            username='temporadas@example.com',
            email='temporadas@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'))
        titulo_en_carrusel = next(
            titulo
            for carrusel in respuesta.context['carruseles']
            if carrusel['etiqueta'] == 'Series'
            for titulo in carrusel['titulos']
            if titulo.pk == serie.pk
        )

        self.assertEqual(titulo_en_carrusel.temporadas, 2)
        self.assertContains(respuesta, '|</span> 2 temporadas')

    def test_mas_reproducidos_solo_cuenta_reproducciones_desde_el_diez_por_ciento(self):
        mas_visto = self.crear_titulo('Título más visto', self.pelicula, con_contenido=True)
        menos_visto = self.crear_titulo('Título menos visto', self.serie, con_contenido=True)
        debajo_del_umbral = self.crear_titulo(
            'Título bajo el umbral',
            self.pelicula,
            con_contenido=True,
        )
        usuario = Usuario.objects.create_user(
            username='catalogo@example.com',
            email='catalogo@example.com',
            password='UnaClave-larga-2026!',
        )
        tipo_perfil = TipoPerfil.objects.create(nombre='Perfil de prueba', edad_max=100)
        imagen = Imagen.objects.create(
            nombre='Avatar de prueba',
            imagen='avatar.svg',
        )

        for indice in range(3):
            perfil = Perfil.objects.create(
                nombre=f'Perfil {indice}',
                imagen=imagen,
                tipo_perfil=tipo_perfil,
                usuario=usuario,
            )
            titulo = mas_visto if indice < 2 else menos_visto
            PerfilContenido.objects.create(
                perfil=perfil,
                contenido=titulo.contenidos.get(),
                segundos_vistos=100,
                ultima_visualizacion=timezone.now(),
            )

        perfil = Perfil.objects.get(nombre='Perfil 2')
        PerfilContenido.objects.create(
            perfil=perfil,
            contenido=menos_visto.contenidos.get(),
            segundos_vistos=99,
            ultima_visualizacion=timezone.now(),
        )
        PerfilContenido.objects.create(
            perfil=perfil,
            contenido=debajo_del_umbral.contenidos.get(),
            segundos_vistos=99,
            ultima_visualizacion=timezone.now(),
        )
        response = self.client.get(reverse('home'))
        carrusel_popular = response.context['carruseles'][0]

        self.assertEqual(carrusel_popular['etiqueta'], 'Populares')
        self.assertEqual(
            [titulo.pk for titulo in carrusel_popular['titulos']],
            [mas_visto.pk, menos_visto.pk],
        )


    def test_visitante_solo_ve_top_diez_populares_con_numeracion(self):
        usuario = Usuario.objects.create_user(
            username='reproducciones@example.com',
            email='reproducciones@example.com',
            password='UnaClave-larga-2026!',
        )
        tipo_perfil = TipoPerfil.objects.create(nombre='Perfil de prueba', edad_max=100)
        primer_titulo = None

        for indice in range(12):
            titulo = self.crear_titulo(
                f'Título {indice:02}',
                self.pelicula,
                con_contenido=True,
            )
            primer_titulo = primer_titulo or titulo
            imagen = Imagen.objects.create(
                nombre=f'Avatar {indice}',
                imagen=f'avatar-{indice}.svg',
            )
            perfil = Perfil.objects.create(
                nombre=f'Perfil {indice}',
                imagen=imagen,
                tipo_perfil=tipo_perfil,
                usuario=usuario,
            )
            PerfilContenido.objects.create(
                perfil=perfil,
                contenido=titulo.contenidos.get(),
                segundos_vistos=100,
                ultima_visualizacion=timezone.now(),
            )

        respuesta = self.client.get(reverse('home'))
        carruseles = respuesta.context['carruseles']

        self.assertEqual(len(carruseles), 1)
        self.assertEqual(carruseles[0]['etiqueta'], 'Populares')
        self.assertTrue(carruseles[0]['mostrar_top'])
        self.assertEqual(len(carruseles[0]['titulos']), 10)
        self.assertEqual(carruseles[0]['titulos'][0].pk, primer_titulo.pk)
        self.assertContains(respuesta, 'aria-label="Puesto 1"')
        self.assertContains(respuesta, 'aria-label="Puesto 10"')
        self.assertContains(respuesta, 'id="popular-list-title">Populares</h2>')
        self.assertContains(respuesta, 'class="popular-grid"')
        self.assertNotContains(respuesta, 'class="title-carousel"')
        self.assertNotContains(respuesta, 'data-carousel-target="carousel-track')

    def test_usuario_autenticado_ve_banners_recientes_con_descripcion_y_elenco(self):
        anterior = self.crear_titulo(
            'Estreno anterior',
            self.pelicula,
            con_contenido=True,
        )
        anterior.fecha_estreno = date(2025, 1, 1)
        anterior.save(update_fields=['fecha_estreno'])
        self.agregar_imagen_titulo(
            anterior,
            'Banner anterior',
            'demo/banners/anterior.svg',
        )
        reciente = self.crear_titulo(
            'Estreno reciente',
            self.serie,
            con_contenido=True,
        )
        reciente.descripcion_original = 'Una aventura nueva para probar el carrusel.'
        reciente.fecha_estreno = date(2026, 10, 1)
        reciente.save(update_fields=['descripcion_original', 'fecha_estreno'])
        self.agregar_imagen_titulo(
            reciente,
            'Banner reciente',
            'demo/banners/reciente.svg',
        )
        persona = Elenco.objects.create(
            pais=self.pais,
            nombre='Artista',
            apellido='Demo',
        )
        rol = Rol.objects.create(nombre='Actor')
        rol_elenco = RolElenco.objects.create(rol=rol, elenco=persona)
        TituloRolElenco.objects.create(titulo=reciente, rol_elenco=rol_elenco)
        usuario = Usuario.objects.create_user(
            username='banners@example.com',
            email='banners@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'))

        self.assertEqual(respuesta.status_code, 200)
        banners = respuesta.context['banners']
        self.assertEqual(
            [banner['titulo'].pk for banner in banners],
            [reciente.pk, anterior.pk],
        )
        self.assertEqual(banners[0]['elenco'], ['Artista Demo'])
        self.assertTrue(banners[0]['imagen_url'].endswith('/media/demo/banners/reciente.svg'))
        self.assertContains(respuesta, 'data-featured-banner')
        self.assertContains(respuesta, 'Una aventura nueva para probar el carrusel.')
        self.assertContains(respuesta, 'Artista Demo')

    def test_visitante_con_banners_en_catalogo_sigue_viendo_portada_anterior(self):
        titulo = self.crear_titulo('Banner privado', self.pelicula, con_contenido=True)
        self.agregar_imagen_titulo(
            titulo,
            'Banner privado',
            'demo/banners/privado.svg',
        )

        respuesta = self.client.get(reverse('home'))

        self.assertEqual(respuesta.context['banners'], [])
        self.assertNotContains(respuesta, '<section class="featured-banner"')
        self.assertContains(respuesta, 'picsum.photos/1920/1080')

    def test_banners_son_los_cinco_titulos_con_imagen_mas_recientes_sin_requerir_marca(self):
        for anio in range(2020, 2026):
            titulo = self.crear_titulo(
                f'Estreno {anio}',
                self.pelicula,
                con_contenido=True,
            )
            titulo.fecha_estreno = date(anio, 1, 1)
            titulo.save(update_fields=['fecha_estreno'])
            self.agregar_imagen_titulo(
                titulo,
                f'Imagen {anio}',
                f'demo/banners/estreno-{anio}.svg',
            )

        usuario = Usuario.objects.create_user(
            username='banners-recientes@example.com',
            email='banners-recientes@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'))

        banners = respuesta.context['banners']
        self.assertEqual(
            [banner['titulo'].nombre_original for banner in banners],
            [f'Estreno {anio}' for anio in range(2025, 2020, -1)],
        )
        self.assertEqual(
            [banner['imagen_url'].rsplit('/', 1)[-1] for banner in banners],
            [f'estreno-{anio}.svg' for anio in range(2025, 2020, -1)],
        )

    def test_categoria_terror_muestra_banners_recientes_aunque_no_tengan_imagen(self):
        terror = Categoria.objects.create(nombre='Terror')
        drama = Categoria.objects.create(nombre='Drama')
        anterior = self.crear_titulo(
            'Terror anterior',
            self.pelicula,
            con_contenido=True,
            categoria=terror,
        )
        anterior.fecha_estreno = date(2024, 1, 1)
        anterior.save(update_fields=['fecha_estreno'])
        reciente = self.crear_titulo(
            'Terror reciente',
            self.serie,
            con_contenido=True,
            categoria=terror,
        )
        reciente.fecha_estreno = date(2026, 1, 1)
        reciente.save(update_fields=['fecha_estreno'])
        fuera_de_categoria = self.crear_titulo(
            'Drama reciente',
            self.pelicula,
            con_contenido=True,
            categoria=drama,
        )
        fuera_de_categoria.fecha_estreno = date(2026, 2, 1)
        fuera_de_categoria.save(update_fields=['fecha_estreno'])
        self.agregar_imagen_titulo(
            fuera_de_categoria,
            'Banner Drama',
            'demo/banners/drama.svg',
        )
        usuario = Usuario.objects.create_user(
            username='banners-terror@example.com',
            email='banners-terror@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'), {'categoria': terror.pk})

        self.assertEqual(
            [banner['titulo'].pk for banner in respuesta.context['banners']],
            [reciente.pk, anterior.pk],
        )
        self.assertTrue(all(not banner['imagen_url'] for banner in respuesta.context['banners']))
        self.assertContains(respuesta, 'featured-banner-slide--without-image')
        self.assertContains(respuesta, 'Terror reciente')

    def test_banners_respetan_el_tipo_filtrado_y_muestran_los_cinco_mas_recientes(self):
        for anio in range(2020, 2026):
            for tipo, prefijo in (
                (self.pelicula, 'Película'),
                (self.serie, 'Serie'),
            ):
                titulo = self.crear_titulo(
                    f'{prefijo} {anio}',
                    tipo,
                    con_contenido=True,
                )
                titulo.fecha_estreno = date(anio, 1, 1)
                titulo.save(update_fields=['fecha_estreno'])
                self.agregar_imagen_titulo(
                    titulo,
                    f'Imagen {prefijo} {anio}',
                    f'demo/{prefijo.lower()}-{anio}.svg',
                )

        usuario = Usuario.objects.create_user(
            username='banners-por-tipo@example.com',
            email='banners-por-tipo@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        for filtro, prefijo in (('peliculas', 'Película'), ('series', 'Serie')):
            with self.subTest(filtro=filtro):
                respuesta = self.client.get(reverse('home'), {'tipo': filtro})
                banners = respuesta.context['banners']

                self.assertEqual(len(banners), 5)
                self.assertTrue(all(
                    banner['titulo'].tipo_titulo.nombre == prefijo
                    for banner in banners
                ))
                self.assertEqual(
                    [banner['titulo'].nombre_original for banner in banners],
                    [f'{prefijo} {anio}' for anio in range(2025, 2020, -1)],
                )


class MiListaTests(TestCase):
    def setUp(self):
        self.pais = Pais.objects.create(nombre='Argentina')
        self.tipo_titulo = TipoTitulo.objects.create(nombre='Película')
        self.tipo_perfil = TipoPerfil.objects.create(nombre='Perfil de prueba', edad_max=100)
        self.usuario = Usuario.objects.create_user(
            username='mi-lista@example.com',
            email='mi-lista@example.com',
            password='UnaClave-larga-2026!',
        )

    def crear_perfil(self, usuario, nombre):
        imagen = Imagen.objects.create(
            nombre=f'Imagen {nombre}',
            imagen=f'demo/{nombre}.svg',
        )
        return Perfil.objects.create(
            nombre=nombre,
            imagen=imagen,
            tipo_perfil=self.tipo_perfil,
            usuario=usuario,
        )

    def agregar_a_lista(
        self,
        perfil,
        nombre,
        fecha_agregado,
        fecha_eliminado=None,
        edad_minima=0,
    ):
        titulo = Titulo.objects.create(
            nombre_original=nombre,
            tipo_titulo=self.tipo_titulo,
            pais=self.pais,
            edad_minima=edad_minima,
        )
        perfil_titulo = PerfilTitulo.objects.create(perfil=perfil, titulo=titulo)
        Porver.objects.create(
            perfil_titulo=perfil_titulo,
            fecha_agregado=fecha_agregado,
            fecha_eliminado=fecha_eliminado,
        )
        return titulo

    def nombres_titulos(self, respuesta):
        return [
            porver.perfil_titulo.titulo.nombre_original
            for porver in respuesta.context['titulos_por_ver']
        ]

    def test_lista_muestra_por_ver_activos_solo_del_perfil_seleccionado(self):
        perfil_principal = self.crear_perfil(self.usuario, 'Principal')
        perfil_secundario = self.crear_perfil(self.usuario, 'Secundario')
        otro_usuario = Usuario.objects.create_user(
            username='otro-usuario@example.com',
            email='otro-usuario@example.com',
            password='UnaClave-larga-2026!',
        )
        perfil_ajeno = self.crear_perfil(otro_usuario, 'Ajeno')
        self.agregar_a_lista(perfil_principal, 'Zorro azul', date(2026, 1, 1))
        self.agregar_a_lista(perfil_secundario, 'Alfombra roja', date(2026, 1, 2))
        self.agregar_a_lista(
            perfil_principal,
            'Título eliminado',
            date(2026, 1, 3),
            fecha_eliminado=date(2026, 1, 4),
        )
        self.agregar_a_lista(perfil_ajeno, 'Privado de otra cuenta', date(2025, 1, 1))
        self.client.force_login(self.usuario)
        session = self.client.session
        session['perfil_activo_id'] = perfil_principal.pk
        session.save()

        respuesta = self.client.get(reverse('mi_lista'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            self.nombres_titulos(respuesta),
            ['Zorro azul'],
        )
        self.assertContains(respuesta, 'Más antiguo')
        self.assertContains(respuesta, 'Más reciente')
        self.assertContains(respuesta, 'Orden alfabético')
        self.assertContains(respuesta, 'href="/mi-lista/"')
        self.assertNotContains(respuesta, 'Privado de otra cuenta')

    def test_mi_lista_ofrece_quitar_titulo_sin_recargar(self):
        perfil = self.crear_perfil(self.usuario, 'Principal')
        titulo = self.agregar_a_lista(perfil, 'Título para quitar', date(2026, 1, 1))
        self.client.force_login(self.usuario)
        session = self.client.session
        session['perfil_activo_id'] = perfil.pk
        session.save()

        respuesta_lista = self.client.get(reverse('mi_lista'))
        respuesta_quitar = self.client.post(
            reverse('toggle_mi_lista', args=[titulo.pk]),
            {'next': reverse('mi_lista')},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )
        lista_actualizada = self.client.get(reverse('mi_lista'))

        self.assertContains(respuesta_lista, 'Quitar de Mi Lista: Título para quitar')
        self.assertContains(respuesta_lista, 'data-title-details-open')
        self.assertContains(respuesta_lista, 'bi bi-list')
        self.assertContains(
            respuesta_lista,
            f'data-title-rating-url="{reverse("calificar_titulo", args=[titulo.pk])}"',
        )
        self.assertEqual(respuesta_quitar.status_code, 200)
        self.assertFalse(respuesta_quitar.json()['en_mi_lista'])
        self.assertNotContains(lista_actualizada, 'Título para quitar')
        self.assertContains(lista_actualizada, 'Todavía no hay títulos en la lista de este perfil.')

    def test_lista_oculta_titulos_sobre_la_edad_maxima_del_perfil(self):
        tipo_perfil = TipoPerfil.objects.create(nombre='Adolescente', edad_max=17)
        imagen = Imagen.objects.create(nombre='Avatar edad', imagen='demo/edad.svg')
        perfil = Perfil.objects.create(
            nombre='Adolescente',
            imagen=imagen,
            tipo_perfil=tipo_perfil,
            usuario=self.usuario,
        )
        self.agregar_a_lista(perfil, 'Permitido +17', date(2026, 1, 1), edad_minima=17)
        self.agregar_a_lista(perfil, 'Restringido +18', date(2026, 1, 2), edad_minima=18)
        self.client.force_login(self.usuario)
        session = self.client.session
        session['perfil_activo_id'] = perfil.pk
        session.save()

        respuesta = self.client.get(reverse('mi_lista'))

        self.assertEqual(self.nombres_titulos(respuesta), ['Permitido +17'])

    def test_lista_puede_ordenarse_por_reciente_y_alfabetico(self):
        perfil = self.crear_perfil(self.usuario, 'Principal')
        self.agregar_a_lista(perfil, 'Zorro azul', date(2026, 1, 3))
        self.agregar_a_lista(perfil, 'Alfombra roja', date(2026, 1, 1))
        self.agregar_a_lista(perfil, 'Bruma', date(2026, 1, 2))
        self.client.force_login(self.usuario)
        session = self.client.session
        session['perfil_activo_id'] = perfil.pk
        session.save()

        respuesta_reciente = self.client.get(
            reverse('mi_lista'),
            {'orden': 'reciente'},
        )
        respuesta_alfabetica = self.client.get(
            reverse('mi_lista'),
            {'orden': 'alfabetico'},
        )

        self.assertEqual(
            self.nombres_titulos(respuesta_reciente),
            ['Zorro azul', 'Bruma', 'Alfombra roja'],
        )
        self.assertEqual(
            self.nombres_titulos(respuesta_alfabetica),
            ['Alfombra roja', 'Bruma', 'Zorro azul'],
        )

    def test_lista_muestra_el_nombre_localizado_del_idioma_del_usuario(self):
        ingles = Idioma.objects.create(nombre='Inglés')
        titulo = self.agregar_a_lista(
            self.crear_perfil(self.usuario, 'Principal'),
            'Nombre original',
            date(2026, 1, 1),
        )
        IdiomaTitulo.objects.create(
            titulo=titulo,
            idioma=ingles,
            nombre='Localized title',
            descripcion='Localized description',
        )
        self.usuario.idioma = ingles
        self.usuario.save(update_fields=['idioma'])
        self.client.force_login(self.usuario)
        perfil = Perfil.objects.get(nombre='Principal')
        session = self.client.session
        session['perfil_activo_id'] = perfil.pk
        session.save()

        respuesta = self.client.get(reverse('mi_lista'))

        self.assertContains(respuesta, 'Localized title')
        self.assertNotContains(respuesta, '<h2 class="h6 fw-semibold mb-1">Nombre original</h2>')

    def test_mi_lista_requiere_autenticacion(self):
        respuesta = self.client.get(reverse('mi_lista'))

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse('login'), respuesta.url)

    def test_mi_lista_sin_perfil_activo_lleva_al_selector(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse('mi_lista'))

        self.assertRedirects(
            respuesta,
            reverse('perfiles'),
            fetch_redirect_response=False,
        )


class PerfilesTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username='perfiles@example.com',
            email='perfiles@example.com',
            password='UnaClave-larga-2026!',
        )
        self.client.force_login(self.usuario)

    def crear_perfil(self, usuario, nombre='Perfil', avatar='avatar-azul.svg'):
        tipo_perfil, _ = TipoPerfil.objects.get_or_create(
            nombre='Adulto',
            defaults={'edad_max': 100},
        )
        nombre_avatar = avatar.removeprefix('avatar-').removesuffix('.svg').capitalize()
        imagen = Imagen.objects.get(
            nombre=f'Avatar {nombre_avatar}',
        )
        return Perfil.objects.create(
            nombre=nombre,
            imagen=imagen,
            tipo_perfil=tipo_perfil,
            usuario=usuario,
        )

    def test_crear_primer_perfil_lo_selecciona_y_lleva_a_inicio(self):
        imagen_avatar = Imagen.objects.get(nombre='Avatar Verde')
        tipo_titulo = TipoTitulo.objects.create(nombre='Película')
        pais = Pais.objects.create(nombre='Argentina')
        titulo = Titulo.objects.create(
            nombre_original='Título para calificación inicial',
            tipo_titulo=tipo_titulo,
            pais=pais,
            edad_minima=0,
        )
        respuesta = self.client.post(reverse('crear_perfil'), {
            'nombre': 'Hogar',
            'tipo_perfil': 'infantil',
            'imagen': imagen_avatar.pk,
        })

        perfil = Perfil.objects.get(usuario=self.usuario)
        self.assertRedirects(respuesta, reverse('home'))
        self.assertEqual(perfil.nombre, 'Hogar')
        self.assertEqual(perfil.imagen, imagen_avatar)
        self.assertEqual(perfil.tipo_perfil.nombre, 'Infantil')
        self.assertEqual(perfil.tipo_perfil.edad_max, 12)
        self.assertEqual(self.client.session['perfil_activo_id'], perfil.pk)
        perfil_titulo = PerfilTitulo.objects.get(perfil=perfil, titulo=titulo)
        self.assertEqual(perfil_titulo.calificacion.estrellas, Decimal('2.5'))

    def test_formulario_muestra_solo_avatares_de_la_aplicacion(self):
        respuesta = self.client.get(reverse('crear_perfil'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Adulto (desde 18 años)')
        self.assertContains(respuesta, 'Adolescente (hasta 17 años)')
        self.assertContains(respuesta, 'Infantil (hasta 12 años)')
        self.assertContains(respuesta, '/media/demo/perfiles/avatar-azul.svg')
        self.assertContains(respuesta, '/media/demo/perfiles/avatar-dorado.svg')
        self.assertNotContains(respuesta, 'type="file"')
        self.assertNotContains(respuesta, 'name="avatar"')

    def test_formulario_rechaza_ids_de_imagen_que_no_existen(self):
        respuesta = self.client.post(reverse('crear_perfil'), {
            'nombre': 'Hogar',
            'tipo_perfil': 'adulto',
            'imagen': 999999,
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Perfil.objects.filter(usuario=self.usuario).exists())
        self.assertIn('imagen', respuesta.context['form'].errors)

    def test_selector_muestra_perfiles_y_agregar_mientras_haya_espacio(self):
        perfil = self.crear_perfil(self.usuario, nombre='Principal')

        respuesta = self.client.get(reverse('perfiles'))

        self.assertContains(respuesta, self.usuario.email)
        self.assertContains(respuesta, 'Principal')
        self.assertContains(respuesta, 'Agregar perfil')
        self.assertContains(respuesta, perfil.imagen.imagen.url)
        self.assertContains(respuesta, 'Cerrar sesión')
        self.assertNotContains(respuesta, 'Mi Lista')
        self.assertNotContains(respuesta, 'Cambiar Perfil')
        self.assertNotContains(respuesta, 'Todos los derechos reservados')

    def test_selector_permite_activar_edicion_y_muestra_lapices(self):
        perfil = self.crear_perfil(self.usuario, nombre='Principal')

        respuesta = self.client.get(reverse('perfiles'), {'editar': '1'})

        self.assertContains(respuesta, 'Listo')
        self.assertContains(respuesta, reverse('configurar_perfil', args=[perfil.pk]))
        self.assertContains(respuesta, 'bi-pencil-fill')
        self.assertNotContains(respuesta, 'Editar perfiles')

    def test_configurar_perfil_actualiza_sus_datos(self):
        perfil = self.crear_perfil(self.usuario, nombre='Principal')
        imagen = Imagen.objects.get(nombre='Avatar Verde')

        respuesta = self.client.post(
            reverse('configurar_perfil', args=[perfil.pk]),
            {
                'nombre': 'Familiar',
                'tipo_perfil': 'infantil',
                'imagen': imagen.pk,
            },
        )

        perfil.refresh_from_db()
        self.assertRedirects(respuesta, reverse('perfiles'))
        self.assertEqual(perfil.nombre, 'Familiar')
        self.assertEqual(perfil.tipo_perfil.nombre, 'Infantil')
        self.assertEqual(perfil.imagen, imagen)
        self.assertTrue(perfil.activo)

    def test_desactivar_perfil_lo_oculta_sin_borrar_y_pide_confirmacion(self):
        perfil = self.crear_perfil(self.usuario, nombre='Principal')
        otro_perfil = self.crear_perfil(self.usuario, nombre='Secundario')
        session = self.client.session
        session['perfil_activo_id'] = perfil.pk
        session.save()

        confirmar = self.client.get(reverse('desactivar_perfil', args=[perfil.pk]))
        respuesta = self.client.post(reverse('desactivar_perfil', args=[perfil.pk]))

        perfil.refresh_from_db()
        self.assertContains(confirmar, '¿Borrar este perfil?')
        self.assertRedirects(respuesta, reverse('perfiles'))
        self.assertFalse(perfil.activo)
        self.assertTrue(Perfil.objects.filter(pk=perfil.pk).exists())
        self.assertNotIn('perfil_activo_id', self.client.session)
        self.assertNotContains(self.client.get(reverse('perfiles')), 'Principal')
        self.assertTrue(otro_perfil.activo)

    def test_no_se_puede_desactivar_el_ultimo_perfil_activo(self):
        perfil = self.crear_perfil(self.usuario, nombre='Principal')

        respuesta = self.client.post(reverse('desactivar_perfil', args=[perfil.pk]))

        perfil.refresh_from_db()
        self.assertRedirects(respuesta, reverse('perfiles'))
        self.assertTrue(perfil.activo)
        self.assertContains(self.client.get(reverse('perfiles')), 'Principal')

    def test_context_processor_de_views_expone_el_perfil_activo(self):
        perfil = self.crear_perfil(self.usuario, nombre='Principal')
        session = self.client.session
        session['perfil_activo_id'] = perfil.pk
        session.save()

        respuesta = self.client.get(reverse('perfiles'))

        self.assertEqual(respuesta.context['perfil_activo'], perfil)

    def test_no_se_puede_agregar_un_sexto_perfil(self):
        for indice in range(5):
            self.crear_perfil(self.usuario, nombre=f'Perfil {indice}')

        selector = self.client.get(reverse('perfiles'))
        crear = self.client.get(reverse('crear_perfil'))

        self.assertNotContains(selector, 'Agregar perfil')
        self.assertRedirects(crear, reverse('perfiles'))
        self.assertEqual(Perfil.objects.filter(usuario=self.usuario).count(), 5)

    def test_selector_no_permite_elegir_perfil_de_otra_cuenta(self):
        self.crear_perfil(self.usuario, nombre='Propio')
        perfil_ajeno = self.crear_perfil(
            Usuario.objects.create_user(
                username='ajeno@example.com',
                email='ajeno@example.com',
                password='UnaClave-larga-2026!',
            ),
            nombre='Ajeno',
        )

        respuesta = self.client.post(reverse('perfiles'), {
            'perfil_id': perfil_ajeno.pk,
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('perfil_activo_id', self.client.session)
        self.assertNotContains(respuesta, 'Ajeno')

    def test_login_con_perfiles_lleva_al_selector(self):
        self.crear_perfil(self.usuario, nombre='Principal')
        self.client.logout()

        respuesta = self.client.post(reverse('login'), {
            'email': self.usuario.email,
            'password': 'UnaClave-larga-2026!',
        })

        self.assertRedirects(respuesta, reverse('perfiles'))


class CargarDatosDemoTests(TestCase):
    def test_carga_categorias_completas_y_es_idempotente(self):
        Categoria.objects.create(nombre='Drama')

        call_command('cargar_datos_demo', stdout=StringIO())

        self.assertTrue(Categoria.objects.get(nombre='Drama').descripcion)
        self.assertFalse(Categoria.objects.filter(nombre__in=['ATP', '+7', '+10', '+13', '+16']).exists())
        self.assertTrue(Contenido.objects.filter(duracion_segundos__gt=0).exists())
        self.assertEqual(Titulo.objects.get(nombre_original='La ruta de prueba').edad_minima, 0)
        self.assertEqual(Titulo.objects.get(nombre_original='Misterios de muestra').edad_minima, 13)
        self.assertEqual(Titulo.objects.get(nombre_original='Noche sin retorno').edad_minima, 18)
        self.assertEqual(Titulo.objects.get(nombre_original='Habitación 404').edad_minima, 18)
        ruta_demo = Titulo.objects.get(nombre_original='La ruta de prueba')
        self.assertEqual(
            IdiomaTitulo.objects.get(titulo=ruta_demo, idioma__nombre='Español').nombre,
            ruta_demo.nombre_original,
        )
        self.assertTrue(Imagen.objects.filter(nombre='Avatar Dorado').exists())
        self.assertTrue(
            IdiomaTitulo.objects.filter(imagen__startswith='demo/banners/').exists()
        )

        conteos_primera_carga = {
            modelo: modelo.objects.count()
            for modelo in (Categoria, Contenido, Imagen, Titulo, Suscripcion)
        }
        call_command('cargar_datos_demo', stdout=StringIO())
        conteos_segunda_carga = {
            modelo: modelo.objects.count()
            for modelo in (Categoria, Contenido, Imagen, Titulo, Suscripcion)
        }

        self.assertEqual(conteos_segunda_carga, conteos_primera_carga)
