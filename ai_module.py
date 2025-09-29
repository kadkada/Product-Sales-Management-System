from flask import request, jsonify, session
import pymysql
import re
import json
from decimal import Decimal
from datetime import datetime, timedelta
from app import get_db_connection, login_required
from ai_service import ai_service, get_database_context, get_historical_sales_data

# 自定义JSON编码器，处理Decimal类型
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return super(DecimalEncoder, self).default(obj)

def intelligent_query():
    """智能问数 - 使用AI增强的自然语言查询销售数据"""
    data = request.get_json()
    query_text = data.get('query_text', '').strip()
    
    if not query_text:
        return jsonify({"code": 0, "msg": "查询内容不能为空"})
    
    try:
        # 使用新的AI服务进行查询解析和数据库查询
        ai_result = ai_service.enhance_query_parsing(query_text)
        
        if not ai_result["success"]:
            return jsonify({
                "code": 0, 
                "msg": f"AI解析失败：{ai_result.get('error', '未知错误')}"
            })
        
        # 记录查询日志
        conn = get_db_connection()
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute(
                "INSERT INTO query_log (user_id, query_text, query_result) VALUES (%s, %s, %s)",
                (session.get('user_id'), query_text, str(ai_result))
            )
            conn.commit()
        finally:
            conn.close()
        
        return jsonify({
            "code": 1,
            "msg": "查询成功",
            "data": {
                "query_text": query_text,
                "info_type": ai_result.get("info"),
                "data_value": ai_result.get("data"),
                "explanation": ai_result.get("explanation"),
                "ai_enhanced": True
            }
        })
        
    except Exception as e:
        return jsonify({"code": 0, "msg": f"查询失败：{str(e)}"})

def get_query_history():
    """获取查询历史记录"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        cursor.execute("""
            SELECT 
                query_text,
                query_result,
                query_time
            FROM query_log
            WHERE user_id = %s
            ORDER BY query_time DESC
            LIMIT 20
        """, (session.get('user_id'),))
        
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

def query_actual_data_from_database(ai_info, cursor):
    """根据AI解析的info字段查询数据库获取实际数据"""
    print(f"查询数据库获取实际数据: {ai_info}")
    
    try:
        # 根据info内容判断查询类型并查询数据库获取实际数据
        if ai_info in ["收入", "销售额", "销售金额", "营业额", "营收"]:
            cursor.execute("SELECT SUM(total_amount) as total_sales FROM orders WHERE status != 'cancelled'")
            result = cursor.fetchone()
            return str(result['total_sales'] or 0) if result else "0"
            
        elif ai_info in ["销量", "销售量", "数量", "件数", "台数"]:
            cursor.execute("SELECT SUM(quantity) as total_quantity FROM order_detail od JOIN orders o ON od.order_id = o.order_id WHERE o.status != 'cancelled'")
            result = cursor.fetchone()
            return str(result['total_quantity'] or 0) if result else "0"
            
        elif ai_info in ["订单数", "订单量", "订单", "单数"]:
            cursor.execute("SELECT COUNT(*) as total_orders FROM orders WHERE status != 'cancelled'")
            result = cursor.fetchone()
            return str(result['total_orders'] or 0) if result else "0"
            
        elif ai_info in ["客户数", "用户数", "客户", "用户", "买家数"]:
            cursor.execute("SELECT COUNT(DISTINCT user_id) as total_customers FROM orders WHERE status != 'cancelled'")
            result = cursor.fetchone()
            return str(result['total_customers'] or 0) if result else "0"
            
        elif ai_info in ["商品种类"]:
            cursor.execute("SELECT category_name FROM category WHERE status = 1 LIMIT 5")
            categories = cursor.fetchall()
            if categories:
                return ", ".join([cat['category_name'] for cat in categories])
            else:
                return "暂无商品种类"
                
        elif ai_info in ["今天", "今日", "当天"]:
            return "今天"
        elif ai_info in ["昨天", "昨日", "前一天"]:
            return "昨天"
        elif "最近" in ai_info and "天" in ai_info:
            import re
            days_match = re.search(r'(\d+)', ai_info)
            days = int(days_match.group(1)) if days_match else 7
            return f"最近{days}天"
        elif ai_info in ["本月", "这个月", "当月"]:
            return "本月"
        elif ai_info in ["今年", "本年", "当年"]:
            return "今年"
        elif "年" in ai_info and "月" in ai_info:
            return ai_info
        else:
            # 可能是商品种类
            cursor.execute("SELECT category_name FROM category WHERE category_name = %s", (ai_info,))
            category_result = cursor.fetchone()
            if category_result:
                return category_result['category_name']
            else:
                return ai_info
                
    except Exception as e:
        print(f"查询数据库数据失败: {e}")
        return ai_info

def build_query_from_info(ai_info, actual_data, query_text, cursor):
    """根据AI返回的info字段构建查询参数"""
    print(f"AI解析信息: {ai_info}, 实际数据: {actual_data}")
    
    # 初始化查询参数
    time_info = None
    category_info = None
    metric = None
    
    # 根据info内容判断查询类型
    if ai_info in ["收入", "销售额", "销售金额", "营业额", "营收"]:
        metric = "sales"
    elif ai_info in ["销量", "销售量", "数量", "件数", "台数"]:
        metric = "quantity"
    elif ai_info in ["订单数", "订单量", "订单", "单数"]:
        metric = "orders"
    elif ai_info in ["客户数", "用户数", "客户", "用户", "买家数"]:
        metric = "customers"
    elif ai_info in ["今天", "今日", "当天"]:
        time_info = {"type": "today"}
    elif ai_info in ["昨天", "昨日", "前一天"]:
        time_info = {"type": "yesterday"}
    elif "最近" in ai_info and "天" in ai_info:
        import re
        days_match = re.search(r'(\d+)', ai_info)
        days = int(days_match.group(1)) if days_match else 7
        time_info = {"type": "week", "value": days}
    elif ai_info in ["本月", "这个月", "当月"]:
        time_info = {"type": "month"}
    elif ai_info in ["今年", "本年", "当年"]:
        time_info = {"type": "year"}
    elif "年" in ai_info and "月" in ai_info:
        import re
        year_match = re.search(r'(\d{4})年', ai_info)
        month_match = re.search(r'(\d{1,2})月', ai_info)
        if year_match and month_match:
            time_info = {
                "type": "custom",
                "year": int(year_match.group(1)),
                "month": int(month_match.group(1))
            }
    else:
        # 可能是商品种类
        cursor.execute("SELECT category_id, category_name FROM category WHERE category_name = %s", (ai_info,))
        category_result = cursor.fetchone()
        if category_result:
            category_info = {
                "category_id": category_result['category_id'],
                "category_name": category_result['category_name']
            }
    
    # 如果没有识别到指标，尝试从原始查询文本中提取
    if not metric:
        metric = extract_metric_from_text(query_text)
    
    # 如果没有识别到时间，尝试从原始查询文本中提取
    if not time_info:
        time_info = extract_time_info(query_text)
    
    # 如果没有识别到商品种类，尝试从原始查询文本中提取
    if not category_info:
        category_info = extract_category_info(query_text, cursor)
    
    if not metric:
        return None
    
    return {
        "time": time_info or {"type": "week", "value": 7},
        "category": category_info,
        "metric": metric,
        "actual_data": actual_data
    }

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

def extract_metric_from_text(text):
    """从文本中提取指标信息（与extract_metric_info功能相同）"""
    return extract_metric_info(text)

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
    """使用AI增强的商品种类销量预测"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 获取历史销售数据
        historical_data = get_historical_sales_data()
        
        # 获取市场上下文信息
        market_context = get_market_context()
        
        # 使用AI进行预测
        try:
            ai_prediction_result = ai_service.generate_sales_prediction(historical_data, market_context)
            
            if ai_prediction_result["success"]:
                # 使用AI预测结果
                ai_predictions = ai_prediction_result["predictions"]
                predictions = []
                
                for pred in ai_predictions:
                    # 获取商品种类ID，如果找不到则使用模糊匹配
                    cursor.execute("SELECT category_id FROM category WHERE category_name = %s", (pred["category_name"],))
                    category_result = cursor.fetchone()
                    
                    if not category_result:
                        # 尝试模糊匹配
                        cursor.execute("SELECT category_id, category_name FROM category WHERE category_name LIKE %s", (f"%{pred['category_name']}%",))
                        category_result = cursor.fetchone()
                    
                    if category_result:
                        predictions.append({
                            'category_id': category_result['category_id'],
                            'category_name': category_result.get('category_name', pred['category_name']),
                            'predicted_sales': pred['predicted_sales'],
                            'demand_level': pred['demand_level'],
                            'confidence': pred.get('confidence', 0.8),
                            'growth_rate': pred.get('growth_rate', 0),
                            'reasoning': pred.get('reasoning', ''),
                            'ai_enhanced': True
                        })
                        print(f"AI预测匹配成功: {pred['category_name']} -> {category_result.get('category_name', pred['category_name'])}")
                    else:
                        print(f"AI预测种类未找到: {pred['category_name']}")
            else:
                # AI预测失败，回退到传统预测方法
                predictions = fallback_prediction_method(cursor)
                
        except Exception as ai_error:
            # AI服务完全失败，回退到传统预测方法
            print(f"AI预测服务异常: {str(ai_error)}")
            predictions = fallback_prediction_method(cursor)
        
        if not predictions:
            return jsonify({"code": 0, "msg": "没有足够的历史数据用于预测"})
        
        # 保存预测结果
        prediction_date = datetime.now().date()
        
        # 先删除当天的旧预测数据
        cursor.execute("DELETE FROM sales_prediction WHERE prediction_date = %s", (prediction_date,))
        
        # 插入新的预测数据
        for pred in predictions:
            cursor.execute("""
                INSERT INTO sales_prediction 
                (category_id, category_name, predicted_sales, demand_level, prediction_date)
                VALUES (%s, %s, %s, %s, %s)
            """, (pred['category_id'], pred['category_name'], pred['predicted_sales'], 
                  pred['demand_level'], prediction_date))
        
        conn.commit()
        
        return jsonify({
            "code": 1,
            "msg": "AI预测完成",
            "data": {
                "predictions": predictions,
                "prediction_date": prediction_date.strftime('%Y-%m-%d'),
                "ai_enhanced": ai_prediction_result["success"],
                "ai_analysis": ai_prediction_result.get("ai_analysis", {})
            }
        })
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"预测功能异常: {str(e)}")
        print(f"详细错误信息: {error_detail}")
        return jsonify({"code": 0, "msg": f"预测失败：{str(e)}", "detail": error_detail})
    finally:
        conn.close()

def get_market_context():
    """获取市场上下文信息"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 获取市场趋势数据
        cursor.execute("""
            SELECT 
                DATE_FORMAT(create_time, '%Y-%m') as month,
                COUNT(*) as order_count,
                SUM(total_amount) as total_revenue,
                AVG(total_amount) as avg_order_value,
                COUNT(DISTINCT user_id) as unique_customers
            FROM orders 
            WHERE create_time >= DATE_SUB(NOW(), INTERVAL 6 MONTH) 
            AND status != 'cancelled'
            GROUP BY DATE_FORMAT(create_time, '%Y-%m')
            ORDER BY month
        """)
        
        market_data = cursor.fetchall()
        
        # 计算市场趋势
        if len(market_data) >= 2:
            latest_month = market_data[-1]
            previous_month = market_data[-2]
            
            revenue_growth = ((latest_month['total_revenue'] - previous_month['total_revenue']) / 
                            previous_month['total_revenue'] * 100) if previous_month['total_revenue'] > 0 else 0
            
            order_growth = ((latest_month['order_count'] - previous_month['order_count']) / 
                          previous_month['order_count'] * 100) if previous_month['order_count'] > 0 else 0
            
            market_context = {
                "market_trends": market_data,
                "revenue_growth_rate": revenue_growth,
                "order_growth_rate": order_growth,
                "current_performance": latest_month,
                "seasonal_factors": "基于历史数据的季节性分析",
                "market_conditions": "正常市场环境"
            }
        else:
            market_context = {
                "market_trends": market_data,
                "insufficient_data": True,
                "market_conditions": "数据不足，基于有限信息分析"
            }
        
        return json.dumps(market_context, ensure_ascii=False, indent=2, cls=DecimalEncoder)
        
    except Exception as e:
        return f"市场上下文获取失败: {str(e)}"
    finally:
        conn.close()

def fallback_prediction_method(cursor):
    """传统预测方法（作为AI预测的回退方案）"""
    print("使用传统预测方法...")
    try:
        # 获取近6个月的销售数据，如果没有数据则使用所有历史数据
        six_months_ago = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
        
        # 先检查是否有最近6个月的数据
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM orders 
            WHERE DATE(create_time) >= %s AND status != 'cancelled'
        """, (six_months_ago,))
        
        recent_count = cursor.fetchone()['count']
        print(f"最近6个月有效订单数: {recent_count}")
        
        if recent_count > 0:
            # 使用最近6个月数据
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
        else:
            # 使用所有历史数据
            print("使用所有历史数据...")
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
                WHERE o.status != 'cancelled'
                GROUP BY c.category_id, c.category_name, DATE_FORMAT(o.create_time, '%Y-%m')
                ORDER BY c.category_id, month
            """)
        
        sales_data = cursor.fetchall()
        print(f"传统预测获取到销售数据: {len(sales_data)} 条记录")
        
        if not sales_data:
            print("没有销售数据，返回空预测")
            return []
        
        # 转换为字典进行分析
        sales_dict = {}
        for item in sales_data:
            category_id = item['category_id']
            if category_id not in sales_dict:
                sales_dict[category_id] = []
            sales_dict[category_id].append(item)
        
        print(f"按种类分组后: {len(sales_dict)} 个种类")
        
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
                    previous_value = monthly_sales[-2]
                    if previous_value and previous_value != 0:
                        growth_rate = (monthly_sales[-1] - previous_value) / previous_value * 100
                    else:
                        growth_rate = 0
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
                    'growth_rate': growth_rate if len(monthly_sales) >= 2 else 0,
                    'ai_enhanced': False
                })
        
        return predictions
        
    except Exception as e:
        return []

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
