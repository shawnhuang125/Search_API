# app/database_init.py
# 用來初始化資料庫的腳本
# 主要是運行服務,連線置資料庫若是空的會直接創立完整系統需要的table schema
import pymysql
import logging
from app.config import Config


def table_exists(cursor, table_name):
    """Check if table already exists"""
    cursor.execute("SHOW TABLES LIKE %s", (table_name,))
    return cursor.fetchone() is not None


def create_table(cursor, table_name, sql):
    """Create table if not exists, log the result"""
    if table_exists(cursor, table_name):
        logging.warning(f"Table `{table_name}` already exists. Skipped.")
        return False

    logging.info(f"Creating table `{table_name}` ...")
    cursor.execute(sql)
    logging.info(f"Table `{table_name}` created successfully.")
    return True


def init_database():
    """Initialize all database tables"""
    try:
        conn = pymysql.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            connect_timeout=5,
            autocommit=True,
        )

        logging.info("Connected to MySQL. Starting table creation...")
        cursor = conn.cursor()
        logging.info("Connected to MySQL successfully!")
        # =============================
        # Users
        # =============================
        create_table(cursor, "users", """
        CREATE TABLE `users` (
            id CHAR(36) PRIMARY KEY,
            email VARCHAR(150) NOT NULL UNIQUE,
            username VARCHAR(100),
            password VARCHAR(255) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # =============================
        # Workspaces
        # =============================
        create_table(cursor, "workspaces", """
        CREATE TABLE `workspaces` (
            id CHAR(36) PRIMARY KEY,
            owner_id CHAR(36) NOT NULL,
            name VARCHAR(255),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES `users`(id)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # =============================
        # Pages
        # =============================
        create_table(cursor, "pages", """
        CREATE TABLE `pages` (
            id CHAR(36) PRIMARY KEY,
            workspace_id CHAR(36) NOT NULL,
            parent_id CHAR(36),
            parent_type ENUM('page', 'workspace', 'database'),
            title VARCHAR(255),
            icon VARCHAR(255),
            cover VARCHAR(255),
            created_by CHAR(36),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES `workspaces`(id)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # =============================
        # Blocks
        # =============================
        create_table(cursor, "blocks", """
        CREATE TABLE `blocks` (
            id CHAR(36) PRIMARY KEY,
            page_id CHAR(36) NOT NULL,
            parent_block_id CHAR(36),
            type VARCHAR(50) NOT NULL,
            content JSON,
            sort_order INT DEFAULT 0,
            created_by CHAR(36),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES `pages`(id)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # =============================
        # Databases
        # =============================
        create_table(cursor, "databases", """
        CREATE TABLE `databases` (
            id CHAR(36) PRIMARY KEY,
            page_id CHAR(36) NOT NULL,
            title VARCHAR(255),
            description TEXT,
            created_by CHAR(36),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES `pages`(id)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # =============================
        # Database Properties
        # =============================
        create_table(cursor, "database_properties", """
        CREATE TABLE `database_properties` (
            id CHAR(36) PRIMARY KEY,
            database_id CHAR(36) NOT NULL,
            name VARCHAR(255) NOT NULL,
            type VARCHAR(50) NOT NULL,
            config JSON,
            sort_order INT DEFAULT 0,
            FOREIGN KEY (database_id) REFERENCES `databases`(id)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # =============================
        # Database Records
        # =============================
        create_table(cursor, "database_records", """
        CREATE TABLE `database_records` (
            id CHAR(36) PRIMARY KEY,
            database_id CHAR(36) NOT NULL,
            page_id CHAR(36) NOT NULL,
            created_by CHAR(36),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (database_id) REFERENCES `databases`(id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            FOREIGN KEY (page_id) REFERENCES `pages`(id)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # =============================
        # Database Property Values
        # =============================
        create_table(cursor, "database_property_values", """
        CREATE TABLE `database_property_values` (
            id CHAR(36) PRIMARY KEY,
            record_id CHAR(36) NOT NULL,
            property_id CHAR(36) NOT NULL,
            value JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (record_id) REFERENCES `database_records`(id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            FOREIGN KEY (property_id) REFERENCES `database_properties`(id)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # =============================
        # Database Views
        # =============================
        create_table(cursor, "database_views", """
        CREATE TABLE `database_views` (
            id CHAR(36) PRIMARY PRIMARY KEY,
            database_id CHAR(36) NOT NULL,
            type ENUM('table','board','list','gallery','calendar') NOT NULL,
            name VARCHAR(255),
            created_by CHAR(36),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (database_id) REFERENCES `databases`(id)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # =============================
        # View Config
        # =============================
        create_table(cursor, "database_view_config", """
        CREATE TABLE `database_view_config` (
            id CHAR(36) PRIMARY KEY,
            view_id CHAR(36) NOT NULL,
            config JSON NOT NULL,
            FOREIGN KEY (view_id) REFERENCES `database_views`(id)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        conn.close()
        logging.info("Database initialization completed successfully.")
        return True

    except Exception as e:
        logging.error(f"Database initialization failed: {e}")
        return False
