from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib import messages
import json
from django.db.models import Count, F
from django.utils.dateparse import parse_date
from .models import Idioma, Precio, Suscripcion, Plan, Tarjeta, MarcaTarjeta, MetodoPago, Cobro, EstadoCobro
from django.contrib.auth.models import User
from datetime import date
from django.utils import timezone

User = get_user_model()

def home(request):
    """Vista para la landing page / página de inicio pública"""
    return render(request, 'home.html')

def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('username')
        password = request.POST.get('password')
        
        # Validar credenciales
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            login(request, user)
            # Redirige a la pantalla de selección de perfil una vez autenticado
            return redirect('home')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
    
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    return redirect('home')

def reporte_ventas_view(request):
    # Capturar fechas del filtro (GET)
    fecha_inicio_str = request.GET.get('fecha_inicio')
    fecha_fin_str = request.GET.get('fecha_fin')

    fecha_inicio = parse_date(fecha_inicio_str) if fecha_inicio_str else None
    fecha_fin = parse_date(fecha_fin_str) if fecha_fin_str else None

    # ------------------------------------------------------------------
    # 1. Cantidad de miembros por plan en el período
    # ------------------------------------------------------------------
    suscripciones_qs = Suscripcion.objects.all()
    if fecha_inicio:
        suscripciones_qs = suscripciones_qs.filter(fecha_inscripcion__gte=fecha_inicio)
    if fecha_fin:
        suscripciones_qs = suscripciones_qs.filter(fecha_inscripcion__lte=fecha_fin)

    miembros_por_plan = (
        suscripciones_qs
        .values(plan_nombre=F('plan__nombre'))
        .annotate(total=Count('id'))
        .order_by('plan__nombre')
    )

    labels_miembros = [item['plan_nombre'] for item in miembros_por_plan]
    data_miembros = [item['total'] for item in miembros_por_plan]

    # ------------------------------------------------------------------
    # 2. Variación de precios en el período
    # ------------------------------------------------------------------
    precios_qs = Precio.objects.select_related('plan').order_by('fecha_inicio')
    if fecha_inicio:
        precios_qs = precios_qs.filter(fecha_inicio__gte=fecha_inicio)
    if fecha_fin:
        precios_qs = precios_qs.filter(fecha_inicio__lte=fecha_fin)

    planes_dict = {}
    fechas_set = set()

    for p in precios_qs:
        fecha_str = p.fecha_inicio.strftime('%Y-%m-%d')
        fechas_set.add(fecha_str)
        nombre_plan = p.plan.nombre
        
        if nombre_plan not in planes_dict:
            planes_dict[nombre_plan] = {}
        planes_dict[nombre_plan][fecha_str] = float(p.precio)

    fechas_precio_labels = sorted(list(fechas_set))

    datasets_precios = []
    colores = ['#e50914', '#10b981', '#f59e0b', '#3b82f6', '#8b5cf6']
    
    for idx, (plan_nombre, precios_fechas) in enumerate(planes_dict.items()):
        data_puntos = [precios_fechas.get(f, None) for f in fechas_precio_labels]
        color = colores[idx % len(colores)]
        datasets_precios.append({
            'label': plan_nombre,
            'data': data_puntos,
            'borderColor': color,
            'backgroundColor': color,
            'tension': 0.2,
            'spanGaps': True
        })

    context = {
        'fecha_inicio': fecha_inicio_str or '',
        'fecha_fin': fecha_fin_str or '',
        'labels_miembros_json': labels_miembros,
        'data_miembros_json': data_miembros,
        'fechas_precio_labels_json': fechas_precio_labels,
        'datasets_precios_json': datasets_precios,
    }

    return render(request, 'reporte_ventas.html', context)




def registro_view(request):
  if request.method == 'POST':
    email = request.POST.get('email')
    password = request.POST.get('password')
    telefono = request.POST.get('telefono')

    if User.objects.filter(email=email).exists():
      messages.error(request, 'Ya existe una cuenta asociada a este correo.')
    else:
      idioma_predeterminado = Idioma.objects.first()

      user = User.objects.create_user(
          username=email,
          email=email,
          password=password,
          telefono=telefono,
          idioma=idioma_predeterminado,  
      )


      login(request, user)

      return redirect('seleccionar_plan')

  return render(request, 'registro.html')


def seleccionar_plan(request):
  if request.method == 'POST':
    plan_id = request.POST.get('plan_id')
    request.session['plan_id'] = plan_id
    return redirect('pago')

  return render(request, 'seleccionar_plan.html')



def pago_view(request):
    """Procesa el pago con tarjeta y genera la primera suscripción + factura"""
    plan_id = request.session.get('plan_id')
    if not plan_id:
        messages.error(request, 'Debes seleccionar un plan antes de proceder al pago.')
        return redirect('seleccionar_plan')
    
    plan = Plan.objects.get(pk=plan_id)
    
    if request.method == 'POST':
        nombre_titular = request.POST.get('nombre_titular')
        numero_tarjeta = request.POST.get('numero_tarjeta')
        fecha_vencimiento = request.POST.get('fecha_vencimiento') # YYYY-MM-DD
        marca_id = request.POST.get('marca_tarjeta')
        
        marca = MarcaTarjeta.objects.get(pk=marca_id)
        metodo, _ = MetodoPago.objects.get_or_create(nombre='Tarjeta de Crédito/Débito')
        
        # 1. Guardar tarjeta (solo guardando los últimos 4 dígitos como está en su modelo)
        tarjeta = Tarjeta.objects.create(
            numero=numero_tarjeta[-4:],
            nombre_titular=nombre_titular,
            fecha_vencimiento=parse_date(fecha_vencimiento) or date.today(),
            marca_tarjeta=marca,
            metodo_pago=metodo,
            habilitado=True
        )
        
        # 2. Crear Suscripción activa
        suscripcion = Suscripcion.objects.create(
            usuario=request.user,
            plan=plan,
            fecha_inscripcion=date.today(),
            habilitado=True
        )
        
        # 3. Registrar primer Cobro / Factura
        estado_aprobado, _ = EstadoCobro.objects.get_or_create(nombre='Aprobado')
        precio_actual = plan.precios.order_by('-fecha_inicio').first()
        monto = precio_actual.precio if precio_actual else 0.0
        
        Cobro.objects.create(
            num_factura=3000000000 + Cobro.objects.count() + 1,
            suscripcion=suscripcion,
            fecha_cobro=date.today(),
            estado_cobro=estado_aprobado,
            tarjeta=tarjeta,
            numero_autorizacion='AUTH-' + str(timezone.now().timestamp()).replace('.', ''),
            monto=monto
        )
        
        messages.success(request, f'¡Suscripción al plan {plan.nombre} realizada con éxito!')
        return redirect('home')

    marcas = MarcaTarjeta.objects.all()
    precio_obj = plan.precios.order_by('-fecha_inicio').first()
    precio_monto = precio_obj.precio if precio_obj else 0.0

    return render(request, 'pago.html', {
        'plan': plan,
        'precio_monto': precio_monto,
        'marcas': marcas
    })

def seleccionar_perfil_view(request):
    """Pantalla para elegir quién está viendo (Perfiles del usuario)"""
    perfiles = request.user.perfil_set.all() if hasattr(request.user, 'perfil_set') else []
    return render(request, 'seleccionar_perfil.html', {'perfiles': perfiles})