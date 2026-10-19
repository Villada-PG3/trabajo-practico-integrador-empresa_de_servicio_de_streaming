from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from phonenumber_field.formfields import PhoneNumberField

from .models import Idioma, Pais

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
    )
    idioma = forms.ModelChoiceField(
        label='Idioma',
        queryset=Idioma.objects.order_by('nombre'),
        empty_label='Selecciona tu idioma',
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
