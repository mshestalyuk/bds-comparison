#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_CMD="docker compose -f ${SCRIPT_DIR}/docker-compose.yml"

# --- Colors ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

usage() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  Database Stack Manager${NC}"
    echo -e "${CYAN}  bds-comparison${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    echo -e "Usage: ${GREEN}$0${NC} <command>"
    echo ""
    echo "Lifecycle:"
    echo -e "  ${GREEN}start${NC}        Start all database containers"
    echo -e "  ${GREEN}stop${NC}         Stop all database containers"
    echo -e "  ${GREEN}restart${NC}      Restart all database containers"
    echo -e "  ${GREEN}status${NC}       Show container status"
    echo -e "  ${GREEN}logs${NC}         Tail logs from all containers"
    echo ""
    echo "Data:"
    echo -e "  ${GREEN}load${NC}         Load sample data into all databases"
    echo ""
    echo "Shell access:"
    echo -e "  ${GREEN}shell${NC}        Interactive menu to pick a DB shell"
    echo -e "  ${GREEN}mongo${NC}        Open MongoDB shell (mongosh)"
    echo -e "  ${GREEN}psql${NC}         Open PostgreSQL shell (psql)"
    echo -e "  ${GREEN}mysql${NC}        Open MySQL shell (mysql)"
    echo -e "  ${GREEN}redis${NC}        Open Redis shell (redis-cli)"
    echo ""
    echo "Danger zone:"
    echo -e "  ${RED}destroy${NC}      Stop containers and remove volumes (DATA LOSS!)"
    echo ""
}

# -----------------------------------------------
# Lifecycle
# -----------------------------------------------

start_stack() {
    echo -e "${GREEN}>>> Starting database stack...${NC}"
    $COMPOSE_CMD up -d
    echo -e "${GREEN}>>> All containers are up.${NC}"
    $COMPOSE_CMD ps
}

stop_stack() {
    echo -e "${YELLOW}>>> Stopping database stack...${NC}"
    $COMPOSE_CMD down
    echo -e "${YELLOW}>>> All containers stopped.${NC}"
}

restart_stack() {
    echo -e "${YELLOW}>>> Restarting database stack...${NC}"
    $COMPOSE_CMD down
    $COMPOSE_CMD up -d
    echo -e "${GREEN}>>> All containers restarted.${NC}"
    $COMPOSE_CMD ps
}

show_status() {
    echo -e "${CYAN}>>> Container status:${NC}"
    $COMPOSE_CMD ps
}

show_logs() {
    $COMPOSE_CMD logs -f --tail=50
}

# -----------------------------------------------
# Load data
# -----------------------------------------------

wait_for_container() {
    local container="$1"
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if docker exec "$container" echo "ready" &>/dev/null; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done

    echo -e "${RED}>>> Timeout waiting for ${container}${NC}"
    return 1
}

load_data() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  Loading sample data${NC}"
    echo -e "${CYAN}  System Ewidencji Personelu${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""

    # Check that containers are running
    if ! docker ps --format '{{.Names}}' | grep -q "mongodb"; then
        echo -e "${RED}>>> Containers are not running. Run '$0 start' first.${NC}"
        exit 1
    fi

    echo -e "${CYAN}>>> Waiting for databases to be ready...${NC}"
    wait_for_container "mongodb"
    wait_for_container "postgresql"
    wait_for_container "mysql"
    wait_for_container "redis"
    sleep 3

    # --- MongoDB ---
    echo -e "${GREEN}[1/4] MongoDB...${NC}"
    docker cp "${SCRIPT_DIR}/mongo-init.js" mongodb:/tmp/mongo-init.js
    docker exec mongodb mongosh \
        --username admin \
        --password mongo_secret_123 \
        --authenticationDatabase admin \
        /tmp/mongo-init.js
    echo ""

    # --- PostgreSQL ---
    echo -e "${GREEN}[2/4] PostgreSQL...${NC}"
    docker cp "${SCRIPT_DIR}/postgres-init.sql" postgresql:/tmp/postgres-init.sql
    docker exec postgresql psql \
        -U admin \
        -d appdb \
        -f /tmp/postgres-init.sql
    echo ""

    # --- MySQL ---
    echo -e "${GREEN}[3/4] MySQL...${NC}"
    docker cp "${SCRIPT_DIR}/mysql-init.sql" mysql:/tmp/mysql-init.sql
    docker exec mysql bash -c "mysql -u admin -pmysql_secret_123 appdb < /tmp/mysql-init.sql"
    echo ""

    # --- Redis ---
    echo -e "${GREEN}[4/4] Redis...${NC}"
    bash "${SCRIPT_DIR}/redis-init.sh"
    echo ""

    echo -e "${CYAN}========================================${NC}"
    echo -e "${GREEN}  All databases initialized!${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    echo "Verify:"
    echo "  $0 mongo   →  db.employees.find().pretty()"
    echo "  $0 psql    →  SELECT * FROM v_employee_overview;"
    echo "  $0 mysql   →  SELECT * FROM v_employee_overview;"
    echo "  $0 redis   →  ZREVRANGE salary:ranking 0 -1 WITHSCORES"
}

# -----------------------------------------------
# Shell access
# -----------------------------------------------

shell_mongo() {
    echo -e "${GREEN}>>> Connecting to MongoDB shell...${NC}"
    docker exec -it mongodb mongosh \
        --username admin \
        --password mongo_secret_123 \
        --authenticationDatabase admin \
        appdb
}

shell_psql() {
    echo -e "${GREEN}>>> Connecting to PostgreSQL shell...${NC}"
    docker exec -it postgresql psql \
        -U admin \
        -d appdb
}

shell_mysql() {
    echo -e "${GREEN}>>> Connecting to MySQL shell...${NC}"
    docker exec -it mysql mysql \
        -u admin \
        -pmysql_secret_123 \
        appdb
}

shell_redis() {
    echo -e "${GREEN}>>> Connecting to Redis shell...${NC}"
    docker exec -it redis redis-cli \
        -a redis_secret_123
}

shell_menu() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  Select a database shell${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    echo "  1) MongoDB    (mongosh)"
    echo "  2) PostgreSQL (psql)"
    echo "  3) MySQL      (mysql)"
    echo "  4) Redis      (redis-cli)"
    echo ""
    read -rp "Enter choice [1-4]: " choice

    case "$choice" in
        1) shell_mongo ;;
        2) shell_psql ;;
        3) shell_mysql ;;
        4) shell_redis ;;
        *) echo -e "${RED}Invalid choice.${NC}"; exit 1 ;;
    esac
}

# -----------------------------------------------
# Danger zone
# -----------------------------------------------

destroy_stack() {
    echo -e "${RED}!!! WARNING: This will stop all containers AND delete all data volumes !!!${NC}"
    read -rp "Are you sure? (yes/no): " confirm
    if [[ "$confirm" == "yes" ]]; then
        $COMPOSE_CMD down -v
        echo -e "${RED}>>> Stack destroyed. All data volumes removed.${NC}"
    else
        echo -e "${YELLOW}>>> Aborted.${NC}"
    fi
}

# -----------------------------------------------
# Main
# -----------------------------------------------

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

case "$1" in
    start)   start_stack ;;
    stop)    stop_stack ;;
    restart) restart_stack ;;
    status)  show_status ;;
    logs)    show_logs ;;
    load)    load_data ;;
    shell)   shell_menu ;;
    mongo)   shell_mongo ;;
    psql)    shell_psql ;;
    mysql)   shell_mysql ;;
    redis)   shell_redis ;;
    destroy) destroy_stack ;;
    *)       usage; exit 1 ;;
esac