from django.urls import path
from . import views

app_name = 'ventas'

urlpatterns = [
    # Punto de Venta 
    path('',                  views.punto_venta,     name='punto_venta'),
    path('historial/',        views.historial,       name='historial'),
    path('buscar-producto/',  views.buscar_producto, name='buscar_producto'),
    path('procesar/',         views.procesar_venta,  name='procesar_venta'),
    path('buscar-producto-sugerencias/', views.buscar_producto_sugerencias, name='buscar_producto_sugerencias'),

    # Corte de caja
    path('caja/abrir/',               views.abrir_caja,   name='abrir_caja'),
    path('caja/cerrar/',              views.cerrar_caja,  name='cerrar_caja'),
    path('caja/historial/',           views.historial_cortes, name='historial_cortes'),
    path('caja/<int:pk>/detalle/',    views.detalle_corte,   name='detalle_corte'),

    # Devoluciones
    path('devolucion/buscar/', views.buscar_venta_devolucion, name='buscar_venta_devolucion'),
    path('devolucion/registrar/<int:venta_id>/', views.registrar_devolucion, name='registrar_devolucion'),

]