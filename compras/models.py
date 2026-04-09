from django.db import models
from django.conf import settings
from inventario.models import Producto, Proveedor

class Compra(models.Model):
    ESTADO = [
        ('pendiente',  'Pendiente'),
        ('recibida',   'Recibida'),
        ('cancelada',  'Cancelada'),
    ]

    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    usuario   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha     = models.DateTimeField(auto_now_add=True)
    total     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado    = models.CharField(max_length=20, choices=ESTADO, default='recibida')
    notas     = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f"Compra #{self.id} — {self.proveedor.nombre}"


class DetalleCompra(models.Model):
    compra          = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name='detalles')
    producto        = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad        = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal        = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre}"