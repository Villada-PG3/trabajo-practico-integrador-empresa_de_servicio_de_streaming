from django.db.models import *
from django.db import models

class Pais(models.Model):
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre


class TipoTitulo(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre


class Idioma(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre


class Rol(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre


class Elenco(models.Model):
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, related_name='elencos')
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)

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

    def __str__(self):
        return self.nombre


class Calificacion(models.Model):
    nombre = models.CharField(max_length=100)
    porcentaje_gusto = models.FloatField()

    def __str__(self):
        return self.nombre


class Titulo(models.Model):
    nombre_original = models.CharField(max_length=255)
    descripcion_original = models.TextField(blank=True, null=True)
    tipo_titulo = models.ForeignKey(TipoTitulo, on_delete=models.PROTECT, related_name='titulos')
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, related_name='titulos')
    fecha_estreno = models.DateField(blank=True, null=True)
    fecha_baja = models.DateField(blank=True, null=True)

    def __str__(self):
        return self.nombre_original


class TituloRolElenco(models.Model):
    rol_elenco = models.ForeignKey(RolElenco, on_delete=models.CASCADE, related_name='titulo_rol_elencos')
    titulo = models.ForeignKey(Titulo, on_delete=models.CASCADE, related_name='titulo_rol_elencos')

    def __str__(self):
        return f'{self.titulo} - {self.rol_elenco}'


class TituloCategoria(models.Model):
    titulo = models.ForeignKey(Titulo, on_delete=models.CASCADE, related_name='titulo_categorias')
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name='titulo_categorias')

    def __str__(self):
        return f'{self.titulo} - {self.categoria}'


class IdiomaTitulo(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    idioma = models.ForeignKey(Idioma, on_delete=models.CASCADE, related_name='idioma_titulos')
    titulo = models.ForeignKey(Titulo, on_delete=models.CASCADE, related_name='idioma_titulos')

    def __str__(self):
        return f'{self.titulo} ({self.idioma})'


class Contenido(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    seccion = models.IntegerField()
    orden = models.IntegerField()
    titulo = models.ForeignKey(Titulo, on_delete=models.CASCADE, related_name='contenidos')

    def __str__(self):
        return self.nombre


class Subtitulo(models.Model):
    contenido = models.ForeignKey(Contenido, on_delete=models.CASCADE, related_name='subtitulos')
    idioma = models.ForeignKey(Idioma, on_delete=models.PROTECT, related_name='subtitulos')
    archivo_vtt = models.BinaryField()

    def __str__(self):
        return f'{self.contenido} - {self.idioma}'


class IdiomaContenido(models.Model):
    idioma = models.ForeignKey(Idioma, on_delete=models.CASCADE, related_name='idioma_contenidos')
    contenido = models.ForeignKey(Contenido, on_delete=models.CASCADE, related_name='idioma_contenidos')

    def __str__(self):
        return f'{self.contenido} - {self.idioma}'


class CalidadIdiomaContenido(models.Model):
    idioma_contenido = models.ForeignKey(IdiomaContenido, on_delete=models.CASCADE, related_name='calidades')
    calidad = models.ForeignKey(Calidad, on_delete=models.PROTECT, related_name='calidad_idioma_contenidos')
    archivo = models.BinaryField()

    def __str__(self):
        return f'{self.idioma_contenido} - {self.calidad}'


class PerfilTitulo(models.Model):
    # Historial de titulos vistos por un perfil, con su calificacion (para recomendaciones)
    perfil = models.ForeignKey('user.Perfil', on_delete=models.CASCADE, related_name='perfil_titulos')
    titulo = models.ForeignKey(Titulo, on_delete=models.CASCADE, related_name='perfil_titulos')
    calificacion = models.ForeignKey(
        Calificacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='perfil_titulos'
    )

    def __str__(self):
        return f'{self.perfil} - {self.titulo}'


class Porver(models.Model):
    perfil_titulo = models.ForeignKey(PerfilTitulo, on_delete=models.CASCADE, related_name='porver')
    fecha_agregado = models.DateField()
    fecha_eliminado = models.DateField(blank=True, null=True)

    def __str__(self):
        return f'Por ver {self.id} - {self.perfil_titulo}'


class PerfilContenido(models.Model):
    # Cuanto vio un perfil un determinado contenido
    perfil = models.ForeignKey('user.Perfil', on_delete=models.CASCADE, related_name='perfil_contenidos')
    contenido = models.ForeignKey(Contenido, on_delete=models.CASCADE, related_name='perfil_contenidos')
    segundos_vistos = models.IntegerField(default=0)
    ultima_visualizacion = models.DateTimeField()

    def __str__(self):
        return f'{self.perfil} - {self.contenido}'