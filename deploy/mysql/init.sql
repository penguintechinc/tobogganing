-- Tobogganing MySQL Initialization Script

-- Create replication user for read replica
CREATE USER IF NOT EXISTS 'repl_user'@'%' IDENTIFIED BY 'repl_password';
GRANT REPLICATION SLAVE ON *.* TO 'repl_user'@'%';

-- Create application user with TLS support (optional)
-- These users are created via environment variables in docker-compose
-- but this shows the structure for manual setup

-- Grant additional privileges to main application user
GRANT ALL PRIVILEGES ON tobogganing.* TO 'tobogganing'@'%';

-- Create read-only user for read replicas
CREATE USER IF NOT EXISTS 'tobogganing_read'@'%' IDENTIFIED BY 'tobogganing-read-password';
GRANT SELECT ON tobogganing.* TO 'tobogganing_read'@'%';

-- Flush privileges
FLUSH PRIVILEGES;

-- Optional: Enable SSL/TLS for secure connections
-- Uncomment these lines if using TLS certificates
-- ALTER USER 'tobogganing'@'%' REQUIRE SSL;
-- ALTER USER 'tobogganing_read'@'%' REQUIRE SSL;

-- Set some useful defaults
SET GLOBAL max_connections = 100;
SET GLOBAL wait_timeout = 3600;
SET GLOBAL interactive_timeout = 3600;