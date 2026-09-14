from django.shortcuts import render


def home(request):
    """Vista para la landing page / página de inicio pública"""
    return render(request, 'home.html')