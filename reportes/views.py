from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
import csv

from users.models import UserRole
from ventas.models import Venta, DetalleVenta, Devolucion
from inventario.models import Producto
from django.db import models as db_models


def get_max_permission(user):
    return UserRole.objects.filter(
        user=user
    ).aggregate(
        max_perm=db_models.Max('role__reportes')
    )['max_perm'] or 0


def get_tienda_actual(user):
    """Retorna la tienda del usuario. Si es superadmin, retorna None (sin filtro)."""
    if user.is_superuser:
        return None
    return user.tienda


@login_required
def dashboard_reportes(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    from decimal import Decimal

    hoy = timezone.now().date()
    ayer = hoy - timedelta(days=1)
    mes = hoy.replace(day=1)
    
    tienda_actual = get_tienda_actual(request.user)

    # Función para calcular ventas netas (ventas - devoluciones)
    def calcular_ventas_netas(fecha_inicio, fecha_fin):
        # Ventas del período
        if tienda_actual:
            ventas = Venta.objects.filter(
                estado='completada',
                fecha__date__gte=fecha_inicio,
                fecha__date__lte=fecha_fin,
                tienda=tienda_actual
            )
            devoluciones = Devolucion.objects.filter(
                estado='aprobada',
                fecha__date__gte=fecha_inicio,
                fecha__date__lte=fecha_fin,
                tienda=tienda_actual
            )
        else:
            ventas = Venta.objects.filter(
                estado='completada',
                fecha__date__gte=fecha_inicio,
                fecha__date__lte=fecha_fin
            )
            devoluciones = Devolucion.objects.filter(
                estado='aprobada',
                fecha__date__gte=fecha_inicio,
                fecha__date__lte=fecha_fin
            )
        
        total_ventas = ventas.aggregate(total=Sum('total'))['total'] or Decimal('0')
        num_ventas = ventas.count()
        
        total_devuelto = devoluciones.aggregate(total=Sum('total_devuelto'))['total'] or Decimal('0')
        
        # Ventas netas
        ventas_netas = total_ventas - total_devuelto
        
        return {
            'total': ventas_netas,
            'count': num_ventas,
            'devuelto': total_devuelto
        }

    # Calcular para cada período
    ventas_hoy_data = calcular_ventas_netas(hoy, hoy)
    ventas_ayer_data = calcular_ventas_netas(ayer, ayer)
    ventas_mes_data = calcular_ventas_netas(mes, hoy)

    # Alertas de stock (con filtro por tienda)
    if tienda_actual:
        productos_sin_stock = Producto.objects.filter(
            activo=True, stock__lte=0, tienda=tienda_actual
        ).count()
        productos_stock_bajo = Producto.objects.filter(
            activo=True, stock__gt=0,
            stock__lte=db_models.F('stock_minimo'),
            tienda=tienda_actual
        ).count()
    else:
        productos_sin_stock = Producto.objects.filter(
            activo=True, stock__lte=0
        ).count()
        productos_stock_bajo = Producto.objects.filter(
            activo=True, stock__gt=0,
            stock__lte=db_models.F('stock_minimo')
        ).count()

    context = {
        'ventas_hoy': ventas_hoy_data['total'],
        'num_ventas_hoy': ventas_hoy_data['count'],
        'ventas_ayer': ventas_ayer_data['total'],
        'ventas_mes': ventas_mes_data['total'],
        'num_ventas_mes': ventas_mes_data['count'],
        'productos_sin_stock': productos_sin_stock,
        'productos_stock_bajo': productos_stock_bajo,
        'max_perm': get_max_permission(request.user),
    }
    return render(request, 'reportes/dashboard.html', context)


@login_required
def reporte_ventas(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    from decimal import Decimal
    from collections import defaultdict

    hoy = timezone.now().date()
    mes = hoy.replace(day=1)
    
    tienda_actual = get_tienda_actual(request.user)

    # Filtros
    fecha_desde = request.GET.get('fecha_desde', str(mes))
    fecha_hasta = request.GET.get('fecha_hasta', str(hoy))
    metodo_pago = request.GET.get('metodo_pago', '')

    # Ventas del período
    if tienda_actual:
        ventas = Venta.objects.filter(
            estado='completada',
            fecha__date__gte=fecha_desde,
            fecha__date__lte=fecha_hasta,
            tienda=tienda_actual
        )
    else:
        ventas = Venta.objects.filter(
            estado='completada',
            fecha__date__gte=fecha_desde,
            fecha__date__lte=fecha_hasta
        )

    if metodo_pago:
        ventas = ventas.filter(metodo_pago=metodo_pago)

    # Devoluciones del período
    if tienda_actual:
        devoluciones = Devolucion.objects.filter(
            estado='aprobada',
            fecha__date__gte=fecha_desde,
            fecha__date__lte=fecha_hasta,
            tienda=tienda_actual
        )
    else:
        devoluciones = Devolucion.objects.filter(
            estado='aprobada',
            fecha__date__gte=fecha_desde,
            fecha__date__lte=fecha_hasta
        )
    
    if metodo_pago:
        devoluciones = devoluciones.filter(venta__metodo_pago=metodo_pago)

    # Totales generales (netos)
    total_ventas_bruto = ventas.aggregate(total=Sum('total'))['total'] or Decimal('0')
    total_devoluciones = devoluciones.aggregate(total=Sum('total_devuelto'))['total'] or Decimal('0')
    total_ventas_neto = total_ventas_bruto - total_devoluciones
    
    total_descuentos = ventas.aggregate(total=Sum('descuento'))['total'] or Decimal('0')
    num_ventas = ventas.count()
    
    total_efectivo_bruto = ventas.filter(metodo_pago='efectivo').aggregate(total=Sum('total'))['total'] or Decimal('0')
    total_tarjeta_bruto = ventas.filter(metodo_pago='tarjeta').aggregate(total=Sum('total'))['total'] or Decimal('0')
    total_transferencia_bruto = ventas.filter(metodo_pago='transferencia').aggregate(total=Sum('total'))['total'] or Decimal('0')
    
    # Devoluciones por método de pago
    dev_efectivo = devoluciones.filter(venta__metodo_pago='efectivo').aggregate(total=Sum('total_devuelto'))['total'] or Decimal('0')
    dev_tarjeta = devoluciones.filter(venta__metodo_pago='tarjeta').aggregate(total=Sum('total_devuelto'))['total'] or Decimal('0')
    dev_transferencia = devoluciones.filter(venta__metodo_pago='transferencia').aggregate(total=Sum('total_devuelto'))['total'] or Decimal('0')
    
    # Totales netos por método
    total_efectivo = total_efectivo_bruto - dev_efectivo
    total_tarjeta = total_tarjeta_bruto - dev_tarjeta
    total_transferencia = total_transferencia_bruto - dev_transferencia

    totales = {
        'total_ventas': total_ventas_neto,
        'total_ventas_bruto': total_ventas_bruto,
        'total_devoluciones': total_devoluciones,
        'total_descuentos': total_descuentos,
        'num_ventas': num_ventas,
        'efectivo': total_efectivo,
        'tarjeta': total_tarjeta,
        'transferencia': total_transferencia,
    }

    # Ventas por día (restando devoluciones)
    ventas_por_dia_dict = defaultdict(lambda: {'total_dia': Decimal('0'), 'count': 0, 'efectivo_dia': Decimal('0'), 'tarjeta_dia': Decimal('0'), 'transferencia_dia': Decimal('0')})
    
    # Agregar ventas brutas por día
    for venta in ventas:
        dia = venta.fecha.date()
        ventas_por_dia_dict[dia]['total_dia'] += venta.total
        ventas_por_dia_dict[dia]['count'] += 1
        if venta.metodo_pago == 'efectivo':
            ventas_por_dia_dict[dia]['efectivo_dia'] += venta.total
        elif venta.metodo_pago == 'tarjeta':
            ventas_por_dia_dict[dia]['tarjeta_dia'] += venta.total
        else:
            ventas_por_dia_dict[dia]['transferencia_dia'] += venta.total
    
    # Restar devoluciones por día
    for devolucion in devoluciones:
        dia = devolucion.fecha.date()
        ventas_por_dia_dict[dia]['total_dia'] -= devolucion.total_devuelto
        if devolucion.venta.metodo_pago == 'efectivo':
            ventas_por_dia_dict[dia]['efectivo_dia'] -= devolucion.total_devuelto
        elif devolucion.venta.metodo_pago == 'tarjeta':
            ventas_por_dia_dict[dia]['tarjeta_dia'] -= devolucion.total_devuelto
        else:
            ventas_por_dia_dict[dia]['transferencia_dia'] -= devolucion.total_devuelto
    
    # Convertir a lista ordenada
    ventas_por_dia = []
    for dia in sorted(ventas_por_dia_dict.keys()):
        ventas_por_dia.append({
            'dia': dia,
            'total_dia': ventas_por_dia_dict[dia]['total_dia'],
            'count': ventas_por_dia_dict[dia]['count'],
            'efectivo_dia': ventas_por_dia_dict[dia]['efectivo_dia'],
            'tarjeta_dia': ventas_por_dia_dict[dia]['tarjeta_dia'],
            'transferencia_dia': ventas_por_dia_dict[dia]['transferencia_dia'],
        })

    # Exportar CSV
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="reporte_ventas_{fecha_desde}_{fecha_hasta}.csv"'
        response.write('\ufeff'.encode('utf-8'))
        writer = csv.writer(response)
        writer.writerow(['Fecha', 'Num. Ventas', 'Efectivo', 'Tarjeta', 'Transferencia', 'Total'])
        for row in ventas_por_dia:
            writer.writerow([
                row['dia'],
                row['count'],
                float(row['efectivo_dia']),
                float(row['tarjeta_dia']),
                float(row['transferencia_dia']),
                float(row['total_dia']),
            ])
        return response

    context = {
        'ventas_por_dia': ventas_por_dia,
        'totales': totales,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'metodo_pago': metodo_pago,
        'metodos': Venta.METODO_PAGO,
        'max_perm': get_max_permission(request.user),
    }
    return render(request, 'reportes/reporte_ventas.html', context)


@login_required
def reporte_productos(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    hoy = timezone.now().date()
    mes = hoy.replace(day=1)
    fecha_desde = request.GET.get('fecha_desde', str(mes))
    fecha_hasta = request.GET.get('fecha_hasta', str(hoy))
    
    tienda_actual = get_tienda_actual(request.user)

    # Productos más vendidos (filtrando por tienda a través de venta y producto)
    if tienda_actual:
        productos = DetalleVenta.objects.filter(
            venta__estado='completada',
            venta__fecha__date__gte=fecha_desde,
            venta__fecha__date__lte=fecha_hasta,
            venta__tienda=tienda_actual,
            producto__tienda=tienda_actual
        ).values(
            'producto__id',
            'producto__nombre',
            'producto__codigo_barra',
            'producto__precio_venta',
        ).annotate(
            total_vendido = Sum('cantidad'),
            total_ingresos = Sum('subtotal'),
            num_ventas    = Count('venta', distinct=True),
        ).order_by('-total_vendido')
    else:
        productos = DetalleVenta.objects.filter(
            venta__estado='completada',
            venta__fecha__date__gte=fecha_desde,
            venta__fecha__date__lte=fecha_hasta,
        ).values(
            'producto__id',
            'producto__nombre',
            'producto__codigo_barra',
            'producto__precio_venta',
        ).annotate(
            total_vendido = Sum('cantidad'),
            total_ingresos = Sum('subtotal'),
            num_ventas    = Count('venta', distinct=True),
        ).order_by('-total_vendido')

    # Exportar CSV
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="productos_mas_vendidos_{fecha_desde}_{fecha_hasta}.csv"'
        response.write('\ufeff'.encode('utf-8'))
        writer = csv.writer(response)
        writer.writerow(['Producto', 'Código', 'Precio venta', 'Unidades vendidas', 'Num. ventas', 'Total ingresos'])
        for p in productos:
            writer.writerow([
                p['producto__nombre'],
                p['producto__codigo_barra'] or '',
                p['producto__precio_venta'],
                p['total_vendido'],
                p['num_ventas'],
                p['total_ingresos'],
            ])
        return response

    context = {
        'productos':    productos,
        'fecha_desde':  fecha_desde,
        'fecha_hasta':  fecha_hasta,
        'max_perm':     get_max_permission(request.user),
    }
    return render(request, 'reportes/reporte_productos.html', context)


# ─── Reporte de devoluciones ─────────────────────────────────

@login_required
def reporte_devoluciones(request):
    """Reporte de devoluciones por período"""
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')
    
    from users.models import User
    from datetime import datetime
    
    # Filtros
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    vendedor_id = request.GET.get('vendedor', '').strip()
    metodo_pago = request.GET.get('metodo_pago', '').strip()
    
    tienda_actual = get_tienda_actual(request.user)
    
    # Base query
    if tienda_actual:
        devoluciones = Devolucion.objects.select_related('venta', 'usuario').filter(
            estado='aprobada',
            tienda=tienda_actual
        )
    else:
        devoluciones = Devolucion.objects.select_related('venta', 'usuario').filter(estado='aprobada')
    
    # Aplicar filtros
    if fecha_desde and fecha_desde != 'None':
        devoluciones = devoluciones.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta and fecha_hasta != 'None':
        devoluciones = devoluciones.filter(fecha__date__lte=fecha_hasta)
    if vendedor_id and vendedor_id != 'None':
        devoluciones = devoluciones.filter(usuario_id=vendedor_id)
    if metodo_pago and metodo_pago != 'None':
        devoluciones = devoluciones.filter(venta__metodo_pago=metodo_pago)
    
    # Totales generales
    total_devuelto = 0
    total_efectivo = 0
    total_tarjeta = 0
    total_transferencia = 0
    num_devoluciones = devoluciones.count()
    
    for dev in devoluciones:
        total_devuelto += float(dev.total_devuelto)
        if dev.venta.metodo_pago == 'efectivo':
            total_efectivo += float(dev.total_devuelto)
        elif dev.venta.metodo_pago == 'tarjeta':
            total_tarjeta += float(dev.total_devuelto)
        else:
            total_transferencia += float(dev.total_devuelto)
    
    # Devoluciones por día
    devoluciones_por_dia = []
    fechas = devoluciones.dates('fecha', 'day', order='DESC')
    
    for fecha in fechas:
        devs_dia = devoluciones.filter(fecha__date=fecha)
        total_dia = sum(float(d.total_devuelto) for d in devs_dia)
        devoluciones_por_dia.append({
            'dia': fecha,
            'total_dia': total_dia,
            'count': devs_dia.count()
        })
    
    # Productos más devueltos
    productos_dict = {}
    
    for dev in devoluciones:
        for detalle in dev.detalles.all():
            producto_id = detalle.producto_id
            producto_nombre = detalle.producto.nombre
            if producto_id not in productos_dict:
                productos_dict[producto_id] = {
                    'producto__id': producto_id,
                    'producto__nombre': producto_nombre,
                    'cantidad_devuelta': 0,
                    'total_devuelto': 0
                }
            productos_dict[producto_id]['cantidad_devuelta'] += detalle.cantidad
            productos_dict[producto_id]['total_devuelto'] += float(detalle.precio_unitario) * detalle.cantidad
    
    productos_devueltos = sorted(
        productos_dict.values(),
        key=lambda x: x['cantidad_devuelta'],
        reverse=True
    )[:10]
    
    # Lista de vendedores para filtro (solo de la tienda actual si aplica)
    if tienda_actual:
        vendedores = User.objects.filter(
            userrole__role__ventas__gt=0,
            tienda=tienda_actual
        ).distinct().order_by('username')
    else:
        vendedores = User.objects.filter(
            userrole__role__ventas__gt=0
        ).distinct().order_by('username')
    
    # Exportar CSV
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="reporte_devoluciones_{fecha_desde or 'inicio'}_{fecha_hasta or 'fin'}.csv"'
        response.write('\ufeff'.encode('utf-8'))
        writer = csv.writer(response)
        writer.writerow(['Fecha', 'Ticket Venta', 'Vendedor', 'Método pago', 'Total devuelto', 'Motivo'])
        
        for dev in devoluciones.order_by('-fecha'):
            writer.writerow([
                dev.fecha.strftime('%d/%m/%Y %H:%M'),
                dev.venta.id,
                dev.usuario.username,
                dev.venta.get_metodo_pago_display(),
                dev.total_devuelto,
                dev.motivo,
            ])
        return response
    
    context = {
        'devoluciones': devoluciones.order_by('-fecha')[:100],
        'devoluciones_por_dia': devoluciones_por_dia,
        'productos_devueltos': productos_devueltos,
        'totales': {
            'total_devuelto': total_devuelto,
            'num_devoluciones': num_devoluciones,
            'efectivo': total_efectivo,
            'tarjeta': total_tarjeta,
            'transferencia': total_transferencia,
        },
        'fecha_desde': fecha_desde if fecha_desde and fecha_desde != 'None' else '',
        'fecha_hasta': fecha_hasta if fecha_hasta and fecha_hasta != 'None' else '',
        'vendedor_id': vendedor_id if vendedor_id and vendedor_id != 'None' else '',
        'metodo_pago': metodo_pago if metodo_pago and metodo_pago != 'None' else '',
        'vendedores': vendedores,
        'metodos': Venta.METODO_PAGO,
    }
    return render(request, 'reportes/reporte_devoluciones.html', context)