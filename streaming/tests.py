from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from .billing import (
    fecha_inicio_suscripcion,
    procesar_cobros_demo,
    suscripcion_activa,
)
from .forms import TarjetaDemoPlanForm
from .models import (
    Categoria,
    Calificacion,
    CambioPlan,
    Calidad,
    CalidadIdiomaContenido,
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
    PlanCalidad,
    Precio,
    Porver,
    Registro,
    MarcaTarjeta,
    MetodoPago,
    Tarjeta,
    EstadoCobro,
    Cobro,
    Rol,
    RolElenco,
    Suscripcion,
    Subtitulo,
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
        self.plan = Plan.objects.create(
            nombre='Plan de registro',
            cantidad_pantallas_simultaneas=1,
        )
        Precio.objects.create(
            plan=self.plan,
            precio=10,
            fecha_inicio=timezone.localdate(),
        )
        self.marca = MarcaTarjeta.objects.get(nombre='Visa')
        self.metodo = MetodoPago.objects.get(nombre='Crédito')

    def datos_usuario(self, email='persona@example.com', password='UnaClave-larga-2026!'):
        return {
            'username': 'persona-usuario',
            'email': email,
            'password': password,
            'pais': self.pais.pk,
            'idioma': self.idioma.pk,
        }

    def test_archivo_de_calidad_idioma_contenido_acepta_mp4_y_rechaza_otras_extensiones(self):
        campo_archivo = CalidadIdiomaContenido._meta.get_field('archivo')

        archivo_mp4 = SimpleUploadedFile(
            'episodio.mp4',
            b'contenido de video de prueba',
            content_type='video/mp4',
        )
        self.assertEqual(
            campo_archivo.clean(archivo_mp4, None).name,
            'episodio.mp4',
        )

        archivo_avi = SimpleUploadedFile(
            'episodio.avi',
            b'contenido de video de prueba',
            content_type='video/x-msvideo',
        )
        with self.assertRaises(ValidationError):
            campo_archivo.clean(archivo_avi, None)

    def test_formulario_de_tarjeta_valida_luhn_y_no_ofrece_efectivo(self):
        tarjeta_valida = TarjetaDemoPlanForm({
            'nombre_titular': 'USUARIO DE PRUEBA',
            'numero_tarjeta': '4111 1111 1111 1111',
            'cvv': '123',
            'marca_tarjeta': MarcaTarjeta.objects.get(nombre='Visa').pk,
            'metodo_pago': MetodoPago.objects.get(nombre='Crédito').pk,
        })
        self.assertTrue(tarjeta_valida.is_valid(), tarjeta_valida.errors)
        self.assertEqual(
            tarjeta_valida.cleaned_data['numero_tarjeta'],
            '4111111111111111',
        )

        tarjeta_invalida = TarjetaDemoPlanForm({
            'nombre_titular': 'USUARIO DE PRUEBA',
            'numero_tarjeta': '4111 1111 1111 1112',
            'cvv': '123',
            'marca_tarjeta': MarcaTarjeta.objects.get(nombre='Visa').pk,
            'metodo_pago': MetodoPago.objects.get(nombre='Crédito').pk,
        })
        self.assertFalse(tarjeta_invalida.is_valid())
        self.assertIn('Luhn', str(tarjeta_invalida.errors))

        MetodoPago.objects.create(nombre='Efectivo')
        formulario_vista = TarjetaDemoPlanForm()
        metodos_disponibles = set(
            formulario_vista.fields['metodo_pago'].queryset.values_list(
                'nombre',
                flat=True,
            )
        )
        self.assertEqual(metodos_disponibles, {'Débito', 'Crédito'})

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

    def test_registro_usuario_planes_y_tarjeta_completan_el_alta(self):
        response = self.client.post(reverse('registro'), self.datos_usuario())

        self.assertRedirects(response, reverse('seleccionar_plan'))
        usuario = Usuario.objects.get(username='persona-usuario')
        self.assertEqual(usuario.email, 'persona@example.com')
        self.assertEqual(usuario.pais, self.pais)
        self.assertEqual(usuario.idioma, self.idioma)
        self.assertTrue(usuario.check_password('UnaClave-larga-2026!'))
        self.assertTrue('_auth_user_id' in self.client.session)
        self.assertFalse(Suscripcion.objects.filter(usuario=usuario).exists())

        respuesta_planes = self.client.get(reverse('seleccionar_plan'))
        self.assertEqual(respuesta_planes.status_code, 200)
        self.assertContains(respuesta_planes, 'Plan de registro')
        respuesta_seleccion = self.client.post(
            reverse('seleccionar_plan'),
            {'plan': self.plan.pk},
        )
        self.assertRedirects(
            respuesta_seleccion,
            reverse('pagar_suscripcion', args=[self.plan.pk]),
        )
        respuesta_pago = self.client.post(
            reverse('pagar_suscripcion', args=[self.plan.pk]),
            {
                'nombre_titular': 'USUARIO DE PRUEBA',
                'numero_tarjeta': '4111111111111111',
                'cvv': '123',
                'marca_tarjeta': self.marca.pk,
                'metodo_pago': self.metodo.pk,
            },
        )
        self.assertRedirects(respuesta_pago, reverse('crear_perfil'))

        suscripcion = Suscripcion.objects.get(usuario=usuario)
        hoy = timezone.localdate()
        self.assertEqual(suscripcion.plan, self.plan)
        self.assertEqual(suscripcion.fecha_inscripcion, hoy)
        self.assertEqual(suscripcion.fecha_vigencia, hoy)
        self.assertEqual(suscripcion.tarjeta.numero, '1111')
        cobro = Cobro.objects.get(suscripcion=suscripcion)
        self.assertEqual(cobro.fecha_cobro, hoy)
        self.assertEqual(cobro.estado_cobro.nombre, 'Por aprobar')
        self.assertEqual(cobro.tarjeta, suscripcion.tarjeta)

    def test_registro_permite_omitir_pais_e_idioma(self):
        datos = self.datos_usuario('sin-preferencias@example.com')
        datos.pop('pais')
        datos.pop('idioma')
        datos['username'] = 'sin-preferencias'
        response = self.client.post(reverse('registro'), datos)

        self.assertRedirects(response, reverse('seleccionar_plan'))
        usuario = Usuario.objects.get(username='sin-preferencias')
        self.assertIsNone(usuario.pais)
        self.assertIsNone(usuario.idioma)

    def test_registro_pide_datos_de_usuario_antes_de_seleccionar_plan(self):
        response = self.client.post(reverse('registro'), {
            'email': 'incompleto@example.com',
            'password': 'UnaClave-larga-2026!',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nombre de usuario')
        self.assertNotContains(response, 'Número de tarjeta de prueba')
        self.assertContains(response, 'Continuar a planes')
        self.assertEqual(
            Usuario.objects.filter(email='incompleto@example.com').count(),
            0,
        )

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

        self.assertRedirects(
            response,
            reverse('pagar_suscripcion', args=[plan.pk]),
        )
        response = self.client.post(
            reverse('pagar_suscripcion', args=[plan.pk]),
            {
                'nombre_titular': 'USUARIO DE PRUEBA',
                'numero_tarjeta': '4111 1111 1111 1111',
                'cvv': '123',
                'marca_tarjeta': MarcaTarjeta.objects.get(nombre='Visa').pk,
                'metodo_pago': MetodoPago.objects.get(nombre='Crédito').pk,
            },
        )
        self.assertRedirects(response, reverse('crear_perfil'))
        suscripcion = Suscripcion.objects.get(usuario=usuario)
        self.assertEqual(suscripcion.plan, plan)
        self.assertEqual(suscripcion.fecha_inscripcion, timezone.localdate())
        self.assertEqual(suscripcion.tarjeta.numero, '1111')
        self.assertEqual(suscripcion.tarjeta.marca_tarjeta.nombre, 'Visa')
        self.assertEqual(suscripcion.tarjeta.metodo_pago.nombre, 'Crédito')
        self.assertFalse(hasattr(suscripcion.tarjeta, 'cvv'))
        cobro = Cobro.objects.get(suscripcion=suscripcion)
        self.assertEqual(cobro.tarjeta, suscripcion.tarjeta)
        self.assertEqual(cobro.estado_cobro.nombre, 'Por aprobar')

    @override_settings(DEBUG=True)
    def test_nueva_suscripcion_al_plan_basico_tiene_primer_mes_gratis(self):
        usuario = Usuario.objects.create_user(
            username='nuevo-basico@example.com',
            email='nuevo-basico@example.com',
            password='UnaClave-larga-2026!',
        )
        plan = Plan.objects.create(
            nombre='Básico',
            cantidad_pantallas_simultaneas=1,
        )
        precio = Precio.objects.create(
            plan=plan,
            precio=3500,
            fecha_inicio=timezone.localdate(),
        )
        self.client.force_login(usuario)

        respuesta_planes = self.client.get(reverse('seleccionar_plan'))
        self.assertContains(
            respuesta_planes,
            'Gratis el primer mes, luego a $3500.00 por mes',
        )
        respuesta_pago = self.client.get(
            reverse('pagar_suscripcion', args=[plan.pk]),
        )
        self.assertContains(respuesta_pago, 'Monto del primer cobro')
        self.assertContains(respuesta_pago, '$0.00')
        self.assertContains(respuesta_pago, '$3500.00 por mes')

        respuesta_confirmacion = self.client.post(
            reverse('pagar_suscripcion', args=[plan.pk]),
            {
                'nombre_titular': 'USUARIO DE PRUEBA',
                'numero_tarjeta': '4111111111111111',
                'cvv': '123',
                'marca_tarjeta': self.marca.pk,
                'metodo_pago': self.metodo.pk,
            },
        )

        self.assertRedirects(respuesta_confirmacion, reverse('crear_perfil'))
        primer_cobro = Cobro.objects.get(
            suscripcion__usuario=usuario,
        )
        self.assertEqual(primer_cobro.monto, 0)

        procesar_cobros_demo(
            ahora=timezone.now() + timedelta(days=31, seconds=10),
        )
        cobro_siguiente = Cobro.objects.get(
            suscripcion=primer_cobro.suscripcion,
            fecha_cobro__gt=primer_cobro.fecha_cobro,
        )
        self.assertEqual(cobro_siguiente.monto, precio.precio)

    def test_cuenta_con_suscripcion_anterior_no_recibe_promocion_basica(self):
        usuario = Usuario.objects.create_user(
            username='recurrente@example.com',
            email='recurrente@example.com',
            password='UnaClave-larga-2026!',
        )
        Suscripcion.objects.create(
            usuario=usuario,
            plan=self.plan,
            fecha_inscripcion=timezone.localdate() - timedelta(days=60),
            fecha_vigencia=timezone.localdate() - timedelta(days=30),
            habilitado=False,
        )
        plan = Plan.objects.create(
            nombre='Plan Demo Basico',
            cantidad_pantallas_simultaneas=1,
        )
        precio = Precio.objects.create(
            plan=plan,
            precio=3500,
            fecha_inicio=timezone.localdate(),
        )
        self.client.force_login(usuario)

        respuesta_planes = self.client.get(reverse('seleccionar_plan'))
        self.assertNotContains(respuesta_planes, 'Gratis el primer mes')
        respuesta_pago = self.client.get(
            reverse('pagar_suscripcion', args=[plan.pk]),
        )
        self.assertNotContains(respuesta_pago, 'Promoción de bienvenida')

        respuesta_confirmacion = self.client.post(
            reverse('pagar_suscripcion', args=[plan.pk]),
            {
                'nombre_titular': 'USUARIO DE PRUEBA',
                'numero_tarjeta': '4111111111111111',
                'cvv': '123',
                'marca_tarjeta': self.marca.pk,
                'metodo_pago': self.metodo.pk,
            },
        )

        self.assertRedirects(respuesta_confirmacion, reverse('crear_perfil'))
        cobro = Cobro.objects.get(suscripcion__usuario=usuario)
        self.assertEqual(cobro.monto, precio.precio)


class CuentaTests(TestCase):
    def setUp(self):
        self.pais = Pais.objects.create(nombre='Argentina')
        self.otro_pais = Pais.objects.create(nombre='Chile')
        self.idioma = Idioma.objects.create(nombre='Español')
        self.otro_idioma = Idioma.objects.create(nombre='English')
        self.usuario = Usuario.objects.create_user(
            username='cuenta@example.com',
            email='cuenta@example.com',
            password='Clave-Segura-2026!',
            pais=self.pais,
            idioma=self.idioma,
        )
        self.client.force_login(self.usuario)

    def crear_suscripcion_con_limite(self, limite):
        plan = Plan.objects.create(
            nombre=f'Plan de {limite} dispositivos',
            cantidad_pantallas_simultaneas=limite,
        )
        return Suscripcion.objects.create(
            usuario=self.usuario,
            plan=plan,
            fecha_inscripcion=timezone.localdate(),
            fecha_vigencia=timezone.localdate(),
        )

    def test_bloquea_el_dispositivo_siguiente_al_limite_del_plan(self):
        self.crear_suscripcion_con_limite(2)
        self.assertEqual(self.client.get(reverse('cuenta')).status_code, 200)

        segundo_dispositivo = Client()
        segundo_dispositivo.force_login(self.usuario)
        self.assertEqual(
            segundo_dispositivo.get(reverse('cuenta')).status_code,
            200,
        )

        tercer_dispositivo = Client()
        tercer_dispositivo.force_login(self.usuario)
        respuesta_bloqueo = tercer_dispositivo.get(reverse('cuenta'))
        self.assertRedirects(
            respuesta_bloqueo,
            reverse('dispositivos_bloqueados'),
            fetch_redirect_response=False,
        )
        pagina_bloqueo = tercer_dispositivo.get(
            reverse('dispositivos_bloqueados'),
        )
        self.assertEqual(pagina_bloqueo.status_code, 200)
        self.assertContains(pagina_bloqueo, 'El cupo de dispositivos está lleno')
        self.assertFalse(Registro.objects.filter(
            usuario=self.usuario,
            token_disp=tercer_dispositivo.session.session_key,
        ).exists())

        ultima_actividad = timezone.localtime() - timedelta(minutes=2)
        Registro.objects.filter(usuario=self.usuario).update(
            ultima_conexion_fecha=ultima_actividad.date(),
            ultima_conexion_hora=ultima_actividad.time().replace(tzinfo=None),
        )
        respuesta_reintento = tercer_dispositivo.get(reverse('cuenta'))
        self.assertEqual(respuesta_reintento.status_code, 200)
        self.assertTrue(Registro.objects.filter(
            usuario=self.usuario,
            token_disp=tercer_dispositivo.session.session_key,
            estado=True,
        ).exists())

    def test_login_con_cupo_lleno_deja_el_dispositivo_nuevo_en_bloqueo(self):
        self.crear_suscripcion_con_limite(1)
        self.assertEqual(self.client.get(reverse('cuenta')).status_code, 200)
        perfil = Perfil.objects.create(
            nombre='Perfil principal',
            imagen=Imagen.objects.first(),
            tipo_perfil=TipoPerfil.objects.create(
                nombre='Perfil dispositivo lleno',
                edad_max=100,
            ),
            usuario=self.usuario,
        )

        nuevo_dispositivo = Client()
        respuesta_login = nuevo_dispositivo.post(reverse('login'), {
            'email': self.usuario.email,
            'password': 'Clave-Segura-2026!',
        })
        self.assertRedirects(
            respuesta_login,
            reverse('perfiles'),
            fetch_redirect_response=False,
        )
        registro_nuevo = Registro.objects.get(
            usuario=self.usuario,
            token_disp=nuevo_dispositivo.session.session_key,
        )
        self.assertFalse(registro_nuevo.estado)

        respuesta = nuevo_dispositivo.get(reverse('perfiles'))
        self.assertRedirects(
            respuesta,
            reverse('dispositivos_bloqueados'),
            fetch_redirect_response=False,
        )
        pagina_bloqueo = nuevo_dispositivo.get(reverse('dispositivos_bloqueados'))
        self.assertEqual(pagina_bloqueo.status_code, 200)
        self.assertContains(
            pagina_bloqueo,
            f'class="navbar-brand-logo me-4" href="{reverse("perfiles")}"',
        )
        navbar = str(pagina_bloqueo.content).split('<nav', 1)[1].split('</nav>', 1)[0]
        self.assertNotIn('id="navbarContent"', navbar)
        self.assertNotIn(reverse('cuenta'), navbar)
        self.assertNotIn('>Inicio</a>', navbar)
        self.assertNotIn('data-title-search-open', navbar)
        self.assertContains(
            pagina_bloqueo,
            f'class="btn btn-netflix" href="{reverse("perfiles")}">Intentar nuevamente</a>',
        )

        ultima_actividad = timezone.localtime() - timedelta(minutes=2)
        Registro.objects.filter(
            usuario=self.usuario,
            token_disp=self.client.session.session_key,
        ).update(
            ultima_conexion_fecha=ultima_actividad.date(),
            ultima_conexion_hora=ultima_actividad.time().replace(tzinfo=None),
        )
        respuesta_reintento = nuevo_dispositivo.get(reverse('perfiles'))
        self.assertEqual(respuesta_reintento.status_code, 200)
        self.assertContains(respuesta_reintento, '¿Quién está viendo?')

        ultima_actividad = timezone.localtime() - timedelta(minutes=2)
        Registro.objects.filter(usuario=self.usuario).update(
            ultima_conexion_fecha=ultima_actividad.date(),
            ultima_conexion_hora=ultima_actividad.time().replace(tzinfo=None),
        )
        respuesta_reintento = nuevo_dispositivo.get(reverse('perfiles'))
        self.assertEqual(respuesta_reintento.status_code, 200)
        self.assertContains(respuesta_reintento, '¿Quién está viendo?')
        self.assertContains(respuesta_reintento, perfil.nombre)
        registro_nuevo.refresh_from_db()
        self.assertTrue(registro_nuevo.estado)

    def test_heartbeat_actualiza_ultima_conexion_del_dispositivo(self):
        self.crear_suscripcion_con_limite(1)
        self.assertEqual(self.client.get(reverse('cuenta')).status_code, 200)
        registro = Registro.objects.get(
            usuario=self.usuario,
            token_disp=self.client.session.session_key,
        )
        marca_anterior = (
            registro.ultima_conexion_fecha,
            registro.ultima_conexion_hora,
        )

        respuesta = self.client.post(reverse('heartbeat_dispositivo'))

        self.assertEqual(respuesta.status_code, 204)
        registro.refresh_from_db()
        marca_actual = (
            registro.ultima_conexion_fecha,
            registro.ultima_conexion_hora,
        )
        self.assertGreaterEqual(marca_actual, marca_anterior)
        self.assertContains(
            self.client.get(reverse('cuenta')),
            reverse('heartbeat_dispositivo'),
        )

    def test_pagina_cuenta_requiere_autenticacion_y_muestra_campos(self):
        self.client.logout()
        respuesta_sin_sesion = self.client.get(reverse('cuenta'))

        self.assertRedirects(
            respuesta_sin_sesion,
            f'{reverse("login")}?next={reverse("cuenta")}',
        )

        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse('cuenta'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Cuenta')
        self.assertContains(respuesta, 'Nombre de usuario')
        self.assertContains(respuesta, 'Correo electrónico')
        self.assertContains(respuesta, 'Perfiles activos')
        self.assertContains(respuesta, 'Sesiones abiertas')
        self.assertContains(respuesta, '••••••••')
        self.assertContains(respuesta, 'No asignado')
        self.assertContains(respuesta, 'Guardar preferencias')
        self.assertNotContains(respuesta, 'name="current_password"')
        self.assertContains(respuesta, '.account-layout .form-select option')
        self.assertContains(respuesta, 'href="/cuenta/"')
        self.assertContains(respuesta, 'Cerrar todas')
        self.assertTrue(Registro.objects.filter(
            usuario=self.usuario,
            token_disp=self.client.session.session_key,
            estado=True,
        ).exists())

    def test_cerrar_todas_las_sesiones_conserva_la_actual(self):
        self.client.get(reverse('cuenta'))
        sesion_actual = self.client.session.session_key
        otro_cliente = Client()
        respuesta_login = otro_cliente.post(reverse('login'), {
            'email': self.usuario.email,
            'password': 'Clave-Segura-2026!',
        })
        self.assertRedirects(respuesta_login, reverse('crear_perfil'))
        otra_sesion = otro_cliente.session.session_key
        self.assertNotEqual(sesion_actual, otra_sesion)
        self.assertTrue(Session.objects.filter(session_key=otra_sesion).exists())

        respuesta = self.client.post(reverse('cerrar_otras_sesiones'))

        self.assertRedirects(respuesta, f'{reverse("cuenta")}?seccion=usuario')
        self.assertTrue(Session.objects.filter(session_key=sesion_actual).exists())
        self.assertFalse(Session.objects.filter(session_key=otra_sesion).exists())
        self.assertTrue(Registro.objects.get(
            usuario=self.usuario,
            token_disp=sesion_actual,
        ).estado)
        self.assertFalse(Registro.objects.get(
            usuario=self.usuario,
            token_disp=otra_sesion,
        ).estado)
        respuesta_cuenta = self.client.get(reverse('cuenta'))
        self.assertEqual(respuesta_cuenta.status_code, 200)
        self.assertEqual(respuesta_cuenta.context['sesiones_abiertas'], 1)
        self.assertRedirects(
            otro_cliente.get(reverse('cuenta')),
            f'{reverse("login")}?next={reverse("cuenta")}',
        )

    def test_logout_cierra_el_registro_de_la_sesion_actual(self):
        self.client.get(reverse('cuenta'))
        session_key = self.client.session.session_key

        respuesta = self.client.post(reverse('logout'))

        self.assertRedirects(respuesta, reverse('home'))
        self.assertFalse(Registro.objects.get(
            usuario=self.usuario,
            token_disp=session_key,
        ).estado)

    def test_cerrar_sesiones_rechaza_metodo_get(self):
        respuesta = self.client.get(reverse('cerrar_otras_sesiones'))

        self.assertEqual(respuesta.status_code, 405)

    def test_preferencias_de_cuenta_se_actualizan_desde_la_pestana_usuario(self):
        respuesta = self.client.post(
            reverse('cuenta'),
            {
                'pais': self.otro_pais.pk,
                'idioma': self.otro_idioma.pk,
            },
        )

        self.assertRedirects(respuesta, f'{reverse("cuenta")}?seccion=usuario')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.pais, self.otro_pais)
        self.assertEqual(self.usuario.idioma, self.otro_idioma)

    def test_editar_dato_no_se_guarda_con_contrasena_incorrecta(self):
        respuesta = self.client.post(
            reverse('editar_dato_cuenta', args=['username']),
            {
                'username': 'usuario-no-autorizado',
                'current_password': 'incorrecta',
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'La contraseña vigente no es correcta.')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.username, 'cuenta@example.com')

    def test_editar_username_independiente_y_login_por_correo(self):
        respuesta = self.client.post(
            reverse('editar_dato_cuenta', args=['username']),
            {
                'username': 'usuario-publico',
                'current_password': 'Clave-Segura-2026!',
            },
        )

        self.assertRedirects(respuesta, f'{reverse("cuenta")}?seccion=usuario')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.username, 'usuario-publico')
        self.client.logout()
        respuesta_login = self.client.post(reverse('login'), {
            'email': 'cuenta@example.com',
            'password': 'Clave-Segura-2026!',
        })
        self.assertRedirects(respuesta_login, reverse('crear_perfil'))
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_correo_no_se_puede_cambiar_por_uno_ya_asignado(self):
        Usuario.objects.create_user(
            username='ocupado@example.com',
            email='ocupado@example.com',
            password='Clave-Segura-2026!',
        )

        respuesta = self.client.post(
            reverse('editar_dato_cuenta', args=['email']),
            {
                'email': 'OCUPADO@example.com',
                'current_password': 'Clave-Segura-2026!',
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Ese correo ya está asociado a una cuenta.')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.email, 'cuenta@example.com')

    def test_cambiar_correo_permite_iniciar_sesion_con_nuevo_correo(self):
        respuesta = self.client.post(
            reverse('editar_dato_cuenta', args=['email']),
            {
                'email': 'nuevo@example.com',
                'current_password': 'Clave-Segura-2026!',
            },
        )

        self.assertRedirects(respuesta, f'{reverse("cuenta")}?seccion=usuario')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.email, 'nuevo@example.com')
        self.assertEqual(self.usuario.username, 'cuenta@example.com')
        self.client.logout()

        respuesta_login = self.client.post(reverse('login'), {
            'email': 'nuevo@example.com',
            'password': 'Clave-Segura-2026!',
        })

        self.assertRedirects(respuesta_login, reverse('crear_perfil'))
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_cuenta_muestra_suscripcion_mas_reciente_y_sus_calidades(self):
        plan_anterior = Plan.objects.create(
            nombre='Plan anterior',
            cantidad_pantallas_simultaneas=1,
        )
        plan_actual = Plan.objects.create(
            nombre='Plan actual',
            cantidad_pantallas_simultaneas=2,
        )
        Suscripcion.objects.create(
            usuario=self.usuario,
            plan=plan_anterior,
            fecha_inscripcion=date(2025, 1, 1),
            fecha_vigencia=date(2025, 2, 1),
        )
        suscripcion_actual = Suscripcion.objects.create(
            usuario=self.usuario,
            plan=plan_actual,
            fecha_inscripcion=date(2026, 1, 1),
            fecha_vigencia=date(2026, 12, 1),
        )
        Precio.objects.create(
            plan=plan_actual,
            precio=19.99,
            fecha_inicio=timezone.localdate(),
        )
        calidad = Calidad.objects.create(nombre='Full HD')
        PlanCalidad.objects.create(plan=plan_actual, calidad=calidad)
        perfil_activo = Perfil.objects.create(
            nombre='Principal',
            imagen=Imagen.objects.first(),
            tipo_perfil=TipoPerfil.objects.create(
                nombre='Cuenta test adulto',
                edad_max=100,
            ),
            usuario=self.usuario,
            activo=True,
        )
        Perfil.objects.create(
            nombre='Desactivado',
            imagen=perfil_activo.imagen,
            tipo_perfil=perfil_activo.tipo_perfil,
            usuario=self.usuario,
            activo=False,
        )
        Registro.objects.create(
            token_disp='activo-1',
            os='Navegador',
            ultima_conexion_fecha=timezone.localdate(),
            ultima_conexion_hora=timezone.localtime().time(),
            estado=True,
            usuario=self.usuario,
        )
        Registro.objects.create(
            token_disp='inactivo-1',
            os='Dispositivo cerrado',
            ultima_conexion_fecha=timezone.localdate(),
            ultima_conexion_hora=timezone.localtime().time(),
            estado=False,
            usuario=self.usuario,
        )

        respuesta = self.client.get(reverse('cuenta'), {'seccion': 'suscripcion'})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['suscripcion'], suscripcion_actual)
        self.assertContains(respuesta, 'Plan actual')
        self.assertContains(respuesta, '$19.99')
        self.assertContains(respuesta, 'Full HD')
        self.assertContains(respuesta, 'Dispositivos simultáneos')
        self.assertContains(respuesta, '<dd class="col-sm-7 account-subscription-value">2</dd>', html=True)
        self.assertContains(respuesta, '01/01/2026')
        self.assertContains(respuesta, 'Próximo Cobro')
        self.assertContains(respuesta, '01/01/2027')
        self.assertNotContains(respuesta, 'Plan anterior')
        self.assertEqual(respuesta.context['perfiles_activos'], 1)
        self.assertEqual(respuesta.context['sesiones_abiertas'], 1)

    def test_cancelar_plan_programa_baja_para_el_proximo_cobro(self):
        plan = Plan.objects.create(
            nombre='Plan a cancelar',
            cantidad_pantallas_simultaneas=1,
        )
        suscripcion = Suscripcion.objects.create(
            usuario=self.usuario,
            plan=plan,
            fecha_inscripcion=date(2030, 2, 20),
            fecha_vigencia=date(2030, 2, 20),
        )
        cambio = CambioPlan.objects.create(
            suscripcion=suscripcion,
            plan=Plan.objects.create(
                nombre='Plan programado',
                cantidad_pantallas_simultaneas=2,
            ),
            fecha_aplicacion=date(2030, 3, 20),
            nombre_titular='Usuario de prueba',
            tarjeta_ultimos4='1234',
        )
        self.assertContains(
            self.client.get(reverse('cuenta'), {'seccion': 'suscripcion'}),
            'Cancelar Plan',
        )

        respuesta = self.client.post(reverse('cancelar_suscripcion'))

        self.assertRedirects(
            respuesta,
            f'{reverse("cuenta")}?seccion=suscripcion',
        )
        suscripcion.refresh_from_db()
        cambio.refresh_from_db()
        self.assertTrue(suscripcion.habilitado)
        self.assertEqual(suscripcion.fecha_cancelacion, date(2030, 3, 20))
        self.assertEqual(cambio.estado, CambioPlan.ESTADO_CANCELADO)
        self.assertContains(
            self.client.get(reverse('cuenta'), {'seccion': 'suscripcion'}),
            'Fecha de cancelación',
        )
        self.assertTrue(suscripcion_activa(suscripcion, date(2030, 3, 19)))
        self.assertFalse(suscripcion_activa(suscripcion, date(2030, 3, 20)))
        self.assertContains(
            self.client.get(reverse('cuenta'), {'seccion': 'suscripcion'}),
            'Tu suscripción permanecerá activa hasta el',
        )
        self.assertNotContains(
            self.client.get(reverse('cuenta'), {'seccion': 'suscripcion'}),
            'Cancelar Plan',
        )

    def test_cancelar_suscripcion_rechaza_get_y_cuenta_sin_plan(self):
        respuesta_get = self.client.get(reverse('cancelar_suscripcion'))
        self.assertEqual(respuesta_get.status_code, 405)

        respuesta_post = self.client.post(
            reverse('cancelar_suscripcion'),
            follow=True,
        )
        self.assertContains(
            respuesta_post,
            'No tienes una suscripción activa para cancelar.',
        )

    def test_cambiar_plan_recolecta_datos_demo_y_programa_la_aplicacion(self):
        plan_actual = Plan.objects.create(
            nombre='Plan actual de cambio',
            cantidad_pantallas_simultaneas=1,
        )
        plan_nuevo = Plan.objects.create(
            nombre='Plan siguiente',
            cantidad_pantallas_simultaneas=3,
        )
        fecha_vigencia = date(2030, 2, 20)
        suscripcion = Suscripcion.objects.create(
            usuario=self.usuario,
            plan=plan_actual,
            fecha_inscripcion=date(2026, 1, 1),
            fecha_vigencia=fecha_vigencia,
        )
        Precio.objects.create(
            plan=plan_nuevo,
            precio=25,
            fecha_inicio=timezone.localdate(),
        )

        respuesta_cuenta = self.client.get(
            reverse('cuenta'),
            {'seccion': 'suscripcion'},
        )
        self.assertContains(respuesta_cuenta, 'Cambiar Plan')
        respuesta_planes = self.client.get(
            reverse('seleccionar_plan'),
            {'cambiar': '1'},
        )
        self.assertEqual(respuesta_planes.status_code, 200)
        self.assertContains(respuesta_planes, '20/03/2030')

        respuesta_seleccion = self.client.post(
            f'{reverse("seleccionar_plan")}?cambiar=1',
            {'plan': plan_nuevo.pk},
        )
        self.assertRedirects(
            respuesta_seleccion,
            reverse('pagar_cambio_plan', args=[plan_nuevo.pk]),
        )
        url_pago = reverse('pagar_cambio_plan', args=[plan_nuevo.pk])
        respuesta_pago = self.client.get(url_pago)
        self.assertEqual(respuesta_pago.status_code, 200)
        self.assertContains(respuesta_pago, 'nunca datos reales')
        self.assertContains(respuesta_pago, 'Número de tarjeta de prueba')
        self.assertContains(respuesta_pago, 'CVV ficticio')
        self.assertContains(respuesta_pago, 'Marca de la tarjeta')
        self.assertContains(respuesta_pago, 'Método de pago')
        self.assertContains(respuesta_pago, 'nunca datos reales')
        self.assertContains(respuesta_pago, '20/03/2030')

        respuesta_confirmacion = self.client.post(url_pago, {
            'nombre_titular': 'USUARIO DE PRUEBA',
            'numero_tarjeta': '4111111111111111',
            'cvv': '123',
            'marca_tarjeta': MarcaTarjeta.objects.get(nombre='Visa').pk,
            'metodo_pago': MetodoPago.objects.get(nombre='Débito').pk,
        })

        self.assertRedirects(
            respuesta_confirmacion,
            f'{reverse("cuenta")}?seccion=suscripcion',
        )
        cambio = CambioPlan.objects.get(suscripcion=suscripcion)
        self.assertEqual(cambio.plan, plan_nuevo)
        self.assertEqual(cambio.fecha_aplicacion, date(2030, 3, 20))
        self.assertEqual(cambio.tarjeta_ultimos4, '1111')
        self.assertEqual(cambio.nombre_titular, 'USUARIO DE PRUEBA')
        self.assertEqual(cambio.estado, CambioPlan.ESTADO_PENDIENTE)
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.plan, plan_actual)
        self.assertEqual(suscripcion.tarjeta.numero, '1111')
        self.assertEqual(suscripcion.tarjeta.marca_tarjeta.nombre, 'Visa')
        self.assertEqual(suscripcion.tarjeta.metodo_pago.nombre, 'Débito')
        respuesta_final = self.client.get(
            reverse('cuenta'),
            {'seccion': 'suscripcion'},
        )
        self.assertContains(respuesta_final, 'Plan siguiente')
        self.assertContains(respuesta_final, '20/03/2030')

    def test_no_se_puede_programar_mas_de_un_cambio_de_plan_pendiente(self):
        plan_actual = Plan.objects.create(
            nombre='Plan original',
            cantidad_pantallas_simultaneas=1,
        )
        plan_nuevo = Plan.objects.create(
            nombre='Plan programado',
            cantidad_pantallas_simultaneas=2,
        )
        suscripcion = Suscripcion.objects.create(
            usuario=self.usuario,
            plan=plan_actual,
            fecha_inscripcion=timezone.localdate(),
            fecha_vigencia=date(2030, 1, 1),
        )
        CambioPlan.objects.create(
            suscripcion=suscripcion,
            plan=plan_nuevo,
            fecha_aplicacion=date(2030, 1, 1),
            nombre_titular='Demo',
            tarjeta_ultimos4='1234',
        )

        respuesta = self.client.get(
            reverse('seleccionar_plan'),
            {'cambiar': '1'},
        )

        self.assertRedirects(
            respuesta,
            f'{reverse("cuenta")}?seccion=suscripcion',
        )

    def test_suscripcion_muestra_tarjeta_actual_guardada_en_suscripcion(self):
        plan = Plan.objects.create(
            nombre='Plan con cobros',
            cantidad_pantallas_simultaneas=1,
        )
        suscripcion = Suscripcion.objects.create(
            usuario=self.usuario,
            plan=plan,
            fecha_inscripcion=date(2026, 1, 1),
            fecha_vigencia=date(2026, 12, 1),
        )
        marca = MarcaTarjeta.objects.create(nombre='Visa', numero_asignado=4)
        metodo = MetodoPago.objects.create(nombre='Tarjeta')
        tarjeta_anterior = Tarjeta.objects.create(
            numero='1111',
            nombre_titular='Titular',
            fecha_vencimiento=date(2028, 1, 1),
            marca_tarjeta=marca,
            metodo_pago=metodo,
        )
        tarjeta_actual = Tarjeta.objects.create(
            numero='2222',
            nombre_titular='Titular',
            fecha_vencimiento=date(2029, 1, 1),
            marca_tarjeta=marca,
            metodo_pago=metodo,
        )
        suscripcion.tarjeta = tarjeta_actual
        suscripcion.save(update_fields=['tarjeta'])
        estado = EstadoCobro.objects.create(nombre='Aprobado')
        Cobro.objects.create(
            num_factura=1,
            suscripcion=suscripcion,
            fecha_cobro=date(2026, 2, 1),
            estado_cobro=estado,
            tarjeta=tarjeta_anterior,
            monto=10,
        )
        cobro_reciente = Cobro.objects.create(
            num_factura=2,
            suscripcion=suscripcion,
            fecha_cobro=date(2026, 3, 1),
            estado_cobro=estado,
            tarjeta=tarjeta_actual,
            monto=10,
        )

        respuesta = self.client.get(
            reverse('cuenta'),
            {'seccion': 'suscripcion'},
        )

        self.assertEqual(respuesta.context['ultimo_cobro'], cobro_reciente)
        self.assertContains(respuesta, 'Visa terminada en 2222')
        self.assertNotContains(respuesta, '4111')
        self.assertNotContains(respuesta, '2222"')

    def test_pestana_cobros_muestra_todos_ordenados_y_con_su_periodo(self):
        marca = MarcaTarjeta.objects.create(nombre='Visa', numero_asignado=4)
        metodo = MetodoPago.objects.create(nombre='Tarjeta')
        tarjeta = Tarjeta.objects.create(
            numero='4321',
            nombre_titular='Titular',
            fecha_vencimiento=date(2029, 1, 1),
            marca_tarjeta=marca,
            metodo_pago=metodo,
        )
        estado = EstadoCobro.objects.create(nombre='Aprobado')
        suscripcion_anterior = Suscripcion.objects.create(
            usuario=self.usuario,
            plan=Plan.objects.create(
                nombre='Plan anterior',
                cantidad_pantallas_simultaneas=1,
            ),
            fecha_inscripcion=date(2026, 1, 1),
            fecha_vigencia=date(2026, 2, 28),
        )
        suscripcion_actual = Suscripcion.objects.create(
            usuario=self.usuario,
            plan=Plan.objects.create(
                nombre='Plan actual',
                cantidad_pantallas_simultaneas=2,
            ),
            fecha_inscripcion=date(2026, 3, 1),
            fecha_vigencia=date(2026, 3, 28),
        )
        cobro_anterior = Cobro.objects.create(
            num_factura=101,
            suscripcion=suscripcion_anterior,
            fecha_cobro=date(2026, 2, 28),
            estado_cobro=estado,
            tarjeta=tarjeta,
            monto=10,
        )
        cobro_reciente = Cobro.objects.create(
            num_factura=102,
            suscripcion=suscripcion_actual,
            fecha_cobro=date(2026, 3, 28),
            estado_cobro=estado,
            tarjeta=tarjeta,
            monto=20,
        )

        respuesta = self.client.get(
            reverse('cuenta'),
            {'seccion': 'cobros'},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            list(respuesta.context['cobros']),
            [cobro_reciente, cobro_anterior],
        )
        self.assertEqual(
            [cobro.plan_facturado.nombre for cobro in respuesta.context['cobros']],
            ['Plan actual', 'Plan anterior'],
        )
        self.assertContains(respuesta, '28/03/2026')
        self.assertContains(respuesta, '27/04/2026')
        self.assertContains(respuesta, '28/02/2026')
        self.assertContains(respuesta, '27/03/2026')
        self.assertContains(respuesta, '**** 4321')
        self.assertContains(respuesta, '101')
        self.assertContains(respuesta, '102')
        self.assertContains(respuesta, '$20.00')

    def test_suscripcion_sin_cobros_muestra_mensaje_para_tarjeta(self):
        Suscripcion.objects.create(
            usuario=self.usuario,
            plan=Plan.objects.create(
                nombre='Plan sin cobros',
                cantidad_pantallas_simultaneas=1,
            ),
            fecha_inscripcion=date(2026, 1, 1),
            fecha_vigencia=date(2026, 12, 1),
        )

        respuesta = self.client.get(
            reverse('cuenta'),
            {'seccion': 'suscripcion'},
        )

        self.assertContains(respuesta, 'Tarjeta asociada')
        self.assertContains(respuesta, 'No hay una tarjeta asignada a la suscripción.')

    def test_proximo_cobro_ajusta_el_dia_al_ultimo_del_mes(self):
        suscripcion = Suscripcion.objects.create(
            usuario=self.usuario,
            plan=Plan.objects.create(
                nombre='Plan mensual',
                cantidad_pantallas_simultaneas=1,
            ),
            fecha_inscripcion=date(2026, 1, 1),
            fecha_vigencia=date(2026, 1, 31),
        )

        respuesta = self.client.get(
            reverse('cuenta'),
            {'seccion': 'suscripcion'},
        )

        self.assertEqual(respuesta.context['proximo_cobro'], date(2026, 2, 28))
        self.assertContains(respuesta, '28/02/2026')

        suscripcion.fecha_vigencia = date(2024, 1, 31)
        suscripcion.save(update_fields=['fecha_vigencia'])
        respuesta_bisiesta = self.client.get(
            reverse('cuenta'),
            {'seccion': 'suscripcion'},
        )
        self.assertEqual(
            respuesta_bisiesta.context['proximo_cobro'],
            date(2024, 2, 29),
        )

        suscripcion.fecha_vigencia = date(2026, 12, 31)
        suscripcion.save(update_fields=['fecha_vigencia'])
        respuesta_cambio_anio = self.client.get(
            reverse('cuenta'),
            {'seccion': 'suscripcion'},
        )
        self.assertEqual(
            respuesta_cambio_anio.context['proximo_cobro'],
            date(2027, 1, 31),
        )

    def test_sin_fecha_vigencia_no_calcula_proximo_cobro(self):
        Suscripcion.objects.create(
            usuario=self.usuario,
            plan=Plan.objects.create(
                nombre='Plan sin vigencia',
                cantidad_pantallas_simultaneas=1,
            ),
            fecha_inscripcion=date(2026, 1, 1),
            fecha_vigencia=None,
        )

        respuesta = self.client.get(
            reverse('cuenta'),
            {'seccion': 'suscripcion'},
        )

        self.assertIsNone(respuesta.context['proximo_cobro'])
        self.assertContains(respuesta, 'Próximo Cobro')
        self.assertContains(respuesta, 'No asignado')

    def test_editar_contrasena_requiere_actual_y_dos_entradas_iguales(self):
        respuesta = self.client.post(
            reverse('editar_dato_cuenta', args=['password']),
            {
                'current_password': 'Clave-Segura-2026!',
                'new_password': 'Otra-Clave-Segura-2026!',
                'confirm_password': 'Otra-Clave-Segura-2026!',
            },
        )

        self.assertRedirects(respuesta, f'{reverse("cuenta")}?seccion=usuario')
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password('Otra-Clave-Segura-2026!'))

    def test_cambiar_contrasena_cierra_otras_sesiones_y_conserva_la_actual(self):
        self.client.get(reverse('cuenta'))
        session_key_actual = self.client.session.session_key
        otro_cliente = Client()
        otro_cliente.post(reverse('login'), {
            'email': self.usuario.email,
            'password': 'Clave-Segura-2026!',
        })
        session_key_otra = otro_cliente.session.session_key
        self.assertTrue(Session.objects.filter(session_key=session_key_otra).exists())
        self.assertContains(
            self.client.get(reverse('editar_dato_cuenta', args=['password'])),
            'se cerrarán todas las sesiones excepto la actual',
        )

        respuesta = self.client.post(
            reverse('editar_dato_cuenta', args=['password']),
            {
                'current_password': 'Clave-Segura-2026!',
                'new_password': 'Otra-Clave-Segura-2026!',
                'confirm_password': 'Otra-Clave-Segura-2026!',
            },
        )

        self.assertRedirects(respuesta, f'{reverse("cuenta")}?seccion=usuario')
        session_key_actual_nueva = self.client.session.session_key
        self.assertNotEqual(session_key_actual_nueva, session_key_actual)
        self.assertTrue(Session.objects.filter(
            session_key=session_key_actual_nueva,
        ).exists())
        self.assertFalse(Session.objects.filter(session_key=session_key_otra).exists())
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password('Otra-Clave-Segura-2026!'))
        self.assertTrue(Registro.objects.get(
            usuario=self.usuario,
            token_disp=session_key_actual_nueva,
        ).estado)
        self.assertFalse(Registro.objects.get(
            usuario=self.usuario,
            token_disp=session_key_otra,
        ).estado)
        self.assertEqual(self.client.get(reverse('cuenta')).status_code, 200)
        self.assertRedirects(
            otro_cliente.get(reverse('cuenta')),
            f'{reverse("login")}?next={reverse("cuenta")}',
        )
        self.assertTrue('_auth_user_id' in self.client.session)
        self.assertEqual(self.client.get(reverse('cuenta')).status_code, 200)

    def test_editar_contrasena_rechaza_actual_incorrecta_y_confirmacion_distinta(self):
        respuesta = self.client.post(
            reverse('editar_dato_cuenta', args=['password']),
            {
                'current_password': 'incorrecta',
                'new_password': 'Otra-Clave-Segura-2026!',
                'confirm_password': 'No-coincide-2026!',
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'La contraseña vigente no es correcta.')
        self.assertContains(respuesta, 'Las contraseñas nuevas no coinciden.')
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password('Clave-Segura-2026!'))

    def test_pestana_mas_info_muestra_texto_legal_inicial(self):
        respuesta = self.client.get(reverse('cuenta'), {'seccion': 'mas-info'})

        self.assertContains(respuesta, 'Términos de uso')
        self.assertContains(respuesta, 'Privacidad y datos personales')
        self.assertNotContains(respuesta, 'Texto informativo inicial.')
        self.assertContains(respuesta, 'color: rgba(255, 255, 255, 0.9)')
        self.assertContains(respuesta, '.account-legal h2')
        self.assertContains(respuesta, 'color: #fff')
        self.assertContains(respuesta, 'soporte@redflix.example')
        self.assertContains(respuesta, 'privacidad@redflix.example')
        self.assertContains(respuesta, '0800-RED-FLIX')
        self.assertNotContains(respuesta, 'Debe ser revisado y aprobado legalmente')

    def test_footer_no_muestra_opciones_eliminadas(self):
        respuesta = self.client.get(reverse('cuenta'))

        for opcion in (
            'Inversores',
            'Centro de ayuda',
            'Empleo',
            'Canjear tarjetas',
            'Prensa',
            'Comprar tarjetas',
        ):
            with self.subTest(opcion=opcion):
                self.assertNotContains(respuesta, opcion)


class ProcesamientoCobrosTests(TestCase):
    def test_fecha_inicial_se_hereda_solo_si_la_suscripcion_previa_sigue_activa(self):
        hoy = date(2026, 11, 9)
        plan = Plan.objects.create(
            nombre='Plan de fechas',
            cantidad_pantallas_simultaneas=1,
        )
        usuario_nuevo = Usuario.objects.create_user(
            username='nuevo-fechas',
            email='nuevo-fechas@example.test',
            password='UnaClave-larga-2026!',
        )
        self.assertEqual(fecha_inicio_suscripcion(usuario_nuevo, hoy), hoy)

        usuario_activo = Usuario.objects.create_user(
            username='activo-fechas',
            email='activo-fechas@example.test',
            password='UnaClave-larga-2026!',
        )
        Suscripcion.objects.create(
            usuario=usuario_activo,
            plan=plan,
            fecha_inscripcion=date(2026, 11, 1),
            fecha_vigencia=date(2026, 11, 1),
            fecha_cancelacion=date(2026, 12, 31),
            habilitado=True,
        )
        self.assertEqual(
            fecha_inicio_suscripcion(usuario_activo, hoy),
            date(2026, 11, 1),
        )

        usuario_cancelado = Usuario.objects.create_user(
            username='cancelado-fechas',
            email='cancelado-fechas@example.test',
            password='UnaClave-larga-2026!',
        )
        suscripcion_cancelada = Suscripcion.objects.create(
            usuario=usuario_cancelado,
            plan=plan,
            fecha_inscripcion=date(2026, 11, 1),
            fecha_vigencia=date(2026, 11, 1),
            fecha_cancelacion=date(2026, 11, 30),
            habilitado=True,
        )
        self.assertEqual(
            fecha_inicio_suscripcion(usuario_cancelado, hoy),
            date(2026, 11, 1),
        )
        self.assertTrue(suscripcion_activa(suscripcion_cancelada, date(2026, 11, 29)))
        self.assertFalse(suscripcion_activa(suscripcion_cancelada, date(2026, 11, 30)))

    @override_settings(DEBUG=True)
    def test_worker_no_crea_cobro_si_el_siguiente_vencimiento_supera_cancelacion(self):
        usuario = Usuario.objects.create_user(
            username='cancelacion-cobro',
            email='cancelacion-cobro@example.test',
            password='UnaClave-larga-2026!',
        )
        plan = Plan.objects.create(
            nombre='Plan cancelado',
            cantidad_pantallas_simultaneas=1,
        )
        Precio.objects.create(
            plan=plan,
            precio=10,
            fecha_inicio=date(2026, 1, 1),
        )
        marca = MarcaTarjeta.objects.create(
            nombre='Tarjeta Demo',
            numero_asignado=0,
        )
        metodo = MetodoPago.objects.create(nombre='Pago de prueba')
        tarjeta = Tarjeta.objects.create(
            numero='4321',
            nombre_titular='Usuario Demo',
            fecha_vencimiento=date(2036, 2, 1),
            marca_tarjeta=marca,
            metodo_pago=metodo,
        )
        suscripcion = Suscripcion.objects.create(
            usuario=usuario,
            plan=plan,
            fecha_inscripcion=date(2026, 1, 31),
            fecha_vigencia=date(2026, 1, 31),
            fecha_cancelacion=date(2026, 2, 28),
            tarjeta=tarjeta,
        )

        resultado_antes = procesar_cobros_demo(
            ahora=timezone.make_aware(datetime(2026, 2, 27, 12, 0, 0)),
        )
        self.assertEqual(
            resultado_antes,
            {
                'creados': 0,
                'aprobados': 0,
                'suscripciones_canceladas': 0,
            },
        )
        suscripcion.refresh_from_db()
        self.assertTrue(suscripcion.habilitado)

        resultado = procesar_cobros_demo(
            ahora=timezone.make_aware(datetime(2026, 2, 28, 12, 0, 0)),
        )

        self.assertEqual(
            resultado,
            {
                'creados': 0,
                'aprobados': 0,
                'suscripciones_canceladas': 1,
            },
        )
        self.assertFalse(Cobro.objects.filter(suscripcion=suscripcion).exists())
        suscripcion.refresh_from_db()
        self.assertFalse(suscripcion.habilitado)

    @override_settings(DEBUG=True)
    def test_worker_cancela_cobro_pendiente_en_fecha_de_baja(self):
        usuario = Usuario.objects.create_user(
            username='cancelacion-cobro-pendiente',
            email='cancelacion-cobro-pendiente@example.test',
            password='UnaClave-larga-2026!',
        )
        plan = Plan.objects.create(
            nombre='Plan con baja pendiente',
            cantidad_pantallas_simultaneas=1,
        )
        plan_siguiente = Plan.objects.create(
            nombre='Plan siguiente pendiente',
            cantidad_pantallas_simultaneas=2,
        )
        marca = MarcaTarjeta.objects.create(
            nombre='Tarjeta Demo pendiente',
            numero_asignado=0,
        )
        metodo = MetodoPago.objects.create(nombre='Pago pendiente demo')
        tarjeta = Tarjeta.objects.create(
            numero='4321',
            nombre_titular='Usuario Demo',
            fecha_vencimiento=date(2036, 2, 1),
            marca_tarjeta=marca,
            metodo_pago=metodo,
        )
        suscripcion = Suscripcion.objects.create(
            usuario=usuario,
            plan=plan,
            fecha_inscripcion=date(2026, 1, 31),
            fecha_vigencia=date(2026, 1, 31),
            fecha_cancelacion=date(2026, 2, 28),
            tarjeta=tarjeta,
        )
        cambio = CambioPlan.objects.create(
            suscripcion=suscripcion,
            plan=plan_siguiente,
            fecha_aplicacion=date(2026, 2, 28),
            nombre_titular='Usuario Demo',
            tarjeta_ultimos4='4321',
        )
        por_aprobar = EstadoCobro.objects.create(nombre='Por aprobar')
        cobro = Cobro.objects.create(
            num_factura=1,
            suscripcion=suscripcion,
            fecha_cobro=date(2026, 2, 28),
            estado_cobro=por_aprobar,
            tarjeta=tarjeta,
            monto=20,
            fecha_hora_creacion=timezone.make_aware(
                datetime(2026, 2, 28, 12, 0, 0),
            ),
            cambio_plan=cambio,
        )

        resultado = procesar_cobros_demo(
            ahora=timezone.make_aware(datetime(2026, 2, 28, 12, 0, 6)),
        )

        self.assertEqual(
            resultado,
            {'creados': 0, 'aprobados': 0, 'suscripciones_canceladas': 1},
        )
        cobro.refresh_from_db()
        cambio.refresh_from_db()
        suscripcion.refresh_from_db()
        self.assertEqual(cobro.estado_cobro.nombre, 'Cancelado')
        self.assertEqual(cambio.estado, CambioPlan.ESTADO_CANCELADO)
        self.assertFalse(suscripcion.habilitado)
        self.assertEqual(suscripcion.fecha_vigencia, date(2026, 1, 31))

    @override_settings(DEBUG=True)
    def test_cobro_se_crea_en_fecha_mensual_y_se_aprueba_a_los_cinco_segundos(self):
        usuario = Usuario.objects.create_user(
            username='cobros@example.test',
            email='cobros@example.test',
            password='UnaClave-larga-2026!',
        )
        plan_actual = Plan.objects.create(
            nombre='Plan mensual inicial',
            cantidad_pantallas_simultaneas=1,
        )
        plan_siguiente = Plan.objects.create(
            nombre='Plan mensual siguiente',
            cantidad_pantallas_simultaneas=2,
        )
        marca = MarcaTarjeta.objects.create(
            nombre='Tarjeta Demo',
            numero_asignado=0,
        )
        metodo = MetodoPago.objects.create(nombre='Pago de prueba')
        tarjeta = Tarjeta.objects.create(
            numero='4321',
            nombre_titular='Usuario Demo',
            fecha_vencimiento=date(2036, 2, 1),
            marca_tarjeta=marca,
            metodo_pago=metodo,
        )
        suscripcion = Suscripcion.objects.create(
            usuario=usuario,
            plan=plan_actual,
            fecha_inscripcion=date(2026, 1, 1),
            fecha_vigencia=date(2026, 1, 31),
            tarjeta=tarjeta,
        )
        Precio.objects.create(
            plan=plan_actual,
            precio=10,
            fecha_inicio=date(2026, 1, 1),
        )
        Precio.objects.create(
            plan=plan_siguiente,
            precio=20,
            fecha_inicio=date(2026, 1, 1),
        )
        cambio = CambioPlan.objects.create(
            suscripcion=suscripcion,
            plan=plan_siguiente,
            fecha_aplicacion=date(2026, 2, 28),
            nombre_titular='Usuario Demo',
            tarjeta_ultimos4='4321',
        )
        hora_cobro = timezone.make_aware(datetime(2026, 2, 28, 12, 0, 0))

        resultado_creacion = procesar_cobros_demo(ahora=hora_cobro)

        self.assertEqual(
            resultado_creacion,
            {'creados': 1, 'aprobados': 0, 'suscripciones_canceladas': 0},
        )
        cobro = Cobro.objects.get(suscripcion=suscripcion)
        self.assertEqual(cobro.numero_autorizacion, '')
        self.assertEqual(cobro.fecha_cobro, date(2026, 2, 28))
        self.assertEqual(cobro.tarjeta, suscripcion.tarjeta)
        self.assertEqual(cobro.monto, 20)
        self.assertEqual(cobro.estado_cobro.nombre, 'Por aprobar')
        self.assertEqual(cobro.cambio_plan, cambio)
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.plan, plan_actual)
        self.assertEqual(suscripcion.fecha_vigencia, date(2026, 1, 31))

        resultado_aprobacion = procesar_cobros_demo(
            ahora=hora_cobro + timedelta(seconds=6),
        )

        self.assertEqual(
            resultado_aprobacion,
            {'creados': 0, 'aprobados': 1, 'suscripciones_canceladas': 0},
        )
        cobro.refresh_from_db()
        self.assertEqual(cobro.estado_cobro.nombre, 'Aprobado')
        self.assertRegex(cobro.numero_autorizacion, r'^DEMO-AUTH-[0-9A-F]{12}$')
        cambio.refresh_from_db()
        self.assertEqual(cambio.estado, CambioPlan.ESTADO_APLICADO)
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.plan, plan_siguiente)
        self.assertEqual(suscripcion.fecha_vigencia, date(2026, 2, 28))

        siguiente_ciclo = procesar_cobros_demo(
            ahora=timezone.make_aware(datetime(2026, 3, 28, 12, 0, 0)),
        )
        self.assertEqual(
            siguiente_ciclo,
            {'creados': 1, 'aprobados': 0, 'suscripciones_canceladas': 0},
        )
        cobro_siguiente = Cobro.objects.get(
            suscripcion=suscripcion,
            fecha_cobro=date(2026, 3, 28),
        )
        self.assertEqual(cobro_siguiente.tarjeta, tarjeta)
        self.assertEqual(cobro_siguiente.monto, 20)

    @override_settings(DEBUG=False)
    def test_worker_no_procesa_cobros_ficticios_en_produccion(self):
        with self.assertRaisesMessage(
            CommandError,
            'solo puede ejecutarse con DEBUG activado',
        ):
            procesar_cobros_demo()


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
            is_staff=True,
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
        self.client.force_login(usuario)

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
            is_staff=True,
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
        usuario = Usuario.objects.create_user(
            username='estadisticas-admin@example.com',
            email='estadisticas-admin@example.com',
            password='UnaClave-larga-2026!',
            is_staff=True,
        )
        self.client.force_login(usuario)
        response = self.client.get(reverse('reporte_ventas'), {
            'fecha_inicio': '2026-10-20',
            'fecha_fin': '2026-10-19',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'La fecha inicial no puede ser posterior a la fecha final.')
        self.assertEqual(response.context['data_miembros_json'], [])
        self.assertFalse(response.context['es_demostracion'])

    def test_solo_administradores_acceden_a_estadisticas_y_ven_el_enlace(self):
        visitante = self.client.get(reverse('reporte_ventas'))
        self.assertRedirects(
            visitante,
            f'{reverse("login")}?next={reverse("reporte_ventas")}',
        )

        usuario = Usuario.objects.create_user(
            username='cliente@example.com',
            email='cliente@example.com',
            password='UnaClave-larga-2026!',
        )
        self.client.force_login(usuario)
        acceso_cliente = self.client.get(reverse('reporte_ventas'))
        self.assertEqual(acceso_cliente.status_code, 403)
        menu_cliente = self.client.get(reverse('home'))
        self.assertNotContains(menu_cliente, reverse('reporte_ventas'))

        administrador = Usuario.objects.create_user(
            username='admin@example.com',
            email='admin@example.com',
            password='UnaClave-larga-2026!',
            is_staff=True,
        )
        self.client.force_login(administrador)
        acceso_admin = self.client.get(reverse('reporte_ventas'))
        self.assertEqual(acceso_admin.status_code, 200)
        menu_admin = self.client.get(reverse('home'))
        self.assertContains(menu_admin, reverse('reporte_ventas'))


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

    def test_titulo_abre_reproduccion_del_primer_contenido_con_video_localizado(self):
        ingles = Idioma.objects.create(nombre='English')
        titulo = self.crear_titulo(
            'Película para reproducir',
            self.pelicula,
            con_contenido=False,
        )
        contenido_posterior = Contenido.objects.create(
            nombre='Segundo contenido',
            seccion=1,
            orden=2,
            duracion_segundos=120,
            titulo=titulo,
        )
        primer_contenido = Contenido.objects.create(
            nombre='Primer contenido',
            seccion=1,
            orden=1,
            duracion_segundos=60,
            titulo=titulo,
        )
        idioma_espanol = IdiomaContenido.objects.create(
            idioma=self.idioma,
            contenido=primer_contenido,
        )
        idioma_ingles = IdiomaContenido.objects.create(
            idioma=ingles,
            contenido=primer_contenido,
        )
        calidad_hd = Calidad.objects.create(nombre='HD')
        calidad_full_hd = Calidad.objects.create(nombre='Full HD')
        CalidadIdiomaContenido.objects.create(
            idioma_contenido=idioma_ingles,
            calidad=calidad_hd,
            archivo_legacy=b'',
            archivo='videos/primer-contenido-en.mp4',
        )
        video_espanol = CalidadIdiomaContenido.objects.create(
            idioma_contenido=idioma_espanol,
            calidad=calidad_hd,
            archivo_legacy=b'',
            archivo='videos/primer-contenido-es.mp4',
        )
        video_full_hd = CalidadIdiomaContenido.objects.create(
            idioma_contenido=idioma_espanol,
            calidad=calidad_full_hd,
            archivo_legacy=b'',
            archivo='videos/primer-contenido-full-hd.mp4',
        )
        idioma_contenido_posterior = IdiomaContenido.objects.create(
            idioma=self.idioma,
            contenido=contenido_posterior,
        )
        video_posterior = CalidadIdiomaContenido.objects.create(
            idioma_contenido=idioma_contenido_posterior,
            calidad=calidad_hd,
            archivo_legacy=b'',
            archivo='videos/contenido-posterior.mp4',
        )
        plan = Plan.objects.create(
            nombre='Plan HD',
            cantidad_pantallas_simultaneas=1,
        )
        PlanCalidad.objects.create(plan=plan, calidad=calidad_hd)
        usuario = Usuario.objects.create_user(
            username='reproduccion@example.com',
            email='reproduccion@example.com',
            password='UnaClave-larga-2026!',
            idioma=self.idioma,
        )
        Suscripcion.objects.create(
            usuario=usuario,
            plan=plan,
            fecha_inscripcion=timezone.localdate(),
            fecha_vigencia=timezone.localdate(),
        )
        self.autenticar_con_perfil(usuario)

        with patch(
            'django.core.files.storage.FileSystemStorage.exists',
            side_effect=lambda path: path.startswith('videos/'),
        ):
            respuesta_inicio = self.client.get(reverse('home'))
            self.assertContains(
                respuesta_inicio,
                reverse('reproducir_titulo', args=[titulo.pk]),
            )
            pagina_inicio_regreso = self.client.get(
                reverse('home'),
                {'titulo': titulo.pk},
            )
            self.assertContains(
                pagina_inicio_regreso,
                f'data-title-id="{titulo.pk}"',
            )
            self.assertContains(
                pagina_inicio_regreso,
                'new URLSearchParams(window.location.search).get(\'titulo\')',
            )
            respuesta = self.client.get(
                reverse('reproducir_titulo', args=[titulo.pk]),
            )
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.context['contenido'], primer_contenido)
            self.assertContains(respuesta, 'Español')
            self.assertContains(respuesta, 'English')
            self.assertContains(respuesta, 'Plan HD')
            self.assertNotContains(respuesta, 'Full HD')

            respuesta_contenido = self.client.get(
                reverse(
                    'reproducir_contenido',
                    args=[titulo.pk, contenido_posterior.pk],
                ),
            )
            self.assertEqual(respuesta_contenido.status_code, 200)
            self.assertEqual(
                respuesta_contenido.context['contenido'],
                contenido_posterior,
            )
            respuesta_video_posterior = self.client.post(
                reverse(
                    'reproducir_contenido',
                    args=[titulo.pk, contenido_posterior.pk],
                ),
                {
                    'idioma': self.idioma.pk,
                    'video': video_posterior.pk,
                },
            )
            self.assertRedirects(
                respuesta_video_posterior,
                reverse(
                    'reproducir_video',
                    args=[titulo.pk, video_posterior.pk],
                ),
                fetch_redirect_response=False,
            )
            pagina_video_posterior = self.client.get(
                reverse(
                    'reproducir_video',
                    args=[titulo.pk, video_posterior.pk],
                ),
            )
            self.assertEqual(pagina_video_posterior.status_code, 200)
            self.assertEqual(
                pagina_video_posterior.context['contenido'],
                contenido_posterior,
            )
            self.assertContains(
                pagina_video_posterior,
                'videos/contenido-posterior.mp4',
            )

            respuesta_reproduccion = self.client.post(
                reverse('reproducir_titulo', args=[titulo.pk]),
                {
                    'idioma': self.idioma.pk,
                    'video': video_espanol.pk,
                },
            )
            self.assertRedirects(
                respuesta_reproduccion,
                reverse(
                    'reproducir_video',
                    args=[titulo.pk, video_espanol.pk],
                ),
                fetch_redirect_response=False,
            )
            pagina_video = self.client.get(
                reverse('reproducir_video', args=[titulo.pk, video_espanol.pk]),
            )
            self.assertEqual(pagina_video.status_code, 200)
            self.assertEqual(pagina_video.context['video'], video_espanol)
            self.assertContains(pagina_video, 'videos/primer-contenido-es.mp4')
            self.assertNotContains(pagina_video, 'Elige idioma y calidad')
            self.assertContains(
                pagina_video,
                f'href="{reverse("home")}?titulo={titulo.pk}"',
            )
            self.assertContains(pagina_video, 'Volver a Inicio')
            self.assertContains(pagina_video, 'data-video-backward')
            self.assertContains(pagina_video, 'data-video-forward')
            self.assertContains(pagina_video, 'data-video-seek')
            self.assertContains(pagina_video, 'data-video-mute')
            self.assertContains(pagina_video, 'data-video-volume')
            self.assertContains(pagina_video, 'accent-color: #e50914')
            self.assertContains(pagina_video, 'video-volume-control:hover .video-volume')
            self.assertContains(pagina_video, 'video-controls-hidden')
            self.assertContains(pagina_video, '}, 3000)')
            self.assertContains(pagina_video, 'margin-left: auto')
            self.assertNotContains(pagina_video, '<video controls')
            self.assertNotContains(pagina_video, 'Volver a Inicio</')
            self.assertNotContains(pagina_video, '<nav class="navbar')
            self.assertNotContains(pagina_video, '<footer')
            self.assertContains(pagina_video, 'data-captions-toggle')
            self.assertContains(pagina_video, 'data-captions-menu')
            self.assertContains(pagina_video, 'Español')
            self.assertContains(pagina_video, 'English')
            self.assertContains(pagina_video, 'kind="subtitles"')
            subtitulos = list(Subtitulo.objects.filter(contenido=primer_contenido))
            self.assertEqual(len(subtitulos), 2)
            subtitulo_ingles = next(
                subtitulo for subtitulo in subtitulos
                if subtitulo.idioma.nombre in {'Inglés', 'English'}
            )
            respuesta_subtitulo = self.client.get(
                reverse(
                    'servir_subtitulo',
                    args=[titulo.pk, video_espanol.pk, subtitulo_ingles.pk],
                ),
            )
            self.assertEqual(respuesta_subtitulo.status_code, 200)
            self.assertEqual(
                respuesta_subtitulo['Content-Type'],
                'text/vtt; charset=utf-8',
            )
            self.assertTrue(respuesta_subtitulo.content.startswith(b'WEBVTT'))

            respuesta_no_permitida = self.client.post(
                reverse('reproducir_titulo', args=[titulo.pk]),
                {
                    'idioma': self.idioma.pk,
                    'video': video_full_hd.pk,
                },
            )
            self.assertContains(
                respuesta_no_permitida,
                'Selecciona un idioma y una calidad disponibles para tu plan.',
            )
            respuesta_directa_no_permitida = self.client.get(
                reverse('reproducir_video', args=[titulo.pk, video_full_hd.pk]),
            )
            self.assertEqual(respuesta_directa_no_permitida.status_code, 404)
        self.assertEqual(contenido_posterior.orden, 2)

    def test_reproduccion_requiere_perfil_y_respeta_clasificacion_de_edad(self):
        titulo = self.crear_titulo(
            'Contenido restringido',
            self.pelicula,
            con_contenido=True,
            edad_minima=18,
        )
        usuario = Usuario.objects.create_user(
            username='perfil-reproduccion@example.com',
            email='perfil-reproduccion@example.com',
            password='UnaClave-larga-2026!',
        )
        self.client.force_login(usuario)

        respuesta_sin_perfil = self.client.get(
            reverse('reproducir_titulo', args=[titulo.pk]),
        )

        self.assertRedirects(
            respuesta_sin_perfil,
            reverse('perfiles'),
            fetch_redirect_response=False,
        )
        self.autenticar_con_perfil(usuario, edad_max=17)
        respuesta_restringida = self.client.get(
            reverse('reproducir_titulo', args=[titulo.pk]),
        )
        self.assertEqual(respuesta_restringida.status_code, 404)

    def test_busqueda_por_elenco_devuelve_titulos_del_elenco_coincidente(self):
        titulo = self.crear_titulo(
            'Historia con actriz',
            self.pelicula,
            con_contenido=True,
        )
        titulo_restringido = self.crear_titulo(
            'Historia para adultos',
            self.pelicula,
            con_contenido=True,
            edad_minima=18,
        )
        actriz = Elenco.objects.create(
            pais=self.pais,
            nombre='María',
            apellido='De la Cruz',
        )
        rol = Rol.objects.create(nombre='Actriz')
        rol_elenco = RolElenco.objects.create(rol=rol, elenco=actriz)
        TituloRolElenco.objects.create(titulo=titulo, rol_elenco=rol_elenco)
        TituloRolElenco.objects.create(titulo=titulo_restringido, rol_elenco=rol_elenco)
        usuario = Usuario.objects.create_user(
            username='busqueda-elenco@example.com',
            email='busqueda-elenco@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario, edad_max=17)

        respuesta = self.client.get(
            reverse('buscar_titulos'),
            {'q': 'maría de', 'tipo': 'elenco'},
        )

        self.assertEqual(respuesta.status_code, 200)
        resultados = respuesta.json()['resultados']
        self.assertEqual([resultado['id'] for resultado in resultados], [titulo.pk])
        self.assertEqual(
            resultados[0]['elencos_coincidentes'],
            ['María De la Cruz'],
        )

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

    def test_preferencia_ingles_localiza_titulo_y_contenido_en_home(self):
        ingles = Idioma.objects.create(nombre='Inglés')
        titulo = self.crear_titulo(
            'Nombre original',
            self.serie,
            con_contenido=True,
        )
        titulo.descripcion_original = 'Descripción original.'
        titulo.save(update_fields=['descripcion_original'])
        IdiomaTitulo.objects.create(
            titulo=titulo,
            idioma=ingles,
            nombre='English Series',
            descripcion='An English title description.',
        )
        contenido = titulo.contenidos.get()
        contenido.descripcion = 'Descripción del episodio original.'
        contenido.save(update_fields=['descripcion'])
        IdiomaContenido.objects.create(
            contenido=contenido,
            idioma=ingles,
            nombre='English Episode',
            descripcion='An English episode description.',
        )
        usuario = Usuario.objects.create_user(
            username='preferencia-idioma@example.com',
            email='preferencia-idioma@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta_preferencias = self.client.post(
            reverse('cuenta'),
            {
                'pais': '',
                'idioma': ingles.pk,
            },
        )
        self.assertRedirects(
            respuesta_preferencias,
            f'{reverse("cuenta")}?seccion=usuario',
        )
        respuesta_home = self.client.get(
            reverse('home'),
            {'titulo': titulo.pk},
        )

        titulo_home = next(
            titulo_en_lista
            for carrusel in respuesta_home.context['carruseles']
            for titulo_en_lista in carrusel['titulos']
            if titulo_en_lista.pk == titulo.pk
        )
        self.assertEqual(titulo_home.nombre_mostrar, 'English Series')
        self.assertEqual(
            titulo_home.descripcion_mostrar,
            'An English title description.',
        )
        self.assertEqual(
            titulo_home.contenidos_detalle[0]['nombre'],
            'English Episode',
        )
        self.assertEqual(
            titulo_home.contenidos_detalle[0]['descripcion'],
            'An English episode description.',
        )

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
            categoria=self.accion,
            edad_minima=13,
        )
        titulo.descripcion_original = 'Una historia para probar la ficha.'
        titulo.save(update_fields=['descripcion_original'])
        self.agregar_imagen_titulo(
            titulo,
            'Imagen de la historia',
            'demo/banners/historia.svg',
        )
        persona = Elenco.objects.create(
            pais=self.pais,
            nombre='Actriz',
            apellido='De prueba',
        )
        rol = Rol.objects.create(nombre='Actriz')
        rol_elenco = RolElenco.objects.create(rol=rol, elenco=persona)
        TituloRolElenco.objects.create(titulo=titulo, rol_elenco=rol_elenco)
        usuario = Usuario.objects.create_user(
            username='ficha-titulo@example.com',
            email='ficha-titulo@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'))

        self.assertContains(respuesta, 'data-title-details-open')
        self.assertContains(respuesta, 'class="title-poster-play-link"')
        self.assertContains(
            respuesta,
            f'href="{reverse("reproducir_titulo", args=[titulo.pk])}"',
        )
        self.assertContains(respuesta, 'bi bi-list')
        self.assertContains(respuesta, 'role="dialog" aria-modal="true"')
        self.assertContains(respuesta, 'Imagen de la historia')
        self.assertContains(respuesta, 'Una historia para probar la ficha.')
        self.assertContains(respuesta, 'data-title-cast="Actriz De prueba"')
        self.assertContains(respuesta, 'data-title-categories="Acción"')
        self.assertContains(respuesta, 'data-title-age="+13"')
        self.assertContains(respuesta, 'data-title-details-cast')
        self.assertContains(respuesta, 'data-title-details-categories')
        self.assertContains(respuesta, 'data-title-details-age')
        self.assertContains(
            respuesta,
            reverse('calificar_titulo', args=[titulo.pk]),
        )
        self.assertContains(respuesta, 'data-title-rating-star="5"')
        self.assertContains(respuesta, 'data-title-rating=""')
        self.assertNotContains(
            respuesta,
            f'data-title-average-rating="{titulo.pk}"',
        )
        self.assertNotContains(respuesta, 'Promedio de 3 de 5 estrellas')

    def test_detalle_lista_contenidos_ordenados_con_imagenes_del_idioma_preferido(self):
        ingles = Idioma.objects.create(nombre='English')
        titulo = self.crear_titulo(
            'Serie con episodios',
            self.serie,
            con_contenido=False,
        )
        segundo = Contenido.objects.create(
            nombre='Episodio dos',
            descripcion='Descripción del episodio dos.',
            seccion=1,
            orden=2,
            duracion_segundos=2700,
            titulo=titulo,
        )
        extra_cero = Contenido.objects.create(
            nombre='Escena extra',
            descripcion='Contenido extra de la sección cero.',
            seccion=0,
            orden=1,
            duracion_segundos=120,
            titulo=titulo,
        )
        extra_negativo = Contenido.objects.create(
            nombre='Avance',
            descripcion='Contenido extra de la sección negativa.',
            seccion=-1,
            orden=1,
            duracion_segundos=60,
            titulo=titulo,
        )
        primero = Contenido.objects.create(
            nombre='Episodio uno',
            descripcion='Descripción del episodio uno.',
            seccion=1,
            orden=1,
            duracion_segundos=3600,
            titulo=titulo,
        )
        final = Contenido.objects.create(
            nombre='Especial',
            descripcion='Descripción del especial.',
            seccion=2,
            orden=1,
            duracion_segundos=30,
            titulo=titulo,
        )
        IdiomaContenido.objects.create(
            contenido=primero,
            idioma=self.idioma,
            nombre='Episodio uno localizado',
            descripcion='Descripción localizada del episodio uno.',
            imagen='demo/episodios/episodio-uno-es.svg',
        )
        IdiomaContenido.objects.create(
            contenido=primero,
            idioma=ingles,
            imagen='demo/episodios/episode-one-en.svg',
        )
        IdiomaContenido.objects.create(
            contenido=segundo,
            idioma=ingles,
            imagen='demo/episodios/episode-two-en.svg',
        )
        IdiomaContenido.objects.create(
            contenido=extra_cero,
            idioma=self.idioma,
            imagen='demo/episodios/escena-extra.svg',
        )
        IdiomaContenido.objects.create(
            contenido=extra_negativo,
            idioma=self.idioma,
            imagen='demo/episodios/avance.svg',
        )
        IdiomaContenido.objects.create(
            contenido=final,
            idioma=self.idioma,
            imagen='demo/episodios/especial-es.svg',
        )
        usuario = Usuario.objects.create_user(
            username='contenido-detalle@example.com',
            email='contenido-detalle@example.com',
            password='UnaClave-larga-2026!',
            idioma=self.idioma,
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'))

        titulo_renderizado = next(
            titulo_en_lista
            for carrusel in respuesta.context['carruseles']
            for titulo_en_lista in carrusel['titulos']
            if titulo_en_lista.pk == titulo.pk
        )
        contenidos = titulo_renderizado.contenidos_detalle
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            [contenido['nombre'] for contenido in contenidos],
            [
                'Avance',
                'Escena extra',
                'Episodio uno localizado',
                'Episodio dos',
                'Especial',
            ],
        )
        self.assertEqual(
            [contenido['seccion'] for contenido in contenidos],
            [-1, 0, 1, 1, 2],
        )
        self.assertTrue(all(
            contenido['mostrar_numero_episodio']
            for contenido in contenidos
        ))
        self.assertEqual(
            [contenido['imagen'] for contenido in contenidos],
            [
                '/media/demo/episodios/avance.svg',
                '/media/demo/episodios/escena-extra.svg',
                '/media/demo/episodios/episodio-uno-es.svg',
                '/media/demo/episodios/episode-two-en.svg',
                '/media/demo/episodios/especial-es.svg',
            ],
        )
        self.assertEqual(
            [contenido['duracion'] for contenido in contenidos],
            ['1 min', '2 min', '1 h', '45 min', '30 s'],
        )
        self.assertEqual(
            contenidos[2]['descripcion'],
            'Descripción localizada del episodio uno.',
        )
        self.assertEqual(
            contenidos[3]['descripcion'],
            'Descripción del episodio dos.',
        )
        self.assertEqual(
            contenidos[3]['reproducir_url'],
            reverse('reproducir_contenido', args=[titulo.pk, segundo.pk]),
        )
        self.assertContains(respuesta, 'data-title-details-contents')
        self.assertContains(respuesta, 'data-title-contents=')
        self.assertContains(respuesta, 'item.href = content.reproducir_url')

        respuesta_busqueda = self.client.get(
            reverse('buscar_titulos'),
            {'q': 'Serie con episodios'},
        )
        self.assertEqual(respuesta_busqueda.status_code, 200)
        resultado_busqueda = respuesta_busqueda.json()['resultados'][0]
        self.assertEqual(
            [contenido['nombre'] for contenido in resultado_busqueda['contenidos']],
            [
                'Avance',
                'Escena extra',
                'Episodio uno localizado',
                'Episodio dos',
                'Especial',
            ],
        )

        self.client.post(reverse('toggle_mi_lista', args=[titulo.pk]))
        respuesta_lista = self.client.get(reverse('mi_lista'))
        self.assertEqual(respuesta_lista.status_code, 200)
        self.assertContains(respuesta_lista, 'data-title-contents=')

    def test_detalle_de_pelicula_no_agrega_numero_de_episodio(self):
        titulo = self.crear_titulo(
            'Película con contenido',
            self.pelicula,
            con_contenido=True,
        )
        usuario = Usuario.objects.create_user(
            username='pelicula-sin-episodio@example.com',
            email='pelicula-sin-episodio@example.com',
            password='UnaClave-larga-2026!',
        )
        self.autenticar_con_perfil(usuario)

        respuesta = self.client.get(reverse('home'))
        titulo_renderizado = next(
            titulo_en_lista
            for carrusel in respuesta.context['carruseles']
            for titulo_en_lista in carrusel['titulos']
            if titulo_en_lista.pk == titulo.pk
        )

        self.assertFalse(
            titulo_renderizado.contenidos_detalle[0]['mostrar_numero_episodio']
        )

    def test_puntuacion_de_titulo_se_guarda_en_incrementos_de_media_estrella(self):
        titulo = self.crear_titulo(
            'Título puntuado',
            self.pelicula,
            con_contenido=True,
            categoria=self.accion,
        )
        usuario = Usuario.objects.create_user(
            username='puntuacion-titulo@example.com',
            email='puntuacion-titulo@example.com',
            password='UnaClave-larga-2026!',
        )
        perfil = self.autenticar_con_perfil(usuario)
        url = reverse('calificar_titulo', args=[titulo.pk])
        self.assertFalse(
            PerfilTitulo.objects.filter(perfil=perfil, titulo=titulo).exists()
        )

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
        self.assertEqual(
            PerfilTitulo.objects.filter(perfil=perfil, titulo=titulo).count(),
            1,
        )

        for puntuacion in ('0', '5.5', '2.3', 'invalida'):
            with self.subTest(puntuacion=puntuacion):
                respuesta_invalida = self.client.post(
                    url,
                    {'puntuacion': puntuacion},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                    HTTP_ACCEPT='application/json',
                )
                self.assertEqual(respuesta_invalida.status_code, 400)

        for puntuacion, porcentaje in (('0.5', 10), ('5', 100)):
            with self.subTest(puntuacion=puntuacion):
                respuesta_valida = self.client.post(url, {'puntuacion': puntuacion})
                self.assertEqual(respuesta_valida.status_code, 200)
                perfil_titulo.refresh_from_db()
                self.assertEqual(
                    perfil_titulo.calificacion.porcentaje_gusto,
                    porcentaje,
                )
                self.assertEqual(
                    PerfilTitulo.objects.filter(perfil=perfil, titulo=titulo).count(),
                    1,
                )

        respuesta_45 = self.client.post(url, {'puntuacion': '4.5'})
        self.assertEqual(respuesta_45.status_code, 200)
        perfil_titulo.refresh_from_db()
        self.assertEqual(perfil_titulo.calificacion.estrellas, Decimal('4.5'))
        respuesta_inicio = self.client.get(reverse('home'))
        self.assertContains(respuesta_inicio, 'data-title-rating="4.5"')
        self.assertContains(respuesta_inicio, 'data-title-average-percent="90.0"')
        self.assertIn('no-store', respuesta_inicio['Cache-Control'])

        cliente_reiniciado = self.client_class()
        cliente_reiniciado.force_login(usuario)
        session = cliente_reiniciado.session
        session['perfil_activo_id'] = perfil.pk
        session.save()
        respuesta_reinicio = cliente_reiniciado.get(reverse('home'))
        self.assertContains(respuesta_reinicio, 'data-title-rating="4.5"')
        apariciones_titulo = [
            titulo_mostrado
            for carrusel in respuesta_reinicio.context['carruseles']
            for titulo_mostrado in carrusel['titulos']
            if titulo_mostrado.pk == titulo.pk
        ]
        self.assertGreaterEqual(len(apariciones_titulo), 2)
        self.assertTrue(all(
            titulo_mostrado.puntuacion_estrellas == Decimal('4.5')
            and titulo_mostrado.porcentaje_promedio == Decimal('90.0')
            for titulo_mostrado in apariciones_titulo
        ))

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
        self.assertEqual(titulos[redondea_arriba.pk].porcentaje_promedio, Decimal('70.0'))
        self.assertEqual(titulos[redondea_abajo.pk].porcentaje_promedio, Decimal('65.0'))
        self.assertContains(respuesta, '70%')
        self.assertContains(respuesta, '65%')
        self.assertContains(respuesta, 'data-title-rating="4.0"')
        self.assertContains(respuesta, 'data-title-rating="3.5"')

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
            descripcion='A documentary about the northern lights.',
        )
        contenido_localizado = localizado.contenidos.get()
        IdiomaContenido.objects.create(
            contenido=contenido_localizado,
            idioma=ingles,
            nombre='Northern Lights Feature',
            descripcion='A closer look at the lights in the sky.',
        )
        sin_traduccion = self.crear_titulo(
            'Northern Stories',
            self.serie,
            con_contenido=True,
            categoria=self.accion,
            edad_minima=13,
        )
        sin_traduccion.descripcion_original = 'Una descripción para la búsqueda.'
        sin_traduccion.save(update_fields=['descripcion_original'])
        persona = Elenco.objects.create(
            pais=self.pais,
            nombre='Actor',
            apellido='De prueba',
        )
        rol = Rol.objects.create(nombre='Actor')
        rol_elenco = RolElenco.objects.create(rol=rol, elenco=persona)
        TituloRolElenco.objects.create(titulo=sin_traduccion, rol_elenco=rol_elenco)
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
        self.assertEqual(
            resultado_guardado['descripcion'],
            'A documentary about the northern lights.',
        )
        self.assertEqual(
            resultado_guardado['contenidos'][0]['nombre'],
            'Northern Lights Feature',
        )
        self.assertEqual(
            resultado_guardado['contenidos'][0]['descripcion'],
            'A closer look at the lights in the sky.',
        )
        self.assertTrue(resultado_guardado['en_mi_lista'])
        self.assertFalse(resultado_disponible['en_mi_lista'])
        self.assertEqual(resultado_disponible['puntuacion_perfil'], '')
        self.assertIsNone(resultado_disponible['porcentaje_promedio'])
        self.assertEqual(resultado_disponible['descripcion'], 'Una descripción para la búsqueda.')
        self.assertEqual(resultado_disponible['elenco'], 'Actor De prueba')
        self.assertEqual(resultado_disponible['categorias'], 'Acción')
        self.assertEqual(resultado_disponible['edad'], '+13')
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
        self.assertNotContains(respuesta, 'class="title-poster-play-link"')
        self.assertNotContains(respuesta, 'class="featured-banner-play-link"')
        self.assertNotContains(
            respuesta,
            reverse('reproducir_titulo', args=[primer_titulo.pk]),
        )
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
        self.assertContains(respuesta, 'class="featured-banner-play-link"')
        self.assertContains(
            respuesta,
            f'href="{reverse("reproducir_titulo", args=[reciente.pk])}"',
        )
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
        self.assertFalse(
            PerfilTitulo.objects.filter(perfil=perfil, titulo=titulo).exists()
        )

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
        titulo_ingles = IdiomaTitulo.objects.get(
            titulo=ruta_demo,
            idioma__nombre='Inglés',
        )
        self.assertEqual(titulo_ingles.nombre, 'Test Route')
        self.assertIn('fictional movie', titulo_ingles.descripcion)
        contenido_ingles = IdiomaContenido.objects.get(
            contenido__titulo=ruta_demo,
            contenido__seccion=1,
            idioma__nombre='Inglés',
        )
        self.assertEqual(contenido_ingles.nombre, 'Test Route - Main Feature')
        self.assertIn('demonstration content', contenido_ingles.descripcion)
        self.assertTrue(Imagen.objects.filter(nombre='Avatar Dorado').exists())
        self.assertTrue(
            IdiomaTitulo.objects.filter(imagen__startswith='demo/banners/').exists()
        )

        conteos_primera_carga = {
            modelo: modelo.objects.count()
            for modelo in (
                Categoria,
                Contenido,
                Imagen,
                IdiomaTitulo,
                IdiomaContenido,
                Titulo,
                Suscripcion,
            )
        }
        call_command('cargar_datos_demo', stdout=StringIO())
        conteos_segunda_carga = {
            modelo: modelo.objects.count()
            for modelo in (
                Categoria,
                Contenido,
                Imagen,
                IdiomaTitulo,
                IdiomaContenido,
                Titulo,
                Suscripcion,
            )
        }

        self.assertEqual(conteos_segunda_carga, conteos_primera_carga)

    @override_settings(DEBUG=True)
    def test_completar_cobros_demo_cubre_todas_las_cuentas_y_es_idempotente(self):
        plan = Plan.objects.create(
            nombre='Plan ya existente',
            cantidad_pantallas_simultaneas=1,
        )
        usuario_con_suscripcion = Usuario.objects.create_user(
            username='con-suscripcion@example.test',
            email='con-suscripcion@example.test',
            password='UnaClave-larga-2026!',
        )
        Suscripcion.objects.create(
            usuario=usuario_con_suscripcion,
            plan=plan,
            fecha_inscripcion=date(2026, 1, 1),
            fecha_vigencia=date(2026, 12, 1),
        )
        usuario_sin_suscripcion = Usuario.objects.create_user(
            username='sin-suscripcion@example.test',
            email='sin-suscripcion@example.test',
            password='UnaClave-larga-2026!',
        )
        salida = StringIO()

        call_command('completar_cobros_demo', stdout=salida)

        self.assertEqual(Suscripcion.objects.filter(
            usuario=usuario_con_suscripcion,
        ).count(), 1)
        self.assertEqual(Suscripcion.objects.filter(
            usuario=usuario_sin_suscripcion,
        ).count(), 1)
        self.assertEqual(Cobro.objects.filter(
            suscripcion__usuario__in=[
                usuario_con_suscripcion,
                usuario_sin_suscripcion,
            ],
        ).count(), 2)
        cobro_demo = Cobro.objects.get(
            suscripcion__usuario=usuario_sin_suscripcion,
        )
        self.assertEqual(cobro_demo.tarjeta.numero, '0000')
        self.assertEqual(cobro_demo.tarjeta.marca_tarjeta.nombre, 'Tarjeta Demo')
        self.assertEqual(cobro_demo.tarjeta.metodo_pago.nombre, 'Pago de prueba')
        self.assertEqual(cobro_demo.estado_cobro.nombre, 'Aprobado')

        call_command('completar_cobros_demo', stdout=StringIO())

        self.assertEqual(Cobro.objects.filter(
            suscripcion__usuario__in=[
                usuario_con_suscripcion,
                usuario_sin_suscripcion,
            ],
        ).count(), 2)

    @override_settings(DEBUG=False)
    def test_completar_cobros_demo_se_rechaza_fuera_de_debug(self):
        usuario = Usuario.objects.create_user(
            username='cuenta@example.test',
            email='cuenta@example.test',
            password='UnaClave-larga-2026!',
        )

        with self.assertRaisesMessage(
            CommandError,
            'solo puede ejecutarse con DEBUG activado',
        ):
            call_command('completar_cobros_demo', stdout=StringIO())

        self.assertFalse(Suscripcion.objects.filter(usuario=usuario).exists())
        self.assertFalse(Cobro.objects.filter(suscripcion__usuario=usuario).exists())
