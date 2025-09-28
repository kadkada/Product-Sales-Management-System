#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商品销售管理系统启动脚本
"""

import os
import sys
from app import app

def main():
    """主函数"""
    print("=" * 50)
    print("商品销售管理系统")
    print("=" * 50)
    print("正在启动系统...")
    print("访问地址: http://localhost:5000")
    print("默认管理员账号: admin / admin123")
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n系统已停止")
    except Exception as e:
        print(f"启动失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
