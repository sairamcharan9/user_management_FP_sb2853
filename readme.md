# User Management System with Profile Pictures

## Student Information
- **Name**: Sai Ram Charan BANDARUPALLI
- **Project**: User Management FastAPI Application

## Project Overview
This project is a comprehensive user management system built with FastAPI that provides secure user authentication, profile management, and profile picture upload functionality using MinIO object storage. The application allows users to register, login, update their profiles, and upload profile pictures.

## Key Features
- **User Authentication**: Secure login and registration with JWT token-based authentication
- **Email Verification**: Verification email system for new account creation
- **Profile Management**: Users can view and update their profile information
- **Profile Picture Upload**: Integration with MinIO for storing and serving user profile pictures
- **Role-Based Access Control**: Different permission levels for regular users, managers, and admins
- **API Documentation**: Auto-generated Swagger documentation at `/docs` endpoint

## Technologies Used
- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Object Storage**: MinIO for profile picture storage
- **Authentication**: JWT tokens
- **Email Service**: SMTP integration for verification emails
- **Containerization**: Docker and Docker Compose
- **Testing**: pytest with Mocking and Coverage

## Setup and Running the Project

### Prerequisites
- Docker and Docker Compose installed
- Git for version control

### Installation Steps
1. Clone the repository:
   ```bash
   git clone https://github.com/sairamcharan9/user_management_FP_sb2853.git
   cd user_management_FP_sb2853
   ```

2. Create or update the `.env` file with appropriate values. A sample configuration:
   ```
   # Database configuration
   database_url=postgresql+asyncpg://user:password@postgres:5432/myappdb
   postgres_user=user
   postgres_password=password
   postgres_server=postgres
   postgres_port=5432
   postgres_db=myappdb

   # Security settings
   secret_key=use_a_strong_random_string_here
   jwt_secret_key=use_a_strong_random_string_here
   algorithm=HS256
   access_token_expire_minutes=30
   max_login_attempts=5
   debug=True

   # Email settings
   smtp_server=sandbox.smtp.mailtrap.io
   smtp_port=2525
   smtp_username=your_username
   smtp_password=your_password
   send_real_mail=True

   # Server configuration
   server_base_url=http://localhost

   # MinIO configuration
   minio_endpoint=localhost:9000
   minio_access_key=minioadmin
   minio_secret_key=minioadmin
   minio_secure=False
   minio_bucket=profiles
   minio_region=
   ```

3. Start the application using Docker Compose:
   ```bash
   docker-compose up -d
   ```

4. Access the application:
   - API documentation: http://localhost/docs
   - MinIO Console: http://localhost:9001 (login with minioadmin/minioadmin)
   - PgAdmin: http://localhost:5050 (if configured)

### Running Tests
To run tests in the Docker container:
```bash
docker compose exec fastapi pytest
```

For test coverage reporting:
```bash
docker compose exec fastapi pytest --cov
```

## Common Issues and Solutions

### Profile Picture Upload Issues
- Ensure the MinIO container is running
- Verify the MinIO endpoint is correctly set to `localhost:9000` in the `.env` file
- Check that the `minio_bucket` setting matches the `minio_bucket_name` expected in the settings

### Database Connection Issues
- Ensure the PostgreSQL container is running and healthy
- Verify the database credentials match in both the `.env` file and container configuration

### Email Verification Not Working
- Check the SMTP settings in the `.env` file
- Ensure `send_real_mail` is set to `True`

### Database Issues After Running Tests
If you encounter database issues after running pytest or if Docker fails:

1. Connect to the PostgreSQL database using pgAdmin or the psql command line:
   ```bash
   docker exec -it user_management_fp_sb2853-postgres-1 psql -U user myappdb
   ```

2. Drop all tables manually if necessary:
   ```sql
   DROP SCHEMA public CASCADE;
   CREATE SCHEMA public;
   GRANT ALL ON SCHEMA public TO user;
   GRANT ALL ON SCHEMA public TO public;
   ```

3. Run Alembic migrations to recreate all tables:
   ```bash
   docker exec -it user_management_fp_sb2853-fastapi-1 alembic upgrade head
   ```

This will reset your database to a clean state with the correct schema.

## API Endpoints

### Authentication
- `POST /register`: Register a new user
- `POST /login`: Authenticate and get JWT tokens
- `GET /auth/verify-email`: Verify email with token

### Users
- `GET /users/me`: Get current user profile
- `PUT /users/me`: Update current user profile
- `GET /users/{user_id}`: Get user by ID (admin only)

### Profile Pictures
- `POST /users/{user_id}/profile-picture`: Upload profile picture

## Development Features

- **Comprehensive Testing**: Unit and integration tests with pytest
- **CI/CD Pipeline**: GitHub Actions for automatic testing
- **Containerized Development**: Docker setup for consistent environments
- **API Documentation**: Auto-generated with Swagger UI
