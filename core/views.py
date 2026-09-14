from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import F
from django.utils import timezone

from .models import Producto, Venta, Proveedor
from .forms import ProductoForm


def dashboard(request):
    """Panel principal con métricas rápidas del negocio."""
    total_productos = Producto.objects.count()
    total_proveedores = Proveedor.objects.count()

    productos_bajo_stock = Producto.objects.filter(
        stock_actual__lte=F('stock_minimo')
    ).select_related('proveedor')

    hoy = timezone.now().date()
    ventas_hoy = Venta.objects.filter(fecha__date=hoy)
    total_ventas_hoy = sum((v.total for v in ventas_hoy), start=0)

    context = {
        'total_productos': total_productos,
        'total_proveedores': total_proveedores,
        'productos_bajo_stock': productos_bajo_stock,
        'cantidad_bajo_stock': productos_bajo_stock.count(),
        'ventas_hoy_cantidad': ventas_hoy.count(),
        'total_ventas_hoy': total_ventas_hoy,
    }
    return render(request, 'dashboard.html', context)


def productos_lista(request):
    """Lista de productos con buscador simple por nombre."""
    query = request.GET.get('q', '').strip()
    productos = Producto.objects.select_related('proveedor').order_by('nombre')

    if query:
        productos = productos.filter(nombre__icontains=query)

    context = {
        'productos': productos,
        'query': query,
        'form': ProductoForm(),
    }
    return render(request, 'productos.html', context)


def producto_crear(request):
    """Procesa el formulario modal de creación de producto."""
    if request.method == 'POST':
        form = ProductoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Producto '{form.instance.nombre}' creado correctamente.")
            return redirect('core:productos_lista')

        messages.error(request, 'Revisa los datos del formulario, hay campos inválidos.')
        productos = Producto.objects.select_related('proveedor').order_by('nombre')
        return render(request, 'productos.html', {
            'productos': productos, 'form': form, 'query': '',
        })

    return redirect('core:productos_lista')