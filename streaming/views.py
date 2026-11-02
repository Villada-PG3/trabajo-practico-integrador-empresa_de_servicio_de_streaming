from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages


def home(request):
    """Vista para la landing page / página de inicio pública"""
    return render(request, 'home.html')

def login(request, login=True):
    # le damos el mail al login si lo pusimos en el paso anterior
    email = request.GET.get('email', '')
    context = {
        "email": email,
        "login": login
        }
    if login:
        return render(request, 'login.html', context)
    else:
        ## el login y el signin son parecidos asi que podemos modificar uno para el otro
        return render(request, 'login.html', context)
