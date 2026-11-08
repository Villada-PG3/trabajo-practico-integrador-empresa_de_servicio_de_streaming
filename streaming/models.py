from django.db.models import *
from django.db import models
from django.contrib.auth.models import AbstractUser
from phonenumber_field.modelfields import PhoneNumberField
from django.utils.text import slugify
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator

def idioma_default():
    try:
        return Idioma.objects.get_or_create(id=1, nombre="Español")[0].pk
    except Exception as e:
        print("no existen idiomas cargados y por ende no hay default")
        print(e)


def pais_default():
    try:
        return Pais.objects.get_or_create(id=1, nombre="Argentina")[0].pk
    except Exception as e:
        print("no existen paises cargados y por ende no hay default")
        print(e)

# instance es el objeto Imagen que se está guardando
def imagen_upload_path(instance, filename):
    carpeta = slugify(instance.titulo.nombre_original)
    return f'perfil/{carpeta}/{filename}'

class Pais(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'País'
        verbose_name_plural = 'Países'

    def __str__(self):
        return self.nombre 


class TipoTitulo(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Tipo de título'
        verbose_name_plural = 'Tipos de título'

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return self.nombre


class Idioma(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Idioma'
        verbose_name_plural = 'Idiomas'

    def __str__(self):
        return self.nombre


class Rol(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.nombre


class Elenco(models.Model):
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, related_name='elencos')
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Elenco'
        verbose_name_plural = 'Elencos'

    def __str__(self):
        return f'{self.nombre} {self.apellido}'


class RolElenco(models.Model):
    # Un elenco puede tener varios roles
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name='rol_elencos')
    elenco = models.ForeignKey(Elenco, on_delete=models.CASCADE, related_name='rol_elencos')

    class Meta:
        verbose_name = 'Rol de elenco'
        verbose_name_plural = 'Roles de elenco'

    def __str__(self):
        return f'{self.elenco} - {self.rol}'


class Calidad(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Calidad'
        verbose_name_plural = 'Calidades'

    def __str__(self):
        return self.nombre


class Calificacion(models.Model):
    nombre = models.CharField(max_length=100)
    porcentaje_gusto = models.FloatField()

    class Meta:
        verbose_name = 'Calificación'
        verbose_name_plural = 'Calificaciones'

    def __str__(self):
        return self.nombre


class Titulo(models.Model):
    nombre_original = models.CharField(max_length=255)
    descripcion_original = models.TextField(blank=True, null=True)
    tipo_titulo = models.ForeignKey(TipoTitulo, on_delete=models.PROTECT, related_name='titulos')
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, related_name='titulos')
    fecha_estreno = models.DateField(blank=True, null=True)
    fecha_baja = models.DateField(blank=True, null=True)

    class Meta:
        verbose_name = 'Título'
        verbose_name_plural = 'Títulos'

    def __str__(self):
        return self.nombre_original


class TituloRolElenco(models.Model):
    rol_elenco = models.ForeignKey(RolElenco, on_delete=models.CASCADE, related_name='titulo_rol_elencos')
    titulo = models.ForeignKey(Titulo, on_delete=models.CASCADE, related_name='titulo_rol_elencos')

    class Meta:
        verbose_name = 'Rol de elenco del título'
        verbose_name_plural = 'Roles de elenco del título'

    def __str__(self):
        return f'{self.titulo} - {self.rol_elenco}'


class TituloCategoria(models.Model):
    titulo = models.ForeignKey(Titulo, on_delete=models.CASCADE, related_name='titulo_categorias')
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name='titulo_categorias')

    class Meta:
        verbose_name = 'Categoría del título'
        verbose_name_plural = 'Categorías del título'

    def __str__(self):
        return f'{self.titulo} - {self.categoria}'


class IdiomaTitulo(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    idioma = models.ForeignKey(Idioma, on_delete=models.CASCADE, related_name='idioma_titulos')
    titulo = models.ForeignKey(Titulo, on_delete=models.CASCADE, related_name='idioma_titulos')

    class Meta:
        verbose_name = 'Idioma del título'
        verbose_name_plural = 'Idiomas del título'

    def __str__(self):
        return f'{self.titulo} ({self.idioma})'


class Contenido(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    seccion = models.IntegerField()
    orden = models.IntegerField()
    titulo = models.ForeignKey(Titulo, on_delete=models.CASCADE, related_name='contenidos')

    class Meta:
        verbose_name = 'Contenido'
        verbose_name_plural = 'Contenidos'

    def __str__(self):
        return self.nombre


class Subtitulo(models.Model):
    contenido = models.ForeignKey(Contenido, on_delete=models.CASCADE, related_name='subtitulos')
    idioma = models.ForeignKey(Idioma, on_delete=models.PROTECT, related_name='subtitulos')
    archivo_vtt = models.FileField()

    class Meta:
        verbose_name = 'Subtítulo'
        verbose_name_plural = 'Subtítulos'

    def __str__(self):
        return f'{self.contenido} - {self.idioma}'


class IdiomaContenido(models.Model):
    idioma = models.ForeignKey(Idioma, on_delete=models.CASCADE, related_name='idioma_contenidos')
    contenido = models.ForeignKey(Contenido, on_delete=models.CASCADE, related_name='idioma_contenidos')

    class Meta:
        verbose_name = 'Idioma del contenido'
        verbose_name_plural = 'Idiomas del contenido'

    def __str__(self):
        return f'{self.contenido} - {self.idioma}'


class CalidadIdiomaContenido(models.Model):
    idioma_contenido = models.ForeignKey(IdiomaContenido, on_delete=models.CASCADE, related_name='calidades')
    calidad = models.ForeignKey(Calidad, on_delete=models.PROTECT, related_name='calidad_idioma_contenidos')
    archivo = models.FileField()

    class Meta:
        verbose_name = 'Calidad del idioma del contenido'
        verbose_name_plural = 'Calidades del idioma del contenido'

    def __str__(self):
        return f'{self.idioma_contenido} - {self.calidad}'


class PerfilTitulo(models.Model):
    # Historial de titulos vistos por un perfil, con su calificacion (para recomendaciones)
    perfil = models.ForeignKey('Perfil', on_delete=models.CASCADE, related_name='perfil_titulos')
    titulo = models.ForeignKey(Titulo, on_delete=models.CASCADE, related_name='perfil_titulos')
    calificacion = models.ForeignKey(
        Calificacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='perfil_titulos'
    )

    class Meta:
        verbose_name = 'Título de perfil'
        verbose_name_plural = 'Títulos de perfil'

    def __str__(self):
        return f'{self.perfil} - {self.titulo}'


class Porver(models.Model):
    perfil_titulo = models.ForeignKey(PerfilTitulo, on_delete=models.CASCADE, related_name='porver')
    fecha_agregado = models.DateField()
    fecha_eliminado = models.DateField(blank=True, null=True)

    class Meta:
        verbose_name = 'Por ver'
        verbose_name_plural = 'Por ver'

    def __str__(self):
        return f'Por ver {self.id} - {self.perfil_titulo}'


class PerfilContenido(models.Model):
    # Cuanto vio un perfil un determinado contenido
    perfil = models.ForeignKey('Perfil', on_delete=models.CASCADE, related_name='perfil_contenidos')
    contenido = models.ForeignKey(Contenido, on_delete=models.CASCADE, related_name='perfil_contenidos')
    segundos_vistos = models.IntegerField(default=0)
    ultima_visualizacion = models.DateTimeField()

    class Meta:
        verbose_name = 'Contenido de perfil'
        verbose_name_plural = 'Contenidos de perfil'

    def __str__(self):
        return f'{self.perfil} - {self.contenido}'


class MarcaTarjeta(models.Model):
    nombre = models.CharField(max_length=100)
    numero_asignado = models.IntegerField()
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Marca de tarjeta'
        verbose_name_plural = 'Marcas de tarjeta'

    def __str__(self):
        return self.nombre


class MetodoPago(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Método de pago'
        verbose_name_plural = 'Métodos de pago'

    def __str__(self):
        return self.nombre


class Tarjeta(models.Model):
    numero = models.CharField(max_length=4)
    fecha_vencimiento = models.DateField()
    marca_tarjeta = models.ForeignKey(MarcaTarjeta, on_delete=models.PROTECT, related_name='tarjetas')
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT, related_name='tarjetas')
    habilitado = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Tarjeta'
        verbose_name_plural = 'Tarjetas'

    def __str__(self):
        return f'{self.marca_tarjeta} **** **** **** {self.numero}'



class Plan(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    cantidad_pantallas_simultaneas = models.IntegerField()

    class Meta:
        verbose_name = 'Plan'
        verbose_name_plural = 'Planes'

    def __str__(self):
        return self.nombre


class PlanCalidad(models.Model):
    # Soluciona la n:m entre Plan y Calidad (streaming)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='plan_calidades')
    calidad = models.ForeignKey('streaming.Calidad', on_delete=models.CASCADE, related_name='plan_calidades')

    class Meta:
        verbose_name = 'Calidad del plan'
        verbose_name_plural = 'Calidades del plan'

    def __str__(self):
        return f'{self.plan} - {self.calidad}'


class Precio(models.Model):
    precio = models.FloatField()
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(blank=True, null=True)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='precios')

    class Meta:
        verbose_name = 'Precio'
        verbose_name_plural = 'Precios'

    def __str__(self):
        return f'{self.plan} - {self.precio}'


class Suscripcion(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='suscripciones')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='suscripciones')
    tarjeta = models.ForeignKey(Tarjeta, on_delete=models.CASCADE, related_name='suscripciones')
    fecha_inscripcion = models.DateField()
    fecha_vigencia = models.DateField(blank=True, null=True)
    fecha_cancelacion = models.DateField(blank=True, null=True)
    habilitado = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Suscripción'
        verbose_name_plural = 'Suscripciones'

    def __str__(self):
        return f'{self.usuario} - {self.plan}'


class EstadoCobro(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Estado de cobro'
        verbose_name_plural = 'Estados de cobro'

    def __str__(self):
        return self.nombre


class Cobro(models.Model):
    # num_factura es el id automatico de django
    suscripcion = models.ForeignKey(Suscripcion, on_delete=models.CASCADE, related_name='cobros')
    fecha_cobro = models.DateField()
    estado_cobro = models.ForeignKey(EstadoCobro, on_delete=models.CASCADE, related_name='cobros')
    # se copia de la suscripcion al momento del cobro, para dejar historial
    tarjeta = models.ForeignKey(Tarjeta, on_delete=models.CASCADE, related_name='cobros')
    numero_autorizacion = models.CharField(max_length=100, blank=True, null=True)
    monto = models.FloatField()

    class Meta:
        verbose_name = 'Cobro'
        verbose_name_plural = 'Cobros'

    def __str__(self):
        return f'Factura {self.id} - {self.suscripcion}'
     
class Imagen(Model):
    id = BigAutoField(primary_key=True)
    nombre = CharField(max_length=100)
    titulo = ForeignKey(Titulo, on_delete=CASCADE)
    imagen = models.ImageField(upload_to=imagen_upload_path, null=True, blank=True)
    class Meta:
        verbose_name = 'Imagen'
        verbose_name_plural = 'Imágenes'
    
    def __str__(self):
        return self.nombre

class Usuario(AbstractUser):
    id = BigAutoField(primary_key=True)
    telefono = PhoneNumberField(blank=True)
    pais = ForeignKey(Pais, on_delete=CASCADE, default=pais_default)
    idioma = ForeignKey(Idioma, on_delete=CASCADE, default=idioma_default)
    # hay que ver despues la cuestion con tarjeta

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
    
    def __str__(self):
        return self.username
    
class TipoPerfil(Model):
    id = BigAutoField(primary_key=True)
    nombre = CharField(max_length=100)
    edad_max = IntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])

    class Meta:
        verbose_name = 'Tipo de perfil'
        verbose_name_plural = 'Tipos de perfil'
    
    def __str__(self):
        return self.nombre
    
class Perfil(Model):
    id = BigAutoField(primary_key=True)
    nombre = CharField(max_length=100)
    imagen = ForeignKey(Imagen, on_delete=CASCADE)
    tipo_perfil = ForeignKey(TipoPerfil, on_delete=CASCADE)
    usuario = ForeignKey(settings.AUTH_USER_MODEL, on_delete=CASCADE)

    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfiles'
    
    def __str__(self):
        return self.nombre
    
class Registro(Model):
    id = BigAutoField(primary_key=True)
    token_disp = CharField(max_length=100)
    os = CharField(max_length=100)
    ultima_conexion_fecha = DateField()
    ultima_conexion_hora = TimeField()
    estado = BooleanField()
    usuario = ForeignKey(settings.AUTH_USER_MODEL, on_delete=CASCADE)

    class Meta:
        verbose_name = 'Registro'
        verbose_name_plural = 'Registros'
    
    def __str__(self):
        return f'{self.usuario} - {self.os}'