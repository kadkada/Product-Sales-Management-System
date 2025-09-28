from flask import request, jsonify, session
import pymysql
import re
from app import get_db_connection, login_required, admin_required

def submit_message():
    """提交留言"""
    data = request.get_json()
    customer_name = data.get('customer_name', '').strip()
    contact_info = data.get('contact_info', '').strip()
    content = data.get('content', '').strip()
    
    if not customer_name or not contact_info or not content:
        return jsonify({"code": 0, "msg": "姓名、联系方式和留言内容不能为空"})
    
    # 简单的内容过滤，防止SQL注入
    if not is_valid_content(content):
        return jsonify({"code": 0, "msg": "留言内容包含非法字符"})
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO message (customer_name, contact_info, content) VALUES (%s, %s, %s)",
            (customer_name, contact_info, content)
        )
        conn.commit()
        
        return jsonify({"code": 1, "msg": "留言提交成功，我们会尽快回复"})
    except Exception as e:
        conn.rollback()
        return jsonify({"code": 0, "msg": f"提交失败：{str(e)}"})
    finally:
        conn.close()

def get_message_list():
    """获取留言列表（管理员）"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    status = request.args.get('status', '')  # unread, replied
    keyword = request.args.get('keyword', '')
    
    offset = (page - 1) * page_size
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 构建查询条件
        where_clause = "WHERE 1=1"
        params = []
        
        if status:
            where_clause += " AND status = %s"
            params.append(status)
        
        if keyword:
            where_clause += " AND (customer_name LIKE %s OR content LIKE %s)"
            params.extend([f'%{keyword}%', f'%{keyword}%'])
        
        # 查询总数
        cursor.execute(f"SELECT COUNT(*) as total FROM message {where_clause}", params)
        total = cursor.fetchone()['total']
        
        # 查询数据
        cursor.execute(
            f"SELECT m.*, u.real_name as reply_user_name FROM message m LEFT JOIN user u ON m.reply_user_id = u.user_id {where_clause} ORDER BY m.create_time DESC LIMIT %s OFFSET %s",
            params + [page_size, offset]
        )
        messages = cursor.fetchall()
        
        return jsonify({
            "code": 1,
            "msg": "获取成功",
            "data": {
                "list": messages,
                "total": total,
                "page": page,
                "page_size": page_size
            }
        })
    except Exception as e:
        return jsonify({"code": 0, "msg": f"获取失败：{str(e)}"})
    finally:
        conn.close()

def reply_message():
    """回复留言（管理员）"""
    data = request.get_json()
    message_id = data.get('message_id')
    reply_content = data.get('reply_content', '').strip()
    
    if not message_id or not reply_content:
        return jsonify({"code": 0, "msg": "留言ID和回复内容不能为空"})
    
    # 简单的内容过滤
    if not is_valid_content(reply_content):
        return jsonify({"code": 0, "msg": "回复内容包含非法字符"})
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 检查留言是否存在
        cursor.execute("SELECT message_id FROM message WHERE message_id = %s", (message_id,))
        if not cursor.fetchone():
            return jsonify({"code": 0, "msg": "留言不存在"})
        
        # 更新留言状态和回复内容
        cursor.execute(
            "UPDATE message SET status = 'replied', reply_content = %s, reply_time = NOW(), reply_user_id = %s WHERE message_id = %s",
            (reply_content, session.get('user_id'), message_id)
        )
        conn.commit()
        
        return jsonify({"code": 1, "msg": "回复成功"})
    except Exception as e:
        conn.rollback()
        return jsonify({"code": 0, "msg": f"回复失败：{str(e)}"})
    finally:
        conn.close()

def delete_message():
    """删除留言（管理员）"""
    data = request.get_json()
    message_id = data.get('message_id')
    
    if not message_id:
        return jsonify({"code": 0, "msg": "留言ID不能为空"})
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 检查留言是否存在
        cursor.execute("SELECT message_id FROM message WHERE message_id = %s", (message_id,))
        if not cursor.fetchone():
            return jsonify({"code": 0, "msg": "留言不存在"})
        
        # 删除留言
        cursor.execute("DELETE FROM message WHERE message_id = %s", (message_id,))
        conn.commit()
        
        return jsonify({"code": 1, "msg": "删除成功"})
    except Exception as e:
        conn.rollback()
        return jsonify({"code": 0, "msg": f"删除失败：{str(e)}"})
    finally:
        conn.close()

def get_message_stats():
    """获取留言统计（管理员）"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 统计未回复留言数量
        cursor.execute("SELECT COUNT(*) as unread_count FROM message WHERE status = 'unread'")
        unread_count = cursor.fetchone()['unread_count']
        
        # 统计总留言数量
        cursor.execute("SELECT COUNT(*) as total_count FROM message")
        total_count = cursor.fetchone()['total_count']
        
        # 统计今日新增留言数量
        cursor.execute("SELECT COUNT(*) as today_count FROM message WHERE DATE(create_time) = CURDATE()")
        today_count = cursor.fetchone()['today_count']
        
        return jsonify({
            "code": 1,
            "msg": "获取成功",
            "data": {
                "unread_count": unread_count,
                "total_count": total_count,
                "today_count": today_count
            }
        })
    except Exception as e:
        return jsonify({"code": 0, "msg": f"获取失败：{str(e)}"})
    finally:
        conn.close()

def is_valid_content(content):
    """检查内容是否合法"""
    # 禁止的特殊字符和SQL注入关键词
    forbidden_patterns = [
        r'<script.*?>.*?</script>',  # 脚本标签
        r'javascript:',  # JavaScript协议
        r'on\w+\s*=',  # 事件处理器
        r'union\s+select',  # SQL注入
        r'drop\s+table',  # SQL注入
        r'delete\s+from',  # SQL注入
        r'insert\s+into',  # SQL注入
        r'update\s+set',  # SQL注入
    ]
    
    for pattern in forbidden_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return False
    
    return True
