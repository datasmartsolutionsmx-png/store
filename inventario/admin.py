from django.contrib import admin
from .models import Categoria, Proveedor, Producto, MovimientoStock

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'activa')
    search_fields = ('nombre',)

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'telefono', 'email', 'activo')
    search_fields = ('nombre',)

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'codigo_barra', 'precio_venta', 'stock', 'categoria', 'activo')
    search_fields = ('nombre', 'codigo_barra', 'sku')
    list_filter   = ('activo', 'categoria')


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    list_display  = ('producto', 'tipo', 'cantidad', 'stock_anterior', 'stock_nuevo', 'usuario', 'fecha')
    list_filter   = ('tipo', 'fecha')
    search_fields = ('producto__nombre',)