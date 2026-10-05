from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('reporte-ventas/', views.reporte_ventas_view, name='reporte_ventas'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]
