# 🐟 Aquaculture Management System - Backend

A comprehensive IoT-based aquaculture monitoring and management system designed for fish farms in Algeria. This FastAPI-powered backend provides real-time water quality monitoring, anomaly detection, automated alerting, and comprehensive analytics for optimizing aquaculture operations.

## 🌟 Features

### 🔍 Real-time Monitoring
- **Multi-sensor Support**: Temperature, pH, dissolved oxygen, turbidity, and ammonia monitoring
- **Live Data Processing**: Real-time sensor data ingestion and validation
- **Data Quality Assurance**: Automated data cleaning and outlier detection
- **Historical Analytics**: Comprehensive trend analysis and reporting

### 🚨 Intelligent Alerting System
- **Page-Hinkley Change Detection**: Advanced anomaly detection using statistical change point detection
- **Multi-level Alerts**: Critical, warning, and informational alert classifications
- **Smart Notifications**: Email alerts with multilingual support (Arabic, French, English)
- **Alert Management**: Configurable thresholds and notification preferences

### 📊 Analytics & Insights
- **Health Score Calculation**: Automated pond health assessment based on multiple parameters
- **Trend Analysis**: Historical data visualization and pattern recognition
- **Performance Metrics**: KPI tracking and optimization recommendations
- **Data Aggregation**: Hourly and daily data summaries for efficient querying

### 🏢 Multi-tenancy & Security
- **Organization Management**: Multi-tenant architecture with role-based access
- **JWT Authentication**: Secure API access with token-based authentication
- **User Roles**: Admin, manager, and operator permission levels
- **Data Isolation**: Secure data separation between organizations

### 🌐 API & Integration
- **RESTful API**: Comprehensive REST endpoints for all operations
- **OpenAPI Documentation**: Auto-generated API documentation with Swagger UI
- **Data Export**: CSV and JSON export capabilities
- **IoT Integration**: MQTT and HTTP endpoints for sensor data ingestion

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   IoT Sensors   │───▶│   FastAPI App   │───▶│   PostgreSQL    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                               │
                               ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │  Alert Engine   │───▶│   Email Service │
                       └─────────────────┘    └─────────────────┘
                               │
                               ▼
                       ┌─────────────────┐
                       │     Redis       │
                       │   (Caching)     │
                       └─────────────────┘
```

### Technology Stack
- **Backend Framework**: FastAPI with Python 3.11+
- **Database**: PostgreSQL 15 with SQLAlchemy ORM
- **Caching**: Redis for session management and caching
- **Task Scheduling**: APScheduler for background jobs
- **Authentication**: JWT with bcrypt password hashing
- **Deployment**: Docker with docker-compose orchestration
- **Monitoring**: Built-in health checks and logging

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for local development)
- PostgreSQL 15+ (if running without Docker)

### 1. Clone and Setup
```bash
git clone <repository-url>
cd aquaculture-backend
cp .env.example .env
```

### 2. Configure Environment
Edit `.env` file with your settings:
```bash
# Database Configuration
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/aquaculture
DATABASE_PASSWORD=your_secure_password

# Security
SECRET_KEY=your-super-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key

# Email Configuration (for alerts)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Application Settings
ENVIRONMENT=production
DEBUG=false
ANOMALY_DETECTION_THRESHOLD=0.1
```

### 3. Start with Docker (Recommended)
```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Run database migrations
docker-compose exec api alembic upgrade head
```

### 4. Access the Application
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **API Base URL**: http://localhost:8000/api/v1

## 🛠️ Development Setup

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set up pre-commit hooks
pip install pre-commit
pre-commit install

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_sensors.py -v
```

## 📡 API Usage

### Authentication
```bash
# Login to get access token
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=your_password"

# Use token in subsequent requests
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/ponds/"
```

### Sensor Data Submission
```bash
# Submit sensor readings
curl -X POST "http://localhost:8000/api/v1/sensors/data" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pond_id": 1,
    "sensor_type": "temperature",
    "value": 25.5,
    "unit": "celsius",
    "timestamp": "2024-01-15T10:30:00Z"
  }'
```

### Pond Management
```bash
# Create new pond
curl -X POST "http://localhost:8000/api/v1/ponds/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Pond Alpha",
    "location": "Farm Section A",
    "capacity": 5000,
    "species": "Tilapia"
  }'

# Get pond health status
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/ponds/1/health"
```

## 🔍 Anomaly Detection

The system uses the **Page-Hinkley algorithm** for real-time change point detection:

### How it Works
1. **Continuous Monitoring**: Each sensor reading is processed through the Page-Hinkley detector
2. **Statistical Analysis**: Detects significant changes in data distribution
3. **Threshold-based Alerts**: Configurable sensitivity for different sensor types
4. **Contextual Awareness**: Considers historical patterns and seasonal variations

### Configuration
```python
# In your .env file
ANOMALY_DETECTION_THRESHOLD=0.1  # Lower = more sensitive
PAGE_HINKLEY_DELTA=0.01          # Detection sensitivity
PAGE_HINKLEY_LAMBDA=50           # Forgetting factor
```

### Alert Types
- **Critical**: Immediate action required (e.g., oxygen depletion)
- **Warning**: Attention needed (e.g., temperature drift)
- **Info**: Informational updates (e.g., feeding reminders)

## 📧 Email Notifications

### Multilingual Support
The system supports alerts in multiple languages:
- **Arabic**: للتنبيهات الحرجة
- **French**: Pour les alertes critiques
- **English**: For critical alerts

### Email Templates
- **Critical Alerts**: Immediate notification with action items
- **Daily Summaries**: Comprehensive daily reports
- **System Status**: Health checks and maintenance notifications

### Configuration
```bash
# SMTP Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your-email@domain.com
SMTP_PASSWORD=your-app-password

# Alert Settings
ALERT_EMAIL_FROM=alerts@yourfarm.com
ALERT_EMAIL_REPLY_TO=support@yourfarm.com
```

## 🐳 Deployment

### Production Deployment
```bash
# Clone repository on server
git clone <repository-url>
cd aquaculture-backend

# Configure production environment
cp .env.example .env
# Edit .env with production values

# Deploy with Docker Compose
docker-compose -f docker-compose.prod.yml up -d

# Set up SSL with Let's Encrypt (optional)
docker-compose exec nginx certbot --nginx -d yourdomain.com
```

### Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `SECRET_KEY` | Application secret key | Required |
| `SMTP_SERVER` | Email server hostname | localhost |
| `SMTP_PORT` | Email server port | 587 |
| `ANOMALY_DETECTION_THRESHOLD` | Sensitivity for anomaly detection | 0.1 |
| `DATA_RETENTION_DAYS` | Days to keep raw sensor data | 90 |

### Health Monitoring
```bash
# Check application health
curl http://localhost:8000/health

# Monitor logs
docker-compose logs -f api

# Database health
docker-compose exec postgres pg_isready
```

## 🔧 Maintenance

### Data Management
```bash
# Backup database
docker-compose exec postgres pg_dump -U postgres aquaculture > backup.sql

# Restore database
docker-compose exec postgres psql -U postgres aquaculture < backup.sql

# Clean old data (automated via cron)
docker-compose exec api python -m app.tasks.data_aggregation cleanup_old_data
```

### Performance Optimization
- **Database Indexing**: Automatic indexing on frequently queried columns
- **Query Optimization**: Efficient SQL queries with proper joins
- **Caching**: Redis caching for frequently accessed data
- **Connection Pooling**: SQLAlchemy connection pooling for database efficiency

## 🛡️ Security

### Best Practices
- **JWT Tokens**: Secure authentication with expirable tokens
- **Password Hashing**: bcrypt for secure password storage
- **CORS Configuration**: Proper cross-origin request handling
- **Input Validation**: Pydantic models for request validation
- **SQL Injection Protection**: SQLAlchemy ORM prevents SQL injection

### Security Headers
```python
# Automatically configured security headers
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
```

## 📝 API Documentation

### Interactive Documentation
- **Swagger UI**: Available at `/docs`
- **ReDoc**: Available at `/redoc`
- **OpenAPI Schema**: Available at `/openapi.json`

### Main Endpoints
- `POST /api/v1/auth/login` - User authentication
- `GET /api/v1/ponds/` - List all ponds
- `POST /api/v1/sensors/data` - Submit sensor readings
- `GET /api/v1/alerts/` - Retrieve alerts
- `GET /api/v1/analytics/health/{pond_id}` - Pond health metrics

## 🤝 Contributing

### Development Workflow
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Run the test suite: `pytest`
5. Commit your changes: `git commit -m 'Add amazing feature'`
6. Push to your fork: `git push origin feature/amazing-feature`
7. Create a Pull Request

### Code Standards
- **Black**: Code formatting with `black app/`
- **Flake8**: Linting with `flake8 app/`
- **Type Hints**: Full type annotation coverage
- **Docstrings**: Comprehensive documentation for all functions

## 📊 Monitoring & Analytics

### Built-in Metrics
- **System Health**: API response times, database connections
- **Data Quality**: Sensor reading validation and completeness
- **Alert Performance**: Alert response times and accuracy
- **User Activity**: API usage patterns and authentication metrics

### Integration Options
- **Prometheus**: Metrics collection and monitoring
- **Grafana**: Visualization and dashboarding
- **ELK Stack**: Log aggregation and analysis

## 🐛 Troubleshooting

### Common Issues

#### Database Connection Issues
```bash
# Check database connectivity
docker-compose exec api python -c "from app.database import engine; print(engine.execute('SELECT 1').scalar())"

# Reset database
docker-compose down
docker volume rm aquaculture-backend_postgres_data
docker-compose up -d
```

#### Email Notifications Not Working
```bash
# Test SMTP configuration
docker-compose exec api python -c "
from app.services.notification import send_test_email
send_test_email('test@example.com')
"
```

#### High Memory Usage
```bash
# Monitor resource usage
docker stats aquaculture_api

# Adjust memory limits in docker-compose.yml
mem_limit: 512m
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

For support and questions:
- **Documentation**: Check the `/docs` endpoint for API documentation
- **Issues**: Create an issue on the repository for bug reports
- **Email**: Contact the development team for enterprise support

---

## 🎯 Roadmap

### Upcoming Features
- [ ] **Mobile App Integration**: React Native companion app
- [ ] **Machine Learning**: Predictive analytics for water quality
- [ ] **IoT Expansion**: Support for additional sensor types
- [ ] **Blockchain Integration**: Supply chain traceability
- [ ] **Advanced Analytics**: AI-powered insights and recommendations

### Recent Updates
- ✅ **Page-Hinkley Anomaly Detection**: Advanced change point detection
- ✅ **Multilingual Email Alerts**: Arabic, French, and English support
- ✅ **Docker Deployment**: Complete containerization with docker-compose
- ✅ **Real-time Monitoring**: Live sensor data processing and alerts

---

*Built with ❤️ for the aquaculture industry in Algeria*
