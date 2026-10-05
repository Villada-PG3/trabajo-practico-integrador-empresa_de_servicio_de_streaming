from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages


def home(request):
    """Vista para la landing page / página de inicio pública"""
    return render(request, 'home.html')
