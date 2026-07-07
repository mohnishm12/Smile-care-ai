# HealFlow AI — HIPAA Compliance Architecture

## 1. Data Encryption

### At Rest (AES-256)
- **Database**: PostgreSQL TDE (Transparent Data Encryption) via disk-level encryption
  - AWS EBS encryption for volumes (AES-256)
  - Encrypted snapshots for backups
- **File Storage**: S3 server-side encryption (SSE-S3 or SSE-KMS)
- **Backups**: Encrypted archive files (AES-256-GCM)
- **Key Management**: AWS KMS or HashiCorp Vault for key rotation

### In Transit (TLS 1.3)
- **API Endpoints**: TLS 1.3 minimum, enforced at Nginx/AWS Load Balancer
- **Database Connections**: SSL/TLS with certificate validation
- **Redis Connections**: TLS-enabled with AUTH password
- **Internal Services**: mTLS between microservices via service mesh (Istio/Linkerd)

## 2. Access Control

### Authentication
- Multi-factor authentication (MFA) for all admin/doctor accounts
- OAuth 2.0 / OpenID Connect for SSO integration
- JWT tokens with short expiry (30 min access, 7 day refresh)
- Session rotation and revocation capability

### Authorization (RBAC)
| Role | Permissions |
|------|-------------|
| Super Admin | Full system access, audit logs, user management |
| Clinic Admin | Clinic-level settings, staff management, reports |
| Doctor | Patient records, appointments, messaging |
| Nurse/Staff | Limited read/write to assigned patients |
| Patient | Own records only, appointments, messages |

### Audit Logging
- All access to PHI (Protected Health Information) logged
- Login attempts (successful and failed)
- Data modifications with before/after values
- Export/download attempts
- API access patterns

## 3. Audit Logging Configuration

### Log Types
- **Access Logs**: Who accessed what, when, from where
- **Activity Logs**: Create, read, update, delete operations on PHI
- **System Logs**: Infrastructure changes, deployments, scaling events
- **Security Logs**: Authentication attempts, permission changes

### Retention
- Audit logs: 365 days minimum (HIPAA requirement)
- System logs: 90 days
- Metrics: 30 days at full resolution, 1 year at reduced resolution

### Storage
- Centralized logging with immutable log storage (AWS CloudWatch / ELK / Loki)
- Logs shipped via OpenTelemetry or Filebeat
- Access to logs restricted to authorized personnel only

## 4. Backup and Disaster Recovery

### Backup Schedule
- **Database**: Continuous WAL archiving + hourly snapshots
- **File Storage**: Daily incremental, weekly full
- **Configurations**: Version-controlled in Git

### Retention Policy
- Daily backups: 7 days
- Weekly backups: 4 weeks
- Monthly backups: 12 months
- Yearly backups: 7 years (HIPAA requirement)

### Recovery Objectives
- **RPO** (Recovery Point Objective): < 1 hour
- **RTO** (Recovery Time Objective): < 4 hours for critical systems
- **DR Testing**: Quarterly disaster recovery drills

### Disaster Recovery Plan
1. Failover to standby region (multi-region deployment)
2. Restore database from latest WAL archive
3. Spin up application stack via Terraform
4. Verify data integrity and connectivity
5. Switch DNS traffic to DR region

## 5. BAA-Ready Architecture

### Business Associate Agreement (BAA) Requirements
- AWS BAA in place for all covered services
- Sub-processor due diligence for any third-party services
- Data Processing Agreement (DPA) for EU patients (GDPR compliance)

### Data Flow Compliance
- PHI never leaves the production VPC
- All data transfers logged and monitored
- De-identification/minimization where possible
- Patient consent tracking and management

## 6. Consent Management

### Patient Consent Flow
1. **Registration**: Explicit consent for data collection and processing
2. **Opt-in**: Separate consent for marketing / research communications
3. **Revocation**: Patient can withdraw consent at any time
4. **Tracking**: Consent status and history stored in database
5. **Granularity**: Per-purpose consent (appointment reminders, lab results, etc.)

### Consent Storage
- Timestamped consent records with versioning
- Audit trail for consent changes
- Consent expiration handling

## 7. Data Retention and Deletion

### Retention Periods
| Data Type | Retention Period | Rationale |
|-----------|-----------------|-----------|
| Medical Records | 7 years after last visit | HIPAA requirement |
| Billing Records | 7 years | Tax/legal requirements |
| Audit Logs | 6 years | HIPAA security rule |
| Communication Logs | 3 years | Operational need |
| Temporary/Ephemeral | 30 days | Internal processing |
| Marketing Data | Until consent withdrawn | GDPR/CCPA |

### Deletion Policy
- **Hard Delete**: Immediate removal from active database
- **Soft Delete**: Flagged as deleted, purged after retention period
- **Anonymization**: Aggregate data kept for analytics after PII removed
- **Verification**: Post-deletion integrity check and certification

## 8. Security Incident Response

### Incident Types
- Unauthorized access to PHI
- Data breach or leakage
- Ransomware / malware infection
- DDoS attack
- Insider threat

### Response Procedure
1. **Detection**: Automated monitoring alerts (Sentry, Prometheus, WAF)
2. **Containment**: Isolate affected systems, revoke credentials
3. **Analysis**: Determine scope, root cause, affected records
4. **Notification**: Notify affected patients and authorities (within 60 days per HIPAA)
5. **Recovery**: Restore from clean backups, patch vulnerabilities
6. **Post-mortem**: Document lessons learned, update security measures

## 9. Technical Controls

### Network Security
- VPC with private subnets for databases and internal services
- Security groups with least-privilege rules
- WAF (Web Application Firewall) for OWASP Top 10 protection
- DDoS protection (AWS Shield / Cloudflare)
- VPN/PrivateLink for administrative access

### Application Security
- Input validation and sanitization (Pydantic models)
- Parameterized queries to prevent SQL injection
- CSP (Content Security Policy) headers
- XSS and CSRF protection via security middleware
- Rate limiting at API gateway and application level

### Container Security
- Weekly vulnerability scanning (Trivy / Snyk)
- Minimal base images (Alpine / distroless)
- Non-root user execution
- Read-only root filesystem where possible
- Image signing and verification

## 10. Compliance Checklist

### Required Documentation
- [ ] HIPAA Privacy Rule policies and procedures
- [ ] HIPAA Security Rule risk assessment
- [ ] BAA with AWS and all sub-processors
- [ ] Incident response plan
- [ ] Disaster recovery plan
- [ ] Employee training records
- [ ] Audit log review procedures
- [ ] Data retention and disposal policies
- [ ] Patient consent management procedures
- [ ] Breach notification procedures

### Technical Checklist
- [ ] TLS 1.3 enforced for all external communications
- [ ] Database encryption at rest enabled
- [ ] Audit logging configured and monitored
- [ ] MFA enabled for all privileged accounts
- [ ] Automated vulnerability scanning in CI/CD
- [ ] Secrets management (no hardcoded credentials)
- [ ] RBAC implemented and tested
- [ ] Session management with timeouts
- [ ] Rate limiting configured
- [ ] WAF rules active
- [ ] Backups encrypted and tested
- [ ] Incident response tested quarterly