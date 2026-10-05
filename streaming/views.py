from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages


def home(request):
    """Vista para la landing page / página de inicio pública"""
    return render(request, 'home.html')

import json
from django.shortcuts import render
from django.db.models import Count, F
from django.utils.dateparse import parse_date

# Modelos con los nombres exactos definidos en tu models.py
from .models import Precio, Suscripcion, Plan

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
        .order_by('plan_nombre')
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