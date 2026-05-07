.PHONY: up down logs ps init-rds

# Start local Airflow stack
up:
	docker compose up -d

# Stop and remove containers (volumes are preserved)
down:
	docker compose down

# Tail webserver logs
logs:
	docker compose logs -f airflow-webserver airflow-scheduler

# Show running containers
ps:
	docker compose ps

# Run rds_init.sql against your RDS instance.
init-rds:
	@echo "Running rds_init.sql against RDS..."
	PGPASSWORD=$(RDS_PASS) psql \
		-h $(RDS_HOST) \
		-U datapulse_admin \
		-d datapulse \
		-f infra/rds_init.sql
	@echo "Done."
