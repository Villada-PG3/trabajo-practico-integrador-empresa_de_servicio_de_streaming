from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from .models import (
    Pais, TipoTitulo, Categoria, Idioma, Rol, Elenco, RolElenco,
    Calidad, Calificacion, Titulo, TituloRolElenco, TituloCategoria,
    IdiomaTitulo, Contenido, Subtitulo, IdiomaContenido, CalidadIdiomaContenido,
    PerfilTitulo, Porver, PerfilContenido, MarcaTarjeta, MetodoPago, Tarjeta,
    Plan, PlanCalidad, Precio, Suscripcion, CambioPlan, EstadoCobro, Cobro,
    Imagen, Usuario, TipoPerfil, Perfil, Registro
)

# --- FORMS PARA USUARIO PERSONALIZADO ---

class UsuarioCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ('username', 'email', 'telefono', 'pais', 'idioma')


class UsuarioChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Usuario
        fields = '__all__'


# --- INLINES (Deben ir ARRIBA antes de ser usados en los Admin) ---

class ContenidoInline(admin.TabularInline):
    model = Contenido
    extra = 1

class TituloCategoriaInline(admin.TabularInline):
    model = TituloCategoria
    extra = 1

class IdiomaTituloInline(admin.TabularInline):
    model = IdiomaTitulo
    extra = 1

class PlanCalidadInline(admin.TabularInline):
    model = PlanCalidad
    extra = 1

class PrecioInline(admin.TabularInline):
    model = Precio
    extra = 1


# --- MODEL ADMINS PERSONALIZADOS ---

@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    add_form = UsuarioCreationForm
    form = UsuarioChangeForm
    fieldsets = UserAdmin.fieldsets + (
        ('Datos de cuenta', {'fields': ('telefono', 'pais', 'idioma')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Datos de cuenta', {'fields': ('email', 'telefono', 'pais', 'idioma')}),
    )
    list_display = ('username', 'email', 'telefono', 'pais', 'idioma', 'is_staff')
    search_fields = ('username', 'email', 'telefono')

@admin.register(Titulo)
class TituloAdmin(admin.ModelAdmin):
    list_display = ('nombre_original', 'tipo_titulo', 'pais', 'fecha_estreno', 'edad_minima')
    list_filter = ('tipo_titulo', 'pais', 'fecha_estreno')
    search_fields = ('nombre_original', 'descripcion_original')
    inlines = [TituloCategoriaInline, IdiomaTituloInline, ContenidoInline]

@admin.register(Contenido)
class ContenidoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'titulo', 'seccion', 'orden', 'duracion_segundos')
    list_filter = ('titulo', 'seccion')
    search_fields = ('nombre', 'titulo__nombre_original')

@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'usuario', 'tipo_perfil', 'activo')
    list_filter = ('tipo_perfil', 'activo')
    search_fields = ('nombre', 'usuario__username')

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cantidad_pantallas_simultaneas')
    inlines = [PlanCalidadInline, PrecioInline]

@admin.register(Suscripcion)
class SuscripcionAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'plan', 'fecha_inscripcion', 'fecha_vigencia', 'habilitado')
    list_filter = ('plan', 'habilitado')
    search_fields = ('usuario__username', 'usuario__email')

@admin.register(Cobro)
class CobroAdmin(admin.ModelAdmin):
    list_display = ('num_factura', 'suscripcion', 'monto', 'fecha_cobro', 'estado_cobro')
    list_filter = ('estado_cobro', 'fecha_cobro')
    search_fields = ('num_factura', 'suscripcion__usuario__username')

@admin.register(CalidadIdiomaContenido)
class CalidadIdiomaContenidoAdmin(admin.ModelAdmin):
    pass


# --- REGISTRO MASIVO (Solo modelos que NO tienen @admin.register arriba) ---

admin.site.register([
    Calidad,
    Calificacion,
    Categoria,
    Elenco,
    EstadoCobro,
    Idioma,
    IdiomaContenido,
    IdiomaTitulo,
    Imagen,
    MarcaTarjeta,
    MetodoPago,
    Pais,
    PerfilContenido,
    PerfilTitulo,
    PlanCalidad,
    Precio,
    Porver,
    Registro,
    Rol,
    RolElenco,
    Subtitulo,
    Tarjeta,
    TipoPerfil,
    TipoTitulo,
    TituloCategoria,
    TituloRolElenco,
    CambioPlan,
])