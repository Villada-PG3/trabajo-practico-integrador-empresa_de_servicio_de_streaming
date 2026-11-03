from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Usuario, Pais, Idioma, Plan, Precio, 
    MarcaTarjeta, MetodoPago, Suscripcion, Cobro, EstadoCobro, Titulo, Categoria
)

# Registrar modelo de Usuario personalizado
admin.site.register(Usuario, UserAdmin)

# Registrar modelos secundarios y auxiliares
admin.site.register(Pais)
admin.site.register(Idioma)
admin.site.register(Plan)
admin.site.register(Precio)
admin.site.register(MarcaTarjeta)
admin.site.register(MetodoPago)
admin.site.register(Suscripcion)
admin.site.register(Cobro)
admin.site.register(EstadoCobro)
admin.site.register(Titulo)
admin.site.register(Categoria)