from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import LoginForm, RegistroForm, ReporteVentasFiltroForm
from .models import Plan, Precio, Suscripcion


def home(request):
    suscripcion_actual = None
    if request.user.is_authenticated:
        suscripcion_actual = (
            Suscripcion.objects.filter(usuario=request.user, habilitado=True)
            .select_related('plan')
            .order_by('-fecha_inscripcion')
            .first()
        )
    return render(request, 'home.html', {'suscripcion_actual': suscripcion_actual})


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
