-- 商品销售管理系统数据库结构
-- 创建数据库
CREATE DATABASE IF NOT EXISTS product_sales_system DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE product_sales_system;

-- 用户表
CREATE TABLE user (
    user_id INT(11) PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID，主键自增',
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名，不可重复',
    password VARCHAR(100) NOT NULL COMMENT '密码，MD5加密存储',
    role VARCHAR(20) NOT NULL DEFAULT 'normal' COMMENT '角色：admin（管理员）/normal（普通用户）',
    real_name VARCHAR(50) COMMENT '真实姓名',
    phone VARCHAR(20) COMMENT '联系电话',
    email VARCHAR(100) COMMENT '邮箱',
    status TINYINT(1) DEFAULT 1 COMMENT '状态：1-启用，0-禁用',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息表';

-- 商品种类表
CREATE TABLE category (
    category_id INT(11) PRIMARY KEY AUTO_INCREMENT COMMENT '种类ID，主键自增',
    category_name VARCHAR(100) NOT NULL COMMENT '种类名称',
    description TEXT COMMENT '种类描述',
    parent_id INT(11) DEFAULT 0 COMMENT '父级种类ID，0表示顶级种类',
    sort_order INT(11) DEFAULT 0 COMMENT '排序',
    status TINYINT(1) DEFAULT 1 COMMENT '状态：1-启用，0-禁用',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_parent_id (parent_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品种类表';

-- 商品表
CREATE TABLE goods (
    goods_id INT(11) PRIMARY KEY AUTO_INCREMENT COMMENT '商品ID，主键自增',
    goods_name VARCHAR(200) NOT NULL COMMENT '商品名称',
    category_id INT(11) NOT NULL COMMENT '商品种类ID',
    price DECIMAL(10,2) NOT NULL COMMENT '商品价格',
    stock INT(11) DEFAULT 0 COMMENT '库存数量',
    description TEXT COMMENT '商品描述',
    image_url VARCHAR(500) COMMENT '商品图片URL',
    status TINYINT(1) DEFAULT 1 COMMENT '状态：1-上架，0-下架',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (category_id) REFERENCES category(category_id) ON DELETE RESTRICT,
    INDEX idx_category_id (category_id),
    INDEX idx_status (status),
    INDEX idx_price (price)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品信息表';

-- 订单表
CREATE TABLE orders (
    order_id VARCHAR(50) PRIMARY KEY COMMENT '订单号，主键',
    user_id INT(11) NOT NULL COMMENT '下单用户ID',
    total_amount DECIMAL(10,2) NOT NULL COMMENT '订单总金额',
    status VARCHAR(20) DEFAULT 'pending' COMMENT '订单状态：pending-待发货，shipped-已发货，completed-已完成，cancelled-已取消',
    shipping_address TEXT COMMENT '收货地址',
    contact_phone VARCHAR(20) COMMENT '联系电话',
    remark TEXT COMMENT '订单备注',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE RESTRICT,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表';

-- 订单详情表
CREATE TABLE order_detail (
    detail_id INT(11) PRIMARY KEY AUTO_INCREMENT COMMENT '详情ID，主键自增',
    order_id VARCHAR(50) NOT NULL COMMENT '订单号',
    goods_id INT(11) NOT NULL COMMENT '商品ID',
    goods_name VARCHAR(200) NOT NULL COMMENT '商品名称（冗余字段）',
    price DECIMAL(10,2) NOT NULL COMMENT '商品单价',
    quantity INT(11) NOT NULL COMMENT '购买数量',
    subtotal DECIMAL(10,2) NOT NULL COMMENT '小计金额',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    FOREIGN KEY (goods_id) REFERENCES goods(goods_id) ON DELETE RESTRICT,
    INDEX idx_order_id (order_id),
    INDEX idx_goods_id (goods_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单详情表';

-- 留言表
CREATE TABLE message (
    message_id INT(11) PRIMARY KEY AUTO_INCREMENT COMMENT '留言ID，主键自增',
    customer_name VARCHAR(50) NOT NULL COMMENT '客户姓名',
    contact_info VARCHAR(100) NOT NULL COMMENT '联系方式',
    content TEXT NOT NULL COMMENT '留言内容',
    status VARCHAR(20) DEFAULT 'unread' COMMENT '状态：unread-未回复，replied-已回复',
    reply_content TEXT COMMENT '回复内容',
    reply_time DATETIME COMMENT '回复时间',
    reply_user_id INT(11) COMMENT '回复人ID',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (reply_user_id) REFERENCES user(user_id) ON DELETE SET NULL,
    INDEX idx_status (status),
    INDEX idx_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='留言表';

-- 智能问数记录表
CREATE TABLE query_log (
    log_id INT(11) PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID，主键自增',
    user_id INT(11) NOT NULL COMMENT '查询用户ID',
    query_text TEXT NOT NULL COMMENT '查询问题',
    query_result TEXT COMMENT '查询结果',
    query_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '查询时间',
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_query_time (query_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能问数记录表';

-- 销量预测结果表
CREATE TABLE sales_prediction (
    prediction_id INT(11) PRIMARY KEY AUTO_INCREMENT COMMENT '预测ID，主键自增',
    category_id INT(11) NOT NULL COMMENT '商品种类ID',
    category_name VARCHAR(100) NOT NULL COMMENT '种类名称',
    predicted_sales INT(11) NOT NULL COMMENT '预测销量',
    demand_level VARCHAR(10) NOT NULL COMMENT '需求等级：high-高，medium-中，low-低',
    accuracy_rate DECIMAL(5,2) COMMENT '预测准确率',
    prediction_date DATE NOT NULL COMMENT '预测日期',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (category_id) REFERENCES category(category_id) ON DELETE CASCADE,
    UNIQUE KEY uk_category_date (category_id, prediction_date),
    INDEX idx_category_id (category_id),
    INDEX idx_prediction_date (prediction_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='销量预测结果表';