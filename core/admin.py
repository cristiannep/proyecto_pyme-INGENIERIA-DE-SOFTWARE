# core/admin.py
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from .models import Proveedor, Producto, Venta, DetalleVenta, Compra

# ========================================================== 
# Detalles dentro de la venta 
# ========================================================== 
class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 1
    fields = ('producto', 'cantidad', 'precio_venta_registrado_display', 'subtotal_display')
    readonly_fields = ('precio_venta_registrado_display', 'subtotal_display')
    
    def precio_venta_registrado_display(self, obj):
        """Muestra el precio unitario del producto (si existe)"""
        if obj.id:
            return f"${obj.precio_venta_registrado:,.0f}"
        return "-"
    precio_venta_registrado_display.short_description = "Precio Unitario"
    
    def subtotal_display(self, obj):
        """Muestra el subtotal calculado"""
        if obj.id:
            return f"${obj.subtotal:,.0f}"
        return "-"
    subtotal_display.short_description = "Subtotal"

# ========================================================== 
# ADMIN: Ventas CON VALIDACIÓN DE STOCK
# ========================================================== 
@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'usuario', 'producto', 'cantidad', 'total_display', 'estado_stock')
    list_filter = ('fecha', 'usuario')
    readonly_fields = ('fecha', 'total_display', 'alerta_stock_display')
    fields = ('producto', 'cantidad', 'alerta_stock_display', 'fecha', 'total_display')
    
    #  Habilitar acciones de eliminación múltiple
    actions = ['eliminar_ventas_seleccionadas']
    
    def total_display(self, obj):
        if obj.id:
            return f"${obj.total:,.0f}"
        return "$0"
    total_display.short_description = "Total"
    
    def estado_stock(self, obj):
        """ Muestra el estado del stock en la lista"""
        if obj.producto:
            stock = obj.producto.stock_actual
            if stock == 0:
                return format_html('<span style="color: red;"> SIN STOCK</span>')
            elif stock < obj.cantidad:
                return format_html('<span style="color: orange;"> STOCK BAJO ({}/{})</span>', stock, obj.cantidad)
            else:
                return format_html('<span style="color: green;"> OK</span>')
        return "-"
    estado_stock.short_description = "Estado Stock"
    
    def alerta_stock_display(self, obj):
        """ Muestra alerta en el formulario de edición"""
        if obj.producto:
            stock = obj.producto.stock_actual
            cantidad = obj.cantidad or 0
            
            if stock == 0:
                return format_html(
                    '<div style="background: #ffebee; padding: 10px; border-left: 4px solid #f44336;">'
                    '<strong> SIN STOCK</strong><br>'
                    'No hay unidades disponibles de "{}".'
                    '</div>',
                    obj.producto.nombre
                )
            elif cantidad > stock:
                return format_html(
                    '<div style="background: #fff3e0; padding: 10px; border-left: 4px solid #ff9800;">'
                    '<strong> STOCK INSUFICIENTE</strong><br>'
                    'Solicitado: {} unidades<br>'
                    'Disponible: {} unidades<br>'
                    '<em>Ajusta la cantidad o realiza la venta por lo disponible.</em>'
                    '</div>',
                    cantidad, stock
                )
            else:
                return format_html(
                    '<div style="background: #e8f5e9; padding: 10px; border-left: 4px solid #4caf50;">'
                    ' Stock disponible: {} unidades'
                    '</div>',
                    stock
                )
        return "-"
    alerta_stock_display.short_description = "Estado del Stock"
    
    def save_model(self, request, obj, form, change):
        """ Guarda con validación y mensajes de usuario"""
        if not obj.usuario:
            obj.usuario = request.user
        
        try:
            # Detectar si es una edición
            es_edicion = change and obj.pk
            
            if es_edicion:
                cantidad_anterior = obj._cantidad_anterior
                diferencia = obj.cantidad - cantidad_anterior
                
                if diferencia != 0:
                    messages.info(
                        request,
                        f' Ajustando venta: {"+" if diferencia > 0 else ""}{diferencia} unidades'
                    )
            
            super().save_model(request, obj, form, change)
            
            # Mensaje de éxito con información del stock restante
            if obj.producto:
                stock_restante = obj.producto.stock_actual
                if stock_restante <= obj.producto.stock_minimo:
                    messages.warning(
                        request,
                        f' {"Venta actualizada" if es_edicion else "Venta registrada"}. '
                        f'Stock de "{obj.producto.nombre}" está bajo el mínimo: {stock_restante} unidades.'
                    )
                else:
                    messages.success(
                        request,
                        f' {"Venta actualizada" if es_edicion else "Venta registrada"} correctamente. '
                        f'Stock restante: {stock_restante} unidades.'
                    )
        
        except ValidationError as e:
            #  Capturar error de validación y mostrarlo al usuario
            messages.error(request, f' Error: {e.message}')
            raise
        
        except Exception as e:
            messages.error(request, f' Error inesperado: {str(e)}')
            raise
    
    def delete_model(self, request, obj):
        """ Al eliminar una venta individual"""
        producto_nombre = obj.producto.nombre if obj.producto else "Producto"
        cantidad = obj.cantidad
        producto = obj.producto
        
        # Primero eliminar la venta (esto elimina DetalleVenta por CASCADE)
        super().delete_model(request, obj)
        
        # MANUALMENTE devolver el stock (por si el CASCADE no ejecutó el delete() de DetalleVenta)
        if producto and cantidad:
            producto.stock_actual += cantidad
            producto.save()
        
        messages.success(
            request,
            f' Venta eliminada. Stock de "{producto_nombre}" restaurado: +{cantidad} unidades.'
        )
    
    def delete_queryset(self, request, queryset):
        """ Al eliminar múltiples ventas"""
        total_ventas = queryset.count()
        
        # Recopilar información y devolver stock ANTES de eliminar
        ajustes_stock = {}
        for venta in queryset:
            if venta.producto:
                producto = venta.producto
                if producto.id not in ajustes_stock:
                    ajustes_stock[producto.id] = {
                        'nombre': producto.nombre,
                        'cantidad': 0,
                        'objeto': producto
                    }
                ajustes_stock[producto.id]['cantidad'] += venta.cantidad
        
        # Eliminar las ventas
        queryset.delete()
        
        # MANUALMENTE devolver el stock
        for producto_id, info in ajustes_stock.items():
            producto = info['objeto']
            producto.stock_actual += info['cantidad']
            producto.save()
        
        # Mensaje informativo
        mensaje = f' {total_ventas} venta(s) eliminada(s). Stock restaurado:\n'
        for info in ajustes_stock.values():
            mensaje += f'  • {info["nombre"]}: +{info["cantidad"]} unidades\n'
        
        messages.success(request, mensaje)
    
    def eliminar_ventas_seleccionadas(self, request, queryset):
        """Acción personalizada para eliminar ventas"""
        self.delete_queryset(request, queryset)
    
    eliminar_ventas_seleccionadas.short_description = " Eliminar ventas seleccionadas (restaura stock)"

# ========================================================== 
# ADMIN: Productos 
# ========================================================== 
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = (
        'codigo_barras', 
        'nombre', 
        'proveedor', 
        'precio_compra', 
        'precio_venta_display', 
        'stock_actual', 
        'stock_minimo', 
        'alerta_stock'
    )
    search_fields = ('nombre', 'codigo_barras', 'proveedor__nombre')
    list_filter = ('proveedor', 'stock_minimo')
    readonly_fields = ('codigo_barras',)
    
    def precio_venta_display(self, obj):
        return f"${obj.precio_venta:,.0f}"
    precio_venta_display.short_description = "Precio Venta"
    
    def alerta_stock(self, obj):
        if obj.stock_actual == 0:
            return format_html('<span style="color: red; font-weight: bold;"> SIN STOCK</span>')
        elif obj.stock_actual <= obj.stock_minimo:
            return format_html('<span style="color: orange; font-weight: bold;"> BAJO</span>')
        return format_html('<span style="color: green;"> OK</span>')
    alerta_stock.short_description = "Estado Stock"

# ========================================================== 
# ADMIN: Proveedores 
# ========================================================== 
@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'productos_asociados')
    search_fields = ('nombre',)
    
    def productos_asociados(self, obj):
        return obj.productos.count()
    productos_asociados.short_description = "N° Productos"

# ========================================================== 
# ADMIN: Detalle de Venta
# ========================================================== 
@admin.register(DetalleVenta)
class DetalleVentaAdmin(admin.ModelAdmin):
    list_display = ('venta', 'producto', 'proveedor', 'usuario', 'cantidad', 'precio_venta_registrado', 'subtotal_display')
    list_filter = ('venta__fecha', 'producto__proveedor', 'proveedor', 'usuario')
    readonly_fields = ('proveedor', 'usuario')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def subtotal_display(self, obj):
        return f"${obj.subtotal:,.0f}"
    subtotal_display.short_description = "Subtotal"

# ========================================================== 
# ADMIN: Compras
# ========================================================== 
@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'proveedor', 'producto', 'cantidad', 'precio_compra_unitario_display', 'total_compra_display', 'usuario')
    list_filter = ('fecha', 'proveedor', 'usuario')
    readonly_fields = ('fecha', 'total_compra_display', 'precio_sugerido_display')
    fields = ('proveedor', 'producto', 'cantidad', 'precio_sugerido_display', 'precio_compra_unitario', 'total_compra_display', 'fecha')
    search_fields = ('producto__nombre', 'proveedor__nombre')
    
    # Habilitar acciones de eliminación múltiple
    actions = ['eliminar_compras_seleccionadas']
    
    def precio_compra_unitario_display(self, obj):
        if obj.precio_compra_unitario:
            return f"${obj.precio_compra_unitario:,.0f}"
        return "-"
    precio_compra_unitario_display.short_description = "Precio Unit."
    
    def precio_sugerido_display(self, obj):
        """ Muestra el precio de compra del producto como referencia"""
        if obj.producto:
            return format_html(
                '<div style="background: #e3f2fd; padding: 8px; border-radius: 4px;">'
                ' <strong>Precio sugerido:</strong> ${:,.0f} '
                '<small>(del catálogo de productos)</small>'
                '</div>',
                obj.producto.precio_compra
            )
        return "-"
    precio_sugerido_display.short_description = "Referencia"
    
    #  Habilitar acciones de eliminación múltiple
    actions = ['eliminar_compras_seleccionadas']
    
    def total_compra_display(self, obj):
        if obj.id:
            return f"${obj.total_compra:,.0f}"
        return "$0"
    total_compra_display.short_description = "Total Compra"
    
    def save_model(self, request, obj, form, change):
        """ Guarda compra y asigna usuario automáticamente"""
        if not obj.usuario:
            obj.usuario = request.user
        
        try:
            es_edicion = change and obj.pk
            
            if es_edicion:
                cantidad_anterior = obj._cantidad_anterior
                diferencia = obj.cantidad - cantidad_anterior
                
                if diferencia != 0:
                    messages.info(
                        request,
                        f' Ajustando compra: {"+" if diferencia > 0 else ""}{diferencia} unidades'
                    )
            
            super().save_model(request, obj, form, change)
            
            # Mensaje de éxito
            stock_actual = obj.producto.stock_actual
            messages.success(
                request,
                f' {"Compra actualizada" if es_edicion else "Compra registrada"} correctamente. '
                f'Stock actual de "{obj.producto.nombre}": {stock_actual} unidades.'
            )
        
        except Exception as e:
            messages.error(request, f' Error: {str(e)}')
            raise
    
    def delete_model(self, request, obj):
        """ Al eliminar una compra individual"""
        producto_nombre = obj.producto.nombre
        cantidad = obj.cantidad
        producto = obj.producto
        
        # Eliminar la compra
        super().delete_model(request, obj)
        
        # El método delete() del modelo ya ajustó el stock
        messages.success(
            request,
            f' Compra eliminada. Stock de "{producto_nombre}" ajustado: -{cantidad} unidades. '
            f'Stock actual: {producto.stock_actual} unidades.'
        )
    
    def delete_queryset(self, request, queryset):
        """ Al eliminar múltiples compras"""
        total_compras = queryset.count()
        
        # Recopilar información ANTES de eliminar
        ajustes_stock = {}
        for compra in queryset:
            producto = compra.producto
            if producto.id not in ajustes_stock:
                ajustes_stock[producto.id] = {
                    'nombre': producto.nombre,
                    'cantidad': 0,
                    'objeto': producto
                }
            ajustes_stock[producto.id]['cantidad'] += compra.cantidad
        
        # Eliminar las compras (los métodos delete() individuales ajustarán el stock)
        for compra in queryset:
            compra.delete()
        
        # Mensaje informativo
        mensaje = f' {total_compras} compra(s) eliminada(s). Stock ajustado:\n'
        for info in ajustes_stock.values():
            producto_actual = info['objeto']
            producto_actual.refresh_from_db()
            mensaje += f'  • {info["nombre"]}: -{info["cantidad"]} unidades (Stock actual: {producto_actual.stock_actual})\n'
        
        messages.success(request, mensaje)
    
    def eliminar_compras_seleccionadas(self, request, queryset):
        """ Acción personalizada para eliminar compras"""
        self.delete_queryset(request, queryset)
    
    eliminar_compras_seleccionadas.short_description = " Eliminar compras seleccionadas (ajusta stock)"