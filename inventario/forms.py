from django import forms
from .models import Producto, Categoria, Proveedor


class ProductoForm(forms.ModelForm):
    class Meta:
        model  = Producto
        fields = [
            'nombre', 'descripcion', 'codigo_barra', 'sku',
            'precio_compra', 'precio_venta',
            'categoria', 'proveedor', 'activo'
        ]
        
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
        }


class CsvUploadForm(forms.Form):
    csv_file = forms.FileField(
        label='Archivo CSV',
        help_text='El archivo debe contener encabezados: nombre, descripcion, codigo_barra, sku, precio_compra, precio_venta, categoria, proveedor, activo'
    )