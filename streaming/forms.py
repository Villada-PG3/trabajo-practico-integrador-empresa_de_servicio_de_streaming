from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from phonenumber_field.formfields import PhoneNumberField

from .models import Idioma, Imagen, Pais, Perfil, TipoPerfil

Usuario = get_user_model()


class RegistroForm(forms.Form):
    email = forms.EmailField(label='Correo electrónico')
    password = forms.CharField(
        label='Contraseña',
        strip=False,
        widget=forms.PasswordInput,
    )
    telefono = PhoneNumberField(
        label='Teléfono (opcional)',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '+54 9 11 1234-5678'}),
    )
    pais = forms.ModelChoiceField(
        label='País',
        queryset=Pais.objects.order_by('nombre'),
        empty_label='Selecciona tu país',
        required=False,
    )
    idioma = forms.ModelChoiceField(
        label='Idioma',
        queryset=Idioma.objects.order_by('nombre'),
        empty_label='Selecciona tu idioma',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name in {'pais', 'idioma'}:
                field.widget.attrs['class'] = 'form-select bg-secondary text-white border-0 py-2 fs-6'
            else:
                field.widget.attrs['class'] = 'form-control bg-secondary text-white border-0 py-2 fs-6'
        self.fields['email'].widget.attrs.update({
            'placeholder': 'Ingresa tu email',
            'autocomplete': 'email',
        })
        self.fields['password'].widget.attrs.update({
            'placeholder': 'Crea tu contraseña',
            'autocomplete': 'new-password',
        })
        self.fields['telefono'].widget.attrs['autocomplete'] = 'tel'

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Usuario.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError('Ya existe una cuenta asociada a este correo.')
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        email = self.cleaned_data.get('email')
        if email:
            user = Usuario(username=email, email=email)
            try:
                validate_password(password, user)
            except ValidationError as error:
                raise forms.ValidationError(error.messages) from error
        return password

    def save(self):
        if not self.is_valid():
            raise ValueError('No se puede crear la cuenta con un formulario inválido.')
        data = self.cleaned_data
        return Usuario.objects.create_user(
            username=data['email'],
            email=data['email'],
            password=data['password'],
            telefono=data['telefono'] or '',
            pais=data['pais'],
            idioma=data['idioma'],
        )


class LoginForm(forms.Form):
    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={
            'class': 'form-control bg-secondary text-white border-0 py-2 fs-6',
            'placeholder': 'Ingresa tu email',
            'autocomplete': 'username',
        }),
    )
    password = forms.CharField(
        label='Contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control bg-secondary text-white border-0 py-2 fs-6',
            'placeholder': 'Ingresa tu contraseña',
            'autocomplete': 'current-password',
        }),
    )


class PerfilForm(forms.Form):
    TIPOS_PERFIL = (
        ('adulto', 'Adulto (desde 18 años)'),
        ('adolescente', 'Adolescente (hasta 17 años)'),
        ('infantil', 'Infantil (hasta 12 años)'),
    )

    nombre = forms.CharField(
        label='Nombre del perfil',
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control bg-secondary text-white border-0 py-2',
            'placeholder': 'Por ejemplo, Alex',
            'autocomplete': 'off',
        }),
    )
    tipo_perfil = forms.ChoiceField(
        label='Tipo de perfil',
        choices=TIPOS_PERFIL,
        widget=forms.Select(attrs={
            'class': 'form-select bg-secondary text-white border-0 py-2',
        }),
    )
    imagen = forms.ModelChoiceField(
        label='Elige un avatar',
        queryset=Imagen.objects.order_by('nombre'),
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, perfil=None, **kwargs):
        super().__init__(*args, **kwargs)
        if perfil is not None:
            tipos_por_edad = {100: 'adulto', 17: 'adolescente', 12: 'infantil'}
            self.initial.update({
                'nombre': perfil.nombre,
                'tipo_perfil': tipos_por_edad.get(perfil.tipo_perfil.edad_max, 'adulto'),
                'imagen': perfil.imagen_id,
            })
        else:
            primer_avatar = self.fields['imagen'].queryset.first()
            if primer_avatar:
                self.fields['imagen'].initial = primer_avatar.pk

    def save(self, usuario, perfil=None):
        if not self.is_valid():
            raise ValueError('No se puede guardar el perfil con un formulario inválido.')

        tipos_por_clave = {
            'adulto': ('Adulto', 100),
            'adolescente': ('Adolescente', 17),
            'infantil': ('Infantil', 12),
        }
        nombre_tipo, edad_max = tipos_por_clave[self.cleaned_data['tipo_perfil']]
        tipo_perfil, _ = TipoPerfil.objects.get_or_create(
            nombre=nombre_tipo,
            defaults={'edad_max': edad_max},
        )
        if perfil is None:
            perfil = Perfil(usuario=usuario)
        perfil.nombre = self.cleaned_data['nombre'].strip()
        perfil.imagen = self.cleaned_data['imagen']
        perfil.tipo_perfil = tipo_perfil
        perfil.save()
        return perfil


class ReporteVentasFiltroForm(forms.Form):
    fecha_inicio = forms.DateField(
        label='Fecha Desde',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-dark'}),
    )
    fecha_fin = forms.DateField(
        label='Fecha Hasta',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-dark'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
            raise forms.ValidationError('La fecha inicial no puede ser posterior a la fecha final.')
        return cleaned_data
