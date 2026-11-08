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


# Rutas dentro de MEDIA_ROOT (los nombres de idioma y calidad van en slug: "Español" -> espanol, "Full HD" -> full-hd):
#   subtitulo/titulo{id}/contenido{id}/{idioma}.vtt
#   video/titulo{id}/contenido{id}/{idioma}/{calidad}.mp4
MEDIA = Path(settings.MEDIA_ROOT)

# Los videos NO los crea el mock: se copian a mano en la ruta del primer contenido (titulo 1 / contenido 1),
# al final del script se imprime cuales faltan. Los demas contenidos tienen el registro pero sin archivo.
# Se crea un .vtt por cada contenido e idioma, con este texto
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
# OJO: Argentina y Español se crean primero para que tengan id=1 (los defaults de Usuario usan id=1)
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
Titulo.objects.filter(nombre_original="La Última Función").update(fecha_baja=hoy + timedelta(days=60))

for t, cats in zip(titulos, [["Drama"], ["Acción", "Ciencia ficción"], ["Acción", "Ciencia ficción"], ["Drama", "Comedia"], ["Acción"], ["Documental"]]):
    for c in cats:
        TituloCategoria.objects.create(titulo=t, categoria=cat[c])
for t in titulos:
    for rel in roles_elenco[:3]:
        TituloRolElenco.objects.create(titulo=t, rol_elenco=rel)
for t, n in zip(titulos, ["Shadows of the South", "Code Zero", "Neon Samurai", "The Last Show", "Vanishing Point", "Invisible Oceans"]):
    IdiomaTitulo.objects.create(titulo=t, idioma=idi["Inglés"], nombre=n, descripcion=f"English title: {n}")

# Imagen.imagen es un ImageField con upload_to=imagen_upload_path: se guarda en media/perfil/<slug-del-titulo>/
# (hay que pasar el titulo al crear la Imagen, porque la ruta se arma con instance.titulo)
imgs_titulo = [Imagen.objects.create(nombre=f"Portada {t.nombre_original}", titulo=t,
                                     imagen=png(t.nombre_original, COLORES[i % len(COLORES)], "portada.png"))
               for i, t in enumerate(titulos)]

# ---------- CONTENIDO (series: 2 temporadas x 3 episodios; resto: 1 contenido) ----------
contenidos = [Contenido.objects.create(nombre=f"{t.nombre_original} - T{s}E{e}", descripcion=f"Episodio {e} de la temporada {s}", seccion=s, orden=e, titulo=t) for t in titulos[:3] for s in (1, 2) for e in (1, 2, 3)]
contenidos += [Contenido.objects.create(nombre=t.nombre_original, descripcion="Contenido completo", seccion=1, orden=1, titulo=t) for t in titulos[3:]]
idiomas_contenido = [IdiomaContenido.objects.create(idioma=idi[i], contenido=c) for c in contenidos for i in ("Español", "Inglés")]

# Los FileField reciben la ruta (str) relativa a MEDIA_ROOT; los .vtt se crean en esa ruta, los videos no
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

# ---------- PLANES ----------
planes = {n: Plan.objects.create(nombre=n, descripcion=f"Plan {n}", cantidad_pantallas_simultaneas=p) for n, p in [("Básico", 1), ("Estándar", 2), ("Premium", 4)]}
for n, qs in {"Básico": ["SD", "HD"], "Estándar": ["HD", "Full HD"], "Premium": ["HD", "Full HD", "4K"]}.items():
    for q in qs:
        PlanCalidad.objects.create(plan=planes[n], calidad=cal[q])
for n, p in [("Básico", 3500.0), ("Estándar", 5500.0), ("Premium", 8000.0)]:
    Precio.objects.create(plan=planes[n], precio=p * 0.8, fecha_inicio=hoy - timedelta(days=365), fecha_fin=hoy - timedelta(days=1))  # precio histórico
    Precio.objects.create(plan=planes[n], precio=p, fecha_inicio=hoy)  # precio vigente

# ---------- USUARIOS, PERFILES, DISPOSITIVOS ----------
usuarios = [Usuario.objects.create_user(username=u, email=f"{u}@mail.com", password="test1234", first_name=u.capitalize(), telefono=tel, pais=pa[p], idioma=idi[i]) for u, tel, p, i in [
    ("juan", "+5493514000001", "Argentina", "Español"), ("maria", "+5493514000002", "Argentina", "Español"),
    ("john", "+12025550143", "Estados Unidos", "Inglés"), ("carla", "+34600000001", "España", "Español")]]
tp = {n: TipoPerfil.objects.create(nombre=n, edad_max=e) for n, e in [("Infantil", 12), ("Adolescente", 16), ("Adulto", 100)]}
# Imagen exige un titulo, asi que cada avatar se asocia a uno (carpeta media/perfil/<titulo>/)
avatares = [Imagen.objects.create(nombre=f"Avatar {i}", titulo=titulos[i % len(titulos)],
                                  imagen=png(f"Avatar {i}", COLORES[i % len(COLORES)], f"avatar_{i}.png", (200, 200)))
            for i in range(1, 9)]
perfiles = []
for i, u in enumerate(usuarios):
    perfiles += [Perfil.objects.create(nombre=u.first_name, imagen=avatares[i], tipo_perfil=tp["Adulto"], usuario=u),
                 Perfil.objects.create(nombre=f"Kids de {u.first_name}", imagen=avatares[i + 4], tipo_perfil=tp["Infantil"], usuario=u)]
for u in usuarios:
    for n, o in enumerate(["Android", "iOS", "Windows"], start=1):
        Registro.objects.create(token_disp=f"tok-{u.username}-{n}", os=o, ultima_conexion_fecha=hoy, ultima_conexion_hora=ahora.time(), estado=(n == 1), usuario=u)

# ---------- HISTORIAL / RECOMENDACIONES ----------
perfiles_titulos = [PerfilTitulo.objects.create(perfil=p, titulo=titulos[(i + j) % len(titulos)], calificacion=list(calif.values())[(i + j) % 3] if j < 2 else None) for i, p in enumerate(perfiles) for j in range(3)]
for pt in perfiles_titulos[::2]:
    Porver.objects.create(perfil_titulo=pt, fecha_agregado=hoy - timedelta(days=5))
for pt in perfiles_titulos[1::5]:
    Porver.objects.create(perfil_titulo=pt, fecha_agregado=hoy - timedelta(days=20), fecha_eliminado=hoy - timedelta(days=2))
for i, p in enumerate(perfiles):
    for j in range(3):
        PerfilContenido.objects.create(perfil=p, contenido=contenidos[(i * 2 + j) % len(contenidos)], segundos_vistos=300 * (j + 1), ultima_visualizacion=ahora - timedelta(days=j))

# ---------- TARJETAS (los vencimientos van siempre al ultimo dia del mes) ----------
tarjetas = [
    Tarjeta.objects.create(numero="1111", fecha_vencimiento=date(2029, 12, 31), marca_tarjeta=marcas["Visa"], metodo_pago=metodos["Crédito"]),
    Tarjeta.objects.create(numero="4444", fecha_vencimiento=date(2028, 6, 30), marca_tarjeta=marcas["Mastercard"], metodo_pago=metodos["Débito"]),
    Tarjeta.objects.create(numero="0005", fecha_vencimiento=date(2030, 3, 31), marca_tarjeta=marcas["American Express"], metodo_pago=metodos["Crédito"]),
    Tarjeta.objects.create(numero="5556", fecha_vencimiento=date(2027, 9, 30), marca_tarjeta=marcas["Visa"], metodo_pago=metodos["Débito"]),
]
# Tarjeta anterior de juan: vencio el mes pasado y esta deshabilitada
tarjeta_vieja = Tarjeta.objects.create(numero="9012", fecha_vencimiento=hoy.replace(day=1) - timedelta(days=1),
                                       marca_tarjeta=marcas["Mastercard"], metodo_pago=metodos["Crédito"], habilitado=False)

# ---------- SUSCRIPCIONES ----------
suscripciones = [Suscripcion.objects.create(usuario=u, plan=planes[p], tarjeta=t,
                                            fecha_inscripcion=hoy - timedelta(days=90), fecha_vigencia=hoy + timedelta(days=30))
                 for u, p, t in zip(usuarios, ["Básico", "Estándar", "Premium", "Estándar"], tarjetas)]
suscripciones[3].fecha_cancelacion = hoy - timedelta(days=3)  # carla canceló
suscripciones[3].habilitado = False
suscripciones[3].save()

# ---------- COBROS (3 meses de historial por suscripción) ----------
n = 1000
for i, (s, t) in enumerate(zip(suscripciones, tarjetas)):
    monto = Precio.objects.get(plan=s.plan, fecha_fin__isnull=True).precio
    for meses in (2, 1, 0):
        n += 1
        fallo = (i == 2 and meses == 0)  # un cobro rechazado de ejemplo (john)
        # juan cambió de tarjeta: los cobros viejos quedan con la tarjeta anterior (historial)
        tarjeta_cobro = tarjeta_vieja if (i == 0 and meses > 0) else t
        Cobro.objects.create(
            suscripcion=s, fecha_cobro=hoy - timedelta(days=30 * meses),
            estado_cobro=estados["Rechazado"] if fallo else estados["Pagado"], tarjeta=tarjeta_cobro,
            numero_autorizacion=None if fallo else f"AUTH{n}", monto=monto)

print("Mock cargado: usuarios juan, maria, john y carla (contraseña: test1234)")