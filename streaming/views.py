from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib import messages
import calendar
from django.db.models import Count, F, Q
from django.utils.dateparse import parse_date
from .models import *
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
            return redirect('seleccionar_perfil')
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
    password2 = request.POST.get('password2')
    telefono = request.POST.get('telefono')

    if password != password2:
        messages.error(request, 'Las contraseñas no coinciden')

    if User.objects.filter(email=email).exists():
      messages.error(request, 'Ya existe una cuenta asociada a este correo.')
    else:
      user = User.objects.create_user(
          username=email,
          email=email,
          password=password,
          telefono=telefono,
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
    
    plan = Plan.objects.get(id=plan_id)
    
    # nos van a hacer falta en el POST para redireccionar si hay errores
    marcas = MarcaTarjeta.objects.all()
    precio_obj = plan.precios.order_by('-fecha_inicio').first()
    precio_monto = precio_obj.precio if precio_obj else 0.0
    
    context =  {
        'plan': plan,
        'precio_monto': precio_monto,
        'marcas': marcas
    }
    
    if request.method == 'POST':
        numero_tarjeta = request.POST.get('numero_tarjeta')
        fecha_vencimiento = request.POST.get('fecha_vencimiento') 
        marca_id = request.POST.get('marca_tarjeta')
        
        try:
            mes, anio = fecha_vencimiento.split("/")
            ultimo_dia = calendar.monthrange(int(anio), int(mes))[1]
            vencimiento = date(int(anio), int(mes), ultimo_dia)
        except ValueError:
            messages.error(request, "Usá el formato MM/AAAA, por ejemplo 08/2028")
            context["datos"] = request.POST
            return render(request, 'pago.html', context=context)
            
        if vencimiento < date.today():
            messages.error(request, "La tarjeta está vencida.")
            context["datos"] = request.POST
            return render(request, 'pago.html', context=context)
        
        marca = MarcaTarjeta.objects.get(pk=marca_id)
        metodo, _ = MetodoPago.objects.get_or_create(nombre='Tarjeta de Crédito/Débito')
        
        # Guardar la tarjeta
        tarjeta = Tarjeta.objects.create(
            numero=numero_tarjeta[-4:],
            fecha_vencimiento=vencimiento,
            marca_tarjeta=marca,
            metodo_pago=metodo,
            habilitado=True
        )
        
        # 2. Crear Suscripción activa
        suscripcion = Suscripcion.objects.create(
            tarjeta=tarjeta,
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
            suscripcion=suscripcion,
            fecha_cobro=date.today(),
            estado_cobro=estado_aprobado,
            tarjeta=tarjeta,
            numero_autorizacion='AUTH-' + str(timezone.now().timestamp()).replace('.', ''),
            monto=monto
        )
        
        messages.success(request, f'¡Suscripción al plan {plan.nombre} realizada con éxito!')
        return redirect('seleccionar_perfil')

    return render(request, 'pago.html', context=context)

def seleccionar_perfil_view(request):
    """Pantalla para elegir quién está viendo (Perfiles del usuario)"""
    perfiles = request.user.perfil_set.all() if hasattr(request.user, 'perfil_set') else []
    return render(request, 'seleccionar_perfil.html', {'perfiles': perfiles})


def seleccionar_perfil_view(request):
    """Muestra los perfiles creados del usuario autenticado"""
    perfiles = Perfil.objects.filter(usuario=request.user)
    return render(request, 'seleccionar_perfil.html', {'perfiles': perfiles})

def crear_perfil_view(request):
    """Crea un nuevo perfil para el usuario autenticado"""
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        tipo_default = TipoPerfil.objects.first()
        imagen_default = Imagen.objects.first()
        
        Perfil.objects.create(
            nombre=nombre,
            usuario=request.user,
            tipo_perfil=tipo_default,
            imagen=imagen_default
        )
        messages.success(request, f'Perfil "{nombre}" creado con éxito.')
    return redirect('seleccionar_perfil')
 
def get_perfil(request, perfil_id):
    # usuario=request.user impide entrar a perfiles ajenos cambiando el numero de la URL
    return get_object_or_404(Perfil, pk=perfil_id, usuario=request.user)
 
 
def get_portada(titulo_id):
    # Las portadas son archivos sueltos: MEDIA_ROOT/portada/titulo{id}.png (no pasan por el modelo Imagen).
    # Si el archivo no existe devuelve None y la template muestra el cartel con el nombre.
    ruta = f"portada/titulo{titulo_id}.png"
    return default_storage.url(ruta) if default_storage.exists(ruta) else None
 
 
@login_required
def catalogo(request, perfil_id):
    perfil = get_perfil(request, perfil_id)
    hoy = date.today()
 
    # Una sola consulta: cada fila es un par (titulo, categoria). Solo titulos ya estrenados y no dados de baja.
    relaciones = (
        TituloCategoria.objects
        .filter(
            Q(titulo__fecha_estreno__isnull=True) | Q(titulo__fecha_estreno__lte=hoy),
            Q(titulo__fecha_baja__isnull=True) | Q(titulo__fecha_baja__gte=hoy),
        )
        .select_related("categoria", "titulo", "titulo__tipo_titulo")
        .order_by("categoria__nombre", "titulo__nombre_original")
    )
 
    filas = {}      # categoria_id -> {"nombre": ..., "titulos": [...]}
    por_id = {}     # titulo_id -> instancia (para armar la fila "Mi lista" sin consultas extra)
    portadas = {}   # titulo_id -> url (un titulo puede estar en varias categorias: se resuelve una sola vez)
    for r in relaciones:
        if r.titulo_id not in portadas:
            portadas[r.titulo_id] = get_portada(r.titulo_id)
        r.titulo.portada = portadas[r.titulo_id]
        por_id.setdefault(r.titulo_id, r.titulo)
        fila = filas.setdefault(r.categoria_id, {"nombre": r.categoria.nombre, "titulos": []})
        fila["titulos"].append(r.titulo)
    filas = list(filas.values())
 
    # Mi lista = filas de Porver sin fecha_eliminado del perfil activo (mas reciente primero)
    ids_mi_lista = list(dict.fromkeys(
        Porver.objects
        .filter(perfil_titulo__perfil=perfil, fecha_eliminado__isnull=True)
        .order_by("-fecha_agregado", "-id")
        .values_list("perfil_titulo__titulo_id", flat=True)
    ))
    mi_lista = [por_id[i] for i in ids_mi_lista if i in por_id]
    if mi_lista:
        filas.insert(0, {"nombre": "Mi lista", "titulos": mi_lista})
 
    return render(request, "catalogo.html", {
        "perfil": perfil,
        "filas": filas,                       # [{"nombre": str, "titulos": [Titulo con .portada]}]
        "en_mi_lista": set(ids_mi_lista),     # ids de titulos para marcar el boton
    })
 
 
@login_required
@require_POST
def toggle_mi_lista(request, perfil_id, titulo_id):
    perfil = get_perfil(request, perfil_id)
    titulo = get_object_or_404(Titulo, pk=titulo_id)
 
    perfil_titulo = (
        PerfilTitulo.objects.filter(perfil=perfil, titulo=titulo).first()
        or PerfilTitulo.objects.create(perfil=perfil, titulo=titulo)
    )
    activo = Porver.objects.filter(perfil_titulo=perfil_titulo, fecha_eliminado__isnull=True).first()
 
    if activo:  # ya estaba en la lista: se "elimina" (queda el historial con fecha_eliminado)
        activo.fecha_eliminado = date.today()
        activo.save(update_fields=["fecha_eliminado"])
    else:
        Porver.objects.create(perfil_titulo=perfil_titulo, fecha_agregado=date.today())
 
    return redirect("catalogo", perfil_id=perfil.id)
 
