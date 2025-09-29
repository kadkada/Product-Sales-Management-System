#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI服务模块 - 集成SiliconFlow API
"""

import requests
import json
import pymysql
from datetime import datetime, timedelta
from decimal import Decimal
from app import get_db_connection

# 自定义JSON编码器，处理Decimal类型
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return super(DecimalEncoder, self).default(obj)

# SiliconFlow API配置
SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/chat/completions"
SILICONFLOW_API_KEY = "sk-vfxewwbfcgthjjabvksdrezxdvtwqjmpdglubfthmzinlren"

class AIService:
    """AI服务类"""

    def __init__(self):
        self.api_url = SILICONFLOW_API_URL
        self.api_key = SILICONFLOW_API_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def call_ai_api(self, messages, model="moonshotai/Kimi-K2-Instruct-0905", max_tokens=1024, temperature=0.7):
        """调用SiliconFlow API"""
        try:
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            response = requests.post(self.api_url, headers=self.headers, json=payload, timeout=60)
            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "content": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                }
            else:
                return {"success": False, "error": f"API失败 {response.status_code}: {response.text}"}
        except Exception as e:
            return {"success": False, "error": f"API调用异常: {str(e)}"}

    def enhance_query_parsing(self, query_text, database_context=None):
        """解析用户问题 -> 执行数据库查询 -> 返回数值+自然语言解释"""
        print(f"开始解析查询: {query_text}")

        # AI识别查询类型
        system_prompt = """你是专业的销售数据分析助手。请根据用户问题识别他们想要查询的数据类型。
只返回一个JSON：
{"info": "销售额/销量/订单数/客户数/商品种类"}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户问题: {query_text}"}
        ]
        result = self.call_ai_api(messages)
        if not result["success"]:
            return result

        try:
            ai_response = result["content"].strip()
            if "```json" in ai_response:
                ai_response = ai_response.split("```json")[1].split("```")[0].strip()
            elif "```" in ai_response:
                ai_response = ai_response.split("```")[1].strip()
            parsed_result = json.loads(ai_response)
            info_type = parsed_result.get("info")
        except Exception as e:
            return {"success": False, "error": f"解析AI响应失败: {str(e)}"}

        if not info_type:
            return {"success": False, "error": "AI未识别查询类型"}

        # 数据库字段映射
        sql_map = {
            "销售额": "SELECT SUM(total_amount) AS value FROM orders WHERE status != 'cancelled'",
            "收入": "SELECT SUM(total_amount) AS value FROM orders WHERE status != 'cancelled'",
            "销量": """SELECT SUM(od.quantity) AS value 
                      FROM order_detail od 
                      LEFT JOIN orders o ON od.order_id = o.order_id 
                      WHERE o.status != 'cancelled'""",
            "订单数": "SELECT COUNT(*) AS value FROM orders WHERE status != 'cancelled'",
            "客户数": "SELECT COUNT(DISTINCT customer_id) AS value FROM orders WHERE status != 'cancelled'",
            "商品种类": "SELECT category_name AS value FROM category WHERE status = 1 LIMIT 10"
        }

        sql = sql_map.get(info_type)
        if not sql:
            return {"success": False, "error": f"不支持的查询类型: {info_type}"}

        # 查询数据库
        conn = get_db_connection()
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute(sql)
            row = cursor.fetchone()
            data_value = list(row.values())[0] if row else "暂无数据"
        finally:
            conn.close()

        # 调用解释接口
        explanation = self.generate_query_explanation(query_text, f"{info_type}: {data_value}")

        return {
            "success": True,
            "info": info_type,
            "data": data_value,
            "explanation": explanation.get("explanation") if explanation["success"] else None
        }

    def generate_query_explanation(self, query_text, query_result):
        """生成自然语言解释"""
        system_prompt = """你是专业的销售数据分析师。请基于用户问题和查询结果，生成简短的解释。
要求：
1. 数据总结：点明核心数据
2. 业务分析：解释含义
3. 专业建议：简短建议
字数在80~120字之间。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户查询: {query_text}\n查询结果: {query_result}\n请提供简短专业解释。"}
        ]
        result = self.call_ai_api(messages, max_tokens=256)
        if result["success"]:
            return {"success": True, "explanation": result["content"].strip()}
        else:
            return result


# ========== 工具函数 ==========
def get_database_context():
    """获取数据库上下文信息"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT category_id, category_name FROM category WHERE status = 1")
        categories = cursor.fetchall()
        cursor.execute("""
            SELECT DATE_FORMAT(create_time, '%Y-%m') as month,
                   COUNT(*) as order_count,
                   SUM(total_amount) as total_sales
            FROM orders 
            WHERE create_time >= DATE_SUB(NOW(), INTERVAL 6 MONTH) 
              AND status != 'cancelled'
            GROUP BY DATE_FORMAT(create_time, '%Y-%m')
            ORDER BY month DESC
        """)
        sales_overview = cursor.fetchall()
        return json.dumps({
            "categories": categories,
            "recent_sales": sales_overview,
            "available_metrics": ["销售额", "销量", "订单数", "客户数"],
            "time_periods": ["今天", "昨天", "最近7天", "本月", "今年"]
        }, ensure_ascii=False, indent=2, cls=DecimalEncoder)
    finally:
        conn.close()
    
    def generate_sales_prediction(self, historical_data, market_context):
        """使用AI生成销量预测"""
        print("开始AI销量预测...")
        
        # 获取数据库中的实际商品种类
        conn = get_db_connection()
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("SELECT category_name FROM category WHERE status = 1 LIMIT 10")
            categories = cursor.fetchall()
            category_names = [cat['category_name'] for cat in categories]
            print(f"数据库中的商品种类: {category_names}")
        except Exception as e:
            print(f"获取商品种类失败: {str(e)}")
            category_names = ["手机", "电脑", "电子产品"]
        finally:
            conn.close()
        
        # 基于实际商品种类生成预测
        system_prompt = f"""基于以下商品种类生成销量预测JSON：
{category_names}

返回格式：
{{
  "predictions": [
    {{"category_name": "具体种类名", "predicted_sales": 数字, "demand_level": "high/medium/low", "confidence": 0.8, "growth_rate": 数字}}
  ]
}}

只返回JSON，不要其他文字。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"基于历史数据为以下种类生成销量预测: {', '.join(category_names[:5])}"}
        ]
        
        result = self.call_ai_api(messages, max_tokens=2048)
        print(f"AI API调用结果: {result}")
        
        if result["success"]:
            try:
                ai_response = result["content"].strip()
                print(f"AI原始响应: {ai_response}")
                
                # 清理响应内容
                if "```json" in ai_response:
                    ai_response = ai_response.split("```json")[1].split("```")[0].strip()
                elif "```" in ai_response:
                    ai_response = ai_response.split("```")[1].strip()
                
                # 尝试解析JSON
                prediction_result = json.loads(ai_response)
                predictions = prediction_result.get("predictions", [])
                
                print(f"解析后的预测结果: {predictions}")
                
                return {
                    "success": True,
                    "predictions": predictions,
                    "ai_analysis": prediction_result
                }
            except json.JSONDecodeError as e:
                print(f"JSON解析失败: {str(e)}")
                return {
                    "success": False,
                    "error": f"AI预测结果格式错误: {str(e)}"
                }
        else:
            print(f"AI API调用失败: {result}")
            return result
    
    def generate_query_explanation(self, query_text, query_result):
        """生成查询结果的智能解释"""
        print(f"开始AI查询解释: {query_text}")
        
        # 精准的查询解释提示词
        system_prompt = """你是专业的销售数据分析师。请为用户提供精准、专业的查询结果解释。

【解释要求】
1. 数据解读：准确解读查询结果的数据含义
2. 业务洞察：提供有价值的业务分析
3. 趋势分析：如有历史对比，分析趋势变化
4. 专业建议：基于数据给出专业建议
5. 语言风格：专业、准确、简洁（80-120字）

【解释结构】
- 数据总结：核心数据指标
- 业务分析：数据背后的业务含义
- 专业建议：基于数据的建议或提醒

请提供精准、专业的解释，帮助用户理解数据价值。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户查询: {query_text}\n查询结果: {query_result}\n请提供专业的解释和分析。"}
        ]
        
        result = self.call_ai_api(messages, max_tokens=512)
        print(f"查询解释API结果: {result}")
        
        if result["success"]:
            return {
                "success": True,
                "explanation": result["content"]
            }
        else:
            print(f"查询解释API失败: {result}")
            return result

def get_database_context():
    """获取数据库上下文信息"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 获取商品种类信息
        cursor.execute("SELECT category_id, category_name FROM category WHERE status = 1")
        categories = cursor.fetchall()
        
        # 获取最近销售数据概览
        cursor.execute("""
            SELECT 
                DATE_FORMAT(create_time, '%Y-%m') as month,
                COUNT(*) as order_count,
                SUM(total_amount) as total_sales
            FROM orders 
            WHERE create_time >= DATE_SUB(NOW(), INTERVAL 6 MONTH) 
            AND status != 'cancelled'
            GROUP BY DATE_FORMAT(create_time, '%Y-%m')
            ORDER BY month DESC
        """)
        sales_overview = cursor.fetchall()
        
        context = {
            "categories": categories,
            "recent_sales": sales_overview,
            "available_metrics": ["销售额", "销量", "订单数", "客户数"],
            "time_periods": ["今天", "昨天", "最近7天", "本月", "今年"]
        }
        
        return json.dumps(context, ensure_ascii=False, indent=2, cls=DecimalEncoder)
        
    except Exception as e:
        return f"数据库上下文获取失败: {str(e)}"
    finally:
        conn.close()

def get_historical_sales_data():
    """获取历史销售数据用于预测"""
    print("开始获取历史销售数据...")
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 首先检查基本数据
        print("检查基本数据...")
        cursor.execute("SELECT COUNT(*) as total FROM orders WHERE status != 'cancelled'")
        total_orders = cursor.fetchone()['total']
        print(f"总有效订单数: {total_orders}")
        
        cursor.execute("SELECT COUNT(*) as total FROM order_detail")
        total_details = cursor.fetchone()['total']
        print(f"总订单详情数: {total_details}")
        
        cursor.execute("SELECT COUNT(*) as total FROM category WHERE status = 1")
        total_categories = cursor.fetchone()['total']
        print(f"总商品种类数: {total_categories}")
        
        # 检查最近6个月的数据
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM orders 
            WHERE create_time >= DATE_SUB(NOW(), INTERVAL 6 MONTH) 
            AND status != 'cancelled'
        """)
        recent_orders = cursor.fetchone()['count']
        print(f"最近6个月有效订单数: {recent_orders}")
        
        # 如果最近6个月没有数据，扩展到所有历史数据
        if recent_orders == 0:
            print("最近6个月无数据，使用所有历史数据...")
            cursor.execute("""
                SELECT 
                    c.category_id,
                    c.category_name,
                    DATE_FORMAT(o.create_time, '%Y-%m') as month,
                    SUM(od.quantity) as monthly_sales,
                    SUM(od.subtotal) as monthly_revenue,
                    COUNT(DISTINCT o.order_id) as order_count
                FROM order_detail od
                LEFT JOIN goods g ON od.goods_id = g.goods_id
                LEFT JOIN category c ON g.category_id = c.category_id
                LEFT JOIN orders o ON od.order_id = o.order_id
                WHERE o.status != 'cancelled'
                GROUP BY c.category_id, c.category_name, DATE_FORMAT(o.create_time, '%Y-%m')
                ORDER BY c.category_id, month
            """)
        else:
            print("使用最近6个月数据...")
            cursor.execute("""
                SELECT 
                    c.category_id,
                    c.category_name,
                    DATE_FORMAT(o.create_time, '%Y-%m') as month,
                    SUM(od.quantity) as monthly_sales,
                    SUM(od.subtotal) as monthly_revenue,
                    COUNT(DISTINCT o.order_id) as order_count
                FROM order_detail od
                LEFT JOIN goods g ON od.goods_id = g.goods_id
                LEFT JOIN category c ON g.category_id = c.category_id
                LEFT JOIN orders o ON od.order_id = o.order_id
                WHERE DATE(o.create_time) >= DATE_SUB(NOW(), INTERVAL 6 MONTH) 
                AND o.status != 'cancelled'
                GROUP BY c.category_id, c.category_name, DATE_FORMAT(o.create_time, '%Y-%m')
                ORDER BY c.category_id, month
            """)
        
        sales_data = cursor.fetchall()
        print(f"获取到销售数据记录数: {len(sales_data)}")
        if sales_data:
            print(f"销售数据示例: {sales_data[0]}")
        
        # 获取市场趋势信息
        if recent_orders == 0:
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(create_time, '%Y-%m') as month,
                    COUNT(*) as total_orders,
                    SUM(total_amount) as total_revenue,
                    AVG(total_amount) as avg_order_value
                FROM orders 
                WHERE status != 'cancelled'
                GROUP BY DATE_FORMAT(create_time, '%Y-%m')
                ORDER BY month
            """)
        else:
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(create_time, '%Y-%m') as month,
                    COUNT(*) as total_orders,
                    SUM(total_amount) as total_revenue,
                    AVG(total_amount) as avg_order_value
                FROM orders 
                WHERE create_time >= DATE_SUB(NOW(), INTERVAL 6 MONTH) 
                AND status != 'cancelled'
                GROUP BY DATE_FORMAT(create_time, '%Y-%m')
                ORDER BY month
            """)
        
        market_trends = cursor.fetchall()
        print(f"获取到市场趋势记录数: {len(market_trends)}")
        if market_trends:
            print(f"市场趋势示例: {market_trends[0]}")
        
        context = {
            "sales_data": sales_data,
            "market_trends": market_trends,
            "analysis_period": "6个月" if recent_orders > 0 else "全部历史",
            "current_date": datetime.now().strftime('%Y-%m-%d'),
            "data_summary": {
                "total_orders": total_orders,
                "total_details": total_details,
                "total_categories": total_categories,
                "recent_orders": recent_orders
            }
        }
        
        result = json.dumps(context, ensure_ascii=False, indent=2, cls=DecimalEncoder)
        print(f"历史数据获取成功，数据长度: {len(result)}")
        return result
        
    except Exception as e:
        error_msg = f"历史数据获取失败: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg
    finally:
        conn.close()

# 创建全局AI服务实例
ai_service = AIService()



