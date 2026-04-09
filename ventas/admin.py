from django.contrib import admin
from .models import Venta, DetalleVenta

class DetalleVentaInline(admin.TabularInline):
    model  = DetalleVenta
    extra  = 0
    fields = ('producto', 'cantidad', 'precio_unitario', 'subtotal')
    readonly_fields = ('subtotal',)

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display   = ('id', 'usuario', 'fecha', 'total', 'metodo_pago', 'estado')
    list_filter    = ('estado', 'metodo_pago', 'fecha')
    search_fields  = ('usuario__username',)
    inlines        = [DetalleVentaInline]
    readonly_fields = ('subtotal', 'total', 'fecha')

from .models import Venta, DetalleVenta, CorteCaja

@admin.register(CorteCaja)
class CorteCajaAdmin(admin.ModelAdmin):
    list_display  = ('id', 'usuario', 'fecha_apertura', 'fecha_cierre', 'fondo_inicial', 'total_ventas', 'estado')
    list_filter   = ('estado', 'fecha_apertura')
    search_fields = ('usuario__username',)
    readonly_fields = ('fecha_apertura', 'total_ventas', 'num_ventas')