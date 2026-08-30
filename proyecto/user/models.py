import uuid
from django.db.models import *
from django.contrib.auth.models import AbstractUser
from phonenumber_field.modelfields import PhoneNumberField
from streaming.models import Pais, Idioma, Titulo
from pagos.models import Tarjeta
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
    
class Imagen(Model):
    id = BigAutoField(primary_key=True)
    nombre = CharField(max_length=100)
    imagen = FileField() # hay que ver despues como se implementa
    titulo = ForeignKey(Titulo, on_delete=CASCADE)
    
    def __str__(self):
        return self.nombre

class Usuario(AbstractUser):
    id = BigAutoField(primary_key=True)
    telefono = PhoneNumberField(blank=True)
    pais = ForeignKey(Pais, on_delete=CASCADE)
    idioma = ForeignKey(Idioma, on_delete=CASCADE)
    # hay que ver despues la cuestion con tarjeta
    
    def __str__(self):
        return self.username
    
class TipoPerfil(Model):
    id = BigAutoField(primary_key=True)
    nombre = CharField(max_length=100)
    edad_max = IntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    
    def __str__(self):
        return self.nombre
    
class Perfil(Model):
    id = BigAutoField(primary_key=True)
    nombre = CharField(max_length=100)
    imagen = ForeignKey(Imagen, on_delete=CASCADE)
    tipo_perfil = ForeignKey(TipoPerfil, on_delete=CASCADE)
    usuario = ForeignKey(settings.AUTH_USER_MODEL, on_delete=CASCADE)
    
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
    
    def __str__(self):
        return f'{self.usuario} - {self.os}'