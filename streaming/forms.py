from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from phonenumber_field.formfields import PhoneNumberField

from .billing import normalizar_numero_tarjeta, numero_tarjeta_valido
from .models import (
    Idioma,
    Imagen,
    MarcaTarjeta,
    MetodoPago,
    Pais,
    Perfil,
    TipoPerfil,
)

Usuario = get_user_model()


class RegistroForm(forms.Form):
    username = forms.CharField(label='Nombre de usuario', max_length=150)
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
        self.fields['username'].widget.attrs.update({
            'placeholder': 'Elige un nombre de usuario',
            'autocomplete': 'username',
        })
        self.fields['password'].widget.attrs.update({
            'placeholder': 'Crea tu contraseña',
            'autocomplete': 'new-password',
        })
        self.fields['telefono'].widget.attrs['autocomplete'] = 'tel'

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if (
            Usuario.objects.filter(email__iexact=email).exists()
            or Usuario.objects.filter(username__iexact=email).exists()
        ):
            raise forms.ValidationError('Ya existe una cuenta asociada a este correo.')
        return email

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if Usuario.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Ese nombre de usuario ya está en uso.')
        return username

    def clean_password(self):
        password = self.cleaned_data['password']
        username = self.cleaned_data.get('username')
        email = self.cleaned_data.get('email')
        if username and email:
            user = Usuario(username=username, email=email)
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
            username=data['username'],
            email=data['email'],
            password=data['password'],
            telefono=data['telefono'] or '',
            pais=data['pais'],
            idioma=data['idioma'],
        )


class CuentaPreferenciasForm(forms.Form):
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

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.initial.update({
            'pais': usuario.pais_id,
            'idioma': usuario.idioma_id,
        })
        self.fields['pais'].widget.attrs['class'] = (
            'form-select bg-secondary text-white border-0 py-2'
        )
        self.fields['idioma'].widget.attrs['class'] = (
            'form-select bg-secondary text-white border-0 py-2'
        )

    def save(self):
        if not self.is_valid():
            raise ValueError('No se pueden guardar preferencias inválidas.')
        self.usuario.pais = self.cleaned_data['pais']
        self.usuario.idioma = self.cleaned_data['idioma']
        self.usuario.save(update_fields=['pais', 'idioma'])
        return self.usuario


class EditarCuentaForm(forms.Form):
    CAMPOS = {
        'username': 'Nombre de usuario',
        'email': 'Correo electrónico',
        'telefono': 'Teléfono',
        'password': 'Contraseña',
    }

    def __init__(self, *args, usuario, campo, **kwargs):
        super().__init__(*args, **kwargs)
        if campo not in self.CAMPOS:
            raise ValueError('El dato de cuenta solicitado no es editable.')
        self.usuario = usuario
        self.campo = campo
        self.fields['current_password'] = forms.CharField(
            label='Contraseña actual',
            strip=False,
            widget=forms.PasswordInput(attrs={
                'autocomplete': 'current-password',
            }),
        )
        if campo == 'username':
            modelo = Usuario._meta.get_field('username')
            self.fields[campo] = forms.CharField(
                label=self.CAMPOS[campo],
                max_length=modelo.max_length,
                validators=modelo.validators,
                initial=usuario.username,
            )
        elif campo == 'email':
            self.fields[campo] = forms.EmailField(
                label=self.CAMPOS[campo],
                max_length=254,
                initial=usuario.email,
                widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
            )
        elif campo == 'telefono':
            self.fields[campo] = PhoneNumberField(
                label=self.CAMPOS[campo],
                required=False,
                initial=usuario.telefono,
                widget=forms.TextInput(attrs={
                    'placeholder': '+54 9 11 1234-5678',
                    'autocomplete': 'tel',
                }),
            )
        else:
            self.fields['new_password'] = forms.CharField(
                label='Nueva contraseña',
                strip=False,
                widget=forms.PasswordInput(attrs={
                    'autocomplete': 'new-password',
                }),
            )
            self.fields['confirm_password'] = forms.CharField(
                label='Repetir nueva contraseña',
                strip=False,
                widget=forms.PasswordInput(attrs={
                    'autocomplete': 'new-password',
                }),
            )

        for field in self.fields.values():
            field.widget.attrs['class'] = (
                'form-control bg-secondary text-white border-0 py-2'
            )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if Usuario.objects.filter(username__iexact=username).exclude(
            pk=self.usuario.pk
        ).exists():
            raise forms.ValidationError('Ese nombre de usuario ya está en uso.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if (
            Usuario.objects.filter(email__iexact=email).exclude(pk=self.usuario.pk).exists()
            or Usuario.objects.filter(username__iexact=email).exclude(pk=self.usuario.pk).exists()
        ):
            raise forms.ValidationError('Ese correo ya está asociado a una cuenta.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        if not self.usuario.check_password(cleaned_data.get('current_password', '')):
            self.add_error('current_password', 'La contraseña vigente no es correcta.')

        if self.campo != 'password':
            return cleaned_data

        if cleaned_data.get('new_password') != cleaned_data.get('confirm_password'):
            self.add_error(
                'confirm_password',
                'Las contraseñas nuevas no coinciden.',
            )
        if cleaned_data.get('new_password'):
            try:
                validate_password(cleaned_data['new_password'], self.usuario)
            except ValidationError as error:
                self.add_error('new_password', error)
        return cleaned_data

    def save(self):
        if not self.is_valid():
            raise ValueError('No se puede editar un dato con un formulario inválido.')
        if self.campo == 'password':
            self.usuario.set_password(self.cleaned_data['new_password'])
            self.usuario.save(update_fields=['password'])
        else:
            valor = self.cleaned_data[self.campo]
            setattr(self.usuario, self.campo, valor or '')
            self.usuario.save(update_fields=[self.campo])
        return self.usuario


class TarjetaDemoPlanForm(forms.Form):
    nombre_titular = forms.CharField(
        label='Nombre del titular',
        max_length=150,
    )
    numero_tarjeta = forms.CharField(
        label='Número de tarjeta de prueba',
        max_length=23,
        widget=forms.TextInput(attrs={
            'inputmode': 'numeric',
            'autocomplete': 'off',
            'placeholder': '4111 1111 1111 1111',
        }),
    )
    cvv = forms.CharField(
        label='CVV ficticio',
        max_length=4,
        min_length=3,
        validators=[
            RegexValidator(
                r'^[0-9]{3,4}$',
                'Ingresa un CVV ficticio de 3 o 4 dígitos.',
            ),
        ],
        widget=forms.PasswordInput(attrs={
            'inputmode': 'numeric',
            'autocomplete': 'off',
            'placeholder': '123',
        }),
    )
    marca_tarjeta = forms.ModelChoiceField(
        label='Marca de la tarjeta',
        queryset=MarcaTarjeta.objects.none(),
        empty_label='Selecciona una marca',
    )
    metodo_pago = forms.ModelChoiceField(
        label='Método de pago',
        queryset=MetodoPago.objects.none(),
        empty_label='Selecciona débito o crédito',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['marca_tarjeta'].queryset = MarcaTarjeta.objects.filter(
            nombre__in=(
                'Visa',
                'Mastercard',
                'American Express',
                'Discover',
                'Diners Club',
            ),
        ).order_by('nombre')
        self.fields['metodo_pago'].queryset = MetodoPago.objects.filter(
            nombre__in=('Débito', 'Crédito'),
        ).order_by('nombre')
        for field in self.fields.values():
            field.widget.attrs['class'] = (
                'form-control bg-secondary text-white border-0 py-2'
            )
        for field_name in ('marca_tarjeta', 'metodo_pago'):
            self.fields[field_name].widget.attrs['class'] = (
                'form-select bg-secondary text-white border-0 py-2'
            )
        self.fields['nombre_titular'].widget.attrs.update({
            'autocomplete': 'cc-name',
        })

    def clean_numero_tarjeta(self):
        numero = normalizar_numero_tarjeta(
            self.cleaned_data['numero_tarjeta'],
        )
        if not numero_tarjeta_valido(numero):
            raise forms.ValidationError(
                'Ingresa un número de tarjeta ficticio válido según Luhn '
                '(entre 12 y 19 dígitos).'
            )
        return numero


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
