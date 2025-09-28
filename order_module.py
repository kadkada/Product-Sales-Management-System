from flask import request, jsonify, session
import pymysql
import time
import random
from datetime import datetime
from app import get_db_connection, login_required, admin_required

def generate_order_id():
    """生成唯一订单号"""
    timestamp = int(time.time())
    random_num = random.randint(1000, 9999)
    return f"{timestamp}{random_num}"

def create_order():
    """创建订单"""
    data = request.get_json()
    user_id = data.get('user_id')
    goods_list = data.get('goods_list', [])
    shipping_address = data.get('shipping_address', '')
    contact_phone = data.get('contact_phone', '')
    remark = data.get('remark', '')
    
    if not user_id or not goods_list:
        return jsonify({"code": 0, "msg": "用户ID和商品列表不能为空"})
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 计算订单总金额并检查库存
        total_amount = 0
        order_details = []
        
        for item in goods_list:
            goods_id = item.get('goods_id')
            quantity = int(item.get('quantity', 0))
            
            if not goods_id or quantity <= 0:
                return jsonify({"code": 0, "msg": "商品ID和数量必须大于0"})
            
            # 查询商品信息
            cursor.execute(
                "SELECT goods_id, goods_name, price, stock FROM goods WHERE goods_id=%s AND status=1",
                (goods_id,)
            )
            goods = cursor.fetchone()
            
            if not goods:
                return jsonify({"code": 0, "msg": f"商品ID {goods_id} 不存在或已下架"})
            
            if goods['stock'] < quantity:
                return jsonify({"code": 0, "msg": f"商品 {goods['goods_name']} 库存不足，当前库存：{goods['stock']}"})
            
            subtotal = goods['price'] * quantity
            total_amount += subtotal
            
            order_details.append({
                'goods_id': goods_id,
                'goods_name': goods['goods_name'],
                'price': goods['price'],
                'quantity': quantity,
                'subtotal': subtotal
            })
        
        # 生成订单号
        order_id = generate_order_id()
        
        # 开始事务
        cursor.execute("START TRANSACTION")
        
        # 插入订单
        cursor.execute(
            "INSERT INTO orders (order_id, user_id, total_amount, shipping_address, contact_phone, remark) VALUES (%s, %s, %s, %s, %s, %s)",
            (order_id, user_id, total_amount, shipping_address, contact_phone, remark)
        )
        
        # 插入订单详情并扣减库存
        for detail in order_details:
            cursor.execute(
                "INSERT INTO order_detail (order_id, goods_id, goods_name, price, quantity, subtotal) VALUES (%s, %s, %s, %s, %s, %s)",
                (order_id, detail['goods_id'], detail['goods_name'], detail['price'], detail['quantity'], detail['subtotal'])
            )
            
            # 扣减库存
            cursor.execute(
                "UPDATE goods SET stock = stock - %s WHERE goods_id = %s",
                (detail['quantity'], detail['goods_id'])
            )
        
        # 提交事务
        cursor.execute("COMMIT")
        
        return jsonify({
            "code": 1,
            "msg": "订单创建成功",
            "data": {"order_id": order_id, "total_amount": total_amount}
        })
        
    except Exception as e:
        cursor.execute("ROLLBACK")
        return jsonify({"code": 0, "msg": f"订单创建失败：{str(e)}"})
    finally:
        conn.close()

def get_order_list():
    """获取订单列表"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    status = request.args.get('status', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    offset = (page - 1) * page_size
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 构建查询条件
        where_clause = "WHERE 1=1"
        params = []
        
        if status:
            where_clause += " AND o.status = %s"
            params.append(status)
        
        if start_date:
            where_clause += " AND DATE(o.create_time) >= %s"
            params.append(start_date)
        
        if end_date:
            where_clause += " AND DATE(o.create_time) <= %s"
            params.append(end_date)
        
        # 查询总数
        cursor.execute(f"SELECT COUNT(*) as total FROM orders o {where_clause}", params)
        total = cursor.fetchone()['total']
        
        # 查询数据
        cursor.execute(
            f"SELECT o.*, u.username, u.real_name FROM orders o LEFT JOIN user u ON o.user_id = u.user_id {where_clause} ORDER BY o.create_time DESC LIMIT %s OFFSET %s",
            params + [page_size, offset]
        )
        orders = cursor.fetchall()
        
        return jsonify({
            "code": 1,
            "msg": "获取成功",
            "data": {
                "list": orders,
                "total": total,
                "page": page,
                "page_size": page_size
            }
        })
    except Exception as e:
        return jsonify({"code": 0, "msg": f"获取失败：{str(e)}"})
    finally:
        conn.close()

def get_order_detail():
    """获取订单详情"""
    order_id = request.args.get('order_id')
    
    if not order_id:
        return jsonify({"code": 0, "msg": "订单ID不能为空"})
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 查询订单基本信息
        cursor.execute(
            "SELECT o.*, u.username, u.real_name FROM orders o LEFT JOIN user u ON o.user_id = u.user_id WHERE o.order_id = %s",
            (order_id,)
        )
        order_info = cursor.fetchone()
        
        if not order_info:
            return jsonify({"code": 0, "msg": "订单不存在"})
        
        # 查询订单详情
        cursor.execute(
            "SELECT * FROM order_detail WHERE order_id = %s ORDER BY detail_id",
            (order_id,)
        )
        order_details = cursor.fetchall()
        
        return jsonify({
            "code": 1,
            "msg": "获取成功",
            "data": {
                "order_info": order_info,
                "order_details": order_details
            }
        })
    except Exception as e:
        return jsonify({"code": 0, "msg": f"获取失败：{str(e)}"})
    finally:
        conn.close()

def update_order_status():
    """更新订单状态"""
    data = request.get_json()
    order_id = data.get('order_id')
    status = data.get('status')
    
    if not order_id or not status:
        return jsonify({"code": 0, "msg": "订单ID和状态不能为空"})
    
    valid_statuses = ['pending', 'shipped', 'completed', 'cancelled']
    if status not in valid_statuses:
        return jsonify({"code": 0, "msg": "无效的订单状态"})
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 检查订单是否存在
        cursor.execute("SELECT order_id FROM orders WHERE order_id = %s", (order_id,))
        if not cursor.fetchone():
            return jsonify({"code": 0, "msg": "订单不存在"})
        
        # 更新订单状态
        cursor.execute(
            "UPDATE orders SET status = %s WHERE order_id = %s",
            (status, order_id)
        )
        conn.commit()
        
        return jsonify({"code": 1, "msg": "订单状态更新成功"})
    except Exception as e:
        conn.rollback()
        return jsonify({"code": 0, "msg": f"更新失败：{str(e)}"})
    finally:
        conn.close()
