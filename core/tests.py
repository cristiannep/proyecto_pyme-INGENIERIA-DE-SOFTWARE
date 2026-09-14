# core/tests.py

from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from .models import Producto, Proveedor, Compra, Venta, DetalleVenta
from decimal import Decimal

# ==========================================================
# PRUEBAS UNITARIAS
# ==========================================================
class PruebasUnitariasTestCase(TestCase):
    
    def setUp(self):
        """Prepara los datos básicos para las pruebas unitarias."""
        self.proveedor = Proveedor.objects.create(nombre="Proveedor de Prueba")
        self.producto = Producto.objects.create(
            nombre="Producto Unitario",
            proveedor=self.proveedor,
            precio_compra=Decimal('1000.00'),
            porcentaje_ganancia=Decimal('20.00'),
            stock_actual=10
        )

    def test_unit_01_calculo_precio_venta(self):
        """Prueba Unitaria 1: El cálculo del precio de venta en el modelo Producto es correcto."""
        # Cálculo: (1000 * 1.20) * 1.19 = 1428.00
        precio_esperado = Decimal('1428.00').quantize(Decimal('0.01'))
        self.assertEqual(self.producto.precio_venta, precio_esperado)

    def test_unit_02_generacion_codigo_barras(self):
        """Prueba Unitaria 2: Un nuevo producto genera un código de barras si no se provee uno."""
        producto_sin_codigo = Producto.objects.create(
            nombre="Producto Sin Código",
            precio_compra=500,
            porcentaje_ganancia=30
        )
        self.assertIsNotNone(producto_sin_codigo.codigo_barras)
        self.assertEqual(len(producto_sin_codigo.codigo_barras), 13)

    def test_unit_03_representacion_str_producto(self):
        """Prueba Unitaria 3: El método __str__ del Producto devuelve el nombre."""
        self.assertEqual(str(self.producto), "Producto Unitario")

    def test_unit_04_representacion_str_proveedor(self):
        """Prueba Unitaria 4: El método __str__ del Proveedor devuelve el nombre."""
        self.assertEqual(str(self.proveedor), "Proveedor de Prueba")

    def test_unit_05_calculo_total_compra(self):
        """Prueba Unitaria 5: La propiedad total_compra calcula el total correctamente."""
        compra = Compra(
            producto=self.producto,
            proveedor=self.proveedor,
            cantidad=5,
            precio_compra_unitario=Decimal('1100.00')
        )
        # Cálculo: 5 * 1100.00 = 5500.00
        self.assertEqual(compra.total_compra, Decimal('5500.00'))

    def test_unit_06_calculo_subtotal_detalle_venta(self):
        """Prueba Unitaria 6: La propiedad subtotal de DetalleVenta calcula el total correctamente."""
        detalle = DetalleVenta(
            cantidad=3,
            precio_venta_registrado=Decimal('1500.00')
        )
        # Cálculo: 3 * 1500.00 = 4500.00
        self.assertEqual(detalle.subtotal, Decimal('4500.00'))

    def test_unit_07_validacion_stock_insuficiente_venta(self):
        """Prueba Unitaria 7: El método clean() de Venta lanza un error si el stock es insuficiente."""
        usuario = User.objects.create_user('testuser')
        venta_excesiva = Venta(
            producto=self.producto,
            cantidad=11, # Stock actual es 10
            usuario=usuario
        )
        with self.assertRaises(ValidationError):
            venta_excesiva.clean() # clean() debe fallar

    def test_unit_08_representacion_str_compra(self):
        """Prueba Unitaria 8: El método __str__ de Compra funciona correctamente."""
        compra = Compra(id=1, producto=self.producto, cantidad=10)
        self.assertEqual(str(compra), "Compra #1 - Producto Unitario (10 unidades)")


# ==========================================================
# PRUEBAS DE INTEGRACIÓN
# ==========================================================
class PruebasIntegracionTestCase(TestCase):
    
    def setUp(self):
        """Prepara los datos básicos para las pruebas de integración."""
        self.usuario = User.objects.create_user(username='vendedor', password='123')
        self.proveedor = Proveedor.objects.create(nombre="Proveedor Principal")
        self.producto = Producto.objects.create(
            nombre="Producto de Integración",
            proveedor=self.proveedor,
            precio_compra=Decimal('2000.00'),
            porcentaje_ganancia=Decimal('50.00'),
            stock_actual=100
        )

    def test_int_01_crear_compra_aumenta_stock(self):
        """Prueba de Integración 1: Al crear una Compra, el stock del Producto aumenta."""
        stock_inicial = self.producto.stock_actual
        Compra.objects.create(
            proveedor=self.proveedor,
            producto=self.producto,
            cantidad=25
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, stock_inicial + 25)

    def test_int_02_eliminar_compra_disminuye_stock(self):
        """Prueba de Integración 2: Al eliminar una Compra, el stock del Producto disminuye."""
        compra = Compra.objects.create(
            proveedor=self.proveedor,
            producto=self.producto,
            cantidad=10
        )
        self.producto.refresh_from_db()
        stock_despues_de_compra = self.producto.stock_actual
        
        compra.delete()
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, stock_despues_de_compra - 10)

    def test_int_03_crear_venta_disminuye_stock(self):
        """Prueba de Integración 3: Al crear una Venta, el stock del Producto disminuye."""
        stock_inicial = self.producto.stock_actual
        Venta.objects.create(
            usuario=self.usuario,
            producto=self.producto,
            cantidad=5
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, stock_inicial - 5)

    def test_int_04_eliminar_venta_restaura_stock(self):
        """Prueba de Integración 4: Al eliminar una Venta, el stock del Producto se restaura."""
        venta = Venta.objects.create(
            usuario=self.usuario,
            producto=self.producto,
            cantidad=8
        )
        self.producto.refresh_from_db()
        stock_despues_de_venta = self.producto.stock_actual
        
        venta.delete()
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, stock_despues_de_venta + 8)

    def test_int_05_editar_compra_ajusta_stock(self):
        """Prueba de Integración 5: Al editar la cantidad de una Compra, el stock se ajusta correctamente."""
        compra = Compra.objects.create(proveedor=self.proveedor, producto=self.producto, cantidad=10)
        self.producto.refresh_from_db()
        stock_intermedio = self.producto.stock_actual # Debería ser 110
        
        # --- LÍNEA CORREGIDA ---
        # Volvemos a cargar la compra desde la BD para simular una edición real
        compra_a_editar = Compra.objects.get(pk=compra.pk)
        compra_a_editar.cantidad = 15 # Aumentamos en 5
        compra_a_editar.save()
        
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, stock_intermedio + 5)

    def test_int_06_editar_venta_ajusta_stock(self):
        """Prueba de Integración 6: Al editar la cantidad de una Venta, el stock se ajusta correctamente."""
        venta = Venta.objects.create(usuario=self.usuario, producto=self.producto, cantidad=10)
        self.producto.refresh_from_db()
        stock_intermedio = self.producto.stock_actual # Debería ser 90
        
        # --- LÍNEA CORREGIDA ---
        # Volvemos a cargar la venta desde la BD
        venta_a_editar = Venta.objects.get(pk=venta.pk)
        venta_a_editar.cantidad = 7 # Disminuimos la venta en 3, el stock debe aumentar en 3
        venta_a_editar.save()
        
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, stock_intermedio + 3)
        
    def test_int_07_proteger_borrado_producto_con_compra(self):
        """Prueba de Integración 7: Un Producto no se puede eliminar si tiene Compras asociadas."""
        Compra.objects.create(proveedor=self.proveedor, producto=self.producto, cantidad=1)
        with self.assertRaises(ProtectedError):
            self.producto.delete()

    def test_int_08_proteger_borrado_proveedor_con_compra(self):
        """Prueba de Integración 8: Un Proveedor no se puede eliminar si tiene Compras asociadas."""
        Compra.objects.create(proveedor=self.proveedor, producto=self.producto, cantidad=1)
        with self.assertRaises(ProtectedError):
            self.proveedor.delete()
