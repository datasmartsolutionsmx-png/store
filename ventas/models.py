from django.db import models
from django.conf import settings
from inventario.models import Producto
from tiendas.models import Tienda
from django.db.models import Max

def generar_folio(tienda):
    """Genera el siguiente folio para una tienda"""
    ultima_venta = Venta.objects.filter(tienda=tienda).aggregate(max_folio=Max('folio'))
    siguiente = (ultima_venta['max_folio'] or 0) + 1
    return siguiente

class Venta(models.Model):
    METODO_PAGO = [
        ('efectivo',      'Efectivo'),
        ('tarjeta',       'Tarjeta'),
        ('transferencia', 'Transferencia'),
    ]
    ESTADO = [
        ('completada', 'Completada'),
        ('cancelada',  'Cancelada'),
        ('devuelta',   'Devuelta'),
    ]

    tienda = models.ForeignKey(Tienda, on_delete=models.PROTECT, null=True, blank=True)
    usuario     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha       = models.DateTimeField(auto_now_add=True)
    subtotal    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO, default='efectivo')
    estado      = models.CharField(max_length=20, choices=ESTADO, default='completada')
    notas       = models.TextField(blank=True, null=True)
    total_devuelto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    folio = models.IntegerField(default=0)

    class Meta:
        ordering = ['-fecha']
        unique_together = ['tienda', 'folio'] 

    def __str__(self):
        return f"Venta #{self.id} — {self.fecha.strftime('%d/%m/%Y')}"


class DetalleVenta(models.Model):

    venta           = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto        = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad        = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal        = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre}"


class Devolucion(models.Model):
    ESTADO = [
        ('pendiente', 'Pendiente'),
        ('aprobada',  'Aprobada'),
        ('rechazada', 'Rechazada'),
    ]

    tienda = models.ForeignKey(Tienda, on_delete=models.PROTECT, null=True, blank=True)
    venta          = models.ForeignKey(Venta, on_delete=models.PROTECT)
    usuario        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha          = models.DateTimeField(auto_now_add=True)
    motivo         = models.TextField()
    total_devuelto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado         = models.CharField(max_length=20, choices=ESTADO, default='pendiente')

    def __str__(self):
        return f"Devolución de Venta #{self.venta.id}"


class DetalleDevolucion(models.Model):

    devolucion      = models.ForeignKey(Devolucion, on_delete=models.CASCADE, related_name='detalles')
    producto        = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad        = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre}"
    

class CorteCaja(models.Model):
    ESTADO = [
        ('abierto', 'Abierto'),
        ('cerrado', 'Cerrado'),
    ]

    tienda = models.ForeignKey(Tienda, on_delete=models.PROTECT, null=True, blank=True)
    folio = models.IntegerField(default=0)
    usuario          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_apertura   = models.DateTimeField(auto_now_add=True)
    fecha_cierre     = models.DateTimeField(null=True, blank=True)
    fondo_inicial    = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Totales calculados al cerrar
    total_efectivo      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tarjeta       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_transferencia = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_ventas        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    num_ventas          = models.IntegerField(default=0)

    # Conteo real que hace el cajero al cerrar
    conteo_efectivo      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    conteo_tarjeta       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    conteo_transferencia = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Diferencia (conteo real vs esperado)
    diferencia_efectivo      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    diferencia_tarjeta       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    diferencia_transferencia = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    estado = models.CharField(max_length=10, choices=ESTADO, default='abierto')
    notas  = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha_apertura']
        unique_together = ['tienda', 'folio']
        verbose_name = 'Corte de caja'
        verbose_name_plural = 'Cortes de caja'

    def __str__(self):
        return f"Corte #{self.id} — {self.usuario.username} {self.fecha_apertura.strftime('%d/%m/%Y %H:%M')}"

    @property
    def efectivo_esperado(self):
        return self.fondo_inicial + self.total_efectivo
    
def generar_folio_corte(tienda):
    """Genera el siguiente folio de corte para una tienda"""
    from .models import CorteCaja
    ultimo_corte = CorteCaja.objects.filter(tienda=tienda).aggregate(max_folio=Max('folio'))
    siguiente = (ultimo_corte['max_folio'] or 0) + 1
    return siguiente