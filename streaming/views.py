from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import (
    Case,
    CharField,
    Count,
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
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import LoginForm, PerfilForm, RegistroForm, ReporteVentasFiltroForm
from .models import (
    Categoria,
    Contenido,
    IdiomaTitulo,
    Plan,
    Perfil,
    PerfilTitulo,
    Porver,
    Precio,
    Suscripcion,
    Titulo,
)

LIMITE_TITULOS_CARRUSEL = 30
LIMITE_PERFILES = 5
SESION_PERFIL_ACTIVO = 'perfil_activo_id'


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


def marcar_estado_mi_lista(titulos, titulos_guardados):
    for titulo in titulos:
        titulo.en_mi_lista = titulo.pk in titulos_guardados
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

    cantidad_populares = LIMITE_TITULOS_CARRUSEL if request.user.is_authenticated else 10
    suscripcion_actual = None
    if request.user.is_authenticated:
        suscripcion_actual = (
            Suscripcion.objects.filter(usuario=request.user, habilitado=True)
            .select_related('plan')
            .order_by('-fecha_inscripcion')
            .first()
        )

    imagenes_catalogo = Prefetch(
        'idioma_titulos',
        queryset=IdiomaTitulo.objects.exclude(imagen='').order_by('idioma__nombre', 'id'),
        to_attr='imagenes_catalogo',
    )
    textos_catalogo = Prefetch(
        'idioma_titulos',
        queryset=IdiomaTitulo.objects.select_related('idioma').order_by('idioma__nombre', 'id'),
        to_attr='idiomas_texto',
    )
    contenidos_catalogo = Prefetch(
        'contenidos',
        queryset=Contenido.objects.order_by('id'),
        to_attr='contenidos_catalogo',
    )
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
            'etiqueta': 'Más reproducidos',
            'titulos': mas_reproducidos,
            'mostrar_top': not request.user.is_authenticated,
        })

    if request.user.is_authenticated:
        tipos = (
            ('Películas', 'pel'),
            ('Series', 'ser'),
        )
        if prefijo_tipo:
            tipos = tuple(
                tipo for tipo in tipos if tipo[1] == prefijo_tipo
            )
        for etiqueta, prefijo in tipos:
            titulos = marcar_estado_mi_lista(
                ordenar_categorias_titulo(list(
                    titulos_con_contenido.filter(
                        tipo_titulo__nombre__istartswith=prefijo
                    )[:LIMITE_TITULOS_CARRUSEL]
                )),
                titulos_guardados,
            )
            asignar_textos_titulo(titulos, getattr(request.user, 'idioma_id', None))
            if titulos:
                carruseles.append({'etiqueta': etiqueta, 'titulos': titulos})

        categorias = Categoria.objects.filter(
            titulo_categorias__titulo__contenidos__isnull=False
        ).distinct().order_by('nombre')
        if prefijo_tipo:
            categorias = categorias.filter(
                titulo_categorias__titulo__tipo_titulo__nombre__istartswith=prefijo_tipo
            )
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
                carruseles.append({'etiqueta': categoria.nombre, 'titulos': titulos})

    banners = []
    if request.user.is_authenticated:
        titulos_banner = titulos_con_contenido.filter(
            fecha_estreno__isnull=False,
            idioma_titulos__imagen__gt='',
        )
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

    return render(request, 'home.html', {
        'suscripcion_actual': suscripcion_actual,
        'carruseles': carruseles,
        'banners': banners,
        'filtro_tipo': filtro_tipo,
        'url_actual': request.get_full_path(),
    })


@login_required
@require_GET
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
            }
            for titulo in titulos
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
        )
        .prefetch_related(imagenes_titulo, textos_titulo)
        .order_by(*ordenamientos[orden])
    )
    titulos_por_ver_lista = list(titulos_por_ver)
    asignar_textos_titulo(
        [
            porver.perfil_titulo.titulo
            for porver in titulos_por_ver_lista
        ],
        request.user.idioma_id,
    )
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
        user = authenticate(
            request,
            username=email,
            password=form.cleaned_data['password'],
        )
        if user is not None:
            login(request, user)
            if not form.data.get('remember_me'):
                request.session.set_expiry(0)
            if Perfil.objects.filter(usuario=user, activo=True).exists():
                return redirect('perfiles')
            return redirect('crear_perfil')
        form.add_error(None, 'Correo electrónico o contraseña incorrectos.')

    return render(request, 'login.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
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
        return redirect('crear_perfil')
    return render(request, 'registro.html', {'form': form})


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

    context = {
        'form': form,
        'fecha_inicio': request.GET.get('fecha_inicio', ''),
        'fecha_fin': request.GET.get('fecha_fin', ''),
        'labels_miembros_json': labels_miembros,
        'data_miembros_json': data_miembros,
        'fechas_precio_labels_json': fechas_precio_labels,
        'datasets_precios_json': datasets_precios,
    }
    return render(request, 'reporte_ventas.html', context)
