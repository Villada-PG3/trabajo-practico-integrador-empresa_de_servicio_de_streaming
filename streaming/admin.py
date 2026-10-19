from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import (
    Calidad,
    CalidadIdiomaContenido,
    Calificacion,
    Categoria,
    Cobro,
    Contenido,
    Elenco,
    EstadoCobro,
    Idioma,
    IdiomaContenido,
    IdiomaTitulo,
    Imagen,
    MarcaTarjeta,
    MetodoPago,
    Pais,
    Perfil,
    PerfilContenido,
    PerfilTitulo,
    Plan,
    PlanCalidad,
    Precio,
    Porver,
    Registro,
    Rol,
    RolElenco,
    Subtitulo,
    Suscripcion,
    Tarjeta,
    TipoPerfil,
    TipoTitulo,
    Titulo,
    TituloCategoria,
    TituloRolElenco,
    Usuario,
)


class UsuarioCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ('username', 'email', 'telefono', 'pais', 'idioma')


class UsuarioChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Usuario
        fields = '__all__'


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


admin.site.register([
    Calidad,
    CalidadIdiomaContenido,
    Calificacion,
    Categoria,
    Cobro,
    Contenido,
    Elenco,
    EstadoCobro,
    Idioma,
    IdiomaContenido,
    IdiomaTitulo,
    Imagen,
    MarcaTarjeta,
    MetodoPago,
    Pais,
    Perfil,
    PerfilContenido,
    PerfilTitulo,
    Plan,
    PlanCalidad,
    Precio,
    Porver,
    Registro,
    Rol,
    RolElenco,
    Subtitulo,
    Suscripcion,
    Tarjeta,
    TipoPerfil,
    TipoTitulo,
    Titulo,
    TituloCategoria,
    TituloRolElenco,
])
