from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Idioma, Pais, Plan, Precio, Suscripcion, Usuario


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
