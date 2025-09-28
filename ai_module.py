from flask import request, jsonify, session
import pymysql
import re
# import pandas as pd
# import numpy as np
from datetime import datetime, timedelta
from app import get_db_connection, login_required

def intelligent_query():
    """智能问数 - 自然语言查询销售数据"""
    data = request.get_json()
    query_text = data.get('query_text', '').strip()
    
    if not query_text:
        return jsonify({"code": 0, "msg": "查询内容不能为空"})
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 解析查询内容
        parsed_query = parse_query(query_text)
        
        if not parsed_query:
            return jsonify({
                "code": 0, 
                "msg": "请尝试更简洁的提问方式，如'[时间] [商品种类] 的 [销售额/销量] 是多少'"
            })
        
        # 执行查询
        result = execute_parsed_query(cursor, parsed_query)
        
        # 记录查询日志
        cursor.execute(
            "INSERT INTO query_log (user_id, query_text, query_result) VALUES (%s, %s, %s)",
            (session.get('user_id'), query_text, str(result))
        )
        conn.commit()
        
        return jsonify({
            "code": 1,
            "msg": "查询成功",
            "data": {
                "query_text": query_text,
                "parsed_query": parsed_query,
                "result": result
            }
        })
        
    except Exception as e:
        return jsonify({"code": 0, "msg": f"查询失败：{str(e)}"})
    finally:
        conn.close()

def parse_query(query_text):
    """解析自然语言查询"""
    query_text = query_text.lower()
    
    # 提取时间信息
    time_info = extract_time_info(query_text)
    
    # 提取商品种类信息
    category_info = extract_category_info(query_text)
    
    # 提取指标信息
    metric_info = extract_metric_info(query_text)
    
    if not metric_info:
        return None
    
    return {
        'time': time_info,
        'category': category_info,
        'metric': metric_info
    }

def extract_time_info(text):
    """提取时间信息"""
    # 匹配各种时间表达
    patterns = {
        'today': r'今天|今日',
        'yesterday': r'昨天|昨日',
        'week': r'近.*?天|最近.*?天|过去.*?天',
        'month': r'本月|这个月|当月',
        'year': r'今年|本年|当年',
        'custom': r'(\d{4})年(\d{1,2})月'
    }
    
    for key, pattern in patterns.items():
        if re.search(pattern, text):
            if key == 'week':
                # 提取天数
                match = re.search(r'(\d+)天', text)
                if match:
                    return {'type': 'days', 'value': int(match.group(1))}
            elif key == 'custom':
                match = re.search(pattern, text)
                if match:
                    year = int(match.group(1))
                    month = int(match.group(2))
                    return {'type': 'month', 'year': year, 'month': month}
            else:
                return {'type': key}
    
    return {'type': 'week', 'value': 7}  # 默认最近7天

def extract_category_info(text):
    """提取商品种类信息"""
    # 查询所有商品种类
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT category_id, category_name FROM category WHERE status = 1")
        categories = cursor.fetchall()
        
        for category in categories:
            if category['category_name'] in text:
                return {
                    'category_id': category['category_id'],
                    'category_name': category['category_name']
                }
    except:
        pass
    finally:
        conn.close()
    
    return None

def extract_metric_info(text):
    """提取指标信息"""
    metrics = {
        'sales': ['销售额', '销售金额', '营业额', '收入'],
        'quantity': ['销量', '销售量', '数量', '件数'],
        'orders': ['订单数', '订单量', '订单'],
        'customers': ['客户数', '客户量', '用户数']
    }
    
    for metric, keywords in metrics.items():
        for keyword in keywords:
            if keyword in text:
                return metric
    
    return None

def execute_parsed_query(cursor, parsed_query):
    """执行解析后的查询"""
    time_info = parsed_query['time']
    category_info = parsed_query['category']
    metric = parsed_query['metric']
    
    # 构建时间条件
    time_condition = build_time_condition(time_info)
    
    # 构建种类条件
    category_condition = ""
    params = []
    
    if category_info:
        category_condition = "AND g.category_id = %s"
        params.append(category_info['category_id'])
    
    # 根据指标类型构建查询
    if metric == 'sales':
        sql = f"""
            SELECT SUM(o.total_amount) as value
            FROM orders o
            LEFT JOIN order_detail od ON o.order_id = od.order_id
            LEFT JOIN goods g ON od.goods_id = g.goods_id
            WHERE {time_condition} AND o.status != 'cancelled' {category_condition}
        """
    elif metric == 'quantity':
        sql = f"""
            SELECT SUM(od.quantity) as value
            FROM order_detail od
            LEFT JOIN orders o ON od.order_id = o.order_id
            LEFT JOIN goods g ON od.goods_id = g.goods_id
            WHERE {time_condition} AND o.status != 'cancelled' {category_condition}
        """
    elif metric == 'orders':
        sql = f"""
            SELECT COUNT(*) as value
            FROM orders o
            LEFT JOIN order_detail od ON o.order_id = od.order_id
            LEFT JOIN goods g ON od.goods_id = g.goods_id
            WHERE {time_condition} AND o.status != 'cancelled' {category_condition}
        """
    elif metric == 'customers':
        sql = f"""
            SELECT COUNT(DISTINCT o.user_id) as value
            FROM orders o
            LEFT JOIN order_detail od ON o.order_id = od.order_id
            LEFT JOIN goods g ON od.goods_id = g.goods_id
            WHERE {time_condition} AND o.status != 'cancelled' {category_condition}
        """
    
    cursor.execute(sql, params)
    result = cursor.fetchone()
    
    return {
        'metric': metric,
        'value': result['value'] or 0,
        'category': category_info['category_name'] if category_info else '全部',
        'time_period': format_time_period(time_info)
    }

def build_time_condition(time_info):
    """构建时间查询条件"""
    if time_info['type'] == 'today':
        return "DATE(o.create_time) = CURDATE()"
    elif time_info['type'] == 'yesterday':
        return "DATE(o.create_time) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)"
    elif time_info['type'] == 'week':
        days = time_info.get('value', 7)
        return f"DATE(o.create_time) >= DATE_SUB(CURDATE(), INTERVAL {days} DAY)"
    elif time_info['type'] == 'month':
        return "DATE_FORMAT(o.create_time, '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m')"
    elif time_info['type'] == 'year':
        return "YEAR(o.create_time) = YEAR(CURDATE())"
    elif time_info['type'] == 'custom':
        year = time_info['year']
        month = time_info['month']
        return f"YEAR(o.create_time) = {year} AND MONTH(o.create_time) = {month}"
    
    return "DATE(o.create_time) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"

def format_time_period(time_info):
    """格式化时间周期显示"""
    if time_info['type'] == 'today':
        return '今天'
    elif time_info['type'] == 'yesterday':
        return '昨天'
    elif time_info['type'] == 'week':
        days = time_info.get('value', 7)
        return f'最近{days}天'
    elif time_info['type'] == 'month':
        return '本月'
    elif time_info['type'] == 'year':
        return '今年'
    elif time_info['type'] == 'custom':
        return f"{time_info['year']}年{time_info['month']}月"
    
    return '最近7天'

def sales_prediction():
    """商品种类销量预测"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 获取近6个月的销售数据
        six_months_ago = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
        
        cursor.execute("""
            SELECT 
                c.category_id,
                c.category_name,
                DATE_FORMAT(o.create_time, '%Y-%m') as month,
                SUM(od.quantity) as monthly_sales
            FROM order_detail od
            LEFT JOIN goods g ON od.goods_id = g.goods_id
            LEFT JOIN category c ON g.category_id = c.category_id
            LEFT JOIN orders o ON od.order_id = o.order_id
            WHERE DATE(o.create_time) >= %s AND o.status != 'cancelled'
            GROUP BY c.category_id, c.category_name, DATE_FORMAT(o.create_time, '%Y-%m')
            ORDER BY c.category_id, month
        """, (six_months_ago,))
        
        sales_data = cursor.fetchall()
        
        if not sales_data:
            return jsonify({"code": 0, "msg": "没有足够的历史数据用于预测"})
        
        # 转换为字典进行分析
        sales_dict = {}
        for item in sales_data:
            category_id = item['category_id']
            if category_id not in sales_dict:
                sales_dict[category_id] = []
            sales_dict[category_id].append(item)
        
        # 按种类分组进行预测
        predictions = []
        for category_id, items in sales_dict.items():
            if not items:
                continue
                
            category_name = items[0]['category_name']
            
            # 使用简单移动平均法预测
            monthly_sales = [item['monthly_sales'] for item in items]
            
            if len(monthly_sales) >= 3:
                # 计算3个月移动平均
                predicted_sales = int(sum(monthly_sales[-3:]) / len(monthly_sales[-3:]))
                
                # 计算需求等级
                if len(monthly_sales) >= 2:
                    growth_rate = (monthly_sales[-1] - monthly_sales[-2]) / monthly_sales[-2] * 100
                    if growth_rate >= 15:
                        demand_level = 'high'
                    elif growth_rate >= 0:
                        demand_level = 'medium'
                    else:
                        demand_level = 'low'
                else:
                    demand_level = 'medium'
                
                predictions.append({
                    'category_id': category_id,
                    'category_name': category_name,
                    'predicted_sales': predicted_sales,
                    'demand_level': demand_level,
                    'growth_rate': growth_rate if len(monthly_sales) >= 2 else 0
                })
        
        # 保存预测结果
        prediction_date = datetime.now().date()
        for pred in predictions:
            cursor.execute("""
                INSERT INTO sales_prediction 
                (category_id, category_name, predicted_sales, demand_level, prediction_date)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                predicted_sales = VALUES(predicted_sales),
                demand_level = VALUES(demand_level),
                create_time = CURRENT_TIMESTAMP
            """, (pred['category_id'], pred['category_name'], pred['predicted_sales'], 
                  pred['demand_level'], prediction_date))
        
        conn.commit()
        
        return jsonify({
            "code": 1,
            "msg": "预测完成",
            "data": {
                "predictions": predictions,
                "prediction_date": prediction_date.strftime('%Y-%m-%d')
            }
        })
        
    except Exception as e:
        return jsonify({"code": 0, "msg": f"预测失败：{str(e)}"})
    finally:
        conn.close()

def get_prediction_history():
    """获取预测历史记录"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        cursor.execute("""
            SELECT 
                prediction_date,
                category_name,
                predicted_sales,
                demand_level,
                create_time
            FROM sales_prediction
            ORDER BY prediction_date DESC, category_name
        """)
        
        history = cursor.fetchall()
        
        return jsonify({
            "code": 1,
            "msg": "获取成功",
            "data": history
        })
        
    except Exception as e:
        return jsonify({"code": 0, "msg": f"获取失败：{str(e)}"})
    finally:
        conn.close()
