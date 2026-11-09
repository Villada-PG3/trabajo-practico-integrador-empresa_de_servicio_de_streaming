import calendar
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth import SESSION_KEY as AUTH_SESSION_KEY
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import (
    Case,
    CharField,
    Count,
    Avg,
    ExpressionWrapper,
    F,
    FloatField,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, NullIf, Trim
from django.http import JsonResponse
from django.contrib.sessions.models import Session
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    CuentaPreferenciasForm,
    EditarCuentaForm,
    LoginForm,
    PerfilForm,
    RegistroForm,
    ReporteVentasFiltroForm,
)
from .models import (
    Categoria,
    Calificacion,
    Contenido,
    IdiomaContenido,
    IdiomaTitulo,
    Plan,
    Perfil,
    PerfilTitulo,
    Porver,
    Precio,
    Registro,
    Suscripcion,
    Titulo,
)

LIMITE_TITULOS_CARRUSEL = 30
LIMITE_PERFILES = 5
SESION_PERFIL_ACTIVO = 'perfil_activo_id'


def registrar_sesion_usuario(request, usuario):
    session_key = request.session.session_key
    if not session_key:
        request.session.save()
        session_key = request.session.session_key

    if not session_key:
        raise RuntimeError('No se pudo obtener el identificador de sesión.')

    ahora = timezone.localtime()
    registro = Registro.objects.filter(
        usuario=usuario,
        token_disp=session_key,
    ).first()
    if registro is None:
        Registro.objects.create(
            token_disp=session_key,
            os=request.META.get('HTTP_USER_AGENT', 'Navegador')[:100],
            ultima_conexion_fecha=ahora.date(),
            ultima_conexion_hora=ahora.time(),
            estado=True,
            usuario=usuario,
        )
        return

    registro.os = request.META.get('HTTP_USER_AGENT', 'Navegador')[:100]
    registro.ultima_conexion_fecha = ahora.date()
    registro.ultima_conexion_hora = ahora.time()
    registro.estado = True
    registro.save(update_fields=[
        'os',
        'ultima_conexion_fecha',
        'ultima_conexion_hora',
        'estado',
    ])


def contar_sesiones_abiertas(request, usuario):
    session_key = request.session.session_key
    sesiones_registradas = Registro.objects.filter(
        usuario=usuario,
        estado=True,
    ).values_list('token_disp', flat=True)
    claves_registradas = list(sesiones_registradas)
    claves_vigentes = set(
        Session.objects.filter(
            session_key__in=claves_registradas,
            expire_date__gt=timezone.now(),
        ).values_list('session_key', flat=True)
    )
    Registro.objects.filter(
        usuario=usuario,
        estado=True,
    ).exclude(token_disp=session_key).exclude(
        token_disp__in=claves_vigentes,
    ).update(estado=False)
    return Registro.objects.filter(usuario=usuario, estado=True).count()


def cerrar_sesiones_excepto(usuario, session_key):
    otras_sesiones = []
    sesiones_vigentes = Session.objects.filter(expire_date__gt=timezone.now())
    for sesion in sesiones_vigentes.iterator():
        if sesion.session_key == session_key:
            continue
        datos_sesion = sesion.get_decoded()
        if str(datos_sesion.get(AUTH_SESSION_KEY, '')) == str(usuario.pk):
            otras_sesiones.append(sesion.session_key)

    if otras_sesiones:
        Session.objects.filter(session_key__in=otras_sesiones).delete()
    Registro.objects.filter(
        usuario=usuario,
        estado=True,
    ).exclude(token_disp=session_key).update(estado=False)


def calcular_proximo_cobro(fecha_vigencia):
    if fecha_vigencia is None:
        return None

    mes_siguiente = fecha_vigencia.year * 12 + fecha_vigencia.month
    anio, mes = divmod(mes_siguiente, 12)
    mes += 1
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(fecha_vigencia.day, ultimo_dia))


def active_profile(request):
    if not request.user.is_authenticated:
        return {'perfil_activo': None}

    return {'perfil_activo': get_active_profile(request)}


def get_active_profile(request):
    perfil_id = request.session.get(SESION_PERFIL_ACTIVO)
    return Perfil.objects.select_related('imagen', 'tipo_perfil').filter(
        pk=perfil_id,
        usuario=request.user,
        activo=True,
    ).first()


def ordenar_categorias_titulo(titulos, categoria_prioritaria=None):
    for titulo in titulos:
        if titulo.tipo_titulo.nombre.casefold().startswith('pel'):
            duracion_segundos = sum(
                contenido.duracion_segundos or 0
                for contenido in titulo.contenidos_catalogo
            )
            total_minutos = (duracion_segundos + 30) // 60
            horas, minutos = divmod(total_minutos, 60)
            titulo.duracion_formateada = ' '.join(
                parte for parte in (
                    f'{horas} h' if horas else '',
                    f'{minutos} min' if minutos else '',
                ) if parte
            )

        categorias = [
            relacion.categoria
            for relacion in titulo.titulo_categorias.all()
        ]
        titulo.categorias_ordenadas = sorted(
            categorias,
            key=lambda categoria: (
                categoria_prioritaria is not None
                and categoria.pk != categoria_prioritaria.pk,
                categoria.nombre.casefold(),
            ),
        )
        edad_minima = titulo.edad_minima
        titulo.clasificacion_edad = (
            'ATP' if edad_minima == 0 else f'+{edad_minima}'
        ) if edad_minima is not None else None
    return titulos


def asignar_metadatos_detalle(titulos):
    for titulo in titulos:
        elenco = []
        for relacion in titulo.titulo_rol_elencos.all():
            persona = relacion.rol_elenco.elenco
            nombre = f'{persona.nombre} {persona.apellido}'.strip()
            if nombre not in elenco:
                elenco.append(nombre)
        titulo.elenco_detalle = ', '.join(elenco)
        categorias = [
            relacion.categoria
            for relacion in titulo.titulo_categorias.all()
        ]
        titulo.categorias_detalle = ', '.join(
            categoria.nombre
            for categoria in sorted(
                categorias,
                key=lambda categoria: categoria.nombre.casefold(),
            )
        )
        edad_minima = titulo.edad_minima
        titulo.clasificacion_edad = (
            'ATP' if edad_minima == 0 else f'+{edad_minima}'
        ) if edad_minima is not None else ''
    return titulos


def prefetch_contenidos_detalle(prefix=''):
    imagenes_idioma = (
        IdiomaContenido.objects
        .select_related('idioma')
        .order_by('idioma__nombre', 'pk')
    )
    return Prefetch(
        f'{prefix}contenidos',
        queryset=Contenido.objects.order_by('seccion', 'orden', 'pk').prefetch_related(
            Prefetch(
                'idioma_contenidos',
                queryset=imagenes_idioma,
                to_attr='imagenes_idioma_catalogo',
            )
        ),
        to_attr='contenidos_catalogo',
    )


def asignar_contenidos_detalle(titulos, idioma_id=None):
    for titulo in titulos:
        mostrar_numero_episodio = not titulo.tipo_titulo.nombre.casefold().startswith('pel')
        contenidos = getattr(titulo, 'contenidos_catalogo', None)
        if contenidos is None:
            contenidos = list(titulo.contenidos.all().order_by('seccion', 'orden', 'pk'))

        titulo.contenidos_detalle = []
        for contenido in contenidos:
            imagenes = getattr(contenido, 'imagenes_idioma_catalogo', [])
            imagen_localizada = next(
                (imagen for imagen in imagenes if imagen.idioma_id == idioma_id),
                None,
            ) if idioma_id is not None else None
            idioma_contenido = imagen_localizada
            imagen_idioma = next(
                (localizacion for localizacion in imagenes if localizacion.imagen),
                None,
            )
            imagen = (
                imagen_localizada
                if imagen_localizada and imagen_localizada.imagen
                else imagen_idioma
            )
            nombre = (
                idioma_contenido.nombre.strip()
                if idioma_contenido and idioma_contenido.nombre.strip()
                else contenido.nombre
            )
            descripcion = (
                (idioma_contenido.descripcion or '').strip()
                if idioma_contenido and (idioma_contenido.descripcion or '').strip()
                else (contenido.descripcion or '').strip()
            )
            duracion_segundos = contenido.duracion_segundos
            duracion = ''
            if duracion_segundos is not None:
                if duracion_segundos < 60:
                    duracion = f'{duracion_segundos} s'
                else:
                    total_minutos = (duracion_segundos + 30) // 60
                    horas, minutos = divmod(total_minutos, 60)
                    duracion = ' '.join(
                        parte for parte in (
                            f'{horas} h' if horas else '',
                            f'{minutos} min' if minutos else '',
                        ) if parte
                    )

            titulo.contenidos_detalle.append({
                'seccion': contenido.seccion,
                'orden': contenido.orden,
                'nombre': nombre,
                'descripcion': descripcion,
                'duracion': duracion,
                'imagen': imagen.imagen.url if imagen else '',
                'mostrar_numero_episodio': mostrar_numero_episodio,
            })
        titulo.contenidos_detalle_json = json.dumps(
            titulo.contenidos_detalle,
            ensure_ascii=False,
        )
    return titulos


def marcar_estado_mi_lista(titulos, titulos_guardados):
    for titulo in titulos:
        titulo.en_mi_lista = titulo.pk in titulos_guardados
    return titulos


def asignar_promedio_estrellas(titulos):
    titulos_por_id = {}
    for titulo in titulos:
        titulos_por_id.setdefault(titulo.pk, []).append(titulo)
        titulo.porcentaje_promedio = None
        titulo.estrellas_promedio = None
        titulo.estrellas_promedio_redondeado = None
    if not titulos_por_id:
        return titulos

    promedios = (
        PerfilTitulo.objects.filter(
            titulo_id__in=titulos_por_id,
            calificacion__isnull=False,
        )
        .values('titulo_id')
        .annotate(promedio=Avg('calificacion__porcentaje_gusto'))
    )
    for resultado in promedios:
        porcentaje_promedio = Decimal(str(resultado['promedio']))
        estrellas_promedio = porcentaje_promedio / Decimal('20')
        estrellas_promedio_redondeado = int(
            estrellas_promedio.quantize(
                Decimal('1'),
                rounding=ROUND_HALF_UP,
            )
        )
        for titulo in titulos_por_id[resultado['titulo_id']]:
            titulo.porcentaje_promedio = porcentaje_promedio
            titulo.estrellas_promedio = estrellas_promedio
            titulo.estrellas_promedio_redondeado = estrellas_promedio_redondeado
    return titulos


def asignar_textos_titulo(titulos, idioma_id=None):
    for titulo in titulos:
        idiomas_titulo = getattr(titulo, 'idiomas_texto', [])
        idioma_preferido = next(
            (
                idioma_titulo for idioma_titulo in idiomas_titulo
                if idioma_titulo.idioma_id == idioma_id
            ),
            None,
        ) if idioma_id is not None else next(
            (
                idioma_titulo for idioma_titulo in idiomas_titulo
                if idioma_titulo.nombre.strip() or (idioma_titulo.descripcion or '').strip()
            ),
            None,
        )
        titulo.nombre_mostrar = (
            idioma_preferido.nombre.strip()
            if idioma_preferido and idioma_preferido.nombre.strip()
            else titulo.nombre_original
        )
        titulo.descripcion_mostrar = (
            (idioma_preferido.descripcion or '').strip()
            if idioma_preferido and (idioma_preferido.descripcion or '').strip()
            else titulo.descripcion_original
        )
    return titulos


def nombre_titulo_para_busqueda(idioma_id):
    textos = IdiomaTitulo.objects.filter(titulo_id=OuterRef('pk'))
    if idioma_id is not None:
        textos = textos.filter(idioma_id=idioma_id).order_by('pk')
    else:
        textos = textos.filter(
            Q(nombre__gt='') | Q(descripcion__gt=''),
        ).order_by('idioma__nombre', 'pk')
    nombre_localizado = NullIf(
        Trim(Subquery(textos.values('nombre')[:1])),
        Value(''),
    )
    return Coalesce(
        nombre_localizado,
        F('nombre_original'),
        output_field=CharField(),
    )


@never_cache
def home(request):
    perfil_activo = None
    if request.user.is_authenticated:
        perfil_activo = get_active_profile(request)
    titulos_guardados = set()
    if perfil_activo is not None:
        titulos_guardados = set(
            Porver.objects.filter(
                perfil_titulo__perfil=perfil_activo,
                fecha_eliminado__isnull=True,
            ).values_list('perfil_titulo__titulo_id', flat=True)
        )

    prefijos_tipos = {'series': 'ser', 'peliculas': 'pel'}
    filtro_tipo = request.GET.get('tipo')
    prefijo_tipo = prefijos_tipos.get(filtro_tipo)
    if prefijo_tipo is None:
        filtro_tipo = ''
    try:
        filtro_categoria_id = int(request.GET.get('categoria', ''))
    except (TypeError, ValueError):
        filtro_categoria_id = None
    categoria_seleccionada = (
        Categoria.objects.filter(pk=filtro_categoria_id).first()
        if filtro_categoria_id is not None else None
    )

    cantidad_populares = LIMITE_TITULOS_CARRUSEL if request.user.is_authenticated else 10
    suscripcion_actual = None
    if request.user.is_authenticated:
        suscripcion_actual = (
            Suscripcion.objects.filter(usuario=request.user, habilitado=True)
            .select_related('plan')
            .order_by('-fecha_inscripcion')
            .first()
        )

    idioma_preferido_id = getattr(request.user, 'idioma_id', None)
    imagenes_idioma_query = IdiomaTitulo.objects.exclude(imagen='').order_by(
        'idioma__nombre',
        'id',
    )
    if idioma_preferido_id is not None:
        imagenes_idioma_query = imagenes_idioma_query.order_by(
            Case(
                When(idioma_id=idioma_preferido_id, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            'idioma__nombre',
            'id',
        )
    imagenes_catalogo = Prefetch(
        'idioma_titulos',
        queryset=imagenes_idioma_query,
        to_attr='imagenes_catalogo',
    )
    textos_catalogo = Prefetch(
        'idioma_titulos',
        queryset=IdiomaTitulo.objects.select_related('idioma').order_by('idioma__nombre', 'id'),
        to_attr='idiomas_texto',
    )
    contenidos_catalogo = prefetch_contenidos_detalle()
    relaciones_elenco = 'titulo_rol_elencos__rol_elenco__elenco'
    titulos_query = Titulo.objects.filter(contenidos__isnull=False)
    titulo_seleccionado = request.GET.get('titulo')
    if titulo_seleccionado is not None:
        try:
            titulo_seleccionado = int(titulo_seleccionado)
        except (TypeError, ValueError):
            titulo_seleccionado = -1
        titulos_query = titulos_query.filter(pk=titulo_seleccionado)
    if perfil_activo is not None:
        titulos_query = titulos_query.filter(
            edad_minima__lte=perfil_activo.tipo_perfil.edad_max,
        )
    elif request.user.is_authenticated:
        titulos_query = titulos_query.none()
    if prefijo_tipo:
        titulos_query = titulos_query.filter(
            tipo_titulo__nombre__istartswith=prefijo_tipo
        )
    if filtro_categoria_id is not None:
        titulos_query = titulos_query.filter(
            titulo_categorias__categoria_id=filtro_categoria_id
        )
    titulos_con_contenido = (
        titulos_query.distinct()
        .select_related('tipo_titulo')
        .annotate(
            temporadas=Count(
                'contenidos__seccion',
                filter=Q(
                    tipo_titulo__nombre__istartswith='ser',
                    contenidos__seccion__gte=1,
                ),
                distinct=True,
            )
        )
        .prefetch_related(
            'titulo_categorias__categoria',
            relaciones_elenco,
            imagenes_catalogo,
            textos_catalogo,
            contenidos_catalogo,
        )
        .order_by('-fecha_estreno', 'nombre_original')
    )
    carruseles = []

    reproduccion_valida = Q(
        contenidos__duracion_segundos__gt=0,
        contenidos__perfil_contenidos__segundos_vistos__gte=ExpressionWrapper(
            F('contenidos__duracion_segundos') * 0.1,
            output_field=FloatField(),
        )
    )
    mas_reproducidos_query = Titulo.objects.filter(
        contenidos__isnull=False,
        contenidos__duracion_segundos__gt=0,
    )
    if titulo_seleccionado is not None:
        mas_reproducidos_query = mas_reproducidos_query.filter(
            pk=titulo_seleccionado
        )
    if perfil_activo is not None:
        mas_reproducidos_query = mas_reproducidos_query.filter(
            edad_minima__lte=perfil_activo.tipo_perfil.edad_max,
        )
    elif request.user.is_authenticated:
        mas_reproducidos_query = mas_reproducidos_query.none()
    if prefijo_tipo:
        mas_reproducidos_query = mas_reproducidos_query.filter(
            tipo_titulo__nombre__istartswith=prefijo_tipo
        )
    if filtro_categoria_id is not None:
        mas_reproducidos_query = mas_reproducidos_query.filter(
            titulo_categorias__categoria_id=filtro_categoria_id
        )
    mas_reproducidos_query = (
        mas_reproducidos_query
        .annotate(
            reproducciones=Count(
                'contenidos__perfil_contenidos',
                filter=reproduccion_valida,
            ),
            temporadas=Count(
                'contenidos__seccion',
                filter=Q(
                    tipo_titulo__nombre__istartswith='ser',
                    contenidos__seccion__gte=1,
                ),
                distinct=True,
            ),
        )
        .filter(reproducciones__gt=0)
        .select_related('tipo_titulo')
        .prefetch_related(
            'titulo_categorias__categoria',
            relaciones_elenco,
            imagenes_catalogo,
            textos_catalogo,
            contenidos_catalogo,
        )
        .order_by('-reproducciones', '-fecha_estreno', 'nombre_original')
    )
    mas_reproducidos = marcar_estado_mi_lista(
        ordenar_categorias_titulo(
            list(mas_reproducidos_query[:cantidad_populares])
        ),
        titulos_guardados,
    )
    asignar_textos_titulo(mas_reproducidos, getattr(request.user, 'idioma_id', None))
    if mas_reproducidos:
        carruseles.append({
            'etiqueta': 'Más reproducidos' if request.user.is_authenticated else 'Populares',
            'titulos': mas_reproducidos,
            'mostrar_top': not request.user.is_authenticated,
        })

    if request.user.is_authenticated:
        if perfil_activo is not None and not prefijo_tipo:
            lista_por_ver = Porver.objects.filter(
                perfil_titulo__perfil=perfil_activo,
                fecha_eliminado__isnull=True,
                perfil_titulo__titulo__edad_minima__lte=perfil_activo.tipo_perfil.edad_max,
            )
            if filtro_categoria_id is not None:
                lista_por_ver = lista_por_ver.filter(
                    perfil_titulo__titulo__titulo_categorias__categoria_id=filtro_categoria_id
                ).order_by(
                    '-perfil_titulo__titulo__fecha_estreno',
                    '-fecha_agregado',
                    '-pk',
                )
            else:
                lista_por_ver = lista_por_ver.order_by('fecha_agregado', 'pk')
            titulos_mi_lista_ids = list(
                lista_por_ver.values_list(
                    'perfil_titulo__titulo_id',
                    flat=True,
                )[:LIMITE_TITULOS_CARRUSEL]
            )
            titulos_mi_lista = list(
                Titulo.objects.filter(pk__in=titulos_mi_lista_ids)
                .select_related('tipo_titulo')
                .annotate(
                    temporadas=Count(
                        'contenidos__seccion',
                        filter=Q(
                            tipo_titulo__nombre__istartswith='ser',
                            contenidos__seccion__gte=1,
                        ),
                        distinct=True,
                    )
                )
                .prefetch_related(
                    'titulo_categorias__categoria',
                    relaciones_elenco,
                    imagenes_catalogo,
                    textos_catalogo,
                    contenidos_catalogo,
                )
            )
            orden_mi_lista = {
                titulo_id: indice
                for indice, titulo_id in enumerate(titulos_mi_lista_ids)
            }
            titulos_mi_lista.sort(key=lambda titulo: orden_mi_lista[titulo.pk])
            titulos_mi_lista = marcar_estado_mi_lista(
                ordenar_categorias_titulo(titulos_mi_lista),
                titulos_guardados,
            )
            asignar_textos_titulo(
                titulos_mi_lista,
                getattr(request.user, 'idioma_id', None),
            )
            asignar_metadatos_detalle(titulos_mi_lista)
            if titulos_mi_lista:
                carruseles.append({
                    'etiqueta': 'Mi Lista',
                    'titulos': titulos_mi_lista,
                    'es_mi_lista': True,
                })

        if prefijo_tipo is None:
            for etiqueta, prefijo in (('Series', 'ser'), ('Películas', 'pel')):
                titulos = marcar_estado_mi_lista(
                    ordenar_categorias_titulo(list(
                        titulos_con_contenido.filter(
                            tipo_titulo__nombre__istartswith=prefijo
                        )[:LIMITE_TITULOS_CARRUSEL]
                    )),
                    titulos_guardados,
                )
                asignar_textos_titulo(
                    titulos,
                    getattr(request.user, 'idioma_id', None),
                )
                if titulos:
                    carruseles.append({'etiqueta': etiqueta, 'titulos': titulos})

        categorias = Categoria.objects.filter(
            titulo_categorias__titulo__contenidos__isnull=False
        ).distinct().order_by('nombre')
        if prefijo_tipo:
            categorias = categorias.filter(
                titulo_categorias__titulo__tipo_titulo__nombre__istartswith=prefijo_tipo
            )
        if filtro_categoria_id is not None:
            categorias = categorias.exclude(pk=filtro_categoria_id)
        titulos_en_categorias = set()
        for categoria in categorias:
            titulos = marcar_estado_mi_lista(
                ordenar_categorias_titulo(list(
                    titulos_con_contenido.filter(
                        titulo_categorias__categoria=categoria
                    )[:LIMITE_TITULOS_CARRUSEL]
                ), categoria_prioritaria=categoria),
                titulos_guardados,
            )
            asignar_textos_titulo(titulos, getattr(request.user, 'idioma_id', None))
            if titulos:
                titulos_en_categorias.update(titulo.pk for titulo in titulos)
                carruseles.append({'etiqueta': categoria.nombre, 'titulos': titulos})

        if prefijo_tipo:
            titulos_no_mostrados = marcar_estado_mi_lista(
                ordenar_categorias_titulo(list(
                    titulos_con_contenido.exclude(
                        pk__in=titulos_en_categorias
                    )[:LIMITE_TITULOS_CARRUSEL]
                )),
                titulos_guardados,
            )
            asignar_textos_titulo(
                titulos_no_mostrados,
                getattr(request.user, 'idioma_id', None),
            )
            if titulos_no_mostrados:
                carruseles.append({
                    'etiqueta': 'Más títulos',
                    'titulos': titulos_no_mostrados,
                })

    banners = []
    if request.user.is_authenticated:
        titulos_banner = titulos_con_contenido.filter(fecha_estreno__isnull=False)
        if filtro_categoria_id is None:
            titulos_banner = titulos_banner.filter(idioma_titulos__imagen__gt='')
        if prefijo_tipo:
            titulos_banner = titulos_banner.filter(
                tipo_titulo__nombre__istartswith=prefijo_tipo
            )
        titulos_banner = titulos_banner.distinct().order_by(
            '-fecha_estreno', 'nombre_original', 'pk'
        )[:5]
        for titulo in titulos_banner:
            nombres_elenco = []
            for relacion in titulo.titulo_rol_elencos.all():
                persona = relacion.rol_elenco.elenco
                nombre = f'{persona.nombre} {persona.apellido}'
                if nombre not in nombres_elenco:
                    nombres_elenco.append(nombre)
            imagen_banner = titulo.imagenes_catalogo[0] if titulo.imagenes_catalogo else None
            titulo.en_mi_lista = titulo.pk in titulos_guardados
            asignar_textos_titulo([titulo], getattr(request.user, 'idioma_id', None))
            banners.append({
                'titulo': titulo,
                'elenco': nombres_elenco[:4],
                'imagen_url': imagen_banner.imagen.url if imagen_banner and imagen_banner.imagen else '',
            })

    titulos_en_pantalla = [
        titulo
        for carrusel in carruseles
        for titulo in carrusel['titulos']
    ]
    titulos_en_pantalla.extend(banner['titulo'] for banner in banners)
    asignar_metadatos_detalle(titulos_en_pantalla)
    asignar_contenidos_detalle(
        titulos_en_pantalla,
        getattr(request.user, 'idioma_id', None),
    )
    asignar_promedio_estrellas(titulos_en_pantalla)
    puntuaciones_perfil = {}
    if perfil_activo is not None:
        puntuaciones_perfil = dict(
            PerfilTitulo.objects.filter(perfil=perfil_activo)
            .values_list('titulo_id', 'calificacion__estrellas')
        )
    for titulo in titulos_en_pantalla:
        titulo.puntuacion_estrellas = puntuaciones_perfil.get(titulo.pk)

    return render(request, 'home.html', {
        'suscripcion_actual': suscripcion_actual,
        'carruseles': carruseles,
        'banners': banners,
        'filtro_tipo': filtro_tipo,
        'filtro_categoria_id': filtro_categoria_id,
        'categoria_seleccionada': categoria_seleccionada,
        'url_actual': request.get_full_path(),
        'pagina_inicio': True,
    })


def pagina_inicial_view(request):
    if request.user.is_authenticated:
        return redirect('perfiles')
    return redirect('home')


def not_found_view(request, exception=None):
    return render(request, 'NotFound.html', status=404)


@login_required
def categorias_view(request):
    perfil_activo = get_active_profile(request)
    if perfil_activo is None:
        return redirect('perfiles')

    categorias = Categoria.objects.filter(
        titulo_categorias__titulo__contenidos__isnull=False,
        titulo_categorias__titulo__edad_minima__lte=perfil_activo.tipo_perfil.edad_max,
    ).distinct().order_by('nombre', 'pk')
    return render(request, 'categorias.html', {
        'categorias': categorias,
        'pagina_categorias': True,
    })


@login_required
@require_GET
@never_cache
def buscar_titulos_view(request):
    consulta = request.GET.get('q', '').strip()
    if len(consulta) < 2:
        return JsonResponse({'resultados': []})

    perfil_activo = get_active_profile(request)
    if perfil_activo is None:
        return JsonResponse(
            {'error': 'Selecciona un perfil activo para buscar títulos.'},
            status=400,
        )

    idioma_id = request.user.idioma_id
    nombre_titulo = nombre_titulo_para_busqueda(idioma_id)
    imagenes = IdiomaTitulo.objects.filter(
        titulo_id=OuterRef('pk'),
        imagen__gt='',
    )
    if idioma_id is not None:
        imagenes = imagenes.order_by(
            Case(
                When(idioma_id=idioma_id, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            'idioma__nombre',
            'pk',
        )
    else:
        imagenes = imagenes.order_by('idioma__nombre', 'pk')
    titulos = (
        Titulo.objects.filter(
            contenidos__isnull=False,
            edad_minima__lte=perfil_activo.tipo_perfil.edad_max,
        )
        .annotate(nombre_busqueda=nombre_titulo)
        .annotate(imagen_busqueda=Subquery(imagenes.values('imagen')[:1]))
        .filter(nombre_busqueda__icontains=consulta)
        .select_related('tipo_titulo')
        .distinct()
        .order_by('nombre_busqueda', 'pk')
        .prefetch_related(
            'titulo_categorias__categoria',
            'titulo_rol_elencos__rol_elenco__elenco',
            Prefetch(
                'idioma_titulos',
                queryset=IdiomaTitulo.objects.select_related('idioma').order_by(
                    'idioma__nombre',
                    'pk',
                ),
                to_attr='idiomas_texto',
            ),
            prefetch_contenidos_detalle(),
        )
    )
    titulos_guardados = set(
        Porver.objects.filter(
            perfil_titulo__perfil=perfil_activo,
            fecha_eliminado__isnull=True,
        ).values_list('perfil_titulo__titulo_id', flat=True)
    )
    resultados_busqueda = list(titulos)
    asignar_textos_titulo(resultados_busqueda, idioma_id)
    asignar_metadatos_detalle(resultados_busqueda)
    asignar_contenidos_detalle(resultados_busqueda, idioma_id)
    asignar_promedio_estrellas(resultados_busqueda)
    puntuaciones_perfil = dict(
        PerfilTitulo.objects.filter(perfil=perfil_activo)
        .values_list('titulo_id', 'calificacion__estrellas')
    )

    return JsonResponse({
        'resultados': [
            {
                'id': titulo.pk,
                'nombre': titulo.nombre_busqueda,
                'tipo': titulo.tipo_titulo.nombre,
                'imagen': default_storage.url(titulo.imagen_busqueda)
                if titulo.imagen_busqueda else '',
                'url': f"{reverse('home')}?titulo={titulo.pk}",
                'toggle_url': reverse('toggle_mi_lista', args=[titulo.pk]),
                'rating_url': reverse('calificar_titulo', args=[titulo.pk]),
                'en_mi_lista': titulo.pk in titulos_guardados,
                'estrellas_promedio': titulo.estrellas_promedio_redondeado,
                'porcentaje_promedio': (
                    float(titulo.porcentaje_promedio)
                    if titulo.porcentaje_promedio is not None else None
                ),
                'puntuacion_perfil': str(puntuaciones_perfil.get(titulo.pk) or ''),
                'descripcion': titulo.descripcion_mostrar or '',
                'elenco': titulo.elenco_detalle,
                'categorias': titulo.categorias_detalle,
                'edad': titulo.clasificacion_edad,
                'contenidos': titulo.contenidos_detalle,
            }
            for titulo in resultados_busqueda
        ],
    })


@login_required
@require_POST
def toggle_mi_lista_view(request, titulo_id):
    es_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    fecha_actual = timezone.localdate()
    with transaction.atomic():
        perfil_activo = Perfil.objects.select_for_update().filter(
            pk=request.session.get(SESION_PERFIL_ACTIVO),
            usuario=request.user,
            activo=True,
        ).select_related('tipo_perfil').first()
        if perfil_activo is None:
            if es_ajax:
                return JsonResponse(
                    {'error': 'Selecciona un perfil activo antes de modificar Mi Lista.'},
                    status=400,
                )
            messages.error(request, 'Selecciona un perfil activo antes de modificar Mi Lista.')
            return redirect('perfiles')

        titulo = Titulo.objects.filter(
            pk=titulo_id,
            edad_minima__lte=perfil_activo.tipo_perfil.edad_max,
        ).first()
        if titulo is None:
            if es_ajax:
                return JsonResponse(
                    {'error': 'No se encontró un título disponible para este perfil.'},
                    status=404,
                )
            messages.error(request, 'No se encontró un título disponible para este perfil.')
            return redirect('home')

        perfil_titulo = PerfilTitulo.objects.filter(
            perfil=perfil_activo,
            titulo=titulo,
        ).first()
        titulos_activos = (
            Porver.objects.select_for_update().filter(
                perfil_titulo=perfil_titulo,
                fecha_eliminado__isnull=True,
            )
            if perfil_titulo is not None
            else Porver.objects.none()
        )
        if titulos_activos.exists():
            titulos_activos.update(fecha_eliminado=fecha_actual)
            en_mi_lista = False
            mensaje = 'Se quitó el título de Mi Lista.'
        else:
            if not titulo.contenidos.exists():
                if es_ajax:
                    return JsonResponse(
                        {'error': 'El título no está disponible para agregar a Mi Lista.'},
                        status=404,
                    )
                messages.error(request, 'El título no está disponible para agregar a Mi Lista.')
                return redirect('home')
            if perfil_titulo is None:
                perfil_titulo = PerfilTitulo.objects.create(
                    perfil=perfil_activo,
                    titulo=titulo,
                )
            Porver.objects.create(
                perfil_titulo=perfil_titulo,
                fecha_agregado=fecha_actual,
            )
            en_mi_lista = True
            mensaje = 'Se agregó el título a Mi Lista.'

    if es_ajax:
        return JsonResponse({
            'en_mi_lista': en_mi_lista,
            'mensaje': mensaje,
            'titulo_id': titulo.pk,
        })

    messages.success(request, mensaje)

    url_siguiente = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(
        url_siguiente,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(url_siguiente)
    return redirect('home')


@login_required
@require_POST
def calificar_titulo_view(request, titulo_id):
    perfil_activo = get_active_profile(request)
    if perfil_activo is None:
        return JsonResponse(
            {'error': 'Selecciona un perfil activo antes de calificar un título.'},
            status=400,
        )

    try:
        puntuacion = Decimal(request.POST.get('puntuacion', ''))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({'error': 'Selecciona una puntuación válida.'}, status=400)

    if (
        not puntuacion.is_finite()
        or puntuacion < Decimal('0.5')
        or puntuacion > Decimal('5')
        or puntuacion * 2 != (puntuacion * 2).to_integral_value()
    ):
        return JsonResponse(
            {'error': 'La puntuación debe estar entre 0,5 y 5 estrellas.'},
            status=400,
        )

    titulo = Titulo.objects.filter(
        pk=titulo_id,
        edad_minima__lte=perfil_activo.tipo_perfil.edad_max,
        contenidos__isnull=False,
    ).first()
    if titulo is None:
        return JsonResponse(
            {'error': 'No se encontró un título disponible para este perfil.'},
            status=404,
        )

    with transaction.atomic():
        perfil_titulo, _ = PerfilTitulo.objects.select_for_update().get_or_create(
            perfil=perfil_activo,
            titulo=titulo,
        )
        porcentaje_gusto = float(puntuacion * 20)
        calificacion, _ = Calificacion.objects.update_or_create(
            estrellas=puntuacion,
            defaults={
                'nombre': f'{puntuacion} estrellas',
                'porcentaje_gusto': porcentaje_gusto,
            },
        )
        perfil_titulo.calificacion = calificacion
        perfil_titulo.save(update_fields=['calificacion'])
        perfil_titulo.refresh_from_db(fields=['calificacion'])

    asignar_promedio_estrellas([titulo])
    return JsonResponse({
        'titulo_id': titulo.pk,
        'puntuacion': str(perfil_titulo.calificacion.estrellas),
        'estrellas_promedio': titulo.estrellas_promedio_redondeado,
        'porcentaje_promedio': float(titulo.porcentaje_promedio),
        'mensaje': 'Se guardó tu puntuación.',
    })


@login_required
@never_cache
def mi_lista_view(request):
    perfil_id = request.session.get(SESION_PERFIL_ACTIVO)
    perfil_activo = Perfil.objects.filter(
        pk=perfil_id,
        usuario=request.user,
        activo=True,
    ).select_related('tipo_perfil').first()
    if perfil_activo is None:
        return redirect('perfiles')

    orden = request.GET.get('orden', 'antiguo')
    ordenamientos = {
        'antiguo': ('fecha_agregado', 'pk'),
        'reciente': ('-fecha_agregado', '-pk'),
        'alfabetico': ('pk',),
    }
    if orden not in ordenamientos:
        orden = 'antiguo'

    imagenes_titulo = Prefetch(
        'perfil_titulo__titulo__idioma_titulos',
        queryset=IdiomaTitulo.objects.exclude(imagen='').order_by('idioma__nombre', 'id'),
        to_attr='imagenes_mi_lista',
    )
    textos_titulo = Prefetch(
        'perfil_titulo__titulo__idioma_titulos',
        queryset=IdiomaTitulo.objects.select_related('idioma').order_by('idioma__nombre', 'id'),
        to_attr='idiomas_texto',
    )
    titulos_por_ver = (
        Porver.objects.filter(
            perfil_titulo__perfil=perfil_activo,
            fecha_eliminado__isnull=True,
            perfil_titulo__titulo__edad_minima__lte=perfil_activo.tipo_perfil.edad_max,
        )
        .select_related(
            'perfil_titulo__titulo__tipo_titulo',
            'perfil_titulo__perfil',
            'perfil_titulo__calificacion',
        )
        .prefetch_related(
            'perfil_titulo__titulo__titulo_categorias__categoria',
            'perfil_titulo__titulo__titulo_rol_elencos__rol_elenco__elenco',
            imagenes_titulo,
            textos_titulo,
            prefetch_contenidos_detalle(prefix='perfil_titulo__titulo__'),
        )
        .order_by(*ordenamientos[orden])
    )
    titulos_por_ver_lista = list(titulos_por_ver)
    titulos_lista = [
        porver.perfil_titulo.titulo
        for porver in titulos_por_ver_lista
    ]
    asignar_promedio_estrellas(titulos_lista)
    asignar_textos_titulo(
        titulos_lista,
        request.user.idioma_id,
    )
    asignar_metadatos_detalle(titulos_lista)
    asignar_contenidos_detalle(titulos_lista, request.user.idioma_id)
    if orden == 'alfabetico':
        titulos_por_ver_lista.sort(
            key=lambda porver: (
                porver.perfil_titulo.titulo.nombre_mostrar.casefold(),
                porver.pk,
            )
        )
    return render(request, 'mi_lista.html', {
        'titulos_por_ver': titulos_por_ver_lista,
        'orden': orden,
        'pagina_mi_lista': True,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('perfiles')

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email'].strip().lower()
        user_model = get_user_model()
        usuario = user_model.objects.filter(email__iexact=email).first()
        if usuario is None:
            usuario = user_model.objects.filter(username__iexact=email).first()
        user = authenticate(
            request,
            username=usuario.get_username() if usuario else email,
            password=form.cleaned_data['password'],
        )
        if user is not None:
            login(request, user)
            if not form.data.get('remember_me'):
                request.session.set_expiry(0)
            registrar_sesion_usuario(request, user)
            if Perfil.objects.filter(usuario=user, activo=True).exists():
                return redirect('perfiles')
            return redirect('crear_perfil')
        form.add_error(None, 'Correo electrónico o contraseña incorrectos.')

    return render(request, 'login.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        if request.user.is_authenticated and request.session.session_key:
            Registro.objects.filter(
                usuario=request.user,
                token_disp=request.session.session_key,
                estado=True,
            ).update(estado=False)
        logout(request)
    return redirect('home')


def registro_view(request):
    if request.user.is_authenticated:
        return redirect('perfiles')

    initial = {'email': request.GET.get('email', '').strip().lower()}
    form = RegistroForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        registrar_sesion_usuario(request, user)
        return redirect('crear_perfil')
    return render(request, 'registro.html', {'form': form})


@login_required(login_url='login')
def cuenta_view(request):
    registrar_sesion_usuario(request, request.user)
    seccion = request.GET.get('seccion', 'usuario')
    if seccion not in {'usuario', 'suscripcion', 'mas-info'}:
        seccion = 'usuario'

    form = CuentaPreferenciasForm(
        request.POST or None,
        usuario=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Se actualizaron tus preferencias.')
        return redirect(f'{reverse("cuenta")}?seccion=usuario')

    hoy = timezone.localdate()
    suscripcion = (
        Suscripcion.objects.filter(usuario=request.user)
        .select_related('plan')
        .prefetch_related('plan__plan_calidades__calidad')
        .order_by('-fecha_inscripcion', '-pk')
        .first()
    )
    precio_actual = None
    ultimo_cobro = None
    if suscripcion is not None:
        precio_actual = (
            Precio.objects.filter(
                plan=suscripcion.plan,
                fecha_inicio__lte=hoy,
            )
            .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy))
            .order_by('-fecha_inicio', '-pk')
            .first()
        )
        ultimo_cobro = (
            suscripcion.cobros.select_related(
                'tarjeta',
                'tarjeta__marca_tarjeta',
                'tarjeta__metodo_pago',
            )
            .order_by('-fecha_cobro', '-pk')
            .first()
        )

    return render(request, 'cuenta.html', {
        'form': form,
        'seccion_cuenta': seccion,
        'perfiles_activos': Perfil.objects.filter(
            usuario=request.user,
            activo=True,
        ).count(),
        'sesiones_abiertas': contar_sesiones_abiertas(request, request.user),
        'suscripcion': suscripcion,
        'proximo_cobro': (
            calcular_proximo_cobro(suscripcion.fecha_vigencia)
            if suscripcion is not None else None
        ),
        'precio_actual': precio_actual,
        'ultimo_cobro': ultimo_cobro,
        'calidades': (
            suscripcion.plan.plan_calidades.select_related('calidad').order_by(
                'calidad__nombre',
                'pk',
            )
            if suscripcion is not None else []
        ),
        'pagina_cuenta': True,
    })


@login_required(login_url='login')
@require_POST
def cerrar_otras_sesiones_view(request):
    session_key = request.session.session_key
    if not session_key:
        registrar_sesion_usuario(request, request.user)
        session_key = request.session.session_key

    cerrar_sesiones_excepto(request.user, session_key)
    messages.success(
        request,
        'Se cerraron las demás sesiones. Esta sesión permanece abierta.',
    )
    return redirect(f'{reverse("cuenta")}?seccion=usuario')


@login_required(login_url='login')
def editar_dato_cuenta_view(request, campo):
    if campo not in EditarCuentaForm.CAMPOS:
        messages.error(request, 'El dato solicitado no se puede editar.')
        return redirect(f'{reverse("cuenta")}?seccion=usuario')

    form = EditarCuentaForm(
        request.POST or None,
        usuario=request.user,
        campo=campo,
    )
    if request.method == 'POST' and form.is_valid():
        es_contrasena = campo == 'password'
        form.save()
        if es_contrasena:
            update_session_auth_hash(request, request.user)
            session_key = request.session.session_key
            if not session_key:
                raise RuntimeError('No se pudo obtener la sesión actual tras cambiar la contraseña.')
            registrar_sesion_usuario(request, request.user)
            cerrar_sesiones_excepto(request.user, session_key)
            messages.success(
                request,
                'Se actualizó la contraseña y se cerraron todas las demás sesiones. '
                'Esta sesión permanece abierta.',
            )
        else:
            messages.success(request, 'Se actualizó el dato de tu cuenta.')
        return redirect(f'{reverse("cuenta")}?seccion=usuario')

    return render(request, 'editar_cuenta_dato.html', {
        'form': form,
        'nombre_dato': EditarCuentaForm.CAMPOS[campo],
        'pagina_cuenta': True,
    })


@login_required
def perfiles_view(request):
    perfiles = (
        Perfil.objects.filter(usuario=request.user, activo=True)
        .select_related('imagen')
        .order_by('pk')
    )
    if not perfiles.exists():
        return redirect('crear_perfil')

    if request.method == 'POST':
        perfil = perfiles.filter(pk=request.POST.get('perfil_id')).first()
        if perfil is None:
            messages.error(request, 'Selecciona un perfil válido de esta cuenta.')
        else:
            request.session[SESION_PERFIL_ACTIVO] = perfil.pk
            return redirect('home')

    return render(request, 'perfiles.html', {
        'perfiles': perfiles,
        'puede_agregar_perfil': perfiles.count() < LIMITE_PERFILES,
        'editar_perfiles': request.GET.get('editar') == '1',
        'pagina_perfiles': True,
    })


@login_required
def crear_perfil_view(request):
    cantidad_perfiles = Perfil.objects.filter(usuario=request.user, activo=True).count()
    if cantidad_perfiles >= LIMITE_PERFILES:
        messages.info(request, 'Esta cuenta ya tiene el máximo de cinco perfiles.')
        return redirect('perfiles')

    form = PerfilForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if Perfil.objects.filter(usuario=request.user, activo=True).count() >= LIMITE_PERFILES:
                messages.error(request, 'Esta cuenta ya tiene el máximo de cinco perfiles.')
                return redirect('perfiles')
            perfil = form.save(request.user)

        request.session[SESION_PERFIL_ACTIVO] = perfil.pk
        return redirect('home')

    return render(request, 'crear_perfil.html', {
        'form': form,
        'pagina_crear_perfil': True,
        'primer_perfil': cantidad_perfiles == 0,
    })


@login_required
def configurar_perfil_view(request, perfil_id):
    perfil = Perfil.objects.filter(
        pk=perfil_id,
        usuario=request.user,
        activo=True,
    ).first()
    if perfil is None:
        messages.error(request, 'No se encontró un perfil activo de esta cuenta.')
        return redirect('perfiles')

    form = PerfilForm(request.POST or None, perfil=perfil)
    if request.method == 'POST' and form.is_valid():
        form.save(request.user, perfil=perfil)
        messages.success(request, 'Se guardaron los cambios del perfil.')
        return redirect('perfiles')

    return render(request, 'crear_perfil.html', {
        'form': form,
        'pagina_perfiles': True,
        'editar_perfil': perfil,
        'primer_perfil': False,
    })


@login_required
def desactivar_perfil_view(request, perfil_id):
    perfil = Perfil.objects.filter(
        pk=perfil_id,
        usuario=request.user,
        activo=True,
    ).first()
    if perfil is None:
        messages.error(request, 'No se encontró un perfil activo de esta cuenta.')
        return redirect('perfiles')

    if request.method == 'POST':
        perfiles_activos = Perfil.objects.filter(usuario=request.user, activo=True)
        if perfiles_activos.count() <= 1:
            messages.error(request, 'La cuenta debe conservar al menos un perfil activo.')
            return redirect('perfiles')

        perfil.activo = False
        perfil.save(update_fields=['activo'])
        if request.session.get(SESION_PERFIL_ACTIVO) == perfil.pk:
            request.session.pop(SESION_PERFIL_ACTIVO, None)
        messages.success(request, 'El perfil dejó de mostrarse. Sus datos se conservaron.')
        return redirect('perfiles')

    return render(request, 'confirmar_desactivar_perfil.html', {
        'perfil': perfil,
        'pagina_perfiles': True,
    })


@login_required
def seleccionar_plan_view(request):
    hoy = timezone.localdate()
    precios_vigentes = Precio.objects.filter(fecha_inicio__lte=hoy).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)
    )
    planes = (
        Plan.objects.filter(precios__in=precios_vigentes)
        .distinct()
        .prefetch_related('precios')
        .order_by('nombre')
    )

    if Suscripcion.objects.filter(usuario=request.user, habilitado=True).exists():
        messages.info(request, 'Tu cuenta ya tiene una suscripción activa.')
        return redirect('home')

    if request.method == 'POST':
        plan_id = request.POST.get('plan')
        try:
            plan = planes.get(pk=plan_id)
        except (Plan.DoesNotExist, ValueError, TypeError):
            messages.error(request, 'Selecciona un plan disponible para continuar.')
        else:
            Suscripcion.objects.create(
                usuario=request.user,
                plan=plan,
                fecha_inscripcion=hoy,
                fecha_vigencia=hoy,
            )
            messages.success(request, 'Tu plan quedó asociado a la cuenta.')
            return redirect('home')

    planes_con_precio = []
    for plan in planes:
        precio_actual = (
            precios_vigentes.filter(plan=plan)
            .order_by('-fecha_inicio')
            .first()
        )
        if precio_actual:
            planes_con_precio.append({'plan': plan, 'precio': precio_actual})

    return render(request, 'seleccionar_plan.html', {'planes': planes_con_precio})


def reporte_ventas_view(request):
    form = ReporteVentasFiltroForm(request.GET or None)
    fecha_inicio = None
    fecha_fin = None
    filtros_validos = not request.GET or form.is_valid()

    if filtros_validos and request.GET:
        fecha_inicio = form.cleaned_data['fecha_inicio']
        fecha_fin = form.cleaned_data['fecha_fin']
    elif request.GET:
        messages.error(request, 'Revisa las fechas ingresadas para generar el reporte.')

    miembros_por_plan = []
    precios_qs = Precio.objects.none()
    if filtros_validos:
        suscripciones_qs = Suscripcion.objects.all()
        if fecha_inicio:
            suscripciones_qs = suscripciones_qs.filter(fecha_inscripcion__gte=fecha_inicio)
        if fecha_fin:
            suscripciones_qs = suscripciones_qs.filter(fecha_inscripcion__lte=fecha_fin)

        miembros_por_plan = list(
            suscripciones_qs
            .values(plan_nombre=F('plan__nombre'))
            .annotate(total=Count('id'))
            .order_by('plan_nombre')
        )

        precios_qs = Precio.objects.select_related('plan').order_by('fecha_inicio')
        if fecha_inicio:
            precios_qs = precios_qs.filter(fecha_inicio__gte=fecha_inicio)
        if fecha_fin:
            precios_qs = precios_qs.filter(fecha_inicio__lte=fecha_fin)

    labels_miembros = [item['plan_nombre'] for item in miembros_por_plan]
    data_miembros = [item['total'] for item in miembros_por_plan]
    planes_dict = {}
    fechas_set = set()

    for precio in precios_qs:
        fecha_str = precio.fecha_inicio.strftime('%Y-%m-%d')
        fechas_set.add(fecha_str)
        planes_dict.setdefault(precio.plan.nombre, {})[fecha_str] = float(precio.precio)

    fechas_precio_labels = sorted(fechas_set)
    colores = ['#e50914', '#10b981', '#f59e0b', '#3b82f6', '#8b5cf6']
    datasets_precios = [
        {
            'label': plan_nombre,
            'data': [precios_fechas.get(fecha) for fecha in fechas_precio_labels],
            'borderColor': colores[indice % len(colores)],
            'backgroundColor': colores[indice % len(colores)],
            'tension': 0.2,
            'spanGaps': True,
        }
        for indice, (plan_nombre, precios_fechas) in enumerate(planes_dict.items())
    ]

    es_demostracion = False
    if filtros_validos and not request.GET and not miembros_por_plan and not datasets_precios:
        hoy = timezone.localdate()
        meses = []
        nombres_meses = (
            'ene', 'feb', 'mar', 'abr', 'may', 'jun',
            'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
        )
        for desplazamiento in range(5, -1, -1):
            indice_mes = hoy.year * 12 + hoy.month - 1 - desplazamiento
            anio, mes_cero_indexado = divmod(indice_mes, 12)
            meses.append(f'{anio}-{mes_cero_indexado + 1:02}')
        fechas_precio_labels = meses
        miembros_por_plan = [
            {'plan_nombre': 'Básico', 'total': 128},
            {'plan_nombre': 'Estándar', 'total': 86},
            {'plan_nombre': 'Premium', 'total': 54},
        ]
        labels_miembros = [item['plan_nombre'] for item in miembros_por_plan]
        data_miembros = [item['total'] for item in miembros_por_plan]
        precios_demostracion = (
            ('Básico', [3999, 4499, 4499, 4999, 4999, 5499]),
            ('Estándar', [5999, 6499, 6999, 6999, 7499, 7999]),
            ('Premium', [7999, 8499, 8999, 9499, 9999, 10999]),
        )
        datasets_precios = [
            {
                'label': nombre,
                'data': valores,
                'borderColor': colores[indice],
                'backgroundColor': colores[indice],
                'tension': 0.35,
                'spanGaps': True,
            }
            for indice, (nombre, valores) in enumerate(precios_demostracion)
        ]
        es_demostracion = True

    total_miembros = sum(item['total'] for item in miembros_por_plan)
    precios_actuales = [
        next(
            (valor for valor in reversed(dataset['data']) if valor is not None),
            None,
        )
        for dataset in datasets_precios
    ]
    precios_actuales = [precio for precio in precios_actuales if precio is not None]
    precio_promedio = (
        round(sum(precios_actuales) / len(precios_actuales), 2)
        if precios_actuales else None
    )

    context = {
        'form': form,
        'fecha_inicio': request.GET.get('fecha_inicio', ''),
        'fecha_fin': request.GET.get('fecha_fin', ''),
        'labels_miembros_json': labels_miembros,
        'data_miembros_json': data_miembros,
        'fechas_precio_labels_json': fechas_precio_labels,
        'datasets_precios_json': datasets_precios,
        'total_miembros': total_miembros,
        'cantidad_planes': len(labels_miembros),
        'precio_promedio': precio_promedio,
        'es_demostracion': es_demostracion,
        'pagina_estadisticas': True,
    }
    return render(request, 'reporte_ventas.html', context)
