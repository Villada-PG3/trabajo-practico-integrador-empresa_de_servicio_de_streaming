from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *
from django.utils.html import format_html

# admin default view
admin.site.register([
    Pais, TipoTitulo, Categoria, Idioma, Rol, Elenco, RolElenco,
    Calidad, Calificacion, Titulo, TituloRolElenco, TituloCategoria,
    IdiomaTitulo, Contenido, Subtitulo, IdiomaContenido,
    CalidadIdiomaContenido, PerfilTitulo, Porver, PerfilContenido,
    MarcaTarjeta, MetodoPago, Tarjeta, Plan, PlanCalidad, Precio,
    Suscripcion, EstadoCobro, Cobro, TipoPerfil, Perfil,
    Registro,
])

# aniade una miniatura para imagenes
@admin.register(Imagen)
class ImagenAdmin(admin.ModelAdmin):
   
    list_display = ('nombre', 'mostrar_miniatura')
    readonly_fields = ('mostrar_imagen_detalle',)

    def mostrar_miniatura(self, obj):
        if obj.imagen:
            return format_html('<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;" />', obj.imagen.url)
        return "Sin imagen"
    
    mostrar_miniatura.short_description = 'Miniatura'

    def mostrar_imagen_detalle(self, obj):
        if obj.imagen:
            return format_html('<img src="{}" style="max-width: 600px; max-height: 600px; border: 1px solid #ccc;" />', obj.imagen.url)
        return "Sin imagen"

    mostrar_imagen_detalle.short_description = 'Preview'

# Como Usuario hereda de AbstractUser se debe usar UserAdmin con el decorador de registo
# ademas de para añadir los campos extra 
@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    
    fieldsets = UserAdmin.fieldsets + (
        ("Datos adicionales", {"fields": ("telefono", "pais", "idioma")}),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Datos adicionales", {"fields": ("telefono", "pais", "idioma")}),
    )
