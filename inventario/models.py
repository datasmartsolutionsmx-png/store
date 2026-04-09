from django.db import models
from django.conf import settings
from tiendas.models import Tienda

class Categoria(models.Model):
    nombre      = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activa      = models.BooleanField(default=True)
    tienda = models.ForeignKey(Tienda, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Categorías"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Proveedor(models.Model):
    nombre    = models.CharField(max_length=150)
    contacto  = models.CharField(max_length=100, blank=True)
    telefono  = models.CharField(max_length=20, blank=True)
    email     = models.EmailField(blank=True)
    direccion = models.TextField(blank=True)
    activo    = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    tienda = models.ForeignKey(Tienda, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    nombre         = models.CharField(max_length=200)
    descripcion    = models.TextField(blank=True)
    codigo_barra   = models.CharField(max_length=100, unique=True, blank=True, null=True)
    sku            = models.CharField(max_length=100, unique=True, blank=True, null=True)
    precio_compra  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_venta   = models.DecimalField(max_digits=10, decimal_places=2)
    stock          = models.IntegerField(default=0)
    stock_minimo   = models.IntegerField(default=5)
    categoria      = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True)
    proveedor      = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True)
    activo         = models.BooleanField(default=True)
    creado_por     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    creado_en      = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    tienda         = models.ForeignKey(Tienda, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ['nombre']
        verbose_name_plural = "Productos"

    def __str__(self):
        return f"{self.nombre} ({self.codigo_barra})"

    @property
    def stock_bajo(self):
        return self.stock <= self.stock_minimo


class MovimientoStock(models.Model):
    TIPO = [
        ('entrada',  'Entrada'),
        ('salida',   'Salida'),
        ('ajuste',   'Ajuste'),
    ]

    tienda = models.ForeignKey(Tienda, on_delete=models.PROTECT, null=True, blank=True)
    producto   = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='movimientos')
    tipo       = models.CharField(max_length=10, choices=TIPO)
    cantidad   = models.IntegerField()
    stock_anterior = models.IntegerField()
    stock_nuevo    = models.IntegerField()
    motivo     = models.CharField(max_length=200, blank=True)
    usuario    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name_plural = 'Movimientos de stock'

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.producto.nombre} ({self.cantidad})"