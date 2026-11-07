from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Categoria,
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

    def test_reporte_muestra_error_para_rango_invertido(self):
        response = self.client.get(reverse('reporte_ventas'), {
            'fecha_inicio': '2026-10-20',
            'fecha_fin': '2026-10-19',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'La fecha inicial no puede ser posterior a la fecha final.')
        self.assertEqual(response.context['data_miembros_json'], [])


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
        self.assertContains(response, 'src="/media/demo/posters/pelicula.svg"')
        self.assertEqual(
            [titulo.pk for titulo in carruseles['Series']],
            [serie.pk],
        )
        self.assertEqual(
            [titulo.pk for titulo in carruseles['Acción']],
            [pelicula.pk],
        )
        for titulos in carruseles.values():
            self.assertNotIn(sin_contenido.pk, [titulo.pk for titulo in titulos])
            self.assertTrue(all(titulo.contenidos.exists() for titulo in titulos))

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
        self.assertIn('Series', etiquetas_series)
        self.assertIn('Misterio', etiquetas_series)
        self.assertNotIn('Películas', etiquetas_series)
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
        self.assertIn('Películas', etiquetas_peliculas)
        self.assertIn('Acción', etiquetas_peliculas)
        self.assertNotIn('Series', etiquetas_peliculas)
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

        self.assertContains(respuesta_home, f'Agregar a Mi Lista: {titulo.nombre_original}')
        self.assertEqual(respuesta_agregar.status_code, 302)
        self.assertEqual(respuesta_agregar.url, '/?tipo=peliculas')
        self.assertContains(respuesta_guardado, f'Quitar de Mi Lista: {titulo.nombre_original}')
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

        self.assertEqual(carrusel_popular['etiqueta'], 'Más reproducidos')
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
        self.assertEqual(carruseles[0]['etiqueta'], 'Más reproducidos')
        self.assertTrue(carruseles[0]['mostrar_top'])
        self.assertEqual(len(carruseles[0]['titulos']), 10)
        self.assertEqual(carruseles[0]['titulos'][0].pk, primer_titulo.pk)
        self.assertContains(respuesta, 'aria-label="Puesto 1"')
        self.assertContains(respuesta, 'aria-label="Puesto 10"')
        self.assertNotContains(respuesta, 'id="carousel-title-2"')

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
