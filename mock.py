from streaming.models import *
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw

hoy = date.today()
ahora = timezone.now()

"""
SCRIPT PARA GENERAR DATOS 'MOCK' PARA TESTING
CORRER CON ' python manage.py shell '
Y DENTRO DE LA SHELL ' 
exec(open('mock.py', encoding='utf-8').read()) 
' 
"""

# La base tiene que estar vacia (para repetirlo: borrar la db y volver a migrar)
if Pais.objects.exists() or Usuario.objects.exists():
    raise RuntimeError("La base ya tiene datos, el mock esta pensado para una base vacia.\nPara vaciar la DB, correr:\nmanage.py flush")

# ---------- ARCHIVOS DE APOYO ----------
COLORES = ["#c0392b", "#8e44ad", "#2980b9", "#16a085", "#d35400", "#2c3e50", "#27ae60", "#7f8c8d"]


def png(texto, color, nombre, size=(400, 600)):
    """Genera una imagen PNG de color con texto, lista para asignar a un ImageField."""
    img = Image.new("RGB", size, color)
    ImageDraw.Draw(img).text((20, 20), texto, fill="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return ContentFile(buf.getvalue(), name=nombre)


MEDIA = Path(settings.MEDIA_ROOT)

VTT = {
    "Español": "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHola, este es un subtítulo de prueba.\n\n00:00:05.000 --> 00:00:08.000\nSegunda línea de subtítulo.\n",
    "Inglés": "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello, this is a test subtitle.\n\n00:00:05.000 --> 00:00:08.000\nSecond subtitle line.\n",
}


def ruta_subtitulo(contenido, idioma):
    return f"subtitulo/titulo{contenido.titulo_id}/contenido{contenido.id}/{slugify(idioma.nombre)}.vtt"


def ruta_video(contenido, idioma, calidad):
    return f"video/titulo{contenido.titulo_id}/contenido{contenido.id}/{slugify(idioma.nombre)}/{slugify(calidad.nombre)}.mp4"


def escribir_texto(ruta, texto):
    destino = MEDIA / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")

# ---------- CATÁLOGOS ----------
pa = {n: Pais.objects.create(nombre=n) for n in ["Argentina", "Estados Unidos", "España", "México", "Japón", "Corea del Sur"]}
idi = {n: Idioma.objects.create(nombre=n, descripcion=f"Idioma {n}") for n in ["Español", "Inglés", "Japonés", "Coreano"]}
tt = {n: TipoTitulo.objects.create(nombre=n, descripcion=f"Tipo: {n}") for n in ["Película", "Serie", "Documental"]}
cat = {n: Categoria.objects.create(nombre=n, descripcion=f"Categoría {n}") for n in ["Drama", "Comedia", "Acción", "Ciencia ficción", "Terror", "Documental"]}
rol = {n: Rol.objects.create(nombre=n, descripcion=f"Rol de {n}") for n in ["Actor", "Actriz", "Director", "Guionista"]}
cal = {n: Calidad.objects.create(nombre=n, descripcion=f"Resolución {n}") for n in ["SD", "HD", "Full HD", "4K"]}
calif = {n: Calificacion.objects.create(nombre=n, porcentaje_gusto=p, estrellas=e) for n, p, e in [("No me gusta", 0.0, 1.0), ("Me gusta", 75.0, 4.0), ("Me encanta", 100.0, 5.0)]}
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
roles_elenco += [RolElenco.objects.create(rol=rol["Guionista"], elenco=elencos[i]) for i in (0, 2, 6)]

# ---------- IMÁGENES DE CARÁTULA Y AVATARES ----------
imagenes_titulos = [
    Imagen.objects.create(
        nombre=f"Poster {i}",
        imagen=png(f"Poster {i}", COLORES[i % len(COLORES)], f"poster_{i}.png", (400, 600))
    )
    for i in range(1, 7)
]

avatares = [
    Imagen.objects.create(
        nombre=f"Avatar {i}",
        imagen=png(f"Avatar {i}", COLORES[(i + 2) % len(COLORES)], f"avatar_{i}.png", (200, 200))
    )
    for i in range(1, 9)
]

# ---------- TÍTULOS ----------
datos_titulos = [
    ("Sombras del Sur", "Una familia esconde un secreto en la Patagonia.", "Serie", "Argentina", 2022, 13),
    ("Code Zero", "Un equipo de hackers intenta evitar un apagón global.", "Serie", "Estados Unidos", 2023, 16),
    ("Neon Samurai", "Un ronin recorre una Tokio futurista.", "Serie", "Japón", 2021, 13),
    ("La Última Función", "Un cine de barrio lucha por no cerrar.", "Película", "España", 2020, 0),
    ("Punto de Fuga", "Persecución a contrarreloj por Ciudad de México.", "Película", "México", 2024, 16),
    ("Océanos Invisibles", "Un recorrido por el fondo marino.", "Documental", "Estados Unidos", 2019, 0)
]

titulos = []
for idx, (n, d, t, p, y, ed) in enumerate(datos_titulos):
    titulos.append(
        Titulo.objects.create(
            nombre_original=n,
            descripcion_original=d,
            tipo_titulo=tt[t],
            pais=pa[p],
            fecha_estreno=date(y, 1, 15),
            edad_minima=ed
        )
    )

for t, cats in zip(titulos, [["Drama"], ["Acción", "Ciencia ficción"], ["Acción", "Ciencia ficción"], ["Drama", "Comedia"], ["Acción"], ["Documental"]]):
    for c in cats:
        TituloCategoria.objects.create(titulo=t, categoria=cat[c])

for t in titulos:
    for rel in roles_elenco[:3]:
        TituloRolElenco.objects.create(titulo=t, rol_elenco=rel)

nombres_en = ["Shadows of the South", "Code Zero", "Neon Samurai", "The Last Show", "Vanishing Point", "Invisible Oceans"]
for idx, (t, n_en) in enumerate(zip(titulos, nombres_en)):
    img_t = imagenes_titulos[idx]
    # IdiomaTítulo en Español
    IdiomaTitulo.objects.create(
        titulo=t,
        idioma=idi["Español"],
        nombre=t.nombre_original,
        descripcion=t.descripcion_original,
        imagen=img_t.imagen
    )
    # IdiomaTítulo en Inglés
    IdiomaTitulo.objects.create(
        titulo=t,
        idioma=idi["Inglés"],
        nombre=n_en,
        descripcion=f"English title: {n_en}",
        imagen=img_t.imagen
    )

# ---------- CONTENIDO ----------
contenidos = [
    Contenido.objects.create(
        nombre=f"{t.nombre_original} - T{s}E{e}",
        descripcion=f"Episodio {e} de la temporada {s}",
        seccion=s,
        orden=e,
        titulo=t,
        duracion_segundos=2700
    )
    for t in titulos[:3] for s in (1, 2) for e in (1, 2, 3)
]
contenidos += [
    Contenido.objects.create(
        nombre=t.nombre_original,
        descripcion="Contenido completo",
        seccion=0,
        orden=0,
        titulo=t,
        duracion_segundos=5400
    )
    for t in titulos[3:]
]

idiomas_contenido = []
for c in contenidos:
    for i in ("Español", "Inglés"):
        img_obj = imagenes_titulos[titulos.index(c.titulo)]
        ic = IdiomaContenido.objects.create(
            idioma=idi[i],
            contenido=c,
            nombre=c.nombre,
            descripcion=c.descripcion,
            # Le pasamos el campo File/Image (img_obj.imagen) y no la instancia del modelo Imagen:
            imagen=img_obj.imagen if hasattr(img_obj, 'imagen') else img_obj
        )
        idiomas_contenido.append(ic)

rutas_video = []
for ic in idiomas_contenido:
    for q in ("HD", "Full HD"):
        ruta = ruta_video(ic.contenido, ic.idioma, cal[q])
        CalidadIdiomaContenido.objects.create(idioma_contenido=ic, calidad=cal[q], archivo=ruta)
        rutas_video.append(ruta)

for c in contenidos:
    for i in ("Español", "Inglés"):
        ruta = ruta_subtitulo(c, idi[i])
        Subtitulo.objects.create(contenido=c, idioma=idi[i], archivo_vtt=ruta)
        escribir_texto(ruta, VTT[i])

# ---------- PLANES Y PRECIOS ----------
planes = {n: Plan.objects.create(nombre=n, descripcion=f"Plan {n}", cantidad_pantallas_simultaneas=p) for n, p in [("Básico", 1), ("Estándar", 2), ("Premium", 4)]}
for n, qs in {"Básico": ["SD", "HD"], "Estándar": ["HD", "Full HD"], "Premium": ["HD", "Full HD", "4K"]}.items():
    for q in qs:
        PlanCalidad.objects.create(plan=planes[n], calidad=cal[q])

for n, p in [("Básico", 3500.0), ("Estándar", 5500.0), ("Premium", 8000.0)]:
    Precio.objects.create(plan=planes[n], precio=p * 0.8, fecha_inicio=hoy - timedelta(days=365), fecha_fin=hoy - timedelta(days=1))
    Precio.objects.create(plan=planes[n], precio=p, fecha_inicio=hoy)

# ---------- USUARIOS, PERFILES, DISPOSITIVOS ----------
usuarios = [
    Usuario.objects.create_user(
        username=u,
        email=f"{u}@mail.com",
        password="test1234",
        first_name=u.capitalize(),
        telefono=tel,
        pais=pa[p],
        idioma=idi[i]
    )
    for u, tel, p, i in [
        ("juan", "+5493514000001", "Argentina", "Español"),
        ("maria", "+5493514000002", "Argentina", "Español"),
        ("john", "+12025550143", "Estados Unidos", "Inglés"),
        ("carla", "+34600000001", "España", "Español")
    ]
]

tp = {n: TipoPerfil.objects.create(nombre=n, edad_max=e) for n, e in [("Infantil", 12), ("Adolescente", 16), ("Adulto", 100)]}

perfiles = []
for i, u in enumerate(usuarios):
    perfiles += [
        Perfil.objects.create(nombre=u.first_name, imagen=avatares[i], tipo_perfil=tp["Adulto"], usuario=u, activo=True),
        Perfil.objects.create(nombre=f"Kids de {u.first_name}", imagen=avatares[i + 4], tipo_perfil=tp["Infantil"], usuario=u, activo=True)
    ]

for u in usuarios:
    for n, o in enumerate(["Android", "iOS", "Windows"], start=1):
        Registro.objects.create(token_disp=f"tok-{u.username}-{n}", os=o, ultima_conexion_fecha=hoy, ultima_conexion_hora=ahora.time(), estado=(n == 1), usuario=u)

# ---------- HISTORIAL Y RECOMENDACIONES ----------
perfiles_titulos = [
    PerfilTitulo.objects.create(
        perfil=p,
        titulo=titulos[(i + j) % len(titulos)],
        calificacion=list(calif.values())[(i + j) % 3] if j < 2 else None
    )
    for i, p in enumerate(perfiles) for j in range(3)
]

for pt in perfiles_titulos[::2]:
    Porver.objects.create(perfil_titulo=pt, fecha_agregado=hoy - timedelta(days=5))

for pt in perfiles_titulos[1::5]:
    Porver.objects.create(perfil_titulo=pt, fecha_agregado=hoy - timedelta(days=20), fecha_eliminado=hoy - timedelta(days=2))

for i, p in enumerate(perfiles):
    for j in range(3):
        PerfilContenido.objects.create(
            perfil=p,
            contenido=contenidos[(i * 2 + j) % len(contenidos)],
            segundos_vistos=300 * (j + 1),
            ultima_visualizacion=ahora - timedelta(days=j)
        )

# ---------- TARJETAS ----------
tarjetas = [
    Tarjeta.objects.create(numero="1111", fecha_vencimiento=date(2029, 12, 31), marca_tarjeta=marcas["Visa"], metodo_pago=metodos["Crédito"]),
    Tarjeta.objects.create(numero="4444", fecha_vencimiento=date(2028, 6, 30), marca_tarjeta=marcas["Mastercard"], metodo_pago=metodos["Débito"]),
    Tarjeta.objects.create(numero="0005", fecha_vencimiento=date(2030, 3, 31), marca_tarjeta=marcas["American Express"], metodo_pago=metodos["Crédito"]),
    Tarjeta.objects.create(numero="5556", fecha_vencimiento=date(2027, 9, 30), marca_tarjeta=marcas["Visa"], metodo_pago=metodos["Débito"]),
]

tarjeta_vieja = Tarjeta.objects.create(
    numero="9012",
    fecha_vencimiento=hoy.replace(day=1) - timedelta(days=1),
    marca_tarjeta=marcas["Mastercard"],
    metodo_pago=metodos["Crédito"],
    habilitado=False
)

# ---------- SUSCRIPCIONES Y COBROS ----------
suscripciones = [
    Suscripcion.objects.create(
        usuario=u,
        plan=planes[p],
        tarjeta=t,
        fecha_inscripcion=hoy - timedelta(days=90),
        fecha_vigencia=hoy + timedelta(days=30)
    )
    for u, p, t in zip(usuarios, ["Básico", "Estándar", "Premium", "Estándar"], tarjetas)
]
suscripciones[3].fecha_cancelacion = hoy - timedelta(days=3)
suscripciones[3].habilitado = False
suscripciones[3].save()

n = 1000
for i, (s, t) in enumerate(zip(suscripciones, tarjetas)):
    monto = Precio.objects.get(plan=s.plan, fecha_fin__isnull=True).precio
    for meses in (2, 1, 0):
        n += 1
        fallo = (i == 2 and meses == 0)
        tarjeta_cobro = tarjeta_vieja if (i == 0 and meses > 0) else t
        Cobro.objects.create(
            num_factura=n,
            suscripcion=s,
            fecha_cobro=hoy - timedelta(days=30 * meses),
            estado_cobro=estados["Rechazado"] if fallo else estados["Pagado"],
            tarjeta=tarjeta_cobro,
            numero_autorizacion=None if fallo else f"AUTH{n}",
            monto=monto
        )

# ---------- USUARIO ADMINISTRADOR ----------
admin_user = Usuario.objects.create_superuser(
    username="admin",
    email="admin@stream.com",
    password="admin123",
    first_name="Administrador",
    pais=pa["Argentina"],
    idioma=idi["Español"]
)

Perfil.objects.create(
    nombre="Admin Main",
    imagen=avatares[0],
    tipo_perfil=tp["Adulto"],
    usuario=admin_user,
    activo=True
)

print("Mock cargado correctamente. Usuarios: juan, maria, john, carla (password: test1234) y admin (password: admin123).")