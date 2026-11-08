from streaming.models import *
from datetime import date, timedelta
from django.utils import timezone
import random

hoy = date.today()
ahora = timezone.now()

"""
SCRIPT PARA GENERAR DATOS 'MOCK' PARA TESTING
CORRER CON ' python manage.py shell '
Y DENTRO DE LA SHELL ' exec(open('mock.py', encoding='utf-8').read()) ' 
"""
# ---------- CATÁLOGOS ----------
pa = {n: Pais.objects.create(nombre=n) for n in ["Argentina", "Estados Unidos", "España", "México", "Japón", "Corea del Sur"]}
idi = {n: Idioma.objects.create(nombre=n, descripcion=f"Idioma {n}") for n in ["Español", "Inglés", "Japonés", "Coreano"]}
tt = {n: TipoTitulo.objects.create(nombre=n, descripcion=f"Tipo: {n}") for n in ["Película", "Serie", "Documental"]}
cat = {n: Categoria.objects.create(nombre=n, descripcion=f"Categoría {n}") for n in ["Drama", "Comedia", "Acción", "Ciencia ficción", "Terror", "Documental"]}
rol = {n: Rol.objects.create(nombre=n, descripcion=f"Rol de {n}") for n in ["Actor", "Actriz", "Director", "Guionista"]}
cal = {n: Calidad.objects.create(nombre=n, descripcion=f"Resolución {n}") for n in ["SD", "HD", "Full HD", "4K"]}
calif = {n: Calificacion.objects.create(nombre=n, porcentaje_gusto=p) for n, p in [("No me gusta", 0.0), ("Me gusta", 75.0), ("Me encanta", 100.0)]}
marcas = {n: MarcaTarjeta.objects.create(nombre=n, numero_asignado=i, descripcion=f"Tarjetas {n}") for i, n in enumerate(["Visa", "Mastercard", "American Express"], start=1)}
metodos = {n: MetodoPago.objects.create(nombre=n, descripcion=f"Pago con {n}") for n in ["Crédito", "Débito"]}
estados = {n: EstadoCobro.objects.create(nombre=n, descripcion=f"Cobro {n.lower()}") for n in ["Pagado", "Pendiente", "Rechazado"]}

# ---------- ELENCO ----------
elencos = [Elenco.objects.create(pais=pa[p], nombre=n, apellido=a, fecha_nacimiento=date(y, 3, 12), descripcion=f"Biografía de {n} {a}") for n, a, p, y in [
    ("Martín", "Salazar", "Argentina", 1978), ("Lucía", "Ferreyra", "Argentina", 1985),
    ("James", "Holloway", "Estados Unidos", 1970), ("Emily", "Carter", "Estados Unidos", 1990),
    ("Carmen", "Ibáñez", "España", 1982), ("Diego", "Ramírez", "México", 1975),
    ("Haruto", "Tanaka", "Japón", 1968), ("Min-jun", "Park", "Corea del Sur", 1988)]]
roles_elenco = [RolElenco.objects.create(rol=rol[r], elenco=e) for e, r in zip(elencos, ["Actor", "Actriz", "Director", "Actriz", "Actriz", "Actor", "Director", "Actor"])]
roles_elenco += [RolElenco.objects.create(rol=rol["Guionista"], elenco=elencos[i]) for i in (0, 2, 6)]  # algunos con 2 roles

# ---------- TÍTULOS ----------
titulos = [Titulo.objects.create(nombre_original=n, descripcion_original=d, tipo_titulo=tt[t], pais=pa[p], fecha_estreno=date(y, 1, 15)) for n, d, t, p, y in [
    ("Sombras del Sur", "Una familia esconde un secreto en la Patagonia.", "Serie", "Argentina", 2022),
    ("Code Zero", "Un equipo de hackers intenta evitar un apagón global.", "Serie", "Estados Unidos", 2023),
    ("Neon Samurai", "Un ronin recorre una Tokio futurista.", "Serie", "Japón", 2021),
    ("La Última Función", "Un cine de barrio lucha por no cerrar.", "Película", "España", 2020),
    ("Punto de Fuga", "Persecución a contrarreloj por Ciudad de México.", "Película", "México", 2024),
    ("Océanos Invisibles", "Un recorrido por el fondo marino.", "Documental", "Estados Unidos", 2019)]]
fechas_baja = Titulo.objects.filter(nombre_original="La Última Función").update(fecha_baja=hoy + timedelta(days=60))
for t, cats in zip(titulos, [["Drama"], ["Acción", "Ciencia ficción"], ["Acción", "Ciencia ficción"], ["Drama", "Comedia"], ["Acción"], ["Documental"]]): [TituloCategoria.objects.create(titulo=t, categoria=cat[c]) for c in cats]
for t in titulos: [TituloRolElenco.objects.create(titulo=t, rol_elenco=re) for re in roles_elenco[:3]]
for t, n in zip(titulos, ["Shadows of the South", "Code Zero", "Neon Samurai", "The Last Show", "Vanishing Point", "Invisible Oceans"]): IdiomaTitulo.objects.create(titulo=t, idioma=idi["Inglés"], nombre=n, descripcion=f"English title: {n}")
imgs_titulo = [Imagen.objects.create(nombre=f"Portada {t.nombre_original}", imagen=f"portadas/{t.id}.jpg", titulo=t) for t in titulos]

# ---------- CONTENIDO (series: 2 temporadas x 3 episodios; resto: 1 contenido) ----------
contenidos = [Contenido.objects.create(nombre=f"{t.nombre_original} - T{s}E{e}", descripcion=f"Episodio {e} de la temporada {s}", seccion=s, orden=e, titulo=t) for t in titulos[:3] for s in (1, 2) for e in (1, 2, 3)]
contenidos += [Contenido.objects.create(nombre=t.nombre_original, descripcion="Contenido completo", seccion=1, orden=1, titulo=t) for t in titulos[3:]]
idiomas_contenido = [IdiomaContenido.objects.create(idioma=idi[i], contenido=c) for c in contenidos for i in ("Español", "Inglés")]
for ic in idiomas_contenido: [CalidadIdiomaContenido.objects.create(idioma_contenido=ic, calidad=cal[q], archivo=b"\x00FAKE_VIDEO_BYTES") for q in ("HD", "Full HD")]
for c in contenidos: [Subtitulo.objects.create(contenido=c, idioma=idi[i], archivo_vtt=f"WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nSubtítulo de prueba ({i})".encode()) for i in ("Español", "Inglés")]

# ---------- PLANES ----------
planes = {n: Plan.objects.create(nombre=n, descripcion=f"Plan {n}", cantidad_pantallas_simultaneas=p) for n, p in [("Básico", 1), ("Estándar", 2), ("Premium", 4)]}
for n, qs in {"Básico": ["SD", "HD"], "Estándar": ["HD", "Full HD"], "Premium": ["HD", "Full HD", "4K"]}.items(): [PlanCalidad.objects.create(plan=planes[n], calidad=cal[q]) for q in qs]
for n, p in [("Básico", 3500.0), ("Estándar", 5500.0), ("Premium", 8000.0)]:
    Precio.objects.create(plan=planes[n], precio=p * 0.8, fecha_inicio=hoy - timedelta(days=365), fecha_fin=hoy - timedelta(days=1))  # precio histórico
    Precio.objects.create(plan=planes[n], precio=p, fecha_inicio=hoy)  # precio vigente

# ---------- USUARIOS, PERFILES, DISPOSITIVOS ----------
usuarios = [Usuario.objects.create_user(username=u, email=f"{u}@mail.com", password="test1234", first_name=u.capitalize(), telefono=tel, pais=pa[p], idioma=idi[i]) for u, tel, p, i in [
    ("juan", "+5493514000001", "Argentina", "Español"), ("maria", "+5493514000002", "Argentina", "Español"),
    ("john", "+12025550143", "Estados Unidos", "Inglés"), ("carla", "+34600000001", "España", "Español")]]
tp = {n: TipoPerfil.objects.create(nombre=n, edad_max=e) for n, e in [("Infantil", 12), ("Adolescente", 16), ("Adulto", 100)]}
avatares = [Imagen.objects.create(nombre=f"Avatar {i}", imagen=f"avatares/{i}.png", titulo=titulos[i % len(titulos)]) for i in range(1, 9)]
perfiles = []
for i, u in enumerate(usuarios): perfiles += [Perfil.objects.create(nombre=f"{u.first_name}", imagen=avatares[i], tipo_perfil=tp["Adulto"], usuario=u), Perfil.objects.create(nombre=f"Kids de {u.first_name}", imagen=avatares[i + 4], tipo_perfil=tp["Infantil"], usuario=u)]
for i, u in enumerate(usuarios): [Registro.objects.create(token_disp=f"tok-{u.username}-{n}", os=o, ultima_conexion_fecha=hoy, ultima_conexion_hora=ahora.time(), estado=(n == 1), usuario=u) for n, o in enumerate(["Android", "iOS", "Windows"], start=1)]

# ---------- HISTORIAL / RECOMENDACIONES ----------
perfiles_titulos = [PerfilTitulo.objects.create(perfil=p, titulo=titulos[(i + j) % len(titulos)], calificacion=list(calif.values())[(i + j) % 3] if j < 2 else None) for i, p in enumerate(perfiles) for j in range(3)]
for pt in perfiles_titulos[::2]: Porver.objects.create(perfil_titulo=pt, fecha_agregado=hoy - timedelta(days=5))
for pt in perfiles_titulos[1::5]: Porver.objects.create(perfil_titulo=pt, fecha_agregado=hoy - timedelta(days=20), fecha_eliminado=hoy - timedelta(days=2))
for i, p in enumerate(perfiles): [PerfilContenido.objects.create(perfil=p, contenido=contenidos[(i * 2 + j) % len(contenidos)], segundos_vistos=300 * (j + 1), ultima_visualizacion=ahora - timedelta(days=j)) for j in range(3)]

# ---------- CATÁLOGOS ----------
visa, _ = MarcaTarjeta.objects.get_or_create(nombre="Visa", defaults={"numero_asignado": 1, "descripcion": "Tarjetas Visa"})
master, _ = MarcaTarjeta.objects.get_or_create(nombre="Mastercard", defaults={"numero_asignado": 2, "descripcion": "Tarjetas Mastercard"})
amex, _ = MarcaTarjeta.objects.get_or_create(nombre="American Express", defaults={"numero_asignado": 3, "descripcion": "Tarjetas American Express"})
credito, _ = MetodoPago.objects.get_or_create(nombre="Crédito", defaults={"descripcion": "Pago con Crédito"})
debito, _ = MetodoPago.objects.get_or_create(nombre="Débito", defaults={"descripcion": "Pago con Débito"})
pagado, _ = EstadoCobro.objects.get_or_create(nombre="Pagado", defaults={"descripcion": "Cobro pagado"})
rechazado, _ = EstadoCobro.objects.get_or_create(nombre="Rechazado", defaults={"descripcion": "Cobro rechazado"})

# ---------- PLANES Y PRECIOS ----------
planes = {}
for nombre, pantallas, precio in [("Básico", 1, 3500.0), ("Estándar", 2, 5500.0), ("Premium", 4, 8000.0)]:
    plan, _ = Plan.objects.get_or_create(nombre=nombre, defaults={"descripcion": f"Plan {nombre}", "cantidad_pantallas_simultaneas": pantallas})
    Precio.objects.get_or_create(plan=plan, fecha_fin=None, defaults={"precio": precio, "fecha_inicio": hoy})
    planes[nombre] = plan

# ---------- USUARIOS ----------
arg, _ = Pais.objects.get_or_create(nombre="Argentina")
esp, _ = Pais.objects.get_or_create(nombre="España")
eeuu, _ = Pais.objects.get_or_create(nombre="Estados Unidos")
es, _ = Idioma.objects.get_or_create(nombre="Español", defaults={"descripcion": "Idioma Español"})
en, _ = Idioma.objects.get_or_create(nombre="Inglés", defaults={"descripcion": "Idioma Inglés"})

usuarios = []
for username, tel, pais, idioma in [("juan", "+5493514000001", arg, es), ("maria", "+5493514000002", arg, es),
                                    ("john", "+12025550143", eeuu, en), ("carla", "+34600000001", esp, es)]:
    u = Usuario.objects.filter(username=username).first() or Usuario.objects.create_user(
        username=username, email=f"{username}@mail.com", password="test1234",
        first_name=username.capitalize(), telefono=tel, pais=pais, idioma=idioma)
    usuarios.append(u)

# ---------- TARJETAS ----------
tarjetas = [
    Tarjeta.objects.create(numero="1111", fecha_vencimiento=date(2029, 12, 31), marca_tarjeta=visa, metodo_pago=credito),
    Tarjeta.objects.create(numero="4444", fecha_vencimiento=date(2028, 6, 30), marca_tarjeta=master, metodo_pago=debito),
    Tarjeta.objects.create(numero="0005", fecha_vencimiento=date(2030, 3, 31), marca_tarjeta=amex, metodo_pago=credito),
    Tarjeta.objects.create(numero="5556", fecha_vencimiento=date(2027, 9, 30), marca_tarjeta=visa, metodo_pago=debito),
    Tarjeta.objects.create(numero="9012", fecha_vencimiento=date(2025, 1, 31), marca_tarjeta=master, metodo_pago=credito, habilitado=False),  # vencida y deshabilitada
]

# ---------- SUSCRIPCIONES ----------
suscripciones = [Suscripcion.objects.create(usuario=u, plan=planes[p], tarjeta=t,
                                            fecha_inscripcion=hoy - timedelta(days=90), fecha_vigencia=hoy + timedelta(days=30))
                 for u, p, t in zip(usuarios, ["Básico", "Estándar", "Premium", "Estándar"], tarjetas)]
suscripciones[3].fecha_cancelacion = hoy - timedelta(days=3)
suscripciones[3].habilitado = False
suscripciones[3].save()

# ---------- COBROS (cada suscripción con su tarjeta; 3 meses de historial) ----------
n = 1000
for i, (s, t) in enumerate(zip(suscripciones, tarjetas)):
    monto = Precio.objects.get(plan=s.plan, fecha_fin__isnull=True).precio
    for meses in (2, 1, 0):
        n += 1
        fallo = (i == 2 and meses == 0)  # un cobro rechazado de ejemplo
        Cobro.objects.create(
            suscripcion=s, fecha_cobro=hoy - timedelta(days=30 * meses),
            estado_cobro=rechazado if fallo else pagado, tarjeta=t,
            numero_autorizacion=None if fallo else f"AUTH{n}", monto=monto)

# Un usuario que cambió de tarjeta: el último cobro de "juan" lo hace con otra (historial)
c = Cobro.objects.filter(suscripcion=suscripciones[0]).order_by("-fecha_cobro").first()
c.tarjeta = tarjetas[3]; c.save()
