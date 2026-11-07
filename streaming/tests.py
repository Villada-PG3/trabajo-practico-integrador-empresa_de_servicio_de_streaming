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
    Pais,
    Perfil,
    PerfilContenido,
    Plan,
    Precio,
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

    def test_registro_crea_usuario_y_redirige_a_planes(self):
        response = self.client.post(reverse('registro'), self.datos_usuario())

        self.assertRedirects(response, reverse('seleccionar_plan'))
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

        self.assertRedirects(response, reverse('seleccionar_plan'))
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

    def test_inicio_de_sesion_autentica_y_usa_la_suscripcion(self):
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

        self.assertRedirects(response, reverse('home'))
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)

    def test_inicio_de_sesion_sin_plan_redirige_a_seleccion(self):
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

        self.assertRedirects(response, reverse('seleccionar_plan'))

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
        self.pelicula = TipoTitulo.objects.create(nombre='Película')
        self.serie = TipoTitulo.objects.create(nombre='Serie')
        self.accion = Categoria.objects.create(nombre='Acción')

    def crear_titulo(self, nombre, tipo, con_contenido, categoria=None):
        titulo = Titulo.objects.create(
            nombre_original=nombre,
            tipo_titulo=tipo,
            pais=self.pais,
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

    def test_home_separa_carouseles_y_omite_titulos_sin_contenido(self):
        pelicula = self.crear_titulo(
            'Película de acción',
            self.pelicula,
            con_contenido=True,
            categoria=self.accion,
        )
        Imagen.objects.create(
            nombre='Póster de prueba',
            imagen='demo/posters/pelicula.svg',
            titulo=pelicula,
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
        self.client.force_login(usuario)

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

    def test_carouseles_limitan_a_treinta_titulos_por_categoria(self):
        usuario = Usuario.objects.create_user(
            username='limite@example.com',
            email='limite@example.com',
            password='UnaClave-larga-2026!',
        )
        self.client.force_login(usuario)
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

    def test_categoria_del_carrusel_va_primero_y_restantes_alfabeticamente(self):
        misterio = Categoria.objects.create(nombre='Misterio')
        aventura = Categoria.objects.create(nombre='Aventura')
        suspenso = Categoria.objects.create(nombre='Suspenso')
        edad = Categoria.objects.create(nombre='+13', es_edad=True)
        categoria_mas_siete = Categoria.objects.create(nombre='+7')
        titulo = self.crear_titulo(
            'Misterio entre montañas',
            self.pelicula,
            con_contenido=True,
        )
        for categoria in (suspenso, misterio, edad, aventura, categoria_mas_siete):
            TituloCategoria.objects.create(titulo=titulo, categoria=categoria)
        usuario = Usuario.objects.create_user(
            username='categorias@example.com',
            email='categorias@example.com',
            password='UnaClave-larga-2026!',
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse('home'))

        carruseles = {
            carrusel['etiqueta']: carrusel['titulos']
            for carrusel in respuesta.context['carruseles']
        }
        self.assertEqual(
            [categoria.nombre for categoria in carruseles['Misterio'][0].categorias_ordenadas],
            ['Misterio', '+7', 'Aventura', 'Suspenso'],
        )
        self.assertEqual(carruseles['Misterio'][0].clasificacion_edad.nombre, '+13')
        self.assertEqual(
            [categoria.nombre for categoria in carruseles['Películas'][0].categorias_ordenadas],
            ['+7', 'Aventura', 'Misterio', 'Suspenso'],
        )
        self.assertEqual(carruseles['Películas'][0].clasificacion_edad.nombre, '+13')
        self.assertNotIn('+13', carruseles)
        self.assertEqual([titulo.pk for titulo in carruseles['+7']], [titulo.pk])
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
        self.client.force_login(usuario)

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
            titulo=mas_visto,
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
                titulo=titulo,
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
        Imagen.objects.create(
            nombre='Banner anterior',
            imagen='demo/banners/anterior.svg',
            es_banner=True,
            titulo=anterior,
        )
        reciente = self.crear_titulo(
            'Estreno reciente',
            self.serie,
            con_contenido=True,
        )
        reciente.descripcion_original = 'Una aventura nueva para probar el carrusel.'
        reciente.fecha_estreno = date(2026, 10, 1)
        reciente.save(update_fields=['descripcion_original', 'fecha_estreno'])
        Imagen.objects.create(
            nombre='Banner reciente',
            imagen='demo/banners/reciente.svg',
            es_banner=True,
            titulo=reciente,
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
        self.client.force_login(usuario)

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
        Imagen.objects.create(
            nombre='Banner privado',
            imagen='demo/banners/privado.svg',
            es_banner=True,
            titulo=titulo,
        )

        respuesta = self.client.get(reverse('home'))

        self.assertEqual(respuesta.context['banners'], [])
        self.assertNotContains(respuesta, '<section class="featured-banner"')
        self.assertContains(respuesta, 'picsum.photos/1920/1080')


class CargarDatosDemoTests(TestCase):
    def test_carga_categorias_completas_y_es_idempotente(self):
        Categoria.objects.create(nombre='+7', es_edad=False)
        Categoria.objects.create(nombre='Drama', es_edad=True)

        call_command('cargar_datos_demo', stdout=StringIO())

        self.assertTrue(Categoria.objects.get(nombre='+7').es_edad)
        self.assertFalse(Categoria.objects.get(nombre='Drama').es_edad)
        self.assertTrue(Categoria.objects.get(nombre='ATP').es_edad)
        self.assertFalse(Categoria.objects.get(nombre='Acción').es_edad)
        self.assertTrue(Categoria.objects.get(nombre='Drama').descripcion)
        self.assertTrue(Contenido.objects.filter(duracion_segundos__gt=0).exists())
        self.assertTrue(Imagen.objects.filter(es_banner=True).exists())
        self.assertTrue(Imagen.objects.filter(es_banner=False).exists())

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
