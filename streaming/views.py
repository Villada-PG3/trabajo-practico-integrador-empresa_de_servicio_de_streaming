from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages


def home(request):
    """Vista para la landing page / página de inicio pública"""
    return render(request, 'home.html')

def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('username')
        password = request.POST.get('password')
        
        # Validar credenciales
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            login(request, user)
            # Redirige a la pantalla de selección de perfil una vez autenticado
            return redirect('seleccionar_perfil')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
    
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    return redirect('home')