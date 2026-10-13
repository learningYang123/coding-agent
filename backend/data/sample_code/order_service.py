# 示例业务代码 - 电子商务订单系统

# ==================== 订单服务 ====================

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum


class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = "pending"           # 待支付
    PAID = "paid"                 # 已支付
    SHIPPED = "shipped"           # 已发货
    DELIVERED = "delivered"       # 已送达
    CANCELLED = "cancelled"       # 已取消
    REFUNDED = "refunded"         # 已退款


class PaymentMethod(Enum):
    """支付方式"""
    WECHAT = "wechat"
    ALIPAY = "alipay"
    CREDIT_CARD = "credit_card"
    BANK_TRANSFER = "bank_transfer"


class OrderItem:
    """订单商品条目"""

    def __init__(self, product_id: str, product_name: str,
                 quantity: int, unit_price: float):
        self.product_id = product_id
        self.product_name = product_name
        self.quantity = quantity
        self.unit_price = unit_price
        self.subtotal = quantity * unit_price

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "subtotal": self.subtotal,
        }


class Order:
    """订单模型"""

    def __init__(self, user_id: str, items: List[OrderItem],
                 shipping_address: str, payment_method: PaymentMethod):
        self.order_id = str(uuid.uuid4())
        self.user_id = user_id
        self.items = items
        self.shipping_address = shipping_address
        self.payment_method = payment_method
        self.status = OrderStatus.PENDING
        self.created_at = datetime.now()
        self.paid_at: Optional[datetime] = None
        self.shipped_at: Optional[datetime] = None
        self.delivered_at: Optional[datetime] = None
        self.cancelled_at: Optional[datetime] = None
        self.total_amount = sum(item.subtotal for item in items)
        self.discount_amount = 0.0
        self.final_amount = self.total_amount
        self.remark: Optional[str] = None

    def calculate_final_amount(self, discount_rate: float = 0.0) -> float:
        """计算折后金额"""
        self.discount_amount = self.total_amount * discount_rate
        self.final_amount = self.total_amount - self.discount_amount
        return self.final_amount

    def mark_as_paid(self, transaction_id: str) -> bool:
        """标记为已支付"""
        if self.status != OrderStatus.PENDING:
            return False
        self.status = OrderStatus.PAID
        self.paid_at = datetime.now()
        self.transaction_id = transaction_id
        return True

    def mark_as_shipped(self, tracking_number: str) -> bool:
        """标记为已发货"""
        if self.status != OrderStatus.PAID:
            return False
        self.status = OrderStatus.SHIPPED
        self.shipped_at = datetime.now()
        self.tracking_number = tracking_number
        return True

    def mark_as_delivered(self) -> bool:
        """标记为已送达"""
        if self.status != OrderStatus.SHIPPED:
            return False
        self.status = OrderStatus.DELIVERED
        self.delivered_at = datetime.now()
        return True

    def cancel(self, reason: str = "") -> bool:
        """取消订单"""
        if self.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.REFUNDED):
            return False
        self.status = OrderStatus.CANCELLED
        self.cancelled_at = datetime.now()
        self.cancel_reason = reason
        return True

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "status": self.status.value,
            "items": [item.to_dict() for item in self.items],
            "total_amount": self.total_amount,
            "final_amount": self.final_amount,
            "payment_method": self.payment_method.value,
            "shipping_address": self.shipping_address,
            "created_at": self.created_at.isoformat(),
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "shipped_at": self.shipped_at.isoformat() if self.shipped_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
        }


class OrderService:
    """订单服务 - 处理订单核心业务逻辑"""

    def __init__(self):
        self._orders: Dict[str, Order] = {}
        self._user_orders: Dict[str, List[str]] = {}

    def create_order(self, user_id: str, items: List[Dict],
                     shipping_address: str, payment_method: str) -> Order:
        """创建新订单"""
        # 转换商品条目
        order_items = [
            OrderItem(
                product_id=item["product_id"],
                product_name=item["product_name"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
            )
            for item in items
        ]

        # 验证库存（模拟）
        for item in order_items:
            if item.quantity <= 0:
                raise ValueError(f"商品 {item.product_name} 数量必须大于 0")
            if item.unit_price <= 0:
                raise ValueError(f"商品 {item.product_name} 价格必须大于 0")

        # 创建订单
        order = Order(
            user_id=user_id,
            items=order_items,
            shipping_address=shipping_address,
            payment_method=PaymentMethod(payment_method),
        )

        # 保存
        self._orders[order.order_id] = order
        if user_id not in self._user_orders:
            self._user_orders[user_id] = []
        self._user_orders[user_id].append(order.order_id)

        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        """查询订单"""
        return self._orders.get(order_id)

    def get_user_orders(self, user_id: str,
                        status: Optional[OrderStatus] = None) -> List[Order]:
        """获取用户的订单列表"""
        order_ids = self._user_orders.get(user_id, [])
        orders = [self._orders[oid] for oid in order_ids if oid in self._orders]

        if status:
            orders = [o for o in orders if o.status == status]

        # 按创建时间倒序
        orders.sort(key=lambda o: o.created_at, reverse=True)
        return orders

    def pay_order(self, order_id: str, transaction_id: str) -> bool:
        """
        支付订单

        业务规则：
        - 只有 PENDING 状态的订单可以支付
        - 支付成功后订单状态变为 PAID
        - 必须提供有效的交易号
        """
        order = self.get_order(order_id)
        if not order:
            raise ValueError("订单不存在")

        if not transaction_id or len(transaction_id) < 10:
            raise ValueError("无效的交易号")

        return order.mark_as_paid(transaction_id)

    def ship_order(self, order_id: str, tracking_number: str) -> bool:
        """
        发货

        业务规则：
        - 只有 PAID 状态的订单可以发货
        - 发货后状态变为 SHIPPED
        - 必须提供物流单号
        """
        order = self.get_order(order_id)
        if not order:
            raise ValueError("订单不存在")

        if order.status != OrderStatus.PAID:
            raise ValueError(f"订单当前状态 {order.status.value}，无法发货")

        if not tracking_number:
            raise ValueError("物流单号不能为空")

        return order.mark_as_shipped(tracking_number)

    def complete_order(self, order_id: str) -> bool:
        """
        确认收货

        业务规则：
        - 只有 SHIPPED 状态的订单可以确认收货
        - 确认后状态变为 DELIVERED
        - 发货后 1 天内不能确认收货（防误操作）
        """
        order = self.get_order(order_id)
        if not order:
            raise ValueError("订单不存在")

        if order.status != OrderStatus.SHIPPED:
            raise ValueError(f"订单当前状态 {order.status.value}，无法完成")

        # 检查发货时间
        min_hours = 24
        hours_since_ship = (datetime.now() - order.shipped_at).total_seconds() / 3600
        if hours_since_ship < min_hours:
            raise ValueError(
                f"发货不足 {min_hours} 小时，还不能确认收货"
            )

        return order.mark_as_delivered()

    def cancel_order(self, order_id: str, reason: str = "") -> bool:
        """
        取消订单

        业务规则：
        - PENDING 状态可直接取消
        - PAID 状态取消需走退款流程（此处简化）
        - SHIPPED/DELIVERED 状态不能取消
        """
        order = self.get_order(order_id)
        if not order:
            raise ValueError("订单不存在")

        if order.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise ValueError("已发货或已送达的订单无法取消")

        return order.cancel(reason)

    def get_orders_by_status(self, status: OrderStatus) -> List[Order]:
        """按状态查询订单（管理员功能）"""
        return [o for o in self._orders.values() if o.status == status]


# ==================== 库存服务 ====================

class InventoryService:
    """库存管理服务"""

    def __init__(self):
        self._stock: Dict[str, int] = {}
        self._reservations: Dict[str, int] = {}  # 预占库存

    def set_stock(self, product_id: str, quantity: int):
        """设置库存数量"""
        self._stock[product_id] = quantity

    def get_stock(self, product_id: str) -> int:
        """获取可用库存"""
        total = self._stock.get(product_id, 0)
        reserved = self._reservations.get(product_id, 0)
        return total - reserved

    def reserve_stock(self, product_id: str, quantity: int) -> bool:
        """
        预占库存（下单时）

        返回 True 表示预占成功
        """
        available = self.get_stock(product_id)
        if available < quantity:
            return False
        self._reservations[product_id] = (
            self._reservations.get(product_id, 0) + quantity
        )
        return True

    def confirm_stock(self, product_id: str, quantity: int):
        """
        确认扣减库存（支付成功后）
        """
        self._stock[product_id] = (
            self._stock.get(product_id, 0) - quantity
        )
        self._reservations[product_id] = (
            self._reservations.get(product_id, 0) - quantity
        )

    def release_stock(self, product_id: str, quantity: int):
        """释放预占库存（取消订单时）"""
        self._reservations[product_id] = (
            self._reservations.get(product_id, 0) - quantity
        )


# ==================== 支付服务 ====================

class PaymentService:
    """支付服务（模拟）"""

    def __init__(self):
        self._transactions: Dict[str, dict] = {}

    def process_payment(self, order_id: str, amount: float,
                        method: str) -> Dict:
        """
        处理支付（模拟）

        真实业务中这里会调用第三方支付网关
        """
        import uuid as uuid_mod

        transaction_id = f"TXN_{uuid_mod.uuid4().hex[:16].upper()}"

        transaction = {
            "transaction_id": transaction_id,
            "order_id": order_id,
            "amount": amount,
            "method": method,
            "status": "success",
            "created_at": datetime.now().isoformat(),
        }

        self._transactions[transaction_id] = transaction
        return transaction

    def refund(self, transaction_id: str, reason: str = "") -> Dict:
        """退款（模拟）"""
        txn = self._transactions.get(transaction_id)
        if not txn:
            raise ValueError("交易不存在")

        txn["status"] = "refunded"
        txn["refund_reason"] = reason
        txn["refunded_at"] = datetime.now().isoformat()

        return txn


# ==================== 使用示例 ====================

def demo_usage():
    """演示用法"""
    # 初始化服务
    order_service = OrderService()
    inventory = InventoryService()
    payment = PaymentService()

    # 设置库存
    inventory.set_stock("P001", 100)  # 商品 A
    inventory.set_stock("P002", 50)   # 商品 B

    # 用户下单
    items = [
        {"product_id": "P001", "product_name": "商品A", "quantity": 2, "unit_price": 99.0},
        {"product_id": "P002", "product_name": "商品B", "quantity": 1, "unit_price": 199.0},
    ]

    order = order_service.create_order(
        user_id="U12345",
        items=items,
        shipping_address="北京市朝阳区xxx",
        payment_method="wechat",
    )

    print(f"订单创建成功: {order.order_id}")
    print(f"订单金额: {order.total_amount}")

    # 预占库存
    inventory.reserve_stock("P001", 2)
    inventory.reserve_stock("P002", 1)

    # 支付
    txn = payment.process_payment(order.order_id, order.final_amount, "wechat")
    order_service.pay_order(order.order_id, txn["transaction_id"])

    print(f"支付成功: {txn['transaction_id']}")
    print(f"订单状态: {order.status.value}")


if __name__ == "__main__":
    demo_usage()
