from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, ExpressionWrapper, F, FloatField, Prefetch, Q
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import LoginForm, RegistroForm, ReporteVentasFiltroForm
from .models import Categoria, Contenido, Imagen, Plan, Precio, Suscripcion, Titulo

LIMITE_TITULOS_CARRUSEL = 30


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
        clasificaciones_edad = sorted(
            (categoria for categoria in categorias if categoria.es_edad),
            key=lambda categoria: categoria.nombre.casefold(),
        )
        titulo.clasificacion_edad = clasificaciones_edad[0] if clasificaciones_edad else None
        titulo.categorias_ordenadas = sorted(
            (categoria for categoria in categorias if not categoria.es_edad),
            key=lambda categoria: (
                categoria_prioritaria is not None
                and categoria.pk != categoria_prioritaria.pk,
                categoria.nombre.casefold(),
            ),
        )
    return titulos


def home(request):
    cantidad_populares = LIMITE_TITULOS_CARRUSEL if request.user.is_authenticated else 10
    suscripcion_actual = None
    if request.user.is_authenticated:
        suscripcion_actual = (
            Suscripcion.objects.filter(usuario=request.user, habilitado=True)
            .select_related('plan')
            .order_by('-fecha_inscripcion')
            .first()
        )

    imagenes_banner = Prefetch(
        'imagen_set',
        queryset=Imagen.objects.filter(es_banner=True).order_by('id'),
        to_attr='imagenes_banner',
    )
    imagenes_catalogo = Prefetch(
        'imagen_set',
        queryset=Imagen.objects.order_by('id'),
        to_attr='imagenes_catalogo',
    )
    contenidos_catalogo = Prefetch(
        'contenidos',
        queryset=Contenido.objects.order_by('id'),
        to_attr='contenidos_catalogo',
    )
    relaciones_elenco = 'titulo_rol_elencos__rol_elenco__elenco'
    titulos_con_contenido = (
        Titulo.objects.filter(contenidos__isnull=False)
        .distinct()
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
            imagenes_banner,
            imagenes_catalogo,
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
    mas_reproducidos_query = (
        Titulo.objects.filter(
            contenidos__isnull=False,
            contenidos__duracion_segundos__gt=0,
        )
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
            imagenes_banner,
            imagenes_catalogo,
            contenidos_catalogo,
        )
        .order_by('-reproducciones', '-fecha_estreno', 'nombre_original')
    )
    mas_reproducidos = ordenar_categorias_titulo(
        list(mas_reproducidos_query[:cantidad_populares])
    )
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
        for etiqueta, prefijo in tipos:
            titulos = ordenar_categorias_titulo(list(
                titulos_con_contenido.filter(
                    tipo_titulo__nombre__istartswith=prefijo
                )[:LIMITE_TITULOS_CARRUSEL]
            ))
            if titulos:
                carruseles.append({'etiqueta': etiqueta, 'titulos': titulos})

        categorias = Categoria.objects.filter(
            titulo_categorias__titulo__contenidos__isnull=False
        ).filter(es_edad=False).distinct().order_by('nombre')
        for categoria in categorias:
            titulos = ordenar_categorias_titulo(list(
                titulos_con_contenido.filter(
                    titulo_categorias__categoria=categoria
                )[:LIMITE_TITULOS_CARRUSEL]
            ), categoria_prioritaria=categoria)
            if titulos:
                carruseles.append({'etiqueta': categoria.nombre, 'titulos': titulos})

    banners = []
    if request.user.is_authenticated:
        titulos_banner = titulos_con_contenido.filter(
            fecha_estreno__isnull=False,
            imagen__es_banner=True,
        ).distinct()[:5]
        for titulo in titulos_banner:
            nombres_elenco = []
            for relacion in titulo.titulo_rol_elencos.all():
                persona = relacion.rol_elenco.elenco
                nombre = f'{persona.nombre} {persona.apellido}'
                if nombre not in nombres_elenco:
                    nombres_elenco.append(nombre)
            imagen_banner = titulo.imagenes_banner[0] if titulo.imagenes_banner else None
            banners.append({
                'titulo': titulo,
                'elenco': nombres_elenco[:4],
                'imagen_url': imagen_banner.imagen.url if imagen_banner and imagen_banner.imagen else '',
            })

    return render(request, 'home.html', {
        'suscripcion_actual': suscripcion_actual,
        'carruseles': carruseles,
        'banners': banners,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

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
            if not Suscripcion.objects.filter(usuario=user, habilitado=True).exists():
                return redirect('seleccionar_plan')
            return redirect('home')
        form.add_error(None, 'Correo electrónico o contraseña incorrectos.')

    return render(request, 'login.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('home')


def registro_view(request):
    if request.user.is_authenticated:
        return redirect('seleccionar_plan')

    initial = {'email': request.GET.get('email', '').strip().lower()}
    form = RegistroForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('seleccionar_plan')
    return render(request, 'registro.html', {'form': form})


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
